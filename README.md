# Heating AI 2.0

Replacement heating controller for Home Assistant.

## Project status (2026-11-03)
- **G0**: ADR01–07 and four owner clarifications approved.
- **WP0**: audited and reviewed in [PR #2](https://github.com/dragonidf/ha-heating-2/pull/2).
- **WP1A**: accepted into main in [PR #6](https://github.com/dragonidf/ha-heating-2/pull/6); 92 offline tests and Python 3.12/3.13/3.14 CI.
- **WP1B NOW AUTHORIZED**: **offline-only** SQLite critical store, fake gateway and crash/replay/failure simulator. See [owner approval](docs/wp1b/APPROVAL-2026-11-03.md) and [detailed Codex task](docs/wp1b/WP1B-TASK.md), [Issue #7](https://github.com/dragonidf/ha-heating-2/issues/7).
- **G1 remains BLOCKED** with B01–B08 in [Issue #3](https://github.com/dragonidf/ha-heating-2/issues/3).
- **Not authorized**: WP1C, live HA integration, real device command gateway, deploying, physical tests, migration or cutover. Follow [roadmap and gates](docs/ROADMAP-TO-LAUNCH.md).

## Documentation
- [Project handoff](docs/spec/heating-ai-2.0/HANDOFF.md)
- [Owner approval](docs/spec/heating-ai-2.0/APPROVAL-2026-11-03.md)
- [Full architecture](docs/spec/heating-ai-2.0/02-Architecture.md)
- [Full engineering specification](docs/spec/heating-ai-2.0/03-Codex-specification.md)
- [Tests](docs/spec/heating-ai-2.0/04-Test-strategy.md)
- [Requirements](docs/spec/heating-ai-2.0/requirements.csv)
- [Scenarios](docs/spec/heating-ai-2.0/test-scenarios.csv)
- [Migration gates](docs/spec/heating-ai-2.0/06-Migration-and-acceptance.md)
- [WP0 audit readiness](docs/wp0/07-gate-G1-readiness.md)
- [WP0 blockers](docs/wp0/06-open-questions-and-blockers.md)

The legacy application `dragonidf/ha-heating-ai` is a read-only baseline. **No secrets, addresses, production config, runtime state, telemetry or backups may be committed to this repository.**

## WP1A offline library

`packages/contracts` provides immutable versioned data; `packages/control` provides pure evaluation/reduction into intent descriptions. They contain no actuator route. All policy values and fixtures are synthetic; G1 remains BLOCKED. See the [WP1A report](docs/wp1a/REPORT.md), [decisions](docs/wp1a/ADR-WP1A.md), [86 requirement mappings](docs/wp1a/requirements-coverage.csv) and [38 scenario mappings](docs/wp1a/scenario-coverage.csv).

Python 3.12/3.13 are the specified baseline; CI also checks 3.14 compatibility. Runtime dependencies: standard library only. Use an isolated local environment:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
make check PYTHON=.venv/bin/python
make benchmark PYTHON=.venv/bin/python
sha256sum --check docs/wp1a/SHA256SUMS
```

The pure WP1A modules retain their standard-library boundary. The combined test suite now also needs a qualified linked SQLite; use the WP1B environment below when the native library is unqualified. Benchmarks describe their test host only and cannot accept the future N100 gate. No Home Assistant connection is needed or provided.

## WP1B offline proof

`packages/control_store` persists synthetic critical state; `packages/simulator` can only record fake actions in memory. See the [report](docs/wp1b/REPORT.md), [decisions](docs/wp1b/ADR-WP1B.md), [additive requirements](docs/wp1b/requirements-coverage.csv) and [scenarios](docs/wp1b/scenario-coverage.csv). G1/B01–B08 remain BLOCKED; no WP1C or real device transport exists.

Run only in a disposable Linux development/CI environment. The pinned SQLite build downloads official source and creates a test library under `/tmp`; it does not replace system or production libraries:

```sh
.venv/bin/python -m tests.fixtures.build_sqlite
mkdir -p /tmp/heating-wp1b-db-tmp
LD_LIBRARY_PATH=/tmp/heating-wp1b-sqlite-3510300 TMPDIR=/tmp/heating-wp1b-db-tmp make check PYTHON=.venv/bin/python
LD_LIBRARY_PATH=/tmp/heating-wp1b-sqlite-3510300 TMPDIR=/tmp/heating-wp1b-db-tmp .venv/bin/python -m tests.properties.benchmark_store
sha256sum --check docs/wp1b/SHA256SUMS
```

Use a disposable directory on the filesystem being evaluated as `TMPDIR` and record its type; tmpfs does not prove disk durability. The actual linked SQLite/version/source ID must qualify before any simulated HEAT. CI checks 3.12/3.13/3.14 with the pinned library, retains every WP1A test and exercises isolated SIGKILL/fault scenarios. The deliverable remains an unmerged review PR.
