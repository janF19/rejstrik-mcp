from pydantic import BaseModel

from rejstrik.core.text import normalize_label
from rejstrik.documents.schema import Figure, FinancialStatement

# Per-field matching rules over normalized (accent-stripped, lowercased) labels.
#   prefix  — label starts with any of these
#   exact   — label equals any of these
#   any     — any substring appears in the label
#   exclude — if any appears, the label is rejected (checked first)
_FIELD_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "total_assets": {"any": ("aktiva celkem", "total assets")},
    "current_assets": {"any": ("obezna aktiva", "current assets")},
    "equity": {"any": ("vlastni kapital", "equity")},
    "current_liabilities": {"any": ("kratkodobe zavazky", "current liabilities")},
    "total_liabilities": {"any": ("cizi zdroje", "total liabilities")},
    "revenue": {
        "prefix": (
            "trzby z prodeje vyrobk",
            "trzby z prodeje sluzeb",
            "trzby z prodeje zbozi",
            "trzby za prodej vlastnich",
            "trzby za prodej zbozi",
        ),
        "exact": ("trzby", "vynosy", "revenue", "turnover"),
        "exclude": ("dlouhodob", "majetk"),
    },
    "operating_profit": {"any": ("provozni vysledek hospodareni", "operating profit")},
    "net_profit": {
        "any": (
            "vysledek hospodareni za ucetni obdobi",
            "zisk za ucetni obdobi",
            "net profit",
            "net income",
        )
    },
    "interest_expense": {"any": ("nakladove uroky", "interest expense")},
    "cash": {"any": ("penezni prostredky", "cash and cash equivalents")},
    "inventories": {"any": ("zasoby", "inventories")},
    "receivables": {"any": ("pohledavky", "receivables")},
    "operating_cash_flow": {
        "any": (
            "penezni tok z provozni",
            "cash flow from operat",
        )
    },
}

_FIELDS: tuple[str, ...] = (
    "total_assets",
    "current_assets",
    "equity",
    "total_liabilities",
    "current_liabilities",
    "revenue",
    "operating_profit",
    "net_profit",
    "interest_expense",
    "cash",
    "inventories",
    "receivables",
    "operating_cash_flow",
)


class NormalizedFinancials(BaseModel):
    period_year: int | None = None
    total_assets: float | None = None
    equity: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    total_liabilities: float | None = None
    revenue: float | None = None
    operating_profit: float | None = None
    net_profit: float | None = None
    interest_expense: float | None = None
    cash: float | None = None
    inventories: float | None = None
    receivables: float | None = None
    operating_cash_flow: float | None = None


def _rule_matches(rule: dict[str, tuple[str, ...]], label: str) -> bool:
    if any(token in label for token in rule.get("exclude", ())):
        return False
    if any(label.startswith(prefix) for prefix in rule.get("prefix", ())):
        return True
    if label in rule.get("exact", ()):
        return True
    return any(token in label for token in rule.get("any", ()))


def _keyword_value(field: str, figures: list[Figure]) -> float | None:
    rule = _FIELD_RULES[field]
    for figure in figures:
        if figure.value is None:
            continue
        if _rule_matches(rule, normalize_label(figure.label)):
            return figure.value
    return None


def normalize(statement: FinancialStatement) -> NormalizedFinancials:
    figures: list[Figure] = [
        *statement.balance_sheet,
        *statement.income_statement,
        *statement.cash_flow,
    ]
    canonical = statement.canonical
    values: dict[str, float] = {}
    for field in _FIELDS:
        if canonical is not None:
            fig = getattr(canonical, field)
            if fig is not None and fig.value is not None:
                values[field] = fig.value
                continue
        value = _keyword_value(field, figures)
        if value is not None:
            values[field] = value
    return NormalizedFinancials(period_year=statement.period_year, **values)
