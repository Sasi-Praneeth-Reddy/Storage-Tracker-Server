"""
routers/database.py — Raw database table access endpoints.
"""

from typing import List, Optional

from fastapi import APIRouter, Query

from api.database import get_connection

router = APIRouter(prefix="/api/database", tags=["database"])


def _rows_to_dicts(rows) -> List[dict]:
    return [dict(r) for r in rows]


@router.get("/pre-mover-leads")
def get_pre_mover_leads(
    search: Optional[str] = Query(None, description="Search across all string columns"),
):
    """
    Return up to 5000 rows from pre_mover_leads.
    If `search` is provided, filters any row where ANY text column contains the term
    (case-insensitive).
    """
    with get_connection() as conn:
        # Discover column names so we can build a dynamic LIKE filter
        cursor = conn.execute("SELECT * FROM pre_mover_leads LIMIT 0")
        col_names = [d[0] for d in cursor.description] if cursor.description else []

        if search and col_names:
            # Build: col1 LIKE ? OR col2 LIKE ? ...  (only for TEXT-ish columns)
            # SQLite is loosely typed, so we apply LIKE to all columns; non-text
            # columns cast implicitly and matches are extremely unlikely.
            like_term = f"%{search}%"
            conditions = " OR ".join([f"CAST({col} AS TEXT) LIKE ?" for col in col_names])
            sql = f"SELECT * FROM pre_mover_leads WHERE {conditions} LIMIT 5000"
            params = [like_term] * len(col_names)
            rows = conn.execute(sql, params).fetchall()
        else:
            rows = conn.execute("SELECT * FROM pre_mover_leads LIMIT 5000").fetchall()

    return _rows_to_dicts(rows)
