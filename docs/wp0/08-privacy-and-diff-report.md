# WP0 — privacy, action audit and documentation diff

## Authorized effect

The only remote writes in this task are the documentation branch/commit/PR in `dragonidf/ha-heating-2`. No PR merge, release, controller implementation, deployment or runtime was created. `dragonidf/ha-heating-ai` was read at immutable SHA; its code/tests were executed only as verified copies in sandbox temporary storage.

**Production command/config/lifecycle/backup writes by this agent:0. Legacy repository mutations by this agent:0.** This statement is about the recorded actions, not an independent assertion that no other user, automation or ordinary controller cycle changed the running system. Runtime0.3.21 drift from pinned0.3.20 is disclosed rather than hidden as a global “unchanged” claim.

## Read-only action audit

| Surface | Operations actually used | Excluded mutations |
|---|---|---|
| GitHub legacy | Repository/commit/tree/blob/file/release/compare/check-run/workflow metadata GETs at pinned refs | No branch, commit, PR, release/tag, workflow rerun, issue/comment or other legacy mutation. |
| HA control/model/source interfaces | ha_get_state and ha_get_entity; only targeted roles/attributes, registry metadata and source checks | No service/event call, control command or device operation; no helper/entity changes. |
| HA config/dependencies | Four ha_config_get_automation reads, targeted helper ha_get_integration, exact/broad ha_search, resource list | No automation/script/dashboard/resource/integration/registry edits, enabling/disabling or import. |
| HA history and metadata | Bounded ha_get_history; ha_get_app metadata; initial ha_get_system_health; ha_get_skill_guide; Jinja render of derived availability/config predicates | No Recorder dump/edit, check/fault injection, managed app lifecycle/proxy write or log-level change. Template rendering is a read calculation, not an intent/event. |
| File editor/AppDaemon/HACS | Status/options/versions and published module proof read | No File editor start/access expansion; no backup creation; no restart/start/stop/update/install. |
| Sandbox | Public-file materialization, checksum tools, git local branch, declared test dependencies in temporary environment, old make check/test and synthetic metric tool, documentation validation | No production address/token bound to tests; fake HA I/O only. Initial stalled sandbox test was terminated locally, not a production service. |
| New GitHub repo | Only docs/wp0 additions in audit/wp0-readonly, documentation PR to main | No source/spec/root changes, merge, release, deployment, integration, compute app or new controller tests/code. |

The transcript/tool history is the action evidence. No full production filesystem before/after diff, full service-author export or external task audit is available; those limits remain explicit. Opaque automation config hashes were re-read unchanged at H02. Existing live states naturally continued to change.

## Public-data policy and validation

- Only already public specification/code identifiers and purpose-based binding references are included. Physical IDs are logical aliases, **not MAC/Tuya IDs, device/config-entry unique IDs or inferred wiring**. New private bindings are represented as PRIVATE_BINDINGS/BLOCKED rather than raw exported configuration.
- Public-source comparison identified14 binding references not present verbatim in the approved package/public legacy files; all14 were replaced by purpose-based PRIVATE_BINDING markers before publication. The full mapping must remain in owner-controlled private evidence, not this public CSV.
- An exact-identifier check covered88 observed private registry/config/context/physical identifiers. Matching semantic alias text was replaced with a new logical role name; the reviewed final diff contains none of those88 original identifiers.
- No state.json, JSONL, decision snapshots, logs, Recorder DB, household time series, current comfort schedule/value dump, coordinates, IP/hostname, credentials, user/context IDs, tokens, external task payload or backup was added. Existing approved specification files remain byte-identical; their historical readings were not expanded with a new household dump.
- Public source/manifest/test-log hashes are checksums of public fixtures or source. Automation config_hash values are opaque read receipts. No private persistence SHA or verified backup claim is invented when artifacts were not obtained.
- The candidate diff is checked for exact private identifiers observed during targeted reads, secret/key/JWT patterns, IP/address patterns, unwanted binary/archive/database/runtime files, broken local document links, changed source/spec files, requirements/scenario ID loss and stale status substitution. Findings are reviewed manually; a heuristic scan alone is not a guarantee against every secret format.
- CSVs are parsed and validated:50 binding/policy rows,86 unique requirement traces,38 unique scenario reviews; all canonical IDs/statuses retained. Source paths/line anchors and declared old test/harness files exist in verified legacy baseline. `NONE` is a visible missing equivalent old test, not a skipped new test.

## Exact new-file allowlist

| Added file | Purpose |
|---|---|
|00-source-and-integrity.md |Immutable inputs, versions/drift, evidence index and complete file checksums |
|01-bindings-topology.csv |Sanitized physical-purpose/interface/unit/origin/quality/owner/fallback map, explicit blockers |
|02-command-owners.md |All known direct/indirect authors, external unknowns, modes/one-shot/manual and future fencing |
|03-storage-and-energy.md |Persistence/model/archive/counter chain and future dry-run/parity plan |
|04-runtime-compatibility.md |Observed runtime, actual old tests/metrics, dependencies and unmeasured2.0 limits |
|05-requirements-traceability.csv |86 requirements: old source/tests → proposed module → T-ID/scenarios/UI/gap |
|06-open-questions-and-blockers.md |Eight prioritized open items, contract differences and owner evidence required |
|07-gate-G1-readiness.md |Executive conclusion, WP0/G0–G9 statuses and C1–C4 acceptance mapping |
|08-privacy-and-diff-report.md |This action/privacy/diff report |
|09-scenarios-review.csv |All38 scenarios reviewed without pretending new execution |

All ten paths are under `docs/wp0/`, UTF-8 text only. No root AGENTS/README, approved spec, existing code, workflow, dependency declaration or test file is changed. Final publication checks compare the PR's ten added files and their Git blob hashes with the reviewed local bytes; PR remains unmerged. WP1 and all physical/production work require a separate instruction.
