import ast
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
ALLOWED = {"sqlite3", "tempfile", "contextlib", "dataclasses", "hashlib", "pathlib", "time", "typing", "re", "threading"}


def bad_imports(source):
    invalid = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            invalid.extend(x.name for x in node.names if x.name.split(".")[0] not in ALLOWED)
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if not (module in ALLOWED or module in {"packages.contracts", "packages.control", "packages.control_store.store"}
                    or node.level and module == "qualification"):
                invalid.append(module)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec", "__import__"}:
            invalid.append(node.func.id)
    return invalid


class OfflineBoundaryTests(unittest.TestCase):
    def test_store_simulator_have_no_device_or_network_import_path(self):
        paths = sorted([*(ROOT / "packages/control_store").glob("*.py"), *(ROOT / "packages/simulator").glob("*.py")])
        self.assertEqual(len(paths), 5)
        for path in paths:
            self.assertEqual(bad_imports(path.read_text()), [], str(path))
        for invalid in ("import socket", "from urllib.request import urlopen", "import hassapi", "import paho.mqtt",
                        "from packages.ha import send", "__import__('requests')"):
            self.assertTrue(bad_imports(invalid))

    def test_fresh_simulator_with_network_disabled(self):
        result = subprocess.run([sys.executable, "-B", "-m", "tests.fixtures.network_denied_probe"],
                                cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
