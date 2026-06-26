from rejstrik.documents.ask import ask_filing
from rejstrik.documents.answer import Answer, Citation
from rejstrik.documents.source import PdfSource

SRC = PdfSource(data=b"%PDF x", sha256="x", filename="f.pdf")


class FakeLLM:
    def __init__(self):
        self.calls = []

    def extract(self, source, schema, instructions):
        raise NotImplementedError

    def ask(self, source, question):
        self.calls.append((source, question))
        return Answer(
            text="A pledge exists.",
            citations=[Citation(cited_text="zástavní právo", page=43)],
        )


def test_ask_filing_delegates_and_returns_answer():
    fake = FakeLLM()
    ans = ask_filing(SRC, "Are there pledges over assets?", llm=fake)
    assert ans.text == "A pledge exists."
    assert ans.citations[0].page == 43
    src, question = fake.calls[0]
    assert src is SRC
    assert question == "Are there pledges over assets?"
