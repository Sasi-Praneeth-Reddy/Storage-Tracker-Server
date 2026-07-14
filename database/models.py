"""
database/models.py — Helper functions for reading/writing the SQLite database

Usage:
    from database.models import (
        upsert_facility, insert_pricing_snapshot,
        insert_mls_data, get_latest_pricing, ...
    )
"""

import json
import sqlite3
from datetime import datetime
from typing import Optional

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from database.db_setup import get_connection


# ================================================================
# FACILITIES
# ================================================================

def upsert_facility(data: dict) -> int:
    """
    Insert or update a facility by google_place_id.
    Returns the facility's row ID.
    """
    conn = get_connection()
    now  = datetime.utcnow().isoformat()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO facilities
                (google_place_id, name, brand, address, city, state, zip_code,
                 lat, lon, phone, website, google_rating, google_reviews, last_updated)
            VALUES
                (:google_place_id, :name, :brand, :address, :city, :state, :zip_code,
                 :lat, :lon, :phone, :website, :google_rating, :google_reviews, :last_updated)
            ON CONFLICT(google_place_id) DO UPDATE SET
                name            = excluded.name,
                brand           = excluded.brand,
                address         = excluded.address,
                city            = excluded.city,
                state           = excluded.state,
                zip_code        = excluded.zip_code,
                lat             = excluded.lat,
                lon             = excluded.lon,
                phone           = excluded.phone,
                website         = excluded.website,
                google_rating   = excluded.google_rating,
                google_reviews  = excluded.google_reviews,
                last_updated    = excluded.last_updated
        """, {**data, "last_updated": now})
        conn.commit()
        cur.execute("SELECT id FROM facilities WHERE google_place_id = ?",
                    (data["google_place_id"],))
        row = cur.fetchone()
        return row["id"]
    finally:
        conn.close()


def get_all_facilities() -> list[dict]:
    """Return all facilities as a list of dicts."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM facilities ORDER BY name")
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_facilities_by_zip(zip_code: str) -> list[dict]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM facilities WHERE zip_code = ?", (zip_code,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ================================================================
# PRICING SNAPSHOTS
# ================================================================

def insert_pricing_snapshot(data: dict) -> None:
    """Insert a new pricing snapshot row."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO pricing_snapshots
                (facility_id, unit_size, unit_type, street_rate,
                 web_rate, availability, source)
            VALUES
                (:facility_id, :unit_size, :unit_type, :street_rate,
                 :web_rate, :availability, :source)
        """, data)
        conn.commit()
    finally:
        conn.close()


def get_latest_pricing(facility_id: Optional[int] = None,
                        unit_size: Optional[str] = None) -> list[dict]:
    """
    Return the most recent pricing snapshot for each
    (facility_id, unit_size) combination.
    Optionally filter by facility_id and/or unit_size.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = """
            SELECT p.*, f.name AS facility_name, f.brand, f.address,
                   f.city, f.zip_code, f.lat, f.lon
            FROM pricing_snapshots p
            JOIN facilities f ON f.id = p.facility_id
            WHERE p.scraped_at = (
                SELECT MAX(p2.scraped_at)
                FROM pricing_snapshots p2
                WHERE p2.facility_id = p.facility_id
                  AND p2.unit_size = p.unit_size
            )
        """
        params = []
        if facility_id is not None:
            query += " AND p.facility_id = ?"
            params.append(facility_id)
        if unit_size is not None:
            query += " AND p.unit_size = ?"
            params.append(unit_size)
        query += " ORDER BY p.web_rate ASC"
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_pricing_history(facility_id: int, unit_size: str,
                         days: int = 30) -> list[dict]:
    """Return price history for a specific facility + unit over N days."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM pricing_snapshots
            WHERE facility_id = ?
              AND unit_size = ?
              AND scraped_at >= datetime('now', ?)
            ORDER BY scraped_at ASC
        """, (facility_id, unit_size, f"-{days} days"))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_market_avg_rates(unit_size: str = "10x10",
                          days: int = 30) -> list[dict]:
    """Return daily average web_rate across all facilities for a unit size."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT date(scraped_at) AS day,
                   unit_size,
                   ROUND(AVG(web_rate), 2)    AS avg_web_rate,
                   ROUND(MIN(web_rate), 2)    AS min_web_rate,
                   ROUND(MAX(web_rate), 2)    AS max_web_rate,
                   COUNT(*)                   AS sample_count
            FROM pricing_snapshots
            WHERE unit_size = ?
              AND web_rate IS NOT NULL
              AND scraped_at >= datetime('now', ?)
            GROUP BY day
            ORDER BY day ASC
        """, (unit_size, f"-{days} days"))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ================================================================
# PROMOTIONS
# ================================================================

def upsert_promotion(data: dict) -> None:
    """Insert a promotion or mark an existing one as still active."""
    conn = get_connection()
    now = datetime.utcnow().isoformat()
    try:
        cur = conn.cursor()
        # Check if this exact promo already exists for this facility
        cur.execute("""
            SELECT id FROM promotions
            WHERE facility_id = ? AND description = ? AND is_active = 1
        """, (data["facility_id"], data["description"]))
        existing = cur.fetchone()
        if existing:
            cur.execute("""
                UPDATE promotions SET last_seen = ? WHERE id = ?
            """, (now, existing["id"]))
        else:
            cur.execute("""
                INSERT INTO promotions
                    (facility_id, description, unit_size, discount_pct,
                     expiry_date, source, is_active)
                VALUES
                    (:facility_id, :description, :unit_size, :discount_pct,
                     :expiry_date, :source, 1)
            """, data)
        conn.commit()
    finally:
        conn.close()


def get_active_promotions(zip_code: Optional[str] = None) -> list[dict]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = """
            SELECT p.*, f.name AS facility_name, f.brand,
                   f.address, f.city, f.zip_code
            FROM promotions p
            JOIN facilities f ON f.id = p.facility_id
            WHERE p.is_active = 1
        """
        params = []
        if zip_code:
            query += " AND f.zip_code = ?"
            params.append(zip_code)
        query += " ORDER BY p.found_at DESC"
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ================================================================
# MLS / MARKET DATA
# ================================================================

def insert_mls_data(data: dict) -> None:
    """Insert a housing market data snapshot."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO mls_market_data
                (zip_code, active_listings, median_list_price, median_sqft,
                 price_per_sqft, new_listings_30d, avg_days_on_market, source)
            VALUES
                (:zip_code, :active_listings, :median_list_price, :median_sqft,
                 :price_per_sqft, :new_listings_30d, :avg_days_on_market, :source)
        """, data)
        conn.commit()
    finally:
        conn.close()


def get_latest_mls_by_zip() -> list[dict]:
    """Return the most recent housing market snapshot for each ZIP code."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT *
            FROM mls_market_data
            WHERE fetched_at = (
                SELECT MAX(m2.fetched_at)
                FROM mls_market_data m2
                WHERE m2.zip_code = mls_market_data.zip_code
            )
            ORDER BY zip_code
        """)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ================================================================
# LOGGING
# ================================================================

def log_email(recipients: list, subject: str, status: str,
              error_msg: str = None, message_id: str = None) -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO email_log (recipients, subject, status, error_msg, message_id)
            VALUES (?, ?, ?, ?, ?)
        """, (json.dumps(recipients), subject, status, error_msg, message_id))
        conn.commit()
    finally:
        conn.close()


def log_scrape(source: str, status: str, records_written: int = 0,
               error_msg: str = None, duration_sec: float = None) -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO scrape_log
                (source, status, records_written, error_msg, duration_sec)
            VALUES (?, ?, ?, ?, ?)
        """, (source, status, records_written, error_msg, duration_sec))
        conn.commit()
    finally:
        conn.close()
