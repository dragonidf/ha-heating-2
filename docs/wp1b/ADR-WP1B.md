# WP1B — offline durability and fake command execution

Authority: owner approval 2026-11-03, Issue #7 and WP1B-TASK.md. This implements an isolated simulation. It grants no HA/device authority and closes no G1/G3 gate.

## Boundaries and protocol

The seven WP1A contract/kernel files stay unchanged and pure. File/SQLite I/O is isolated in `packages/control_store`; `packages/simulator` imports only pure contracts/kernel, that store, and in-memory synchronization/data helpers. It accepts the exact FakeActuator class, whose send operation only appends an immutable FakeCall in RAM. There is no device identifier/binding, client URL, service sender or network implementation. The test-only SQLite source downloader/compiler is outside these packages.

Store paths must be an existing, dedicated `heating-wp1b-*` directory directly below the explicitly selected temporary root. Database name is fixed; symlink/hardlink database files are rejected on open. Missing, truncated, unknown-version or corrupt stores cannot reset themselves to defaults. This is not an interface to open a production/legacy database.

Contract envelope 1.0 remains strict. Store protocol is `heating-offline-control/1;contracts/1.0`; SQLite `user_version=2`. The synthetic v1 rehearsal contains metadata/control/events/boots; migration adds outbox/one-shots transactionally. Unknown schema/protocol rejects without reinitialization. Version rehearsal does not implement import of any legacy or private state.

Control state/policy and every event/decision, outbox intent, receipt and one-shot have versioned payloads plus SHA-256 checksums. Index identity/fence bindings are checked separately. Checksums detect corruption; they are not authentication against an attacker able to rewrite both data and hash. State/configuration changes use explicit transaction revision CAS; booleans are not revisions. Owner acquisition, manual/OFF latch release and replay frontiers cannot be forged by ordinary transitions. Event identity is immutable/idempotent; receipt progression cannot rewrite known facts. Late duplicate ACK/echo is ignored without regressing stored evidence.

Critical simulation capacity is explicitly bounded: 4,096 events, 256 outbox records and 256 one-shot markers. Capacity exhaustion rejects a new critical write; no protected source is deleted. This is an offline software bound, not an energy/session cap or production retention policy. Retention/archival and practical long-lived target sizing are future work.

## SQLite and filesystem qualification

Only actual linked SQLite major 3 at least 3.51.3 passes the current minimum WAL-reset gate. Older purported backports need independent provenance and are rejected here; future major versions are not presumed compatible. Every open reads the runtime/source ID, store protocol and actual WAL/FULL settings. Ordinary lock timeout is 25 ms. Transactions operate on bounded critical records; no model/history/learning work is included.

Native CI SQLite 3.46.1 is unqualified. The isolated test harness builds official SQLite 3.51.3 from the pinned archive:

- URL: `https://www.sqlite.org/2026/sqlite-amalgamation-3510300.zip`
- SHA-256: `acb1e6f5d832484bf6d32b681e858c38add8b2acdfd42ac5df24b8afb46552b4`
- Source ID: `2026-03-13 10:38:09 737ae4a34738ffa0c3ff7f9bb18df914dd1cad163f28fd6b6e114a344fe6d618`
- Compile: shared/PIC, `SQLITE_THREADSAFE=1`, `-O2`; library and source remain disposable. `LD_LIBRARY_PATH` applies only to the test process/job. CI asserts the actual linked version **and** source ID before running the suite.

No system/production library is replaced. WAL/FULL readback, cross-process locking, OS-acknowledged file/directory fsync, crash recovery and corrupt/full/read-only failures prove only the declared test environment. A container overlay or tmpfs cannot establish physical media flush behavior or survival of power loss. Actual target packaging/FS/SQLite qualification remains B06 BLOCKED.

## Prepare, send and independent stop

There is one fake writer capability per FakeActuator. Every Simulator construction reserves it and performs a durable new boot/owner transition; even a previously reconciled persisted HEAT state cannot activate it. Old writer capabilities are rejected. The ordinary queue holds at most one latest desired HEAT; STOP/manual/epoch changes cancel it.

HEAT requires a committed reducer transition, matching current revision/epoch/intent and live guards, durable prepare, then a single durable send claim. Prepare and optional one-shot consumption share one transaction. A claim records UNKNOWN before the fake send: a crash between claim and send cannot grant a second attempt. After send, SENT/ACK/echo are distinct committed facts. A commit, ACK or echo never creates physical power evidence.

Prepare admission budget is 250 ms using a store-side monotonic deadline, a bounded busy wait and SQLite progress cancellation. A late/failed prepare can leave a committed PREPARED record, but cannot authorize HEAT; it is fenced on restart. Actual fsync may block a worker longer than the deadline: this is not a hard OS I/O cancellation guarantee. STOP neither acquires that transaction lock nor waits for its completion.

The harness advances virtual clock/snapshot explicitly through `update_inputs` and events. Ingress rejects backward monotonic/as-of/grid epochs or UTC rollback beyond the existing tolerance. While HEAT is desired, a newly unsafe/expired input immediately fences demand and clears pending work/plan/reconcile readiness; an older queued pump call cannot erase that fact and re-arm. Its omitted audit is explicitly counted. Pump checks latest inputs again after prepare/claim, as well as current durable revision/state/policy. Changes in grid, ages, limits, clock, intent/plan expiry, manual owner or configuration deny emission. Asynchronous measurement cadences retain WP1A per-source age rules. There is no autonomous timer/daemon or claim of live sampling here.

Authoritative updates in the simulation pass through the coordinating actor; a different FakeActuator represents a different fake device. Arbitrary external writers, real distributed command transport, atomic coupling of hardware with a DB transaction, real service latency and installed bindings are unqualified future boundaries, not capabilities of this library.

Emergency assertions require a FakeAuthority-issued, event-bound in-process capability. A JSON `authorized=True` alone is rejected. This models a trusted future boundary; it is not backend authentication. The pure reducer maintains boot/owner and the separate emergency replay frontier. STOP demand is appended to fake calls before ordinary persistence, or without any store call on the emergency lane. It can preempt a stalled prepare; the late worker cannot HEAT after its generation changes. Manual latches survive; SHADOW emits no fake writes.

Emergency audit is deferred and bounded to 16 entries. On overload the newest frontier replaces the last pending entry and omitted-event count increases. Failed audit remains explicit through `audit_missing`; it is never presented as committed. Flush preserves the latest state/frontier when possible. A crash before flush still requires a fresh boot/fake reconciliation; it does not resurrect automatic HEAT. STOP demand is never a promise that physical equipment is OFF.

## Restart, observations and one-shot

Restart increments boot/owner fencing, clears plan/reconcile readiness and desired HEAT, preserves manual/OFF and armed settings, and records unresolved receipts as UNKNOWN while retaining known timestamps. Boot identities cannot be reused. No outbox replay worker exists. One-shot CONSUMED becomes UNKNOWN on restart and its consumption timestamp survives; existing completed/unknown markers cannot be registered as new pending work.

Reconciliation needs fresh, current-epoch evidence issued by the same fake adapter with known fake state/authors. `feedback(...)` explicitly injects synthetic observations as fixture premises; it does not infer a relay, ownership or power state from service return. Unknown state/writers or foreign/stale evidence cannot reconcile. A manual observation preserves/establishes pause. Only a separately attested resume can change owner authority; it still needs reconciliation, fresh guards and a strictly newer valid plan plus stability/min-off.

One-shot remains `HEAT_AFTER_GRID_RESTORE`. Only generic durable consumption/unknown semantics are implemented, with no automatic session executor, elapsed/reboot credit or global 180-minute limit. B08 is unchanged.

## Failure proof and limits

Disposable subprocesses receive SIGKILL at 13 checkpoints across prepare/claim/send/ACK/echo, owner transaction, migration and SQLite checkpoint execution. A synced synthetic trace distinguishes whether a fake send happened. Both committed and uncommitted outcomes restart closed; no test sends to any actual device. Checkpoint kill occurs while its SQLite VM executes, not at a verified physical disk power-loss boundary.

Actual SQLite page-limit FULL, read-only mode, cross-process lock contention, truncation/checksum/identity corruption and controlled transaction/sync/latency injection are distinct cases. A Linux-only child additionally preloads a path-restricted test shim: SQLite fsync/fdatasync receives EIO, and pwrite/pwrite64 receives ENOSPC, only for that child's disposable control.sqlite3 files after the explicit fault marker. A witness confirms the fault reached the VFS path; neither case may emit HEAT. The shim is never imported/linked into runtime packages and preserves any inherited preload chain. This is not an exhaustive VFS, filesystem or hardware power-loss campaign. N100, real sole-writer/OEM behavior, target linked libraries, OS scheduling SLOs, credentials and real transport remain BLOCKED/NOT_TESTED. WP1C requires separate approval.
