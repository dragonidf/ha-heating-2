"""Fresh disposable process: actual socket/network constructors are disabled."""

import socket
from unittest.mock import patch
import unittest
from tests.wp2a.helpers import harness, planned
from packages.offline.codec import encode, decode
from packages.migration.rehearsal import stage, dry_run, rollback_copy
from packages.evidence.store import EvidenceStore
from tests.wp2a.helpers import temp
from tests.wp2a.test_migration import legacy


def denied(*args, **kwargs):
    raise AssertionError("Network forbidden")


case = unittest.TestCase()
try:
    with patch.object(socket, "socket", denied), patch.object(
        socket, "create_connection", denied
    ), patch.object(socket, "getaddrinfo", denied):
        runtime, session = harness(case)
        clock, proposal = planned(runtime)
        assert runtime.pump(clock)
        assert decode(encode(runtime.status(session, clock))).physical_verified is False
        runtime.trusted_stop(clock)
        runtime.flush_evidence()
        store = EvidenceStore.create(temp(case))
        plan = dry_run(legacy())
        stage(plan, store)
        result = rollback_copy(plan, store, temp(case))
        assert not result.bundle.policy.armed
finally:
    case.doCleanups()
