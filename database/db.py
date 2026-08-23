import sqlite3

DB_PATH = "database/db.sqlite3"

# Static seed data — pre-loaded into bin_master on first run
SEED_BINS = [
    ("BIN-001", "Colombo Fort",   6.900, 79.850, 120),
    ("BIN-002", "Pettah Market",  6.905, 79.860, 120),
    ("BIN-003", "Slave Island",   6.910, 79.870, 120),
    ("BIN-004", "Bambalapitiya",  6.915, 79.880, 120),
    ("BIN-005", "Wellawatte",     6.920, 79.890, 120),
]


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def create_tables():
    """
    Creates the two-table relational schema if it does not already exist,
    then seeds bin_master with the 5 fixed bin records.
    """
    conn = connect()
    cursor = conn.cursor()

    # --- Table 1: Static bin metadata ---
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bin_master (
        bin_id          TEXT    PRIMARY KEY,
        location_name   TEXT    NOT NULL,
        latitude        REAL    NOT NULL,
        longitude       REAL    NOT NULL,
        capacity_litres INTEGER NOT NULL
    )
    """)

    # --- Table 2: Telemetry log (one row per sensor reading) ---
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS telemetry (
        id          INTEGER  PRIMARY KEY AUTOINCREMENT,
        bin_id      TEXT     NOT NULL,
        fill_level  INTEGER  NOT NULL,
        timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (bin_id) REFERENCES bin_master(bin_id)
    )
    """)

    # Seed bin_master only if it is empty
    cursor.execute("SELECT COUNT(*) FROM bin_master")
    if cursor.fetchone()[0] == 0:
        cursor.executemany("""
        INSERT INTO bin_master (bin_id, location_name, latitude, longitude, capacity_litres)
        VALUES (?, ?, ?, ?, ?)
        """, SEED_BINS)

    conn.commit()
    conn.close()


def insert_reading(bin_id, fill_level):
    """Insert a single sensor reading into the telemetry log."""
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO telemetry (bin_id, fill_level)
    VALUES (?, ?)
    """, (bin_id, fill_level))
    conn.commit()
    conn.close()


def get_bin_locations():
    """
    Returns a dict of {bin_id: (latitude, longitude)} sourced from bin_master.
    This is the single source of truth for coordinates — no hardcoding elsewhere.
    """
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT bin_id, latitude, longitude FROM bin_master")
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: (row[1], row[2]) for row in rows}


def prune_old_readings(keep_last_n=500):
    """
    Delete telemetry rows older than the most recent `keep_last_n` readings.
    Prevents unbounded table growth during long simulation runs.
    """
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
    DELETE FROM telemetry
    WHERE id NOT IN (
        SELECT id FROM telemetry
        ORDER BY timestamp DESC
        LIMIT ?
    )
    """, (keep_last_n,))
    conn.commit()
    conn.close()