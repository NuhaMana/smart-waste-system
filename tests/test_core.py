"""
tests/test_core.py
==================
Unit tests for the Smart Waste Monitoring System.

Test classes and what they cover
─────────────────────────────────────────────────────────────
  TestHaversine               Haversine great-circle distance formula
  TestComputeVolume           Physical waste volume calculation (litres)
  TestNearestNeighbourRoute   Nearest-Neighbour TSP heuristic (depot + stops)
  TestSequentialRouteDistance Fixed sequential benchmark route (12.36 km)
  TestBuildLatestBins         Deduplication of most-recent reading per bin
  TestDatabaseOperations      DB schema creation, insert, log, and prune
                              (uses a temporary SQLite file — production
                               database is NEVER opened or modified)

Run from the project root directory:
    python -m unittest tests/test_core.py -v
"""

import os
import sys
import sqlite3
import tempfile
import unittest

# Ensure the project root is on the import path regardless of
# the working directory this file is invoked from.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─────────────────────────────────────────────────────────────
# TEST CLASS 1: HAVERSINE FORMULA
# ─────────────────────────────────────────────────────────────

class TestHaversine(unittest.TestCase):
    """
    Verify the Haversine great-circle distance formula implemented
    in app.py.  The Haversine formula is the standard method for
    computing shortest-path distances on a spherical Earth surface.
    """

    @classmethod
    def setUpClass(cls):
        from app import haversine
        cls.haversine = staticmethod(haversine)

    def test_known_distance_depot_to_bin001(self):
        """
        DEPOT (6.895, 79.840) to BIN-001 (6.900, 79.850).
        This is one leg of the verified 12.36 km sequential route.
        Expected result: approximately 1.236 km.
        """
        dist = self.haversine((6.895, 79.840), (6.900, 79.850))
        self.assertAlmostEqual(dist, 1.236, places=2)

    def test_zero_distance_same_point(self):
        """Distance from a coordinate to itself must be exactly zero."""
        dist = self.haversine((6.900, 79.850), (6.900, 79.850))
        self.assertAlmostEqual(dist, 0.0, places=5)

    def test_symmetry_a_to_b_equals_b_to_a(self):
        """
        The Haversine formula is symmetric.
        Distance A → B must equal Distance B → A.
        """
        a = (6.895, 79.840)
        b = (6.920, 79.890)
        self.assertAlmostEqual(
            self.haversine(a, b),
            self.haversine(b, a),
            places=10
        )

    def test_returns_positive_for_distinct_points(self):
        """Any two distinct geographic points must produce a positive distance."""
        dist = self.haversine((6.895, 79.840), (6.905, 79.860))
        self.assertGreater(dist, 0)


# ─────────────────────────────────────────────────────────────
# TEST CLASS 2: VOLUME CALCULATION
# ─────────────────────────────────────────────────────────────

class TestComputeVolume(unittest.TestCase):
    """
    Verify _compute_volume(), which calculates actual waste volume
    in litres using: volume = fill_level / 100 × capacity_litres.
    All seeded bins have capacity_litres = 120.
    """

    @classmethod
    def setUpClass(cls):
        from app import _compute_volume
        cls.compute_volume = staticmethod(_compute_volume)

    def test_empty_bin_produces_zero_litres(self):
        """A bin at 0% fill must contain 0.0 litres."""
        self.assertEqual(self.compute_volume("BIN-001", 0), 0.0)

    def test_full_bin_equals_capacity_in_litres(self):
        """A bin at 100% fill must equal its 120 L capacity."""
        self.assertEqual(self.compute_volume("BIN-001", 100), 120.0)

    def test_half_full_bin_is_sixty_litres(self):
        """A bin at 50% fill must contain 60.0 litres (50/100 × 120)."""
        self.assertEqual(self.compute_volume("BIN-001", 50), 60.0)

    def test_unknown_bin_id_falls_back_to_default_capacity(self):
        """
        An unrecognised bin_id must fall back to the 120 L default,
        not raise a KeyError or return an incorrect value.
        """
        vol = self.compute_volume("BIN-UNKNOWN", 50)
        self.assertEqual(vol, 60.0)   # 50 / 100 × 120 (default)


# ─────────────────────────────────────────────────────────────
# TEST CLASS 3: NEAREST-NEIGHBOUR ROUTE
# ─────────────────────────────────────────────────────────────

class TestNearestNeighbourRoute(unittest.TestCase):
    """
    Verify nearest_neighbour_route(), the Nearest-Neighbour TSP
    heuristic that builds the optimised collection route.
    The route must always start and end at the depot.
    """

    @classmethod
    def setUpClass(cls):
        from app import nearest_neighbour_route, DEPOT
        cls.nn_route = staticmethod(nearest_neighbour_route)
        cls.DEPOT    = DEPOT

    def test_empty_input_returns_empty_route_and_zero_distance(self):
        """
        When no bins are critical, the function must return an empty
        route and zero distance — not raise an exception.
        """
        route, dist = self.nn_route([])
        self.assertEqual(route, [])
        self.assertEqual(dist, 0.0)

    def test_single_location_produces_three_waypoints(self):
        """
        One critical bin → DEPOT → bin → DEPOT.
        The returned route must contain exactly 3 waypoints.
        """
        route, _ = self.nn_route([(6.900, 79.850)])
        self.assertEqual(len(route), 3)

    def test_route_always_starts_at_depot(self):
        """The first waypoint must always be the depot coordinate."""
        route, _ = self.nn_route([(6.900, 79.850), (6.910, 79.870)])
        self.assertEqual(route[0], list(self.DEPOT))

    def test_route_always_ends_at_depot(self):
        """The last waypoint must always be the depot (return leg)."""
        route, _ = self.nn_route([(6.900, 79.850), (6.910, 79.870)])
        self.assertEqual(route[-1], list(self.DEPOT))

    def test_all_supplied_locations_are_visited(self):
        """
        Every supplied critical-bin coordinate must appear in the route.
        3 bins + depot start + depot end = 5 waypoints.
        """
        locs  = [(6.900, 79.850), (6.905, 79.860), (6.910, 79.870)]
        route, _ = self.nn_route(locs)
        self.assertEqual(len(route), 5)

    def test_total_distance_is_positive(self):
        """A route visiting at least one bin must have a positive total distance."""
        _, dist = self.nn_route([(6.900, 79.850), (6.905, 79.860)])
        self.assertGreater(dist, 0)


# ─────────────────────────────────────────────────────────────
# TEST CLASS 4: SEQUENTIAL BASELINE ROUTE
# ─────────────────────────────────────────────────────────────

class TestSequentialRouteDistance(unittest.TestCase):
    """
    Verify sequential_route_distance(), the fixed benchmark that
    models a driver following a paper schedule with no DSS.
    Route: DEPOT → BIN-001 → BIN-002 → BIN-003 → BIN-004 → BIN-005 → DEPOT.
    Verified total: 12.36 km.
    """

    @classmethod
    def setUpClass(cls):
        from app import sequential_route_distance
        cls.seq_dist = staticmethod(sequential_route_distance)

    def test_returns_positive_distance(self):
        """The sequential route must cover a positive distance."""
        self.assertGreater(self.seq_dist(), 0)

    def test_is_deterministic(self):
        """
        Because bin locations are fixed, two calls must return
        an identical value — no randomness involved.
        """
        self.assertEqual(self.seq_dist(), self.seq_dist())

    def test_matches_verified_distance_of_12_36_km(self):
        """
        The sequential route has been independently verified at 12.36 km
        using the Haversine formula across all six legs.
        """
        self.assertAlmostEqual(self.seq_dist(), 12.36, places=1)


# ─────────────────────────────────────────────────────────────
# TEST CLASS 5: LATEST-BIN DEDUPLICATION
# ─────────────────────────────────────────────────────────────

class TestBuildLatestBins(unittest.TestCase):
    """
    Verify _build_latest_bins(), which filters raw telemetry rows
    (newest-first) to keep only the most recent reading per bin.
    This is critical: the analytics and dashboard must show current
    fill levels, not historical ones.
    """

    @classmethod
    def setUpClass(cls):
        from app import _build_latest_bins
        cls.build = staticmethod(_build_latest_bins)

    def test_keeps_most_recent_reading_per_bin(self):
        """
        When a bin has multiple readings, only the first occurrence
        (most recent, because data is ordered DESC by timestamp)
        must be retained.
        """
        data = [
            ("BIN-001", 85, "2026-08-24 12:00:10"),   # most recent
            ("BIN-002", 60, "2026-08-24 12:00:10"),
            ("BIN-001", 30, "2026-08-24 11:59:55"),   # older — must be dropped
        ]
        result = self.build(data)
        self.assertEqual(len(result), 2)
        self.assertEqual(result["BIN-001"][1], 85)

    def test_empty_input_returns_empty_dict(self):
        """An empty telemetry list must return an empty dict, not an exception."""
        self.assertEqual(self.build([]), {})


# ─────────────────────────────────────────────────────────────
# TEST CLASS 6: DATABASE OPERATIONS
# ─────────────────────────────────────────────────────────────

class TestDatabaseOperations(unittest.TestCase):
    """
    Tests for all core database functions in database/db.py.

    IMPORTANT: Each test uses a fresh TEMPORARY SQLite file created
    by Python's tempfile module.  The production database
    (database/db.sqlite3) is NEVER opened, read, or modified by
    any test in this class.
    """

    def setUp(self):
        # Create a temporary file to use as the isolated test database.
        tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(tmp_fd)

        # Redirect the db module's DB_PATH to the temp file before
        # any db function is called in this test.
        import database.db as db_module
        self._original_path = db_module.DB_PATH
        db_module.DB_PATH   = self.tmp_path

        # Initialise the schema + seed data in the isolated temp DB.
        from database.db import create_tables
        create_tables()

    def tearDown(self):
        # Always restore the original DB_PATH and delete the temp file.
        import database.db as db_module
        db_module.DB_PATH = self._original_path
        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)

    # ── Schema ──────────────────────────────────────────────

    def test_all_three_tables_are_created(self):
        """
        create_tables() must produce all three required tables:
        bin_master, telemetry, and collection_events.
        """
        conn   = sqlite3.connect(self.tmp_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        self.assertIn("bin_master",        tables)
        self.assertIn("telemetry",         tables)
        self.assertIn("collection_events", tables)

    def test_bin_master_is_seeded_with_five_bins(self):
        """create_tables() must seed exactly 5 bins into bin_master."""
        conn   = sqlite3.connect(self.tmp_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM bin_master")
        count  = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count, 5)

    # ── insert_reading ───────────────────────────────────────

    def test_insert_reading_persists_correct_fill_level(self):
        """
        insert_reading() must write the exact fill_level value
        to the telemetry table.
        """
        from database.db import insert_reading
        insert_reading("BIN-001", 75)
        conn   = sqlite3.connect(self.tmp_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT fill_level FROM telemetry WHERE bin_id='BIN-001'"
        )
        row = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 75)

    # ── log_collection_event ─────────────────────────────────

    def test_log_collection_event_records_correct_fill(self):
        """
        log_collection_event() must write the correct fill_at_collection
        value to the collection_events table.
        """
        from database.db import log_collection_event
        log_collection_event("BIN-002", 96)
        conn   = sqlite3.connect(self.tmp_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT fill_at_collection FROM collection_events "
            "WHERE bin_id='BIN-002'"
        )
        row = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 96)

    # ── prune_old_readings ───────────────────────────────────

    def test_prune_retains_exact_requested_row_count(self):
        """
        prune_old_readings(keep_last_n=10) must leave exactly 10 rows
        in the telemetry table when called after 20 inserts.
        """
        from database.db import insert_reading, prune_old_readings
        for i in range(20):
            insert_reading("BIN-001", i % 100)
        prune_old_readings(keep_last_n=10)
        conn   = sqlite3.connect(self.tmp_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM telemetry")
        count  = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count, 10)


# ─────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
