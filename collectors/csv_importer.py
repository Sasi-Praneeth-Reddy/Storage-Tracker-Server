"""
collectors/csv_importer.py

Imports CSV files exported from the USA Home Listings portal
into the SQLite database (pre_mover_leads table).

Handles:
- Single large CSV or multiple filtered CSVs
- Auto-detects column names (portal may use different headers)
- Deduplicates on address + listed_date
- Exports clean filtered CSVs by county/ZIP for easy re-download

Usage:
    # Import all CSVs from Downloads folder:
    venv\\Scripts\\python collectors/csv_importer.py

    # Import a specific file:
    venv\\Scripts\\python collectors/csv_importer.py --file "C:/Users/.../Downloads/listings.csv"

    # Export filtered CSVs (one per county) after importing:
    venv\\Scripts\\python collectors/csv_importer.py --export-by county

    # Export filtered CSVs by state:
    venv\\Scripts\\python collectors/csv_importer.py --export-by state
"""

import sys
import csv
import re
import pathlib
import logging
import argparse
import sqlite3
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from database.db_setup import get_connection, create_tables

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Where to look for CSVs automatically
DOWNLOADS_DIR = pathlib.Path.home() / "Downloads"
PROJECT_DATA_DIR = pathlib.Path(__file__).parent.parent / "data" / "imports"

# Where to write exported filtered CSVs
EXPORT_DIR = pathlib.Path(__file__).parent.parent / "data" / "exports"

# ── Column name mapping ──────────────────────────────────────────
# Maps possible portal column names -> our standard names
# Add more aliases here if the portal uses different headers
COLUMN_MAP = {
    # Address fields
    "address":            "address",
    "street":             "address",
    "street_address":     "address",
    "property_address":   "address",
    "mailing_address":    "address",

    # City
    "city":               "city",
    "city_name":          "city",

    # State
    "state":              "state",
    "state_code":         "state",
    "st":                 "state",

    # ZIP
    "zip":                "zip_code",
    "zip_code":           "zip_code",
    "zipcode":            "zip_code",
    "postal_code":        "zip_code",

    # County
    "county":             "county",
    "county_name":        "county",

    # Status
    "status":             "status",
    "listing_status":     "status",
    "mls_status":         "status",
    "property_status":    "status",

    # Price
    "price":              "list_price",
    "list_price":         "list_price",
    "listing_price":      "list_price",
    "asking_price":       "list_price",
    "sale_price":         "list_price",

    # Bedrooms
    "beds":               "bedrooms",
    "bedrooms":           "bedrooms",
    "bd":                 "bedrooms",
    "br":                 "bedrooms",
    "num_bedrooms":       "bedrooms",

    # Bathrooms
    "baths":              "bathrooms",
    "bathrooms":          "bathrooms",
    "ba":                 "bathrooms",
    "num_bathrooms":      "bathrooms",

    # Sqft
    "sqft":               "sqft",
    "sq_ft":              "sqft",
    "square_feet":        "sqft",
    "living_area":        "sqft",
    "size":               "sqft",

    # Date
    "list_date":          "listed_date",
    "listing_date":       "listed_date",
    "listed_date":        "listed_date",
    "date_listed":        "listed_date",
    "on_market_date":     "listed_date",
    "active_date":        "listed_date",

    # Vacancy
    "vacant":             "is_vacant",
    "is_vacant":          "is_vacant",
    "vacancy":            "is_vacant",
    "vacancy_ai":         "is_vacant",

    # ID
    "id":                 "source_id",
    "listing_id":         "source_id",
    "mls_id":             "source_id",
    "property_id":        "source_id",

    # Coordinates
    "latitude":           "latitude",
    "lat":                "latitude",
    "longitude":          "longitude",
    "lng":                "longitude",
    "lon":                "longitude",
}

# Status normalisation
STATUS_MAP = {
    "active":           "for_sale",
    "for sale":         "for_sale",
    "for_sale":         "for_sale",
    "new":              "for_sale",
    "pending":          "under_contract",
    "under contract":   "under_contract",
    "under_contract":   "under_contract",
    "contingent":       "under_contract",
    "sold":             "sold",
    "closed":           "sold",
    "expired":          "expired",
    "withdrawn":        "expired",
    "cancelled":        "expired",
}


# ── DB setup ─────────────────────────────────────────────────────

def ensure_leads_table():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pre_mover_leads (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            address           TEXT,
            city              TEXT,
            state             TEXT,
            county            TEXT,
            zip_code          TEXT,
            status            TEXT,
            previous_status   TEXT,
            status_updated_at TEXT,
            list_price        REAL,
            bedrooms          INTEGER,
            bathrooms         REAL,
            sqft              INTEGER,
            is_vacant         INTEGER DEFAULT 0,
            listed_date       TEXT,
            source_id         TEXT,
            import_file       TEXT,
            scraped_at        TEXT DEFAULT (datetime('now')),
            latitude          REAL,
            longitude         REAL,
            UNIQUE(address, zip_code)
        )
    """)
    # Add columns that may not exist in older schemas
    for col_def in [
        "county TEXT",
        "import_file TEXT",
        "previous_status TEXT",
        "status_updated_at TEXT",
    ]:
        try:
            conn.execute("ALTER TABLE pre_mover_leads ADD COLUMN {}".format(col_def))
        except Exception:
            pass  # Column already exists

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_leads_zip
            ON pre_mover_leads(zip_code)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_leads_county
            ON pre_mover_leads(county)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_leads_state
            ON pre_mover_leads(state)
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_address_zip
            ON pre_mover_leads(address, zip_code)
    """)
    conn.commit()
    conn.close()


# ── CSV parsing ──────────────────────────────────────────────────

def map_headers(raw_headers: list) -> dict:
    """Map raw CSV headers to our standard column names."""
    mapping = {}
    for i, h in enumerate(raw_headers):
        normalised = h.strip().lower().replace(" ", "_").replace("-", "_")
        if normalised in COLUMN_MAP:
            mapping[i] = COLUMN_MAP[normalised]
        else:
            # Keep unknown columns as-is (lowercase)
            mapping[i] = normalised
    return mapping


def parse_price(value: str) -> float | None:
    if not value:
        return None
    cleaned = value.replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_int(value: str) -> int | None:
    if not value:
        return None
    try:
        return int(float(value.strip()))
    except ValueError:
        return None


def parse_float(value: str) -> float | None:
    if not value:
        return None
    try:
        return float(value.strip())
    except ValueError:
        return None


def parse_vacant(value: str) -> int:
    if not value:
        return 0
    return 1 if value.strip().lower() in ("yes", "true", "1", "vacant", "y") else 0


def normalise_status(raw: str) -> str:
    if not raw:
        return "for_sale"
    return STATUS_MAP.get(raw.strip().lower(), raw.strip().lower())


def parse_row(row: list, header_map: dict) -> dict:
    """Convert a CSV row list into a standardised lead dict."""
    raw = {}
    for i, value in enumerate(row):
        col = header_map.get(i, "col_{}".format(i))
        raw[col] = value.strip() if value else ""

    lead = {
        "address":     raw.get("address", ""),
        "city":        raw.get("city", ""),
        "state":       raw.get("state", ""),
        "county":      raw.get("county", ""),
        "zip_code":    raw.get("zip_code", "")[:5] if raw.get("zip_code") else "",
        "status":      normalise_status(raw.get("status", "")),
        "list_price":  parse_price(raw.get("list_price", "")),
        "bedrooms":    parse_int(raw.get("bedrooms", "")),
        "bathrooms":   parse_int(raw.get("bathrooms", "")),
        "sqft":        parse_int(raw.get("sqft", "")),
        "is_vacant":   parse_vacant(raw.get("is_vacant", "")),
        "listed_date": raw.get("listed_date", ""),
        "source_id":   raw.get("source_id", ""),
        "latitude":    parse_float(raw.get("latitude", "")),
        "longitude":   parse_float(raw.get("longitude", "")),
    }
    return lead


def import_csv(filepath: pathlib.Path) -> tuple[int, int]:
    """
    Import a single CSV file into pre_mover_leads.
    Returns (rows_imported, rows_skipped).
    """
    imported = 0
    skipped  = 0
    conn = get_connection()

    try:
        with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.reader(f)
            headers = next(reader, None)
            if not headers:
                log.warning("Empty file: %s", filepath.name)
                return 0, 0

            header_map = map_headers(headers)
            log.info("  Columns detected: %s", list(header_map.values())[:10])

            batch = []
            for row_num, row in enumerate(reader, start=2):
                if not any(row):
                    continue
                lead = parse_row(row, header_map)
                lead["import_file"] = filepath.name

                if not lead["address"] and not lead["zip_code"]:
                    skipped += 1
                    continue

                scraped_at_val = None
                date_matches = re.findall(r'\d{4}-\d{2}-\d{2}', filepath.name)
                if date_matches:
                    scraped_at_val = f"{date_matches[-1]} 12:00:00"

                batch.append((
                    lead["address"], lead["city"], lead["state"],
                    lead["county"], lead["zip_code"], lead["status"],
                    lead["list_price"], lead["bedrooms"], lead["bathrooms"],
                    lead["sqft"], lead["is_vacant"], lead["listed_date"],
                    lead["source_id"], lead["import_file"], lead["latitude"],
                    lead["longitude"], scraped_at_val,
                ))

                # Write in batches of 500
                if len(batch) >= 500:
                    imported += _write_batch(conn, batch)
                    batch = []

            if batch:
                imported += _write_batch(conn, batch)

        conn.commit()
        
        # Delete file after successful import to save space
        try:
            filepath.unlink()
            log.info("  Deleted %s", filepath.name)
        except Exception as e:
            log.warning("  Could not delete %s: %s", filepath.name, e)
            
    except Exception as exc:
        log.error("Error reading %s: %s", filepath.name, exc, exc_info=True)
    finally:
        conn.close()

    return imported, skipped


def _write_batch(conn: sqlite3.Connection, batch: list) -> int:
    written = 0
    for row in batch:
        try:
            cur = conn.execute("""
                INSERT INTO pre_mover_leads
                    (address, city, state, county, zip_code, status,
                     list_price, bedrooms, bathrooms, sqft, is_vacant,
                     listed_date, source_id, import_file, latitude, longitude, scraped_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, COALESCE(?, datetime('now')))
                ON CONFLICT(address, zip_code) DO UPDATE SET
                    previous_status   = CASE
                        WHEN excluded.status != pre_mover_leads.status
                        THEN pre_mover_leads.status
                        ELSE pre_mover_leads.previous_status
                    END,
                    status_updated_at = CASE
                        WHEN excluded.status != pre_mover_leads.status
                        THEN datetime('now')
                        ELSE pre_mover_leads.status_updated_at
                    END,
                    status     = excluded.status,
                    list_price = COALESCE(excluded.list_price, pre_mover_leads.list_price),
                    is_vacant  = excluded.is_vacant,
                    import_file = excluded.import_file
            """, row)
            if cur.rowcount:
                written += 1
        except Exception as exc:
            log.warning("Row skip: %s", exc)
    return written


# ── Export helpers ───────────────────────────────────────────────

def export_by_county():
    """Export one CSV per county into data/exports/by_county/"""
    out_dir = EXPORT_DIR / "by_county"
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    conn.row_factory = sqlite3.Row

    counties = [r[0] for r in conn.execute(
        "SELECT DISTINCT county FROM pre_mover_leads "
        "WHERE county != '' ORDER BY county"
    ).fetchall()]

    if not counties:
        log.warning("No county data found. Check that CSVs include a 'county' column.")
        conn.close()
        return

    log.info("Exporting %d county files...", len(counties))
    for county in counties:
        rows = conn.execute("""
            SELECT address, city, state, county, zip_code, status,
                   list_price, bedrooms, bathrooms, sqft,
                   is_vacant, listed_date, source_id
            FROM pre_mover_leads
            WHERE county = ?
            ORDER BY zip_code, address
        """, (county,)).fetchall()

        safe_name = county.replace(" ", "_").replace("/", "-").replace("\\", "-")
        out_file  = out_dir / "{}_listings.csv".format(safe_name)
        with open(out_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Address", "City", "State", "County", "ZIP Code", "Status",
                "List Price", "Beds", "Baths", "Sqft",
                "Vacant", "Listed Date", "Source ID"
            ])
            writer.writerows(rows)
        log.info("  %s -> %d rows", out_file.name, len(rows))

    conn.close()
    log.info("County exports saved to: %s", out_dir)


def export_by_state():
    """Export one CSV per state."""
    out_dir = EXPORT_DIR / "by_state"
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    states = [r[0] for r in conn.execute(
        "SELECT DISTINCT state FROM pre_mover_leads WHERE state != '' ORDER BY state"
    ).fetchall()]

    for state in states:
        rows = conn.execute("""
            SELECT address, city, state, county, zip_code, status,
                   list_price, bedrooms, bathrooms, sqft,
                   is_vacant, listed_date, source_id
            FROM pre_mover_leads WHERE state = ?
            ORDER BY county, zip_code, address
        """, (state,)).fetchall()

        out_file = out_dir / "{}_listings.csv".format(state.replace(" ", "_"))
        with open(out_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Address", "City", "State", "County", "ZIP Code", "Status",
                "List Price", "Beds", "Baths", "Sqft",
                "Vacant", "Listed Date", "Source ID"
            ])
            writer.writerows(rows)
        log.info("  %s -> %d rows", out_file.name, len(rows))

    conn.close()
    log.info("State exports saved to: %s", out_dir)


def export_by_zip():
    """Export one CSV per ZIP code."""
    out_dir = EXPORT_DIR / "by_zip"
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    zips = [r[0] for r in conn.execute(
        "SELECT DISTINCT zip_code FROM pre_mover_leads WHERE zip_code != '' ORDER BY zip_code"
    ).fetchall()]

    for z in zips:
        rows = conn.execute("""
            SELECT address, city, state, county, zip_code, status,
                   list_price, bedrooms, bathrooms, sqft,
                   is_vacant, listed_date, source_id
            FROM pre_mover_leads WHERE zip_code = ?
            ORDER BY status, address
        """, (z,)).fetchall()

        out_file = out_dir / "ZIP_{}_listings.csv".format(z)
        with open(out_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Address", "City", "State", "County", "ZIP Code", "Status",
                "List Price", "Beds", "Baths", "Sqft",
                "Vacant", "Listed Date", "Source ID"
            ])
            writer.writerows(rows)

    log.info("%d ZIP exports saved to: %s", len(zips), out_dir)
    conn.close()


def print_summary():
    """Print a quick summary of what's in the database."""
    conn = get_connection()
    total    = conn.execute("SELECT COUNT(*) FROM pre_mover_leads").fetchone()[0]
    by_state = conn.execute(
        "SELECT state, COUNT(*) FROM pre_mover_leads GROUP BY state ORDER BY COUNT(*) DESC"
    ).fetchall()
    by_status = conn.execute(
        "SELECT status, COUNT(*) FROM pre_mover_leads GROUP BY status ORDER BY COUNT(*) DESC"
    ).fetchall()
    conn.close()

    print("\n" + "=" * 50)
    print("  DATABASE SUMMARY")
    print("=" * 50)
    print("  Total leads: {:,}".format(total))
    print("\n  By State:")
    for s, n in by_state:
        print("    {:10s}  {:,}".format(s or "Unknown", n))
    print("\n  By Status:")
    for s, n in by_status:
        print("    {:20s}  {:,}".format(s or "Unknown", n))
    print("=" * 50)


# ── Main ─────────────────────────────────────────────────────────

def find_csv_files(specific_file: str = None) -> list[pathlib.Path]:
    """Find CSV files to import."""
    if specific_file:
        p = pathlib.Path(specific_file)
        if p.exists():
            return [p]
        log.error("File not found: %s", specific_file)
        return []

    found = []
    for search_dir in [DOWNLOADS_DIR, PROJECT_DATA_DIR]:
        if search_dir.exists():
            csvs = sorted(search_dir.rglob("*.csv"))
            if csvs:
                log.info("Found %d CSV(s) in %s", len(csvs), search_dir)
                found.extend(csvs)

    if not found:
        log.warning("No CSV files found in:")
        log.warning("  %s", DOWNLOADS_DIR)
        log.warning("  %s", PROJECT_DATA_DIR)
        log.info("Tip: Copy your downloaded CSVs to either folder and re-run.")
    return found


def run(specific_file: str = None) -> int:
    """Import CSVs and return total records imported."""
    ensure_leads_table()
    PROJECT_DATA_DIR.mkdir(parents=True, exist_ok=True)

    files = find_csv_files(specific_file)
    if not files:
        return 0

    total_imported = 0
    total_skipped  = 0

    for f in files:
        log.info("Importing: %s  (%s)", f.name, _human_size(f.stat().st_size))
        imp, skip = import_csv(f)
        total_imported += imp
        total_skipped  += skip
        log.info("  -> %d imported, %d skipped", imp, skip)

    log.info("TOTAL: %d records imported, %d skipped", total_imported, total_skipped)
    print_summary()
    return total_imported


def _human_size(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return "{:.1f} {}".format(n, unit)
        n /= 1024
    return "{:.1f} TB".format(n)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="USA Home Listings CSV Importer")
    parser.add_argument("--file",         default=None,
                        help="Path to a specific CSV file to import")
    parser.add_argument("--export-by",    choices=["county", "state", "zip"],
                        help="After importing, export filtered CSVs by this dimension")
    parser.add_argument("--export-only",  action="store_true",
                        help="Skip import, only run the export")
    parser.add_argument("--summary",      action="store_true",
                        help="Just print database summary, no import/export")
    args = parser.parse_args()

    ensure_leads_table()

    if args.summary:
        print_summary()
        sys.exit(0)

    if not args.export_only:
        run(args.file)

    if args.export_by == "county":
        export_by_county()
    elif args.export_by == "state":
        export_by_state()
    elif args.export_by == "zip":
        export_by_zip()
