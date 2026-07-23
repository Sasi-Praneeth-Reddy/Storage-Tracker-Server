"""
config.py — Central configuration for the Self-Storage Market Tracker

All ZIP codes for Northern Virginia, Washington DC, and
neighboring Maryland (Montgomery County + Prince George's County).
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ================================================================
# API KEYS (loaded from .env)
# ================================================================
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
RENTCAST_API_KEY    = os.getenv("RENTCAST_API_KEY", "")
BREVO_API_KEY       = os.getenv("BREVO_API_KEY", "")

# USA Home Listings portal credentials
USAHOMELISTINGS_EMAIL    = os.getenv("USAHOMELISTINGS_EMAIL", "")
USAHOMELISTINGS_PASSWORD = os.getenv("USAHOMELISTINGS_PASSWORD", "")

# ================================================================
# EMAIL SETTINGS
# ================================================================
EMAIL_FROM_ADDRESS = os.getenv("EMAIL_FROM_ADDRESS", "storage.tracker@aroundtownmovers.com")
EMAIL_FROM_NAME    = os.getenv("EMAIL_FROM_NAME", "Around Town Movers — Storage Tracker")
EMAIL_TO_ADDRESSES = [
    addr.strip()
    for addr in os.getenv("EMAIL_TO_ADDRESSES", "whitehat.sspr@gmail.com").split(",")
    if addr.strip()
]
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:8501")

# ================================================================
# DATABASE
# ================================================================
import pathlib
BASE_DIR = pathlib.Path(__file__).parent
DB_PATH  = BASE_DIR / "database" / "storage_tracker.db"

# ================================================================
# SCRAPING SETTINGS
# ================================================================
SCRAPE_DELAY_SECONDS   = 2      # Polite delay between requests
REQUEST_TIMEOUT        = 30     # Seconds before a request times out
MAX_RETRIES            = 3      # Retries on network errors
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# ================================================================
# TARGET ZIP CODES — Northern Virginia, DC, and Neighboring MD
# ================================================================

NOVA_ZIP_CODES = {
    # ---------- Alexandria City ----------
    "Alexandria": [
        "22301", "22302", "22303", "22304", "22305",
        "22306", "22307", "22308", "22309", "22310",
        "22311", "22312", "22314", "22315",
    ],
    # ---------- Arlington County ----------
    "Arlington": [
        "22201", "22202", "22203", "22204", "22205",
        "22206", "22207", "22209", "22213",
    ],
    # ---------- Fairfax City & County ----------
    "Fairfax": [
        "22030", "22031", "22032", "22033", "22034",
        "22035", "22036", "22037", "22038", "22039",
    ],
    # ---------- Falls Church ----------
    "Falls Church": [
        "22041", "22042", "22043", "22044", "22046",
    ],
    # ---------- Annandale / Burke / Springfield ----------
    "Annandale-Burke-Springfield": [
        "22003", "22015", "22150", "22151", "22152", "22153",
    ],
    # ---------- McLean / Vienna / Great Falls ----------
    "McLean-Vienna-Great Falls": [
        "22066", "22101", "22102", "22180", "22181", "22182",
    ],
    # ---------- Reston / Herndon ----------
    "Reston-Herndon": [
        "20170", "20171", "20190", "20191", "20194",
    ],
    # ---------- Sterling / Ashburn (Loudoun) ----------
    "Sterling-Ashburn": [
        "20147", "20148", "20164", "20165", "20166",
    ],
    # ---------- Leesburg / Loudoun County ----------
    "Leesburg-Loudoun": [
        "20132", "20141", "20152", "20158", "20175", "20176",
    ],
    # ---------- Chantilly / Centreville / Manassas ----------
    "Chantilly-Centreville-Manassas": [
        "20109", "20110", "20111", "20112", "20120",
        "20121", "20151", "20152", "20155", "20169",
    ],
    # ---------- Gainesville / Haymarket / Prince William ----------
    "Prince William": [
        "22025", "22026", "22125", "22191", "22192",
        "22193", "22195",
    ],
}

DC_ZIP_CODES = {
    # ---------- Washington DC (residential ZIPs) ----------
    "Washington DC": [
        "20001", "20002", "20003", "20004", "20005",
        "20006", "20007", "20008", "20009", "20010",
        "20011", "20012", "20015", "20016", "20017",
        "20018", "20019", "20020", "20024", "20032",
    ],
}

MARYLAND_ZIP_CODES = {
    # ---------- Montgomery County MD ----------
    "Montgomery County MD": [
        "20814", "20815", "20816", "20817",  # Bethesda
        "20852", "20853", "20854", "20855",  # Rockville / Potomac
        "20877", "20878", "20879", "20882", "20886",  # Gaithersburg
        "20895", "20896",                    # Kensington
        "20901", "20902", "20903", "20904",  # Silver Spring
        "20905", "20906", "20907",           # Silver Spring (outer)
        "20910", "20912",                    # Silver Spring / Takoma Park
    ],
    # ---------- Prince George's County MD ----------
    "Prince George's County MD": [
        "20705", "20706", "20707", "20708",  # Laurel / Beltsville
        "20710", "20712",                    # Bladensburg / Mount Rainier
        "20720", "20721",                    # Upper Marlboro / Bowie
        "20722",                             # Brentwood
        "20743", "20744", "20745",           # Capitol Heights / Fort Washington
        "20746", "20747", "20748",           # Suitland / Lanham
        "20770", "20772",                    # Greenbelt / Upper Marlboro
        "20774",                             # Upper Marlboro
        "20781", "20782", "20783",           # Hyattsville / Chillum
        "20784", "20785",                    # Landover
    ],
}

# Flat lists for convenience
ALL_ZIP_CODES = (
    [z for zips in NOVA_ZIP_CODES.values()   for z in zips]
    + [z for zips in DC_ZIP_CODES.values()   for z in zips]
    + [z for zips in MARYLAND_ZIP_CODES.values() for z in zips]
)
ALL_ZIP_CODES = sorted(set(ALL_ZIP_CODES))  # deduplicate

# Storage specific ZIP codes (Northern Virginia only)
STORAGE_ZIP_CODES = sorted(set([z for zips in NOVA_ZIP_CODES.values() for z in zips]))

# Geographic center for map initialization (Tysons Corner area)
MAP_CENTER_LAT = 38.9072
MAP_CENTER_LON = -77.0369
MAP_DEFAULT_ZOOM = 10

# Storage brands to specifically target
TARGET_BRANDS = [
    "Public Storage",
    "Extra Space Storage",
    "CubeSmart",
    "Life Storage",
    "U-Haul",
    "StorQuest",
    "Simply Self Storage",
    "National Storage Centers",
    "Storage Post",
    "Stor-All",
]

# Unit sizes to track (width x depth in feet)
UNIT_SIZES = [
    "5x5", "5x10", "10x10", "10x15", "10x20", "10x25", "10x30"
]

if __name__ == "__main__":
    print(f"✅ Config loaded.")
    print(f"   Total ZIP codes: {len(ALL_ZIP_CODES)}")
    print(f"   NoVA ZIPs:       {sum(len(v) for v in NOVA_ZIP_CODES.values())}")
    print(f"   DC ZIPs:         {sum(len(v) for v in DC_ZIP_CODES.values())}")
    print(f"   Maryland ZIPs:   {sum(len(v) for v in MARYLAND_ZIP_CODES.values())}")
    print(f"   Email → {EMAIL_TO_ADDRESSES}")
    print(f"   DB path: {DB_PATH}")
