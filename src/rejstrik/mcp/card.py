import html

from rejstrik.analysis.report import CompanyFinancialReport

_SEVERITY_COLOR = {"critical": "#c0392b", "warning": "#b76500", "info": "#667085"}

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
        flags = "<div class='flag' style='background:#2f855a'>No red flags detected.</div>"

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>{_STYLE}</style></head>
<body>
  <h1>{_esc(report.company_name or "")}</h1>
  <div class="sub">ICO {_esc(report.ico or "-")} &middot; period {_esc(report.period_year or "-")} &middot; {_esc(report.currency or "")}</div>
  <table>{rows}</table>
  {flags}
  <div class="foot">Source: {_esc(report.source_filing_title or "Sbirka listin")}</div>
</body></html>"""
