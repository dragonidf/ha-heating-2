"""Closed import graph + source path scan + fresh-process side-effect guards."""
import ast
import pathlib
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
ALLOWED = {"dataclasses", "datetime", "enum", "math", "json", "types", "typing", "hashlib"}
LOCAL = {"models", "control", "codec", "kernel"}
FORBIDDEN_CALLS = {"open", "exec", "eval", "__import__", "getattr_static", "system", "connect", "call_service",
                   "now", "utcnow", "today"}


def violations(source):
    errors = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            errors.extend(alias.name for alias in node.names if alias.name.split(".")[0] not in ALLOWED)
        elif isinstance(node, ast.ImportFrom):
            name = node.module or ""
            if not ((node.level and name in LOCAL) or name in ALLOWED or name == "packages.contracts"):
                errors.append(name)
        elif isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if name in FORBIDDEN_CALLS:
                errors.append(name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            errors.append("mutable global")
    return errors


class PurityTests(unittest.TestCase):
    def test_closed_import_graph_and_no_actuator_paths(self):
        sources = sorted((ROOT / "packages").rglob("*.py"))
        self.assertEqual(len(sources), 7)
        for path in sources:
            with self.subTest(module=str(path.relative_to(ROOT))):
                self.assertEqual(violations(path.read_text()), [])

    def test_guard_itself_rejects_io_dynamic_import_and_ha(self):
        for source in ("import os", "from pathlib import Path", "import hassapi",
                       "from packages.gateway import send", "__import__('socket')", "open('data')",
                       "hass.call_service('climate/set_temperature')", "exec('print(1)')", "datetime.now()"):
            self.assertTrue(violations(source), source)

    def test_fresh_import_and_reducer_run_with_external_apis_disabled(self):
        result = subprocess.run([sys.executable, "-B", "-m", "tests.properties.import_probe"],
                                cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
