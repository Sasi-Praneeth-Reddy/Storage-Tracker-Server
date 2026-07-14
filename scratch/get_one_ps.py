import sqlite3
import pandas as pd
conn = sqlite3.connect('database/storage_tracker.db')
df = pd.read_sql("SELECT * FROM facilities WHERE brand = 'Public Storage' LIMIT 1", conn)
print(df.iloc[0].to_dict())
