# Heating AI 2.0 — approved package handoff (read first)

**Architecture:** approved ADR01–07 with 4 mandatory owner clarifications on 2026-11-03.  
**Implementation:** not started. **Production changes:** prohibited until a separate explicit deployment approval.  
**Repo:** `dragonidf/ha-heating-2`; **legacy pinned:** `dragonidf/ha-heating-ai@db7d7ce9c53e4e88c1c27ee10e1f53d6cce10426` (v0.3.20).

## Canonical reading order

1. `APPROVAL-2026-11-03.md` — owner approval and 4 non-negotiable clarifications.
2. `00-READ-FIRST.md` — original Work cover document and scope.
3. `01-Audit-and-feature-register.md` — verified baseline, limitations, feature parity.
4. `02-Architecture.md` — ADR01–07, contracts and bounded fallback.
5. `03-Codex-specification.md` + `requirements.csv` — normative design and canonical requirements IDs.
6. `04-Test-strategy.md` + `test-scenarios.csv` — mandatory test expectations.
7. `05-UI-design.md`, `ui-concept.svg/png` — style/prototype direction, not verified live UI.
8. `06-Migration-and-acceptance.md` — G0–G9 gates, cutover and rollback, not permission to deploy.
9. `validation-summary.md` — tests of old code only; `manifest.sha256` — hashes of original Work files.
10. `CODEX-WP0.md` — **the only executable assignment now** (read-only baseline and evidence audit).

The original Work documents remain unchanged. The approval is an addendum: do not silently weaken P0/P1 or assume unverified HA inputs. If specs conflict, record an ADR/question before implementation.

## Procedure to add to GitHub (DO NOT upload ZIP as the only repository content)

1. Confirm repository visibility. It is currently **public**; do not include secrets, state.json, Recorder databases, logs, exact property coordinates or private HA exports. Prefer private visibility if confidential project context is needed, but that change requires owner action.
2. Create a branch such as `docs/approved-spec-2026-11-03` in `dragonidf/ha-heating-2` (do not touch `dragonidf/ha-heating-ai`).
3. Extract the ZIP. Upload the extracted `docs/spec/heating-ai-2.0/` tree **as individual files** preserving paths. The existing root README should not be overwritten. Check `manifest.sha256` against the 12 original source assets.
4. Commit documentation only and open a PR: `docs: approve Heating AI 2.0 architecture and WP0 handoff`.
5. Review that all files, especially the addendum, requirements, scenarios, design reference, and WP0 task, appear in the PR. Merge/leave the PR according to the owner's decision. For Codex, specify the branch or merged default-branch commit containing those files.
6. Open Codex attached to `dragonidf/ha-heating-2`; provide the concise entry prompt below, point it at `docs/spec/heating-ai-2.0/CODEX-WP0.md`, and prohibit WP1 or deployment.

## Concise entry prompt for Codex

> Implement only `docs/spec/heating-ai-2.0/CODEX-WP0.md` for Heating AI 2.0. ADR01–07 and four clarifications are approved in `APPROVAL-2026-11-03.md`. Read every source document and both CSVs. Work only in `dragonidf/ha-heating-2` on branch `audit/wp0-readonly` via documentation PR. Read old repository at pinned commit. Production HA, devices, active heating, legacy repo and all connected systems are **strictly read-only**; no backup creation, installation, tests with actual relay or restarts. Do not publish private HA artifacts in this public repository. Report G1 blockers honestly; do not progress to WP1 without a separate instruction.
