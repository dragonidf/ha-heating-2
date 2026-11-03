"""Fake source normalization; no service calls or freshness manufactured by fetch."""

from dataclasses import replace
from hashlib import sha256
from packages.contracts import (
    Clock,
    ControlState,
    ControlSnapshot,
    Reading,
    Revisions,
    QualityStatus,
    SourceKind,
)
from packages.contracts.models import require
from packages.offline.contracts import Registry, SourceEvent


class SourceAdapter:
    def __init__(self, registry: Registry):
        self.registry = registry
        self._latest: dict[str, SourceEvent] = {}
        self._seen: dict[str, SourceEvent] = {}
        self.grid_epoch = 0
        self._grid: bool | None = None
        self._generation = -1
        self._last_utc: float | None = None
        self._clock_bad = False

    def connection(self, generation: int) -> None:
        if generation != self._generation:
            self._generation = generation
            self._latest = {}
            self._grid = None
            self.grid_epoch += 1

    def ingest(self, event: SourceEvent) -> bool:
        old = self._seen.get(event.identity)
        if old is not None:
            require(old == event, "Source identity conflict")
            return False
        require(len(self._seen) < 4096, "Bounded source replay frontier full")
        binding = next(
            (b for b in self.registry.bindings if b.entity == event.entity), None
        )
        require(binding is not None, "Unbound fake event")
        if event.reading is not None and binding is not None:
            require(
                (event.reading.unit, event.reading.physical_id, event.reading.source_id)
                == (binding.unit, binding.physical_id, binding.source_id),
                "Source provenance mismatch",
            )
        self._seen[event.identity] = event
        previous = self._latest.get(event.entity)
        if previous is not None and (
            event.sequence <= previous.sequence
            or event.received_at < previous.received_at
        ):
            return False
        if (
            previous
            and event.reading
            and previous.reading
            and event.reading.observed_at < previous.reading.observed_at
        ):
            event = replace(
                event, reading=None
            )  # Clock rollback invalidates this source; never refresh old heat data.
        self._latest[event.entity] = event
        return True

    def current_event(self, event: SourceEvent) -> bool:
        return self._latest.get(event.entity) == event and event.reading is not None

    def select(self, role: str, clock: Clock, *, connected: bool) -> Reading | None:
        if not connected or self._clock_bad:
            return None
        candidates = []
        for b in sorted(
            (b for b in self.registry.bindings if b.role == role),
            key=lambda b: b.priority,
        ):
            event = self._latest.get(b.entity)
            r = event.reading if event else None
            if (
                r is not None
                and r.value is not None
                and r.quality.status is QualityStatus.VALID
                and r.provenance.kind not in (SourceKind.HELD, SourceKind.FORECAST)
                and 0 <= clock.utc - r.observed_at <= b.max_age_s
                and r.observed_at <= r.received_at <= clock.utc
                and r.quality.age_s <= b.max_age_s
            ):
                candidates.append(r)
        if not candidates:
            return None
        first = candidates[0]
        if self.registry.alias_policy == "conflict_unknown" and (
            max(r.observed_at for r in candidates)
            - min(r.observed_at for r in candidates)
            > self.registry.max_skew_s
            or any(
                abs(float(r.value) - float(first.value))
                > self.registry.conflict_tolerance
                for r in candidates
                if r.value is not None and first.value is not None
            )
        ):
            return None
        return replace(
            first,
            quality=replace(
                first.quality,
                age_s=max(first.quality.age_s, clock.utc - first.observed_at),
            ),
        )

    def snapshot(
        self,
        clock: Clock,
        state: ControlState,
        config_revision: int,
        model_revision: int,
        *,
        connected: bool
    ) -> ControlSnapshot:
        if self._last_utc is not None and clock.utc < self._last_utc:
            self._clock_bad = True
        self._last_utc = clock.utc
        readings = {
            role: self.select(role, clock, connected=connected)
            for role in ("room", "return", "thermostat", "grid")
        }
        grid = readings["grid"].value if readings["grid"] else None
        if grid is not self._grid:
            self.grid_epoch += 1
            self._grid = grid if type(grid) is bool else None
        digest = sha256(
            repr((readings, self.registry, state.owner_epoch, self.grid_epoch)).encode()
        ).hexdigest()
        return ControlSnapshot(
            snapshot_id="synthetic.snapshot." + digest[:32],
            input_hash=digest,
            boot_id=state.boot_id,
            revisions=Revisions(
                config=config_revision,
                model=model_revision,
                topology=self.registry.revision,
            ),
            grid_epoch=self.grid_epoch,
            owner_epoch=state.owner_epoch,
            captured_at=clock.utc,
            room=readings["room"],
            return_temperature=readings["return"],
            thermostat=readings["thermostat"],
            grid_actual=readings["grid"],
            forecast_grid=None,
            power=None,
            compute_available=connected,
            hard_stop=False,
            scheduled_outage=False,
        )
