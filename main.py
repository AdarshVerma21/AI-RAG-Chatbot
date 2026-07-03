"""
main.py — FastAPI application entry point.

Startup tasks:
  - Create SQLite tables (if not exist)
  - Ensure upload / chroma directories exist
  - Register routers with CORS middleware
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import Base, engine  # Base must come before model imports
import models  # noqa: F401 — importing triggers User + Document registration with Base.metadata
from routers import auth, chat, pdf


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ────────────────────────────────────────────────────────────────
    # Create all DB tables
    Base.metadata.create_all(bind=engine)

    # Ensure required directories exist
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.chroma_persist_dir).mkdir(parents=True, exist_ok=True)

    print("[OK] Database tables created.")
    print(f"[OK] Upload dir: {settings.upload_dir}")
    print(f"[OK] ChromaDB dir: {settings.chroma_persist_dir}")

    yield  # application runs here

    # ── Shutdown ───────────────────────────────────────────────────────────────
    print("[INFO] Shutting down PDF RAG Chatbot API.")


app = FastAPI(
    title="PDF RAG Chatbot API",
    description=(
        "Full-stack PDF Retrieval-Augmented Generation chatbot. "
        "Upload PDFs, ask questions, get grounded answers powered by Groq + ChromaDB."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
# Allow Streamlit (and any localhost port during dev) to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(pdf.router)
app.include_router(chat.router)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def root():
    return {
        "status": "ok",
        "service": "PDF RAG Chatbot API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy"}
