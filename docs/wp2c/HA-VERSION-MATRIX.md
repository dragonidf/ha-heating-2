# HA / runtime qualification matrix

| Composition | Evidence class | Scope |
|---|---|---|
| Official Core2026.10.4 wheel + frontend20260930.5 + pinned generic-class import closure + Python3.14.2 + linked SQLite3.51.3, Debian bookworm disposable container | PASS_ISOLATED for executed native checks | actual onboarding/login/auth, SDK flow/entry/registry/panel, fake events, durable synthetic settings, lifecycle and failure recovery; exact logs in evidence/ and final CI artifacts |
| Pure contracts/core and native service on Python3.12/3.13/3.14 | MOCK_ONLY, full CI matrix | no HA SDK imported in pure modules; preserves351 accepted cases, adds native service/meter/boundary cases; unchanged strict mypy/95% coverage floor |
| Chromium/WebKit mobile+desktop standalone | MOCK_ONLY backend, real browsers | all80 accepted cases retained, same visual/accessibility criteria |
| Chromium/WebKit in actual isolated HA | native qualification only after actual browser results | injected session/panel, authoritative settings/history, reconnect, responsive and accessibility; official Playwright1.64.1-noble image pin in SOURCES.md |
| HA Core on Python3.12/3.13 | NOT_APPLICABLE to pinned SDK | upstream2026.10.4 requires Python>=3.14.2; pure modules still qualified in all three versions |
| Other HA Core/HA OS/HACS versions, owner Android WebView/screen reader/N100 | BLOCKED / NOT_TESTED | no compatibility or performance extrapolation |
| Household sources/devices/OEM/metrology/physical relay/actual fsync/cutover | BLOCKED | G1/B01–B08; G2–G9 unqualified |

The locally built image is content-addressed by the isolation report; it is not an official appliance digest. Base image and Core wheel are independently pinned by digest/SHA. HA dependencies are resolved during image setup; `--skip-pip` prohibits runtime installation. Build output records source/artifact hashes. No broad HA-version support is asserted from one SDK build.

The full official appliance image exceeded this sandbox filesystem quota. A smaller official PyPI Core composition was used without reducing native assertions. The host-built SQLite math extension initially required a newer glibc; removing that unused extension preserved required WAL/FULL/FTS/RTREE functionality and permitted the pinned bookworm ABI. Local storage constraints are test-host facts, not production requirements.
