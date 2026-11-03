# WP1A contract and reducer decisions

Scope: [issue #5](https://github.com/dragonidf/ha-heating-2/issues/5), [task](WP1A-TASK.md), root AGENTS.md. These decisions implement a synthetic pure slice of approved ADR01–07. They do not resolve commissioning questions or authorize runtime work.

## Boundary and trust

- Frozen, slotted dataclasses, enums, immutable tuples and explicit nullable fields. Schema envelope `1.0` rejects unknown fields/types/versions, duplicate JSON keys, malformed/oversized input and nonfinite values. Optional `source_sequence` distinguishes absent, null and zero. There is no storage implementation or schema migration.
- All input, policy, revisions and clocks are injected. The only imports are other pure modules and a closed standard-library allowlist. No sender, service name, binding, file path, network, database, background loop or deployment entry point exists. `STOP` means a demand description; it does not prove equipment OFF.
- Input validation establishes shape and software ranges, not truth or authority. `limits_qualified`, actual-grid provenance, `authorized` resume and event classification are assertions from a future trusted adapter. A boolean cannot authenticate a caller or commission an installation. Never construct live policy from these fixtures. Counter exhaustion or invalid contract construction raises sanitized `ContractError`; a future boundary must fail closed, never recover by dispatching HEAT.
- Future restart must construct a fresh STARTING state with a new boot identity and reconcile. Loading JSON alone must never establish readiness. In-memory `reconciled` is a modeled precondition, not actual state verification or durable proof.

## Priority and ownership

SHADOW always produces zero intent descriptions, including hard-stop events. In other modes current hard stop precedes event rejection and manual processing; a valid manual event still updates its authority latch. Other required guards, qualified upper/return limits, outage/window boundaries and expiry precede min-on. Ordinary manual/observation pauses relinquish automatic demand without describing a command that could undo a manual action. Explicit OFF or safety stop can describe STOP.

Event `sequence` and `at` describe a trusted **ingress ordering frontier**, not a sensor's measurement timestamp. Boot/owner identity, increasing sequence, nondecreasing ingress time, event expiry and injected monotonic time are checked. Late own receipt identity is ignored without inventing a manual action; an external or uncorrelated actuator change explicitly creates MANUAL_PAUSE, increments ownership and invalidates pending plan/receipt. Only authorized explicit RESUME releases a latch, increments ownership again, clears old plans and requires reconciliation. Caller must obtain a new snapshot for the new owner epoch.

Rejected proposals/events still recheck current safety. They cannot mask a newly hot room, missing grid, expired intent or other unsafe condition while HEAT is desired. UTC rollback beyond configured skew also stops demand. Strict windows and plan segments use absolute UTC `[start,end)` boundaries. Caller supplies timezone objects for conversion; ambiguous local instants require explicit fold and nonexistent instants are rejected.

## Plans, fallback and recovery

Plan admission binds boot/grid/owner epochs, config/model/topology revisions and original input SHA-256. Later live input hashes may change without invalidating the admitted original hash; every tick independently rechecks current live guards. New proposals must match the new input hash. No planner or thermal/energy computation exists.

With compute unavailable, only the already accepted, currently valid plan can produce AUTO_HOLD. Once missing/expired/unsafe, the conservative fallback is STOP-only. Native-auto heat and local hysteresis are **NOT_IMPLEMENTED** pending B01/B05. This FALLBACK enum is not proof of the complete S11 reserve controller.

Faults invalidate the plan, including a plan issued at the same instant as a fault. Recovery requires fresh safe observations for the injected stability duration, explicit new plan admission and min-off. Repeated failure retains the incident start; unhealthy inputs reset the stability timer. All durations are supplied by policy; synthetic 3/5/10-second fixtures are test values, not replacements for the specified production intervals. No global session cap is introduced.

Intent descriptions are deterministic, snapshot-bound, epoch/sequence scoped and expiring. Repeat safe ticks do not duplicate a description. HEAT expiry is clipped to the active segment and plan horizon. This slice conservatively stops and requires recovery after an expired HEAT description; it implements no lease renewal, delivery retry, timer, queue or gateway. Continuous live command lifecycle remains future work.

## Evidence and unresolved surfaces

REQUESTED, PREPARED, SENT, HA ACK, device echo and externally supplied physical evidence have separate timestamps. Reducer never manufactures receipts or physical success. Physical-stage records require non-null VALID independent direct readings with non-overlapping provenance; their real calibration, freshness and relevance still need a qualified future evidence evaluator. A zero-watt reading alone is not proof of a relay state.

Derived/held/forecast sources cannot claim independent metrology. Shared physical IDs or component footprints cannot become two independent meters. There is no balance solver or ledger yet. Actual grid is required for live eligibility even for conditional segments; forecast never substitutes for it.

One-shot kind is only `heat_after_grid_restore`, with explicit expiry, consumption marker and unknown outcome. It has no executor or durable exactly-once claim. B08 remains open: legacy one-shot-only 180-minute cap is not generalized to ordinary scheduled sessions. Cap/elapsed/reboot behavior awaits owner decision.

Deferred contracts/modules include thermostat offset/clamp/capabilities, qualified native fallback, fan arbitration, thermal model, forecast provider, planner, ledger, learner, compatibility clients, authentication, durable receipts/store, import/migration and UI. No full requirement or SC integration/physical acceptance is asserted by this ADR.
