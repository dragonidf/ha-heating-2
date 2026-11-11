import tempfile
from pathlib import Path
from dataclasses import replace
import unittest
from packages.ha_native.health import HealthInputs, HealthPolicy
from packages.ha_native.backend import NativeBackend
from packages.ha_native.store import StoreError
from tests.wp2c_backend.test_clock import FakeTime
from tests.wp2c_backend.test_backend import fixture, observe


class NativeHealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='heating-wp2c-');self.addCleanup(self.tmp.cleanup)
        self.clock = FakeTime()
        self.evidence = HealthInputs(thermostat_qualified=True, thermostat_age_s=0, owner='synthetic.owner', plan_ok=True)
        self.backend = NativeBackend(Path(self.tmp.name), fixture(), enabled=True, clock=self.clock,
            health_policy=HealthPolicy(room_timeout_s=60, recovery_s=5, cold_grace_s=0), health_evidence=lambda: self.evidence)
        self.backend.open();self.addCleanup(self.backend.close)
        observe(self.backend)

    def test_native_projection_keeps_room_authority_and_ages_without_new_reports(self):
        room = self.backend.status(True)['room'].copy()
        self.evidence = replace(self.evidence, fireplace_qualified=True, fireplace_age_s=0)
        self.clock.advance(61)
        state = self.backend.status(True)
        self.assertEqual(state['room']['value'], room['value'])
        self.assertEqual(state['room']['observed'], room['observed'])
        health = state['system_health']
        self.assertEqual(len(health['components']), 6)
        self.assertEqual(health['components'][0]['status'], 'PROBLEM')
        self.assertEqual(health['components'][1]['status'], 'OK')
        # Electrical evidence expired as well: AUTO must never be proposed.
        self.assertNotEqual((health['intent'] or {}).get('mode'), 'AUTO')
        self.assertFalse(state['status']['physical_verified'])

    def test_stop_and_durable_health_alarm_survive_restart(self):
        self.clock.advance(61);self.backend.status(True);self.backend.flush_stop()
        body = self.backend.status(True)
        self.backend.stop_request(dict(version=[2,0],entry_id='synthetic-entry',boot_id=body['status']['boot_id'],
            generation=body['generation'],owner_epoch=body['status']['owner_epoch'],kind='pause',request_id='health-stop'),True)
        self.backend.status(True);self.backend.flush_stop();self.backend.reboot()
        state = self.backend.status(True)
        self.assertEqual(state['status']['mode'], 'MANUAL_PAUSE')
        self.assertTrue(state['health_memory']['operator_latched'])
        self.assertIsNone(state['system_health']['intent'])

    def test_new_heartbeat_is_not_temperature_change_or_substitute_room(self):
        from packages.contracts import Reading, Quality, QualityStatus, Provenance, SourceKind, Unit
        from packages.offline.contracts import SourceEvent
        old = self.backend.status(True)['room'].copy()
        self.clock.advance(61)
        reading = Reading(physical_id='synthetic.native.room', source_id='synthetic.native.room',
            value=old['value'], unit=Unit.CELSIUS, observed_at=old['observed'], received_at=self.clock.utc,
            quality=Quality(status=QualityStatus.VALID, age_s=61, reason='synthetic-heartbeat'),
            provenance=Provenance(kind=SourceKind.DIRECT, independent=True), evidence_ids=())
        self.backend.accept_source(SourceEvent('synthetic.heartbeat', 'synthetic.native.room', 1, self.clock.utc, reading))
        state = self.backend.status(True)
        self.assertEqual(state['system_health']['components'][0]['status'], 'WAITING')
        self.assertEqual(state['system_health']['components'][0]['age_s'], 0)
        # The heartbeat proves liveness, not a new qualified model observation.
        self.assertNotEqual(state['room']['quality'], 'valid')
        fresh = replace(reading, observed_at=self.clock.utc, quality=Quality(status=QualityStatus.VALID, age_s=0, reason='synthetic-report'))
        self.backend.accept_source(SourceEvent('synthetic.new-report', 'synthetic.native.room', 2, self.clock.utc, fresh))
        self.assertEqual(self.backend.status(True)['room']['value'], old['value'])

    def test_invalid_durable_memory_fails_closed_instead_of_clearing_alarm(self):
        self.backend.close()
        with self.backend.critical.transaction() as connection:
            stored = self.backend.critical.read_from(connection, 'snapshot')
            stored['health_memory'] = 'invalid-health-schema'
            self.backend.critical.write(connection, 'snapshot', stored)
        with self.assertRaises(StoreError):
            self.backend.open()
        self.assertFalse(self.backend._opened)

    def test_one_recovery_report_expires_before_dwell_without_bypassing_freshness(self):
        from packages.contracts import Reading, Quality, QualityStatus, Provenance, SourceKind, Unit
        from packages.offline.contracts import SourceEvent
        from tests.wp2c_meter.test_voltage import frame
        self.backend._health_policy = HealthPolicy(room_timeout_s=60, recovery_s=30, cold_grace_s=0)
        self.clock.advance(61)
        self.backend.accept_voltage(frame(self.clock.utc));self.backend.flush_stop()
        lost = self.backend.status(True)
        self.assertEqual(lost['system_health']['mode'], 'AUTO_PROPOSED')
        now = self.clock.utc
        reading = Reading(physical_id='synthetic.native.room', source_id='synthetic.native.room',
            value=21.8, unit=Unit.CELSIUS, observed_at=now, received_at=now,
            quality=Quality(status=QualityStatus.VALID, age_s=0, reason='synthetic-recovery'),
            provenance=Provenance(kind=SourceKind.DIRECT, independent=True), evidence_ids=())
        self.assertTrue(self.backend.accept_source(SourceEvent('synthetic.recover-once', 'synthetic.native.room', 1, now, reading)))
        self.backend.flush_stop()
        fresh = self.backend.status(True)
        self.assertEqual(fresh['system_health']['mode'], 'RECOVERING')
        self.clock.advance(30.1)
        # Keep only electrical evidence current; do not fabricate another room report.
        self.backend.accept_voltage(frame(self.clock.utc));self.backend.flush_stop()
        after = self.backend.status(True)
        self.assertEqual(after['room']['observed'], now)
        self.assertEqual(after['room']['quality'], 'stale')
        self.assertFalse(after['permitted'])
        self.assertIsNone(after['system_health']['intent'])
        self.assertIsNone(after['system_health']['proposal'])
        self.assertEqual(after['system_health']['mode'], 'RECOVERING')
        self.assertIsNone(after['health_memory']['recovery_since'])
        self.assertEqual(after['health_memory']['auto_owner'], 'synthetic.owner')

    def test_missing_reading_does_not_refresh_report_provenance(self):
        from packages.offline.contracts import SourceEvent
        before = self.backend._room_report
        self.clock.advance(1)
        self.assertFalse(self.backend.accept_source(SourceEvent('synthetic.missing-reading', 'synthetic.native.room', 1, self.clock.utc, None)))
        self.assertEqual(self.backend._room_report, before)
        self.assertNotEqual(self.backend.status(True)['room']['quality'], 'valid')
