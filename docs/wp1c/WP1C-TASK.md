# WP1C — Codex execution contract (approved offline only)

**APPROVED 2026-11-03, offline/synthetic ONLY.** This file binds Codex to the comprehensive implementation plan and acceptance criteria in [Issue #11](https://github.com/dragonidf/ha-heating-2/issues/11). It intentionally **does not rewrite the 86 canonical requirements, 38 scenarios, or the accepted architecture**.

## Execution order

1. Read root `AGENTS.md`, `docs/wp1c/APPROVAL-2026-11-03.md`, and full **Issue #11**.
2. Read `docs/spec/heating-ai-2.0/02-Architecture.md`, `03-Codex-specification.md` (especially D01–D10, P01–P12, M01–M09, F01–F06), `04-Test-strategy.md`, `06-Migration-and-acceptance.md`, `requirements.csv`, `test-scenarios.csv`.
3. Read prior WP1A/WP1B reports, accepted `packages/contracts/`, `packages/control/`, `packages/control_store/`, `packages/simulator/`, and their tests. Maintain their **155-test regression baseline** without weakening any existing P0 condition.
4. Implement **one substantial cohesive package** in `feature/wp1c-offline-model-planner`: pure thermal baseline/observer, bounded deterministic planner, qualified champion/challenger evaluation, pure fireplace/night fan arbiter. Typed, versioned synthetic inputs and unambiguous uncertainty.
5. Cover winter/night/07:00 morning 30-minute need and safety exceptions; DST Kyiv; scheduled/unknown outages; 3/6/9 candidate scenarios; immutable 12h forecast reference and comparison-ready evidence; weather/source quality; manual/STOP/grid safety; budget and unknown-power gaps; stale results; no hidden disappearance of the morning plan. Cover fan hysteresis and arbitration. No live device commands.
6. Add focused negative/property/scenario tests first for safety-critical edge cases, then broader synthetic end-to-end planner scenarios; verify Python 3.12/3.13/3.14, type checks, checksums and regression suite. Report actual runtimes/test environment rather than asserting N100 qualification.
7. Source legacy two-state thermal equations/units from pinned old repository **read-only** when feasible. If real baseline coefficients or parity cannot be verified, implement only a clearly labeled synthetic model with explicit `NOT_PARITY_VERIFIED` status; never invent real household calibration.
8. Document `docs/wp1c/REPORT.md`, ADR, additive 86/38 traceability, limitations and final-SHA CI links. Prior incomplete physical/integration cases remain `BLOCKED/NOT_IMPLEMENTED`.
9. Open a **single unmerged PR** and stop. Provide a short handoff: PR URL, final SHA, number of tests, CI result, critical limitations. Independent ChatGPT review will inspect changes; **do not auto-merge or begin WP2A**.

## Boundaries

- No edits to production Home Assistant or old repository; no actual hardware service, MQTT/HA transport, enabled integration, device test, installation, sidecar, migration, private config/export/backup, or access to live household sources.
- Use synthetic fixtures only. Pure planner/thermal/fan code cannot import the simulator's `FakeActuator`, control store I/O, network, clock or Home Assistant APIs.
- The planner produces **only typed proposals**; physical authorization remains exclusively in previously accepted safety kernel/future separately authorized gateway.
- Do not silently decide B08 or redefine any global session cap; do not alter automatic heating authority.
- G1 / B01–B08 remain BLOCKED; WP1C offline acceptance will not pass G1/G3/physical safety.

**Issue #11 is the complete feature checklist and acceptance specification.** Complete its full offline scope in one code PR; do not stop after a prototype.
