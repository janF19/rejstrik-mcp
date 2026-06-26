import base64
from typing import Protocol, TypeVar

import anthropic
from pydantic import BaseModel

from rejstrik.documents.answer import Answer, parse_answer
from rejstrik.documents.config import resolve_model
from rejstrik.documents.source import PdfSource

T = TypeVar("T", bound=BaseModel)


def pdf_block(source: PdfSource, citations: bool = False, cache: bool = False) -> dict:
    block: dict = {
        "type": "document",
        "source": {
            "type": "base64",
            "media_type": "application/pdf",
            "data": base64.standard_b64encode(source.data).decode(),
        },
    }
    if citations:
        block["citations"] = {"enabled": True}
    if cache:
        block["cache_control"] = {"type": "ephemeral"}
    return block


class DocumentLLM(Protocol):
    def extract(self, source: PdfSource, schema: type[T], instructions: str) -> T: ...
    def ask(self, source: PdfSource, question: str) -> Answer: ...


class AnthropicDocumentLLM:
    """Real implementation. Network-bound — covered by the manual smoke test, not CI."""

    def __init__(self, client: anthropic.Anthropic | None = None, model: str | None = None) -> None:
        self._client = client or anthropic.Anthropic()
        self.model = model or resolve_model()

    def extract(self, source: PdfSource, schema: type[T], instructions: str) -> T:
        # structured output — NO citations on this request (mutually exclusive)
        resp = self._client.messages.parse(
            model=self.model,
            max_tokens=16000,
            output_format=schema,
            messages=[{
                "role": "user",
                "content": [pdf_block(source), {"type": "text", "text": instructions}],
            }],
        )
        return resp.parsed_output

    def ask(self, source: PdfSource, question: str) -> Answer:
        # citations enabled — NO output_format on this request
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [pdf_block(source, citations=True, cache=True),
                            {"type": "text", "text": question}],
            }],
        )
        return parse_answer(resp.content)
