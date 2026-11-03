import sqlite3
import unittest

from packages.control_store.qualification import inspect_sqlite, supported_sqlite


class SQLiteQualificationTests(unittest.TestCase):
    def test_wal_reset_minimum_is_explicit_and_unknown_backports_are_not_assumed(self):
        for version, accepted in (("3.51.3", True), ("3.53.1", True), ("3.51.2", False),
                                  ("3.46.1", False), ("3.44.6", False), ("3.50.7", False),
                                  ("4.0.0", False),
                                  ("3.51.3-patched", False), ("unknown", False)):
            with self.subTest(version=version):
                self.assertEqual(supported_sqlite(version), accepted)

    def test_actual_linked_runtime_is_observed_and_never_relabelled(self):
        info = inspect_sqlite()
        self.assertEqual(info.version, sqlite3.sqlite_version)
        self.assertEqual(info.qualified, supported_sqlite(info.version))
        self.assertTrue(info.source_id)
