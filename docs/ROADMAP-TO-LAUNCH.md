# Accelerated path to Heating AI 2.0 — gated roadmap (2026-11-03)

This is a **sequence and parallelization plan, not permission to skip gates**, and not a promise of dates. Owner requests rapid progress toward a dependable unattended controller.

## Current verified status

| Item | Status | Evidence |
|---|---|---|
| G0 / ADR01–07 | APPROVED | `docs/spec/heating-ai-2.0/APPROVAL-2026-11-03.md` |
| WP0 | REVIEWED | PR #2, `docs/wp0/` |
| WP1A | ACCEPTED | PR #6, head 67096ac, main merge 261bd4e; 92 synthetic tests/CI 3.12–3.14 |
| G1 evidence | BLOCKED | B01–B08, Issue #3 |
| WP1B | ACCEPTED, OFFLINE ONLY | PR #9, merged main `1d3a920` / Issue #7 closed |
| WP1C | ACCEPTED, OFFLINE ONLY | PR #13, merged main `9525e46`, Issue #11 closed; 219 tests / CI 9/9 |
| WP2A | APPROVED **OFFLINE ONLY** | `docs/wp2a/APPROVAL-2026-11-03.md`, `docs/wp2a/WP2A-TASK.md`, Issue #14 |
| Live deployment, actual actuation, cutover | NOT AUTHORIZED | Gates G2–G9 remain future |

## Parallel lanes

### Lane A — code on isolated, synthetic/offline development environment

1. **WP1B COMPLETE:** offline SQLite durable store, boot/owner/one-shot persistence, fake gateway, prioritized STOP, 13 crash checkpoints and CI; PR #9 accepted. No real device writers.
2. **WP1C COMPLETE:** pure thermal model, bounded blackout-aware planner and immutable 12h reference, champion/challenger and fireplace/night fan policy; PR #13 accepted, code and tests in main.
3. **WP2A NOW — APPROVED OFFLINE ONLY:** fake HA-facing contracts/client, synthetic event-to-reducer seam, isolated SQLite energy/evidence ledger and synthetic legacy-shaped dry-run/rollback. Issue #14 and `docs/wp2a/WP2A-TASK.md`; absolutely no real HA network/SDK connection, device writer or production data.
4. **Future WP2B (requires new approval):** new separate UI and complete operator experience, frozen 12h plan vs actual graph and setting save receipts, synthetic-first browser/mobile tests.
5. **Future staged integration (requires new approval and actual gate evidence):** an isolated test Home Assistant instance and SDK/FS compatibility verification (not a second writer); then specifically authorized read-only zero-write shadow in real HA only after prerequisites. Physical device activation much later.
6. **Future user-facing migration and parity:** private import only with qualified owner-controlled evidence, continuity, frozen forecast and original history, with a reversible dry-run; preserve all requirement/scenario IDs.
7. **Future release preparation:** G3 software target tests, G4 import dry-run, G5 ≥7-day/3-cycle zero-write shadow; G6 OEM tests, G7 one-writer cutover, G8 probation, G9 quantified quality; each has explicit owner permission and evidence.

### Lane B — G1 evidence/owner decisions (in parallel to Lane A)

- B01: qualified actual current bindings/config and per-source cadence; any existing private export stays private.
- B02: durable private baseline/model/history/counter/one-shot manifest, integrity and continuity; do not generate new production backups without permission.
- B03: verify physical metering topology and signed power with independent corroboration; no unqualified wiring guesses.
- B04: verify all current thermostat/fan command writers, queued callbacks, Tuya/OEM/manual/external clients and cutover quiescence.
- B05: qualified OEM documentation and existing physical behavior evidence; additional physical tests require separate authorization.
- B06: qualify **future** target SQLite/FS/process/lock/flush behavior through isolated test packaging; no production upgrade.
- B07: verify external AI analysis/proposal author and actual downstream apply permissions; never change its ongoing schedule without request.
- B08: owner decision about 180-minute limit scope for one-shot versus normal scheduled heating; no silent invention of global limit.
- Record evidence as PASS/BLOCKED/UNKNOWN; **do not upload private records** to this public repository.

## Mandatory stop lines

- Fast software progress can happen before G1 is complete, but **no live integration/deployment or physical actuation** until its relevant gates, author inventory and safeguards are verified and separately approved.
- Never stop whole AppDaemon, disturb Sky Radar/grid detection/Zigbee2MQTT, rewrite original history, reset utility meters, lose manual settings, or modify the home dashboard.
- No dual automatic thermostat/fan writers. Shadow remains strictly unable to command any real device.
- All future execution tasks must have a bounded issue, explicit permission, dedicated PR, CI, independent review and acceptance report. Each completed package can be merged only after review; do not automatically start the next one.

## Next owner-visible checkpoint

Codex produces a **reviewable, unmerged WP2A implementation PR** with fake HA contracts, independent energy/evidence archive, synthetic migration dry-run and final-head CI. G1/B01–B08 remain separately tracked in Issue #3. Later WP2B, test-HA, shadow, production connection and cutover each require their own stage-specific authorization and evidence.
