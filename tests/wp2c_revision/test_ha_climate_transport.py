"""Focused tests of HA API transport using service/state doubles only."""
import asyncio
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from packages.ha_native.ha_climate_transport import ClimateOrder, LiveClimateTransport

NOW = datetime(2026, 11, 11, tzinfo=timezone.utc)


@dataclass
class State:
    state: str = "heat"
    attributes: dict | None = None
    last_reported: datetime = NOW

    def __post_init__(self):
        if self.attributes is None:
            self.attributes = dict(temperature=18., current_temperature=21.,
                                   min_temp=5., max_temp=35., target_temp_step=.5)


class States:
    def __init__(self):
        self.value = State()

    def get(self, entity_id):
        assert entity_id == "climate.test"
        return self.value


class Services:
    def __init__(self, states):
        self.states = states
        self.calls = []
        self.emit = True
        self.raise_error = False
        self.wait = False

    async def async_call(self, domain, service, service_data, *, blocking, context):
        self.calls.append((domain, service, service_data, blocking, context.user_id))
        if self.wait:
            await asyncio.Event().wait()
        if self.raise_error:
            raise RuntimeError("status unknown after send")
        if self.emit:
            self.states.value.attributes["temperature"] = service_data["temperature"]
            self.states.value.last_reported += timedelta(seconds=1)


class FakeHass:
    def __init__(self):
        self.states = States()
        self.services = Services(self.states)


def order(kind="HEAT", target=23, expected=18, upper=26, identity="example"):
    return ClimateOrder(identity, 5, target, expected, kind, upper if kind == "HEAT" else None)


class LiveClimateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.hass = FakeHass()
        self.allowed = True
        self.context = SimpleNamespace(user_id="test-actor")
        self.transport = LiveClimateTransport(self.hass, "climate.test", lambda o: self.allowed,
                                              enabled=True, timeout_s=.1, poll_s=.01)

    async def test_disabled_and_unauthorized_never_send(self):
        self.transport.enabled = False
        self.assertEqual((await self.transport.execute(order(), context=self.context)).status, "BLOCKED")
        self.transport.enabled = True
        self.assertEqual((await self.transport.execute(order(),
                         context=SimpleNamespace(user_id=None))).status, "BLOCKED")
        self.allowed = False
        self.assertEqual((await self.transport.execute(order(), context=self.context)).status, "BLOCKED")
        self.assertEqual(self.hass.services.calls, [])

    async def test_happy_path_only_ha_echo_no_physical_ack(self):
        r = await self.transport.execute(order(), context=self.context)
        self.assertEqual((r.status, r.physical_ack, r.contacts_open), ("HA_ECHO", False, None))
        self.assertEqual(self.hass.services.calls[0][:4],
                         ("climate", "set_temperature",
                          {"entity_id": "climate.test", "temperature": 23}, True))
        self.assertEqual((await self.transport.execute(order(expected=23),
                         context=self.context)).status, "ALREADY_OBSERVED")
        self.assertEqual(len(self.hass.services.calls), 1)

    async def test_auto_mode_is_not_changed_or_bypassed(self):
        self.hass.states.value.state = "auto"
        self.assertEqual((await self.transport.execute(order(), context=self.context)).status, "BLOCKED")
        self.assertFalse(self.hass.services.calls)

    async def test_invalid_capabilities_or_ceiling_cannot_send(self):
        for change in ("target_temp_step", "current_temperature", "temperature"):
            original = self.hass.states.value.attributes[change]
            self.hass.states.value.attributes[change] = 1 if change == "target_temp_step" else None
            self.assertEqual((await self.transport.execute(order(), context=self.context)).status, "BLOCKED")
            self.hass.states.value.attributes[change] = original
        with self.assertRaises(ValueError):
            order(target=23, upper=22)
        self.assertEqual((await self.transport.execute(order(expected=21),
                         context=self.context)).status, "BLOCKED")
        self.assertFalse(self.hass.services.calls)

    async def test_safe_withdrawal_must_be_below_local_temperature(self):
        self.assertEqual((await self.transport.execute(order("WITHDRAW", target=21),
                         context=self.context)).status, "BLOCKED")
        r = await self.transport.execute(order("WITHDRAW", target=18.5), context=self.context)
        self.assertEqual(r.status, "HA_ECHO")

    async def test_missing_echo_does_not_claim_success_or_retry(self):
        self.hass.services.emit = False
        r = await self.transport.execute(order(), context=self.context)
        self.assertEqual((r.status, r.physical_ack), ("UNCERTAIN", False))
        self.assertEqual(len(self.hass.services.calls), 1)

    async def test_service_failure_and_timeout_are_uncertain(self):
        self.hass.services.raise_error = True
        self.assertEqual((await self.transport.execute(order(), context=self.context)).status, "UNCERTAIN")
        self.hass.services.raise_error = False
        self.hass.services.wait = True
        self.assertEqual((await self.transport.execute(order(), context=self.context)).status, "UNCERTAIN")
        self.assertEqual(len(self.hass.services.calls), 2)

    async def test_owner_revoked_after_send_is_uncertain(self):
        self.hass.services.emit = False

        async def revoke(*args, **kwargs):
            self.allowed = False

        self.hass.services.async_call = revoke
        r = await self.transport.execute(order(), context=self.context)
        self.assertEqual(r.status, "UNCERTAIN")

    async def test_concurrent_dispatch_uses_single_fence(self):
        self.hass.services.wait = True
        first = asyncio.create_task(self.transport.execute(order(), context=self.context))
        await asyncio.sleep(.01)
        self.assertEqual((await self.transport.execute(order(identity="other"),
                         context=self.context)).status, "BLOCKED")
        self.assertEqual((await first).status, "UNCERTAIN")
        self.assertEqual(len(self.hass.services.calls), 1)


if __name__ == "__main__":
    unittest.main()
