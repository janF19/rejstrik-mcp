from pydantic import BaseModel

from rejstrik.analysis.in05 import IN05Result
from rejstrik.analysis.normalize import NormalizedFinancials
from rejstrik.analysis.ratios import Ratios
from rejstrik.analysis.redflags import RedFlag
from rejstrik.analysis.trends import TrendItem, TrendSeriesItem
from rejstrik.documents.schema import FinancialStatement


class YearlyFigures(BaseModel):
    period_year: int | None = None
    revenue: float | None = None
    net_profit: float | None = None
    total_assets: float | None = None
    equity: float | None = None


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
    trend_series: list[TrendSeriesItem] = []
    in05: IN05Result | None = None
    yearly: list[YearlyFigures] = []
    subsidies_total: float | None = None
    contracts_total: float | None = None
    public_money_ratio: float | None = None
    source_filing_title: str | None = None
