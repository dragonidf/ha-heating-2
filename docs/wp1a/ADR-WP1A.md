# WP1A contract and reducer decisions

Scope: [issue #5](https://github.com/dragonidf/ha-heating-2/issues/5), [task](WP1A-TASK.md), root AGENTS.md. These decisions implement a synthetic pure slice of approved ADR01–07. They do not resolve commissioning questions or authorize runtime work.

## Boundary and trust

- Frozen, slotted dataclasses, enums, immutable tuples and explicit nullable fields. Schema envelope `1.0` rejects unknown fields/types/versions, duplicate JSON keys, malformed/oversized input and nonfinite values. Optional `source_sequence` distinguishes absent, null and zero. There is no storage implementation or schema migration.
- All input, policy, revisions and clocks are injected. The only imports are other pure modules and a closed standard-library allowlist. No sender, service name, binding, file path, network, database, background loop or deployment entry point exists. `STOP` means a demand description; it does not prove equipment OFF.
- Input validation establishes shape and software ranges, not truth or authority. `limits_qualified`, actual-grid provenance, `authorized` resume/emergency stop and event classification are assertions from a future trusted adapter. A boolean cannot authenticate a caller or commission an installation. Never construct live policy from these fixtures. Counter exhaustion or invalid contract construction raises sanitized `ContractError`; a future boundary must fail closed, never recover by dispatching HEAT.
- Future restart must construct a fresh STARTING state with a new boot identity and reconcile. Loading JSON alone must never establish readiness. In-memory `reconciled` is a modeled precondition, not actual state verification or durable proof.

## Priority and ownership

SHADOW always produces zero intent descriptions, including hard-stop events. In other modes current hard stop precedes event rejection and manual processing; a valid manual event still updates its authority latch. Other required guards, qualified upper/return limits, outage/window boundaries and expiry precede min-on. Ordinary manual/observation pauses relinquish automatic demand without describing a command that could undo a manual action. Explicit OFF or safety stop can describe STOP.

Event `sequence` and `at` describe a trusted **ingress ordering frontier**, not a sensor's measurement timestamp. Boot/owner identity, increasing sequence, nondecreasing ingress time, event expiry and injected monotonic time are checked. Late own receipt identity is ignored without inventing a manual action; an external or uncorrelated actuator change explicitly creates MANUAL_PAUSE, increments ownership and invalidates pending plan/receipt. Only authorized explicit RESUME releases a latch, increments ownership again, clears old plans and requires reconciliation. Caller must obtain a new snapshot for the new owner epoch.

Emergency `SAFETY_STOP` assertions use a separate lane: `authorized=True`, current boot/owner, assertion time no later than clock plus skew, and sequence strictly greater than `last_safety_stop_sequence`. A newly received trusted assertion bypasses ordinary event sequence/time ordering and ordinary event expiry, so an advancing queue cannot discard an emergency. Its outgoing STOP **intent** has a newly bounded current lifetime; outbound intent TTL/replay checks are unchanged. A trusted boundary must authenticate/classify the assertion and bind its original identity/epoch/sequence; copying an untrusted client's serialized `authorized` flag is forbidden. No authentication or transport implementation exists in WP1A.

The emergency frontier records accepted assertions independently of normal events, rejects duplicate/older assertions during and after recovery, and never advances ordinary event order or changes owner authority. Event sequences belong to one boot/owner ingress sequencer; independent producer counters must not be reused as that sequence. The frontier defaults to -1 in this unreleased contract, roundtrips, and resets on a new owner or boot. Old-epoch, future and unauthorized assertions cannot stop otherwise safe HEAT or poison either frontier. Current snapshot safety still applies independently when a message is rejected. SHADOW records a valid assertion's frontier but emits no intent. Manual latches survive emergency processing.

Rejected proposals/events still recheck current safety. They cannot mask a newly hot room, missing grid, expired intent or other unsafe condition while HEAT is desired. UTC rollback beyond configured skew also stops demand. Strict windows and plan segments use absolute UTC `[start,end)` boundaries. Caller supplies timezone objects for conversion; ambiguous local instants require explicit fold and nonexistent instants are rejected.

## Asynchronous measurements and snapshot coherence

`max_skew_s` bounds future timestamps, clock rollback and observed/received/captured ordering; it is not a reporting cadence or maximum spread between different sensors. Each required role has its own age budget, checked against the injected decision time using both original `observed_at` and quality age. Both observation and receipt must precede the snapshot cut plus clock tolerance; snapshot age itself is independently bounded. Receipt refresh or a new snapshot never moves an observation forward.

The coherent input here is a bounded **as-of collection of latest observations**, with explicit per-role ages and shared snapshot boot/owner/revisions. It does not claim simultaneous room, pipe, thermostat and grid measurements. Reducer evaluates each guard on its accepted original observation without interpolation, extrapolation or changing quality to VALID. ESTIMATED/HELD/FORECAST readings cannot become valid required safety readings. Any future balance/model inference needing simultaneous samples or age-bounded estimation needs its own typed uncertainty/alignment contract; none is implemented here.

Source age limits must be qualified by the future adapter/configuration evidence; synthetic 14,400/20/30/3-second budgets only demonstrate independent cadences. They establish no household sensor or physical bound. B01/B05 remain open. This supersedes the initial incorrect cross-source `max(observed)-min(observed) <= max_skew_s` rule identified in review comment 6605790334 without increasing clock skew tolerance.

## Plans, fallback and recovery

Plan admission binds boot/grid/owner epochs, config/model/topology revisions and original input SHA-256. Later live input hashes may change without invalidating the admitted original hash; every tick independently rechecks current live guards. New proposals must match the new input hash. No planner or thermal/energy computation exists.

With compute unavailable, only the already accepted, currently valid plan can produce AUTO_HOLD. Once missing/expired/unsafe, the conservative fallback is STOP-only. Native-auto heat and local hysteresis are **NOT_IMPLEMENTED** pending B01/B05. This FALLBACK enum is not proof of the complete S11 reserve controller.

Faults invalidate the plan, including a plan issued at the same instant as a fault. Recovery requires fresh safe observations for the injected stability duration, explicit new plan admission with `issued_at > recovery_at`, and min-off. Re-admitting a failure-time plan with the same hash/revisions cannot bypass this strict inequality. Repeated failure retains the incident start; unhealthy inputs reset the stability timer. All durations are supplied by policy; synthetic 3/5/10-second fixtures are test values, not replacements for the specified production intervals. No global session cap is introduced.

Intent descriptions are deterministic, snapshot-bound, epoch/sequence scoped and expiring. Repeat safe ticks do not duplicate a description. HEAT expiry is clipped to the active segment and plan horizon. This slice conservatively stops and requires recovery after an expired HEAT description; it implements no lease renewal, delivery retry, timer, queue or gateway. Continuous live command lifecycle remains future work.

## Evidence and unresolved surfaces

REQUESTED, PREPARED, SENT, HA ACK, device echo and externally supplied physical evidence have separate timestamps. Reducer never manufactures receipts or physical success. Physical-stage records require non-null VALID independent direct readings with non-overlapping provenance; their real calibration, freshness and relevance still need a qualified future evidence evaluator. A zero-watt reading alone is not proof of a relay state.

Derived/held/forecast sources cannot claim independent metrology. Shared physical IDs or component footprints cannot become two independent meters. There is no balance solver or ledger yet. Actual grid is required for live eligibility even for conditional segments; forecast never substitutes for it.

One-shot kind is only `heat_after_grid_restore`, with explicit expiry, consumption marker and unknown outcome. It has no executor or durable exactly-once claim. B08 remains open: legacy one-shot-only 180-minute cap is not generalized to ordinary scheduled sessions. Cap/elapsed/reboot behavior awaits owner decision.

Deferred contracts/modules include thermostat offset/clamp/capabilities, qualified native fallback, fan arbitration, thermal model, forecast provider, planner, ledger, learner, compatibility clients, authentication, durable receipts/store, import/migration and UI. No full requirement or SC integration/physical acceptance is asserted by this ADR.
