from rejstrik.documents.answer import Answer
from rejstrik.documents.llm import DocumentLLM, default_document_llm
from rejstrik.documents.source import PdfSource


def ask_filing(
    source: PdfSource, question: str, llm: DocumentLLM | None = None
) -> Answer:
    llm = llm or default_document_llm()
    return llm.ask(source, question)
