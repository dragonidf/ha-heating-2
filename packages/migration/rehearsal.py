"""Synthetic immutable input → empty disposable evidence DB → disarmed rollback copy."""

from dataclasses import replace
from pathlib import Path
from hashlib import sha256
from packages.contracts import OneShot, Action, RuntimeMode
from packages.contracts.models import require
from packages.offline.contracts import (
    LegacyBundle,
    MigrationPlan,
    ManifestEntry,
    MigrationReceipt,
    RollbackResult,
    Origin,
)
from packages.offline.codec import encode, decode
from packages.evidence.store import (
    EvidenceStore,
    EvidenceConflict,
    EvidenceFailure,
    record,
    checksum,
)


def dry_run(bundle: LegacyBundle) -> MigrationPlan:
    require(type(bundle) is LegacyBundle, "Synthetic legacy schema required")
    source_hash = checksum(encode(bundle))
    manifest = []

    def entry(
        source: str, target: str, unit: str, continuity: str, value: object
    ) -> ManifestEntry:
        return ManifestEntry(
            source,
            target,
            "synthetic-legacy/1",
            "offline/2.0",
            unit,
            continuity,
            checksum(encode(value)),
        )

    for c in bundle.counters:
        manifest.append(
            entry(c.source_key, c.target_key, c.unit.value, c.continuity, c)
        )
    for source, target, unit, value in (
        ("legacy.model", "model.champion", "C; C/(kW*h); 1/h", bundle.coefficients),
        ("legacy.plan", "plan.original", "UTC seconds", bundle.plan),
        ("legacy.fan", "fan.saved", "C delta; UTC seconds", bundle.fan),
        ("legacy.fan_policy", "fan.policy", "percent", bundle.fan_policy),
        ("legacy.settings", "settings.saved", "typed ControlPolicy/1", bundle.policy),
        ("legacy.state", "state.saved", "typed ControlState/1", bundle.state),
    ):
        if value is not None:
            manifest.append(entry(source, target, unit, target, value))
    for shot in bundle.one_shots:
        manifest.append(
            entry(
                "legacy.one_shot",
                shot.intent_id,
                "UTC seconds; grid epoch",
                shot.intent_id,
                shot,
            )
        )
    for forecast in bundle.curves:
        manifest.append(
            entry(
                "legacy.curve",
                forecast.identity,
                "C; kWh; UTC seconds",
                forecast.cycle_id,
                forecast,
            )
        )
    return MigrationPlan(source_hash, source_hash, bundle, tuple(manifest))


def stage(plan: MigrationPlan, target: EvidenceStore) -> MigrationReceipt:
    if dry_run(plan.bundle) != plan:
        raise EvidenceConflict("Forged or changed migration manifest")
    receipt_id = checksum("receipt:" + plan.identity)
    with target.transaction() as con:
        existing = con.execute(
            "SELECT 1 FROM archive WHERE id=?", (receipt_id,)
        ).fetchone()
        if existing:
            value = decode(target._get(con, receipt_id).payload)
            if (
                not isinstance(value, MigrationReceipt)
                or value.source_hash != plan.source_hash
            ):
                raise EvidenceConflict("Migration identity conflict")
            return value
        if target._head(con)[0] != 0:
            raise EvidenceConflict("New empty migration target required")
        first = target._append(
            con,
            record(plan.identity, plan, plan.bundle.captured_at, "synthetic.migration"),
        )
        for c in plan.bundle.counters:
            origin = Origin(
                c.target_key, c.continuity, plan.bundle.captured_at, c.value
            )
            target._append(
                con, record("origin:" + c.target_key, origin, origin.at, origin.stream)
            )
        values = [
            plan.bundle.coefficients,
            plan.bundle.fan,
            plan.bundle.fan_policy,
            plan.bundle.policy,
            plan.bundle.state,
        ]
        if plan.bundle.plan is not None:
            values.append(plan.bundle.plan)
        for index, value in enumerate(values):
            identity = checksum(f"{plan.identity}:state:{index}")
            target._append(
                con,
                record(
                    identity,
                    value,
                    getattr(value, "at", plan.bundle.captured_at),
                    "synthetic.migrated_state",
                ),
            )
        for shot in plan.bundle.one_shots:
            target._append(
                con,
                record(
                    shot.intent_id, shot, plan.bundle.captured_at, "synthetic.one_shots"
                ),
            )
        for forecast in plan.bundle.curves:
            target._append(
                con,
                record(
                    forecast.identity, forecast, forecast.recorded_at, forecast.cycle_id
                ),
            )
        receipt = MigrationReceipt(
            receipt_id, plan.source_hash, first, target._head(con)[0] + 1
        )
        target._append(
            con,
            record(receipt_id, receipt, plan.bundle.captured_at, "synthetic.migration"),
        )
        return receipt


def rollback_copy(
    plan: MigrationPlan, source: EvidenceStore, destination: Path
) -> RollbackResult:
    if dry_run(plan.bundle) != plan:
        raise EvidenceConflict("Changed rollback source manifest")
    source.backup(destination)
    copied = EvidenceStore(destination)
    receipt = decode(copied.get(checksum("receipt:" + plan.identity)).payload)
    if (
        not isinstance(receipt, MigrationReceipt)
        or receipt.source_hash != plan.source_hash
    ):
        raise EvidenceConflict("Rollback source not staged")
    watermark = copied.head()[0]
    # Carry newer consumed/unknown outcomes forward, never restore an older pending marker.
    shots = {shot.intent_id: shot for shot in plan.bundle.one_shots}
    with copied.connection() as con:
        rows = con.execute(
            "SELECT seq,payload,checksum,previous,chain FROM archive WHERE kind='OneShot' ORDER BY seq LIMIT 4097"
        ).fetchall()
        if len(rows) > 4096:
            raise EvidenceFailure("Rollback one-shot bound exceeded")
        for row in rows:
            value = decode(copied._read(row).payload)
            if not isinstance(value, OneShot):
                raise EvidenceFailure("Invalid migrated one-shot")
            previous = shots.get(value.intent_id)
            if (
                previous is not None
                and previous.consumed_at is not None
                and value.consumed_at is None
            ):
                raise EvidenceConflict("One-shot consumption cannot rewind")
            shots[value.intent_id] = value
    counters = tuple(
        replace(c, value=copied.summary(c.target_key).actual_total_kwh)
        for c in plan.bundle.counters
    )
    stopped = replace(
        plan.bundle.state,
        plan=None,
        accepted_input_hash=None,
        last_intent=None,
        last_receipt=None,
        desired_action=Action.STOP,
        reconciled=False,
        mode=RuntimeMode.STARTING,
    )
    bundle = replace(
        plan.bundle,
        counters=counters,
        one_shots=tuple(shots.values()),
        plan=None,
        state=stopped,
        policy=replace(plan.bundle.policy, armed=False, allow_automatic=False),
        fan=replace(plan.bundle.fan, sensor_valid=False, below_since=None),
    )
    # The full SQLite copy retains every post-freeze event, not just the new total.
    identity = checksum("rollback:" + plan.source_hash + str(watermark))
    with copied.connection() as con:
        captured = max(
            plan.bundle.captured_at,
            float(con.execute("SELECT max(at) FROM archive").fetchone()[0]),
        )
    bundle = replace(bundle, identity=identity, captured_at=captured)
    copied.append(record(identity, bundle, captured, "synthetic.rollback"))
    copied.checkpoint()
    artifact_hash = sha256(copied.path.read_bytes()).hexdigest()
    return RollbackResult(bundle, plan.source_hash, watermark, artifact_hash)
