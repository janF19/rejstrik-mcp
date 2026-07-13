import html

from rejstrik.analysis.report import CompanyFinancialReport

_SEVERITY_COLOR = {"critical": "#c0392b", "warning": "#b76500", "info": "#667085"}

_SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}

_RATIO_BLURB = {
    "current_ratio": "short-term obligations vs liquid assets",
    "equity_ratio": "share of assets financed by equity",
    "debt_to_equity": "leverage — liabilities per unit of equity",
    "net_margin": "net profit per unit of revenue",
    "return_on_equity": "net profit per unit of equity",
}

_ARROW = {"up": "▲", "down": "▼", "flat": "→"}

_STYLE = """
body{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;padding:16px;color:#1f2933;background:#fff}
h1{font-size:18px;line-height:1.25;margin:0 0 2px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:#52606d;margin:16px 0 6px}
.sub{color:#52606d;font-size:13px;margin-bottom:8px}
table{border-collapse:collapse;width:100%;margin-bottom:8px}
th,td{padding:5px 8px;border-bottom:1px solid #e4e7eb;font-size:13px;text-align:right}
th:first-child,td:first-child,td.k{text-align:left;color:#52606d}
.blurb{color:#7b8794}
.flag{padding:7px 10px;border-radius:6px;margin:4px 0;color:#fff;font-size:13px}
.pm{padding:8px 10px;border-radius:6px;background:#f0f4f8;font-size:13px;margin:6px 0}
.foot{color:#7b8794;font-size:11px;margin-top:12px}
"""


def _esc(value: object) -> str:
    return html.escape(str(value))


def _shown(value: float | None) -> str:
    if value is None:
        return "-"
    return str(round(value, 3))


def _fmt(value: float | None) -> str:
    if value is None:
        return "-"
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,.2f}"


def _arrow(pct: float | None) -> str:
    if pct is None:
        return _ARROW["flat"]
    if pct > 0.0005:
        return _ARROW["up"]
    if pct < -0.0005:
        return _ARROW["down"]
    return _ARROW["flat"]


def _sorted_flags(report: CompanyFinancialReport):
    return sorted(report.red_flags, key=lambda f: _SEVERITY_RANK.get(f.severity, 3))


def render_report_card(report: CompanyFinancialReport) -> str:
    if report.yearly:
        year_head = "".join(
            f"<th>{_esc(y.period_year or '-')}</th>" for y in report.yearly
        )
        metric_rows = ""
        for label, attr in (
            ("Revenue", "revenue"),
            ("Net profit", "net_profit"),
            ("Total assets", "total_assets"),
            ("Equity", "equity"),
        ):
            cells = "".join(
                f"<td>{_esc(_fmt(getattr(y, attr)))}</td>" for y in report.yearly
            )
            metric_rows += f"<tr><td class='k'>{_esc(label)}</td>{cells}</tr>"
        yearly_html = (
            "<h2>Figures by year</h2>"
            f"<table><tr><th>Metric</th>{year_head}</tr>{metric_rows}</table>"
        )
    else:
        yearly_html = ""

    ratio_rows = "".join(
        f"<tr><td class='k'>{_esc(name)}</td><td>{_esc(_shown(value))}</td>"
        f"<td class='blurb'>{_esc(_RATIO_BLURB.get(name, ''))}</td></tr>"
        for name, value in report.ratios.model_dump().items()
    )

    flags_sorted = _sorted_flags(report)
    if flags_sorted:
        flags = "".join(
            f"<div class='flag' style='background:{_SEVERITY_COLOR.get(flag.severity, '#667085')}'>"
            f"[{_esc(flag.severity.upper())}] {_esc(flag.message)}</div>"
            for flag in flags_sorted
        )
    else:
        flags = (
            "<div class='flag' style='background:#2f855a'>No red flags detected.</div>"
        )

    if report.public_money_ratio is not None:
        public_money = (
            f"<div class='pm'>Public money (subsidies + state contracts) is "
            f"~{_esc(f'{report.public_money_ratio:.0%}')} of revenue.</div>"
        )
    else:
        public_money = ""

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>{_STYLE}</style></head>
<body>
  <h1>{_esc(report.company_name or "")}</h1>
  <div class="sub">IČO {_esc(report.ico or "-")} &middot; period {_esc(report.period_year or "-")} &middot; {_esc(report.currency or "")}</div>
  <div class="sub">Source: {_esc(report.source_filing_title or "Sbírka listin")}</div>
  {yearly_html}
  <h2>Ratios</h2>
  <table>{ratio_rows}</table>
  <h2>Red flags</h2>
  {flags}
  {public_money}
  <div class="foot">Figures as filed; typically thousands of CZK. Source: {_esc(report.source_filing_title or "Sbírka listin")}</div>
</body></html>"""


def render_report_markdown(report: CompanyFinancialReport) -> str:
    lines: list[str] = []
    header = report.company_name or "Company"
    lines.append(f"## {header}")
    lines.append(
        f"IČO {report.ico or '-'} · period {report.period_year or '-'} · "
        f"{report.currency or ''}".rstrip()
    )
    if report.source_filing_title:
        lines.append(f"Source: {report.source_filing_title}")
    lines.append("")

    if report.yearly:
        lines.append("### Figures by year")
        lines.append("| Year | Revenue | Net profit | Total assets | Equity |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for y in report.yearly:
            lines.append(
                f"| {y.period_year or '-'} | {_fmt(y.revenue)} | "
                f"{_fmt(y.net_profit)} | {_fmt(y.total_assets)} | {_fmt(y.equity)} |"
            )
        lines.append("")

    lines.append("### Ratios")
    for name, value in report.ratios.model_dump().items():
        blurb = _RATIO_BLURB.get(name, "")
        shown = _shown(value)
        suffix = f" — {blurb}" if blurb else ""
        lines.append(f"- **{name}**: {shown}{suffix}")
    lines.append("")

    if report.trends:
        lines.append("### Year-over-year (latest vs prior)")
        for t in report.trends:
            pct = f"{t.pct_change:+.0%}" if t.pct_change is not None else "n/a"
            lines.append(f"- {_arrow(t.pct_change)} {t.metric}: {pct}")
        lines.append("")

    lines.append("### Red flags")
    flags = _sorted_flags(report)
    if flags:
        for flag in flags:
            lines.append(f"- **[{flag.severity.upper()}]** {flag.message}")
    else:
        lines.append("- None detected.")
    lines.append("")

    if report.public_money_ratio is not None:
        lines.append(
            f"**Public money** (subsidies + state contracts) is "
            f"~{report.public_money_ratio:.0%} of revenue."
        )
        lines.append("")

    lines.append("_Figures as filed; typically thousands of CZK._")
    return "\n".join(lines)
