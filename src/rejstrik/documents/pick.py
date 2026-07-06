from rejstrik.filings.models import Filing


def pick_financial_filing(
    filings: list[Filing],
    year: int | None = None,
    filing_id: str | None = None,
) -> Filing | None:
    """Pick a financial statement: latest by default, or by year / filing id.

    filing_id matches any filing (financial or not) whose pdf_url equals or
    contains it — document ids are embedded in the portal URLs.
    """
    if filing_id:
        for f in filings:
            if filing_id == f.pdf_url or filing_id in f.pdf_url:
                return f
        return None
    candidates = [f for f in filings if f.is_financial_statement]
    if year is not None:
        candidates = [f for f in candidates if f.year == year]
    return candidates[0] if candidates else None


def pick_latest_financial_filing(filings: list[Filing]) -> Filing | None:
    return pick_financial_filing(filings)
