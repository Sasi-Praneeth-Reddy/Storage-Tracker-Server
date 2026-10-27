"""
routers/storage.py — Storage facility & pricing endpoints.
"""

import os
import signal
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Query

from api.database import get_connection

router = APIRouter(prefix="/api/storage", tags=["storage"])

# Project root is three levels up from this file: api/routers/storage.py
PROJECT_ROOT: Path = Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _rows_to_dicts(rows) -> List[dict]:
    """Convert sqlite3.Row objects to plain dicts."""
    return [dict(r) for r in rows]


def _build_brand_filter(brands_param: Optional[str]) -> tuple:
    """Parse comma-separated brand string into SQL fragment + params."""
    if not brands_param:
        return "", []
    brands = [b.strip() for b in brands_param.split(",") if b.strip()]
    if not brands:
        return "", []
    placeholders = ",".join(["?" for _ in brands])
    return f" AND f.brand IN ({placeholders})", brands


# ---------------------------------------------------------------------------
# Facilities
# ---------------------------------------------------------------------------

@router.get("/facilities")
def get_facilities(
    brand: Optional[str] = Query(None, description="Comma-separated brand names"),
    unit_size: Optional[str] = Query(None),
):
    """Return all facilities with their latest pricing snapshot per unit_size."""
    sql = """
        SELECT f.id, f.name, f.brand, f.address, f.city, f.state, f.zip_code,
               f.lat AS latitude, f.lon AS longitude,
               p.unit_size, p.web_rate, p.availability, p.scraped_at
        FROM facilities f
        LEFT JOIN (
            SELECT facility_id, unit_size, web_rate, availability, scraped_at,
                   ROW_NUMBER() OVER(PARTITION BY facility_id, unit_size ORDER BY scraped_at DESC) AS rn
            FROM pricing_snapshots
        ) p ON f.id = p.facility_id AND p.rn = 1
        WHERE 1=1
    """
    params: list = []

    brand_clause, brand_params = _build_brand_filter(brand)
    sql += brand_clause
    params.extend(brand_params)

    if unit_size:
        sql += " AND p.unit_size = ?"
        params.append(unit_size)

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

@router.get("/kpis")
def get_kpis(
    unit_size: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
):
    """Return high-level KPI metrics for the storage dashboard."""
    # Build base joins/filters
    where_clauses = ["1=1"]
    params: list = []

    brand_clause, brand_params = _build_brand_filter(brand)
    if brand_clause:
        # strip the leading ' AND ' prefix since we're building manually
        where_clauses.append(brand_clause.lstrip(" AND "))
        params.extend(brand_params)

    unit_size_clause = ""
    us_params: list = []
    if unit_size:
        unit_size_clause = " AND p.unit_size = ?"
        us_params.append(unit_size)

    with get_connection() as conn:
        # Total distinct facilities
        total_sql = f"""
            SELECT COUNT(DISTINCT f.id) AS cnt
            FROM facilities f
            LEFT JOIN (
                SELECT facility_id, unit_size, web_rate, availability,
                       ROW_NUMBER() OVER(PARTITION BY facility_id, unit_size ORDER BY scraped_at DESC) AS rn
                FROM pricing_snapshots
            ) p ON f.id = p.facility_id AND p.rn = 1
            WHERE f.brand IS NOT NULL {brand_clause} {unit_size_clause}
        """
        total_facilities = conn.execute(total_sql, params + us_params).fetchone()[0] or 0

        # Average rate
        avg_sql = f"""
            SELECT AVG(p.web_rate) AS avg_rate
            FROM facilities f
            JOIN (
                SELECT facility_id, unit_size, web_rate, availability,
                       ROW_NUMBER() OVER(PARTITION BY facility_id, unit_size ORDER BY scraped_at DESC) AS rn
                FROM pricing_snapshots
            ) p ON f.id = p.facility_id AND p.rn = 1
            WHERE p.web_rate IS NOT NULL {brand_clause} {unit_size_clause}
        """
        avg_rate_row = conn.execute(avg_sql, params + us_params).fetchone()
        avg_rate = round(avg_rate_row[0], 2) if avg_rate_row and avg_rate_row[0] is not None else None

        # Dominant brand
        dom_sql = f"""
            SELECT f.brand, COUNT(DISTINCT f.id) AS cnt
            FROM facilities f
            WHERE f.brand IS NOT NULL {brand_clause}
            GROUP BY f.brand
            ORDER BY cnt DESC
            LIMIT 1
        """
        dom_row = conn.execute(dom_sql, params).fetchone()
        dominant_brand = dom_row["brand"] if dom_row else None

        # Available count
        avail_sql = f"""
            SELECT COUNT(*) AS cnt
            FROM facilities f
            JOIN (
                SELECT facility_id, unit_size, web_rate, availability,
                       ROW_NUMBER() OVER(PARTITION BY facility_id, unit_size ORDER BY scraped_at DESC) AS rn
                FROM pricing_snapshots
            ) p ON f.id = p.facility_id AND p.rn = 1
            WHERE p.availability = 1 {brand_clause} {unit_size_clause}
        """
        avail_row = conn.execute(avail_sql, params + us_params).fetchone()
        available_count = avail_row[0] if avail_row else 0

    return {
        "total_facilities": total_facilities,
        "avg_rate": avg_rate,
        "dominant_brand": dominant_brand,
        "available_count": available_count,
    }


# ---------------------------------------------------------------------------
# Price history
# ---------------------------------------------------------------------------

@router.get("/price-history")
def get_price_history(
    unit_size: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """Return avg web_rate grouped by brand and day."""
    sql = """
        SELECT DATE(p.scraped_at) AS snap_date,
               f.brand,
               ROUND(AVG(p.web_rate), 2) AS avg_rate
        FROM pricing_snapshots p
        JOIN facilities f ON f.id = p.facility_id
        WHERE p.web_rate IS NOT NULL
    """
    params: list = []

    if unit_size:
        sql += " AND p.unit_size = ?"
        params.append(unit_size)

    brand_clause, brand_params = _build_brand_filter(brand)
    if brand_clause:
        sql += brand_clause.replace("f.brand", "f.brand")
        params.extend(brand_params)

    if date_from:
        sql += " AND DATE(p.scraped_at) >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND DATE(p.scraped_at) <= ?"
        params.append(date_to)

    sql += " GROUP BY snap_date, f.brand ORDER BY snap_date"

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# Market share
# ---------------------------------------------------------------------------

@router.get("/market-share")
def get_market_share():
    """Return facility count per brand for a pie chart."""
    sql = """
        SELECT brand, COUNT(*) AS count
        FROM facilities
        WHERE brand IS NOT NULL
        GROUP BY brand
        ORDER BY count DESC
    """
    with get_connection() as conn:
        rows = conn.execute(sql).fetchall()
    return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# Price movement
# ---------------------------------------------------------------------------

@router.get("/price-movement")
def get_price_movement(
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD start of THIS period"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD end of THIS period"),
):
    """Compare current vs previous period avg rate by unit_size."""
    params_this: list = []
    params_prev: list = []

    date_filter_this = "1=1"
    date_filter_prev = "1=1"

    if date_from and date_to:
        # Current period
        date_filter_this = "DATE(scraped_at) BETWEEN ? AND ?"
        params_this = [date_from, date_to]

        # Previous period of equal length
        from datetime import date, timedelta
        d_from = date.fromisoformat(date_from)
        d_to = date.fromisoformat(date_to)
        delta = d_to - d_from
        prev_to = d_from - timedelta(days=1)
        prev_from = prev_to - delta
        date_filter_prev = "DATE(scraped_at) BETWEEN ? AND ?"
        params_prev = [prev_from.isoformat(), prev_to.isoformat()]

    sql = f"""
        WITH this_period AS (
            SELECT unit_size, ROUND(AVG(web_rate), 2) AS this_period
            FROM pricing_snapshots
            WHERE web_rate IS NOT NULL AND {date_filter_this}
            GROUP BY unit_size
        ),
        prev_period AS (
            SELECT unit_size, ROUND(AVG(web_rate), 2) AS prev_period
            FROM pricing_snapshots
            WHERE web_rate IS NOT NULL AND {date_filter_prev}
            GROUP BY unit_size
        )
        SELECT t.unit_size,
               t.this_period,
               p.prev_period,
               ROUND(t.this_period - COALESCE(p.prev_period, t.this_period), 2) AS change_dollar,
               CASE WHEN p.prev_period > 0
                    THEN ROUND(((t.this_period - p.prev_period) / p.prev_period) * 100, 2)
                    ELSE NULL
               END AS change_pct
        FROM this_period t
        LEFT JOIN prev_period p ON t.unit_size = p.unit_size
        ORDER BY t.unit_size
    """

    with get_connection() as conn:
        rows = conn.execute(sql, params_this + params_prev).fetchall()

    return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# Reference lists
# ---------------------------------------------------------------------------

DEFAULT_UNIT_SIZES = ["5x5", "5x10", "10x10", "10x15", "10x20", "10x25", "10x30"]
DEFAULT_BRANDS = [
    "Public Storage",
    "Extra Space Storage",
    "CubeSmart",
    "Life Storage",
    "U-Haul",
    "StorQuest",
    "Simply Self Storage",
]


@router.get("/brands")
def get_brands():
    """Return sorted list of unique brands."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT brand FROM facilities WHERE brand IS NOT NULL ORDER BY brand"
        ).fetchall()
    brands = [r["brand"] for r in rows if r["brand"]]
    return brands if brands else DEFAULT_BRANDS


@router.get("/unit-sizes")
def get_unit_sizes():
    """Return sorted list of unique unit sizes."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT unit_size FROM pricing_snapshots WHERE unit_size IS NOT NULL ORDER BY unit_size"
        ).fetchall()
    sizes = [r["unit_size"] for r in rows if r["unit_size"]]
    return sizes if sizes else DEFAULT_UNIT_SIZES


# ---------------------------------------------------------------------------
# Scraper control
# ---------------------------------------------------------------------------

STATUS_FILE: Path = PROJECT_ROOT / ".scraper_status"
PID_FILE: Path = PROJECT_ROOT / ".scraper_pid"


@router.post("/scraper/start")
def scraper_start():
    """Signal the scraper to start by writing a status sentinel file and launching background worker."""
    if STATUS_FILE.exists():
        return {"started": False, "message": "Scraper is already running"}

    import subprocess
    import sys
    import threading

    STATUS_FILE.write_text("running")

    def bg_run():
        try:
            proc = subprocess.Popen(
                [sys.executable, "-c", "from collectors.run_all import run_self_storage; run_self_storage(dry_run=False)"],
                cwd=str(PROJECT_ROOT)
            )
            PID_FILE.write_text(str(proc.pid))
            proc.wait()
        except Exception as e:
            print(f"Scraper error: {e}")
        finally:
            if STATUS_FILE.exists():
                try: STATUS_FILE.unlink()
                except Exception: pass
            if PID_FILE.exists():
                try: PID_FILE.unlink()
                except Exception: pass

    threading.Thread(target=bg_run, daemon=True).start()
    return {"started": True}


@router.get("/scraper/status")
def scraper_status():
    """Check whether the scraper status sentinel file exists."""
    return {"running": STATUS_FILE.exists()}


@router.post("/scraper/stop")
def scraper_stop():
    """Remove the sentinel file and attempt to kill the PID from the pid file."""
    if STATUS_FILE.exists():
        try: STATUS_FILE.unlink()
        except Exception: pass

    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            if os.name == "nt":
                os.system(f"taskkill /PID {pid} /F")
            else:
                os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
        try:
            PID_FILE.unlink()
        except Exception:
            pass

    return {"stopped": True}

