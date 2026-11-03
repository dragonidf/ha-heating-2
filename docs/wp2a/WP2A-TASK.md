# WP2A — Codex implementation task (authorized offline only)

**Owner authorization: APPROVED 2026-11-03, strictly synthetic/offline.** Full normative scope, failure scenarios and acceptance criteria: [Issue #14](https://github.com/dragonidf/ha-heating-2/issues/14). This is a **single cohesive work package**; don't stop at a mock prototype.

## First reads

1. `AGENTS.md`, `docs/wp2a/APPROVAL-2026-11-03.md`, and the entire Issue #14.
2. `docs/spec/heating-ai-2.0/02-Architecture.md`, `03-Codex-specification.md` (especially D01–10, S01–15, E01–08, P01–12, U/O boundaries), `04-Test-strategy.md`, `05-UI-design.md` where relevant for API shape, `06-Migration-and-acceptance.md`, the canonical `requirements.csv` (86), `test-scenarios.csv` (38).
3. `docs/wp0/`, G1 Issue #3, accepted WP1A/B/C reports and their implementation/tests, and `docs/ROADMAP-TO-LAUNCH.md`. No unqualified assumptions about household mapping, power phase topology, historical calibration or source ownership.

## Execute one branch + one code PR

Create `feature/wp2a-offline-integration-ledger` from latest `main`. Preserve every 219 accepted regression test and previous behavior. Implement all **offline-only** portions of Issue #14, in coherent independently testable libraries:

**A. Fake HA integration contract:** strict versioned entity capability/binding schema, physical source aliases/overlaps, units, freshness, provenance, type and bounded event order; in-memory `FakeHAClient` with fake events only (no actual HA URLs/tokens/sockets/imported service sender). Connect synthetic source events → WP1A snapshots → accepted WP1B store/fake simulator → WP1C planner proposals; keep one-writer fence, manual pause and independently prioritized emergency STOP. API/permission/save receipts must be typed; never imply a fake ACK equals physical actuation. Native HA compatibility is NOT_TESTED until a separate authorization of an isolated real HA instance.

**B. Separate evidence ledger/archive:** own ephemeral SQLite database, independent critical-store lifecycle, append-only raw/provenance/uncertainty coverage, monotonic identity/revision/checksum, idempotent ingest/recovery; meter resets, signed Deye GRID, overlapping groups/aliases, realistic 45s bounded timestamped power integration, pump pulses, unknown time gaps, dated tariffs; immutable original 12h forecast vs factual room/energy with source-issue references and honest missing coverage; bounded indexed cursor queries and versioned serialization. A blocked/busy evidence DB must never block emergency STOP, manually gated safety or invent HEAT.

**C. Synthetic migration rehearsal:** strict legacy→new manifest, version/checksum/continuity keys for counter/model/plan/one-shot/fan/forecast data. Run **read-only dry-run** over synthetic legacy-shaped fixtures, idempotent staged import and rollback on disposable copies with explicit integrity/unknown handling. **Do not fetch, export or back up real production data.**

**D. Testing/evidence:** add deterministic, negative/property and fault tests for race/reorder/double-count/timezone/DST/delayed samples/sensor availability/ownership/STOP/SQLite EIO ENOSPC crash/migration rollback. Add CI for Python 3.12/3.13/3.14, strict mypy, no unauthorized transport/imports, preserve at least the existing quality gates; manifest integrity and all 219 inherited regressions. Provide measured test-host timings only. Map all 86/38 requirements/scenarios with honest PARTIAL_OFFLINE/BLOCKED statuses; no false completeness claims.

Produce `docs/wp2a/REPORT.md`, `ADR-WP2A.md`, coverage matrices, checksums, reproducible failure/benchmark notes. Open **one unmerged PR** and stop; return only PR URL, final SHA, test count, final-head CI status and critical limitations.

## Absolute stop lines

- Never read/write/install/reload/restart/alter production HA or any real devices, services, apps, records or private source data.
- Don't mutate `dragonidf/ha-heating-ai`. No private identifiers, addresses, LAN topology, credentials, historical household data or telemetry in this public repository.
- Never write or enable a real HA integration, service client, MQTT/WebSocket/HTTP device transport, active worker or second physical writer. Pure/fake integration only.
- Don't claim actual meter topology, thermal coefficients, safety/OEM behavior, HA version compatibility, target-host durable storage, or 7-day shadow proof from synthetic tests.
- G1/B01–B08 remain BLOCKED; B08 unresolved. No automatic WP2B, live connection, migration or deployment without a new explicit approval.

**Do all normal sandbox coding/testing independently, without intermediate chat reports.** An independent reviewer handles code review, correctness and merge after the code PR is ready.
