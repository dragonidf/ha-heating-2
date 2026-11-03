# WP0 — runtime, dependencies, resources and limits

**Target compatibility: BLOCKED B06.** A reported package version is not a linked-library or filesystem durability test. All new2.0 SLOs below remain unmeasured; this audit did not benchmark production, open a new control database, install an integration or restart any service.

## Observed environment versus proposed target

| Boundary | Evidence available | Conclusion / missing proof |
|---|---|---|
| HA Core | H07 health reports Core2026.10.4, Python3.14.9, HA OS installation | Relevant native integration API/runtime target. Pure legacy CI on3.12/3.13 does not certify a new HA integration on3.14. Need HA-version test harness and lifecycle/auth contracts in later work. |
| Supervisor / HA OS | H07 reports Supervisor2026.10.5, HA OS18.4 | No install/restart/reconfiguration performed. Actual storage flush/device behavior not established by these versions. |
| AppDaemon App | H07 App version0.19.3, started; declared python_packages Telethon/tzdata | App packaging version is not the exact embedded AppDaemon/Python/SQLite build. Heating imports Hass API, timers, callbacks, submit_to_executor, publish/get_state and render_template. Other apps share lifecycle/dependencies; do not remove their packages. |
| HACS | H07 reports2.0.5; pinned source hacs.json and release workflow inspected | Legacy installation uses nine app modules and generated manifest; current coordinator stops/starts all AppDaemon. New integration/compute lifecycle and major protocol compatibility are not implemented. |
| Legacy runtime code | H01 reports0.3.21 and nine hashes matching public0.3.21 manifest | It is one commit newer than pinned0.3.20. Runtime self-report only; direct module/YAML filesystem export unavailable. Tick caching in0.3.21 is not silently credited to0.3.20 test evidence. |
| Recorder SQLite | H07 reports SQLite3.53.4 | Numerically above O09 threshold, **only for the reported Recorder engine**. Does not prove both future control-store and compute Python linked libraries, build options, actual WAL mode or local FS suitability. Never open/edit Recorder as a migration database. |
| New SQLite contract | Approved ADR04/O09 requires linked≥3.51.3 or documented patched3.44.6/3.50.7; WAL + synchronous FULL read back; local single-host FS | Check each actual packaged process with sqlite3.sqlite_version and documented patch provenance, then isolated WAL/checkpoint/ENOSPC/BUSY/crash/restore tests. Unknown backport is blocked. This is not permission to upgrade HA or activate WAL in production. |
| Storage mounts / hardware | No current mount/type/fsync/backup-restore export for either future store | B06. Do not infer local disk from paths or VM/OS. SQLite WAL shared files must remain on the same host with supported locking; NFS is unsuitable. Hardware ignoring flush is not fixed by a PRAGMA. Sandbox overlayfs is not target proof. |
| HA entity APIs | Targeted states/registry/helper/automation/resource reads succeeded | Six sampled dynamic AppDaemon sensors lack registry entries despite existing states. Reusing IDs/unique IDs/statistics needs supported ownership handling; no direct .storage or Recorder edits. |
| Thermostat / fan capabilities | H01 registry/state capability interfaces read | No independent relay or airflow feedback proven; Tuya echo can be optimistic. Profile3/6/9/AUTO describes hardware selection, not an available stage-switch service. |
| Authentication / protocol | Legacy UI uses HA session and helper/events; no separate new compute protocol exists | Future authenticated HA WS read/control/admin checks, expiry/replay protection, installation binding and major-version handshake need backend tests. No long-lived HA token in browser; no public compute port assumption. Current external-client authority remains B04/B07. |
| Initial native integration install | No new component installed; current custom integration registration untouched | First file installation may require HA restart to discover/register the component. Plan a separate approved preparation window, load hard-disabled/SHADOW, and prove reload/unload support before cutover. Do not promise restart-free initial installation or put a restart inside ownership transfer. |

## Isolated baseline verification actually performed

Unchanged legacy files: all103 Git blobs verified before tests and checked again before publication. Sandbox Python3.12.14, Node24.19.0, linked SQLite3.53.1; these are **not** the production compute build or N100 benchmark environment.

Declared test dependencies were installed only into temporary sandbox storage: Jinja2=3.1.6, Hypothesis=6.170.14, tzdata=2026.6; transitive MarkupSafe=3.0.4, sortedcontainers=2.4.0. The source declaration leaves tzdata with a lower bound and transitive ranges; it is not a complete runtime lock/SBOM. Runtime AppDaemon dependencies and future integration/compute packaging require separate manifests; no production package was installed or changed. No vulnerability-database pass is asserted.

| Check | Actual result | Interpretation |
|---|---|---|
| `make check` | PASS: compileall, generated JS/release manifest check, JS syntax and HACS layout/JSON | No generated source rewrite; all source bytes remain pinned. |
| `make test`, Python | **535 tests, OK,79.919s**, no skip/expected-failure reported | Fake HA and numerical/public fixtures; not physical tests, new integration acceptance or SLO proof. |
| `make test`, JavaScript | **50 pass,0 fail,0 skipped**, Node duration212.247ms | Existing frontend unit suite only. No new UI or live HA browser acceptance. |
| Initial restricted-sandbox run | Aborted after an asynchronous history-dispatch test stalled; no full pass claimed for that run | Standalone unchanged test with10s traceback deadline stalled in event-loop select. Same four tests with network-enabled sandbox passed in0.021s; full unchanged suite then passed in that execution mode. No assertion skipped and no source fix. Exact sandbox cause not established. |
| Baseline CI | E03 exact-SHA Python3.12/3.13 jobs and release succeeded | Historical CI source includes Chromium/WebKit and a11y. Those browser suites were not rerun locally; no new2.0 browser/device check performed. |
| New2.0 tests | NOT EXECUTED; no new implementation | All86 T-IDs remain specified_not_implemented and38 scenarios planned_not_executed. |

Full successful local baseline log SHA-256: `a41aca1221521020a20ba21cacd8d6de9469d490df47854dc382e2c632a3c88c`. Log remains outside the repository; this public checksum is not a private household archive hash.

The existing `tools/check_validation.py` also completed on unchanged public fixtures: baseline planning563.507ms, expanded planning888.003ms (three passes), cached replay7.025ms, fake-I/O fast tick1.671ms, stress evaluation10.942ms, average journal write8.637ms. Synthetic one-hour journal339702bytes extrapolates to108.85MiB/14days. These are single-run sandbox measurements, not percentiles, real archive volume, target N100 performance or2.0 SLO passes. The planner remains unbounded by a killable process deadline despite this fast fixture. Metrics SHA-256: `c08a927eeaeb4f4971c46e744be5c8d10782120f4fe46d6c0d94a5578e30dbff`.

## Resource/failure analysis

The pinned planner uses single-flight executor tasks with copied inputs, key rejection and current-time replay. It does not provide a killable process deadline, resource isolation from shared AppDaemon, or guaranteed fast disk paths. Local learning still runs inside tick. JSON save and journal preparation/compaction share runtime and locks; atomic rename is not a cross-record crash transaction.0.3.21 improves repeated state reads, not all process/storage isolation requirements.

The approved split is coherent: pure kernel/reducer → one HA gateway with dedicated bounded critical writer; separate compute planner/learner/evidence workers. Evidence compaction, AI, history queries and learning cannot hold a lock needed for stop intent. Only qualified HEAT waits for durable prepare (deadline250ms); safety OFF bypasses normal queue/disk wait and records audit afterward. Corruption fails closed for new heat without erasing original evidence.

Legacy archive defaults14d/seven protected days and dynamic256MiB–1GiB budget do not satisfy new30/90d retention automatically. Actual daily volume, source exports and target FS capacity are BLOCKED; proposed2GiB evidence budget and reserve max(2GiB,10%FS) require measurement. Shared inlet/GRID dependence prevents converting agreement of balances into independent confidence.

## Measurable acceptance limits — all planned, none passed by WP0

| Target | Required measurement in isolated future stand | State |
|---|---|---|
| Kernel p99≤10ms on N100 | ≥100000 typed snapshots; import-boundary test; CPU/clock/environment identified | NOT IMPLEMENTED |
| Safety event→stop intent p99≤250ms, max1s | Monotonic source/receive/reducer timestamps under planner/learner/history/I/O stress | NOT IMPLEMENTED |
| Stop intent→service dispatch≤1s | Responsive fake/local HA and gateway timeline; physical relay latency separate | NOT IMPLEMENTED |
| Control tick1s; schedule lag p99≤250ms |24h stand soak; bounded coalescing; preserve safety/manual/grid event order | NOT IMPLEMENTED |
| HEAT durable prepare≤250ms | Real control DB locks/slow disk/full disk; no HEAT on timeout; OFF not delayed | BLOCKED target runtime B06 |
| Planner baseline≤2s, hard≤10s | Real subprocess timeout/kill/stale completion; preserve best validated candidate or search_incomplete | NOT IMPLEMENTED |
| Echo≤10s; physical response initial120s,≤2 retries | Independent receipt stages, fixed incident deadline/reconcile, later approved physical test | BLOCKED B05 |
| History7d cold p95≤2s server; paint≤3s LAN |30d indexed dataset, range flood/cancel/reconnect, browser timestamps; not MCP duration | NOT IMPLEMENTED |
| UI local pending≤100ms, bounded≤10s | Two clients/offline/auth failure/save conflict, keyboard/touch/theme/text matrix | NOT IMPLEMENTED |
| Retention/pressure and DB integrity | Actual volume, ≥30d raw/90d forecast, protected legacy, backup API/restore/crash/WAL tests | BLOCKED B02/B06 |

No short MAE, mock latency, heartbeat or one synthetic run substitutes for physical control,10 qualified energy cycles, seven independent forecast days or long-horizon validation.
