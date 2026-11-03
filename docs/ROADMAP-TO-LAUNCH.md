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
| WP1C | APPROVED **OFFLINE ONLY** | `docs/wp1c/APPROVAL-2026-11-03.md`, `docs/wp1c/WP1C-TASK.md`, Issue #11 |
| Live deployment, actual actuation, cutover | NOT AUTHORIZED | Gates G2–G9 remain future |

## Parallel lanes

### Lane A — code on isolated, synthetic/offline development environment

1. **WP1B COMPLETE:** offline SQLite durable store, boot/owner/one-shot persistence, fake gateway, prioritized STOP, 13 crash checkpoints and CI; PR #9 accepted. No real device writers.
2. **WP1C NOW — APPROVED OFFLINE ONLY:** develop full synthetic thermal model, bounded blackout-aware planner and immutable 12h reference, champion/challenger qualification, fireplace/night fan demand arbiter; preserve all prior safety regressions. Issue #11 and `docs/wp1c/WP1C-TASK.md`; no production/real commands.
3. **Future staged integration (requires another approval and gate evidence):** non-actuating native HA adapter in an isolated HA test instance, with dedicated shadow-only authorization; packaging/storage compatibility and real SDK behavior tests; never connect concurrently as a second writer.
4. **Future UI/history/migration:** new separate dashboard route, evidence/ledger, frozen 12h forecast and factual comparison, continuity/replay importer, read-only first. All requirement and scenario IDs must survive.
5. **Future release preparation:** G3 software target tests, G4 import dry-run, G5 ≥7-day/3-cycle zero-write shadow; G6 OEM tests, G7 one-writer cutover, G8 probation, G9 quantified quality; each has explicit owner permission and evidence.

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

Codex produces a **reviewable, unmerged WP1C code PR** with deterministic synthetic model/planner/learning/fan evidence and full CI, while G1 blockers remain independently tracked in Issue #3. Next phase requires separate approval; no Home Assistant connection/deployment under WP1C.
