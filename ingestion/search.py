"""Step 4 of ingestion: semantic search over the stored policy chunks, with sources for citations."""
from dataclasses import dataclass

from langchain_chroma import Chroma

from ingestion.config import DEFAULT_TOP_K
from ingestion.store import get_store


@dataclass
class SearchResult:
    text: str
    source: str       # document file name
    page: int
    section: str      # section heading, "" if none
    similarity: float  # 1.0 = identical meaning, 0 = unrelated (cosine similarity)

    @property
    def citation(self) -> str:
        section = f", {self.section}" if self.section else ""
        return f"{self.source}, page {self.page}{section}"


def search(
    query: str,
    k: int = DEFAULT_TOP_K,
    source: str | None = None,
    min_similarity: float = 0.0,
    store: Chroma | None = None,
) -> list[SearchResult]:
    """Return the `k` chunks closest in meaning to `query`, best first.

    source          restrict the search to one document (by file name)
    min_similarity  drop weak matches, so an off-topic question returns nothing
                    instead of the least-bad chunks
    """
    store = store or get_store()
    hits = store.similarity_search_with_score(
        query, k=k, filter={"source": source} if source else None
    )
    results = [
        SearchResult(
            text=doc.page_content,
            source=doc.metadata["source"],
            page=doc.metadata["page"],
            section=doc.metadata.get("section", ""),
            similarity=round(1 - distance, 4),  # the collection uses cosine distance
        )
        for doc, distance in hits
    ]
    return [r for r in results if r.similarity >= min_similarity]


def format_results(results: list[SearchResult]) -> str:
    """Render results as text for an LLM, each chunk labelled with the citation to quote."""
    if not results:
        return "No relevant passages found in the uploaded policy documents."
    return "\n\n".join(f"[Source: {r.citation}]\n{r.text}" for r in results)
