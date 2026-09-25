"""
database.py — SQLite connection helper for the Storage Tracker API.
DB path resolves to: <project_root>/database/storage_tracker.db
"""

import sqlite3
from pathlib import Path

# <project_root>/database/storage_tracker.db
DB_PATH: Path = Path(__file__).parent.parent / "database" / "storage_tracker.db"


def get_connection() -> sqlite3.Connection:
    """Return a sqlite3 connection with Row factory enabled."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn
