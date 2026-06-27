from pydantic import BaseModel

from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.analysis.redflags import RedFlag
from rejstrik.analysis.trends import TrendItem
from rejstrik.documents.schema import FinancialStatement


class CompanyFinancialReport(BaseModel):
    company_name: str | None = None
    ico: str | None = None
    period_year: int | None = None
    currency: str | None = None
    statement: FinancialStatement
    normalized: NormalizedFinancials
    ratios: Ratios
    red_flags: list[RedFlag] = []
    trends: list[TrendItem] = []
    source_filing_title: str | None = None
