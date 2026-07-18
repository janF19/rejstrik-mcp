import io

from pydantic import BaseModel
from pypdf import PdfReader

_NO_TEXT_NOTE = (
    "No extractable text layer on this page — the filing is likely a scanned "
    "image. Read the PDF from file_path with your own capabilities, or — on a "
    "host without filesystem access — call read_filing_page_images for this "
    "page range to get legible PNGs."
)


class PageText(BaseModel):
    page: int
    has_text: bool
    text: str
    note: str | None = None


def parse_page_range(
    spec: str, *, page_count: int, max_pages: int = 20
) -> tuple[list[int], str | None]:
    wanted: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start, end = int(start_s), int(end_s)
            wanted.extend(range(start, end + 1))
        else:
            wanted.append(int(part))
    seen: set[int] = set()
    ordered: list[int] = []
    for page in sorted(wanted):
        if 1 <= page <= page_count and page not in seen:
            seen.add(page)
            ordered.append(page)
    message: str | None = None
    if len(ordered) > max_pages:
        message = (
            f"Requested {len(ordered)} pages; capped to the first {max_pages}. "
            f"Call read_filing_text again with a later page range for the rest."
        )
        ordered = ordered[:max_pages]
    return ordered, message


def extract_pages_text(data: bytes, pages: list[int]) -> list[PageText]:
    reader = PdfReader(io.BytesIO(data))
    total = len(reader.pages)
    out: list[PageText] = []
    for page in pages:
        if page < 1 or page > total:
            out.append(
                PageText(
                    page=page,
                    has_text=False,
                    text="",
                    note=f"Page {page} is out of range (document has {total} pages).",
                )
            )
            continue
        text = reader.pages[page - 1].extract_text() or ""
        if text.strip():
            out.append(PageText(page=page, has_text=True, text=text))
        else:
            out.append(PageText(page=page, has_text=False, text="", note=_NO_TEXT_NOTE))
    return out
