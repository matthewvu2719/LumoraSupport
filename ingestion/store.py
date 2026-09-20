"""Step 3 of ingestion: embed chunks and manage them in the Chroma vector DB.

A document is identified by its file name (stored as `source` in every chunk's metadata):
  - uploading a file whose name already exists replaces the old version
  - uploading an unchanged file (same content hash) is skipped
  - a document can be listed and deleted
"""
import hashlib
import io
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from ingestion.chunk import chunk_pages
from ingestion.config import CHROMA_DIR, COLLECTION_NAME, EMBEDDING_MODEL
from ingestion.extract import extract_pages


@dataclass
class IngestResult:
    filename: str
    chunks: int      # chunks now stored for this file
    replaced: bool   # an older version was removed
    skipped: bool    # identical file already stored, nothing changed


@dataclass
class DocumentInfo:
    source: str
    chunks: int
    uploaded_at: str


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    """Load the local embedding model once.

    Uses the cached copy without contacting huggingface.co when it exists, so start-up is fast
    and works offline. On the very first run (nothing cached) it downloads the model (~90 MB).
    """
    def load(local_only: bool) -> HuggingFaceEmbeddings:
        return HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={"local_files_only": local_only},
            encode_kwargs={"normalize_embeddings": True},  # unit vectors, so cosine distance is exact
        )

    try:
        return load(local_only=True)
    except OSError:  # not downloaded yet
        return load(local_only=False)


@lru_cache(maxsize=1)
def get_store() -> Chroma:
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=get_embeddings(),
        persist_directory=str(CHROMA_DIR),
        collection_metadata={"hnsw:space": "cosine"},
    )


def _stored(store: Chroma, filename: str) -> dict:
    return store.get(where={"source": filename}, include=["metadatas"])


def ingest_document(data: bytes, filename: str, store: Chroma | None = None) -> IngestResult:
    """Ingest PDF bytes under `filename`, replacing any existing version of that file.

    Extraction and chunking happen before anything is deleted, so an unreadable
    PDF never destroys the version already stored.
    """
    store = store or get_store()
    file_hash = hashlib.sha256(data).hexdigest()

    existing = _stored(store, filename)
    if existing["ids"] and existing["metadatas"][0].get("file_hash") == file_hash:
        return IngestResult(filename, len(existing["ids"]), replaced=False, skipped=True)

    chunks = chunk_pages(extract_pages(io.BytesIO(data)), filename)  # raises on bad/scanned PDFs
    uploaded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for chunk in chunks:
        chunk.metadata.update(file_hash=file_hash, uploaded_at=uploaded_at)

    replaced = bool(existing["ids"])
    if replaced:
        store.delete(ids=existing["ids"])
    store.add_documents(chunks, ids=[f"{filename}::{c.metadata['chunk_index']}" for c in chunks])
    return IngestResult(filename, len(chunks), replaced=replaced, skipped=False)


def ingest_path(path: str | Path, store: Chroma | None = None) -> IngestResult:
    path = Path(path)
    return ingest_document(path.read_bytes(), path.name, store)


def list_documents(store: Chroma | None = None) -> list[DocumentInfo]:
    """One entry per document in the vector DB, newest upload first."""
    store = store or get_store()
    counts: dict[str, int] = defaultdict(int)
    uploaded: dict[str, str] = {}
    for meta in store.get(include=["metadatas"])["metadatas"]:
        counts[meta["source"]] += 1
        uploaded[meta["source"]] = meta.get("uploaded_at", "")
    docs = [DocumentInfo(name, n, uploaded[name]) for name, n in counts.items()]
    return sorted(docs, key=lambda d: d.uploaded_at, reverse=True)


def delete_document(filename: str, store: Chroma | None = None) -> int:
    """Remove every chunk of `filename` from the vector DB. Returns how many were deleted."""
    store = store or get_store()
    ids = _stored(store, filename)["ids"]
    if ids:
        store.delete(ids=ids)
    return len(ids)
