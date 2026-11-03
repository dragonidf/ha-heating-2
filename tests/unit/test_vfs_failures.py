import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class VFSFailureTests(unittest.TestCase):
    def test_sqlite_vfs_sync_and_write_failures_cannot_emit_heat(self):
        source = Path(__file__).resolve().parents[1] / "fixtures/sqlite_vfs_fault.c"
        with tempfile.TemporaryDirectory(prefix="heating-wp1b-") as build:
            library = Path(build) / "synthetic-vfs-fault.so"
            subprocess.run(["cc", "-shared", "-fPIC", str(source), "-o", str(library), "-ldl"],
                           check=True, capture_output=True, timeout=30)
            for kind, signature in (("sync", "WP1B_VFS_EIO"), ("full", "WP1B_VFS_ENOSPC")):
                with self.subTest(kind=kind), tempfile.TemporaryDirectory(prefix="heating-wp1b-") as root:
                    preload = str(library) + (" " + os.environ["LD_PRELOAD"] if os.environ.get("LD_PRELOAD") else "")
                    child_env = dict(os.environ, LD_PRELOAD=preload, WP1B_FAULT_ROOT=root, WP1B_FAULT_KIND=kind)
                    result = subprocess.run([sys.executable, "-B", "-m", "tests.fixtures.vfs_failure_worker", root],
                                            env=child_env, capture_output=True, text=True, timeout=15)
                    self.assertIn(signature, result.stderr)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    proof = json.loads(result.stdout)
                    self.assertFalse(proof["fake_heat_emitted"])
                    self.assertIn(proof["recovery"], ("STARTING_STOP_no_replay", "BLOCKED_corrupt_or_unknown_store_no_reset"))
