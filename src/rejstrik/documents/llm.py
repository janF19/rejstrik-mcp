import base64
import os
from typing import Protocol, TypeVar

import anthropic
from openai import OpenAI
from pydantic import BaseModel

from rejstrik.documents.answer import Answer, parse_answer
from rejstrik.documents.config import resolve_model, resolve_provider
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

    def __init__(
        self, client: anthropic.Anthropic | None = None, model: str | None = None
    ) -> None:
        self._client = client or anthropic.Anthropic()
        self.model = model or resolve_model()

    def extract(self, source: PdfSource, schema: type[T], instructions: str) -> T:
        # structured output — NO citations on this request (mutually exclusive)
        resp = self._client.messages.parse(
            model=self.model,
            max_tokens=16000,
            output_format=schema,
            messages=[
                {
                    "role": "user",
                    "content": [
                        pdf_block(source),
                        {"type": "text", "text": instructions},
                    ],
                }
            ],
        )
        return resp.parsed_output

    def ask(self, source: PdfSource, question: str) -> Answer:
        # citations enabled — NO output_format on this request
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        pdf_block(source, citations=True, cache=True),
                        {"type": "text", "text": question},
                    ],
                }
            ],
        )
        return parse_answer(resp.content)


class OpenAIDocumentLLM:
    """OpenAI implementation used when OPENAI_API_KEY is configured."""

    def __init__(self, client: OpenAI | None = None, model: str | None = None) -> None:
        # Construction must not require a key: the caller (server.py) gates on
        # has_llm_key() before extract() is ever invoked, so a real key is
        # guaranteed present by the time a network call actually happens.
        self._client = client or OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY") or "unset"
        )
        self.model = model or resolve_model("openai")

    def extract(self, source: PdfSource, schema: type[T], instructions: str) -> T:
        resp = self._client.responses.create(
            model=self.model,
            max_output_tokens=4096,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_file",
                            "filename": source.filename,
                            "file_data": _openai_file_data(source),
                        },
                        {"type": "input_text", "text": instructions},
                    ],
                }
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                    "strict": False,
                }
            },
        )
        return schema.model_validate_json(resp.output_text)

    def ask(self, source: PdfSource, question: str) -> Answer:
        resp = self._client.responses.create(
            model=self.model,
            max_output_tokens=4096,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_file",
                            "filename": source.filename,
                            "file_data": _openai_file_data(source),
                        },
                        {"type": "input_text", "text": question},
                    ],
                }
            ],
        )
        return Answer(text=resp.output_text, citations=[])


def _openai_file_data(source: PdfSource) -> str:
    encoded = base64.standard_b64encode(source.data).decode()
    return f"data:application/pdf;base64,{encoded}"


def default_document_llm() -> DocumentLLM:
    if resolve_provider() == "openai":
        return OpenAIDocumentLLM()
    return AnthropicDocumentLLM()
