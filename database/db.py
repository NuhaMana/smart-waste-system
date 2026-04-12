import sqlite3

DB_PATH = "database/db.sqlite3"

def connect():
    return sqlite3.connect(DB_PATH)


def create_table():
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bin_id TEXT,
        fill_level INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()


def insert_bin_data(bin_id, fill_level):
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO bins (bin_id, fill_level)
    VALUES (?, ?)
    """, (bin_id, fill_level))

    conn.commit()
    conn.close()