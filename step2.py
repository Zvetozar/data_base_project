import os
import psycopg
from dotenv import load_dotenv

load_dotenv()
conn_str = os.environ["DATABASE_URL"]

DDL = """
DROP TABLE IF EXISTS transactions, accounts, customers;

CREATE TABLE customers (
    customer_id SERIAL PRIMARY KEY,
    full_name   TEXT NOT NULL,
    city        TEXT DEFAULT 'Almaty',
    email       TEXT UNIQUE
);

CREATE TABLE accounts (
    account_id     SERIAL PRIMARY KEY,
    account_number TEXT NOT NULL UNIQUE,
    customer_id    INTEGER NOT NULL REFERENCES customers(customer_id),
    balance        NUMERIC(15,2) NOT NULL DEFAULT 0 CHECK (balance >= 0)
);
CREATE TABLE transactions (
    tx_id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(account_id),
    amount NUMERIC(15, 2) NOT NULL CHECK (amount > 0),
    tx_type TEXT NOT NULL 
);
"""
CUSTOMERS = [
    ("Arman Bekov",      "Almaty",   "arman@mail.kz"),
    ("Zarina Seiit",     "Astana",   "zarina@mail.kz"),
    ("Daniyar Nurlan",   "Shymkent", "daniyar@mail.kz"),
    ("Ernazar Tolegenov", "Semey", "ernazar1609@gmail.com"),
    ("Bekbol Talgat", "Bishkek", "buu09@gmail.com"),
    ("Maksat Askar", "Astana", "maks1002@mail.kz"),
    ("Shalkar Tolegenov", "Uskemen", "shalkar7703@mail.ru"),
    ("Dana Omarova",      "Astana",    "dana@mail.kz"),
    ("Yerlan Kassymov",   "Atyrau",    "yerlan@mail.kz"),
    ("Aruzhan Mukanova",  "Almaty",    "aruzhan@mail.kz"),
]
ACCOUNTS = [
    ("KZ001", 1, 500000),
    ("KZ002", 1, 2000),
    ("KZ003", 2, 750000),
    ("KZ004", 3, 120000),
    ("KZ005", 3, 900),
    ("KZ006", 4, 1000000),
    ("KZ007", 5, 50000),
    ("KZ008", 6, 300000),
    ("KZ009", 6, 1500),
    ("KZ010", 7, 80000),
    ("KZ011", 8, 420000),
    ("KZ012", 9, 15000),
    ("KZ013", 10, 640000),
    ("KZ014", 10, 300),
    ("KZ015", 2, 0),
]
with psycopg.connect(conn_str) as conn:
    conn.execute(DDL)
    conn.cursor().executemany(
        "INSERT INTO customers (full_name, city, email) VALUES (%s, %s, %s)",
        CUSTOMERS
    )
    conn.cursor().executemany(
        "INSERT INTO accounts (account_number, customer_id, balance) VALUES (%s,%s,%s)",
        ACCOUNTS
    )
    conn.commit()
    print("Table created and filled")
    try:
        conn.execute(
            "INSERT INTO accounts (account_number, customer_id, balance) VALUES (%s, %s, %s)",
            ("KZ001", 1, 100)
        )
        conn.commit()
        print("BAD: duplicate was inserted")
    except psycopg.errors.UniqueViolation as e:
        conn.rollback()
        print("UNIQUE works, duplicate rejected:", e)