"""
database/db_setup.py — SQLite schema creation

Run this once to initialize the database:
    python database/db_setup.py

Tables:
    facilities          — Storage facilities discovered via Google Maps / scraping
    pricing_snapshots   — Daily price/availability snapshots per unit size
    mls_market_data     — Housing market stats per ZIP (from RentCast)
    promotions          — Current discounts/specials found during scraping
    email_log           — Record of every email sent by the system
    scrape_log          — Audit log for each collector run
"""

import sqlite3
import sys
import pathlib

# Allow running from any directory
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from config import DB_PATH


def create_tables(conn: sqlite3.Connection) -> None:
    """Create all tables if they don't already exist."""
    cursor = conn.cursor()

    # ── Facilities ──────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS facilities (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            google_place_id TEXT    UNIQUE,
            name            TEXT    NOT NULL,
            brand           TEXT,                   -- e.g. "Public Storage"
            address         TEXT,
            city            TEXT,
            state           TEXT,
            zip_code        TEXT,
            lat             REAL,
            lon             REAL,
            phone           TEXT,
            website         TEXT,
            google_rating   REAL,
            google_reviews  INTEGER,
            first_seen      TEXT    DEFAULT (datetime('now')),
            last_updated    TEXT    DEFAULT (datetime('now'))
        )
    """)

    # ── Pricing Snapshots ────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pricing_snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            facility_id     INTEGER NOT NULL REFERENCES facilities(id),
            unit_size       TEXT    NOT NULL,   -- e.g. "10x10"
            unit_type       TEXT,               -- e.g. "Climate Controlled", "Drive-Up"
            street_rate     REAL,               -- Regular/walk-in price ($/mo)
            web_rate        REAL,               -- Online/web rate ($/mo)
            availability    TEXT,               -- "available", "limited", "waitlist", "unavailable"
            source          TEXT,               -- "sparefoot", "public_storage", "extra_space", etc.
            scraped_at      TEXT    DEFAULT (datetime('now'))
        )
    """)

    # Index for fast time-series queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pricing_facility_size_date
            ON pricing_snapshots(facility_id, unit_size, scraped_at)
    """)

    # ── Promotions ───────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS promotions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            facility_id     INTEGER NOT NULL REFERENCES facilities(id),
            description     TEXT    NOT NULL,   -- e.g. "First month free", "50% off 3 months"
            unit_size       TEXT,               -- Which unit size this applies to (NULL = any)
            discount_pct    REAL,               -- Discount percentage if parseable
            expiry_date     TEXT,               -- When the promo expires (if shown)
            source          TEXT,
            found_at        TEXT    DEFAULT (datetime('now')),
            last_seen       TEXT    DEFAULT (datetime('now')),
            is_active       INTEGER DEFAULT 1   -- 1=active, 0=expired
        )
    """)

    # ── MLS / Housing Market Data ────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mls_market_data (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            zip_code            TEXT    NOT NULL,
            active_listings     INTEGER,
            median_list_price   REAL,
            median_sqft         REAL,
            price_per_sqft      REAL,
            new_listings_30d    INTEGER,
            avg_days_on_market  REAL,
            source              TEXT    DEFAULT 'rentcast',
            fetched_at          TEXT    DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_mls_zip_date
            ON mls_market_data(zip_code, fetched_at)
    """)

    # ── Pre-Mover Leads (USA Home Listings) ──────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pre_mover_leads (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            address       TEXT,
            city          TEXT,
            state         TEXT,
            zip_code      TEXT,
            county        TEXT,
            status        TEXT,
            list_price    REAL,
            bedrooms      INTEGER,
            bathrooms     REAL,
            sqft          INTEGER,
            is_vacant     INTEGER DEFAULT 0,
            listed_date   TEXT,
            first_name    TEXT,
            last_name     TEXT,
            owner_full_name TEXT,
            email         TEXT,
            email_2       TEXT,
            phone         TEXT,
            phone_type    TEXT,
            phone_2       TEXT,
            phone_2_type  TEXT,
            realtor_name  TEXT,
            realtor_email TEXT,
            realtor_phone TEXT,
            realtor_phone_2 TEXT,
            realtor_phone_3 TEXT,
            realtor_address TEXT,
            broker_name   TEXT,
            broker_email  TEXT,
            broker_phone  TEXT,
            broker_phone_2 TEXT,
            broker_phone_3 TEXT,
            broker_address TEXT,
            longitude     REAL,
            latitude      REAL,
            source_id     TEXT,
            scraped_at    TEXT DEFAULT (datetime('now'))
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_leads_zip_date
            ON pre_mover_leads(zip_code, scraped_at)
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_address_zip
            ON pre_mover_leads(address, zip_code)
    """)

    # ── Email Log ────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            recipients  TEXT    NOT NULL,   -- JSON array of addresses
            subject     TEXT,
            status      TEXT,               -- "sent", "failed"
            error_msg   TEXT,
            message_id  TEXT,               -- Brevo message ID
            sent_at     TEXT    DEFAULT (datetime('now'))
        )
    """)

    # ── Scrape Log ───────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scrape_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            source          TEXT    NOT NULL,   -- collector name
            status          TEXT    NOT NULL,   -- "success", "partial", "failed"
            records_written INTEGER DEFAULT 0,
            error_msg       TEXT,
            duration_sec    REAL,
            run_at          TEXT    DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    print("All tables created (or already exist).")


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with row_factory set."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row      # rows behave like dicts
    conn.execute("PRAGMA journal_mode=WAL")   # better concurrent read perf
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


if __name__ == "__main__":
    print("Initializing database at: {}".format(DB_PATH))
    conn = get_connection()
    create_tables(conn)
    conn.close()
    print("Database is ready.")
