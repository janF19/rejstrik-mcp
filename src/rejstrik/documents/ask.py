from rejstrik.documents.answer import Answer
from rejstrik.documents.llm import AnthropicDocumentLLM, DocumentLLM
from rejstrik.documents.source import PdfSource


def ask_filing(
    source: PdfSource, question: str, llm: DocumentLLM | None = None
) -> Answer:
    llm = llm or AnthropicDocumentLLM()
    return llm.ask(source, question)
