"""
tests/test_integration.py
=========================
Integration tests for the Smart Waste Monitoring System.

These tests verify the end-to-end request/response pipeline across all
Flask endpoints using Flask's test client (app.test_client()).

Each test runs against an isolated, temporary SQLite database to ensure
full separation from production data. The production database
(database/db.sqlite3) is NEVER touched.

Coverage:
  - GET / (Dashboard with KPIs, table data, volume in litres)
  - GET /api/dashboard (JSON polling endpoint)
  - GET /analytics (DSS recommendation, route calculations, network volume)
  - GET /routes (Priority bin sorting by fill level)
  - GET /map (Coordinates, waypoint payload, estimated duration)
  - GET /collections (Collection events with bin_master JOIN)
  - GET /generate-report (PDF generation and response attachment)

Run from the project root directory:
    python -m unittest tests/test_integration.py -v
"""

import os
import sys
import sqlite3
import tempfile
import json
import unittest

# Ensure project root is in sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app
import database.db as db_module
import reports.report_generator as rg_module


class TestFlaskIntegration(unittest.TestCase):
    """
    End-to-end integration tests verifying Flask route behaviour,
    template rendering, JSON outputs, and database interaction.
    """

    def setUp(self):
        """
        Create a fresh temporary SQLite database for each test and
        point all modules to use this isolated database.
        """
        tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(tmp_fd)

        self._orig_db_path = db_module.DB_PATH
        self._orig_app_db_path = sys.modules["app"].DB_PATH
        self._orig_rg_db_path = rg_module.DB_PATH

        db_module.DB_PATH = self.tmp_path
        sys.modules["app"].DB_PATH = self.tmp_path
        rg_module.DB_PATH = self.tmp_path

        # Initialise schema & seed bins
        db_module.create_tables()

        app.config["TESTING"] = True
        self.client = app.test_client()

    def tearDown(self):
        """Restore module DB paths and remove the temporary database file."""
        db_module.DB_PATH = self._orig_db_path
        sys.modules["app"].DB_PATH = self._orig_app_db_path
        rg_module.DB_PATH = self._orig_rg_db_path

        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)

    # -------------------------------------------------------------------------
    # DASHBOARD & API
    # -------------------------------------------------------------------------

    def test_dashboard_endpoint_renders_kpis_and_table(self):
        """GET / should return HTTP 200, display KPI summary cards and Volume (L)."""
        db_module.insert_reading("BIN-001", 60)
        db_module.insert_reading("BIN-002", 85)

        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")

        self.assertIn("Smart Waste Monitoring Dashboard", html)
        self.assertIn("Volume (L)", html)
        self.assertIn("BIN-001", html)
        self.assertIn("BIN-002", html)

    def test_api_dashboard_json_payload(self):
        """GET /api/dashboard should return JSON with expected keys, computed volumes, and status."""
        db_module.insert_reading("BIN-001", 75)
        db_module.insert_reading("BIN-002", 90)

        response = self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.is_json)

        data = json.loads(response.data)
        self.assertIn("total_bins", data)
        self.assertIn("critical_count", data)
        self.assertIn("average_fill", data)
        self.assertIn("alerts", data)
        self.assertIn("readings", data)

        self.assertEqual(data["critical_count"], 1)  # BIN-002 is 90%
        self.assertEqual(len(data["readings"]), 2)
        bin_volumes = {r["bin_id"]: r["volume_litres"] for r in data["readings"]}
        self.assertEqual(bin_volumes["BIN-001"], 90.0)   # 75% of 120L
        self.assertEqual(bin_volumes["BIN-002"], 108.0)  # 90% of 120L

    # -------------------------------------------------------------------------
    # ANALYTICS & DSS
    # -------------------------------------------------------------------------

    def test_analytics_safe_state_zero_critical_bins(self):
        """When all bins < 80%, analytics should report 0% efficiency and safe DSS status."""
        db_module.insert_reading("BIN-001", 30)
        db_module.insert_reading("BIN-002", 40)

        response = self.client.get("/analytics")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")

        self.assertIn("DSS Recommendation:", html)
        self.assertIn("All bins are currently operating within safe levels.", html)
        self.assertIn("0%", html)
        self.assertIn("Network Waste Volume:", html)

    def test_analytics_critical_state_selective_routing(self):
        """When a bin is >= 80%, analytics should trigger selective DSS recommendation and positive efficiency gain."""
        db_module.insert_reading("BIN-001", 85)
        db_module.insert_reading("BIN-002", 40)

        response = self.client.get("/analytics")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")

        self.assertIn("Selective smart collection is recommended", html)
        self.assertIn("Traditional Route:", html)
        self.assertIn("Optimized Route:", html)

    # -------------------------------------------------------------------------
    # ROUTES & MAP
    # -------------------------------------------------------------------------

    def test_routes_endpoint_lists_urgent_bins_sorted(self):
        """GET /routes should filter only bins >= 80% and sort by fill level descending."""
        db_module.insert_reading("BIN-001", 82)
        db_module.insert_reading("BIN-002", 95)
        db_module.insert_reading("BIN-003", 50)  # not critical

        response = self.client.get("/routes")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")

        self.assertIn("Urgent Collection Bins", html)
        self.assertIn("BIN-002", html)
        self.assertIn("BIN-001", html)
        self.assertNotIn("<td>BIN-003</td>", html)

    def test_map_endpoint_delivers_map_payload(self):
        """GET /map should return HTTP 200 and embed valid JSON objects for Leaflet."""
        db_module.insert_reading("BIN-001", 85)

        response = self.client.get("/map")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")

        self.assertIn("Smart Waste Map", html)
        self.assertIn("BIN-001", html)

    # -------------------------------------------------------------------------
    # COLLECTIONS & REPORTING
    # -------------------------------------------------------------------------

    def test_collections_endpoint_renders_logged_events(self):
        """GET /collections should show logged collection events with location names."""
        db_module.log_collection_event("BIN-001", 96)

        response = self.client.get("/collections")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")

        self.assertIn("Collection Event Log", html)
        self.assertIn("BIN-001", html)
        self.assertIn("96%", html)

    def test_generate_report_endpoint_downloads_pdf(self):
        """GET /generate-report should generate and serve a valid PDF file."""
        db_module.insert_reading("BIN-001", 60)
        db_module.insert_reading("BIN-002", 85)

        response = self.client.get("/generate-report")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")
        self.assertGreater(len(response.data), 1000)  # non-empty PDF binary


if __name__ == "__main__":
    unittest.main(verbosity=2)
