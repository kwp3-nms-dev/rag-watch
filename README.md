# RAG Watch

A file watcher that automatically scans and ingests documents into a RAG pipeline.

Drop a file into a watched folder and it gets virus-scanned, checked for prompt injection and obfuscation, then ingested into the correct Qdrant collection via the RAG API.

## Features
- **ClamAV** virus scanning
- **Prompt injection** detection (18 patterns)
- **Obfuscation** detection (zero-width chars, homoglyphs, base64 blobs, high non-ASCII ratio)
- **Auto-collection creation** when a new subfolder is added
- **Multi-format support:** `.txt`, `.md`, `.pdf`, `.docx`
- **Quarantine** with scan report sidecars for flagged files
- Runs as a systemd user service

## Directory layout

```
~/rag-watch/
├── inbox/
│   └── <collection_name>/   ← drop files here
├── quarantine/              ← flagged files + scan reports
├── processed/               ← successfully ingested files
└── logs/scan.log
```

## Requirements
- RAG API running at `localhost:8000`
- ClamAV installed (`sudo apt install clamav && sudo freshclam`)

## Install

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configure

Set environment variables (or use the systemd service file):

```bash
export RAG_API_URL=http://localhost:8000
export RAG_API_KEY=your-api-key
export RAG_WATCH_DIR=~/rag-watch   # optional, defaults to ~/rag-watch
export CLAMAV_ENABLED=true
```

## Run

```bash
python watcher.py
```

## Run as a systemd service

```bash
mkdir -p ~/.config/systemd/user
cp rag-watcher.service ~/.config/systemd/user/
# Edit the service file and set RAG_API_KEY
systemctl --user daemon-reload
systemctl --user enable --now rag-watcher
```

## Adding a new collection
Create a subfolder under `inbox/` — the watcher will automatically create the Qdrant collection and ingest any files already inside it.
