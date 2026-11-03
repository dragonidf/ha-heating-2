"""Pinned public SQLite test dependency. Never part of a runtime/device adapter."""
import hashlib
import io
from pathlib import Path
import subprocess
import tempfile
import urllib.request
import zipfile

URL = "https://www.sqlite.org/2026/sqlite-amalgamation-3510300.zip"
SHA256 = "acb1e6f5d832484bf6d32b681e858c38add8b2acdfd42ac5df24b8afb46552b4"
SOURCE_ID = "2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618"


def build() -> Path:
    root = Path(tempfile.gettempdir()) / "heating-wp1b-sqlite-3510300"
    root.mkdir(exist_ok=True)
    if root.is_symlink():
        raise ValueError("Linked build directory forbidden")
    archive = root / "source.zip"
    if not archive.exists():
        with urllib.request.urlopen(URL, timeout=30) as response:
            data = response.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            raise ValueError("Oversized source archive")
    else:
        data = archive.read_bytes()
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError("Source archive checksum mismatch")
    archive.write_bytes(data)
    with zipfile.ZipFile(io.BytesIO(data)) as source:
        for name in ("sqlite3.c", "sqlite3.h"):
            (root / name).write_bytes(source.read("sqlite-amalgamation-3510300/" + name))
    subprocess.run(["cc", "-O2", "-fPIC", "-shared", "-DSQLITE_THREADSAFE=1", str(root / "sqlite3.c"),
                    "-o", str(root / "libsqlite3.so.0"), "-ldl", "-lpthread"], check=True, timeout=120)
    return root


if __name__ == "__main__":
    print(build())
