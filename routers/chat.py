"""
routers/chat.py — Chat/query endpoint.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.security import get_current_user
from database import get_db
from models.document import Document
from models.user import User
from schemas.chat import ChatRequest, ChatResponse
from services.rag_service import query_rag

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/ask", response_model=ChatResponse)
def ask(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Ask a question about uploaded PDFs.

    Optionally restrict retrieval to a specific document by providing
    `document_id` in the request body.
    """
    question = payload.question.strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty.",
        )

    # If document_id is provided, verify it belongs to the user
    if payload.document_id is not None:
        doc = (
            db.query(Document)
            .filter(
                Document.id == payload.document_id,
                Document.user_id == current_user.id,
            )
            .first()
        )
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found.",
            )

    try:
        response = query_rag(
            question=question,
            user_id=current_user.id,
            doc_id=payload.document_id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"RAG query failed: {str(e)}",
        )

    return response
