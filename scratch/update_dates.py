import sqlite3, re

conn = sqlite3.connect('database/storage_tracker.db')
rows = conn.execute('SELECT id, import_file FROM pre_mover_leads WHERE import_file IS NOT NULL').fetchall()
updates = []
count = 0
regex = re.compile(r'_to_(\d{4}-\d{2}-\d{2})\.csv')

for r in rows:
    m = regex.search(r[1])
    if m:
        date_str = m.group(1)
        updates.append((date_str + ' 12:00:00', r[0]))
    
    if len(updates) >= 1000:
        conn.executemany('UPDATE pre_mover_leads SET scraped_at=? WHERE id=?', updates)
        count += len(updates)
        updates = []

if updates:
    conn.executemany('UPDATE pre_mover_leads SET scraped_at=? WHERE id=?', updates)
    count += len(updates)

conn.commit()
conn.close()
print(f'Successfully updated {count} rows with historical dates based on chunks.')
