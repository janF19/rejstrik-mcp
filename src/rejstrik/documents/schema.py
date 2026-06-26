from pydantic import BaseModel


class Figure(BaseModel):
    label: str
    value: float | None = None
    source_page: int | None = None


class NoteItem(BaseModel):
    topic: str
    summary: str
    source_page: int | None = None


class FinancialStatement(BaseModel):
    company_name: str | None = None
    ico: str | None = None
    period_year: int | None = None
    currency: str | None = None
    balance_sheet: list[Figure] = []
    income_statement: list[Figure] = []
    cash_flow: list[Figure] = []
    notes: list[NoteItem] = []
