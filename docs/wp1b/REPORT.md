# WP1B offline state/store and command-simulation report

2026-11-03. **The offline software package is prepared for independent review. G1/B01–B08 remain BLOCKED. No G3/target/physical gate is passed. WP1C is not authorized.**

Authority: [owner approval](APPROVAL-2026-11-03.md), [task](WP1B-TASK.md), [Issue #7](https://github.com/dragonidf/ha-heating-2/issues/7), updated root AGENTS.md. Branch `feature/wp1b-offline-store-simulator`, based on main `cb19fa4dc4cdd35b8dbb3437485642034dc97037`. PR must stay open without merging.

## Delivered boundary

| Surface | Delivered proof |
|---|---|
| `packages/control_store/qualification.py` | Actual linked SQLite version/source observation; known minimum/future-major rejection; no inferred backport or target qualification. |
| `packages/control_store/store.py` | Disposable SQLite-only path boundary; frozen protocol/schema; v1→v2 atomic rehearsal; WAL/FULL readback; checksums; config/state CAS; boot/owner fencing; immutable event identity; durable prepare/claim/receipt stages; manual/OFF and armed preservation; generic one-shot consumed/unknown markers. |
| `packages/simulator/engine.py` | Exact in-memory FakeActuator only; one writer; one pending ordinary desire; fresh boundary permission checks; fake issuer-bound trust/observations; no raw authorized-boolean authentication; independent STOP; deferred bounded audit; no HEAT replay after restart. |
| Tests/fixtures | 92 retained WP1A methods plus **63 WP1B methods**; 13 SIGKILL cut points; OS/VFS failure witnesses; lock/read-only/corruption/CAS/timeout/manual/one-shot/replay/async/compute cases; closed import graph and network-deny probe; standalone benchmark. |
| Dev/CI | Existing strict mypy and **95% coverage threshold unchanged**. Three-interpreter workflows build a pinned test-only SQLite when native 3.46.1 cannot qualify, assert actual linked version/source, run the full suite and checksum verification. |
| Review evidence | [ADR](ADR-WP1B.md), [86-row additive requirements map](requirements-coverage.csv), [38-row scenario map](scenario-coverage.csv), [benchmark](BENCHMARK.json), SHA256SUMS and CI evidence. |

The seven WP1A pure source files are byte-identical to main. All 92 test methods remain. The existing purity scanner now enumerates those exact seven files, since this phase explicitly adds separate I/O packages; its pure import/call rules and seven-file assertion remain intact. A new closed graph/no-network guard covers all five new package files. README, combined CI setup and their integrity entries are deliberately updated; original specification/WP0/trace matrices are unchanged.

## Test environment and qualification

Local: Linux x86_64 cloud sandbox, kernel 6.18.57; Python 3.12.14 linked SQLite **3.53.1**, source ID in BENCHMARK.json. Local Python 3.13.5 natively links **3.46.1 (BLOCKED)**; its offline suite is run with the separately built SQLite **3.51.3**. No local Python 3.14 is installed; that compatibility result comes from CI.

Initial CI observed native SQLite **3.46.1 on all three interpreters**, including its actual source ID. It was never relabeled qualified. Test-only build URL/hash/source/flags are frozen in ADR-WP1B and `tests/fixtures/build_sqlite.py`; no downloaded amalgamation or library is committed. The job-local library is selected through LD_LIBRARY_PATH and actual runtime/source ID is asserted before testing. This is no production SQLite change or HA component installation.

Local `/tmp` is **tmpfs**. The complete filesystem run explicitly selects `/workspace/wp1b-test-tmp` as TMPDIR on **overlay**; that directory is outside the repository and disposable. CI selects a disposable runner filesystem directory and prints actual process/FS identity. Tested: WAL/FULL=(wal,2), cross-process BEGIN IMMEDIATE exclusion, OS-acknowledged file and directory fsync, and process-kill recovery. These observations do not prove hardware flush behavior or power-loss durability. **B06 actual target qualification stays BLOCKED.**

## Commands and observed results

| Command / scope | Result |
|---|---|
| `TMPDIR=/workspace/wp1b-test-tmp make check PYTHON=/tmp/wp1a-venv/bin/python` | PASS: 155 tests; strict mypy (12 files); coverage 97.45%, above unchanged 95% threshold. |
| `TMPDIR=/workspace/wp1b-test-tmp LD_LIBRARY_PATH=/tmp/wp1b-sqlite-build /usr/bin/python3.13 -m unittest discover -q` | PASS: 155 tests, no warnings/failures/errors/skips, Python 3.13.5 with verified test SQLite 3.51.3. No production library changed. |
| `python -m unittest tests.unit.test_store_failures tests.unit.test_simulator_faults tests.unit.test_vfs_failures -v` | Focused negative/fault checks pass in the qualified environment. Regression cases preceded fixes; no tests muted/skipped and no threshold raised to hide failures. |
| `python -B -m tests.fixtures.network_denied_probe` (also a test) | Imports, prepare/send/ACK/echo, emergency and audit execute with network APIs disabled. Only disposable local file/SQLite access is allowed. |
| `sha256sum --check docs/wp1a/SHA256SUMS` and `docs/wp1b/SHA256SUMS` | Integrity manifests verified for the reviewed source/evidence. |
| `git diff --check` | No whitespace errors in prepared changes. |

Final suite: **155 tests**, including all **92 WP1A** tests, **0 failures/errors/skips**. Strict mypy covers **12 runtime source files**. Final local Python 3.12 combined line/branch coverage is **97.45%** (1,374/1,397 statements; 420/444 branches); raw final totals appear in CI evidence. No coverage exclusions were introduced. Counts may differ with interpreter instrumentation; reports retain their actual values. Coverage cannot establish the absence of logic errors or physical safety.

The original 4,440 WP1A generated cases remain, plus **40 seeded send-boundary guard-failure cases and 200 seeded emergency replays** in WP1B. Capacity-one ordinary scheduling, deferred audit coalescing/missing evidence, duplicate ACK/echo, fake service failure, compute loss, frozen asynchronous measurements and clock rollback have focused checks. These are deterministic synthetic cases, not household telemetry replay or a 24-hour soak.

### Historical remote compatibility proof (before review fixes)

[PR #9](https://github.com/dragonidf/ha-heating-2/pull/9), source/test commit `50a41889e9720cdcaf5369b08fc47bbe5bea5afb`: [WP1B run 41672300606](https://github.com/dragonidf/ha-heating-2/actions/runs/41672300606) and [combined foundation run 41672301105](https://github.com/dragonidf/ha-heating-2/actions/runs/41672301105) both PASS, all six jobs completed successfully. Decoded WP1B logs confirm the following; sanitized run/job/runtime summaries are retained in [CI-EVIDENCE.json](CI-EVIDENCE.json).

| Interpreter | Actual test SQLite / FS | Full checks |
|---|---|---|
| Python 3.12.15 | 3.51.3 / ext4 | 150 tests, 0 failures/errors/skips; 12-file mypy; coverage and both manifests PASS |
| Python 3.13.17 | 3.51.3 / ext4 | 150 tests, 0 failures/errors/skips; 12-file mypy; coverage and both manifests PASS |
| Python 3.14.9 | 3.51.3 / ext4 | 150 tests, 0 failures/errors/skips; 12-file mypy; coverage and both manifests PASS |

Native 3.46.1 was observed as unqualified in every job before the pinned test library was selected. The test source ID matches ADR-WP1B exactly. Python 3.12/3.13 report 1,385 statements/23 missing; 3.14 reports 1,258/23; all report 436 branches/25 partial and display 97% combined. No ResourceWarning appears. This follow-up changes only report/evidence/checksums; source/test hashes are unchanged. The final-head matrix is separately verified after publishing it and linked from the PR description; it is not inferred from a prior code SHA.

Early whole-suite checks exposed untested branches/coverage below 95%; the suite was expanded around failure behavior without changing that criterion. Regression work also found and corrected ordinary-event owner acquisition/OFF-latch clearing, stale-owner send claims, receipt fact rewrites, stale worker access after close/restart, and loss of the newest emergency frontier under audit overload. Final queue review reproduced two more unsafe cases: an old pump frame erased newer grid-failure/expiry data. Centralized input admission now immediately fences unsafe inputs and rejects backward context; old queued calls cannot re-arm. Python 3.13 exposed unclosed connections in test fixtures; those connections are explicitly closed, not warning-suppressed.

## Crash and storage-failure evidence

| Class | Exercised boundaries / result |
|---|---|
| Command SIGKILL (10) | Before prepare; after prepare; before send; after claim; after fake send; after sent receipt; before ACK receipt; after ACK; after echo arrival/before durable echo receipt; after echo receipt. A synced synthetic call trace proves whether one fake HEAT occurred. After restart no fake HEAT is replayed; plan/reconcile readiness clears; historical receipt stages stay byte-identical, unresolved delivery is separately unknown, and consumed one-shot markers stay UNKNOWN. |
| Other SIGKILL (3) | During owner/manual transaction, during v1→v2 migration, and while SQLite VM executes checkpoint. Recovery preserves committed state or the prior transaction, never silently defaults/re-arms. A lost uncommitted manual update still starts closed and requires new trusted fake observation. |
| Actual SQLite failures | Read-only URI; cross-process write lock; SQLITE_FULL through bounded page allocation; truncated/checksum/identity/protocol corruption; rejected CAS/boot reuse. Failed transactions cannot prepare HEAT. |
| Actual VFS error-return injection | Disposable Linux child preloads a shim restricted to its control.sqlite3 files. fsync/fdatasync receives EIO; pwrite/pwrite64 receives ENOSPC. A stderr witness confirms each path was exercised. No fake HEAT occurs; recovery is STARTING/STOP or explicitly BLOCKED on untrusted storage, without reset/replay. |
| Timing/transaction injection | Held prepare, rejected commit/sync and >250 ms prepare (including a late committed result). STOP remains independent; old workers cannot send after a newer generation/manual/boot. No unbounded retry/automatic outbox replay. |

An injected STOP is a demand change in RAM, **not actual relay OFF**. Service return, ACK, echo and independent physical evidence are distinct. No simulator code creates physical-success evidence. VFS errors and SIGKILL do not simulate every power-loss write pattern, controller cache or target scheduler.

## Timing observations

`TMPDIR=/workspace/wp1b-test-tmp python -m tests.properties.benchmark_store`, Python 3.12.14 / SQLite 3.53.1 / overlay, 100 disposable runs, no warmup. Raw sanitized distributions and OS-acknowledged sync facts are in BENCHMARK.json.

| Measured path | p50 ms | p95 ms | p99 ms | max ms |
|---|---:|---:|---:|---:|
| Cold store/bootstrap | 14.264779 | 20.785089 | 28.151347 | 28.208543 |
| Prepare + claim + fake send + sent receipt | 9.208257 | 13.786996 | 17.117870 | 22.364601 |
| Trusted STOP while DB write-locked | 0.164572 | 0.361883 | 0.497777 | 0.512259 |
| Checkpoint | 0.243521 | 0.499550 | 0.867663 | 1.095585 |

100/100 fast-path synthetic HEAT admissions succeeded; separate 270 ms and held-until-release stalls deny emission and exercise STOP. These are cloud observations only. **N100 kernel/control/event-loop SLO, real HA/device delay and physical OFF remain NOT_TESTED.** No production performance gate is passed.

## Traceability and blockers

All **86 canonical requirements/T-IDs and 38 scenarios** remain in the additive matrices. **22 WP1B requirement slices** and **15 partial scenario aspects** have passing offline evidence. No complete canonical requirement or full integration/physical scenario is marked PASS.

Newly exercised T-ID slices: **T-S01–S09, S11, S12, S14; T-D01, D02, D05, D09; T-P02; T-O01, O03, O05, O06, O09** (`T-` applies to every ID). Exact test modules and remaining acceptance appear per row. Partial SC aspects: **SC01–SC08, SC10, SC16, SC18, SC30, SC31, SC35, SC38**. Private migration/history/model/physical cases remain NOT_IMPLEMENTED/BLOCKED.

| Blocker | Unchanged closure requirement |
|---|---|
| B01 | Verified private registrations/bindings/config and actual source cadence. No household values inferred from fixtures. |
| B02 | Coherent private state/history/ledger/original forecast/counter/backup evidence; no export/import/backup performed. |
| B03 | Qualified wiring/phase/alias/signed metrology. No physical topology assumption. |
| B04 | All real command authors and future sole-writer/quiescence proof. Fake writer fencing proves no real author inventory. |
| B05 | OEM/physical ON/OFF, pump/anti-freeze, power/HA-loss and fan evidence. No physical test. |
| B06 | Real target packaging, patched linked SQLite, FS/flush/lock/power-loss behavior. Test-only source build and overlay evidence do not close it. |
| B07 | Effective external client/candidate permissions and compatibility consumers; existing external task unchanged. |
| B08 | Owner cap/elapsed/reboot decision. Only generic `HEAT_AFTER_GRID_RESTORE` consumed/unknown markers; no global 180-minute cap/session executor. |

Future real transport/authentication, actual adapter sampling/continuous scheduling, compute/model/planner, ledger/history/UI, private import, packaging, target soak and commissioning remain deferred. The model advances synthetic inputs explicitly and accepts synthetic feedback as declared fixture premises; it does not infer trustworthy physical state from a boolean or echo. Store checksums are integrity checks, not authorization.

## Action audit and readiness

Production HA connections/reads/writes, device commands, component installs, lifecycle changes and production backups in WP1B: **0**. Legacy repository mutations: **0**. All DB/process/compiler/fault artifacts are disposable sandbox files; no private payload, address, credential, entity/device identity or household recording was added. Public SQLite source is the sole additional CI build download, outside runtime packages.

Ready for **independent offline WP1B review**, with exact source/test/evidence hashes in SHA256SUMS and CI observations in the PR. The final SHA must pass Python 3.12/3.13/3.14 before handoff. The PR remains open; no auto-merge, installation, rollout or automatic WP1C. G1 and actual target readiness remain BLOCKED.

## Consolidated review corrections — Issue #10 / comment 6610149771

Both findings were reproduced before implementation in `tests/unit/test_wp1b_review.py`, then fixed as one package. Codex performs implementation/self-testing; independent acceptance remains with ChatGPT.

- Restart no longer rewrites any outbox receipt. The seven-stage PREPARED/SENT/ACK/ECHO/PHYSICAL/FAILED/UNKNOWN matrix verifies exact payload/checksum/evidence preservation across repeated boots, corruption rejection, no old send claim and no replay. Typed derived delivery status distinguishes unresolved old work from confirmed historical evidence; current device state stays unreconciled with no live receipt. No schema migration or default reset is needed.
- Fresh unexpected HEAT cannot establish a STOP startup baseline. Trusted active-heat observations become durable manual/unknown-causation pause without overriding external demand. Tests include known/unknown authors, manual HEAT, stale/fresh STOP, denied plan admission, untrusted resume, and the positive explicit-resume/fresh-STOP/new-plan procedure. Fake observations remain synthetic premises, never physical proof.
- Existing crash assertions were corrected to preserve historical stage AND check delivery uncertainty; their no-replay, boot fencing and consumed-marker checks remain. All 150 prior tests and all 92 WP1A tests remain, plus five focused methods. No skips, lowered thresholds or new dependency.

Local full checks: 155 tests on Python 3.12.14 and qualified 3.13.5, 0 failures/errors/skips; strict mypy 12 files; combined coverage 97.45% (unchanged 95% criterion). Earlier CI tables/CI-EVIDENCE.json retain explicitly historical observations and do not certify this correction. The final-SHA six-job 3.12/3.13/3.14 result is recorded in the native repository [PR checks](https://github.com/dragonidf/ha-heating-2/pull/9/checks) and PR description after execution. G1/B01–B08 remain BLOCKED; no production/legacy/device changes, merge or WP1C.
