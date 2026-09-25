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
