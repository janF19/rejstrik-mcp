from rejstrik.filings.models import Filing


def pick_latest_financial_filing(filings: list[Filing]) -> Filing | None:
    for f in filings:
        if f.is_financial_statement:
            return f
    return None
