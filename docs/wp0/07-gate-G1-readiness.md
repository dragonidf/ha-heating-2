# WP0 — G1 readiness and executive conclusion

**WP0: BLOCKED. G1: BLOCKED. WP1 is not authorized or declared ready.** The read-only audit and all requested documentation are prepared for review; missing private/physical evidence prevents a complete verified migration baseline. A documentation PR must not be interpreted as permission to implement or activate a controller.

## Executive summary

- Specification pinned at `232e8a61985c98bb34d730c56d6cd51a8614209a`: all17 assets read; manifests12/12 and16/16 match. Legacy baseline `db7d7ce9c53e4e88c1c27ee10e1f53d6cce10426` (0.3.20),103/103 files match Git bytes. Live self-report0.3.21 is separately identified, nine hashes match its public manifest; no source/runtime update performed.
- All **86 requirements (49 P0/37 P1)** map to old evidence, planned modules, canonical test IDs and UI/compatibility; all **38 scenarios** are reviewed. New-system statuses remain specified/not implemented and planned/not executed. No requirement or scenario was discarded, relaxed or treated as passed by old regressions.
- Current software evidence: **535 Python tests and50 JS tests pass**, no skips; make check passes. Bounded synthetic measurements and exact-SHA historical CI are documented separately. They prove no physical or2.0 acceptance result.
- The map has50 sanitized binding/policy rows and the thermostat/fan owner graph. Direct AppDaemon/watchdog and AppDaemon/night fan paths coexist. Current phase topology is not verified. Counter source chain is verified at helper-definition level; complete private model/history/counter parity is not.
- **Eight open items: six P0, two P1**, detailed in [06](06-open-questions-and-blockers.md). Private YAML/assets, physical topology/OEM evidence and external-writer/client authority are the primary G1 blockers. Actual future linked SQLite/FS compatibility and session-cap scope are also unresolved.
- Our production control/config/lifecycle/backup writes: **0**. Legacy GitHub mutations: **0**. This PR adds documentation only; no private configuration payload, raw telemetry, credentials, addresses or physical unique IDs.

## WP0 completion criteria

| CODEX-WP0 criterion | Status | Exact evidence / remaining limit |
|---|---|---|
| Read source package and verify integrity/reference SHA | PASS |00 inventory and E01; both manifests,19 new-repo blobs and103 legacy blobs verified. |
| Audit all86 requirements /38 scenarios and four owner clarifications | PASS for audit coverage |05 trace CSV and09 scenario review; original statuses retained. This is not implementation/test acceptance. |
| Form source/owner/risk map and explicitly block uncertain links | PASS for inventory, BLOCKED for verification completeness |01/02 maps; B01–B05/B07 identify missing bindings, topology, authors and physical evidence without assumptions. |
| No production write/control/deployment/restart or legacy change | PASS for this agent's actions |08 action audit. No assertion that other actors or normal runtime stopped changing state. |
| Public output has no private payload | PASS for prepared diff |08 privacy scan/manual review and allowlisted documentation files; private exports never added. |
| Reviewable documentation branch/PR, no automatic WP1 | PASS for deliverable preparation | Branch `audit/wp0-readonly`, all nine mandatory files plus09 scenario CSV; review targets main, no merge/activation. Live PR URL is supplied in final handoff. |

## G1 evidence checklist

| G1 evidence | Result | Evidence / blocker |
|---|---|---|
| Approved architecture, constraints and immutable source identity | PASS |G0/addendum, E01–E03. |
| Complete actual app registration/YAML/source bindings | BLOCKED |Partial published map/registry reads, but full source and fireplace/heartbeat/tariff binding absent. B01. |
| Actual coherent private state/telemetry/archive/backup hashes | BLOCKED |No such export obtained; H06 bounded history cannot substitute. B02. |
| Source units/origins, helper interfaces and counter source chain | PASS for inspected interfaces |H01/H04/H09;50-row map. Hardware calibration, all timestamps/aliases and full persisted continuity not certified. |
| Verified electrical topology, aliases, signed/non-overlap and OEM limits | BLOCKED |Zero-entry unverified topology, shared sources, no physical outcome evidence. B03/B05. |
| All automatic/manual/external authors and quiescence plan | BLOCKED |Known writers documented; literal searches complete within returned surface, external/dynamic authors not excluded. B04/B07. |
| Actual model/candidate/one-shot/initial/12h original evidence parity | BLOCKED |Software contracts inspected; no private original bytes/markers. B02; session scope B08. |
| UI resource/registry/consumer compatibility | PARTIAL → BLOCKED overall |One local heating resource found; dynamic sensor identity and native meter chain inspected. Full YAML/external consumer manifest and live UI/device verification absent. B01/B07. |
| Overall G1 | **BLOCKED** |No silent waiver of the remaining evidence. |

## G0–G9 status

| Gate | Status | Reason |
|---|---|---|
| G0 architectural approval | PASS |ADR01–07 and C1–C4 explicitly approved2026-11-03. |
| G1 read-only baseline | BLOCKED |Evidence checklist above. |
| G2 private backup/restore rehearsal | BLOCKED / NOT STARTED |No production backup allowed in WP0; existing private manifest unavailable, isolated restore not performed. |
| G3 implementation/stand | BLOCKED / NOT STARTED |No new code; B06/O09 qualification and new suites absent. |
| G4 import dry-run | BLOCKED / NOT STARTED |Only plan/parity checklist written; no import even into production directories. B02 and future code required. |
| G5 shadow | BLOCKED / NOT STARTED |No new runtime, seven-day/three-cycle evidence absent; no shadow installation authorized here. |
| G6 physical commissioning | BLOCKED / NOT STARTED |B03/B05; new explicit scoped approval required for real device tests. |
| G7 cutover | BLOCKED / NOT STARTED |Sole writer/quiescence/import/rollback evidence missing and no deployment approval. |
| G8 probation | BLOCKED / NOT STARTED |No activation; no new24h/three-cycle evidence. |
| G9 quality acceptance | BLOCKED / NOT STARTED |No10 qualified cycles or seven independent days per required horizon; no physical energy metrology claim. |

No FAIL is assigned merely because future work has not begun. BLOCKED means the gate cannot be accepted on present evidence; it does not authorize changing production to obtain a pass.

## Owner clarification acceptance mapping

| Clarification | Requirements / scenarios | Audit result and future acceptance |
|---|---|---|
| C1 morning comfort, safe continuous30min, stable immutable plan |P03–P06,P10–P12,E03/E06; SC14–18,23,25 |Legacy continuity/reserve/stability/original evidence paths identified; preserve meaningful elapsed credit and energy sufficiency. No forced heat at upper/grid off. New bounded planner and private replay unverified. |
| C2 independent fallback and manual priority |S01–S08,S11–S15,O01/O03/O05; SC01–07,30–33,35 |Shared legacy runtime/multiple writers are a migration risk, not evidence of new isolated fallback. No auto reclaim from manual pause; owner/boot epochs and crash receipts planned. |
| C3 feature completeness, one-shot/fire/fan/vent, history/model/totals |S14,D01–D10,M01–M10,E01–E08,F01–F06,O08,G01–G04; SC06,08–13,19–28,32,36–38 |One-shot confirmed as heating after next grid return; fireplace actual binding missing; night direct branch/arbiter and read-only ventilation documented. Counter/model/private archive parity remains blocked. |
| C4 simple three-tab UI, original12h/fact, mobile and expert functions |U01–U10,E06/E08; SC25/26/29/34/35 |PNG/SVG direction inspected; no live/new interactive acceptance implied. Preserve actual/desired/physical evidence, accessible graph and expert paths; browser/device checks future only. |

## Recommended next safe work

Review this documentation PR without merging automatically. Obtain B01–B05/B07 evidence through existing read-only/private channels; record B08 session semantics and target manifests for B06. Confirm the gate status from those artifacts. Only after a separate WP1 instruction may pure contracts/kernel tests proceed with synthetic inputs; do not depend on unverified household bindings, install a second writer or advance to production. The current project is **not ready for an unqualified WP1/G1 pass**.
