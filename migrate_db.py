import sqlite3
import pathlib

# Assumes script is in project root
DB_PATH = pathlib.Path(__file__).parent / "database" / "storage_tracker.db"

NEW_COLUMNS = [
    ("first_name", "TEXT"),
    ("last_name", "TEXT"),
    ("county", "TEXT"),
    ("owner_full_name", "TEXT"),
    ("email", "TEXT"),
    ("email_2", "TEXT"),
    ("phone", "TEXT"),
    ("phone_type", "TEXT"),
    ("phone_2", "TEXT"),
    ("phone_2_type", "TEXT"),
    ("realtor_name", "TEXT"),
    ("realtor_email", "TEXT"),
    ("realtor_phone", "TEXT"),
    ("realtor_phone_2", "TEXT"),
    ("realtor_phone_3", "TEXT"),
    ("realtor_address", "TEXT"),
    ("broker_name", "TEXT"),
    ("broker_email", "TEXT"),
    ("broker_phone", "TEXT"),
    ("broker_phone_2", "TEXT"),
    ("broker_phone_3", "TEXT"),
    ("broker_address", "TEXT"),
    ("longitude", "REAL"),
    ("latitude", "REAL"),
]

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for col, ctype in NEW_COLUMNS:
        try:
            cursor.execute(f"ALTER TABLE pre_mover_leads ADD COLUMN {col} {ctype}")
            print(f"Added column: {col}")
        except sqlite3.OperationalError as e:
            # Column likely already exists
            print(f"Skipping {col}: {e}")
            
    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
