import ast, subprocess, sys, unittest
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
from packages.contracts import ContractError
from packages.offline.contracts import Origin
from packages.evidence.store import EvidenceStore, EvidenceFailure, EvidenceConflict
from packages.offline.codec import encode, decode
from tests.wp2a.helpers import temp, registry, binding
from tests.wp2a.test_migration import legacy
from tests.wp2a.test_energy import point

ROOT = Path(__file__).resolve().parents[2]
STDLIB = {
    "dataclasses",
    "datetime",
    "hashlib",
    "typing",
    "sqlite3",
    "tempfile",
    "contextlib",
    "pathlib",
    "json",
}
LOCAL = {
    "packages.contracts",
    "packages.contracts.models",
    "packages.contracts.codec",
    "packages.control_store.qualification",
    "packages.control_store.store",
    "packages.simulator.engine",
    "packages.planner",
    "packages.planner.sources",
    "packages.planner.evidence",
    "packages.fan_policy",
    "packages.thermal",
    "packages.thermal.wire",
    "packages.offline.contracts",
    "packages.offline.codec",
    "packages.evidence.store",
    "packages.evidence.energy",
    "packages.ha_fake.client",
    "packages.ha_fake.adapter",
}
BANNED = {
    "open",
    "exec",
    "eval",
    "__import__",
    "now",
    "utcnow",
    "today",
    "call_service",
    "urlopen",
    "getattr_static",
}


def violations(source):
    errors = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            errors.extend(
                alias.name for alias in node.names if alias.name not in STDLIB
            )
        if isinstance(node, ast.ImportFrom) and node.module not in STDLIB | LOCAL:
            errors.append(node.module)
        if isinstance(node, ast.Call):
            name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            )
            if name in BANNED:
                errors.append(name)
    return errors


class BoundaryTests(unittest.TestCase):
    def test_closed_static_graph_has_no_network_real_ha_or_dynamic_escape(self):
        paths = sorted(
            p
            for group in ("offline", "evidence", "ha_fake", "migration")
            for p in (ROOT / "packages" / group).glob("*.py")
        )
        self.assertEqual(len(paths), 12)
        for path in paths:
            self.assertEqual(violations(path.read_text()), [], str(path))
        for bad in (
            "import socket",
            "from homeassistant.core import HomeAssistant",
            "import requests",
            "from urllib.request import urlopen",
            "__import__('os')",
            "hass.call_service('climate/on')",
            "datetime.now()",
        ):
            self.assertTrue(violations(bad))
        # Accepted synthetic graph stays closed. The only separately reviewed
        # real-HA profile is a read-only v2 observer; its no-write AST barrier
        # is enforced by tests.wp2c_revision.test_live_shadow_v2.
        live = ROOT / "custom_components"
        self.assertEqual({p.name for p in live.iterdir()}, {"heating_ai_v2"})

    def test_actual_synthetic_integration_migration_and_stop_with_network_denied(self):
        result = subprocess.run(
            [sys.executable, "-B", "-m", "tests.wp2a.network_probe"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_unqualified_linked_sqlite_and_changed_journal_mode_fail_closed(self):
        with patch("packages.evidence.store.inspect_sqlite") as info:
            info.return_value.qualified = False
            with self.assertRaises(EvidenceFailure):
                EvidenceStore.create(temp(self))
        root = temp(self)
        store = EvidenceStore.create(root)
        store.origin(Origin("s", "c", 100, 1))
        with patch("packages.evidence.store.inspect_sqlite") as info:
            info.return_value.qualified = False
            with self.assertRaises(EvidenceFailure):
                EvidenceStore(root)
        with store.connection() as con:
            con.execute("PRAGMA journal_mode=DELETE")
        with self.assertRaises(EvidenceFailure):
            store.head()

    def test_source_and_future_legacy_boundaries_are_not_assumed_qualified(self):
        r = registry()
        bindings = r.bindings
        with self.assertRaises(ContractError):
            replace(
                r,
                bindings=(
                    bindings[0],
                    replace(bindings[1], source_id=bindings[0].source_id),
                ),
            )
        b = legacy()
        with self.assertRaises(ContractError):
            replace(b, captured_at=99998)
        with self.assertRaises(ContractError):
            replace(
                b,
                counters=(
                    b.counters[0],
                    replace(b.counters[1], continuity=b.counters[0].continuity),
                ),
            )

    def test_link_replacement_after_open_is_rejected(self):
        source = EvidenceStore.create(temp(self))
        source.origin(Origin("s", "c", 100, 0))
        source.checkpoint()
        other = EvidenceStore.create(temp(self))
        other.origin(Origin("s", "d", 100, 9))
        other.checkpoint()
        source.path.unlink()
        source.path.symlink_to(other.path)
        with self.assertRaises(EvidenceFailure):
            source.head()
