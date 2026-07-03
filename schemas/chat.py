"""
schemas/chat.py — Pydantic schemas for chat/query endpoints.
"""
from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str
    document_id: int | None = None  # Optional: restrict to a specific document


class SourceChunk(BaseModel):
    content: str
    page: int | None = None
    source: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]
    question: str
