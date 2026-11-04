#!/usr/bin/env python3
"""Runs only inside the newly created network-none HA container."""

from __future__ import annotations

import asyncio
from importlib.metadata import version
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys
from time import perf_counter

import aiohttp

BASE = "http://127.0.0.1:8123"
SECRETS = Path("/config/.wp2c-secrets.json")


def guard() -> None:
    assert os.environ.get("HEATING_AI_TEST_SANDBOX") == "1"
    assert Path("/config/.heating-ai-isolated-test").read_text() == "synthetic-only\n"
    assert version("homeassistant") == "2026.10.4"


def save_secrets(value: dict) -> None:
    SECRETS.write_text(json.dumps(value))
    SECRETS.chmod(0o600)


async def ready(session: aiohttp.ClientSession) -> None:
    for _ in range(120):
        try:
            async with session.get(BASE + "/", timeout=aiohttp.ClientTimeout(total=2)) as response:
                if response.status in (200, 302):
                    return
        except (aiohttp.ClientError, TimeoutError):
            pass
        await asyncio.sleep(1)
    raise AssertionError("Pinned isolated HA did not start within 120 seconds")


async def http(session: aiohttp.ClientSession, method: str, path: str, data: dict | None = None, token: str | None = None) -> tuple[int, object]:
    headers = {"Authorization": "Bearer " + token} if token else {}
    async with session.request(method, BASE + path, json=data, headers=headers) as response:
        try:
            value = await response.json()
        except (aiohttp.ContentTypeError, json.JSONDecodeError):
            value = await response.text()
        return response.status, value


async def token_exchange(session: aiohttp.ClientSession, code: str) -> dict:
    async with session.post(BASE + "/auth/token", data={"grant_type": "authorization_code", "code": code, "client_id": BASE + "/"}) as response:
        assert response.status == 200, "Synthetic authorization code exchange failed"
        return await response.json()


async def login(session: aiohttp.ClientSession, username: str, password: str) -> dict:
    status, flow = await http(session, "POST", "/auth/login_flow", {"client_id": BASE + "/", "handler": ["homeassistant", None], "redirect_uri": BASE + "/"})
    assert status == 200 and isinstance(flow, dict), "Native login flow unavailable"
    status, result = await http(session, "POST", "/auth/login_flow/" + flow["flow_id"], {"client_id": BASE + "/", "username": username, "password": password})
    assert status == 200 and isinstance(result, dict) and result["type"] == "create_entry", "Synthetic HA login failed"
    return await token_exchange(session, result["result"])


class WS:
    def __init__(self, connection: aiohttp.ClientWebSocketResponse) -> None:
        self.connection = connection
        self.sequence = 0

    @classmethod
    async def connect(cls, session: aiohttp.ClientSession, token: str) -> WS:
        connection = await session.ws_connect(BASE + "/api/websocket")
        assert (await connection.receive_json())["type"] == "auth_required"
        await connection.send_json({"type": "auth", "access_token": token})
        assert (await connection.receive_json())["type"] == "auth_ok", "Synthetic WS login failed"
        return cls(connection)

    async def request(self, operation: str, **fields: object) -> dict:
        self.sequence += 1
        await self.connection.send_json({"id": self.sequence, "type": operation, **fields})
        while True:
            response = await self.connection.receive_json(timeout=15)
            if response.get("id") == self.sequence and response.get("type") == "result":
                return response

    async def ok(self, operation: str, **fields: object) -> object:
        response = await self.request(operation, **fields)
        assert response["success"], f"Native operation {operation} failed: {response.get('error', {}).get('code')}"
        return response["result"]


async def bootstrap() -> dict:
    secrets = json.loads(SECRETS.read_text())
    async with aiohttp.ClientSession(trust_env=False) as session:
        await ready(session)
        if "admin_token" not in secrets:
            status, result = await http(session, "POST", "/api/onboarding/users", {
                "name": "Synthetic Administrator", "username": secrets["admin_user"],
                "password": secrets["admin_password"], "client_id": BASE + "/", "language": "en",
            })
            assert status == 200 and isinstance(result, dict), "Native synthetic user onboarding failed"
            secrets["admin_token"] = (await token_exchange(session, result["auth_code"]))["access_token"]
            save_secrets(secrets)
        ws = await WS.connect(session, secrets["admin_token"])
        if "reader_token" not in secrets:
            user = await ws.ok("config/auth/create", name="Synthetic Read Only", group_ids=["system-read-only"], local_only=True)
            assert isinstance(user, dict)
            await ws.ok("config/auth_provider/homeassistant/create", user_id=user["user"]["id"], username=secrets["reader_user"], password=secrets["reader_password"])
            secrets["reader_token"] = (await login(session, secrets["reader_user"], secrets["reader_password"]))["access_token"]
            save_secrets(secrets)
        config = await ws.ok("get_config")
        assert isinstance(config, dict) and config["version"] == "2026.10.4"
        status, _ = await http(session, "GET", "/api/config")
        assert status == 401, "Anonymous API must not authenticate"
        async with session.ws_connect(BASE + "/api/websocket") as unauth:
            await unauth.receive_json()
            await unauth.send_json({"type": "auth", "access_token": "synthetic-invalid"})
            assert (await unauth.receive_json())["type"] == "auth_invalid"
        await ws.connection.close()
    return {"qualification": "PASS_ISOLATED", "checks": ["actual_ha_startup", "native_owner_onboarding", "native_authorization_code_exchange", "native_read_only_identity", "native_login_flow", "anonymous_api_denied", "invalid_ws_auth_denied"], "count": 7}


async def isolation() -> dict:
    assert sqlite3.sqlite_version_info >= (3, 51, 3)
    assert version("home-assistant-frontend") == "20260930.5"
    database = sqlite3.connect(":memory:")
    try:
        sqlite_source_id = database.execute("SELECT sqlite_source_id()").fetchone()[0]
    finally:
        database.close()
    secrets = json.loads(SECRETS.read_text())
    async with aiohttp.ClientSession(trust_env=False) as session:
        ws = await WS.connect(session, secrets["admin_token"])
        config = await ws.ok("get_config")
        assert isinstance(config, dict)
        components = sorted(config["components"])
        forbidden = {"default_config", "zeroconf", "ssdp", "dhcp", "bluetooth", "cloud", "mqtt", "zha", "tuya", "met", "google_translate", "radio_browser"}
        assert not forbidden.intersection(components), "Discovery or external integration was loaded"
        await ws.connection.close()
    route_lines = Path("/proc/net/route").read_text().splitlines()
    assert len(route_lines) == 1, "network-none namespace must have no IPv4 routes"
    probes = []
    for host, port in (("192.0.2.1", 8123), ("198.51.100.1", 1883), ("203.0.113.1", 502), ("127.0.0.1", 9)):
        with socket.socket() as probe:
            probe.settimeout(0.2)
            code = probe.connect_ex((host, port))
            assert code != 0, "Negative isolation transport unexpectedly connected"
            probes.append({"destination": host, "port": port, "errno": code, "connected": False})
    listeners = []
    for line in Path("/proc/net/tcp").read_text().splitlines()[1:]:
        fields = line.split()
        if fields[3] == "0A":
            listeners.append(fields[1])
    assert listeners == ["0100007F:1FBB"], f"Unexpected listener: {listeners}"
    return {"ha_version": version("homeassistant"), "frontend_version": version("home-assistant-frontend"), "python_version": sys.version.split()[0], "sqlite_version": sqlite3.sqlite_version, "sqlite_source_id": sqlite_source_id, "sqlite_library_sha256": sha256(Path("/opt/wp2c/lib/libsqlite3.so.0").read_bytes()).hexdigest(), "components": components, "ipv4_routes": [], "tcp_listeners": listeners, "negative_transport_probes": probes, "count": 8}


async def integration(restart: bool = False) -> dict:
    secrets = json.loads(SECRETS.read_text())
    completed: list[str] = []
    async with aiohttp.ClientSession(trust_env=False) as session:
        await ready(session)
        admin = await WS.connect(session, secrets["admin_token"])
        reader = await WS.connect(session, secrets["reader_token"])
        common: dict = {}

        async def read(operation: str, who: WS = admin, **extra: object) -> dict:
            result = await who.ok("heating_ai/" + operation, **common, **extra)
            assert isinstance(result, dict)
            return result

        async def wait_loaded() -> dict:
            for _ in range(60):
                response = await admin.request("heating_ai/status", **common)
                if response.get("success"):
                    return response["result"]
                await asyncio.sleep(0.2)
            raise AssertionError("Native config entry did not load")

        async def mutate(operation: str, who: WS = admin, **extra: object) -> dict:
            state = await read("status")
            return await read(operation, who, boot_id=state["status"]["boot_id"], generation=state["generation"], owner_epoch=state["status"]["owner_epoch"], **extra)

        async def options(enabled: bool, extra: dict | None = None) -> None:
            code, flow = await http(session, "POST", "/api/config/config_entries/options/flow", {"handler": secrets["entry_id"]}, secrets["admin_token"])
            assert code == 200 and isinstance(flow, dict)
            code, result = await http(session, "POST", "/api/config/config_entries/options/flow/" + flow["flow_id"], {"simulation_enabled": enabled} | (extra or {}), secrets["admin_token"])
            assert code == 200 and isinstance(result, dict) and result["type"] == "create_entry", "Native options flow failed"
            await asyncio.sleep(0.3)
            await wait_loaded()

        async def create_entry(stage: str) -> str:
            code, flow = await http(session, "POST", "/api/config/config_entries/flow", {"handler": "heating_ai", "show_advanced_options": True}, secrets["admin_token"])
            assert code == 200 and isinstance(flow, dict) and flow["type"] == "form", "Native integration user flow missing"
            completed.append(stage + "_native_config_flow_form")
            code, invalid = await http(session, "POST", "/api/config/config_entries/flow/" + flow["flow_id"], {"confirm_isolated": False}, secrets["admin_token"])
            assert code == 200 and isinstance(invalid, dict) and invalid["type"] == "form"
            completed.append(stage + "_native_config_flow_requires_explicit_confirmation")
            code, result = await http(session, "POST", "/api/config/config_entries/flow/" + flow["flow_id"], {"confirm_isolated": True}, secrets["admin_token"])
            assert code == 200 and isinstance(result, dict) and result["type"] == "create_entry", "Native config entry creation failed"
            return result["result"]["entry_id"]

        if not restart:
            if "entry_id" in secrets:
                code, _ = await http(session, "DELETE", "/api/config/config_entries/entry/" + secrets["entry_id"], token=secrets["admin_token"])
                assert code == 200, "Prior disposable native entry could not be removed"
            first_entry = await create_entry("install")
            common.update(entry_id=first_entry, version=[2, 0])
            await wait_loaded()
            code, _ = await http(session, "DELETE", "/api/config/config_entries/entry/" + first_entry, token=secrets["admin_token"])
            assert code == 200
            response = await admin.request("heating_ai/status", **common)
            assert response["success"] is False and "heating-ai" not in await admin.ok("get_panels")
            registry = await admin.ok("config/entity_registry/list")
            assert not any(row["config_entry_id"] == first_entry for row in registry)
            completed.append("native_uninstall_removes_entry_panel_transport_and_registry")
            secrets["entry_id"] = await create_entry("reinstall")
            save_secrets(secrets)
            completed.append("native_reinstall_new_disposable_entry")
        common.update(entry_id=secrets["entry_id"], version=[2, 0])
        initial = await wait_loaded()
        if restart:
            expected = secrets["restart_expected"]
            assert initial["status"]["boot_id"] != expected["boot_id"]
            assert initial["generation"] > expected["generation"]
            assert initial["status"]["owner_epoch"] > expected["owner_epoch"]
            assert initial["status"]["mode"] == "MANUAL_PAUSE"
            assert initial["status"]["desired"] == "stop_demand" and initial["status"]["actual"] is None
            assert (await read("settings/get"))["values"] == expected["settings"]
            assert initial["oneShot"]["state"] in ("unknown_outcome", "consumed")
            completed.extend(["restart_new_boot_generation_and_owner_epoch", "restart_preserves_manual_stop", "restart_never_repeats_heat", "restart_settings_readback", "restart_oneshot_no_replay"])
            await admin.connection.close()
            await reader.connection.close()
            return {"qualification": "PASS_ISOLATED", "checks": completed, "count": len(completed)}
        else:
            assert initial["permitted"] is False and initial["status"]["physical_verified"] is False
            completed.append("disabled_by_default_and_no_physical_authority")
        code, duplicate = await http(session, "POST", "/api/config/config_entries/flow", {"handler": "heating_ai"}, secrets["admin_token"])
        assert code == 200 and isinstance(duplicate, dict) and duplicate["type"] == "abort"
        completed.append("native_duplicate_config_entry_cannot_create_second_owner")
        overview = await read("overview")
        assert overview["physical_authority"] is False and len(overview["gates"]) == 8
        completed.append("g1_gates_and_physical_authority_stay_blocked")
        for bad in ({"version": [99, 0]}, {"entry_id": "synthetic-foreign"}, {"admin": True}, {"service": "arbitrary"}):
            response = await admin.request("heating_ai/status", **(common | bad))
            assert response["success"] is False
        completed.append("invalid_version_entry_permission_and_service_flags_denied")
        response = await reader.request("heating_ai/diagnostics", **common)
        assert response["success"] is False
        assert (await read("status", reader))["permitted"] is False
        completed.append("native_read_only_identity_permissions")
        registry = await admin.ok("config/entity_registry/list")
        rows = [row for row in registry if row["config_entry_id"] == secrets["entry_id"]]
        assert len(rows) == 3 and all(row["disabled_by"] == "integration" for row in rows)
        completed.append("three_native_registry_sensors_disabled_by_default")
        panels = await admin.ok("get_panels")
        assert "heating-ai" in panels and panels["heating-ai"]["config"]["entry_id"] == secrets["entry_id"]
        code, page = await http(session, "GET", "/heating-ai")
        assert code == 200 and isinstance(page, str) and "home-assistant" in page
        code, asset = await http(session, "GET", "/heating_ai/assets/panel.js")
        assert code == 200 and isinstance(asset, str) and len(asset) > 1000
        completed.extend(["native_panel_registration_and_http_shell", "native_packaged_panel_asset"])
        await options(True)
        empty = await read("status")
        assert empty["permitted"] is False and empty["room"]["value"] is None and empty["room"]["quality"] == "missing"
        assert (await mutate("control", kind="arm", request_id="native-no-input"))["status"] == "denied"
        completed.append("native_enabled_reload_requires_new_qualified_input")
        completed.append("native_options_enable_and_reload")

        # Use the accepted typed codec, then send the envelope through actual HA auth/event APIs.
        sys.path.insert(0, "/config")
        from custom_components.heating_ai.core.contracts import Reading, Quality, QualityStatus, Provenance, SourceKind, Unit
        from custom_components.heating_ai.core.offline.contracts import SourceEvent
        from custom_components.heating_ai.core.offline.codec import encode

        async def sample(sequence: int, *, at: float | None = None, value: float = 0) -> None:
            state = await read("status")
            now = state["now"] if at is None else at
            reading = Reading(physical_id="synthetic.native.room", source_id="synthetic.native.room", value=value, unit=Unit.CELSIUS, observed_at=now, received_at=now, quality=Quality(status=QualityStatus.VALID, age_s=0, reason="synthetic"), provenance=Provenance(kind=SourceKind.DIRECT, independent=True), evidence_ids=())
            envelope = json.loads(encode(SourceEvent("native-" + str(sequence), "synthetic.native.room", sequence, now, reading)))
            await admin.ok("fire_event", event_type="heating_ai_synthetic_sample", event_data={"entry_id": secrets["entry_id"], "envelope": envelope})
            await asyncio.sleep(0.1)

        await options(True, {"freshness_s": 120, "meter_source_id": "synthetic.future.boiler"})
        await options(False)
        await options(True)
        binding = (await read("diagnostics"))["meter_binding"]
        assert binding["source_id"] == "synthetic.future.boiler" and binding["physical_authority"] is False and binding["bound"] is False
        completed.append("native_partial_options_preserve_unverified_future_meter_selection")
        await sample(0, at=(await read("status"))["now"] - 60)
        assert (await read("status"))["permitted"] is True
        completed.append("native_partial_options_preserve_authoritative_source_age")
        await options(True, {"freshness_s": 30, "meter_source_id": ""})
        await sample(1)
        state = await read("status")
        assert state["room"]["value"] == 0 and state["room"]["quality"] == "valid"
        assert state["status"]["physical_verified"] is False
        completed.append("native_authenticated_synthetic_source_zero_is_valid")
        generation = state["generation"]
        await sample(1)
        assert (await read("status"))["generation"] == generation
        await admin.ok("fire_event", event_type="heating_ai_synthetic_sample", event_data={"entry_id": secrets["entry_id"], "envelope": {"invalid": True}})
        await asyncio.sleep(0.1)
        invalid_state = await read("status")
        assert invalid_state["room"]["quality"] == "missing" and invalid_state["status"]["mode"] in ("SAFE_HOLD", "MANUAL_PAUSE")
        assert invalid_state["permitted"] is False
        await sample(2, at=state["now"] - 100)
        assert (await read("status"))["permitted"] is False
        await sample(3)
        completed.extend(["native_duplicate_source_ignored", "native_invalid_source_fails_closed", "native_stale_source_fails_closed"])
        denied = await mutate("control", reader, kind="arm", request_id="native-reader-arm")
        assert denied["status"] == "denied"
        completed.append("native_read_only_user_cannot_mutate")
        settings = await read("settings/get")
        values = settings["values"] | {"day": 22 if settings["values"]["day"] != 22 else 23}
        before = await read("status")
        body = common | {"boot_id": before["status"]["boot_id"], "generation": before["generation"], "owner_epoch": before["status"]["owner_epoch"], "request_id": "native-save-" + str(settings["revision"]), "expected_revision": settings["revision"], "values": values}
        receipt = await admin.ok("heating_ai/settings/save", **body)
        assert receipt["status"] == "saved" and (await read("settings/get"))["values"] == values
        assert await admin.ok("heating_ai/settings/save", **body) == receipt
        conflict = await admin.ok("heating_ai/settings/save", **(body | {"values": values | {"fan": 71}}))
        assert conflict["status"] == "conflict"
        completed.extend(["native_durable_settings_cas_and_readback", "native_idempotent_retry", "native_request_body_conflict"])
        frozen = json.dumps((await read("overview"))["original"], sort_keys=True)
        assert frozen != "null"
        for index, kind in enumerate(("train", "promote", "freeze", "rollback")):
            result = await mutate("model", kind=kind, request_id="native-model-" + str(index))
            assert isinstance(result["reason"], str) and isinstance(result["model"], dict)
        completed.append("native_authenticated_model_actions_use_backend")
        assert json.dumps((await read("overview"))["original"], sort_keys=True) == frozen
        completed.append("native_nonempty_original_unchanged_through_model_actions")
        invalid = await mutate("settings/save", request_id="native-invalid-settings", expected_revision=receipt["revision"], values=values | {"day": 99})
        assert invalid["status"] == "denied"
        response = await admin.request("heating_ai/control", **common, boot_id="synthetic-old-boot", generation=1, owner_epoch=state["status"]["owner_epoch"], kind="arm")
        assert response["success"] is False
        completed.extend(["native_invalid_settings_denied", "native_stale_boot_denied"])
        history = await read("history", start=state["now"] - 86400, end=state["now"], cursor=None, limit=128)
        assert len(history["rows"]) <= 128 and len(json.dumps(history).encode()) <= 65536
        assert isinstance(await admin.ok("heating_ai/energy", **common), list)
        completed.append("native_bounded_history_and_independent_energy")
        subscription = await WS.connect(session, secrets["admin_token"])
        await subscription.ok("heating_ai/subscribe", **common)
        event = await subscription.connection.receive_json(timeout=5)
        assert event["type"] == "event" and event["event"]["status"]["physical_verified"] is False
        await subscription.ok("unsubscribe_events", subscription=1)
        await subscription.connection.close()
        completed.append("native_subscription_initial_snapshot_and_unsubscribe")
        old_boot = (await read("status"))["status"]["boot_id"]
        code, _ = await http(session, "POST", "/api/config/config_entries/entry/" + secrets["entry_id"] + "/reload", {}, secrets["admin_token"])
        assert code == 200
        assert (await wait_loaded())["status"]["boot_id"] != old_boot
        completed.append("native_reload_refreshes_boot")
        await admin.ok("config_entries/disable", entry_id=secrets["entry_id"], disabled_by="user")
        response = await admin.request("heating_ai/status", **common)
        assert response["success"] is False
        assert "heating-ai" not in await admin.ok("get_panels")
        completed.append("native_unload_removes_transport_and_panel")
        await admin.ok("config_entries/disable", entry_id=secrets["entry_id"], disabled_by=None)
        await wait_loaded()
        completed.append("native_reenable_reloads_entry")
        # These are only this entry's newly generated stores; never HA Recorder or private data.
        store_root = Path("/tmp") / ("heating-wp2c-" + secrets["entry_id"])
        critical = store_root / "critical.sqlite3"
        await admin.ok("config_entries/disable", entry_id=secrets["entry_id"], disabled_by="user")
        with sqlite3.connect(critical) as database:
            database.execute("PRAGMA user_version=1")
        await admin.ok("config_entries/disable", entry_id=secrets["entry_id"], disabled_by=None)
        await wait_loaded()
        with sqlite3.connect(critical) as database:
            assert database.execute("PRAGMA user_version").fetchone()[0] == 2
        assert critical.with_suffix(".migration.sqlite3").is_file()
        assert (await read("settings/get"))["values"] == values
        completed.append("native_entry_reloads_and_migrates_synthetic_sqlite_with_backup")
        await admin.ok("config_entries/disable", entry_id=secrets["entry_id"], disabled_by="user")
        with sqlite3.connect(critical) as database:
            database.execute("PRAGMA user_version=99")
        try:
            await admin.ok("config_entries/disable", entry_id=secrets["entry_id"], disabled_by=None)
            response = await admin.request("heating_ai/status", **common)
            assert response["success"] is False
            assert "heating-ai" not in await admin.ok("get_panels")
            completed.append("native_startup_schema_failure_has_no_transport_or_panel")
        finally:
            with sqlite3.connect(critical) as database:
                database.execute("PRAGMA user_version=2")
        code, _ = await http(session, "POST", "/api/config/config_entries/entry/" + secrets["entry_id"] + "/reload", {}, secrets["admin_token"])
        assert code == 200
        await wait_loaded()
        completed.append("native_synthetic_startup_recovery")
        await sample(1)
        lock = sqlite3.connect(critical, timeout=0, isolation_level=None)
        lock.execute("BEGIN IMMEDIATE")
        try:
            started = perf_counter()
            result = await mutate("control", kind="pause", request_id="native-stop-locked")
            stop_ms = (perf_counter() - started) * 1000
            assert result["status"] == "accepted_fake" and stop_ms < 500
            assert (await read("status"))["status"]["mode"] == "MANUAL_PAUSE"
            await asyncio.sleep(0.1)
        finally:
            lock.rollback()
            lock.close()
        await mutate("control", kind="pause", request_id="native-stop-reconcile")
        await asyncio.sleep(0.2)
        completed.append("native_stop_memory_first_while_critical_sqlite_locked")
        await mutate("control", kind="resume", request_id="native-resume-before-registry")
        registry_row = rows[0]
        await admin.ok("config/entity_registry/update", entity_id=registry_row["entity_id"], name="Synthetic lifecycle rename")
        await asyncio.sleep(0.1)
        assert (await read("status"))["permitted"] is False
        completed.append("native_registry_update_invalidates_source")
        await sample(2)
        await admin.ok("config/entity_registry/remove", entity_id=registry_row["entity_id"])
        await asyncio.sleep(0.1)
        assert (await read("status"))["permitted"] is False
        completed.append("native_registry_remove_invalidates_source")
        await sample(3)
        assert (await mutate("control", kind="arm", request_id="native-arm-restart"))["status"] == "accepted_fake"
        assert (await mutate("control", kind="pause", request_id="native-pause-restart"))["status"] == "accepted_fake"
        await asyncio.sleep(0.2)
        state = await read("status")
        secrets["restart_expected"] = {"boot_id": state["status"]["boot_id"], "generation": state["generation"], "owner_epoch": state["status"]["owner_epoch"], "settings": (await read("settings/get"))["values"]}
        save_secrets(secrets)
        completed.append("native_manual_stop_and_oneshot_restart_fixture")
        await admin.connection.close()
        await reader.connection.close()
    return {"qualification": "PASS_ISOLATED", "checks": completed, "count": len(completed), "stop_locked_sqlite_ms": round(stop_ms, 3)}


async def migration() -> dict:
    secrets = json.loads(SECRETS.read_text())
    completed = []
    async with aiohttp.ClientSession(trust_env=False) as session:
        await ready(session)
        admin = await WS.connect(session, secrets["admin_token"])
        common = {"entry_id": secrets["entry_id"], "version": [2, 0]}
        for _ in range(120):
            response = await admin.request("heating_ai/status", **common)
            if response["success"]:
                state = response["result"]
                break
            await asyncio.sleep(0.2)
        else:
            raise AssertionError("Migrated native config entry did not load")
        overview = await admin.ok("heating_ai/overview", **common)
        assert overview["enabled"] is False and state["permitted"] is False
        assert state["status"]["physical_verified"] is False
        completed.append("actual_config_entry_v1_minor0_migration_disables_simulation")
        for _ in range(60):
            store = json.loads(Path("/config/.storage/core.config_entries").read_text())
            entry = next(row for row in store["data"]["entries"] if row["entry_id"] == secrets["entry_id"])
            if entry["minor_version"] == 1 and entry["data"] == {"schema_version": 1, "synthetic": True}:
                break
            await asyncio.sleep(0.2)
        else:
            raise AssertionError("Migrated native config entry was not persisted")
        completed.append("actual_config_entry_migration_persisted_native_schema")
        config = await admin.ok("get_config")
        assert "recorder" in config["components"]
        status, _ = await http(session, "POST", "/api/states/sensor.wp2c_synthetic_recorded", {"state": "0", "attributes": {"synthetic": True, "unit_of_measurement": "W", "physical_verified": False}}, secrets["admin_token"])
        assert status in (200, 201)
        path = Path("/config/wp2c-synthetic-recorder.sqlite3")
        for _ in range(60):
            if path.exists():
                try:
                    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as database:
                        rows = database.execute("SELECT states.state FROM states JOIN states_meta ON states.metadata_id=states_meta.metadata_id WHERE states_meta.entity_id=? ORDER BY states.state_id DESC LIMIT 1", ("sensor.wp2c_synthetic_recorded",)).fetchall()
                    if rows == [("0",)]:
                        break
                except sqlite3.Error:
                    pass
            await asyncio.sleep(0.2)
        else:
            raise AssertionError("New synthetic Recorder did not persist the fake zero reading")
        completed.extend(["actual_new_synthetic_recorder_schema_created", "actual_recorder_persists_fake_zero_state"])
        assert str(path) != str(Path("/tmp") / ("heating-wp2c-" + secrets["entry_id"]) / "critical.sqlite3")
        completed.append("critical_and_evidence_stores_separate_from_synthetic_recorder")
        latencies = []
        for _ in range(50):
            started = perf_counter()
            sample = await admin.ok("heating_ai/status", **common)
            assert sample["status"]["physical_verified"] is False and sample["permitted"] is False
            latencies.append((perf_counter() - started) * 1000)
        completed.append("short_50_request_native_status_consistency_soak")
        await admin.connection.close()
    return {"qualification": "PASS_ISOLATED", "checks": completed, "count": len(completed), "status_50_requests_ms": {"max": round(max(latencies), 3), "mean": round(sum(latencies) / len(latencies), 3)}}


async def main() -> None:
    guard()
    action = sys.argv[1]
    result = await {"bootstrap": bootstrap, "isolation": isolation, "integration": integration, "restart": lambda: integration(True), "migration": migration}[action]()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
