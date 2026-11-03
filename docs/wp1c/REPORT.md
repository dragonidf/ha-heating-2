# WP1C — offline implementation and self-test handoff

WP1C implements the approved Issue #11 offline package on base `2106166a4e60ffa8bc7d5870f46f98131f9084bf`. It is submitted for independent review, not independent acceptance. The PR stays open; no deployment, merge or WP2A is authorized. Production and the legacy repository were not changed or contacted for live data.

## Delivered behavior

- `packages/thermal/`: frozen typed intervals, versioned/bounded two-state coefficients, hourly-unit Euler model, saved-state cooling observer preserving original observation age, bounded outside/power/fire/ventilation/external-gain uncertainty. Raw return probe and stored-state limits are separate.
- `packages/planner/`: deterministic bounded5min search, 24h/default and72h reserve policy, Kyiv07:00 cycles and DST-safe UTC durations, day/sleep and strict/night/comfort policies, synthetic3/6/9 and explicitly calibrated AUTO scenarios. Needed/safe continuous morning30min based on the exact07:00 coast prediction and reserve to the next confirmed allowed heat, qualified elapsed-session credit, outage-driven<=180min advance, explicit shortfall/block/exhaustion, dated prices and unknown price, soft known-spend budget and unknown coverage. Current raw return/room age/grid/permissions are checked; every future ON segment is conditional with typed reason provenance. Its forecast feasibility cannot authorize actual heat. The bridge rejects missing reason provenance or a future unconditional segment.
- Provider normalization: weather issue/receive/provider horizon and bounded interpolation without extension; outage date/region/queue/coverage/emergency/freshness and content dedup; confirmed next available slot never extrapolates unknown days. These functions consume records and do not fetch providers.
- Stable replay and evidence:19 small refreshes retain a schedule only after current safety replay. Material changes and failed replay produce explicit causes. Retention now requires a zero-change bound on every semantic safety/objective input; publication-only refreshes may differ only while the weather-validity classification stays unchanged. The fixed replay must reproduce feasibility, morning obligation, continuous duration, comfort deficit, energy, overrun, uncertainty and trajectory. The caller flag cannot authorize arbitrary changed inputs. Initial/prestart/original12h curves are immutable and separate from latest. Exact cutoff, source times, checksum and coverage determine original evidence. Missing original stays missing. Unknown actual intervals break comparisons and do not become claimed savings.
- `packages/learning/`: offline staged ridge fit, parent/day coefficient limits, independent local train/holdout dates, seven horizons1/3/6/12/24/36/48h and explicit required regime partition. Metrics include signed maximum underprediction. Promotion requires approval/CAS and receipt equality against recomputed prospective backtests; rejection/pending never mutates champion. Revisioned rollback and pure Kyiv10:00/20:45 due-slot catch-up/dedup.
- `packages/fan_policy/`: ignition/trend, start/intense/keep, continuous300s cool-down, fast-off and >90s continuity reset, night900s arbitration, night cap, manual ownership, explicit STOP and permission/grid denials. Stale sensor removes demand without reporting observed extinction. Speeds38/42/50 occur only in synthetic tests.
- Strict versioned JSON contracts and an explicit bridge to the accepted WP1A `Plan`/reducer. No compute function calls `FakeActuator`, store or external API. A bridged proposal can still be denied by actual grid, manual/STOP, missing readings, stale accepted input or independent kernel limits.

## Provenance and parity

Read-only public reference: `dragonidf/ha-heating-ai` commit `db7d7ce9c53e4e88c1c27ee10e1f53d6cce10426`, `apps/heating_ai/heating_model.py`, blob `5dd99bd097af40f7796a65ff8495e7ae8162193f`, SHA256 `9028b4bd811d37052b4c4b01b226d0ddb6f8d88871479483c07bd547a20bdc5a`. Source equations at lines31–36 and declared bounds/defaults were inspected. The local read-only reference copy was hashed and matched that source checksum.

For hours `h`, the reproduced baseline is:

```
room'   = room + (floor_air*(stored-room) - room_loss*(room-outside)
                 + fire_gain*max(0,fire_delta))*h
stored' = stored + (heat_gain*power_kw - floor_decay*(stored-room))*h
```

`floor_air`, `room_loss`, `floor_decay`, `fire_gain` are hourly rates; `heat_gain` is °C/(kW·hour). Ventilation is an explicit dimensionless loss multiplier and external gain is an explicit interval in°C/hour; zero values are premises of the baseline parity fixture. Bounds remain `.001–.20`, `.001–.15`, `.01–1.5`, `.02–3`, `0–.15` respectively. One hundred seeded synthetic points reproduce the pinned equations. This establishes arithmetic/units parity only. The invented test coefficients `.04/.02/.10/.60/.02` are not household calibration. Actual saved champion, state, sensor mapping and physical parity remain **NOT_PARITY_VERIFIED / BLOCKED B01/B02/B03/B05**. No legacy forecast, training archive or measured household accuracy was fabricated.

## Validation and reproduction

The full suite contains **219 tests: all155 accepted WP1A/WP1B tests, all48 original WP1C tests, and16 review regressions**. Old source and regression files are hashed in `REGRESSION-BASELINE.sha256`; none of those files was changed. Strict mypy and branch coverage retain the existing95% minimum. No skip/xfail, exclusion or reduced acceptance threshold was added.

Synthetic tests exercise cold/warm/fire24h/72h, no need/overheat, budget/gaps, unknown power/AUTO, permissions and raw return age/receive timestamps, partial/interrupted morning sessions, outage advance/move/removal, DST and repeated-hour contracts, immutable originals before/equal/after12h cutoff, stale bridge stamps, wire corruption/nonfinite/fuzz/full72h payload, learning leakage/quality/daily zero/precision boundaries/forged receipts/CAS/rollback, and fan threshold edges/stale/gaps/manual/STOP/night ordering. Seeded safety properties and fresh-process external-effect denial supplement the import graph guard. An external20s process deadline bounds six24/72h scenarios; injected cancellation and deterministic work caps leave no executable segments on exhaustion. This harness does not qualify a production worker kill deadline.

Run in a disposable checkout using pinned `requirements-dev.txt`:

```sh
python -m pip install -r requirements-dev.txt
python -m tests.fixtures.build_sqlite
LD_LIBRARY_PATH=/tmp/heating-wp1b-sqlite-3510300 make check
python -m tests.properties.benchmark_planner
sha256sum --check docs/wp1a/SHA256SUMS
sha256sum --check docs/wp1b/SHA256SUMS
sha256sum --check docs/wp1c/REGRESSION-BASELINE.sha256
sha256sum --check docs/wp1c/SHA256SUMS
```

The store tests need a disposable real filesystem via `TMPDIR`, not a production database or tmpfs for durability assertions. The existing builder downloads verified SQLite3.51.3 into temporary test space only. Locally Python3.12.14 links qualified SQLite3.53.1; Python3.13.5 is tested with the existing temporary pinned3.51.3 build. Python3.14 and all three final-SHA jobs are covered by [WP1C CI](https://github.com/dragonidf/ha-heating-2/actions/workflows/wp1c.yml); retained WP1A/WP1B PR workflows also execute the full suite. The new workflow explicitly checks out PR head SHA, records exact tested SHA/Python/test inventory/linked SQLite in its final step, and prints benchmark measurements. Final CI run URLs/conclusions belong to the PR check records and PR description, so adding results does not invalidate the tested code SHA. Local environment/test/coverage and benchmark observations are in `LOCAL-VALIDATION.txt` and `BENCHMARK.txt`.

The approved WP1C documentation in main had changed README after the prior manifests were written. Only that README hash and the resulting nested WP1A-manifest hash were refreshed in WP1A/B manifests; previous code/test evidence remains intact.

## Traceability and remaining limits

`requirements-coverage.csv` contains all86 canonical requirement IDs; `scenario-coverage.csv` contains all38 scenario IDs. They add WP1C evidence and retain prior phase status. `PARTIAL_SYNTHETIC_PASS` denotes the described offline aspect, never complete physical/integration acceptance. Canonical requirements/scenarios/specification were not rewritten. UI, live adapters, ledger recovery, physical commissioning, archive deployment and migration retain prior deferred/blocked status.

G1/B01–B08 remain BLOCKED. G2–G9 do not pass from this PR. In particular:

- No verified household coefficients/duty/topology/limits, saved state/original curves, external command authors or report permissions. Qualified test flags are invented premises.
- No target N100 SLO, target SQLite/filesystem durability, actual power loss, OEM protection, physical OFF/ON timing, fan-running evidence or real energy/accuracy claim.
- Planner is a bounded beam heuristic. Exhaustion, capacity and model-predicted shortfall are not proofs of physical infeasibility. Conditional future heat is not an execution permit. Unknown source values require caller-supplied bounds; callers must not manufacture VALID quality.
- Pure evidence/promotion/due-slot APIs have no persistent archive, atomic publication service, background worker or scheduler. Those integration components and live classification/transport require a later separately authorized phase.
- No global180min session limit was introduced. Morning outage advance is a separate <=180min rule; B08 remains unresolved, and legacy one-shot semantics remain unchanged.

The package is ready for independent **offline WP1C code review**, subject to green final-SHA CI. It does not authorize household use or progression to WP2A.


## Consolidated independent-review correction

Source: [review6612587291](https://github.com/dragonidf/ha-heating-2/pull/13#issuecomment-6612587291) on `79c67084ca211f39890a272914faa4f4ebffcd04`. All three findings were reproduced **before algorithm edits** by the first three tests in `tests/unit/test_wp1c_review.py`: stale zero-heat retention, sticky morning need despite coasted fireplace warming, and unconditional future ON under unknown actual grid. All three failed on the reviewed code. `RED-REPRODUCTION.txt` preserves that focused run; the later bridge hardening was also reproduced before its fix. These are offline source defects, not observed production-controller incidents.

1. **Retention:** every semantic input has a verified zero-change bound. The retention fingerprint includes model/state/uncertainty, all slots/targets/grid/prices, windows, effective powers, morning/confirmed credit, budget, guards and algorithm limits. Only input-hash/publication times can differ; the weather-current predicate is part of the fingerprint. Any numeric weather/state/target change, including a tiny one, triggers a full search. A fixed replay must also reproduce the previous objective/trajectory exactly. Missing old retention evidence fails closed. Both warm→cold and cold→warm now search correctly with `material_change=False`, and even when the input hash was accidentally not updated. Nineteen publication-only refreshes retain identical feasibility/objective. This conservative zero-tolerance rule avoids an invented household materiality threshold.
2. **Morning need:** the mandatory30min flag is derived at the exact injected07:00 deadline (including inside-slot interpolation), and at predicted states through the next confirmed normal/allowed heating opportunity. Unknown availability cannot end the reserve. Before07:00, a safe coasting warm-up that already meets deadline/reserve is not counted as a boiler deficit within the morning window; legitimate comfort deficits before that window and after07:00 still count. Cold reserve, missing grid, overheat and qualified elapsed credit remain separate from physical permission. An uncovered deadline is not fabricated; ON reasons include missing morning horizon and no mandatory morning claim is made from an earlier prefix alone.
3. **Future uncertainty:** all slots starting after the injected present carry `future_execution_unverified`, independently of provider-normal grid or a synthetic-qualified model. Missing/OFF actual grid, stale/missing raw return, stale/estimated state, unknown scheduled grid and other source gaps are explicit per-segment reasons. Safe present-time eligibility is separate. Segments with different reason sets remain separate even if both are conditional. Existing WP1A actual-grid/manual/upper/STOP guards remain unchanged; bridge validation adds a fail-closed provenance/future-conditional check.

Sixteen new tests cover the reproductions and adjacent changes in target/weather/uncertainty, cold→warm cancellation, unchanged19-refresh objective, stale or missing retention evidence, modified objective, natural fireplace warming, reserve/no-grid/upper, legitimate intervening comfort, exact deadline/cancellation, normal-vs-unknown future forecast and current OFF/UNKNOWN/missing/stale return. The full219-test Python3.12/3.13 local checks and final-SHA nine-job CI retain strict mypy,98% reported branch coverage and the95% minimum. Final-SHA job URLs/results are recorded in the PR description; the exact-SHA workflow step remains the evidence source. All previous tests are unchanged. G1/B01–B08 remain BLOCKED; no merge, WP2A or production work is included.
