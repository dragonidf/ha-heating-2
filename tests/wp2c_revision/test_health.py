"""Bounded synthetic #27 proposals: no HA writes or device confirmations."""
from dataclasses import asdict, replace
import unittest
from packages.ha_native.health import HealthInputs, HealthMemory, HealthPolicy, project_health


class HealthTests(unittest.TestCase):
    policy = HealthPolicy(room_timeout_s=10800, recovery_s=30, cold_grace_s=0)

    def inputs(self, **extra):
        return replace(HealthInputs(room_age_s=10, room_report_verified=True, room_valid=True,
            room_report_id='synthetic.new-report', electrical_eligible=True,
            thermostat_qualified=True, thermostat_age_s=1, clock_ok=True,
            persistence_ok=True, plan_ok=True, owner='synthetic.owner'), **extra)

    def step(self, i, at=100, memory=None, boot='synthetic.boot'):
        return project_health(i, now=at, mono=at, boot=boot, policy=self.policy, memory=memory or HealthMemory())

    def lost(self, **extra):
        return self.inputs(room_age_s=10801, room_valid=False, room_report_id='synthetic.old-report', **extra)

    def test_confirmed_room_loss_proposes_owned_auto_once_without_program_write(self):
        view, memory = self.step(self.lost())
        self.assertEqual(view['intent']['mode'], 'AUTO')
        self.assertTrue(view['intent']['preserve_weekly_program'])
        self.assertEqual(view['intent']['stage'], 'proposed')
        self.assertFalse(view['intent']['physical_authority'])
        repeated, _ = self.step(self.lost(), 101, memory)
        self.assertIsNone(repeated['intent'])
        self.assertIsNone(repeated['notification'])

    def test_loss_with_voltage_or_kws_unknown_never_auto(self):
        for fault in (False, True):
            view, _ = self.step(self.lost(electrical_eligible=False, electrical_fault=fault))
            self.assertEqual(view['intent']['action'], 'cannot_confirm_withdrawal')
            self.assertNotIn('mode', view['intent'])
            self.assertTrue(any(c['status'] == 'PROBLEM' for c in view['components']))
            self.assertEqual(view['components'][-1]['status'], 'PROBLEM')
        unsafe = {'action': 'withdraw_demand', 'mode': 'AUTO', 'physical_authority': False}
        view, _ = self.step(self.lost(electrical_eligible=False, withdrawal=unsafe))
        self.assertNotEqual(view['intent'].get('mode'), 'AUTO')
        safe = {'action': 'withdraw_demand', 'mode': 'HEAT', 'setpoint_c': 18, 'physical_authority': False}
        view, _ = self.step(self.lost(electrical_eligible=False, withdrawal=safe))
        self.assertEqual(view['intent']['mode'], 'HEAT')

    def test_single_fresh_verified_report_then_timer_recovers_without_two_reports(self):
        _, m = self.step(self.lost())
        recovering, m = self.step(self.inputs(), 101, m)
        self.assertIsNone(recovering['intent'])
        pending, _ = self.step(self.inputs(), 130, m)
        self.assertIsNone(pending['intent'])
        recovered, m = self.step(self.inputs(), 131, m)
        self.assertEqual(recovered['intent']['mode'], 'HEAT')
        self.assertIsNotNone(recovered['notification'])
        self.assertIsNone(self.step(self.inputs(), 132, m)[0]['intent'])

    def test_stop_operator_and_revoked_owner_latch_survive_restart(self):
        for change in ({'manual_stop': True}, {'operator_changed_mode': True}, {'owner': None}):
            _, m = self.step(self.lost())
            blocked, m = self.step(self.inputs(**change), 101, m)
            self.assertIsNone(blocked['intent'])
            record = asdict(m);record['transitions'] = {k:list(v) for k,v in m.transitions.items()}
            restored = HealthMemory.from_record(record)
            after, _ = self.step(self.inputs(), 1, restored, 'synthetic.reboot')
            self.assertIsNone(after['intent'])
            self.assertEqual(after['mode'], 'BLOCKED')

    def test_restart_preserves_auto_proposal_but_restarts_recovery_dwell(self):
        _, m = self.step(self.lost())
        _, m = self.step(self.inputs(), 101, m)
        record = asdict(m);record['transitions'] = {k:list(v) for k,v in m.transitions.items()}
        m = HealthMemory.from_record(record)
        pending, m = self.step(self.inputs(), 1, m, 'synthetic.reboot')
        self.assertIsNone(pending['intent'])
        self.assertEqual(m.auto_owner, 'synthetic.owner')
        self.assertEqual(self.step(self.inputs(), 31, m, 'synthetic.reboot')[0]['intent']['mode'], 'HEAT')

    def test_same_temperature_is_not_source_loss_and_unproven_age_is_unknown(self):
        for i in (self.inputs(room_age_s=3600), self.inputs(room_report_verified=False),
                  self.inputs(room_age_s=None), self.inputs(room_valid=False, room_age_s=4000)):
            view, _ = self.step(i)
            self.assertIsNone(view['intent'])
            self.assertNotEqual(view['components'][0]['status'], 'PROBLEM')
        view, _ = self.step(self.inputs(room_valid=False, room_age_s=15000, room_report_verified=False))
        self.assertEqual(view['components'][0]['status'], 'WAITING')

    def test_bad_phase_plan_one_shot_or_thermostat_blocks_recovery(self):
        for change in ({'electrical_eligible': False}, {'plan_ok': False}, {'one_shot_blocked': True},
                       {'thermostat_qualified': False}, {'thermostat_age_s': 121}):
            _, m = self.step(self.lost())
            view, m = self.step(self.inputs(**change), 101, m)
            self.assertNotEqual((view['intent'] or {}).get('action'), 'proposed_recovery')
            _, m = self.step(self.inputs(), 102, m)
            self.assertIsNone(self.step(self.inputs(), 131, m)[0]['intent'])

    def test_fireplace_and_thermostat_never_substitute_for_room(self):
        view, _ = self.step(self.inputs(room_valid=False, room_age_s=None,
            fireplace_qualified=True, fireplace_age_s=1))
        self.assertEqual(view['components'][0]['status'], 'WAITING')
        self.assertEqual(view['components'][1]['status'], 'OK')
        self.assertIsNone(view['intent'])

    def test_cold_grace_and_cooldown_and_clock_fault(self):
        p = replace(self.policy, cold_grace_s=60)
        view, _ = project_health(self.lost(), now=100, mono=100, boot='synthetic.boot', policy=p, memory=HealthMemory())
        self.assertIsNone(view['intent'])
        _, m = self.step(self.lost())
        view, _ = self.step(self.inputs(), 99, m)
        self.assertIsNone(view['intent'])
        self.assertEqual(view['components'][-1]['status'], 'PROBLEM')

    def test_recovery_notification_waits_for_cooldown_instead_of_disappearing(self):
        policy = replace(self.policy, recovery_s=0)
        first, memory = project_health(self.lost(), now=100, mono=100, boot='synthetic.boot', policy=policy, memory=HealthMemory())
        self.assertIsNotNone(first['notification'])
        recovered, memory = project_health(self.inputs(), now=101, mono=101, boot='synthetic.boot', policy=policy, memory=memory)
        self.assertEqual(recovered['intent']['mode'], 'HEAT')
        self.assertIsNone(recovered['notification'])
        notified, memory = project_health(self.inputs(), now=130, mono=130, boot='synthetic.boot', policy=policy, memory=memory)
        self.assertIn('повернення', notified['notification'])
        self.assertIsNone(project_health(self.inputs(), now=131, mono=131, boot='synthetic.boot', policy=policy, memory=memory)[0]['notification'])

    def test_proposal_identity_is_stable_per_episode_but_unique_next_loss(self):
        first, memory = self.step(self.lost())
        self.assertIsNone(self.step(self.lost(), 101, memory)[0]['intent'])
        _, memory = self.step(self.inputs(), 102, memory)
        recovered, memory = self.step(self.inputs(), 132, memory)
        self.assertEqual(recovered['intent']['mode'], 'HEAT')
        second, _ = self.step(self.lost(), 133, memory)
        self.assertEqual(second['intent']['mode'], 'AUTO')
        self.assertNotEqual(first['intent']['id'], second['intent']['id'])

    def test_durable_proposal_is_observable_without_reissuing_or_unsafe_replay(self):
        first, memory = self.step(self.lost())
        record = asdict(memory);record['transitions'] = {k:list(v) for k,v in memory.transitions.items()}
        restored = HealthMemory.from_record(record)
        repeated, memory = self.step(self.lost(), 101, restored)
        self.assertIsNone(repeated['intent'])
        self.assertEqual(repeated['proposal']['id'], first['intent']['id'])
        blocked, _ = self.step(self.inputs(manual_stop=True), 102, memory)
        self.assertIsNone(blocked['proposal'])
        electrical, _ = self.step(self.lost(electrical_eligible=False), 102, memory)
        self.assertNotEqual((electrical['proposal'] or {}).get('mode'), 'AUTO')
