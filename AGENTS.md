# AGENTS.md — Heating AI 2.0

Before working, read these repository documents in full:
1. `docs/spec/heating-ai-2.0/HANDOFF.md`
2. `docs/spec/heating-ai-2.0/APPROVAL-2026-11-03.md`
3. `docs/spec/heating-ai-2.0/CODEX-WP0.md`
4. `docs/spec/heating-ai-2.0/02-Architecture.md`
5. `docs/spec/heating-ai-2.0/06-Migration-and-acceptance.md`
6. `docs/spec/heating-ai-2.0/requirements.csv` and `test-scenarios.csv`

## Current authorization
Only **WP0: read-only inventory, source mapping, risk and blocker analysis, compatibility review, and documentation in this repository** is approved.
Architecture ADR01–07 is approved with the four owner's clarifications in the approval file.
Do not begin WP1 or implement/install new controller code.

## Hard constraints
- Never change production Home Assistant settings, files, helpers, automations, services, running add-ons, entities, or connected devices.
- Never issue control commands, reboots, updates, or physical fault injections.
- Never modify `dragonidf/ha-heating-ai`; it is read-only baseline.
- Do not create production backups or retrieve/commit unredacted private runtime dumps without separate authorization.
- Do not place credentials, token values, private IP/addresses, identifiable telemetry, or private configuration in GitHub, PRs, logs, or CI artifacts.
- Check actual evidence and distinguish confirmed findings from assumptions or historical observations. Mark unavailable evidence **BLOCKED**.
- Work in a dedicated branch and PR, preserving traceability. WP0 report must state what was read, verified, not verified, and what is blocked.
- No automatic progression from WP0 to WP1 or production cutover.

All safety-critical and operating decisions defer to the approved docs and explicit owner approval.
