# WP2B browser and accessibility matrix

All values/screenshots are synthetic. Commands in frontend/README.md; exact lockfile/browser versions are part of SHA evidence.68 cases =17 operator flows (including all14 original flows) ×4 projects; no retry/skip/xfail. Four checked-in Home golden images are generated with real Chromium/WebKit, not image generation.

| Check | Chromium390×844 | Chromium1440×1000 | WebKit390×844 | WebKit1440×1000 |
|---|---|---|---|---|
| Comfort/authority/alert and chart start in first viewport; Home screenshot | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE |
| Three-tab navigation, focus, keyboard/touch slider and table | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE |
| Real IndexedDB save/reload/cancel/undo and two-client CAS/rebase | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE |
| Full-range dense history (>8000), endpoints/gaps, date invalidation and empty state | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE |
| Midnight counter split, changing tariffs, separate estimated costs | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE |
| Disjoint merge, all12 comparison, explicit collision choice and dirty quick-save protection | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE |
| Offline/in-flight/reconnect, readback failure/draft, denied/revoked | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE |
| Missing original/actual-only, scoped energy/cost, Kyiv23/25h dates | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE |
| Safety>manual>quality>comfort>budget; fake ACK/heat/STOP/zero/unknown | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE |
| Modal focus/Escape, one-shot, nested model promotion/rollback | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE |
| Axe WCAG2A/AA/2.1AA, local light/dark, rem200%, long Ukrainian | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE |
| Additional320/700/1100 widths,44px targets, reduced motion | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE | PASS_OFFLINE |

Status above refers only to final successful local/CI runs linked in PR checks; failures remain in CI logs/artifacts and are corrected rather than skipped. Native HA SDK/session/theme/WS is NOT_TESTED; actual owner phone/Android WebView, practical screen-reader and10-second comprehension task are BLOCKED/NOT_TESTED. Automated axe is not a complete WCAG certification.

Screenshots normalize font during capture only to installed DejaVu Sans, with a predeclared1.5% pixel rasterization allowance. Shipped UI uses the system font stack and is separately exercised by normal browser tests. Default Home main-content height target≤1300px and chart-start target are asserted on mobile. UI text uses rem so the200% check enlarges actual text, rather than a no-op root font change against px labels.

Local managed host lacks some browser system libraries. They were downloaded/extracted only under /tmp; WebKit's temporary downloaded sys/lib directory links those files. Actual ctypes/ELF loading and WebKit27.2 navigation were verified. The local `PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1` bypasses only Playwright's system ldconfig-cache precheck, which cannot see temporary libraries; it does not skip a browser test or substitute jsdom. CI uses supported Ubuntu test-host dependency installation and leaves that flag unset. No production system was read/installed/changed.

Review corrections keep all four existing golden PNGs unchanged; the final matrix compares them without regeneration. All56 original browser cases remain, with stronger explicit same-field conflict resolution.
