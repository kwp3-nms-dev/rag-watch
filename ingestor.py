"""
Text extraction, chunking, and ingestion into the RAG API.
"""
import logging
from pathlib import Path
from typing import List

import httpx

from config import (
    CHUNK_OVERLAP, CHUNK_SIZE, RAG_API_KEY, RAG_API_URL, SUPPORTED_EXTENSIONS,
)

log = logging.getLogger("rag-watch.ingestor")


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md"):
        return path.read_text(errors="replace")
    if suffix == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            raise ValueError(f"PDF extraction failed: {e}")
    if suffix == ".docx":
        try:
            import docx
            doc = docx.Document(str(path))
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception as e:
            raise ValueError(f"DOCX extraction failed: {e}")
    raise ValueError(f"Unsupported file type: {suffix}")


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    words = text.split()
    if not words:
        return []
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunks.append(" ".join(words[start:end]))
        start += chunk_size - overlap
    return [c for c in chunks if c.strip()]


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def ingest_chunks(collection: str, chunks: List[str], source: str) -> int:
    """POST each chunk to the RAG API. Returns number of chunks ingested."""
    headers = {"X-API-Key": RAG_API_KEY, "Content-Type": "application/json"}
    ingested = 0
    with httpx.Client(timeout=60) as client:
        for i, chunk in enumerate(chunks):
            payload = {
                "collection": collection,
                "text": chunk,
                "metadata": {"source": source, "chunk": i},
            }
            try:
                resp = client.post(f"{RAG_API_URL}/ingest", json=payload, headers=headers)
                if resp.status_code == 200:
                    ingested += 1
                else:
                    log.error("Ingest chunk %d failed (%s): %s", i, resp.status_code, resp.text)
            except Exception as e:
                log.error("Ingest chunk %d error: %s", i, e)
    return ingested
