"""
routers/pdf.py — PDF upload, list, and delete endpoints.
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from core.security import get_current_user
from database import get_db
from models.document import Document
from models.user import User
from schemas.pdf import DeleteResponse, DocumentListResponse, DocumentOut, UploadResponse
from services.pdf_service import delete_document_vectors, delete_upload_file, ingest_pdf, save_upload

router = APIRouter(prefix="/pdf", tags=["PDF Documents"])

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_pdf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload and ingest a PDF.
    - Validates MIME type and file size.
    - Saves file to disk.
    - Runs LangChain ingestion pipeline → ChromaDB.
    - Records metadata in SQLite.
    """
    # Validate file type
    if not file.content_type or "pdf" not in file.content_type.lower():
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only PDF files are accepted.",
            )

    # Read file and check size
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum size is 50 MB.",
        )
    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    original_filename = file.filename or "document.pdf"

    # Save file to disk
    file_path = save_upload(file_bytes, original_filename)

    # Create a DB record first (to get the doc_id for metadata)
    doc_record = Document(
        filename=file_path,
        original_filename=original_filename,
        chunk_count=0,
        user_id=current_user.id,
    )
    db.add(doc_record)
    db.commit()
    db.refresh(doc_record)

    # Run ingestion pipeline
    try:
        chunk_count = ingest_pdf(
            file_path=file_path,
            original_filename=original_filename,
            user_id=current_user.id,
            doc_id=doc_record.id,
        )
    except Exception as e:
        # Rollback: delete DB record and file
        db.delete(doc_record)
        db.commit()
        delete_upload_file(file_path)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to process PDF: {str(e)}",
        )

    # Update chunk count
    doc_record.chunk_count = chunk_count
    db.commit()
    db.refresh(doc_record)

    return UploadResponse(
        message="PDF uploaded and ingested successfully.",
        document_id=doc_record.id,
        original_filename=original_filename,
        chunk_count=chunk_count,
    )


@router.get("/list", response_model=DocumentListResponse)
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all PDFs uploaded by the current user."""
    docs = (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .order_by(Document.uploaded_at.desc())
        .all()
    )
    return DocumentListResponse(
        documents=[DocumentOut.model_validate(d) for d in docs],
        total=len(docs),
    )


@router.delete("/{document_id}", response_model=DeleteResponse)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a document: removes the DB record, the physical PDF file,
    and all associated ChromaDB vectors.
    """
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.user_id == current_user.id)
        .first()
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    # Remove vectors from ChromaDB
    delete_document_vectors(user_id=current_user.id, doc_id=document_id)

    # Remove physical file
    delete_upload_file(doc.filename)

    # Remove DB record
    db.delete(doc)
    db.commit()

    return DeleteResponse(message="Document deleted successfully.", document_id=document_id)
