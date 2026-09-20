"""Try the search against the real vector DB.

Run:  python -m ingestion.check_retrieval                  # built-in sample questions
      python -m ingestion.check_retrieval "your question"  # your own question
"""
import sys

from ingestion.config import DEFAULT_MIN_SIMILARITY
from ingestion.search import search

SAMPLE_QUESTIONS = [
    "What is the current refund policy?",
    "What is the weather in Paris today?",  # off-topic: should score low
]
MIN_SIMILARITY = DEFAULT_MIN_SIMILARITY  # results below this are treated as "not found"


def main() -> None:
    for question in sys.argv[1:] or SAMPLE_QUESTIONS:
        print(f"\nQ: {question}")
        results = search(question)
        if not results:
            print("   (vector DB is empty: run python -m ingestion.ingest_seed first)")
            continue
        for r in results:
            mark = " " if r.similarity >= MIN_SIMILARITY else "x"
            print(f"  {mark} {r.similarity:.3f}  {r.citation}" + r.text[:150].replace("\n", " | ")
)
        if results[0].similarity < MIN_SIMILARITY:
            print("   -> no relevant match (best score below threshold)")


if __name__ == "__main__":
    main()
