"""
schemas/pdf.py — Pydantic schemas for PDF upload/list/delete endpoints.
"""
from datetime import datetime

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: int
    filename: str
    original_filename: str
    chunk_count: int
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    documents: list[DocumentOut]
    total: int


class DeleteResponse(BaseModel):
    message: str
    document_id: int


class UploadResponse(BaseModel):
    message: str
    document_id: int
    original_filename: str
    chunk_count: int
