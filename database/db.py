import sqlite3

DB_PATH = "database/db.sqlite3"

# Seed data: (bin_id, location_name, latitude, longitude, capacity_litres, fill_rate)
# fill_rate = base fill % per 5-second cycle, calibrated by location footfall
SEED_BINS = [
    ("BIN-001", "Colombo Fort",   6.900, 79.850, 120, 7),  # High-traffic commercial hub
    ("BIN-002", "Pettah Market",  6.905, 79.860, 120, 9),  # Very high-traffic market area
    ("BIN-003", "Slave Island",   6.910, 79.870, 120, 5),  # Medium-traffic mixed zone
    ("BIN-004", "Bambalapitiya",  6.915, 79.880, 120, 6),  # Medium-high residential/commercial
    ("BIN-005", "Wellawatte",     6.920, 79.890, 120, 4),  # Lower-traffic residential area
]


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def create_tables():
    """
    Creates all three tables and safely applies schema migrations.
    Safe to call on every application startup — uses IF NOT EXISTS throughout.
    """
    conn = None
    try:
        conn = connect()
        cursor = conn.cursor()

        # --- Table 1: Static bin metadata ---
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS bin_master (
            bin_id          TEXT    PRIMARY KEY,
            location_name   TEXT    NOT NULL,
            latitude        REAL    NOT NULL,
            longitude       REAL    NOT NULL,
            capacity_litres INTEGER NOT NULL,
            fill_rate       INTEGER NOT NULL DEFAULT 5
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

        # --- Table 3: Collection event log (separate from telemetry readings) ---
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS collection_events (
            id                  INTEGER  PRIMARY KEY AUTOINCREMENT,
            bin_id              TEXT     NOT NULL,
            fill_at_collection  INTEGER  NOT NULL,
            collected_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (bin_id) REFERENCES bin_master(bin_id)
        )
        """)

        # --- Migration: add fill_rate column if upgrading from older schema ---
        cursor.execute("PRAGMA table_info(bin_master)")
        existing_cols = [row[1] for row in cursor.fetchall()]
        if "fill_rate" not in existing_cols:
            cursor.execute(
                "ALTER TABLE bin_master ADD COLUMN fill_rate INTEGER NOT NULL DEFAULT 5"
            )

        # --- Seed bin_master if empty ---
        cursor.execute("SELECT COUNT(*) FROM bin_master")
        if cursor.fetchone()[0] == 0:
            cursor.executemany("""
            INSERT INTO bin_master
                (bin_id, location_name, latitude, longitude, capacity_litres, fill_rate)
            VALUES (?, ?, ?, ?, ?, ?)
            """, SEED_BINS)
        else:
            # Update fill_rate for existing rows in case they predate this column
            for seed in SEED_BINS:
                cursor.execute(
                    "UPDATE bin_master SET fill_rate = ? WHERE bin_id = ?",
                    (seed[5], seed[0])
                )

        conn.commit()

    except sqlite3.Error as e:
        print(f"[DB ERROR] create_tables: {e}")
    finally:
        if conn:
            conn.close()


def insert_reading(bin_id, fill_level):
    """Insert a single sensor reading into the telemetry log."""
    conn = None
    try:
        conn = connect()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO telemetry (bin_id, fill_level) VALUES (?, ?)",
            (bin_id, fill_level)
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"[DB ERROR] insert_reading({bin_id}, {fill_level}): {e}")
    finally:
        if conn:
            conn.close()


def log_collection_event(bin_id, fill_level):
    """
    Record a bin collection event in collection_events.
    Called when the simulator empties a bin (fill >= 95%).
    Kept separate from the telemetry log for clean queryability.
    """
    conn = None
    try:
        conn = connect()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO collection_events (bin_id, fill_at_collection) VALUES (?, ?)",
            (bin_id, fill_level)
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"[DB ERROR] log_collection_event({bin_id}): {e}")
    finally:
        if conn:
            conn.close()


def get_bin_locations():
    """
    Returns {bin_id: (latitude, longitude)} from bin_master.
    Single source of truth — coordinates are never hardcoded elsewhere.
    """
    conn = None
    try:
        conn = connect()
        cursor = conn.cursor()
        cursor.execute("SELECT bin_id, latitude, longitude FROM bin_master")
        rows = cursor.fetchall()
        return {row[0]: (row[1], row[2]) for row in rows}
    except sqlite3.Error as e:
        print(f"[DB ERROR] get_bin_locations: {e}")
        return {}
    finally:
        if conn:
            conn.close()


def get_fill_rates():
    """
    Returns {bin_id: fill_rate} from bin_master.
    Used by the simulator to apply per-bin, location-aware fill increments.
    """
    conn = None
    try:
        conn = connect()
        cursor = conn.cursor()
        cursor.execute("SELECT bin_id, fill_rate FROM bin_master")
        rows = cursor.fetchall()
        return {row[0]: row[1] for row in rows}
    except sqlite3.Error as e:
        print(f"[DB ERROR] get_fill_rates: {e}")
        return {}
    finally:
        if conn:
            conn.close()


def get_bin_capacities():
    """
    Returns {bin_id: capacity_litres} from bin_master.
    Used to compute actual waste volumes: fill_level / 100 * capacity_litres.
    """
    conn = None
    try:
        conn = connect()
        cursor = conn.cursor()
        cursor.execute("SELECT bin_id, capacity_litres FROM bin_master")
        rows = cursor.fetchall()
        return {row[0]: row[1] for row in rows}
    except sqlite3.Error as e:
        print(f"[DB ERROR] get_bin_capacities: {e}")
        return {}
    finally:
        if conn:
            conn.close()


def prune_old_readings(keep_last_n=500):
    """Delete telemetry rows beyond the most recent keep_last_n, preventing unbounded growth."""
    conn = None
    try:
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
    except sqlite3.Error as e:
        print(f"[DB ERROR] prune_old_readings: {e}")
    finally:
        if conn:
            conn.close()