"""
services/rag_service.py — LangChain RAG chain using ChromaDB + Groq.

Uses LangChain Expression Language (LCEL) pipeline — compatible with LangChain 1.x.

Flow:
  User question → embed (HuggingFace) → similarity_search (ChromaDB)
  → build context prompt → Groq (llama-3.3-70b-versatile) → answer + sources
"""
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq

from config import settings
from schemas.chat import ChatResponse, SourceChunk
from services.pdf_service import get_chroma_client, get_embeddings

# ── System prompt ─────────────────────────────────────────────────────────────
_SYSTEM_MSG = """You are a helpful assistant that answers questions based on the provided document context.

Use ONLY the following context to answer the question. If the answer is not contained within the context, say "I don't have enough information in the uploaded documents to answer that question."

Context:
{context}"""

RAG_PROMPT = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM_MSG),
    ("human", "{question}"),
])


def _format_docs(docs: list[Document]) -> str:
    return "\n\n---\n\n".join(d.page_content for d in docs)


# ── LLM singleton ─────────────────────────────────────────────────────────────
_llm: ChatGroq | None = None


def get_llm() -> ChatGroq:
    global _llm
    if _llm is None:
        _llm = ChatGroq(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            temperature=0.1,
            max_tokens=2048,
        )
    return _llm


# ── RAG query function ────────────────────────────────────────────────────────

def query_rag(
    question: str,
    user_id: int,
    doc_id: int | None = None,
    top_k: int = 4,
) -> ChatResponse:
    """
    Run a RAG query against the user's ChromaDB collection.

    Args:
        question: The user's question string.
        user_id:  Authenticated user's ID (scopes the vector search).
        doc_id:   Optional document ID to restrict retrieval to one file.
        top_k:    Number of chunks to retrieve.

    Returns:
        ChatResponse with answer text and source chunk list.
    """
    collection_name = f"user_{user_id}"
    client = get_chroma_client()

    # Verify the collection exists and has documents
    try:
        collection = client.get_collection(collection_name)
        if collection.count() == 0:
            return ChatResponse(
                answer="No documents have been uploaded yet. Please upload a PDF first.",
                sources=[],
                question=question,
            )
    except Exception:
        return ChatResponse(
            answer="No documents have been uploaded yet. Please upload a PDF first.",
            sources=[],
            question=question,
        )

    # Build LangChain Chroma vector store wrapper
    embeddings = get_embeddings()
    vectorstore = Chroma(
        client=client,
        collection_name=collection_name,
        embedding_function=embeddings,
    )

    # Build search kwargs — optionally filter to a single document
    search_kwargs: dict = {"k": top_k}
    if doc_id is not None:
        search_kwargs["filter"] = {"doc_id": str(doc_id)}

    retriever = vectorstore.as_retriever(search_kwargs=search_kwargs)

    # ── LCEL pipeline ─────────────────────────────────────────────────────────
    # 1. Retrieve relevant docs
    # 2. Format into context string + pass question through
    # 3. Format prompt
    # 4. Call Groq LLM
    # 5. Parse to string

    llm = get_llm()

    # First retrieve docs (needed both for context and for source citations)
    source_docs: list[Document] = retriever.invoke(question)

    if not source_docs:
        # No relevant chunks found
        return ChatResponse(
            answer="I couldn't find relevant information in your uploaded documents to answer that question.",
            sources=[],
            question=question,
        )

    context = _format_docs(source_docs)

    # Build and invoke the chain
    chain = RAG_PROMPT | llm | StrOutputParser()
    answer = chain.invoke({"context": context, "question": question})

    # Build deduplicated source chunks for the response
    seen_contents: set[str] = set()
    sources: list[SourceChunk] = []
    for doc in source_docs:
        content_preview = doc.page_content[:300]
        if content_preview in seen_contents:
            continue
        seen_contents.add(content_preview)

        meta = doc.metadata or {}
        page_str = meta.get("page", None)
        try:
            page_num = int(page_str) + 1 if page_str is not None else None  # 1-indexed
        except (ValueError, TypeError):
            page_num = None

        sources.append(
            SourceChunk(
                content=doc.page_content,
                page=page_num,
                source=meta.get("source", "Unknown"),
            )
        )

    return ChatResponse(answer=answer, sources=sources, question=question)
