"""verify_setup.py - Phase 1 setup verification for Self-Storage Tracker."""

import sys
import pathlib

# Fix: avoid any \S or \p invalid escape sequences in docstrings
# Run with: venv\\Scripts\\python verify_setup.py


def check(label, passed, detail=""):
    icon = "[PASS]" if passed else "[FAIL]"
    msg = "  {}  {}".format(icon, label)
    if detail:
        msg += "  ->  {}".format(detail)
    print(msg)
    sys.stdout.flush()
    return passed


def main():
    print()
    print("=" * 55)
    print("  Self-Storage Tracker -- Phase 1 Verification")
    print("=" * 55)
    sys.stdout.flush()
    all_pass = True

    # 1. Python Version
    print("\n[1] Python Version")
    major, minor = sys.version_info.major, sys.version_info.minor
    ok = major >= 3 and minor >= 10
    all_pass &= check("Python {}.{}".format(major, minor), ok,
                      "(need 3.10+)" if not ok else "")

    # 2. Required Packages
    print("\n[2] Required Packages")
    packages = [
        ("streamlit",    "streamlit"),
        ("plotly",       "plotly"),
        ("pandas",       "pandas"),
        ("folium",       "folium"),
        ("requests",     "requests"),
        ("bs4",          "beautifulsoup4"),
        ("lxml",         "lxml"),
        ("playwright",   "playwright"),
        ("dotenv",       "python-dotenv"),
        ("apscheduler",  "apscheduler"),
        ("jinja2",       "Jinja2"),
        ("brevo",        "brevo-python"),
    ]
    for module, pkg_name in packages:
        try:
            __import__(module)
            all_pass &= check(pkg_name, True)
        except ImportError:
            all_pass &= check(pkg_name, False, "pip install --prefer-binary -r requirements.txt")

    # 3. Database
    print("\n[3] Database")
    try:
        sys.path.insert(0, str(pathlib.Path(__file__).parent))
        from database.db_setup import DB_PATH, get_connection, create_tables
        conn = get_connection()
        create_tables(conn)
        expected = {"facilities", "pricing_snapshots", "promotions",
                    "mls_market_data", "email_log", "scrape_log"}
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        actual = {r[0] for r in cur.fetchall()}
        conn.close()
        all_pass &= check("DB file created", DB_PATH.exists(), str(DB_PATH))
        for t in sorted(expected):
            all_pass &= check("Table: {}".format(t), t in actual)
    except Exception as exc:
        all_pass &= check("Database", False, str(exc))

    # 4. .env file
    print("\n[4] Environment (.env)")
    env_path = pathlib.Path(".env")
    env_exists = env_path.exists()
    all_pass &= check(".env file present", env_exists,
                      "Copy .env.example to .env and fill in API keys" if not env_exists else "")
    if env_exists:
        from dotenv import dotenv_values
        vals = dotenv_values(".env")
        for key in ["GOOGLE_MAPS_API_KEY", "RENTCAST_API_KEY",
                    "BREVO_API_KEY", "EMAIL_TO_ADDRESSES"]:
            val = vals.get(key, "")
            filled = bool(val) and "your_" not in val
            all_pass &= check(".env: {}".format(key), filled,
                              "Not yet filled in" if not filled else "")
    else:
        print("  [SKIP] .env checks skipped (file not found)")

    # 5. Config
    print("\n[5] Configuration")
    try:
        from config import ALL_ZIP_CODES, EMAIL_TO_ADDRESSES
        all_pass &= check("config.py imports OK", True)
        all_pass &= check("ZIP codes loaded ({} total)".format(len(ALL_ZIP_CODES)),
                          len(ALL_ZIP_CODES) > 100)
        all_pass &= check("Email recipients: {}".format(", ".join(EMAIL_TO_ADDRESSES)),
                          len(EMAIL_TO_ADDRESSES) > 0)
    except Exception as exc:
        all_pass &= check("config.py", False, str(exc))

    # Summary
    print()
    print("=" * 55)
    if all_pass:
        print("  ALL CHECKS PASSED -- Phase 1 complete!")
        print("  Ready for Phase 2: Data Collectors (Jun 26-27)")
    else:
        print("  Some checks FAILED -- fix [FAIL] items above,")
        print("  then re-run this script.")
    print("=" * 55)
    print()
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
