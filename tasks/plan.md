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

Implementation checkpoints1–5 completed:202 unit/component/hook tests,80 actual browser cases and all351 inherited Python tests. Checkpoint6 source/manifests/report complete; final-head CI and independent review tracked by the single PR checks/description. No deployment/merge/next phase is part of this plan.

Review correction batch6624485241: reproduce four findings before fixes; retain disjoint settings edits with explicit collisions; aggregate the complete dense history; require qualified historical continuity; clip energy/cost with honest estimated quality. All seven original red reproductions plus adjacent quick-intent/late-reread/quality/zero regressions pass. Source, docs,86/38 traceability and manifests are prepared for final-head CI. CI result and independent ChatGPT re-review remain recorded by PR19; no self-acceptance or merge.

Follow-up6625889290: eight red cases reproduced shared archive errors/future-as-fact/invalid quality; reconnect red cases reproduced stale errors. Independent results, strict now cutoff and quality normalization are implemented only in history/chart modules with synthetic fault fixtures. New25 frontend and12 browser cases retain all177/68 prior cases; keyboard scroll-region issue exposed by expanded axe was fixed without suppressing the rule. Final-head CI and focused independent recheck remain on PR19. G1/B01–B08 BLOCKED; no next phase or production access.

# WP2C — Issue20 isolated native packaging (owner approved)

Base main662a9c4; prior WP2B accepted. Tasks tracked here and in Issue20. Scope: new isolated HA only; never home HA/Proxmox/LAN; G1/B01–B08 BLOCKED; no WP2D. Contract is docs/wp2c/PROTOCOL.md.

1. Pin official HA version/digest; launch HA and real browsers in the same network-none namespace with synthetic auth/config and disposable volumes. Verify no published ports, no egress/discovery and reproducible teardown. Native proof must be real or BLOCKED. Dependency: none; checkpoint: SDK source/startup/isolation checks.
2. Typed future meter/source binding and arbitration, resets/jumps/phase/overlap/quality/fallback tests. Dependency: accepted contracts; checkpoint: strict mypy and new pure tests on3.12/3.13/3.14.
3. Authoritative fake-only backend: disabled state, bounded versioned projections, separate transactional settings/evidence, CAS/readback, boot/ownership/manual/one-shot, emergency STOP and synthetic rollback/fault tests. Dependency: protocol; checkpoint: red/green unit and real SQLite faults.
4. HA SDK config/options/registry/panel/auth/lifecycle/migrations wrapper and self-contained deterministic packaging. Dependency:1/3; checkpoint: genuine install/unload/reload/restart/auth tests.
5. Native HA panel mounts reviewed UI through existing authenticated connection and backend overview/settings/history. Preserve standalone202/80 and add native browser/a11y/failure coverage. Dependency: protocol/3/4; checkpoint: full real Chromium/WebKit suites.
6. All351 inherited Python cases + new unit/native/fault/perf checks; keep14 baseline jobs and add native CI. Reports/ADR/version/isolation/86–38/checksums/source hashes; one open feature/wp2c-isolated-ha-packaging PR, no merge. Final CI and independent review are recorded in PR metadata, no untested follow-up commit.

Independent slices may be implemented in parallel after this shared contract; database migrations and shared API changes remain coordinated/sequential. Each slice owns its source/tests and performs self-testing; independent acceptance is reserved for ChatGPT/owner.

WP2C checkpoints1–4 completed locally: actualCore2026.10.4 synthetic62native groups/strictSDK40filesPASS, isolated resources removed. Pure suite now427cases; preceding3.12/3.13 runs and resumed3.12 run98%coveragePASS; all101acceptedPythonassets unchanged. Checkpoint5 source/build frozen:255frontendcasesPASS,28nativebrowsercases defined; actualnativebrowserqualification deferred to ephemeralCI due localinodebudget. Checkpoint6 uses16final-headjobs (14preserved+2realHA), exact86/38canonicalmappings and refreshedsource/artifactSHA. FinalCI/independentreview recordedby oneopenPR, no automaticnextphase.
