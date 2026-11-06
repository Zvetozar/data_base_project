import os
import psycopg
from dotenv import load_dotenv

load_dotenv()
conn_str = os.environ["DATABASE_URL"]

with psycopg.connect(conn_str) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT version()")
        row = cur.fetchone()
        print(row[0])

    print("autocommit =", conn.autocommit)