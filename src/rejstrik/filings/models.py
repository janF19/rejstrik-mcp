import unicodedata

from pydantic import BaseModel

_KEYWORDS = (
    "ucetni zaverka",
    "vyrocni zprava",
    "rozvaha",
    "vykaz zisku",
    "zprava auditora",
)


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    no_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return no_marks.lower()


def classify_financial(title: str) -> bool:
    norm = _normalize(title)
    return any(kw in norm for kw in _KEYWORDS)


class Filing(BaseModel):
    title: str
    year: int | None = None
    pdf_url: str
    is_financial_statement: bool = False
