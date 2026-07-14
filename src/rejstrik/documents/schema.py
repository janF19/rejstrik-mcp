from typing import Literal

from pydantic import BaseModel, Field


class Figure(BaseModel):
    label: str
    value: float | None = None
    source_page: int | None = None


class NoteItem(BaseModel):
    topic: str
    summary: str
    source_page: int | None = None


class CanonicalFigures(BaseModel):
    """Key statutory lines mapped to stable fields. The extractor fills these
    directly; each description names the exact Czech line so a host model (or a
    keyed server prompt) knows which figure feeds which field."""

    total_assets: Figure | None = Field(
        default=None, description="Aktiva celkem (total assets)"
    )
    current_assets: Figure | None = Field(
        default=None, description="Oběžná aktiva (current assets)"
    )
    equity: Figure | None = Field(default=None, description="Vlastní kapitál (equity)")
    total_liabilities: Figure | None = Field(
        default=None, description="Cizí zdroje (total liabilities)"
    )
    current_liabilities: Figure | None = Field(
        default=None, description="Krátkodobé závazky (current liabilities)"
    )
    revenue: Figure | None = Field(
        default=None,
        description="Tržby z prodeje výrobků, služeb a zboží (revenue)",
    )
    operating_profit: Figure | None = Field(
        default=None,
        description="Provozní výsledek hospodaření (operating profit / EBIT)",
    )
    net_profit: Figure | None = Field(
        default=None,
        description="Výsledek hospodaření za účetní období (net profit)",
    )
    interest_expense: Figure | None = Field(
        default=None, description="nákladové úroky (interest expense)"
    )
    cash: Figure | None = Field(
        default=None,
        description="Peněžní prostředky (cash and cash equivalents)",
    )
    inventories: Figure | None = Field(default=None, description="Zásoby (inventories)")
    receivables: Figure | None = Field(
        default=None, description="Pohledávky (receivables)"
    )
    operating_cash_flow: Figure | None = Field(
        default=None,
        description="Peněžní tok z provozní činnosti (operating cash flow)",
    )
    depreciation_amortization: Figure | None = Field(
        default=None,
        description="Úpravy hodnot v provozní oblasti (depreciation & amortization)",
    )


class FinancialStatement(BaseModel):
    company_name: str | None = None
    ico: str | None = None
    period_year: int | None = None
    currency: str | None = None
    unit: Literal["czk", "thousands_czk", "millions_czk"] | None = Field(
        default=None,
        description=(
            "Scale the figures are printed in, as declared on the statement "
            "(usually on the first page of the rozvaha): 'v celých tisících Kč' "
            "→ thousands_czk, plain Kč → czk, 'v celých milionech Kč' → "
            "millions_czk. Record every figure verbatim as printed and set this "
            "field instead of converting; None means unknown and is treated as "
            "thousands_czk, the Czech statutory default."
        ),
    )
    canonical: CanonicalFigures | None = None
    balance_sheet: list[Figure] = []
    income_statement: list[Figure] = []
    cash_flow: list[Figure] = []
    notes: list[NoteItem] = []
