from typing import Literal

from pydantic import BaseModel

from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.core.text import normalize_label
from rejstrik.documents.schema import NoteItem

_GOING_CONCERN = ("going concern", "nepretrzite trvani")
_RELATED_PARTY = ("related part", "spojene osob", "spriznene")


class RedFlag(BaseModel):
    code: str
    severity: Literal["critical", "warning", "info"]
    message: str


def detect_red_flags(
    financials: NormalizedFinancials,
    ratios: Ratios,
    notes: list[NoteItem],
    insolvent: bool | None = None,
    unreliable_vat: bool | None = None,
) -> list[RedFlag]:
    flags: list[RedFlag] = []

    if financials.equity is not None and financials.equity < 0:
        flags.append(
            RedFlag(
                code="negative_equity",
                severity="critical",
                message="Negative equity - liabilities exceed assets.",
            )
        )
    if financials.net_profit is not None and financials.net_profit < 0:
        flags.append(
            RedFlag(
                code="net_loss",
                severity="warning",
                message="Company reported a net loss for the period.",
            )
        )
    if ratios.current_ratio is not None and ratios.current_ratio < 1:
        flags.append(
            RedFlag(
                code="low_liquidity",
                severity="warning",
                message=(
                    "Current ratio below 1 - short-term liabilities exceed "
                    "current assets."
                ),
            )
        )
    if ratios.debt_to_equity is not None and ratios.debt_to_equity > 3:
        flags.append(
            RedFlag(
                code="high_leverage",
                severity="warning",
                message="Debt-to-equity above 3 - heavily leveraged.",
            )
        )

    for note in notes:
        text = normalize_label(f"{note.topic} {note.summary}")
        if any(keyword in text for keyword in _GOING_CONCERN):
            flags.append(
                RedFlag(
                    code="going_concern",
                    severity="critical",
                    message=f"Going-concern note: {note.summary}",
                )
            )
        if any(keyword in text for keyword in _RELATED_PARTY):
            flags.append(
                RedFlag(
                    code="related_party",
                    severity="info",
                    message=f"Related-party note: {note.summary}",
                )
            )

    if insolvent is True:
        flags.append(
            RedFlag(
                code="insolvency",
                severity="critical",
                message="Company appears in the insolvency register (ISIR).",
            )
        )

    if unreliable_vat is True:
        flags.append(
            RedFlag(
                code="unreliable_vat",
                severity="warning",
                message="Registered as an unreliable VAT payer (nespolehlivy platce DPH).",
            )
        )

    return flags
