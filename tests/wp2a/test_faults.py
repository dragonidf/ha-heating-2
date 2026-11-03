import json, os, sqlite3, subprocess, sys, tempfile, unittest
from pathlib import Path
from packages.evidence.store import EvidenceStore, EvidenceFailure
from packages.offline.contracts import Origin
from packages.migration.rehearsal import stage, dry_run
from tests.wp2a.helpers import temp
from tests.wp2a.test_energy import point
from tests.wp2a.test_migration import legacy


class CrashTests(unittest.TestCase):
    def child(self, root, operation, checkpoint):
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "tests.wp2a.crash_worker",
                str(root),
                operation,
                checkpoint,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 77, result.stdout + result.stderr)

    def test_append_commit_kills_recover_atomic_prefix_without_duplicate(self):
        for where in ("before_commit", "after_commit"):
            root = temp(self)
            store = EvidenceStore.create(root)
            store.origin(Origin("synthetic.heat", "c", 100, 0))
            self.child(root, "power", where)
            opened = EvidenceStore(root)
            self.assertIn(opened.verify(), (1, 2))
            from packages.offline.contracts import PowerPoint

            p = PowerPoint(
                "synthetic.crash",
                "synthetic.heat",
                100,
                100,
                3,
                "derived",
                ("synthetic.meter",),
                "left_hold",
            )
            opened.power(p)
            opened.power(p)
            self.assertEqual(opened.verify(), 2)

    def test_energy_post_kills_cannot_repeat_actual_kwh(self):
        for where, expected in (("before_commit", 0), ("after_commit", 0.025)):
            root = temp(self)
            store = EvidenceStore.create(root)
            store.origin(Origin("synthetic.heat", "c", 100, 0))
            store.power(point(100))
            self.child(root, "finalize", where)
            opened = EvidenceStore(root)
            self.assertAlmostEqual(
                opened.summary("synthetic.heat").actual_total_kwh, expected
            )
            opened.finalize("synthetic.heat", 130, as_of=130)
            self.assertAlmostEqual(
                opened.summary("synthetic.heat").actual_total_kwh, 0.025
            )

    def test_schema_migration_and_staged_import_crash_are_all_or_nothing(self):
        for operation, where in (
            ("schema", "schema_before_commit"),
            ("schema", "after_commit"),
            ("migration", "before_commit"),
            ("migration", "after_commit"),
        ):
            root = temp(self)
            store = EvidenceStore.create(
                root, version=1 if operation == "schema" else 2
            )
            self.child(root, operation, where)
            opened = EvidenceStore(root)
            if operation == "schema":
                opened.migrate()
                self.assertEqual(opened.version, 2)
            else:
                self.assertIn(opened.head()[0], (0, 12))
                receipt = stage(dry_run(legacy()), opened)
                self.assertEqual(
                    opened.summary("synthetic.total").actual_total_kwh, 123.456789
                )
                self.assertEqual(stage(dry_run(legacy()), opened), receipt)

    def test_checkpoint_kill_corrupt_file_and_missing_file_never_reset_data(self):
        root = temp(self)
        store = EvidenceStore.create(root)
        store.origin(Origin("s", "c", 100, 7))
        self.child(root, "checkpoint", "checkpoint_before")
        self.assertEqual(EvidenceStore(root).summary("s").actual_total_kwh, 7)
        store.checkpoint()
        store.path.write_bytes(b"synthetic corrupt sqlite")
        with self.assertRaises(EvidenceFailure):
            EvidenceStore(root)
        self.assertEqual(store.path.read_bytes(), b"synthetic corrupt sqlite")

    def test_actual_sqlite_vfs_eio_enospc_cannot_block_stop_or_create_heat(self):
        source = Path(__file__).with_name("evidence_vfs_fault.c")
        build = temp(self)
        library = build / "fault.so"
        subprocess.run(
            ["cc", "-shared", "-fPIC", str(source), "-o", str(library), "-ldl"],
            check=True,
            capture_output=True,
            timeout=30,
        )
        for mode, signature in (("sync", "WP2A_VFS_EIO"), ("full", "WP2A_VFS_ENOSPC")):
            root = temp(self)
            critical = temp(self, "heating-wp1b-")
            preload = str(library) + (
                " " + os.environ["LD_PRELOAD"] if os.environ.get("LD_PRELOAD") else ""
            )
            environment = dict(
                os.environ,
                LD_PRELOAD=preload,
                WP2A_FAULT_ROOT=str(root),
                WP2A_FAULT_KIND=mode,
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "tests.wp2a.vfs_worker",
                    str(root),
                    str(critical),
                ],
                env=environment,
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(signature, result.stderr)
            proof = json.loads(result.stdout)
            self.assertTrue(proof["archive_failed"])
            self.assertEqual(proof["heat"], 0)
            self.assertTrue(proof["stop"])
            self.assertIn(proof["recovery"], ("valid_prefix", "blocked_no_reset"))
