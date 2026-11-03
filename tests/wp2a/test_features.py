import unittest
from dataclasses import replace
from datetime import date
from zoneinfo import ZoneInfo
from packages.contracts import ContractError, Action, TimeWindow, Clock
from packages.fan_policy import FanState, FanPolicy
from packages.offline.contracts import ProviderEvent
from packages.planner import Forecast
from packages.planner.sources import (
    WeatherSeries,
    WeatherPoint,
    OutageSchedule,
    day_span,
)
from packages.thermal import Interval
from packages.offline.codec import encode, decode
from tests.wp2a.helpers import harness, planned, registry, binding, event, load, temp
from packages.evidence.store import EvidenceStore, EvidenceConflict
from packages.offline.contracts import Origin
from tests.wp2a.test_energy import point


class ExtendedIntegrationTests(unittest.TestCase):
    def test_missing_grid_new_age_and_utc_rollback_stop_without_pending_command(self):
        for mode in ("age", "clock", "grid"):
            runtime, _ = harness(self)
            clock, _ = planned(runtime)
            runtime.pump(clock)
            if mode == "age":
                later = replace(clock, utc=117, monotonic=1017)
            elif mode == "clock":
                later = replace(clock, utc=105, monotonic=1007)
            else:
                b = next(
                    b for b in runtime.client.registry.bindings if b.role == "grid"
                )
                runtime.deliver(
                    event(b, 107, False, 3), replace(clock, utc=107, monotonic=1007)
                )
                later = replace(clock, utc=107, monotonic=1007)
            self.assertFalse(runtime.pump(later))
            self.assertEqual(runtime.simulator.actuator.calls[-1].action, Action.STOP)

    def test_fan_manual_has_independent_ownership_and_night_cannot_stop_fire(self):
        reg = replace(
            registry(),
            bindings=registry().bindings + (binding("fireplace"), binding("fan")),
        )
        runtime, session = harness(self, reg)
        clock, _ = planned(runtime)
        fire = next(b for b in reg.bindings if b.role == "fireplace")
        fan = next(b for b in reg.bindings if b.role == "fan")
        runtime.deliver(event(fire, 106, 24), clock)  # room18 → fire delta6
        policy = FanPolicy(38, 42, 50)
        demand = runtime.fan_demand(
            FanState(105, 0),
            clock,
            policy,
            mode="auto",
            night=False,
            night_request=True,
            permitted=True,
        )
        self.assertEqual(demand.percentage, 42)
        # Night expiry does not remove a freshly supported fireplace request.
        later = load(runtime, 1007, 3)
        runtime.deliver(event(fire, 1007, 24, 2), later)
        demand = runtime.fan_demand(
            demand.state,
            later,
            policy,
            mode="auto",
            night=False,
            night_request=True,
            permitted=True,
        )
        self.assertEqual(demand.percentage, 42)
        runtime.deliver(
            event(fan, 1008, True, 1, author="manual", observed_action=Action.HEAT),
            replace(later, utc=1008, monotonic=1908),
        )
        self.assertFalse(runtime.simulator.state.manual_paused)
        self.assertIsNone(
            runtime.fan_demand(
                demand.state,
                replace(later, utc=1008, monotonic=1908),
                policy,
                mode="auto",
                night=False,
                night_request=False,
                permitted=True,
            ).percentage
        )
        runtime.resume_fan(session)
        self.assertEqual(
            runtime.fan_demand(
                demand.state,
                replace(later, utc=1008, monotonic=1908),
                policy,
                mode="stop",
                night=False,
                night_request=False,
                permitted=True,
            ).percentage,
            0,
        )

    def test_fake_weather_and_absent_tomorrow_outage_keep_provider_horizon_honest(self):
        tz = ZoneInfo("Europe/Kyiv")
        span = day_span(date(2026, 1, 5), tz)
        now = span.start + 100
        w = binding("weather", source="synthetic.weather")
        o = binding("outage", source="synthetic.outage")
        reg = replace(registry(), bindings=registry().bindings + (w, o))
        runtime, _ = harness(self, reg)
        weather = WeatherSeries(
            Forecast(now - 1, now, span, w.source_id),
            (
                WeatherPoint(now, Interval(-10, -8)),
                WeatherPoint(now + 3600, Interval(-5, -3)),
            ),
        )
        e = ProviderEvent("synthetic.weather1", w.entity, 1, now, weather)
        self.assertTrue(runtime.provider(e))
        self.assertFalse(runtime.provider(e))
        self.assertEqual(decode(encode(e)), e)
        self.assertEqual(runtime.client.weather(now + 1800, now), Interval(-7.5, -5.5))
        self.assertIsNone(runtime.client.weather(now + 4000, now))
        self.assertIsNone(runtime.client.weather(now, now + 11))
        schedule = OutageSchedule(
            Forecast(now - 1, now, span, o.source_id),
            "synthetic.region",
            "synthetic.queue",
            date(2026, 1, 5).isoformat(),
            (),
            False,
            False,
        )
        e = ProviderEvent("synthetic.outage1", o.entity, 1, now, schedule)
        runtime.provider(e)
        window = TimeWindow(start=now, end=now + 300)
        self.assertEqual(
            runtime.client.grid_forecast(
                window, now, "synthetic.region", "synthetic.queue", tz
            ),
            "unknown",
        )
        self.assertTrue(
            runtime.provider(
                replace(
                    e,
                    identity="synthetic.normal",
                    sequence=2,
                    forecast=replace(schedule, coverage_known=True),
                )
            )
        )
        self.assertEqual(
            runtime.client.grid_forecast(
                window, now, "synthetic.region", "synthetic.queue", tz
            ),
            "normal",
        )
        tomorrow = TimeWindow(start=span.end, end=span.end + 300)
        self.assertEqual(
            runtime.client.grid_forecast(
                tomorrow, now, "synthetic.region", "synthetic.queue", tz
            ),
            "unknown",
        )
        self.assertFalse(runtime.provider(e))  # older publication cannot replace newest
        emergency = replace(schedule, coverage_known=True, emergency=True)
        runtime.provider(
            replace(e, identity="synthetic.emergency", sequence=3, forecast=emergency)
        )
        self.assertEqual(
            runtime.client.grid_forecast(
                window, now, "synthetic.region", "synthetic.queue", tz
            ),
            "emergency",
        )
        runtime.provider(
            replace(
                e,
                identity="synthetic.scheduled",
                sequence=4,
                forecast=replace(schedule, coverage_known=True, outages=(window,)),
            )
        )
        self.assertEqual(
            runtime.client.grid_forecast(
                window, now, "synthetic.region", "synthetic.queue", tz
            ),
            "scheduled_off",
        )
        with self.assertRaises(ContractError):
            runtime.provider(replace(e, entity=w.entity))
        runtime.client.disconnect()
        self.assertIsNone(runtime.client.weather(now, now))
        self.assertEqual(
            runtime.client.grid_forecast(
                window, now, "synthetic.region", "synthetic.queue", tz
            ),
            "unknown",
        )

    def test_cursor_is_bound_to_archive_prefix_and_reads_pin_one_snapshot(self):
        a = EvidenceStore.create(temp(self))
        b = EvidenceStore.create(temp(self))
        for store in (a, b):
            store.origin(Origin("s", "c", 100, 0))
        for at in (110, 120, 130):
            a.power(replace(point(at), stream="s"))
            b.power(replace(point(at, 6), stream="s"))
        page = a.query("s", "PowerPoint", 100, 200, limit=1)
        with self.assertRaises(EvidenceConflict):
            b.query("s", "PowerPoint", 100, 200, limit=1, cursor=page.cursor)
        with a.read_snapshot() as con:
            head = a._head(con)
            a.power(replace(point(140), stream="s"))
            self.assertEqual(a._head(con), head)
        self.assertGreater(a.head()[0], head[0])

    def test_sensor_storm_reserves_manual_events_and_archives_all_raw_facts(self):
        runtime, _ = harness(self)
        clock = Clock(utc=100, monotonic=1000, boot_id=runtime.simulator.state.boot_id)
        room = runtime.client.registry.bindings[0]
        thermo = runtime.client.registry.bindings[2]
        for seq in range(1, 301):
            runtime.client.push(event(room, 100, 18, seq))
        runtime.client.push(
            event(thermo, 100, 19, 1, author="manual", observed_action=Action.HEAT)
        )
        runtime.drain_events(clock)
        self.assertTrue(runtime.simulator.state.manual_paused)
        while runtime.flush_evidence():
            pass
        self.assertEqual(runtime.client.raw_count, 301)
        # Raw facts survive control-queue coalescing; no false archive-complete receipt.
        self.assertEqual(runtime.evidence.head()[0], 301)
        self.assertEqual(runtime.status(runtime.operator, clock).archive_pending, 0)

    def test_reserved_source_queue_exhaustion_is_visible_and_fails_closed(self):
        runtime, _ = harness(self)
        b = runtime.client.registry.bindings[2]
        for seq in range(1, 129):
            runtime.client.push(event(b, 100, 19, seq, author="unknown"))
        with self.assertRaises(ContractError):
            runtime.client.push(event(b, 100, 19, 129, author="manual"))
        self.assertFalse(runtime.client.connected)
        self.assertIsNone(
            runtime.snapshot(
                Clock(utc=100, monotonic=1000, boot_id=runtime.simulator.state.boot_id)
            ).grid_actual
        )

    def test_admin_recovery_api_denies_reader_and_preview_does_not_write(self):
        from packages.offline.contracts import Principal, RecoveryRequest

        runtime, session = harness(self)
        runtime.evidence.origin(Origin("s", "c", 100, 0))
        slices = runtime.evidence.finalize("s", 200, as_of=200)
        backup = temp(self)
        digest = runtime.evidence.backup(backup)
        request = RecoveryRequest(
            "synthetic.admin-recovery",
            tuple(s.identity for s in slices),
            0.1,
            0,
            digest,
            "a" * 64,
        )
        reader = runtime.client.grant(Principal("synthetic.reader", ("read",), 1))
        with self.assertRaises(ContractError):
            runtime.recovery(request, "s", backup, reader, dry_run=False)
        head = runtime.evidence.head()
        preview = runtime.recovery(request, "s", backup, session, dry_run=True)
        self.assertEqual(runtime.evidence.head(), head)
        self.assertEqual(preview.total_after, 0.1)
        runtime.recovery(request, "s", backup, session, dry_run=False)
        self.assertEqual(runtime.evidence.summary("s").actual_total_kwh, 0.1)

    def test_planner_proposal_and_frozen_forecast_are_queued_then_archived_with_lineage(
        self,
    ):
        from packages.offline.codec import decode

        runtime, _ = harness(self)
        clock, proposal, request = planned(runtime, with_request=True)
        forecast = runtime.queue_forecast(
            proposal, request, "synthetic.cycle", clock.utc + 300, role="initial"
        )
        self.assertEqual(forecast.curve.source_issued, (request.weather.issue,))
        self.assertEqual(forecast.planned_kwh, proposal.energy_kwh)
        self.assertEqual(forecast.curve.model_revision, request.model.revision)
        runtime.flush_evidence()
        self.assertEqual(
            decode(runtime.evidence.get(forecast.identity).payload), forecast
        )
        self.assertEqual(
            decode(runtime.evidence.get(forecast.curve.plan_id).payload), proposal
        )
        with self.assertRaises(ContractError):
            runtime.queue_forecast(
                replace(proposal, trajectory=()),
                request,
                "cycle",
                clock.utc + 300,
                role="latest",
            )
