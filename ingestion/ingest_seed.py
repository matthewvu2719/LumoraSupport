"""Load every PDF in data/policies/ into the vector DB (data/chroma/).

Run:  python -m ingestion.ingest_seed
Safe to rerun: unchanged files are skipped, changed files with the same name are replaced.
"""
from ingestion.config import POLICIES_DIR
from ingestion.store import ingest_path, list_documents


def main() -> None:
    pdfs = sorted(POLICIES_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {POLICIES_DIR}")
        return

    for pdf in pdfs:
        try:
            result = ingest_path(pdf)
        except Exception as exc:  # one bad file should not stop the rest
            print(f"  FAILED    {pdf.name}: {exc}")
            continue
        status = "skipped (unchanged)" if result.skipped else "replaced" if result.replaced else "ingested"
        print(f"  {status:<20} {pdf.name} ({result.chunks} chunks)")

    print("\nDocuments in the vector DB:")
    for doc in list_documents():
        print(f"  {doc.source}: {doc.chunks} chunks, uploaded {doc.uploaded_at}")


if __name__ == "__main__":
    main()
