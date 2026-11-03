"""Fresh-interpreter side-effect probe, also used by CI. Test harness may do I/O."""
import builtins
import importlib
import os
import pathlib
import random
import socket
import sqlite3
import subprocess
import time
from unittest.mock import patch
from contextlib import ExitStack


def deny(*args, **kwargs):
    raise AssertionError("Pure module attempted an external side effect or global clock/random")


def probe():
    targets = ((builtins, "open"), (os, "open"), (pathlib.Path, "open"),
               (socket, "socket"), (socket, "create_connection"), (socket, "getaddrinfo"),
               (sqlite3, "connect"), (subprocess, "Popen"), (os, "system"),
               (time, "time"), (time, "monotonic"), (time, "perf_counter"),
               (time, "sleep"), (random, "random"), (random, "seed"))
    with ExitStack() as stack:
        for module, name in targets:
            stack.enter_context(patch.object(module, name, deny))
        for name in ("packages.contracts.models", "packages.contracts.control", "packages.contracts.codec",
                     "packages.contracts", "packages.control.kernel", "packages.control"):
            importlib.import_module(name)
        # Build only synthetic immutable records; import and invocation are both guarded.
        from tests.fixtures.synthetic import state, event, snapshot, policy, clock
        from packages.control import reduce
        from packages.contracts import from_json, to_json
        decision = reduce(state(), event(), snapshot(), policy(), clock())
        assert decision == from_json(to_json(decision))


if __name__ == "__main__":
    probe()
