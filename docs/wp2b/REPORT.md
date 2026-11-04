# WP2B — complete isolated operator frontend

Implementation and self-test handoff for Issue17, from approved main `e428b9ad3e7c0c4b91b253276fd118243d33439c`. Scope is the full standalone synthetic UI; one open/unmerged code PR. Independent ChatGPT review determines acceptance. G1/B01–B08 remain BLOCKED; WP2C is not started.

## Delivered behavior

| Surface | Working offline behavior | Evidence |
|---|---|---|
| Дім | comfort/target half-degree persisted fake intent; actual physical state unknown vs desired/fake ACK; one prioritized alert; next24h temperature/plan/outage context; morning/session explanation; scoped cycle budget; fire/night circulation sheet; explicit fake pause/resume and one-shot states | Home.tsx; Chart.tsx; mock.ts; component/browser tests |
| Історія | Kyiv calendar7d default,24h/30d/custom≤31 calendar days; actual-only empty/missing/partial/cached states; immutable original requiring both issue+receipt≥12h lead; latest opt-in; scoped units/quality/cost/tariff; shared pointer/keyboard readout, null-separated paths and accessible table/cursor pages | History.tsx; domain.ts; canonical contract fixtures; browser/unit tests |
| Налаштування | compact comfort/windows/strategy/month budget/mode/circulation; staged validation/save/cancel/undo; durable local CAS/readback/revision; two-client conflict diff/rebase/retry; expert search/physical scenario/freshness/AI disclosure | Settings.tsx; useSettings.ts; storage.ts; real IndexedDB E2E |
| Модель і діагностика | nested horizon1/3/6/12/24/36/48h days/sample counts; honest unproved long horizon; fixed synthetic challenger/promotion/freeze/rollback demonstration; separate source/worker/persistence/lag/archive/command health; read-only recovery/fail-safe/ventilation context | Diagnostics.tsx; mock.ts; browser/API tests |

All operating controls are labeled simulation-only. Physical3/6/9kW choices describe unverified calculation scenarios and never issue stage commands. Read-only ventilation factors are not airflow/efficiency. B08 one-shot semantics are not generalized into a180-minute global session cap. No browser closure/reload can replay a device request because no device transport exists.

## Contract and persistence integrity

Python-generated StatusView/APIReceipt/ForecastRecord/BudgetReceipt JSON uses the accepted codec and dataclasses unchanged. TS adapters validate actual envelopes and preserve source receipt separately from original freeze time. UI1 comfort/history/model projections are a new in-process demo seam, not claimed native HA endpoints or a replacement control backend. All101 accepted package/test assets, including351 tests, are hashed in REGRESSION-BASELINE.sha256 and unchanged.

Only synthetic desired UI settings are saved to IndexedDB on the local demo origin. Readwrite transactions serialize cross-window CAS, commit then reread. Failure/ambiguous ACK is unavailable; draft remains; retry may require explicit reread/rebase. Client verifies request ID/generation/revision/value readback before showing Saved, keeps inputs disabled through verification and bounds local waits. Fake capability identity and freshness are checked at commit; arbitrary serialized permissions cannot authorize it. Model/one-shot examples are memory-only and do not claim durable physical execution. Authoritative actual safety/one-shot/storage/learning behavior remains in the unchanged Python packages/tests.

Original source is immutable, genuinely time-covered and received/issued before cutoff; late receipt renders MISSING. Latest never substitutes and actual history is independent. Decimation preserves spikes/endpoints/nulls with a4096 input hard bound; pages128default/256max stay below64KiB. Current/frozen/actual use distinct patterns plus a table. Day/cycle scopes never borrow totals from one another. Known contributions, estimated/recovered categories, unknown duration and missing dated price remain visible. Negative partial remaining is overrun, never savings; causal kWh are not invented.

## Verification and corrections

- All351 accepted Python tests retained; strict mypy and full local Python3.12/3.13 checks PASS,97% branch coverage with unchanged95% floor. CI retains all four Python matrices (12jobs,3.12/3.13/3.14).
- Frontend strict TypeScript, pinned npm lockfile, prettier, production build and111 unit/component/hook tests. Coverage floors are90% lines/statements/functions and85% branches across wire/domain/mock/storage/save-state logic; current observations in LOCAL-VALIDATION.txt. Tests include malformed envelopes/nonfinite/units, receipt/generation races, transaction failure, two clients, retry, unknown/zero, original cutoff/coverage/immutability, gap/spike decimation and DST.
-56 real-browser cases in Chromium/WebKit × mobile/desktop, including additional320/700/1100 widths,44px targets, local dark/light, genuine200% text, long Ukrainian copy, axe/keyboard/focus/touch, in-flight disconnect, conflict/readback errors, missing original, model and one-shot flows. Golden PNGs and browser matrix are synthetic-only. Final-head frontend CI adds two jobs, for14 total required jobs with the12 Python jobs.
- Test-first foundation runs are retained as RED-EVIDENCE.txt. Additional failing regressions exposed wrong-request infinite Saving, an unhandled post-receipt reread failure and a32-day custom-range edge; they were fixed in code. Browser validation exposed real Safari flex overflow at200% and a narrow enlarged simulation badge; wrapping was corrected. A temporary local build concurrent with a browser run invalidated a served asset and caused one blank-load failure; final browser runs use a frozen completed build. First CI at0a667616 passed all12 Python jobs and54/56 browser cases; native Ubuntu font metrics made mobile Home1332px, above the unchanged1300px main-content gate. Responsive spacing was reduced without hiding content or reducing44px targets; all four local screenshot cases then passed. No criterion was weakened or hidden with retries/skips.

## Reproduction and artifacts

At repository root, `python -m tools.wp2b.export_contracts --check` and SHA manifests verify source/fixture evidence. In frontend: npm ci, npm run typecheck, npm run format:check, npm run test:coverage, npm run build, npx playwright install --with-deps chromium webkit, npm run test:browser. Preview binds127.0.0.1 only. No CDN/fonts/analytics/API network is required by the built app; CSP connect-src is none. Browser tests use local static assets and in-process synthetic data.

BUNDLE.json records actual dev-host build bytes/gzip/hashes; Node/tool versions are pinned in package.json/package-lock.json. This is not N100/LAN latency or a30-day soak. BROWSER-MATRIX.md documents actual browsers and the temporary-library local-host workaround; CI uses normal supported dependency installation. Screenshots and test artifacts are retained by the frontend workflow. Final exact tested SHA, counts, run URLs and results are recorded in PR checks/description after completion, without a subsequent untested documentation commit.

## Critical limits

G1/B01–B08 remain BLOCKED; G2–G9 are NOT_TESTED. No production HA read/contact/install/update, old-controller/repository edit, physical command, real telemetry/private data, actual backup/import, shadow, deployment or merge occurred. No enabled HA component, authenticated session, service/MQTT/WebSocket/device writer exists. Fake ACK/echo/IndexedDB durability/browser success do not qualify physical actuation, real authentication, actual energy metrology or target durability. Native HA packaging/theming/auth compatibility, owner phone/Android WebView/screen-reader practical checks, real training/calibration/commissioning and forecast accuracy remain unverified. These constraints are explicit scope limits, not defaults guessed from household equipment.

The offline WP2B package is prepared for independent review only; no launch readiness or WP2C authorization follows.
