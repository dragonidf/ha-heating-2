from pathlib import Path
import tempfile
from dataclasses import replace
from packages.contracts import Unit, Clock, TimeWindow, Action, QualityStatus
from packages.offline.contracts import Binding, Registry, Principal, SourceEvent
from packages.ha_fake.client import FakeHAClient
from packages.ha_fake.runtime import OfflineIntegration
from packages.evidence.store import EvidenceStore
from packages.control_store.store import ControlStore
from packages.simulator.engine import FakeActuator, Simulator
from tests.fixtures.synthetic import state, policy, reading
from tests.fixtures.wp1c import request, thermal
from packages.planner import Stamp, Forecast


def binding(
    role,
    *,
    entity=None,
    physical=None,
    source=None,
    priority=0,
    unit=None,
    coverage=(),
    **changes,
):
    return Binding(
        entity or "synthetic." + role,
        role,
        physical or "synthetic.physical." + role,
        source or "synthetic.source." + role,
        unit
        or (
            Unit.CELSIUS
            if role in ("room", "return", "thermostat", "fireplace", "weather")
            else (
                Unit.WATT
                if role in ("group", "load", "inlet", "deye_grid", "deye_load", "phase")
                else Unit.KWH if role == "counter" else Unit.BOOLEAN
            )
        ),
        10,
        priority,
        ("read",),
        coverage,
        **changes,
    )


def registry(**changes):
    return replace(
        Registry(
            1,
            tuple(binding(role) for role in ("room", "return", "thermostat", "grid")),
            2,
            "conflict_unknown",
            0.5,
        ),
        **changes,
    )


def measurement(b, at, value):
    return reading(
        value,
        b.unit,
        physical_id=b.physical_id,
        source_id=b.source_id,
        observed_at=at,
        received_at=at,
    )


def event(b, at, value, sequence=1, **changes):
    return SourceEvent(
        f"{b.entity}:{sequence}",
        b.entity,
        sequence,
        at,
        measurement(b, at, value),
        **changes,
    )


def temp(test, prefix="heating-wp2a-"):
    directory = tempfile.TemporaryDirectory(prefix=prefix)
    test.addCleanup(directory.cleanup)
    return Path(directory.name)


def harness(test, registry_config=None):
    store = ControlStore.create(
        temp(test, "heating-wp1b-"),
        state(),
        policy(strict_windows=(TimeWindow(start=95, end=10000),)),
    )
    sim = Simulator(store, FakeActuator(), "synthetic.wp2a")
    client = FakeHAClient(registry_config or registry())
    client.connect()
    session = client.grant(
        Principal("synthetic.operator", ("read", "control", "admin"), 1)
    )
    runtime = OfflineIntegration(
        client, sim, EvidenceStore.create(temp(test)), session, model_revision=1
    )
    test.addCleanup(lambda: runtime.simulator.close())
    return runtime, session


def load(runtime, at=100, seq=1):
    clock = Clock(utc=at, monotonic=900 + at, boot_id=runtime.simulator.state.boot_id)
    for b, value in zip(runtime.client.registry.bindings, (18, 25, 19, True)):
        e = event(b, at, value, seq)
        runtime.client.push(e)
    runtime.drain_events(clock)
    return clock


def planned(runtime, with_request=False):
    c = load(runtime)
    runtime.reconcile(c, runtime.operator, action=Action.STOP, writers_known=True)
    c = load(runtime, 106, 2)
    snap = runtime.snapshot(c)
    base = request()
    delta = c.utc - base.state.at
    req = replace(
        base,
        stamp=Stamp(
            snap.input_hash,
            snap.revisions,
            snap.boot_id,
            snap.owner_epoch,
            snap.grid_epoch,
        ),
        state=thermal(c.utc, 18, 24),
        slots=tuple(
            replace(
                s,
                window=TimeWindow(
                    start=s.window.start + delta, end=s.window.end + delta
                ),
            )
            for s in base.slots
        ),
        morning=replace(base.morning, window=TimeWindow(start=c.utc, end=c.utc + 7200)),
        allowed=(TimeWindow(start=c.utc, end=c.utc + 7200),),
        weather=Forecast(
            100, 101, TimeWindow(start=c.utc, end=c.utc + 7200), "synthetic.weather"
        ),
        return_probe=snap.return_temperature,
    )
    p = runtime.plan(req)
    runtime.accept(p, c)
    return (c, p, req) if with_request else (c, p)


def recovery_proof(store, slices, amount, **changes):
    """Independent synthetic counter endpoints, never a production metrology claim."""
    from packages.offline.contracts import RecoveryProof
    from packages.offline.codec import encode
    from packages.evidence.store import record, checksum

    with store.read_snapshot() as con:
        origin = store._origin(con, slices[0].stream)
    start, end = min(s.start for s in slices), max(s.end for s in slices)
    left_id, right_id = "synthetic.proof.left", "synthetic.proof.right"
    for identity, at, sample_kwh in ((left_id, start, 0), (right_id, end, amount)):
        store.append(
            record(
                identity,
                reading(sample_kwh, Unit.KWH, observed_at=at, received_at=at),
                at,
                origin.stream,
            )
        )
    proof = RecoveryProof(
        origin.stream,
        origin.continuity,
        tuple(s.identity for s in slices),
        TimeWindow(start=start, end=end),
        "synthetic.local",
        "synthetic.meter",
        left_id,
        right_id,
        amount,
        QualityStatus.VALID,
    )
    proof = replace(proof, **changes)
    digest = checksum(encode(proof))
    store.append(record(digest, proof, end, origin.stream))
    return digest
