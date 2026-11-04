# WP2B — one Codex execution contract (offline/synthetic APPROVED)

**Owner approval: 2026-11-04. Implementation and tests only in an isolated sandbox.** The *complete normative work scope* is [Issue #17](https://github.com/dragonidf/ha-heating-2/issues/17). This file fixes implementation sequence and stop lines; it is not a replacement for Issue #17 or the 86 canonical requirements/38 scenarios.

## Read before writing

1. Current `AGENTS.md`, `docs/wp2b/APPROVAL-2026-11-04.md`, and **all of Issue #17**.
2. `docs/spec/heating-ai-2.0/05-UI-design.md`, `03-Codex-specification.md` (U01–U10, O01–O07, E/P/M/F and status/receipt requirements), `04-Test-strategy.md`, `06-Migration-and-acceptance.md`, 86/38 CSV registers, approved ADRs, `docs/ROADMAP-TO-LAUNCH.md`.
3. Accepted WP1A/B/C and WP2A source/contracts/report/tests, especially original-12h receipt-cutoff correctness, bounded history/energy provenance and CAS settings receipts. **Preserve all 351 prior tests**.

## Build one complete frontend package

- New `frontend/` with **functional local synthetic-demo**, three main tabs **Дім, Історія, Налаштування**, nested **Модель і діагностика**. Compact, polished mobile 390×844 and desktop; dark/light tokens per 05, Ukrainian strings without clipping.
- Strict versioned UI/client/mock boundary matching the accepted WP2A typed data and statuses, using **only artificial fixtures**; delayed, reordered, unavailable/offline, stale, manual, dangerous, false ACK, recovery, settings conflict, permission revoked, retry/reconnect and unknown states. No implicit claim of actual hardware state.
- Home: legible measured room/target, desired vs actual vs unknown, top-priority alert, next 24h graph/sessions/morning/blackout context, compact fireplace/night circulation and simulation-only controls.
- History: time ranges 24h/7d/30d/custom in Europe/Kyiv with DST, original **issued and received >=12h before** cycle reference vs actual with unconnected gaps, distinct latest forecast/comfort/heat/outage layers, accessible equivalent table, bounded pagination/decimation; verified energy scope, facts/estimated/unknown, honest tariff and overrun.
- Settings: typed form validation, staged changes, server-like durable mock CAS/save/readback receipts, cancel/undo/conflict/reconnect; advanced model diagnostics, learning uncertainty, one-shot semantics and clearly non-actuating physical 3/6/9 kW scenario descriptions.
- Browser/mobile/desktop keyboard, focus, screen-reader labels and accessible chart/table; no CSS overflow at 200% zoom/long Ukrainian text, reduced motion, light/dark contrasts, offline local assets only.
- Produce tests for critical UI state machine, plot/forecast integrity, safety display, missing/stale data, time and DST, source race/reconnect, mock CAS, privacy/no-network, responsive design. Run an actual browser E2E matrix and save reproducible **synthetic-only** screenshots; if browsers cannot run, mark browser acceptance BLOCKED rather than inventing a PASS.
- Keep Python 3.12/3.13/3.14 CI 12-job baseline; add strict frontend type checks, test/build and browser CI. Record exact runner/toolchain/dependencies, hashes, bundle size and test-host timings. Do not change baseline quality thresholds or previously accepted backend behavior.
- Document `docs/wp2b/REPORT.md`, ADR, design tokens, API fixtures, browser/a11y matrix, 86/38 mappings, checksum manifest; honest PASS_OFFLINE/PARTIAL/BLOCKED labels.

## Branch, review and stop

Implement in **one** `feature/wp2b-offline-frontend` branch and open **one PR, unmerged**. Perform normal self-correction until CI is green. Report to owner **only PR URL, final SHA, counts (Python and JS/browser), CI, and critical limitations**.

### Absolute stop lines

No HA live integration/URL/token, network/device commands, MQTT, enabled `custom_components`, production dashboard change, physical actuation, private data, legacy edits, actual migrations, shadow/deployment or WP2C. No backend command bypass or silent owner/permissions changes. **G1/B01–B08 BLOCKED**, B08 unresolved; no unverified real equipment claim.

Independent ChatGPT review is required before merging and no next phase starts automatically.
