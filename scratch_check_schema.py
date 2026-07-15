import sqlite3
c = sqlite3.connect('database/storage_tracker.db')
print(c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='pre_mover_leads'").fetchone()[0])
