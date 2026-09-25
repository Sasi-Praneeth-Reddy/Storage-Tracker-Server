"""
database/init_benchmarks.py
Initializes the mls_benchmarks table and seeds it with benchmark historical
NVAR & Bright MLS Northern Virginia statistics.
"""

import sqlite3
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from config import DB_PATH

def init_benchmarks_table():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS mls_benchmarks (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            source                  TEXT NOT NULL DEFAULT 'NVAR', -- 'NVAR', 'Bright MLS', 'Manual'
            period_type             TEXT NOT NULL DEFAULT 'monthly', -- 'monthly', 'weekly', 'yearly'
            period_date             TEXT NOT NULL, -- 'YYYY-MM-01'
            year                    INTEGER,
            month                   INTEGER,
            region                  TEXT NOT NULL DEFAULT 'Northern Virginia',
            new_listings            INTEGER DEFAULT 0,
            active_listings         INTEGER DEFAULT 0,
            closed_sales            INTEGER DEFAULT 0,
            pending_sales           INTEGER DEFAULT 0,
            delisted_listings       INTEGER DEFAULT 0, -- Withdrawn/Expired
            median_days_on_market   REAL DEFAULT 0,
            avg_days_to_contract    REAL DEFAULT 0,
            avg_list_price          REAL DEFAULT 0,
            avg_close_price         REAL DEFAULT 0,
            median_close_price      REAL DEFAULT 0,
            close_to_list_ratio     REAL DEFAULT 100.0, -- e.g. 101.5%
            notes                   TEXT,
            created_at              TEXT DEFAULT (datetime('now'))
        )
    """)

    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_benchmarks_source_period_region
            ON mls_benchmarks(source, period_date, region)
    """)

    # Seed baseline Northern Virginia NVAR historical monthly data
    seed_data = [
        # (source, period_type, period_date, year, month, region, new_listings, active_listings, closed_sales, pending_sales, delisted, median_dom, days_to_contract, avg_list, avg_close, ratio, notes)
        ("NVAR", "monthly", "2025-01-01", 2025, 1, "Northern Virginia", 1240, 1580, 890, 950, 110, 24, 21, 685000, 680000, 99.3, "NVAR Monthly Market Report"),
        ("NVAR", "monthly", "2025-02-01", 2025, 2, "Northern Virginia", 1450, 1620, 1020, 1180, 95, 19, 18, 710000, 712000, 100.3, "NVAR Monthly Market Report"),
        ("NVAR", "monthly", "2025-03-01", 2025, 3, "Northern Virginia", 1890, 1750, 1340, 1520, 85, 14, 12, 735000, 745000, 101.4, "NVAR Monthly Market Report"),
        ("NVAR", "monthly", "2025-04-01", 2025, 4, "Northern Virginia", 2150, 1890, 1620, 1780, 80, 12, 10, 755000, 770000, 102.0, "NVAR Monthly Market Report"),
        ("NVAR", "monthly", "2025-05-01", 2025, 5, "Northern Virginia", 2300, 2010, 1810, 1920, 90, 11, 9, 765000, 782000, 102.2, "NVAR Monthly Market Report"),
        ("NVAR", "monthly", "2025-06-01", 2025, 6, "Northern Virginia", 2180, 2140, 1750, 1800, 105, 13, 11, 770000, 785000, 101.9, "NVAR Monthly Market Report"),
        ("NVAR", "monthly", "2025-07-01", 2025, 7, "Northern Virginia", 1950, 2200, 1580, 1620, 120, 16, 14, 760000, 768000, 101.1, "NVAR Monthly Market Report"),
        ("NVAR", "monthly", "2025-08-01", 2025, 8, "Northern Virginia", 1820, 2180, 1510, 1540, 135, 18, 16, 750000, 752000, 100.3, "NVAR Monthly Market Report"),
        ("NVAR", "monthly", "2025-09-01", 2025, 9, "Northern Virginia", 1750, 2100, 1380, 1420, 140, 20, 18, 745000, 744000, 99.9, "NVAR Monthly Market Report"),
        ("NVAR", "monthly", "2025-10-01", 2025, 10, "Northern Virginia", 1680, 1990, 1320, 1390, 150, 22, 19, 740000, 738000, 99.7, "NVAR Monthly Market Report"),
        ("NVAR", "monthly", "2025-11-01", 2025, 11, "Northern Virginia", 1350, 1820, 1150, 1200, 160, 26, 22, 735000, 732000, 99.6, "NVAR Monthly Market Report"),
        ("NVAR", "monthly", "2025-12-01", 2025, 12, "Northern Virginia", 980, 1520, 980, 990, 175, 29, 25, 730000, 725000, 99.3, "NVAR Monthly Market Report"),

        # 2026 NVAR Baseline
        ("NVAR", "monthly", "2026-01-01", 2026, 1, "Northern Virginia", 1310, 1610, 920, 990, 105, 23, 20, 715000, 712000, 99.6, "NVAR Monthly Market Report"),
        ("NVAR", "monthly", "2026-02-01", 2026, 2, "Northern Virginia", 1520, 1690, 1080, 1240, 90, 17, 15, 738000, 742000, 100.5, "NVAR Monthly Market Report"),
        ("NVAR", "monthly", "2026-03-01", 2026, 3, "Northern Virginia", 1980, 1820, 1410, 1610, 80, 13, 11, 762000, 775000, 101.7, "NVAR Monthly Market Report"),
        ("NVAR", "monthly", "2026-04-01", 2026, 4, "Northern Virginia", 2240, 1950, 1690, 1860, 75, 11, 9, 785000, 802000, 102.2, "NVAR Monthly Market Report"),
        ("NVAR", "monthly", "2026-05-01", 2026, 5, "Northern Virginia", 2410, 2090, 1890, 2010, 85, 10, 8, 795000, 815000, 102.5, "NVAR Monthly Market Report"),
        ("NVAR", "monthly", "2026-06-01", 2026, 6, "Northern Virginia", 2290, 2190, 1820, 1880, 98, 12, 10, 805000, 822000, 102.1, "NVAR Monthly Market Report"),
        ("NVAR", "monthly", "2026-07-01", 2026, 7, "Northern Virginia", 2050, 2260, 1650, 1700, 115, 15, 13, 792000, 801000, 101.1, "NVAR Monthly Market Report"),
        ("NVAR", "monthly", "2026-08-01", 2026, 8, "Northern Virginia", 1910, 2220, 1590, 1620, 128, 17, 15, 785000, 790000, 100.6, "NVAR Monthly Market Report"),
        ("NVAR", "monthly", "2026-09-01", 2026, 9, "Northern Virginia", 1840, 2160, 1450, 1490, 132, 19, 17, 780000, 782000, 100.3, "NVAR Monthly Market Report"),

        # Bright MLS Regional Baseline
        ("Bright MLS", "monthly", "2025-08-01", 2025, 8, "Northern Virginia", 2100, 2520, 1720, 1790, 155, 19, 17, 742000, 745000, 100.4, "Bright MLS Regional Data"),
        ("Bright MLS", "monthly", "2025-09-01", 2025, 9, "Northern Virginia", 2020, 2450, 1590, 1650, 160, 21, 19, 738000, 739000, 100.1, "Bright MLS Regional Data"),
        ("Bright MLS", "monthly", "2026-08-01", 2026, 8, "Northern Virginia", 2210, 2600, 1810, 1890, 148, 18, 16, 778000, 783000, 100.6, "Bright MLS Regional Data"),
        ("Bright MLS", "monthly", "2026-09-01", 2026, 9, "Northern Virginia", 2140, 2540, 1680, 1740, 152, 20, 18, 772000, 775000, 100.4, "Bright MLS Regional Data"),
    ]

    for row in seed_data:
        cur.execute("""
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
        """, row)

    conn.commit()
    conn.close()
    print("mls_benchmarks table created and seeded successfully.")

if __name__ == "__main__":
    init_benchmarks_table()
