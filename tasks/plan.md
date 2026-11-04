# WP2B implementation plan — Issue17

Scope: one offline frontend PR from main e428b9a. Three operator tabs and nested diagnostics; synthetic in-process API only. G1/B01–B08 BLOCKED. No production/legacy access or WP2C.

Design contract: follow approved05 tokens and ui-concept composition. Home first viewport shows comfort/ownership/one alert and chart start; desktop7:5, mobile single column/bottom navigation. Settings stage edits; save only after transactional simulated persistence and readback. Actual, desired and fake acknowledgement stay separate. No physical evidence can be claimed by fake StatusView.

Implementation order and checkpoints (tasks tracked as this local index under Issue17):
1. Typed fixtures and pure provenance/time/chart rules, tests first. Validate accepted WP2A envelopes and bound projections; exact original issue+receipt cutoff; missing gaps and Kyiv DST. Verify strict TS and unit tests.
2. Home vertical slice with synthetic subscription, permission/session/freshness gating and transactional local-only settings intents. Verify race/reconnect/save/revoke/unknown outcomes in unit/component tests.
3. History slice: Kyiv calendar ranges, bounded pages/decimation, original/latest/fact chart/table, scoped energy/cost/quality. Verify gaps, spikes, tariff/scope and unavailable states.
4. Settings and nested model/diagnostics: staged form/undo/conflict/retry, fake one-shot/fan/ownership, evidence by horizon and expert disclosure. Verify validation, CAS/readback, model gates and read-only physical scenario descriptions.
5. Responsive/accessibility finish: actual Chromium/WebKit matrix mobile/desktop, axe/keyboard/focus/200%text/long Ukrainian copy/reduced motion, synthetic screenshots and privacy/network denial. Inspect screenshots and correct defects.
6. Preserve351 Python tests and accepted sources; full Python3.12/3.13/3.14 CI12-job baseline plus frontend unit/build/browser CI. Docs/ADR/tokens/API fixtures/browser matrix/86–38 mappings/checksums; final SHA and one OPEN/UNMERGED PR.

Risks: real HA/native authentication/physical state unavailable by design; fake receipt is not actuation. Browser storage can fail and must never show false saved. Original history never recomputed/backfilled. Test-host timings do not qualify target host. No unresolved product decisions require expanding existing approval.

Implementation checkpoints1–5 completed:111 unit/component/hook tests,56 actual browser cases and all351 inherited Python tests. Checkpoint6 source/manifests/report complete; final-head CI and independent review tracked by the single PR checks/description. No deployment/merge/next phase is part of this plan.
