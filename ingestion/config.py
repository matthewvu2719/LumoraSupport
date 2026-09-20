"""Central settings for the document ingestion pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Where source policy PDFs live and where the vector DB is persisted.
POLICIES_DIR = ROOT / "data" / "policies"
CHROMA_DIR = ROOT / "data" / "chroma"
COLLECTION_NAME = "policies"

# Local embedding model (runs on CPU, no API key). 384-dim vectors.
# If you change this, delete data/chroma and re-ingest: vectors from
# different models are not comparable.
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Chunking: sizes are in characters. all-MiniLM-L6-v2 truncates input at
# ~256 tokens (about 1000 characters), so chunks are kept below that.
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120

# Default number of chunks returned by a search.
DEFAULT_TOP_K = 6

# Matches scoring below this are treated as "not found" (relevant chunks score ~0.5-0.8,
# off-topic questions score under ~0.2 on the sample policies).
DEFAULT_MIN_SIMILARITY = 0.30

# A document counts as "closely matching" if its best passage scores within this margin of the
# overall best passage. Such documents are always represented in policy search results, so that
# conflicting documents are never hidden behind one document with many similar passages.
DOCUMENT_COVERAGE_MARGIN = 0.20
