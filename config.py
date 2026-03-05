import os
from pathlib import Path

# Directories
BASE_DIR       = Path(os.getenv("RAG_WATCH_DIR", str(Path.home() / "rag-watch")))
INBOX_DIR      = BASE_DIR / "inbox"
QUARANTINE_DIR = BASE_DIR / "quarantine"
PROCESSED_DIR  = BASE_DIR / "processed"
LOG_DIR        = BASE_DIR / "logs"

# RAG API
RAG_API_URL = os.getenv("RAG_API_URL", "http://localhost:8000")
RAG_API_KEY = os.getenv("RAG_API_KEY", "")  # Must be set in environment

# ClamAV
CLAMAV_ENABLED = os.getenv("CLAMAV_ENABLED", "true").lower() == "true"
CLAMSCAN_BIN   = os.getenv("CLAMSCAN_BIN", "clamscan")

# Chunking
CHUNK_SIZE    = int(os.getenv("CHUNK_SIZE", "500"))    # words per chunk
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))  # word overlap

# Supported file types
SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}

# Scan result log
SCAN_LOG = LOG_DIR / "scan.log"
INGEST_LOG = LOG_DIR / "ingest.log"
