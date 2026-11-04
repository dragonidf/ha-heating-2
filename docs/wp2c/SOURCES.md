# WP2C public source and provenance

All data fixtures are deterministic synthetic repository examples. No household configuration, account, token, telemetry or original Recorder file is an input.

| Source | Pin / purpose |
|---|---|
| Accepted repository main | `662a9c4324938981c33db3a7b429cf948abb8321`; includes accepted WP2B and WP2C authorization |
| [Issue20](https://github.com/dragonidf/ha-heating-2/issues/20) | owner-approved bounded native package; G1/B01–B08 remain BLOCKED |
| [Core PyPI](https://pypi.org/pypi/homeassistant/2026.10.4/json) | official wheel `homeassistant-2026.10.4-py3-none-any.whl`, SHA256 `71843060980a763187d856a8ff170640f1e287a7b741334cd838c81404f1f452`; Python>=3.14.2 |
| [HA Core source](https://github.com/home-assistant/core/tree/2026.10.4/homeassistant) | actual config_entries, core, helpers/entity_registry, sensor, panel_custom, frontend, http, websocket_api and onboarding/auth APIs; probatio schemas verified against this version |
| [Frontend PyPI](https://pypi.org/pypi/home-assistant-frontend/20260930.5/json) | official HA frontend20260930.5 required by Core2026.10.4 |
| [HA frontend source](https://github.com/home-assistant/frontend/tree/20260930.5) | hass injected panel, callWS, connection subscription and session lifecycle; see frontend/README.md |
| [HA websocket client](https://github.com/home-assistant/home-assistant-js-websocket/tree/9.7.1) | existing HA connection API; native panel creates no independent client/socket |
| Official Python image | `python:3.14.2-slim-bookworm@sha256:e87711ef5c86aaeaa7031718a69db79d334d94c545c709583f651b8185870941` |
| [SQLite official source](https://www.sqlite.org/2026/sqlite-amalgamation-3510300.zip) | SHA256 `acb1e6f5d832484bf6d32b681e858c38add8b2acdfd42ac5df24b8afb46552b4`; build before runtime; linked version and source ID observed |
| Official Playwright image | `mcr.microsoft.com/playwright:v1.64.1-noble@sha256:2f05f8a734509a7b3f26a912639488ee08f58a7b292d14d62271bcff9038768f`; browser/OS dependency pin, no runtime network |
| Accepted UI fixtures | frontend/src/fixtures.ts; export via tools/wp2c/export-fixtures.mjs; `--check` verifies exact generated native fixture bytes |
| Accepted core and tests | docs/wp2b/REGRESSION-BASELINE.sha256; all101 accepted files and351 cases retained |

`BUILD-MANIFEST.json` in each generated package records source and artifact SHA256 for every SDK/core/JSON/asset file. Accepted core algorithms are copied without behavioral changes. Only `from packages.` import prefixes become package-local `from custom_components.heating_ai.core.`. Browser bundles include local chunks/styles; no CDN resources. Final CI runs and exact tested SHA belong in the PR checks/description, avoiding an untested trailing report commit.
