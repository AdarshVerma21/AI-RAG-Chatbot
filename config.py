"""
config.py — Application settings loaded from .env
Uses Pydantic BaseSettings for type-safe config.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Groq LLM ──────────────────────────────────
    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"

    # ── JWT ────────────────────────────────────────
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # ── Database ───────────────────────────────────
    database_url: str = "sqlite:///./rag_chatbot.db"

    # ── ChromaDB ───────────────────────────────────
    chroma_persist_dir: str = "./chroma_db"

    # ── File uploads ──────────────────────────────
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 50


settings = Settings()
