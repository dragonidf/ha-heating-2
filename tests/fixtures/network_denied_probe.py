"""Network APIs disabled during imports, SQLite and every fake command phase."""
import socket
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch


def deny(*args, **kwargs):
    raise AssertionError("Offline simulator attempted network access")


def run():
    with ExitStack() as stack:
        for name in ("socket", "create_connection", "getaddrinfo"):
            stack.enter_context(patch.object(socket, name, deny))
        from tests.unit.test_simulator import ready_simulator
        from packages.contracts import EventKind
        from tests.fixtures.synthetic import event
        with tempfile.TemporaryDirectory(prefix="heating-wp1b-") as directory:
            sim, s, c = ready_simulator(Path(directory))
            try:
                assert sim.pump(s, c)
                sim.ack(c)
                sim.echo(c)
                stop = event(kind=EventKind.SAFETY_STOP, boot_id=c.boot_id, owner_epoch=sim.state.owner_epoch,
                             sequence=0, at=99, expires_at=99.5)
                sim.emergency(stop, s, c, proof=sim.authority.attest(stop))
                sim.flush_audit()
            finally:
                sim.close()


if __name__ == "__main__":
    run()
