from rejstrik.documents.llm import pdf_block
from rejstrik.documents.llm import OpenAIDocumentLLM, default_document_llm
from rejstrik.documents.schema import FinancialStatement, Figure
from rejstrik.documents.source import PdfSource

SRC = PdfSource(data=b"%PDF-1.4 x", sha256="deadbeef", filename="f.pdf")


def test_pdf_block_is_base64_document():
    block = pdf_block(SRC)
    assert block["type"] == "document"
    assert block["source"]["type"] == "base64"
    assert block["source"]["media_type"] == "application/pdf"
    import base64

    assert block["source"]["data"] == base64.standard_b64encode(SRC.data).decode()
    assert "citations" not in block
    assert "cache_control" not in block


def test_pdf_block_citations_and_cache_flags():
    block = pdf_block(SRC, citations=True, cache=True)
    assert block["citations"] == {"enabled": True}
    assert block["cache_control"] == {"type": "ephemeral"}


class FakeResponses:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)

        class Resp:
            output_text = (
                '{"company_name":"Fake s.r.o.","balance_sheet":'
                '[{"label":"Total assets","value":1.0,"source_page":3}]}'
            )

        return Resp()


class FakeOpenAIClient:
    def __init__(self):
        self.responses = FakeResponses()


def test_openai_extract_sends_pdf_and_schema():
    client = FakeOpenAIClient()
    llm = OpenAIDocumentLLM(client=client, model="gpt-test")

    result = llm.extract(SRC, FinancialStatement, "Extract it")

    assert isinstance(result, FinancialStatement)
    assert result.balance_sheet == [
        Figure(label="Total assets", value=1.0, source_page=3)
    ]
    call = client.responses.calls[0]
    assert call["model"] == "gpt-test"
    assert call["max_output_tokens"] == 4096
    assert call["text"]["format"]["type"] == "json_schema"
    assert call["text"]["format"]["name"] == "FinancialStatement"
    content = call["input"][0]["content"]
    assert content[0]["type"] == "input_file"
    assert content[0]["filename"] == "f.pdf"
    assert content[0]["file_data"].startswith("data:application/pdf;base64,")
    assert content[1] == {"type": "input_text", "text": "Extract it"}


def test_default_document_llm_uses_openai_when_configured(monkeypatch):
    monkeypatch.setattr("rejstrik.documents.llm.resolve_provider", lambda: "openai")

    assert isinstance(default_document_llm(), OpenAIDocumentLLM)
