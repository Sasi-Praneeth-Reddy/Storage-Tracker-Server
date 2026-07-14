import sqlite3
import pandas as pd
conn = sqlite3.connect('database/storage_tracker.db')
df = pd.read_sql("SELECT website FROM facilities WHERE brand = 'Extra Space Storage' AND website IS NOT NULL LIMIT 1", conn)
print(df.iloc[0]['website'])
