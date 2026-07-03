"""
services/pdf_service.py — PDF ingestion pipeline.

Flow:
  PDF file → PyPDF text extraction → RecursiveCharacterTextSplitter
  → HuggingFace embeddings (all-MiniLM-L6-v2) → ChromaDB (per-user collection)

Each chunk is stored with metadata: source filename, page number, doc_id, user_id.
Compatible with LangChain 1.x + chromadb 1.x.
"""
import os
import uuid
from pathlib import Path
from typing import Any

import chromadb
from langchain_community.document_loaders import PyPDFLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import settings

# ── Singleton: HuggingFace Embedding model ────────────────────────────────────
# Loaded once; model is cached locally by sentence-transformers
_embedding_model: HuggingFaceEmbeddings | None = None


def get_embeddings() -> HuggingFaceEmbeddings:
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    return _embedding_model


# ── Singleton: ChromaDB persistent client ────────────────────────────────────
_chroma_client: Any = None


def get_chroma_client() -> Any:
    global _chroma_client
    if _chroma_client is None:
        persist_dir = str(Path(settings.chroma_persist_dir).resolve())
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=persist_dir)
    return _chroma_client


def _collection_name(user_id: int) -> str:
    """Each user gets an isolated ChromaDB collection."""
    return f"user_{user_id}"


# ── Core ingest function ──────────────────────────────────────────────────────

def ingest_pdf(
    file_path: str,
    original_filename: str,
    user_id: int,
    doc_id: int,
) -> int:
    """
    Ingest a PDF into ChromaDB.
    Returns the number of chunks stored.
    """
    # 1. Load PDF pages with LangChain PyPDFLoader
    loader = PyPDFLoader(file_path)
    pages = loader.load()

    if not pages:
        raise ValueError(
            f"Could not extract text from '{original_filename}'. Is it a scanned PDF?"
        )

    # 2. Split into chunks
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", " ", ""],
    )
    chunks = splitter.split_documents(pages)

    if not chunks:
        raise ValueError("No text chunks could be created from this PDF.")

    # 3. Get/create per-user ChromaDB collection
    embeddings = get_embeddings()
    client = get_chroma_client()

    try:
        # chromadb >= 1.x: get_or_create_collection with configuration dict
        collection = client.get_or_create_collection(
            name=_collection_name(user_id),
            metadata={"hnsw:space": "cosine"},
        )
    except TypeError:
        # Fallback for older chromadb API
        collection = client.get_or_create_collection(
            name=_collection_name(user_id),
        )

    texts = [chunk.page_content for chunk in chunks]
    metadatas = [
        {
            "source": original_filename,
            "page": str(chunk.metadata.get("page", 0)),
            "doc_id": str(doc_id),
            "user_id": str(user_id),
        }
        for chunk in chunks
    ]
    ids = [str(uuid.uuid4()) for _ in chunks]

    # 4. Embed + upsert in batches of 100 to avoid memory spikes
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i : i + batch_size]
        batch_meta = metadatas[i : i + batch_size]
        batch_ids = ids[i : i + batch_size]
        batch_embeddings = embeddings.embed_documents(batch_texts)
        collection.upsert(
            ids=batch_ids,
            documents=batch_texts,
            metadatas=batch_meta,
            embeddings=batch_embeddings,
        )

    return len(chunks)


def delete_document_vectors(user_id: int, doc_id: int) -> None:
    """Remove all ChromaDB vectors belonging to a specific document."""
    client = get_chroma_client()
    col_name = _collection_name(user_id)

    try:
        collection = client.get_collection(col_name)
        # Fetch IDs where doc_id matches, then delete them
        results = collection.get(where={"doc_id": str(doc_id)})
        ids_to_delete = results.get("ids", [])
        if ids_to_delete:
            collection.delete(ids=ids_to_delete)
    except Exception:
        # Collection may not exist yet; safe to ignore
        pass


def save_upload(file_bytes: bytes, original_filename: str) -> str:
    """
    Save uploaded PDF bytes to the uploads directory.
    Returns the absolute path of the saved file.
    """
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(original_filename).suffix or ".pdf"
    unique_name = f"{uuid.uuid4().hex}{ext}"
    dest = upload_dir / unique_name
    dest.write_bytes(file_bytes)
    return str(dest.resolve())


def delete_upload_file(file_path: str) -> None:
    """Delete the physical PDF file from disk."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception:
        pass
