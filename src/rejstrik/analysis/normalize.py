from pydantic import BaseModel

from rejstrik.core.text import normalize_label
from rejstrik.documents.schema import Figure, FinancialStatement

_FIELD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "total_assets": ("aktiva celkem", "total assets"),
    "current_assets": ("obezna aktiva", "current assets"),
    "equity": ("vlastni kapital", "equity"),
    "current_liabilities": ("kratkodobe zavazky", "current liabilities"),
    "total_liabilities": ("cizi zdroje", "total liabilities"),
    "revenue": ("trzby", "vynosy", "revenue", "turnover"),
    "net_profit": (
        "vysledek hospodareni",
        "net profit",
        "net income",
        "zisk za",
    ),
}


class NormalizedFinancials(BaseModel):
    period_year: int | None = None
    total_assets: float | None = None
    equity: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    total_liabilities: float | None = None
    revenue: float | None = None
    net_profit: float | None = None


def normalize(statement: FinancialStatement) -> NormalizedFinancials:
    values: dict[str, float] = {}
    figures: list[Figure] = [*statement.balance_sheet, *statement.income_statement]
    for figure in figures:
        if figure.value is None:
            continue
        label = normalize_label(figure.label)
        for field, keywords in _FIELD_KEYWORDS.items():
            if field in values:
                continue
            if any(keyword in label for keyword in keywords):
                values[field] = figure.value
                break
    return NormalizedFinancials(period_year=statement.period_year, **values)
