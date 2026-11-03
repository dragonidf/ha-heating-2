# WP1A proof and review report

2026-11-03. **WP1A isolated software deliverable is ready for review. G1 remains BLOCKED. G3 is not passed. WP1B is not authorized.**

Authority: [issue #5](https://github.com/dragonidf/ha-heating-2/issues/5), [WP1A-TASK](WP1A-TASK.md), root AGENTS.md. Base `main`: `cce1c67ea81609d8d0784176db4ea49736fda759`. Approved specification, WP0 and legacy repository remain unchanged. The earlier WP0 recommendation against unqualified WP1 is superseded only by this later narrow WP1A authorization.

## Delivered files and behavior

| Surface | Files / result |
|---|---|
| Contracts | `packages/contracts/models.py`, `control.py`, `codec.py`, public `__init__.py`: 17 immutable value types; units, quality/provenance, injected clocks/revisions, minimal plan, intent/receipt/one-shot/state/event; strict schema 1.0 JSON. |
| Pure control | `packages/control/kernel.py`, public `__init__.py`: guard evaluation, ownership/order, deterministic single-event reduction and intent admission predicate. No sending, retrying, scheduling or physical-success inference. Parent `packages/__init__.py` only declares the namespace. |
| Automated proof | `tests/contracts/test_*.py`, `tests/unit/test_*.py`, `tests/properties/test_*.py`, synthetic factories in `tests/fixtures/` and contract tests; fresh-process `import_probe.py`; optional `benchmark.py`. All values are synthetic. |
| Tooling | `Makefile`, `pyproject.toml`, pinned `requirements-dev.txt`, `.gitignore`, `.github/workflows/wp1a.yml`, README. Runtime dependencies: standard library only. No installable HA component exists. |
| Review evidence | This report, [decisions](ADR-WP1A.md), [86-row requirements map](requirements-coverage.csv), [38-row scenario map](scenario-coverage.csv), [checksums](SHA256SUMS). Existing task/spec/WP0 files are unchanged. |

Main safeguards: unknown is never zero; received-at refresh never refreshes observed-at; signed power is explicit; aliases/derived balances cannot claim independence; actual grid is distinct from forecast. Upper/return, hard stop, bad data, windows and expiry take priority over min-on. SHADOW emits zero descriptions. Manual priority requires explicit resume and new ownership/reconciliation. Faults discard old plans and require stable inputs plus a newly admitted plan. Fallback deliberately stops when a valid plan cannot be held; it does not implement qualified native heating.

Regression development caught and fixed unsafe early returns from rejected plans/echoes, hard-stop processing during manual events, actual-grid cross-source skew omission, weak physical-evidence shape validation and reuse of a plan issued exactly at failure time. Their focused tests remain in the suite.

## Reproducible local results

Host: isolated x86_64 cloud Linux sandbox, kernel `6.18.57`; not the target N100, Home Assistant or its Python environment. Python 3.12.14 and system Python 3.13.5. Dev environment `/tmp/wp1a-venv`; no global or production packages changed. Coverage 7.17.1, mypy 2.4.1; transitive development versions are pinned in requirements-dev.txt.

| Command (repository root) | Observed result |
|---|---|
| `make check PYTHON=/tmp/wp1a-venv/bin/python` | PASS: strict mypy, 7 source files; **72 tests**, 0 failures/errors/skips; branch coverage enabled. |
| `/usr/bin/python3.13 -m unittest discover -q` | PASS: **72 tests**, 0 failures/errors/skips. This interpreter ran stdlib-only tests, not the 3.12 dev tool environment. |
| `python -B -m tests.properties.import_probe` (also run by unittest) | PASS: fresh imports, construction, reduction and JSON roundtrip with file/network/subprocess/database/system-clock/random APIs disabled. Import machinery may read module code; application data I/O is forbidden. |
| `git diff --check` | PASS for prepared changes. |
| `sha256sum --check docs/wp1a/SHA256SUMS` | Required final integrity check. Manifest covers source/tests/config/README and WP1A review evidence; excludes itself and unchanged task. |
| `python3.14 --version` | Not installed locally; no local 3.14 PASS claimed. CI explicitly includes 3.12/3.13/3.14; see PR checks for remote results. |

Coverage: **759/765 executable statements (99.22%)**, **225/230 branches (97.83%)**, combined **98.89%** (tool displays 99%). No coverage suppression added; remaining paths include defensive codec annotation/encoding errors, optional non-strict windows and unexercised early plan branches. Coverage is code execution evidence, not proof of every possible state or physical safety.

The 72 test methods include **3,800 deterministic generated checks**: 300 permission/mode/grid/quality combinations, 2,000 seeded upper/return/hard-stop cases, 1,000 stale-event/manual replays and 500 corrupt payloads. Seeds are fixed in `test_invariants.py`. Six in-memory policy guard deletions are killed by independent witnesses: hard stop, armed permission, actual grid, room upper, return upper, monotonic/owner check. The event layer provides additional defense in the clock case; mutation evidence concerns pure eligibility, not simulated equipment execution. All eight runtime modes are reached in synthetic transitions. No skipped expected failures hide a P0 regression.

Purity proof combines a closed AST import allowlist, actuator/dynamic-execution/system-clock call scan, negative tests for the scanner itself, fresh-interpreter API denial and execution under the same guard. This proves the reviewed module graph's boundary; it does not sandbox arbitrary future code.

CI uses pinned checkout v4.2.2 and setup-python v5.6.0 commit SHAs verified against public tag refs. Jobs have read-only repository permission, checkout credential persistence disabled, no production connection/secrets/deployment step, pinned isolated dev installation, checks and checksum verification. CI status is reported by the PR; target packaging and linked SQLite qualification remain B06.

## 100,000 synthetic snapshots

Command: `python -m tests.properties.benchmark`, Python 3.12.14, same isolated cloud host. 1,000 warmup calls; 100,000 timed calls, equally divided safe HEAT, hard-stop, unknown actual grid and SHADOW; immutable inputs constructed outside timing; `perf_counter_ns` used only in test harness. Nearest-rank p95/p99 and median:

| p50 | p95 | p99 | max |
|---|---|---|---|
| 0.039029 ms | 0.094732 ms | 0.207691 ms | 12.894131 ms |

Microbenchmark does not cover event loop, physical commands, planner load, persistence, imports, soak or target scheduling. **N100 p99≤10 ms and safety OFF latency gates remain NOT_EXECUTED; these measurements cannot pass them.**

## Requirement and scenario traceability

All **86** canonical IDs/T-IDs and **38** SC IDs remain in the maps, with no original status changed. **26 requirement slices** have passing pure tests, **50 full requirements NOT_IMPLEMENTED**, **10 BLOCKED**. Of the scenarios, **20 have partial pure aspects tested**, **14 NOT_IMPLEMENTED**, **4 BLOCKED**. **No complete canonical requirement/scenario acceptance is marked PASS.**

Implemented pure T-ID slices: **T-S01, S03–S09, S11–S14; T-D01–D05, D07; T-P02, P07, P08, P10, P12; T-O03, O05, O06** (the `T-` prefix applies to every listed ID). The CSV gives exact modules, verification and remaining acceptance per ID.

Mapped partial SC aspects: **SC01–SC13, SC16–SC18, SC26, SC31, SC35, SC36**. For example SC02 tests upper/min-on priority without a DB; SC04 tests in-memory manual authority without durable restart; SC35 tests imports/modes/100k without duplicate gateway, offset/clamp or N100 acceptance. Contract-only observations never substitute for a full fault/physical scenario.

No implemented planner, thermal model, ledger, learner, weather/Svitlo adapter, thermostat capability offset, fan arbitration, store/queue/gateway, real authorization, external compatibility client, UI, migration or crash recovery exists. Those tests remain NOT_IMPLEMENTED or BLOCKED. No B08 cap/elapsed behavior or exactly-once physical delivery is claimed.

## Outstanding evidence and limits

[Issue #3](https://github.com/dragonidf/ha-heating-2/issues/3) remains the closure tracker; WP0 source reports are retained intact.

| Blocker | Status / evidence still required |
|---|---|
| B01 | BLOCKED: complete private app registration/bindings/source timing and configuration evidence. No household parameters imported. |
| B02 | BLOCKED: coherent private saved state/history/original forecasts/counters and existing backup evidence; no export or backup performed. |
| B03 | BLOCKED: qualified wiring/phase/alias/signed topology and metrology. Synthetic IDs are not a household mapping. |
| B04 | BLOCKED: complete external/manual/automatic writer inventory and future quiescence proof. Pure ownership logic cannot establish sole physical authority. |
| B05 | BLOCKED: qualified OEM/physical OFF/ON, pump, anti-freeze, power/HA-loss and fan backup evidence. No physical tests. |
| B06 | BLOCKED: target packaging, linked patched SQLite, filesystem/flush/locking/crash behavior. Python compatibility tests do not qualify these. |
| B07 | BLOCKED, partially narrowed by issue #3's external-task review: effective downstream candidate auto-apply, credential/client permissions and compatibility consumers remain unverified. External task unchanged. |
| B08 | BLOCKED: owner session-cap/elapsed/reboot policy decision. One-shot type preserves HEAT-after-grid-return meaning; no executor and no invented global 180-minute cap. |

Future adapters must establish truthful measurements, clock/identity provenance, authority and actual-state reconciliation. Policy qualification flags in pure input are not evidence. Pure receipts preserve supplied evidence, never verify equipment themselves. Native-auto fallback and continuous transport lease handling remain deferred, as detailed in ADR-WP1A.

## Action and privacy audit / review boundary

Production HA connections, reads, writes, configuration changes, service calls, restarts, installs, backups and physical commands during **WP1A: 0**. Legacy repository mutations: **0**. No private telemetry/configuration/recording, device identities, credentials or addresses were used as fixtures or added to this diff. GitHub mutations are confined to this project's dedicated WP1A branch and review PR. No automatic merge or transition to WP1B.

Integrity provenance is the public base SHA above plus per-file SHA-256 in SHA256SUMS; all evidence refers to synthetic files, not private runtime bytes. The review PR is the completion boundary. The software slice can be reviewed now; an unqualified G1/WP1B readiness or live activation claim remains **BLOCKED**.
