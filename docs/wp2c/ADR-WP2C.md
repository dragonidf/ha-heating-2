# ADR-WP2C — generated, fake-only native HA package

**2026-11-10 revision:** [Source/time clarification](REVISION-2026-11-10.md) supersedes prior source-selection and frozen-clock wording below. KWS Tuya Local is the future boiler evidence role; input220 Zigbee2MQTT alone supplies grid-input voltage. Historical qualification records remain unchanged.

Status: implemented for isolated review; physical gates remain BLOCKED. Authority: Issue20 and APPROVAL-2026-11-04.md. This extends ADR01–07 solely with SDK packaging and synthetic native qualification.

## Decision

Keep accepted deterministic contracts/control/store/model/planner/energy modules unchanged. A small HA SDK template in `ha_sdk/heating_ai` supplies native config/options, registry sensors, authenticated WebSocket projection and panel lifecycle. `tools/wp2c/package.py` creates an installable `custom_components/heating_ai` only under an explicitly disposable output path; it copies accepted Python code, changing only absolute import prefixes, and records original and resulting SHA256 for every file. No package is installed in an existing HA. The original WP2A closed-import/no-installed-component regression remains intact.

Installation requires both an environment marker and an exact synthetic-only file in the new instance. Config creation requires explicit confirmation; simulation defaults false. Only one entry is supported. All three read-only sensors default disabled; missing meter values are unknown, never zero. No climate/switch/fan platform or service/device transport exists. Future meter selection accepts synthetic IDs only and conveys no physical authority.

Backend state is authoritative. Pure `packages/ha_native` owns transactional critical state and a separate evidence database, uses the accepted source adapter and safety kernel, and unconditionally denies physical heat. New boots increment generation/owner epoch, clear source eligibility, preserve manual pause and turn unresolved one-shots into unknown outcomes. No source after restart means SAFE_HOLD until a new authenticated own synthetic event. Options updates preserve unspecified existing fields and reload; source age is authoritative. Registry changes invalidate observations. Unload/shutdown fences in-flight mutations and closes subscriptions.

Every mutation carries entry/version/boot/generation/owner epoch and a request identity. HA supplies the authenticated user privilege; body permission flags cannot authorize. Durable settings use SQLite WAL/FULL, CAS, persisted receipt and independent readback. Exact committed retry may return its receipt without repeating effects; changed-body reuse conflicts, delayed old-owner requests fail. Unknown commit/readback outcome is unavailable. Synthetic schema migration has an explicit rollback copy; partial initialization never becomes successful state.

Logical emergency pause changes bounded memory first, bypassing the normal executor lock and both databases. It invalidates older normal work before asynchronous durability. This protects a simulated desire while disk is stalled; it makes no promise to send a physical OFF. Memory and durable outcomes stay separate. Evidence failure does not disable status/STOP; source and critical persistence faults inhibit normal mutations.

The panel mounts the reviewed React UI in a Shadow DOM using injected `hass.callWS` and existing authenticated connection subscriptions. There is no new socket, token cache or IndexedDB authority. Reconnect obtains a fresh snapshot before writes. Queries/deadlines/subscriptions are fenced; archive failure cannot replace missing native history with local demo facts. Standalone behavior and its accepted browser/visual gates remain intact. Scoped focus avoids document-global ID lookup.

## Isolation and alternatives

An ephemeral Core container has network mode none, no published port, a loopback listener, no device discovery or cloud defaults, dropped capabilities and only two newly labeled disposable volumes. Browser containers join only this namespace. Official dependency downloads occur during setup; running HA cannot reach external or owner hosts. Existing user infrastructure is never a fallback.

The full appliance image exceeded local disposable storage; the qualification target uses the pinned official Core wheel and official frontend on pinned Python3.14.2, with a hash-verified SQLite3.51.3 library. This qualifies that exact Core/SDK composition only, not HA OS, HACS, Android WebView or the owner's N100. See HA-VERSION-MATRIX.md and ISOLATION.md.

## Consequences

Independent review can inspect exact source/artifact hashes, reproduce native auth/lifecycle/browser checks, and distinguish PASS_ISOLATED, MOCK_ONLY and BLOCKED. Native success cannot close G1/B01–B08, prove metrology/OEM behavior or grant installation/shadow/cutover permission. WP2D requires separate authorization.
