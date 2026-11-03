# WP1A — pure contracts and safety reducer (isolated software only)

**Status:** owner requested continuation after reviewing WP0 on 2026-11-03. This is a **narrow implementation authorization for WP1A only**. It does **not** accept G1 or authorize WP1B, a running HA integration, a command gateway, deployment, a backup, or device testing.

## Read before coding
- Root `AGENTS.md`
- `docs/wp0/06-open-questions-and-blockers.md`, `docs/wp0/07-gate-G1-readiness.md`
- `docs/spec/heating-ai-2.0/02-Architecture.md`, `03-Codex-specification.md`, `04-Test-strategy.md`
- `docs/spec/heating-ai-2.0/requirements.csv` and `test-scenarios.csv`
- `docs/spec/heating-ai-2.0/APPROVAL-2026-11-03.md`

Treat G1 as **BLOCKED**; track B01–B08 in [issue #3](https://github.com/dragonidf/ha-heating-2/issues/3). Pure synthetic behavior can be implemented without treating unverified household inputs as facts.

## Goal
Implement the foundational, deterministic, independently testable software only:
1. Typed immutable contracts and schema/version/units boundary.
2. Pure safety policy and state reducer that **never** performs I/O and **cannot** command an HA/device by itself.
3. Synthetic fixtures, deterministic property/regression tests and CI for the isolated library.

This is a bounded first slice of WP1, **not** the complete Heating AI 2.0 controller.

## Allowed paths and dependencies
- `packages/contracts/`: versioned dataclasses/enums, parse/serialize, validation, explicit W↔kW, °C, kWh, UTC/monotonic representation, typed optional fields, quality/provenance.
- `packages/control/`: pure safety priority model, evaluation/reducer, typed in-memory next-state/intent *descriptions* and reason codes.
- `tests/unit/`, `tests/contracts/`, `tests/properties/`, `tests/fixtures/`: deterministic synthetic data; no real household identifiers or recordings.
- `pyproject.toml` or equivalent small project-local dev/test config, isolated CI pipeline, README for WP1A proof. Supported Python runtime matrix should reflect spec 3.12/3.13 and check 3.14 compatibility if test environment allows, clearly distinguishing results.
- `docs/wp1a/`: ADRs, coverage, proof, unimplemented contract surfaces and unresolved blockers.

Do not import `hassapi`, Home Assistant modules, network clients, filesystem/database APIs, or any production actuator in the pure contracts/kernel paths. Inject clock/snapshot/config explicitly; never use global mutable state, system time or random decisions inside the reducer.

## Required contract classes/semantics
- `Reading`: `physical_id`, `source_id`, nullable `value`, `unit`, `observed_at`, `received_at`, optional source sequence, `quality` and evidence provenance. Refreshing received_at must not freshen observed_at.
- `Quality`: valid / estimated / stale / missing / conflicting and age/reason. Unknown is **not** 0.
- `ControlSnapshot`: input/config/model/topology revision IDs, grid epoch, owner epoch, captured-at, typed sensor values, freshness/quality.
- `ControlPolicy`: validated thresholds/permission flags, distinct actual-grid permit vs forecast, manual/armed semantics, strict windows, upper/return temperature constraints only where qualified.
- `HeatPermit`: allow/deny with stable reason code and input revision; cannot be inferred from a historical heartbeat alone.
- `CommandIntent` and `CommandReceipt` **data types only**: intent_id, epoch, sequence, expiry, exact desired action, evidence stages; no service sender, queue, retries or physical success claim.
- `ControlState`/`ControlEvent`: STARTING/SHADOW/AUTO_PLAN/AUTO_HOLD/FALLBACK/MANUAL_PAUSE/OFF/SAFE_HOLD plus strict event-order and ownership rules.
- `Plan` **minimal interface only**: type-safe versioned segments `[start,end)`, expires/hash/revisions, without planning algorithm.
- Persist/JSON schemas must reject incompatible major versions, missing required fields, bad units, `NaN`/`Inf`, invalid ranges, oversized/corrupt payloads. Preserve `null` vs `0` vs `false`.

## Reducer invariants and tests
- No new `HEAT` intent when armed off, observation, manual priority, grid off/unknown, invalid/unfresh required sensors, expired plan/intent, stale owner/boot epoch, or invalid config.
- Explicit safety stop/upper-limit has priority over min-on and budget; a stop decision never blocks on planner/learning/storage.
- No stale event may steal authority from later manual action. Own command echo and external manual change are not interchangeable.
- Distinguish `HEAT requested`, HA acknowledgment, device echo and independent physical evidence. Pure code cannot mark physical success.
- No false claims from power-model sources: overlapping aliases are not independent meters; computed balance is a derived source.
- Unknown outage forecast may create a conditional future scenario but cannot authorize live HEAT.
- No one-shot reinterpretation: legacy `restore_once` is one heating session after grid restoration; it does not mean `OFF on power restore`. Design one-shot type with explicit kind/expiry/consumption/unknown outcome, but **do not settle B08 180-minute cap scope** or silently change behavior; document pending decision.
- Add focused tests for null/zero/false, invalid unit, clock skew, replay/out-of-order, duplicate intents, stale manual/own echo, min-on vs safety OFF, unknown grid, upper boundary, unsigned/negative power semantics, half-open segment boundaries and DST conversion without using private data.
- Import-boundary checks must prove kernel path has no I/O/HA imports.
- Run full checks in isolated environment and report precise command, environment, pass/fail counts. If possible benchmark `100,000` synthetic reducer snapshots and report distribution. N100 p99≤10 ms is a **future physical-host gate**, not automatically passed by sandbox timing.

## Explicitly forbidden in WP1A
- Changing any production Home Assistant config, helpers, automation, database, service, addon, OS, devices or control.
- Touching/updating `dragonidf/ha-heating-ai` or replaying its runtime against production.
- Creating an enabled native HA integration, command gateway, compute daemon, scheduler, background service, dashboard, storage DB, live bindings or one-shot execution.
- Installing, restarting or updating HA/AppDaemon; recording real household telemetry or publishing secrets.
- Claiming G1/G3 PASS or marking all 86 requirements and 38 scenarios implemented.
- Automatically proceeding to WP1B / deployment / physical tests.

## Delivery / acceptance
- Dedicated `feature/wp1a-pure-kernel` branch; **PR left open** for review.
- List each implemented T-ID and mapped scenario, exact tests and evidence. Mark unimplemented runtime/HA/storage tests as BLOCKED or NOT_IMPLEMENTED.
- Prove source is pure and no actuator route exists, with a module-level import/side-effect guard and static path scan.
- Negative tests are as important as green unit tests. Do not weaken or skip failed P0 tests.
- Maintain a concise `docs/wp1a/REPORT.md` with file inventory, test commands/results, test/provenance hashes, outstanding B01–B08 and deferred modules.
- Stop at the reviewable PR. No merge to `main` without separate review, no controller deployment and no automatic WP1B.
