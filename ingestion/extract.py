"""Step 1 of ingestion: pull text out of a PDF and clean it, page by page."""
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Union

from pypdf import PdfReader

PdfSource = Union[str, Path, BinaryIO]  # a path, or a file-like object (e.g. a Streamlit upload)

# "Page 3", "3", "3 / 10", "Page 3 of 10"
_PAGE_NUMBER = re.compile(r"^(page\s*)?\d+(\s*(/|of)\s*\d+)?$", re.IGNORECASE)
# "2. Annual plan refunds", "3.1 Scope": a short numbered line without sentence punctuation
_HEADING = re.compile(r"^\d+(\.\d+)*\.?\s+\S.{0,80}$")
_SENTENCE_END = (".", "!", "?", ":", ";")


@dataclass
class Page:
    number: int  # 1-based, as a reader would see it
    text: str


def is_heading(line: str) -> bool:
    return bool(_HEADING.match(line)) and not line.endswith(_SENTENCE_END)


def _normalize(text: str) -> str:
    """Unicode-normalize (ligatures such as 'ﬁ' become 'fi') and strip control characters."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\x00", "").replace("­", "")  # null bytes, soft hyphens
    return re.sub(r"[ \t]+", " ", text)


def _find_repeated_lines(pages_lines: list[list[str]]) -> set[str]:
    """Lines that show up on most pages are running headers/footers. Needs 3+ pages to be meaningful."""
    if len(pages_lines) < 3:
        return set()
    counts = Counter(line for lines in pages_lines for line in set(lines) if len(line) < 100)
    threshold = max(2, int(len(pages_lines) * 0.6))
    return {line for line, n in counts.items() if n >= threshold}


def _unwrap(lines: list[str]) -> str:
    """Rejoin lines that were only wrapped by the page width, keeping headings and paragraphs apart."""
    out: list[str] = []
    for line in lines:
        if not line:  # blank line = paragraph break
            if out and out[-1] != "":
                out.append("")
            continue
        if not out or out[-1] == "":
            out.append(line)
        elif is_heading(out[-1]) or is_heading(line):
            out.append(line)  # headings stay on their own line
        elif out[-1].endswith(_SENTENCE_END) and line[0].isupper():
            out.append(line)  # previous sentence finished: start a new paragraph
        elif out[-1].endswith("-") and line[0].islower():
            out[-1] = out[-1][:-1] + line  # "sub-\nscription" -> "subscription"
        else:
            out[-1] = f"{out[-1]} {line}"
    return "\n".join(out).strip()


def extract_pages(source: PdfSource) -> list[Page]:
    """Return cleaned text for each page that has any. Raises ValueError if the PDF has no text layer."""
    reader = PdfReader(source)
    raw = [_normalize(page.extract_text() or "") for page in reader.pages]
    pages_lines = [[ln.strip() for ln in text.splitlines()] for text in raw]

    repeated = _find_repeated_lines(pages_lines)
    pages: list[Page] = []
    for i, lines in enumerate(pages_lines, start=1):
        kept = [ln for ln in lines if ln not in repeated and not _PAGE_NUMBER.match(ln)]
        text = _unwrap(kept)
        if text:
            pages.append(Page(number=i, text=text))

    if not pages:
        raise ValueError("No text found in PDF. It may be a scanned document that needs OCR.")
    return pages
