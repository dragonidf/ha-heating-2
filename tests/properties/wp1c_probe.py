"""Disposable-process effect denial around an actual WP1C calculation."""

import builtins
import socket
import time
from unittest.mock import patch
from tests.fixtures.wp1c import request
from packages.planner import solve, bridge
from packages.thermal.wire import encode, decode
from packages.learning import due_slots
from packages.fan_policy import FanState, FanPolicy, reduce_fan
from datetime import datetime, timezone


def denied(*args, **kwargs):
    raise AssertionError("forbidden external effect")


with patch.object(builtins, "open", denied), patch.object(
    socket, "socket", denied
), patch.object(socket, "create_connection", denied), patch.object(
    time, "time", denied
), patch.object(
    time, "monotonic", denied
), patch.object(
    time, "sleep", denied
):
    r = request()
    p = solve(r)
    assert decode(encode(p)) == p
    bridge(p, r.stamp, r.state.at, r.slots[-1].window.end + 1)
    due_slots(datetime(2026, 1, 1, tzinfo=timezone.utc), ())
    reduce_fan(
        FanState(0, 0),
        60,
        5,
        valid=True,
        grid=True,
        armed=True,
        permitted=True,
        mode="auto",
        night=False,
        night_request=False,
        policy=FanPolicy(38, 42, 50),
    )
