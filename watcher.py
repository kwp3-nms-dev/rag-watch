"""
RAG Watch — monitors inbox/, scans, and ingests documents automatically.

Directory layout:
  /home/ken/rag-watch/
    inbox/<collection_name>/<file>   ← drop files here
    quarantine/<collection>/<file>   ← flagged files land here
    processed/<collection>/<file>    ← clean ingested files land here
    logs/                            ← scan.log, ingest.log
"""
import logging
import logging.handlers
import shutil
import sys
import time
from pathlib import Path

import httpx
import requests
from watchdog.events import FileCreatedEvent, DirCreatedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from config import (
    INBOX_DIR, QUARANTINE_DIR, PROCESSED_DIR, LOG_DIR,
    RAG_API_URL, RAG_API_KEY, SCAN_LOG, INGEST_LOG,
)
from ingestor import chunk_text, extract_text, ingest_chunks, is_supported
from scanner import scan_file


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Console
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # Rotating scan log
    fh = logging.handlers.RotatingFileHandler(SCAN_LOG, maxBytes=5_000_000, backupCount=5)
    fh.setFormatter(fmt)
    root.addHandler(fh)


log = logging.getLogger("rag-watch")


# ---------------------------------------------------------------------------
# Qdrant collection management
# ---------------------------------------------------------------------------

def create_collection(name: str, vector_size: int = 2560) -> bool:
    """Create a Qdrant collection via the RAG API's Qdrant proxy, or directly."""
    # We talk to Qdrant directly here since the RAG API doesn't expose collection creation
    from config import RAG_API_URL, QDRANT_URL
    import httpx
    qdrant_url = QDRANT_URL
    try:
        # Check if already exists
        r = httpx.get(f"{qdrant_url}/collections/{name}", timeout=5)
        if r.status_code == 200:
            log.info("Collection '%s' already exists", name)
            return True
        # Create it
        r = httpx.put(
            f"{qdrant_url}/collections/{name}",
            json={"vectors": {"size": vector_size, "distance": "Cosine"}},
            timeout=10,
        )
        if r.status_code in (200, 201):
            log.info("Created Qdrant collection '%s'", name)
            return True
        log.error("Failed to create collection '%s': %s", name, r.text)
        return False
    except Exception as e:
        log.error("Error creating collection '%s': %s", name, e)
        return False


# ---------------------------------------------------------------------------
# File processing pipeline
# ---------------------------------------------------------------------------

def process_file(file_path: Path) -> None:
    """Full pipeline: extract → scan → quarantine or ingest → move."""
    if not file_path.exists() or not file_path.is_file():
        return
    if not is_supported(file_path):
        log.info("Skipping unsupported file type: %s", file_path.name)
        return

    # Derive collection from parent folder name
    collection = file_path.parent.name
    log.info("Processing '%s' → collection '%s'", file_path.name, collection)

    # 1. Extract text
    try:
        text = extract_text(file_path)
    except Exception as e:
        log.error("Text extraction failed for '%s': %s", file_path, e)
        _move_to(file_path, QUARANTINE_DIR / collection, reason="extraction_failed")
        return

    if not text.strip():
        log.warning("Empty content in '%s', skipping", file_path.name)
        return

    # 2. Security scan
    result = scan_file(file_path, text)
    if not result.clean:
        reasons = "; ".join(result.reasons)
        log.warning("QUARANTINE '%s': %s", file_path.name, reasons)
        _move_to(file_path, QUARANTINE_DIR / collection, reason="security_flag")
        # Write a sidecar report
        report = QUARANTINE_DIR / collection / (file_path.stem + ".scan_report.txt")
        report.write_text(f"File: {file_path.name}\nReasons:\n" + "\n".join(f"  - {r}" for r in result.reasons))
        return

    # 3. Chunk and ingest
    chunks = chunk_text(text)
    log.info("Ingesting %d chunks from '%s' into '%s'", len(chunks), file_path.name, collection)
    ingested = ingest_chunks(collection, chunks, source=file_path.name)
    log.info("Ingested %d/%d chunks from '%s'", ingested, len(chunks), file_path.name)

    # 4. Move to processed
    _move_to(file_path, PROCESSED_DIR / collection)


def _move_to(src: Path, dest_dir: Path, reason: str = "") -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    # Avoid collisions
    if dest.exists():
        dest = dest_dir / f"{src.stem}_{int(time.time())}{src.suffix}"
    shutil.move(str(src), str(dest))
    log.info("Moved '%s' → %s%s", src.name, dest_dir, f" ({reason})" if reason else "")


# ---------------------------------------------------------------------------
# Watchdog event handler
# ---------------------------------------------------------------------------

class InboxHandler(FileSystemEventHandler):

    def on_created(self, event):
        path = Path(event.src_path)

        if isinstance(event, DirCreatedEvent):
            # New subfolder = new collection
            collection = path.name
            log.info("New folder detected: '%s' — creating RAG collection", collection)
            create_collection(collection)
            # Ingest any files already in the folder
            for f in path.iterdir():
                if f.is_file():
                    time.sleep(0.5)  # brief pause for file to finish writing
                    process_file(f)
            return

        if isinstance(event, FileCreatedEvent):
            # Only process files directly inside a collection subfolder
            if path.parent.parent != INBOX_DIR:
                return
            time.sleep(1)  # wait for file write to complete
            process_file(path)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    setup_logging()
    log.info("RAG Watch starting — monitoring %s", INBOX_DIR)

    # Ensure inbox collection folders exist
    INBOX_DIR.mkdir(parents=True, exist_ok=True)

    observer = Observer()
    observer.schedule(InboxHandler(), str(INBOX_DIR), recursive=True)
    observer.start()
    log.info("Watching for changes...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Shutting down...")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
