from pydantic import BaseModel


class Citation(BaseModel):
    cited_text: str
    page: int | None = None


class Answer(BaseModel):
    text: str
    citations: list[Citation] = []


def parse_answer(content: list) -> Answer:
    parts: list[str] = []
    citations: list[Citation] = []
    for block in content:
        if getattr(block, "type", None) != "text":
            continue
        parts.append(getattr(block, "text", "") or "")
        for cit in getattr(block, "citations", None) or []:
            if getattr(cit, "type", None) == "page_location":
                citations.append(
                    Citation(
                        cited_text=getattr(cit, "cited_text", "") or "",
                        page=getattr(cit, "start_page_number", None),
                    )
                )
    return Answer(text="".join(parts), citations=citations)
