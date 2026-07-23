import sqlite3
import pgeocode
import pathlib

DB_PATH = pathlib.Path(__file__).parent / "database" / "storage_tracker.db"

def fix_map_coordinates():
    print(f"Connecting to database at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Find all facilities that are stuck at 0.0, 0.0
    cur.execute("SELECT id, zip_code, name FROM facilities WHERE lat = 0.0 OR lon = 0.0")
    rows = cur.fetchall()
    
    if not rows:
        print("All facilities already have map coordinates! Nothing to fix.")
        return

    print(f"Found {len(rows)} facilities missing coordinates. Looking up zip codes...")
    nomi = pgeocode.Nominatim('us')
    
    updated_count = 0
    for row in rows:
        fac_id, zip_code, name = row[0], row[1], row[2]
        zip_data = nomi.query_postal_code(zip_code)
        
        if str(zip_data.latitude) != 'nan':
            lat = float(zip_data.latitude)
            lon = float(zip_data.longitude)
            conn.execute("UPDATE facilities SET lat=?, lon=? WHERE id=?", (lat, lon, fac_id))
            updated_count += 1
            print(f" Fixed {name} (Zip: {zip_code}) -> {lat}, {lon}")
        else:
            print(f" Warning: Could not find coordinates for Zip {zip_code} ({name})")
            
    conn.commit()
    conn.close()
    print(f"\nDone! Successfully updated map coordinates for {updated_count} facilities.")

if __name__ == '__main__':
    fix_map_coordinates()
