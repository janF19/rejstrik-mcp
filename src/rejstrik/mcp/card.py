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
.sub{color:#52606d;font-size:13px;margin-bottom:14px}
table{border-collapse:collapse;width:100%;margin-bottom:14px}
td{padding:5px 8px;border-bottom:1px solid #e4e7eb;font-size:13px}
td.k{color:#52606d}
.flag{padding:7px 10px;border-radius:6px;margin:4px 0;color:#fff;font-size:13px}
.foot{color:#7b8794;font-size:11px;margin-top:10px}
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
    rows = "".join(
        f"<tr><td class='k'>{_esc(name)}</td><td>{_esc(_shown(value))}</td></tr>"
        for name, value in report.ratios.model_dump().items()
    )
    if report.red_flags:
        flags = "".join(
            f"<div class='flag' style='background:{_SEVERITY_COLOR.get(flag.severity, '#667085')}'>"
            f"[{_esc(flag.severity.upper())}] {_esc(flag.message)}</div>"
            for flag in report.red_flags
        )
    else:
        flags = (
            "<div class='flag' style='background:#2f855a'>No red flags detected.</div>"
        )

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>{_STYLE}</style></head>
<body>
  <h1>{_esc(report.company_name or "")}</h1>
  <div class="sub">ICO {_esc(report.ico or "-")} &middot; period {_esc(report.period_year or "-")} &middot; {_esc(report.currency or "")}</div>
  <table>{rows}</table>
  {flags}
  <div class="foot">Source: {_esc(report.source_filing_title or "Sbirka listin")}</div>
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
