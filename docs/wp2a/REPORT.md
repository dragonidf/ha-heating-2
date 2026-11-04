# WP2A — isolated integration, evidence/energy and synthetic migration

Implementation/self-test handoff for Issue #14, based on main `c3eceecee5d8538f6426ee60ecb93563f14d8805`. Owner approval is limited to offline WP2A. This package is submitted for independent review in one unmerged PR; it does not qualify HA deployment or authorize WP2B.

## Delivered package

| Module | Implemented offline behavior | Evidence |
| --- | --- | --- |
| `packages/offline/` | Frozen binding/capability/unit/physical alias schema; source/provider events; permission/save/state receipts; strict envelope2.0; energy/archive/cursor/recovery/budget/migration contracts | `tests/wp2a/test_codec.py`, `test_bindings.py` |
| `packages/ha_fake/` | FakeHAClient without URL/token/network; deterministic source replay, duplicates/reordering/unavailable/reconnect; scalar and provider normalization; event→WP1A snapshot→WP1B fake runtime and WP1C proposal bridge; permission revocation, trusted independent STOP, durable settings receipts, manual fan/thermostat ownership | `test_integration.py`, `test_features.py`, `test_boundaries.py` |
| `packages/evidence/energy.py` | Qualified signed balance with nonoverlap, actual timestamp integration and45s hold, confirmed/derived/estimated/unknown separation, reset/jump handling, independent stage estimate, dated tariffs, DST/day split and explicit prorating | `test_energy.py`, `test_bindings.py` |
| `packages/evidence/store.py` | Separate WAL/FULL SQLite, append-only hash-chain journal, schema migration, identity/interval fencing, immutable canonical origins, atomic finalization/recovery, frozen initial/prestart/original/latest evidence, budgets, stable bounded cursor, snapshot reads, checkpoint and disposable backup | `test_ledger.py`, `test_faults.py` |
| `packages/migration/` | Hashed/unit/version/continuity manifest, read-only dry-run, atomic idempotent staging, disarmed disposable rollback copy retaining new history/totals and consumed intents | `test_migration.py`, `test_faults.py` |

The controller packages from WP1A/B/C and all219 prior tests are unchanged. `REGRESSION-BASELINE.sha256` hashes their71 tracked source/test assets. No runtime dependency was added; development tooling remains pinned in `requirements-dev.txt`.

## Accounting and immutable evidence

Raw inputs keep original values, source IDs, timestamps, method and quality. Derived balances require an explicitly qualified topology and signed GRID, reject declared group/load/phase and runtime source-dependency overlap and preserve negative/out-of-range residuals as conflict. Test9.237kW is accepted under an explicit synthetic12kW bound; it is never rounded to9kW for energy. Pump pulses and3/6/9 estimates cannot establish a heater session or measured kWh.

Planner proposals can be explicitly queued as lineage-bound forecast records, preserving request/model/weather issue metadata and their energy period. An old amount without a known energy scope is retained as source evidence but is not promoted into a verified budget reference. The canonical stream origin is immutable and separate from interval postings. Finalized intervals cannot overlap even after counter/power method switches. Duplicate event/post/recovery identity is idempotent, conflicting identity is rejected. Late measurements are retained as raw facts and cannot automatically change finalized energy. Direct instantaneous power produces derived integration, counter differences confirmed interval energy, estimated inputs estimated energy; unknown coverage stays null. The known total excludes estimated energy and adds administrative recovery separately. No present reading is multiplied by past missing hours.

Unknown gaps and incomplete unposted periods remain in cycle budget coverage. Initial/prestart/latest/original energy are distinct; negative known remaining is a lower-bound overrun, not evidence of savings. Dated prices, unknown price and estimated cost are separate. Partial counter/day/recovery allocation cannot become measured energy or an actual bill. Seeded synthetic integration matches its analytic piecewise-constant reference to11 decimal places; this is arithmetic evidence, not physical metrology.

Initial/prestart cannot be invented after cycle reference. Original selection uses actual issue<=reference−12h and point coverage, retains planned energy and all curve lineage, and permanently records missing when unavailable. Later history does not backfill it. Comparison uses exact reported direct temperature, and gaps remain missing.

Recovery is a separate admin fake API. Preview does not write. Apply verifies expected total, current archive head, exact disposable backup and evidence hashes, then atomically appends the request and unknown-coverage claims. Generic archive append cannot create a recovery or unproven known energy. A second claim cannot count the same gap twice; repeating the same request preserves its result. Original unknown records remain intact.

## PR16 independent review corrections

Review [6620487295](https://github.com/dragonidf/ha-heating-2/pull/16#issuecomment-6620487295) examined `97bb0dd7c681a2e45ceeeb029fec98312021381d`. Before source changes, three new tests failed on that exact code: random recovery hash was accepted, missing manual state did not persist pause, and queued initial forecast had no scope. `REVIEW-RED.txt` preserves that run. The prior statement about verification of recovery evidence hashes described intended behavior and was incorrect for that reviewed SHA.

1. **Recovery proof:** `RecoveryProof` is immutable and content addressed by `checksum(encode(proof))`. It binds stream/continuity, exact unknown IDs, contiguous time window, physical/source identities, direct counter endpoint archive IDs, method, quality and quantity. The worker independently checks the two immutable KWH readings, direct/independent VALID provenance, exact observation times and receipt availability, nonnegative delta and requested quantity (absolute arithmetic tolerance 1e-9 kWh). Neither a backup nor approval supplies energy evidence. Preview and apply both validate proof; summary and budget revalidate historical recovery, failing closed on old unproven records. No old records are rewritten or silently grandfathered. Unknown/estimated evidence cannot qualify. Approval/CAS/current backup and unique gap claims remain required. Tests cover substitution, missing/wrong proof/source/gap/time/quantity, noncontiguous coverage, duplicate claim, zero delta, invalid quality, readback, lost acknowledgement and subprocess termination before/after commit. Synthetic direct readings are explicit metrology premises, not authenticated household measurements; physical source qualification remains BLOCKED.
2. **Ownership:** adapter admission/order/receive freshness is separate from reading qualification. A current fresh external thermostat assertion establishes durable UNKNOWN_CHANGE even when state is missing or aged. Observation-clock rollback, old sequence/receive time, future/delayed assertions and replays cannot manufacture new ownership evidence. Every source author label, including a claimed automatic echo, can only revoke automatic ownership; it never authenticates a writer or an observed HEAT/STOP. The sealed fake feedback carries `action=None`, `manual=False`, `writers_known=False`. Later healthy sensors cannot resume; a current fake control capability must explicitly resume, reconcile and produce a new eligible plan. Independent STOP and fan ownership remain unchanged.
3. **Forecast budget:** queueing validates contiguous trajectory coverage and nonoverlapping segments within the request horizon. Qualified synthetic power must belong to the request stages. It records `TimeWindow(reference, horizon_end)` and integrates only segment overlap with that window; a half-slot reference excludes the prefix. Outside-horizon reference, absent power/qualification or missing trajectory coverage yields no scoped energy amount (`None`). End-to-end queue→flush→finalize→budget tests verify reference/remaining/overrun, known zero, unknown tails and immutable initial identity. Original12h and historical unscoped behavior remain covered by existing tests.

All315 earlier test methods remain present. Recovery fixtures now archive real synthetic typed counter proofs instead of dummy hashes; the prior whole-plan forecast assertion is strengthened to the correctly scoped amount. No quality threshold or accepted WP1A/B/C source/test asset changed. New coverage is in `tests/wp2a/test_review.py`;86/38 matrices retain their offline/blocked limits. Final-head CI evidence is linked in the PR description and checks after publication, without an untested follow-up documentation commit.

## Fault, boundary and integration verification

The full suite contains **340 tests:219 accepted regressions plus121 WP2A tests (96 original plus25 review regressions)**. Strict mypy passes; reported branch coverage is **97%**, with the existing95% minimum unchanged. No skip/xfail, removed assertion, lower threshold or production exception was introduced.

New tests cover alias freshness/skew/conflict, scalar/unit/capability/schema errors, signed GRID and overlap, held45s vs long unknown gap, zero vs missing, pump/nominal-stage separation, analytic trajectories, reset/jump, delayed/reordered points, immutable counters/intervals, historical tariff and DST boundaries, cursor watermark and cross-archive scope, malformed/unknown/NaN JSON, settings permission/CAS/readback failures, reconnect, fresh vs stale manual change, untrusted echo/STOP, explicit grant revocation, event storm and visible saturation. Source facts survive control coalescing through the separate bounded raw journal.

Emergency tests disable all critical-store reads and stall the evidence writer while STOP still completes. After active fake HEAT, absent grid, aged data, clock rollback, revoked permission or disconnect stops even without a queued command. Fan manual ownership is independent of boiler manual pause, and night expiry cannot stop a supported fireplace demand. These tests describe an in-memory fake actuator, not equipment behavior.

SQLite tests use actual transactions, WAL busy locking, read-only mode, immutable triggers, schema rollback, tampered checksums/materialized origins/frontiers, corrupt/missing files and journal-mode/linked-library rejection. Disposable subprocess kills before/after commit, finalization, schema migration, import and checkpoint recover an atomic prefix or block; no implicit reset/replay occurs. A path-restricted Linux preload injects **actual fsync EIO and write ENOSPC** only into the temporary evidence DB. The independent fake STOP still succeeds and no HEAT is created. The C fixture is test-only and is never linked to a runtime package.

The static import graph and fresh-process socket/DNS denial exercise the synthetic integration, migration and STOP. There is no real HA SDK/service client or enabled `custom_components` directory. Both database classes require explicit disposable roots; source/evidence paths cannot be real HA/Recorder databases, and symlink replacement is rejected.

## Synthetic migration rehearsal

`LegacyBundle` is a strict synthetic legacy-shaped contract, not an importer for unverified private formats. Its canonical checksum binds every field. Per-entry source/target schema, units, checksum and continuity key cover total/day counters, model coefficients, plan, saved fan/night state and fan policy, settings/control state, one-shots and frozen original curves.

Read-only `dry_run` is deterministic and leaves the input unchanged. Staging commits all records/origins and a disarmed receipt together, or none. Retry is idempotent. Counter/model/original hashes and values survive exact round-trip; parity tests assert counter totals to9 decimal places, stronger than the10⁻⁶kWh synthetic target. No direct state import arms the fake controller.

Rollback creates a consistent disposable SQLite copy, retains every post-freeze raw/energy event, preserves newer consumed/unknown one-shot outcomes, returns updated canonical counter totals, and remains STOP/disarmed/unreconciled. It never overwrites source data with an older snapshot, rewinds consumption, resets utility meters, edits the legacy repository or creates a real backup. Missing B01/B02/B03 evidence still blocks real mapping/migration claims.

## Reproduction, environment and exact-SHA CI

```sh
python -m pip install -r requirements-dev.txt
python -m tests.fixtures.build_sqlite
# Use a disposable regular filesystem for SQLite durability fault fixtures.
LD_LIBRARY_PATH=/tmp/heating-wp1b-sqlite-3510300 make check
python -m tests.wp2a.benchmark
sha256sum --check docs/wp1a/SHA256SUMS
sha256sum --check docs/wp1b/SHA256SUMS
sha256sum --check docs/wp1c/SHA256SUMS
sha256sum --check docs/wp2a/REGRESSION-BASELINE.sha256
sha256sum --check docs/wp2a/SHA256SUMS
```

Local Python3.12.14 uses qualified SQLite3.53.1; Python3.13.5 uses the temporary pinned SQLite3.51.3 build. Full local outputs are in `LOCAL-VALIDATION.txt`. The accepted test builder verifies SQLite source before building only in disposable space. Actual host benchmark observations are in `BENCHMARK.json`; they are not a target N100 qualification or a30-day soak.

[WP2A CI](https://github.com/dragonidf/ha-heating-2/actions/workflows/wp2a.yml) explicitly checks out PR **head SHA** and runs Python3.12/3.13/3.14, full tests/type/coverage, all manifests and the benchmark. Its last step prints exact tested SHA, Python, test count, run ID and actual linked SQLite/source-ID qualification. Retained WP1A/B/C PR workflows also run the full suite: twelve checks across four matrices. Final run links/conclusions are recorded in PR checks and description, avoiding an untested evidence-only commit. Python3.14 is verified by that final-head matrix, not assumed from local3.12.

The already-approved WP2A governance update in main changed README after older manifests. Only that existing README hash and nested manifest hashes were refreshed in WP1A/B/C evidence; previous code/tests/reports were not rewritten. Canonical86 requirements and38 scenarios remain unchanged. The additive coverage CSVs distinguish verified offline aspects from inherited/deferred and blocked acceptance.

## Critical limits and handoff

- **G1/B01–B08 remain BLOCKED.** No private bindings, actual topology, saved history, command-author inventory, calibration, OEM behavior or physical power/running evidence was verified here.
- Native HA SDK/auth/config/options/async compatibility is **NOT_TESTED**. The fake capability/registration contract is not a running integration or an actual authentication implementation. Calls into the evidence API are explicit worker work, not HA event-loop code.
- Fake source capacity is4096 raw events per replay instance,128 ordinary pending events plus128 reserved ownership events; status exposes pending/lost work. Pages cap at256, atomic append batches512, finalization10000 raw points per call. Larger replay/import work must be explicitly partitioned, never silently truncated. Summary/verify can traverse the archive with bounded memory in the independent worker; target-host latency/retention remains unqualified.
- SQLite WAL/FULL, crash and EIO tests qualify this disposable software test environment only, not target filesystem hardware, real power loss or actual device OFF timing. No N100, seven-day/three-cycle shadow or household energy accuracy claim follows.
- Source/model coefficients, fan levels, phase/power limits, dates, prices and physical IDs are **synthetic premises**. 3/6/9 remain estimates/scenarios; unknown evidence is not nominal heat. B08 remains unresolved and no global180min session cap was added.
- No production HA read/write/install/reload/restart, real network/device call, actual backup/import, private-data use, legacy modification, live shadow, deployment, merge or WP2B was performed.

Ready for independent **offline WP2A review**, subject to final-head green CI. Independent QA decides acceptance; this report is implementation and self-test evidence only.
