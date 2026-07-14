"""
email_reports/report_builder.py

Queries the SQLite database and builds a styled HTML email report showing:
  - Daily storage pricing summary by brand
  - New pre-mover leads by ZIP code (from USA Home Listings)
  - Top ZIP codes by listing activity (demand signal)
  - Active promotions spotted
  - Scrape health status (what ran OK, what failed)

Usage:
    from email_reports.report_builder import build_report
    html = build_report()
"""

import sys
import pathlib
from datetime import datetime, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from database.db_setup import get_connection

# ── Colour palette (inline CSS, email-safe) ──────────────────────
BRAND_COLOR   = "#1a3c5e"   # dark navy
ACCENT        = "#2eaadc"   # bright blue
POSITIVE      = "#27ae60"   # green  (price down = good for renters)
NEGATIVE      = "#e74c3c"   # red    (price up)
NEUTRAL       = "#7f8c8d"   # grey
BG_LIGHT      = "#f4f6f8"
BG_WHITE      = "#ffffff"
TEXT_DARK     = "#2c3e50"
TEXT_MUTED    = "#7f8c8d"


# ── DB query helpers ─────────────────────────────────────────────

def _q(sql: str, params: tuple = ()) -> list[dict]:
    """Run a read-only query and return rows as dicts."""
    conn = get_connection()
    conn.row_factory = __import__("sqlite3").Row
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_pricing_summary(days: int = 1) -> list[dict]:
    """Average price per unit type, grouped by brand, for the last N days."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    return _q("""
        SELECT
            COALESCE(f.brand, 'Independent') AS brand,
            ps.unit_size AS unit_type,
            ROUND(AVG(ps.web_rate), 2)         AS avg_price,
            COUNT(*)                           AS count,
            MIN(ps.web_rate)                   AS min_price,
            MAX(ps.web_rate)                   AS max_price
        FROM pricing_snapshots ps
        JOIN facilities f ON f.id = ps.facility_id
        WHERE ps.scraped_at >= ?
          AND ps.web_rate IS NOT NULL
        GROUP BY f.brand, ps.unit_size
        ORDER BY f.brand, ps.unit_size
    """, (cutoff,))


def get_top_zip_leads(limit: int = 10) -> list[dict]:
    """ZIP codes with the most new pre-mover leads today."""
    today = datetime.utcnow().date().isoformat()
    return _q("""
        SELECT
            zip_code,
            COUNT(*) AS total_leads,
            SUM(CASE WHEN status = 'for_sale'       THEN 1 ELSE 0 END) AS for_sale,
            SUM(CASE WHEN status = 'under_contract'  THEN 1 ELSE 0 END) AS under_contract,
            SUM(CASE WHEN is_vacant = 1              THEN 1 ELSE 0 END) AS vacant_homes
        FROM pre_mover_leads
        WHERE date(scraped_at) = ?
          AND zip_code != ''
        GROUP BY zip_code
        ORDER BY total_leads DESC
        LIMIT ?
    """, (today, limit))


def get_active_promotions() -> list[dict]:
    """Current active promotions from scraped data."""
    return _q("""
        SELECT p.description AS promo_text, p.discount_pct, f.name AS facility_name,
               f.zip_code, f.brand
        FROM promotions p
        JOIN facilities f ON f.id = p.facility_id
        WHERE (p.expiry_date IS NULL OR p.expiry_date >= date('now'))
        ORDER BY p.discount_pct DESC
        LIMIT 15
    """)


def get_scrape_health() -> list[dict]:
    """Last scrape status for each collector."""
    return _q("""
        SELECT source, status, records_written AS records_found,
               error_msg AS error_message, run_at AS scraped_at
        FROM scrape_log
        WHERE run_at >= datetime('now', '-24 hours')
        ORDER BY run_at DESC
    """)


def get_facility_count() -> int:
    rows = _q("SELECT COUNT(*) AS n FROM facilities")
    return rows[0]["n"] if rows else 0


def get_lead_count_today() -> int:
    today = datetime.utcnow().date().isoformat()
    rows = _q("SELECT COUNT(*) AS n FROM pre_mover_leads WHERE date(scraped_at) = ?", (today,))
    return rows[0]["n"] if rows else 0

def get_real_estate_kpis() -> dict:
    rows = _q("""
        SELECT 
            COUNT(*) as total_listings,
            SUM(CASE WHEN status = 'for_sale' THEN 1 ELSE 0 END) as active_listings,
            SUM(CASE WHEN status = 'under_contract' THEN 1 ELSE 0 END) as under_contract,
            AVG(list_price) as avg_price,
            SUM(CASE WHEN previous_status IS NOT NULL THEN 1 ELSE 0 END) as status_changed
        FROM pre_mover_leads
    """)
    if not rows: return {}
    r = rows[0]
    return {
        "total": r["total_listings"] or 0,
        "active": r["active_listings"] or 0,
        "under_contract": r["under_contract"] or 0,
        "avg_price": r["avg_price"] or 0,
        "status_changed": r["status_changed"] or 0
    }

def get_storage_kpis() -> dict:
    # Dominant brand
    brand_rows = _q("SELECT brand FROM facilities GROUP BY brand ORDER BY COUNT(*) DESC LIMIT 1")
    top_brand = brand_rows[0]["brand"] if brand_rows else "N/A"
    
    # Avg 10x10 Rate
    rate_rows = _q("SELECT AVG(web_rate) as avg_rate FROM pricing_snapshots WHERE unit_size = '10x10'")
    avg_rate = rate_rows[0]["avg_rate"] or 0 if rate_rows else 0
    
    return {
        "top_brand": top_brand,
        "avg_10x10": avg_rate
    }


# ── HTML building blocks ─────────────────────────────────────────

def _cell(text, bold=False, color=None, align="left"):
    style = "padding:8px 12px; border-bottom:1px solid #e0e0e0;"
    if bold:
        style += "font-weight:600;"
    if color:
        style += "color:{};".format(color)
    if align != "left":
        style += "text-align:{};".format(align)
    return "<td style='{}'>{}</td>".format(style, text)


def _header_cell(text):
    style = (
        "padding:10px 12px; background:{}; color:#fff; "
        "font-weight:600; font-size:12px; text-transform:uppercase; "
        "letter-spacing:0.5px;".format(BRAND_COLOR)
    )
    return "<th style='{}'>{}</th>".format(style, text)


def _section(title: str, body: str) -> str:
    return """
    <div style='margin:0 0 28px 0;'>
      <h2 style='color:{brand}; font-size:16px; font-weight:700;
                 border-left:4px solid {accent}; padding-left:10px;
                 margin:0 0 14px 0;'>{title}</h2>
      {body}
    </div>
    """.format(brand=BRAND_COLOR, accent=ACCENT, title=title, body=body)


def _kpi_row(metrics: list[tuple]) -> str:
    """Render a row of KPI boxes. metrics = [(label, value, color), ...]"""
    boxes = ""
    for label, value, color in metrics:
        boxes += """
        <td style='text-align:center; padding:0 8px;'>
          <div style='background:{bg}; border-radius:8px; padding:16px 20px;
                      border-top:3px solid {color};'>
            <div style='font-size:28px; font-weight:700; color:{color};'>{value}</div>
            <div style='font-size:12px; color:{muted}; margin-top:4px;'>{label}</div>
          </div>
        </td>
        """.format(bg=BG_LIGHT, color=color, value=value,
                   label=label, muted=TEXT_MUTED)
    return "<table width='100%' cellpadding='0' cellspacing='0'><tr>{}</tr></table>".format(boxes)


# ── Section builders ─────────────────────────────────────────────

def _build_pricing_section(rows: list[dict]) -> str:
    if not rows:
        return "<p style='color:{};'>No pricing data collected yet. Run the scrapers first.</p>".format(TEXT_MUTED)

    header = "<tr>{}</tr>".format(
        "".join(_header_cell(h) for h in ["Brand", "Unit Type", "Avg/mo", "Min", "Max", "# Samples"])
    )
    body_rows = ""
    for r in rows:
        body_rows += "<tr>{}</tr>".format("".join([
            _cell(r["brand"], bold=True),
            _cell(r["unit_type"]),
            _cell("${:,.0f}".format(r["avg_price"]), color=ACCENT, bold=True),
            _cell("${:,.0f}".format(r["min_price"]), color=POSITIVE),
            _cell("${:,.0f}".format(r["max_price"]), color=NEGATIVE),
            _cell(str(r["count"]), align="center"),
        ]))

    table = """
    <table width='100%' cellpadding='0' cellspacing='0'
           style='border-collapse:collapse; font-size:13px;'>
      <thead>{header}</thead>
      <tbody>{body}</tbody>
    </table>
    """.format(header=header, body=body_rows)
    return table


def _build_leads_section(rows: list[dict]) -> str:
    if not rows:
        return "<p style='color:{};'>No lead data yet. USA Home Listings access pending.</p>".format(TEXT_MUTED)

    header = "<tr>{}</tr>".format(
        "".join(_header_cell(h) for h in
                ["ZIP Code", "Total Leads", "For Sale", "Under Contract", "Vacant", "Demand Signal"])
    )
    body_rows = ""
    for r in rows:
        total = r["total_leads"]
        signal_color = NEGATIVE if total >= 20 else (ACCENT if total >= 10 else POSITIVE)
        signal = "HIGH" if total >= 20 else ("MEDIUM" if total >= 10 else "LOW")

        body_rows += "<tr>{}</tr>".format("".join([
            _cell(r["zip_code"], bold=True),
            _cell(str(total), bold=True, color=ACCENT),
            _cell(str(r["for_sale"])),
            _cell(str(r["under_contract"])),
            _cell(str(r["vacant_homes"])),
            _cell(
                "<span style='background:{c};color:#fff;padding:3px 8px;"
                "border-radius:4px;font-size:11px;font-weight:700;'>{s}</span>".format(
                    c=signal_color, s=signal),
                align="center"
            ),
        ]))

    return """
    <table width='100%' cellpadding='0' cellspacing='0'
           style='border-collapse:collapse; font-size:13px;'>
      <thead>{header}</thead>
      <tbody>{body}</tbody>
    </table>
    """.format(header=header, body=body_rows)


def _build_promos_section(rows: list[dict]) -> str:
    if not rows:
        return "<p style='color:{};'>No active promotions found.</p>".format(TEXT_MUTED)

    cards = ""
    for r in rows:
        disc = "{}% off".format(int(r["discount_pct"])) if r.get("discount_pct") else ""
        cards += """
        <div style='display:inline-block; background:{bg}; border-radius:6px;
                    padding:10px 14px; margin:0 8px 8px 0; font-size:13px;
                    border-left:3px solid {accent};'>
          <strong style='color:{brand};'>{name}</strong>
          {disc_badge}
          <div style='color:{muted}; font-size:11px; margin-top:3px;'>{text}</div>
          <div style='color:{muted}; font-size:11px;'>ZIP {zip}</div>
        </div>
        """.format(
            bg=BG_LIGHT, accent=ACCENT, brand=BRAND_COLOR,
            name=r["facility_name"],
            disc_badge=(
                "<span style='background:{};color:#fff;padding:2px 6px;"
                "border-radius:3px;font-size:11px;margin-left:6px;'>{}</span>".format(NEGATIVE, disc)
                if disc else ""
            ),
            text=r["promo_text"][:80] if r.get("promo_text") else "",
            muted=TEXT_MUTED, zip=r.get("zip_code", "")
        )
    return cards


def _build_health_section(rows: list[dict]) -> str:
    if not rows:
        return "<p style='color:{};'>No scrape logs in the last 24 hours.</p>".format(TEXT_MUTED)

    items = ""
    for r in rows:
        ok = r["status"] == "success"
        dot_color = POSITIVE if ok else NEGATIVE
        msg = r.get("error_message") or "{} records".format(r.get("records_found", 0))
        items += """
        <div style='display:flex; align-items:center; margin-bottom:6px; font-size:13px;'>
          <span style='width:10px; height:10px; border-radius:50%;
                       background:{c}; margin-right:8px; flex-shrink:0;'></span>
          <strong style='min-width:200px;'>{source}</strong>
          <span style='color:{muted};'>{msg}</span>
          <span style='margin-left:auto; color:{muted}; font-size:11px;'>{at}</span>
        </div>
        """.format(c=dot_color, source=r["source"], msg=msg,
                   muted=TEXT_MUTED, at=r["scraped_at"][:16])
    return items


# ── Main report assembler ─────────────────────────────────────────

def build_report() -> str:
    """
    Build the full HTML email report.
    Returns an HTML string ready to send via Brevo.
    """
    now = datetime.now()
    date_str  = now.strftime("%A, %B %d, %Y")
    title_str = "Storage Market Daily Report — {}".format(date_str)

    pricing   = get_pricing_summary()
    leads     = get_top_zip_leads()
    promos    = get_active_promotions()
    health    = get_scrape_health()
    fac_count = get_facility_count()
    re_kpis   = get_real_estate_kpis()
    st_kpis   = get_storage_kpis()

    re_kpi_html = _kpi_row([
        ("Total Listings",    "{:,}".format(re_kpis.get("total", 0)), BRAND_COLOR),
        ("Active For Sale",   "{:,}".format(re_kpis.get("active", 0)), POSITIVE),
        ("Under Contract",    "{:,}".format(re_kpis.get("under_contract", 0)), "#FF9800"),
        ("Avg List Price",    "${:,.0f}".format(re_kpis.get("avg_price", 0)), "#9C27B0"),
        ("Status Changed",    "{:,}".format(re_kpis.get("status_changed", 0)), NEGATIVE),
    ])

    st_kpi_html = _kpi_row([
        ("Tracked Facilities", "{:,}".format(fac_count), "#E91E63"),
        ("Dominant Brand",     st_kpis.get("top_brand", "N/A"), "#FFC107"),
        ("Avg 10x10 Rate",     "${:.2f}".format(st_kpis.get("avg_10x10", 0)), "#00BCD4"),
        ("Active Promotions",  str(len(promos)), NEGATIVE if promos else TEXT_MUTED),
    ])

    body = """
    {re_kpi}
    {st_kpi}
    {pricing}
    {leads}
    {promos}
    {health}
    """.format(
        re_kpi  = _section("🏡 Real Estate Market Overview", re_kpi_html),
        st_kpi  = _section("📦 Self-Storage Market Overview", st_kpi_html),
        pricing = _section("Storage Pricing Summary (Last 24h)", _build_pricing_section(pricing)),
        leads   = _section("Top ZIP Codes by Pre-Mover Lead Activity", _build_leads_section(leads)),
        promos  = _section("Active Storage Promotions", _build_promos_section(promos)),
        health  = _section("Data Collection Health", _build_health_section(health)),
    )

    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
</head>
<body style="margin:0; padding:0; background:{bg_light}; font-family:Arial,sans-serif; color:{text_dark};">

  <!-- Header -->
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td style="background:{brand}; padding:24px 32px;">
        <h1 style="color:#fff; margin:0; font-size:20px; font-weight:700;">
          Around Town Movers
        </h1>
        <p style="color:rgba(255,255,255,0.75); margin:4px 0 0; font-size:13px;">
          Self-Storage Market Intelligence &mdash; {date}
        </p>
      </td>
    </tr>
  </table>

  <!-- Body -->
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td style="padding:28px 32px; max-width:900px;">
        {body}
      </td>
    </tr>
  </table>

  <!-- Footer -->
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td style="background:{brand}; padding:16px 32px; text-align:center;">
        <p style="color:rgba(255,255,255,0.6); margin:0; font-size:11px;">
          This report is auto-generated daily by the Around Town Movers Storage Tracker.
          | NoVA &bull; DC &bull; Maryland &bull; 149 ZIP codes
        </p>
      </td>
    </tr>
  </table>

</body>
</html>""".format(
        title=title_str, date=date_str, body=body,
        brand=BRAND_COLOR, bg_light=BG_LIGHT, text_dark=TEXT_DARK
    )

    return html


if __name__ == "__main__":
    html = build_report()
    out = pathlib.Path("debug_screenshots") / "daily_report_preview.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print("Report preview saved to: {}".format(out))
    print("Open it in your browser to preview the email layout.")
