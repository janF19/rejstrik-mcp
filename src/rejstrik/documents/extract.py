from rejstrik.documents.llm import DocumentLLM, default_document_llm
from rejstrik.documents.schema import FinancialStatement
from rejstrik.documents.source import PdfSource

EXTRACT_INSTRUCTIONS = (
    "This is a Czech company financial statement (účetní závěrka). "
    "Extract the balance sheet (rozvaha), income statement (výkaz zisku a ztráty), "
    "cash flow if present, and the narrative notes (příloha). "
    "For every figure and note, record the source_page it was found on (1-indexed). "
    "Use CZK unless the document states otherwise. "
    "If a value is not present, leave it null rather than guessing."
)


def extract_financials(
    source: PdfSource, llm: DocumentLLM | None = None
) -> FinancialStatement:
    llm = llm or default_document_llm()
    return llm.extract(source, FinancialStatement, EXTRACT_INSTRUCTIONS)
