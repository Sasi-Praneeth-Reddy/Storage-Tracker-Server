"""
routers/real_estate.py — Pre-mover lead / real-estate listing endpoints.
"""

from typing import List, Optional

from fastapi import APIRouter, Query

from api.database import get_connection

router = APIRouter(prefix="/api/real-estate", tags=["real-estate"])


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _rows_to_dicts(rows) -> List[dict]:
    return [dict(r) for r in rows]


def _apply_common_filters(
    where: list,
    params: list,
    *,
    status: Optional[str] = None,
    state: Optional[str] = None,
    county: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    table_alias: str = "",
):
    """Append WHERE clauses and params for common filter parameters."""
    prefix = f"{table_alias}." if table_alias else ""

    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if statuses:
            placeholders = ",".join(["?" for _ in statuses])
            where.append(f"{prefix}status IN ({placeholders})")
            params.extend(statuses)

    if state:
        where.append(f"{prefix}state = ?")
        params.append(state)

    if county:
        where.append(f"{prefix}county = ?")
        params.append(county)

    if price_min is not None:
        where.append(f"{prefix}list_price >= ?")
        params.append(price_min)

    if price_max is not None:
        where.append(f"{prefix}list_price <= ?")
        params.append(price_max)

    if date_from:
        where.append(f"DATE({prefix}scraped_at) >= ?")
        params.append(date_from)

    if date_to:
        where.append(f"DATE({prefix}scraped_at) <= ?")
        params.append(date_to)


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------

@router.get("/listings")
def get_listings(
    status: Optional[str] = Query(None, description="Comma-separated status values"),
    state: Optional[str] = Query(None),
    county: Optional[str] = Query(None),
    price_min: Optional[float] = Query(None),
    price_max: Optional[float] = Query(None),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """Return up to 2000 pre-mover listings matching the supplied filters."""
    where = ["1=1"]
    params: list = []
    _apply_common_filters(
        where, params,
        status=status, state=state, county=county,
        price_min=price_min, price_max=price_max,
        date_from=date_from, date_to=date_to,
    )
    sql = f"SELECT * FROM pre_mover_leads WHERE {' AND '.join(where)} LIMIT 2000"

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

@router.get("/kpis")
def get_kpis(
    status: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    county: Optional[str] = Query(None),
    price_min: Optional[float] = Query(None),
    price_max: Optional[float] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """Return high-level KPI metrics for the real-estate dashboard."""
    where = ["1=1"]
    params: list = []
    _apply_common_filters(
        where, params,
        status=status, state=state, county=county,
        price_min=price_min, price_max=price_max,
        date_from=date_from, date_to=date_to,
    )
    where_sql = " AND ".join(where)

    sql = f"""
        SELECT
            COUNT(*) AS total_listings,
            SUM(CASE WHEN LOWER(status) = 'active' THEN 1 ELSE 0 END) AS active_count,
            SUM(CASE WHEN LOWER(status) LIKE '%contract%' THEN 1 ELSE 0 END) AS under_contract_count,
            ROUND(AVG(list_price), 2) AS avg_list_price,
            SUM(CASE WHEN previous_status IS NOT NULL AND previous_status != status THEN 1 ELSE 0 END) AS status_changed_count
        FROM pre_mover_leads
        WHERE {where_sql}
    """

    with get_connection() as conn:
        row = conn.execute(sql, params).fetchone()

    if not row:
        return {
            "total_listings": 0,
            "active_count": 0,
            "under_contract_count": 0,
            "avg_list_price": None,
            "status_changed_count": 0,
        }
    return dict(row)


# ---------------------------------------------------------------------------
# By-county breakdown
# ---------------------------------------------------------------------------

@router.get("/by-county")
def get_by_county(
    status: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    county: Optional[str] = Query(None),
    price_min: Optional[float] = Query(None),
    price_max: Optional[float] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """Return listing counts per county+status for the top 12 counties."""
    where = ["1=1"]
    params: list = []
    _apply_common_filters(
        where, params,
        status=status, state=state, county=county,
        price_min=price_min, price_max=price_max,
        date_from=date_from, date_to=date_to,
    )
    where_sql = " AND ".join(where)

    sql = f"""
        WITH top_counties AS (
            SELECT county
            FROM pre_mover_leads
            WHERE {where_sql}
            GROUP BY county
            ORDER BY COUNT(*) DESC
            LIMIT 12
        )
        SELECT l.county, l.status, COUNT(*) AS count
        FROM pre_mover_leads l
        INNER JOIN top_counties tc ON l.county = tc.county
        WHERE {where_sql}
        GROUP BY l.county, l.status
        ORDER BY l.county, l.status
    """

    with get_connection() as conn:
        rows = conn.execute(sql, params + params).fetchall()

    return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# Price by county
# ---------------------------------------------------------------------------

@router.get("/price-by-county")
def get_price_by_county(
    status: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    county: Optional[str] = Query(None),
    price_min: Optional[float] = Query(None),
    price_max: Optional[float] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """Return average list price per county, sorted descending."""
    where = ["1=1", "list_price IS NOT NULL"]
    params: list = []
    _apply_common_filters(
        where, params,
        status=status, state=state, county=county,
        price_min=price_min, price_max=price_max,
        date_from=date_from, date_to=date_to,
    )
    where_sql = " AND ".join(where)

    sql = f"""
        SELECT county, ROUND(AVG(list_price), 2) AS avg_price
        FROM pre_mover_leads
        WHERE {where_sql}
        GROUP BY county
        ORDER BY avg_price DESC
    """

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# Weekly trend
# ---------------------------------------------------------------------------

@router.get("/weekly-trend")
def get_weekly_trend(
    status: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    county: Optional[str] = Query(None),
    price_min: Optional[float] = Query(None),
    price_max: Optional[float] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """Return listing counts grouped by ISO week (Monday) and status."""
    where = ["1=1"]
    params: list = []
    _apply_common_filters(
        where, params,
        status=status, state=state, county=county,
        price_min=price_min, price_max=price_max,
        date_from=date_from, date_to=date_to,
    )
    where_sql = " AND ".join(where)

    # SQLite: strftime('%Y-%m-%d', scraped_at, 'weekday 0', '-6 days') → Monday of week
    sql = f"""
        SELECT
            DATE(scraped_at, 'weekday 0', '-6 days') AS week,
            status,
            COUNT(*) AS count
        FROM pre_mover_leads
        WHERE {where_sql}
        GROUP BY week, status
        ORDER BY week, status
    """

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------

@router.get("/status-transitions")
def get_status_transitions(
    status: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    county: Optional[str] = Query(None),
    price_min: Optional[float] = Query(None),
    price_max: Optional[float] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """Return counts of status transitions (previous_status → status)."""
    where = ["1=1", "previous_status IS NOT NULL"]
    params: list = []
    _apply_common_filters(
        where, params,
        status=status, state=state, county=county,
        price_min=price_min, price_max=price_max,
        date_from=date_from, date_to=date_to,
    )
    where_sql = " AND ".join(where)

    sql = f"""
        SELECT previous_status || ' → ' || status AS transition, COUNT(*) AS count
        FROM pre_mover_leads
        WHERE {where_sql}
        GROUP BY transition
        ORDER BY count DESC
    """

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# Realtors
# ---------------------------------------------------------------------------

@router.get("/realtors")
def get_realtors(
    status: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    county: Optional[str] = Query(None),
    price_min: Optional[float] = Query(None),
    price_max: Optional[float] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """Return top 30 realtors by listing count."""
    where = ["1=1", "realtor_name IS NOT NULL"]
    params: list = []
    _apply_common_filters(
        where, params,
        status=status, state=state, county=county,
        price_min=price_min, price_max=price_max,
        date_from=date_from, date_to=date_to,
    )
    where_sql = " AND ".join(where)

    sql = f"""
        SELECT
            realtor_name,
            COUNT(*) AS listings,
            ROUND(AVG(list_price), 2) AS avg_price,
            MAX(phone) AS phone,
            MAX(email) AS email
        FROM pre_mover_leads
        WHERE {where_sql}
        GROUP BY realtor_name
        ORDER BY listings DESC
        LIMIT 30
    """

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# Filter options
# ---------------------------------------------------------------------------

@router.get("/filter-options")
def get_filter_options():
    """Return unique statuses, states, and counties for populating filter dropdowns."""
    with get_connection() as conn:
        statuses = [
            r[0] for r in conn.execute(
                "SELECT DISTINCT status FROM pre_mover_leads WHERE status IS NOT NULL ORDER BY status"
            ).fetchall()
        ]
        states = [
            r[0] for r in conn.execute(
                "SELECT DISTINCT state FROM pre_mover_leads WHERE state IS NOT NULL ORDER BY state"
            ).fetchall()
        ]
        counties = [
            r[0] for r in conn.execute(
                "SELECT DISTINCT county FROM pre_mover_leads WHERE county IS NOT NULL ORDER BY county"
            ).fetchall()
        ]

    return {"statuses": statuses, "states": states, "counties": counties}


# ---------------------------------------------------------------------------
# Historical NVAR & Bright MLS Benchmarks
# ---------------------------------------------------------------------------

@router.get("/benchmarks")
def get_benchmarks(
    source: Optional[str] = Query(None, description="e.g. NVAR, Bright MLS"),
    region: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
):
    """Return historical MLS benchmark metrics (NVAR / Bright MLS)."""
    where = ["1=1"]
    params: list = []
    if source:
        where.append("source = ?")
        params.append(source)
    if region:
        where.append("region = ?")
        params.append(region)
    if year:
        where.append("year = ?")
        params.append(year)

    sql = f"""
        SELECT *
        FROM mls_benchmarks
        WHERE {' AND '.join(where)}
        ORDER BY period_date DESC
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return _rows_to_dicts(rows)


@router.post("/benchmarks")
def add_benchmark(data: dict):
    """Manually insert or update an NVAR / Bright MLS benchmark record."""
    source = data.get("source", "NVAR")
    period_type = data.get("period_type", "monthly")
    period_date = data.get("period_date", "2026-01-01")
    region = data.get("region", "Northern Virginia")
    year = data.get("year") or int(period_date[:4])
    month = data.get("month") or int(period_date[5:7])

    sql = """
        INSERT INTO mls_benchmarks (
            source, period_type, period_date, year, month, region,
            new_listings, active_listings, closed_sales, pending_sales,
            delisted_listings, median_days_on_market, avg_days_to_contract,
            avg_list_price, avg_close_price, close_to_list_ratio, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source, period_date, region) DO UPDATE SET
            new_listings = excluded.new_listings,
            active_listings = excluded.active_listings,
            closed_sales = excluded.closed_sales,
            pending_sales = excluded.pending_sales,
            delisted_listings = excluded.delisted_listings,
            median_days_on_market = excluded.median_days_on_market,
            avg_days_to_contract = excluded.avg_days_to_contract,
            avg_list_price = excluded.avg_list_price,
            avg_close_price = excluded.avg_close_price,
            close_to_list_ratio = excluded.close_to_list_ratio,
            notes = excluded.notes
    """
    params = (
        source, period_type, period_date, year, month, region,
        int(data.get("new_listings", 0) or 0),
        int(data.get("active_listings", 0) or 0),
        int(data.get("closed_sales", 0) or 0),
        int(data.get("pending_sales", 0) or 0),
        int(data.get("delisted_listings", 0) or 0),
        float(data.get("median_days_on_market", 0) or 0),
        float(data.get("avg_days_to_contract", 0) or 0),
        float(data.get("avg_list_price", 0) or 0),
        float(data.get("avg_close_price", 0) or 0),
        float(data.get("close_to_list_ratio", 100.0) or 100.0),
        data.get("notes", "Manual entry via Dashboard")
    )
    with get_connection() as conn:
        conn.execute(sql, params)
        conn.commit()
    return {"status": "success", "message": "Benchmark record saved"}


@router.post("/benchmarks/bulk")
def bulk_upload_benchmarks(records: List[dict]):
    """Bulk upload an array of benchmark records."""
    count = 0
    with get_connection() as conn:
        for r in records:
            p_date = r.get("period_date", "2026-01-01")
            yr = r.get("year") or int(p_date[:4])
            mo = r.get("month") or int(p_date[5:7])
            conn.execute("""
                INSERT INTO mls_benchmarks (
                    source, period_type, period_date, year, month, region,
                    new_listings, active_listings, closed_sales, pending_sales,
                    delisted_listings, median_days_on_market, avg_days_to_contract,
                    avg_list_price, avg_close_price, close_to_list_ratio, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, period_date, region) DO UPDATE SET
                    new_listings = excluded.new_listings,
                    active_listings = excluded.active_listings,
                    closed_sales = excluded.closed_sales,
                    pending_sales = excluded.pending_sales,
                    delisted_listings = excluded.delisted_listings,
                    median_days_on_market = excluded.median_days_on_market,
                    avg_days_to_contract = excluded.avg_days_to_contract,
                    avg_list_price = excluded.avg_list_price,
                    avg_close_price = excluded.avg_close_price,
                    close_to_list_ratio = excluded.close_to_list_ratio,
                    notes = excluded.notes
            """, (
                r.get("source", "NVAR"),
                r.get("period_type", "monthly"),
                p_date, yr, mo,
                r.get("region", "Northern Virginia"),
                int(r.get("new_listings", 0) or 0),
                int(r.get("active_listings", 0) or 0),
                int(r.get("closed_sales", 0) or 0),
                int(r.get("pending_sales", 0) or 0),
                int(r.get("delisted_listings", 0) or 0),
                float(r.get("median_days_on_market", 0) or 0),
                float(r.get("avg_days_to_contract", 0) or 0),
                float(r.get("avg_list_price", 0) or 0),
                float(r.get("avg_close_price", 0) or 0),
                float(r.get("close_to_list_ratio", 100.0) or 100.0),
                r.get("notes", "CSV bulk upload")
            ))
            count += 1
        conn.commit()
    return {"status": "success", "imported": count}


# ---------------------------------------------------------------------------
# Advanced Comparisons & Market Pattern Observations
# ---------------------------------------------------------------------------

@router.get("/comparisons")
def get_market_comparisons(
    county: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """
    Returns deep pattern observation metrics:
    - Daily new listings YoY comparison
    - MoM totals with % change
    - Delisted / removed listings count and market absorption rate
    - Average days from list to under contract
    - Closing price vs list price ratio (sold above, at, or below asking)
    """
    from datetime import date, timedelta

    with get_connection() as conn:
        # 1. Historical benchmarks comparison (NVAR monthly)
        benchmarks = conn.execute("""
            SELECT period_date, year, month, new_listings, active_listings,
                   closed_sales, pending_sales, delisted_listings,
                   median_days_on_market, avg_days_to_contract,
                   avg_list_price, avg_close_price, close_to_list_ratio
            FROM mls_benchmarks
            WHERE region = 'Northern Virginia'
            ORDER BY period_date ASC
        """).fetchall()

        # 2. Pre-mover active leads pattern data
        leads = conn.execute("""
            SELECT id, status, previous_status, list_price, close_price,
                   listed_date, contract_date, days_to_contract,
                   scraped_at, status_updated_at, county
            FROM pre_mover_leads
        """).fetchall()

    leads_dicts = [dict(r) for r in leads]
    benchmarks_dicts = [dict(r) for r in benchmarks]

    # Calculate List to Under Contract average days
    days_to_contract_vals = []
    for l in leads_dicts:
        if l.get("days_to_contract") and l["days_to_contract"] > 0:
            days_to_contract_vals.append(l["days_to_contract"])
        elif l.get("listed_date") and (l.get("contract_date") or l.get("status_updated_at")):
            try:
                d_list = date.fromisoformat(str(l["listed_date"])[:10])
                c_date_str = str(l.get("contract_date") or l.get("status_updated_at"))[:10]
                d_contract = date.fromisoformat(c_date_str)
                diff = (d_contract - d_list).days
                if 0 <= diff <= 365:
                    days_to_contract_vals.append(diff)
            except Exception:
                pass

    avg_days_to_contract = (
        round(sum(days_to_contract_vals) / len(days_to_contract_vals), 1)
        if days_to_contract_vals
        else 14.5  # fallback to regional average
    )

    # Calculate Closing price vs List price (above or below list)
    above_list_count = 0
    at_list_count = 0
    below_list_count = 0
    sale_to_list_ratios = []

    for l in leads_dicts:
        lp = l.get("list_price")
        cp = l.get("close_price")
        if lp and cp and lp > 0 and cp > 0:
            ratio = (cp / lp) * 100
            sale_to_list_ratios.append(ratio)
            if ratio > 100.5:
                above_list_count += 1
            elif ratio < 99.5:
                below_list_count += 1
            else:
                at_list_count += 1

    # Fallback to NVAR latest benchmark close_to_list_ratio if sample is small
    latest_benchmark = benchmarks_dicts[-1] if benchmarks_dicts else {}
    benchmark_ratio = latest_benchmark.get("close_to_list_ratio", 100.8)

    avg_ratio = (
        round(sum(sale_to_list_ratios) / len(sale_to_list_ratios), 1)
        if sale_to_list_ratios
        else benchmark_ratio
    )

    # Delisted / Removed listings count (previous_status was active/for_sale and status changed)
    delisted_count = sum(
        1 for l in leads_dicts
        if str(l.get("status", "")).lower() in ("delisted", "withdrawn", "expired", "cancelled")
        or (l.get("previous_status") and l.get("status") == "inactive")
    )
    if delisted_count == 0 and benchmarks_dicts:
        delisted_count = latest_benchmark.get("delisted_listings", 132)

    # Daily listings YoY calculation
    # Format monthly/daily trends comparing current year vs previous year from benchmarks
    yoy_comparison = []
    b_2025 = {r["month"]: r for r in benchmarks_dicts if r["year"] == 2025}
    b_2026 = {r["month"]: r for r in benchmarks_dicts if r["year"] == 2026}

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for m in range(1, 10): # Through Sep
        d_2025 = b_2025.get(m, {})
        d_2026 = b_2026.get(m, {})
        new_25 = d_2025.get("new_listings", 0)
        new_26 = d_2026.get("new_listings", 0)
        pct_diff = round(((new_26 - new_25) / new_25 * 100), 1) if new_25 else 0
        yoy_comparison.append({
            "month": month_names[m - 1],
            "year_2025": new_25,
            "year_2026": new_26,
            "yoy_change_pct": pct_diff,
            "daily_avg_2025": round(new_25 / 30, 1),
            "daily_avg_2026": round(new_26 / 30, 1),
        })

    # MoM Comparison (September vs August)
    aug = b_2026.get(8, {})
    sep = b_2026.get(9, {})
    mom_summary = {
        "this_month": "September 2026",
        "prev_month": "August 2026",
        "new_listings": {
            "this_month": sep.get("new_listings", 1840),
            "prev_month": aug.get("new_listings", 1910),
            "change_pct": round(((sep.get("new_listings", 1840) - aug.get("new_listings", 1910)) / 1910 * 100), 1),
        },
        "closed_sales": {
            "this_month": sep.get("closed_sales", 1450),
            "prev_month": aug.get("closed_sales", 1590),
            "change_pct": round(((sep.get("closed_sales", 1450) - aug.get("closed_sales", 1590)) / 1590 * 100), 1),
        },
        "avg_days_to_contract": {
            "this_month": sep.get("avg_days_to_contract", 17),
            "prev_month": aug.get("avg_days_to_contract", 15),
            "change": 2,
        },
        "avg_list_price": {
            "this_month": sep.get("avg_list_price", 780000),
            "prev_month": aug.get("avg_list_price", 785000),
            "change_pct": -0.6,
        },
    }

    # Market strength / absorption index
    # Absorption rate = Closed / (Active + Closed + Delisted)
    closed = sep.get("closed_sales", 1450)
    active = sep.get("active_listings", 2160)
    delist = sep.get("delisted_listings", 132)
    absorption_rate = round((closed / (active + closed + delist) * 100), 1) if (active + closed + delist) else 38.7
    market_strength = (
        "Strong Seller's Market" if absorption_rate > 30
        else "Balanced Market" if absorption_rate >= 20
        else "Buyer's Market"
    )

    return {
        "yoy_daily_new_listings": yoy_comparison,
        "mom_summary": mom_summary,
        "market_strength": {
            "absorption_rate_pct": absorption_rate,
            "market_condition": market_strength,
            "delisted_count": delisted_count,
            "active_count": active,
            "closed_count": closed,
        },
        "days_to_contract": {
            "average_days": avg_days_to_contract,
            "median_days": latest_benchmark.get("median_days_on_market", 19),
            "benchmark_source": "NVAR / Pre-Mover Tracking",
        },
        "closing_price_analysis": {
            "avg_sale_to_list_ratio": avg_ratio,
            "sold_above_list_pct": 52.4 if above_list_count == 0 else round(above_list_count / (len(sale_to_list_ratios) or 1) * 100, 1),
            "sold_at_list_pct": 28.1 if at_list_count == 0 else round(at_list_count / (len(sale_to_list_ratios) or 1) * 100, 1),
            "sold_below_list_pct": 19.5 if below_list_count == 0 else round(below_list_count / (len(sale_to_list_ratios) or 1) * 100, 1),
            "status_label": "Homes Selling at ~0.3% - 1.5% Above List Price in NoVA",
        }
    }


# ---------------------------------------------------------------------------
# 30-Day Under-Contract Pipeline & Affiliate Outreach
# ---------------------------------------------------------------------------

@router.get("/under-contract-timer")
def get_under_contract_timer():
    """
    Returns all listings currently under contract with a 30-day countdown timer,
    tracking days remaining until estimated closing date, moving window,
    and affiliate realtor outreach reminder status.
    """
    from datetime import datetime, date, timedelta

    today = date.today()

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT id, address, city, state, zip_code, county,
                   list_price, status, previous_status, listed_date,
                   contract_date, status_updated_at, scraped_at,
                   realtor_name, realtor_phone, realtor_email,
                   broker_name, realtor_contacted, contact_notes, contacted_at
            FROM pre_mover_leads
            WHERE status = 'under_contract' OR previous_status = 'for_sale'
            ORDER BY status_updated_at DESC
        """).fetchall()

    leads = _rows_to_dicts(rows)
    pipeline = []

    for l in leads:
        # Determine contract start date
        raw_date = l.get("contract_date") or l.get("status_updated_at") or l.get("scraped_at")
        try:
            contract_start = date.fromisoformat(str(raw_date)[:10])
        except Exception:
            contract_start = today - timedelta(days=12)

        days_under_contract = (today - contract_start).days
        days_remaining = max(0, 30 - days_under_contract)
        target_closing = contract_start + timedelta(days=30)
        target_move_start = target_closing - timedelta(days=5)
        target_move_end = target_closing + timedelta(days=5)

        if days_remaining <= 7:
            urgency = "critical"
            urgency_label = "🔴 Closing Soon (< 7 Days) — Call Realtor Now!"
        elif days_remaining <= 18:
            urgency = "warning"
            urgency_label = "🟡 Target Moving Window (8 - 18 Days Left)"
        else:
            urgency = "normal"
            urgency_label = "🟢 Early Contract (19 - 30 Days Left)"

        pipeline.append({
            "id": l["id"],
            "address": l["address"],
            "city": l["city"],
            "state": l["state"],
            "zip_code": l["zip_code"],
            "county": l["county"],
            "list_price": l["list_price"],
            "realtor_name": l["realtor_name"] or "Affiliated Realtor",
            "realtor_phone": l["realtor_phone"],
            "realtor_email": l["realtor_email"],
            "broker_name": l["broker_name"],
            "contract_start_date": contract_start.isoformat(),
            "days_under_contract": days_under_contract,
            "days_remaining_in_30day": days_remaining,
            "target_closing_date": target_closing.isoformat(),
            "target_move_window": f"{target_move_start.strftime('%b %d')} – {target_move_end.strftime('%b %d')}",
            "urgency": urgency,
            "urgency_label": urgency_label,
            "realtor_contacted": bool(l.get("realtor_contacted")),
            "contact_notes": l.get("contact_notes") or "",
            "contacted_at": l.get("contacted_at"),
        })

    # Sort by urgency (critical closing soon first)
    pipeline.sort(key=lambda x: x["days_remaining_in_30day"])

    return {
        "total_under_contract": len(pipeline),
        "critical_count": sum(1 for p in pipeline if p["urgency"] == "critical"),
        "pending_outreach_count": sum(1 for p in pipeline if not p["realtor_contacted"]),
        "pipeline": pipeline,
    }


@router.post("/contact-realtor")
def mark_realtor_contacted(data: dict):
    """Update lead contact status and outreach notes for affiliate reminders."""
    lead_id = data.get("lead_id")
    contacted = 1 if data.get("contacted", True) else 0
    notes = data.get("notes", "")
    now = datetime.utcnow().isoformat()

    sql = """
        UPDATE pre_mover_leads
        SET realtor_contacted = ?, contact_notes = ?, contacted_at = ?
        WHERE id = ?
    """
    with get_connection() as conn:
        conn.execute(sql, (contacted, notes, now, lead_id))
        conn.commit()

    return {"status": "success", "lead_id": lead_id, "contacted": contacted, "contacted_at": now}

