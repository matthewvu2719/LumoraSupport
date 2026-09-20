"""Policy-document tools: search the knowledge base and manage which documents are in it.

Thin wrappers over the ingestion package that take and return plain JSON-friendly values,
so the MCP server can expose them directly.
"""
import base64
import binascii

from langchain_chroma import Chroma

from ingestion import search as _search
from ingestion import store as _store
from ingestion.config import DEFAULT_MIN_SIMILARITY, DEFAULT_TOP_K, DOCUMENT_COVERAGE_MARGIN

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


def _select(candidates: list, k: int) -> list:
    """Pick k results from candidates (best first), making sure every closely matching document
    is represented. Without this, one long document with many similar passages can fill all the
    slots and hide a second document that says something different about the same topic."""
    if not candidates:
        return []
    cutoff = candidates[0].similarity - DOCUMENT_COVERAGE_MARGIN
    chosen, seen = [], set()
    for r in candidates:  # best passage of each closely matching document
        if r.source not in seen and r.similarity >= cutoff:
            chosen.append(r)
            seen.add(r.source)
    chosen = chosen[:k]
    for r in candidates:  # then fill the remaining slots by score
        if len(chosen) >= k:
            break
        if r not in chosen:
            chosen.append(r)
    return sorted(chosen, key=lambda r: r.similarity, reverse=True)


def search_policies(
    query: str,
    k: int = DEFAULT_TOP_K,
    source: str | None = None,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
    store: Chroma | None = None,
) -> list[dict]:
    """Find policy passages relevant to `query`, best first.

    Each result has the passage `text`, a ready-to-quote `citation` (document, page, section)
    and a `similarity` score. An empty list means nothing relevant was found.
    `source` limits the search to one document.
    """
    if not query.strip():
        raise ValueError("Query is empty.")
    k = max(1, min(k, 10))
    # Fetch extra candidates, then choose which k to return (see _select).
    candidates = _search.search(query, k=k * 4, source=source, min_similarity=min_similarity, store=store)
    results = _select(candidates, k) if source is None else candidates[:k]
    return [
        {
            "text": r.text,
            "citation": r.citation,
            "source": r.source,
            "page": r.page,
            "section": r.section,
            "similarity": r.similarity,
        }
        for r in results
    ]


def list_policy_documents(store: Chroma | None = None) -> list[dict]:
    """The documents currently in the knowledge base, newest upload first."""
    return [
        {"source": d.source, "chunks": d.chunks, "uploaded_at": d.uploaded_at}
        for d in _store.list_documents(store)
    ]


def ingest_policy_document(filename: str, content_base64: str, store: Chroma | None = None) -> dict:
    """Add a PDF (sent base64-encoded) to the knowledge base.

    A file with the same name as an existing document replaces it; an identical file is skipped.
    Returns {"filename", "chunks", "replaced", "skipped"}.
    """
    name = filename.strip()
    if not name or "/" in name or "\\" in name or name in (".", "..") or not name.lower().endswith(".pdf"):
        raise ValueError("filename must be a plain file name ending in .pdf")
    try:
        data = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("content_base64 is not valid base64.") from exc
    if not data:
        raise ValueError("The file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"File is too large ({len(data) / 1e6:.1f} MB). The limit is {MAX_UPLOAD_BYTES // 1_000_000} MB.")
    if not data.startswith(b"%PDF"):
        raise ValueError("The file is not a PDF.")
    try:
        result = _store.ingest_document(data, name, store)
    except ValueError:
        raise  # e.g. scanned PDF with no text: the message is already clear
    except Exception as exc:  # pypdf raises several different errors for damaged files
        raise ValueError(f"Could not read the PDF: {exc}") from exc
    return {"filename": result.filename, "chunks": result.chunks,
            "replaced": result.replaced, "skipped": result.skipped}


def delete_policy_document(filename: str, store: Chroma | None = None) -> dict:
    """Remove a document and all of its passages from the knowledge base."""
    deleted = _store.delete_document(filename, store)
    return {"filename": filename, "deleted_chunks": deleted, "found": deleted > 0}
