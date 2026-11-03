# WP1B — offline crash-consistent control store and simulated gateway

**Status: APPROVED for offline development only, 2026-11-03.**
Authority: owner decision in `APPROVAL-2026-11-03.md`, [Issue #7](https://github.com/dragonidf/ha-heating-2/issues/7), approved architecture ADR01–07. G1/B01–B08 remain BLOCKED in Issue #3.

**Outcome:** an independently testable, reliable persistence and command-transport **simulation**, NOT an HA controller. Speed comes from concentrating on this critical reliability layer and performing synthetic fault tests continuously, not from bypassing gates.

## 0. First reads

1. Root `AGENTS.md`; this file and `APPROVAL-2026-11-03.md`.
2. `docs/wp1a/REPORT.md`, `docs/wp1a/ADR-WP1A.md`, `packages/contracts/`, `packages/control/` and existing tests.
3. `docs/wp0/06-open-questions-and-blockers.md`, `docs/wp0/07-gate-G1-readiness.md`.
4. `docs/spec/heating-ai-2.0/02-Architecture.md`, `03-Codex-specification.md`, `04-Test-strategy.md`, `06-Migration-and-acceptance.md`, `requirements.csv`, `test-scenarios.csv`.

**Do not claim unverified household parameters, physical authority, persistence, or command success.**

## 1. Detailed implementation scope

### WP1B-1: separate critical control store

- Implement `packages/control_store/` or a comparably isolated library with explicit interfaces for `ControlState`, config revision/CAS, owner/boot epoch, manual/armed permissions, accepted plan metadata, outbox intents, receipts, emergency-stop replay frontier, and one-shot consumption/unknown outcomes. Keep large evidence/history/learning **out of critical transactions** and avoid depending on compute.
- Use **SQLite on a disposable local filesystem directory**, with deterministic schema migrations, bounded transactions, explicit owner fencing and idempotent APIs. Verify `PRAGMA journal_mode=WAL` and `synchronous=FULL` by readback when applicable; check actual linked SQLite and patch provenance and report B06 honestly. No compatibility claims beyond exercised interpreters/FS.
- Store immutable source/contract schema version, transaction order and stable IDs; reject incompatible versions, bad checksums, torn/corrupt records, conflicting CAS and wrong owner epochs without rewriting the source of truth. No silent reset to defaults or re-arming of previously manual-paused state.
- Keep file I/O **only in the store/adapters**, not `packages/contracts` or `packages/control`. Avoid a single shared lock that can block STOP while SQLite/analytics stalls.
- Make persisted-state receipts meaningful: `prepared`, `sent`, `ack`, `echo`, `physical evidence` are different facts. A DB commit is not proof that a device changed. No fabricated receipt stage.

### WP1B-2: fake gateway + intent scheduler model

- Implement `packages/simulator/` and optionally `packages/gateway_sim/` with a **FakeActuator** and no HA/MQTT/WS/Tuya imports or network access.
- Model one logical writer, current boot/owner generation, permitted snapshots and typed intent deadlines; no HEAT can be 'sent' without a durable prepare and a fresh permission check at the fake boundary.
- Simulate latest-desired-state-wins for **ordinary** commands using bounded queue capacity. Route trusted emergency STOP via a separate higher-priority lane unaffected by normal queue or blocked DB; use WP1A separate stop replay frontier and reject unauthorized emergency assertions. `authorized=True` is **not** actual authentication: a future adapter must establish trust outside user-supplied JSON.
- Stop needs no synchronous DB commit; audit may be committed later with explicit unknown/missing evidence. 'Demand STOP' is **not** a guaranteed physical relay OFF, and SHADOW never writes to fake actuator.
- Failed/slow durable prepare (target budget 250 ms), lock contention, full disk, read-only DB and corruption must **never cause HEAT emission**. Log missing/outcome UNKNOWN as appropriate; do not spin or retry unboundedly.
- Simulate timeouts, reordering, duplicate ACK/echo, stale epochs, manual intervention, slow unrelated producer, lost compute, and partial failure. Service return ≠ echo ≠ independent power/physical proof.
- Never replay HEAT automatically after a restart if send/echo outcome is uncertain. Reconcile from newly supplied trusted fake state, refreshed owner/manual epoch, valid plan and fresh guards. Preserve one-shot consumed/unknown, do not silently restart a completed session.

### WP1B-3: crash/failure harness

Build reproducible tests using disposable subprocesses/process termination **in the isolated sandbox only**. Kill at each boundary:
1. before prepare
2. after durable prepare, before fake send
3. after fake send, before sent receipt
4. after sent receipt, before ack
5. after ack, before echo
6. after echo, before durable receipt
7. during owner/manual epoch update
8. during migration/CAS conflict and WAL checkpoint

Test failed fsync/transaction, disk-full, DB busy/locked, DB corruption/truncation, stale source ages, unexpected clock rollback and restart. Result must never become duplicate unsafe HEAT or accidental re-arm; unknown outcomes must remain visible/typed. Test STOP ordering under blocked normal queue or DB write.

Use fault injection through controlled adapters and ephemeral files; **never simulate on physical thermostat, actual HA services or a real HA database**.

### WP1B-4: qualified technical constraints

- Contract and kernel stay pure, side-effect free, deterministic. Retain all 92 WP1A regression tests; do not reduce test coverage or loosen thresholds to pass.
- Every authorization and persistence read uses explicit versioned types; no 'secret' default for missing sensor or unknown grid, no conversion of unknown into zero.
- Preserve per-source freshness (slow room/Zigbee vs fast grid) and separate clock skew from allowed observation age.
- B08 remains unresolved; preserve existing one-shot `HEAT_AFTER_GRID_RESTORE` interpretation and **do not implement a global 180-minute cap** or decide detailed reboot/elapsed semantics without owner ADR. Implement only generic durable consumed/unknown states.
- Determine linked SQLite versions separately on each **test** interpreter/host and compare against documented security/correctness requirements (including WAL-reset issue); failing target qualification is `BLOCKED`, not automatic permission to upgrade production.
- CI isolated, no secrets and no network transport to the home; dev-dependency installation from known pinned packages only. Test matrix 3.12/3.13/3.14 where supported. If a host/platform test is unavailable, report NOT_RUN/BLOCKED.
- Benchmark latency under test environment and distinguish cold start/flush stalls/max tail from average; N100 production SLO and real safety OFF SLO remain NOT_TESTED.

## 2. Explicit exclusions

NO `custom_components/heating_ai/` installation/production integration, actual HA service sender, HTTP/WebSocket/MQTT clients, AppDaemon changes, compute daemon, thermal planner/model, energy ledger, ventilation control, full UI, long-running service, source state import, or production backup. No actual commands to any device.

No modification of `dragonidf/ha-heating-ai`. No private runtime data or real entity/device identifiers in any code, issue, test, log, CI artifact, or PR. No production restart, HACS update, file edit, state setting, SQL access, or deployment. Do not automatically progress beyond WP1B.

## 3. Acceptance checks and evidence

1. All existing WP1A tests remain green, including asynchronous freshness, trusted/replayed emergency, and strictly newer recovery plan.
2. Repeatable automated store/queue/CAS, crash-injection, broken-storage, stale/reordered/duplicate and manual/one-shot tests pass across 3.12/3.13/3.14 (when qualified). Failures cannot be 'fixed' by muting tests or raising unsafe limits.
3. Demonstrate in tests that uncertain send/echo is not double-issued as HEAT after restart; manual pause survives and emergency STOP remains nonblocking when normal DB/queue is stalled.
4. Confirm via AST/import/static guard that new packages have **no actual device/HA transport path**. Run a sandbox network-deny probe for simulator.
5. Report actual test-environment SQLite version, WAL/FULL readback, fsync/locking behavior tested, process/FS identity, observed failures/limitations, and preserve B06 BLOCKED until the real target is qualified.
6. Update `docs/wp1b/REPORT.md`, `ADR-WP1B.md`, source/test checksums, plus WP1A's 86/38 traceability as a **new additive matrix**, without falsely marking complete scenario acceptance PASS.
7. Final deliverable is an unmerged `feature/wp1b-offline-store-simulator` PR. Include exact commands, runs, coverage and tests; explain how future HA gateway remains separated. **Stop for independent review.**

## 4. Work sequencing to accelerate without risk

- Implement transactional store + synthetic migrations, and fake gateway/queue as independently testable components. Integrate only through typed interfaces after both have tests.
- Start deterministic crash matrix early and run it on every CI commit; test dangerous failure paths before UI or planner.
- Parallel non-mutating G1 evidence work is tracked in Issue #3, not part of this code PR, and **cannot** be replaced by synthetic data.
- No additional human confirmation needed for ordinary **sandbox-only** file edits, tests, PR creation or CI; obtain separate approval for any access outside these bounds.

**Gate:** WP1B isolated software review may pass while G1 remains BLOCKED; actual HA integration, commissioning and cutover remain unauthorized.
