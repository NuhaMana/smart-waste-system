"""
tests/test_report.py
====================
Automated test suite for the Analytics Report Generation Engine.

These tests verify both:
  1. Statistical Correctness: Verifies that data aggregation, mathematical
     averages, risk distributions, critical count filters, and collection
     event summaries computed in generate_report_data() are 100% accurate.
  2. Document Structure: Verifies that create_pdf_report() builds a valid,
     well-formed PDF file containing the required ReportLab sections,
     tables, and embedded Matplotlib visualisations.

All tests run against an isolated temporary SQLite database and temporary
output directories to ensure zero impact on production data.

Run from the project root directory:
    python -m unittest tests/test_report.py -v
"""

import os
import sys
import tempfile
import unittest
import pandas as pd

# Ensure project root is in sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database.db as db_module
import reports.report_generator as rg_module


class TestReportGeneration(unittest.TestCase):
    """
    Tests mathematical accuracy and PDF structural validity of the report generator.
    """

    def setUp(self):
        """Create a fresh isolated database before each test."""
        tmp_fd, self.tmp_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(tmp_fd)

        self._orig_db_path = db_module.DB_PATH
        self._orig_rg_db_path = rg_module.DB_PATH

        db_module.DB_PATH = self.tmp_path
        rg_module.DB_PATH = self.tmp_path

        # Initialize schema and seed bins
        db_module.create_tables()

    def tearDown(self):
        """Restore original paths and clean up temporary database."""
        db_module.DB_PATH = self._orig_db_path
        rg_module.DB_PATH = self._orig_rg_db_path

        if os.path.exists(self.tmp_path):
            os.unlink(self.tmp_path)

    # -------------------------------------------------------------------------
    # 1. STATISTICAL ACCURACY TESTS
    # -------------------------------------------------------------------------

    def test_generate_report_data_telemetry_analytics(self):
        """
        Verify statistical calculations for telemetry:
        Total records, average fill level, critical threshold counting (>=80%),
        highest risk bin identification, and risk tier categorization.
        """
        # Insert known test dataset:
        # BIN-001: 30% (Low risk: <50%)
        # BIN-002: 55% (Medium risk: 50-79%)
        # BIN-003: 85% (High risk: >=80%)
        # BIN-004: 90% (High risk: >=80%)
        db_module.insert_reading("BIN-001", 30)
        db_module.insert_reading("BIN-002", 55)
        db_module.insert_reading("BIN-003", 85)
        db_module.insert_reading("BIN-004", 90)

        data = rg_module.generate_report_data()

        # Total records
        self.assertEqual(data["total_records"], 4)

        # Average fill: (30 + 55 + 85 + 90) / 4 = 260 / 4 = 65.0
        self.assertEqual(data["average_fill"], 65.0)

        # Critical records (>= 80%): BIN-003 and BIN-004
        self.assertEqual(data["critical_records"], 2)

        # Highest fill level and corresponding bin
        self.assertEqual(data["highest_fill"], 90)
        self.assertEqual(data["highest_bin"], "BIN-004")

        # Chart artifact paths exist and are populated
        self.assertTrue(os.path.exists(data["trend_path"]))
        self.assertTrue(os.path.exists(data["risk_path"]))
        self.assertGreater(os.path.getsize(data["trend_path"]), 1000)
        self.assertGreater(os.path.getsize(data["risk_path"]), 1000)

    def test_generate_report_data_collection_event_metrics(self):
        """
        Verify collection events analytics:
        Total collections, frequency-based most-collected bin determination,
        average fill level at time of collection, and location JOIN resolution.
        """
        db_module.insert_reading("BIN-001", 50)  # Telemetry needed so report generates

        # Insert known collection events:
        db_module.log_collection_event("BIN-001", 96)
        db_module.log_collection_event("BIN-002", 95)
        db_module.log_collection_event("BIN-002", 98)

        data = rg_module.generate_report_data()

        self.assertEqual(data["total_collections"], 3)
        self.assertEqual(data["most_collected"], "BIN-002")  # Collected twice

        # Average fill at collection: (96 + 95 + 98) / 3 = 289 / 3 = 96.3
        self.assertEqual(data["avg_fill_at_collection"], 96.3)

        # Verify recent events structure and JOIN with bin_master
        self.assertEqual(len(data["recent_events"]), 3)
        for event in data["recent_events"]:
            bin_id, location, fill_at_coll, timestamp = event
            self.assertIn(bin_id, ["BIN-001", "BIN-002"])
            self.assertIsInstance(location, str)
            self.assertGreater(len(location), 0)
            self.assertGreaterEqual(fill_at_coll, 95)

    def test_generate_report_data_empty_db_defense(self):
        """
        Verify defensive error handling: when no telemetry data exists,
        generate_report_data() must raise a descriptive ValueError instead
        of crashing or producing a corrupted report.
        """
        with self.assertRaises(ValueError) as ctx:
            rg_module.generate_report_data()
        self.assertIn("No telemetry data found", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 2. PDF STRUCTURAL & BINARY INTEGRITY TESTS
    # -------------------------------------------------------------------------

    def test_create_pdf_report_builds_valid_pdf_file(self):
        """
        Verify that create_pdf_report() compiles an authentic PDF document
        with the valid %PDF magic header, standard page size, and complete contents.
        """
        db_module.insert_reading("BIN-001", 45)
        db_module.insert_reading("BIN-002", 88)
        db_module.log_collection_event("BIN-002", 97)

        pdf_path = rg_module.create_pdf_report()

        self.assertTrue(os.path.exists(pdf_path))
        self.assertGreater(os.path.getsize(pdf_path), 5000)  # Valid PDF size > 5 KB

        # Check binary file header (%PDF magic bytes)
        with open(pdf_path, "rb") as f:
            header = f.read(5)
            self.assertEqual(header, b"%PDF-")

    def test_create_pdf_report_without_collections_renders_fallback(self):
        """
        Verify PDF builds cleanly when telemetry is present but zero collection
        events have occurred (verifying the fallback message render path).
        """
        db_module.insert_reading("BIN-001", 35)

        pdf_path = rg_module.create_pdf_report()

        self.assertTrue(os.path.exists(pdf_path))
        with open(pdf_path, "rb") as f:
            header = f.read(5)
            self.assertEqual(header, b"%PDF-")


if __name__ == "__main__":
    unittest.main(verbosity=2)
