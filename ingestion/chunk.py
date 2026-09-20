"""Step 2 of ingestion: split cleaned pages into chunks, each carrying metadata for citations."""
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ingestion.config import CHUNK_OVERLAP, CHUNK_SIZE
from ingestion.extract import Page, is_heading


def _split_sections(pages: list[Page]) -> list[tuple[int, str, str]]:
    """Group text into (page, heading, body) sections.

    A heading line starts a new section. A section that runs onto the next page keeps
    its heading, so the text on that page is still labelled with the right section.
    """
    sections: list[tuple[int, str, str]] = []
    heading = ""
    for page in pages:
        body: list[str] = []
        for line in page.text.splitlines():
            if is_heading(line):
                if body:
                    sections.append((page.number, heading, "\n".join(body)))
                heading, body = line, []
            elif line.strip():
                body.append(line)
        if body:
            sections.append((page.number, heading, "\n".join(body)))
    return sections


def chunk_pages(pages: list[Page], source: str) -> list[Document]:
    """Split pages into section-aware chunks.

    Every chunk is prefixed with its section heading so it still makes sense on its own
    when retrieved, and carries this metadata (Chroma accepts only str/int/float/bool):
      source       file name, used for citations and for replacing a re-uploaded file
      page         1-based page number
      section      section heading, or "" if the text came before the first heading
      chunk_index  position of the chunk within the document
    """
    chunks: list[Document] = []
    for page_number, heading, body in _split_sections(pages):
        prefix = f"{heading}\n" if heading else ""
        # Leave room for the heading so the finished chunk stays within CHUNK_SIZE.
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=max(CHUNK_SIZE - len(prefix), 200),
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " ", ""],
            keep_separator="end",  # a sentence's full stop stays with that sentence
        )
        for text in splitter.split_text(body):
            chunks.append(Document(
                page_content=prefix + text,
                metadata={
                    "source": source,
                    "page": page_number,
                    "section": heading,
                    "chunk_index": len(chunks),
                },
            ))
    return chunks
