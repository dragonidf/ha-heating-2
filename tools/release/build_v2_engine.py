#!/usr/bin/env python3
"""Package accepted pure heating modules in the isolated v2 HA component.

No synthetic HA transport or simulator is installed, and no production file
is edited. Reproducibility is verified with SHA256 of every copied source.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PURE = (
    "contracts", "control", "thermal", "planner", "control_store",
    "learning", "evidence", "fan_policy", "offline", "migration",
)
ALLOWED = frozenset(PURE)
SOURCE = ROOT / "packages"
DEST = Path("p0-release/custom_components/heating_ai_v2/engine")
NAMESPACE = "custom_components.heating_ai_v2.engine"


def package(destination: Path) -> dict[str, object]:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    (destination / "__init__.py").write_text(
        '"""Accepted pure Heating AI 2.0 modules, namespaced for HA."""\n'
    )
    hashes: dict[str, str] = {}
    for family in PURE:
        source = SOURCE / family
        if not source.is_dir() or not (source / "__init__.py").is_file():
            raise RuntimeError(f"Missing accepted pure module: {family}")
        for original in sorted(source.rglob("*.py")):
            if original.is_symlink() or not original.is_file():
                raise RuntimeError("Unexpected source file type")
            relative = original.relative_to(SOURCE)
            raw = original.read_bytes()
            if len(raw) > 250_000:
                raise RuntimeError("Unbounded module size")
            source_text = raw.decode("utf-8")
            original_tree = ast.parse(source_text, filename=str(relative))
            for node in ast.walk(original_tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = ([alias.name for alias in node.names]
                             if isinstance(node, ast.Import) else [node.module or ""])
                    for name in names:
                        if name.startswith("packages."):
                            package_root = name.split(".")[1]
                            if package_root not in ALLOWED:
                                raise RuntimeError(
                                    f"Unsafe dependency in {relative}: {package_root}"
                                )
                        if name == "packages":
                            raise RuntimeError(f"Unqualified packages import in {relative}")
            # Python source import statements only; do not replace docs/strings.
            transformed = re.sub(
                r"(?m)^(\s*from\s+)packages\.",
                rf"\g<1>{NAMESPACE}.",
                source_text,
            )
            transformed = re.sub(
                r"(?m)^(\s*import\s+)packages\.",
                rf"\g<1>{NAMESPACE}.",
                transformed,
            )
            ast.parse(transformed, filename=str(relative))
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(transformed, encoding="utf-8")
            hashes[relative.as_posix()] = hashlib.sha256(raw).hexdigest()
    report: dict[str, object] = {
        "purpose": "accepted_pure_modules_only",
        "source_namespace": "packages",
        "installed_namespace": NAMESPACE,
        "files": hashes,
    }
    (destination / "SOURCE-SHA256.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEST)
    args = parser.parse_args()
    report = package(args.output)
    print(f"Packaged {len(report['files'])} accepted pure modules; no fake transport")


if __name__ == "__main__":
    main()
