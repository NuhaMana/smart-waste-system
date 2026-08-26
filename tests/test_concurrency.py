"""
tests/test_concurrency.py
=========================
Concurrency tests for the Smart Waste Monitoring System.

These tests verify that SQLite's WAL (Write-Ahead Logging) mode —
configured in database/db.py via PRAGMA journal_mode=WAL — correctly
handles simultaneous read and write operations without data loss,
lock errors, or corruption.

This mirrors the real production pattern used by this system:
  - The simulator writes one telemetry row per bin every 5 seconds.
  - Flask simultaneously serves read requests from the dashboard.

All tests use a temporary SQLite file created fresh per test.
The production database (database/db.sqlite3) is NEVER opened or
modified by any test in this file.

Run from the project root directory:
    python -m unittest tests/test_concurrency.py -v
"""

import os
import sys
import sqlite3
import tempfile
import threading
import time
import unittest

# Ensure the project root is on the import path regardless of
# the working directory this file is invoked from.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSQLiteWALConcurrency(unittest.TestCase):
    """
    Validates that the SQLite WAL mode configured in db.py correctly
    manages concurrent reads and writes without lock errors or data loss.

    The three tests model three distinct concurrency scenarios that occur
    naturally during system operation.
    """

    def setUp(self):
        """
        Before each test: create a fresh isolated temporary SQLite file
        and redirect the database module to use it instead of the real DB.
        """
        tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(tmp_fd)

        import database.db as db_module
        self._original_path = db_module.DB_PATH
        db_module.DB_PATH   = self.tmp_path

        # Initialise schema + seed data in the isolated temp DB
        from database.db import create_tables
        create_tables()

    def tearDown(self):
        """
        After each test: restore the original DB_PATH and delete the
        temporary file. Runs unconditionally even if the test fails.
        """
        import database.db as db_module
        db_module.DB_PATH = self._original_path
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)

    # ------------------------------------------------------------------ #
    # TEST 1: Concurrent writes — no silent data loss
    # ------------------------------------------------------------------ #

    def test_concurrent_writes_do_not_lose_data(self):
        """
        Three writer threads insert telemetry rows simultaneously.
        After all threads complete, the total row count must equal
        the exact number of intended writes — no row must be silently
        dropped due to a lock collision.

        Verifies: SQLite timeout/retry correctly queues concurrent writers.
        """
        from database.db import insert_reading

        NUM_THREADS      = 3
        WRITES_PER_THREAD = 10
        errors           = []

        def writer(bin_id, fill_start):
            for i in range(WRITES_PER_THREAD):
                try:
                    insert_reading(bin_id, fill_start + i)
                except Exception as e:
                    errors.append(f"{bin_id}: {e}")

        threads = [
            threading.Thread(target=writer, args=(f"BIN-00{i + 1}", i * 10))
            for i in range(NUM_THREADS)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()   # wait for every thread to finish before asserting

        # No exceptions must have been raised during any write
        self.assertEqual(
            errors, [],
            f"Exceptions during concurrent writes: {errors}"
        )

        # Every intended row must exist in the database
        conn   = sqlite3.connect(self.tmp_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM telemetry")
        actual_count = cursor.fetchone()[0]
        conn.close()

        expected_count = NUM_THREADS * WRITES_PER_THREAD
        self.assertEqual(
            actual_count, expected_count,
            f"Expected {expected_count} rows but found {actual_count} "
            f"— data was silently dropped under concurrent load."
        )

    # ------------------------------------------------------------------ #
    # TEST 2: Simultaneous reads and writes (the real production pattern)
    # ------------------------------------------------------------------ #

    def test_concurrent_reads_while_writing(self):
        """
        Simulates the exact real-world operation of this system:
          - 1 writer thread inserts telemetry rows (simulator behaviour)
          - 3 reader threads query the telemetry table (Flask dashboard)

        Both must complete without any SQLite 'database is locked' error.
        This is the definitive validation that WAL mode is functioning as
        configured: readers must never block writers, and writers must
        never block readers.
        """
        from database.db import insert_reading

        errors      = []
        NUM_READERS = 3
        NUM_WRITES  = 15

        def writer():
            for i in range(NUM_WRITES):
                try:
                    insert_reading("BIN-001", i % 100)
                    time.sleep(0.01)   # scaled-down version of the 5-second interval
                except Exception as e:
                    errors.append(f"WRITER: {e}")

        def reader(reader_id):
            for _ in range(10):
                try:
                    conn = sqlite3.connect(self.tmp_path, timeout=5)
                    conn.execute("PRAGMA journal_mode=WAL;")
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT bin_id, fill_level, timestamp "
                        "FROM telemetry ORDER BY timestamp DESC LIMIT 50"
                    )
                    cursor.fetchall()
                    conn.close()
                    time.sleep(0.01)
                except Exception as e:
                    errors.append(f"READER-{reader_id}: {e}")

        # Launch 1 writer + 3 readers simultaneously
        threads  = [threading.Thread(target=writer)]
        threads += [
            threading.Thread(target=reader, args=(i,))
            for i in range(NUM_READERS)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(
            errors, [],
            f"WAL concurrency failure — lock errors detected: {errors}"
        )

    # ------------------------------------------------------------------ #
    # TEST 3: Simultaneous collection events — no event lost
    # ------------------------------------------------------------------ #

    def test_concurrent_collection_events_are_all_logged(self):
        """
        All 5 bins reaching the 95% threshold and triggering a collection
        event at the exact same moment must all be successfully logged.
        No event must be silently dropped.

        This models a scenario where multiple bins fill simultaneously
        and the simulator's collection logic fires for all of them in
        the same cycle.
        """
        from database.db import log_collection_event

        BINS   = ["BIN-001", "BIN-002", "BIN-003", "BIN-004", "BIN-005"]
        errors = []

        def log_event(bin_id):
            try:
                log_collection_event(bin_id, 95)
            except Exception as e:
                errors.append(f"{bin_id}: {e}")

        # All 5 bins fire collection events simultaneously
        threads = [threading.Thread(target=log_event, args=(b,)) for b in BINS]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(
            errors, [],
            f"Exceptions during concurrent collection logging: {errors}"
        )

        conn   = sqlite3.connect(self.tmp_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM collection_events")
        count  = cursor.fetchone()[0]
        conn.close()

        self.assertEqual(
            count, len(BINS),
            f"Expected {len(BINS)} collection events but found {count} "
            f"— events were lost under concurrent load."
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
