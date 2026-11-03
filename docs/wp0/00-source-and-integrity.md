# WP0 — source, integrity and evidence

Audit date: 2026-11-03 UTC. **WP0: BLOCKED; G1: BLOCKED.** The authorized audit deliverables are prepared; unavailable evidence is not accepted as verified. No Heating AI 2.0 code, deployment, shadow runtime, import, production backup or device test was created.

## Immutable inputs

- New repository: [dragonidf/ha-heating-2](https://github.com/dragonidf/ha-heating-2), public. Specification/root rules pinned at `232e8a61985c98bb34d730c56d6cd51a8614209a`; branch `audit/wp0-readonly`, base `main`. Root AGENTS read first. HANDOFF/APPROVAL/CODEX-WP0 and every other specification asset were read; SVG source and PNG concept inspected. HANDOFF/approval supersede original pre-approval labels without editing original documents.
- Legacy audit baseline: [0.3.20 at db7d7ce9c53e4e88c1c27ee10e1f53d6cce10426](https://github.com/dragonidf/ha-heating-ai/tree/db7d7ce9c53e4e88c1c27ee10e1f53d6cce10426), committed 2026-11-03 07:25:35 UTC. All **103** files materialized in an isolated sandbox and matched to Git blob bytes, including nine modules, generated assets, frontend, docs, examples, tools, tests and workflows. No mutable legacy main substituted for this baseline.
- `sha256sum -c manifest.sha256`: **12/12 PASS**. `sha256sum -c handoff-manifest.sha256`: **16/16 PASS**. All 19 repository files (17 specification assets plus AGENTS/README) also match their pinned Git blobs. CSV BOM/CRLF and exact trailing newlines were preserved. A text-transport newline mismatch was corrected locally against original blob bytes before verification; no source content was edited.
- Live read at 12:17 UTC reports **0.3.21**, not the pinned baseline. Published nine module hashes match public [0.3.21 commit 9cfa7d50e3d92d5d6dd8d4c46161d05e9b7ceda6](https://github.com/dragonidf/ha-heating-ai/commit/9cfa7d50e3d92d5d6dd8d4c46161d05e9b7ceda6) release manifest, 9/9. Six hashes match 0.3.20; heating_climate, heating_recovery and generated heating_ui_assets differ. This is published runtime self-report, not an independent filesystem measurement. The newer commit adds tick-state caching/diagnostic timing and refresh at dispatch. It was read only to explain drift, never installed or substituted in baseline tests.

## Evidence index and limits

| ID | Evidence | Result / limits |
|---|---|---|
| E01 | Pinned spec/legacy Git trees, blobs and local checksums | Complete byte identity; file inventories below. Source location references in the trace CSV resolve only within pinned legacy SHA. |
| E02 | Both spec CSVs parsed as UTF-8-sig | 86 unique requirements: 49 P0, 37 P1; 86 unique T-IDs; 38 unique SC01–SC38. All scenario references resolve; all 86 requirements occur in scenarios. Statuses unchanged: specified_not_implemented / planned_not_executed. |
| E03 | Exact SHA GitHub CI | [Tests 41596297272](https://github.com/dragonidf/ha-heating-ai/actions/runs/41596297272): success for Python 3.12/3.13; [release 41596985478](https://github.com/dragonidf/ha-heating-ai/actions/runs/41596985478): success. Historical CI is distinct from this audit's local run. |
| E04 | Isolated unchanged baseline tests | Results, environment and log hashes are recorded in 04-runtime-compatibility.md. Existing tests prove software behavior of 0.3.20 only; no new T-ID or physical acceptance pass implied. |
| H01 | Targeted live states/registry, 11:53–12:22 UTC | Seven initial control/model/permission states; later 31 source roles returned without missing IDs. Public report keeps roles/units/availability limits; no raw readings, household schedules, unique device IDs or user/context identities. |
| H02 | Four automation get calls, re-read 12:17 UTC | Watchdog hash `bbec8c6a8dd6c5b6`; weather `01a6b27c70a6b0f0`; updater `ec3d920764714930`; night circulation `10c333e307a99c47`. All unchanged from 11:55 UTC observation. These opaque config hashes are read receipts, not backup SHA-256s. |
| H03 | Exact thermostat/fan references and broad literal climate./fan. searches, 12:21 UTC | partial=false, has_more=false; climate configs: watchdog only; fan configs: night automation plus read-only template consumer. No matching scripts/scenes. Dynamic targets, inaccessible app code, external clients/OEM schedules not ruled out. |
| H04 | Five relevant helper definitions read at 12:19 UTC | Canonical total → compatibility meter → daily/monthly/yearly; definitions and options inspected. Private payload not exported. See 03-storage-and-energy.md. |
| H05 | Runtime settings receipt/template and File editor metadata, 12:19 UTC | Published persisted revision matches current revision. Phase topology has zero entries and no verified flag. Fireplace binding absent from small UI entity map. File editor state error, enforce_basepath=true; never started or reconfigured. Full YAML/private assets BLOCKED. |
| H06 | Bounded Recorder history 05:30–07:40 UTC, read about 12:22 UTC | Four channels: thermostat 15 rows, mode 3, power 57, total 24; each has_more=false. No raw history published. State changes are not a complete service-call log or proof of physical effects/author identity; this is not a full archive export. |
| H07 | HA health/AppDaemon metadata, 11:55–11:58 UTC | Version observations only summarized in 04. Recorder SQLite report does not establish both future linked SQLite libraries or filesystem durability. |
| H08 | Registry and UI-resource reads, 12:23 UTC | Actual thermostat has registry identity. Six sampled AppDaemon sensor states have no returned registry entries although their HA states exist. All 19 UI resources paged in one response; one heating-local module resource found. No resource/config changes or browser live render. |
| H09 | Targeted registry/interface reads, 12:39 UTC | 23 upstream registry entries read: Solarman grid/connection/GRID power, MQTT inlet channels, Tuya Local/Cloud group aliases, google_weather, svitlo_live and Tuya relay sources. Also21 control-helper interfaces returned with no lookup errors; current values/private identities withheld. Registry origin is software provenance, not wiring, calibration or freshness proof. |

Private source artifacts have **no payload SHA asserted** because no authorized owner-controlled export was obtained. Session read receipts and public source hashes are not a substitute for a replayable private baseline. B01–B07 specify the missing access/evidence. No unverified parameter is promoted to a fact.

## Owner clarifications and trace meaning

C1 = morning energy/continuous 30min/stable original plan; C2 = independent fallback/manual priority/stale-event protection; C3 = complete feature/model/counter/one-shot/fire/fan/ventilation compatibility; C4 = three main tabs, 12h original vs fact, mobile/accessibility and expert details. Every trace row identifies applicable C1–C4; the gate report gives their acceptance mapping.

`MAPPED_NOT_ACCEPTANCE_PASS` certifies the audit linkage, not a new implementation. Proposed modules and T-IDs do not exist yet. Existing legacy tests are relevant partial evidence only. `NONE` explicitly means no equivalent executable legacy test was identified; the canonical future test remains required.

## Specification file inventory

| File | Bytes | Git blob SHA-1 | SHA-256 |
|---|---:|---|---|
| `AGENTS.md` | 1771 | `d4961ac0ee3ed7b0e5d85ab4c5a571fc80cdb28d` | `8dd9e9979e74d69f71a4d683e482fed78af07c8b7f263b8b86c745898f52e159` |
| `README.md` | 956 | `55d4215cbd3e3583cde432df3b7dd7efdab648f6` | `28b4bc4227e30dcc3b3ce59ccd7e236ea9bb35b945af5a62970b1bc080d2235f` |
| `docs/spec/heating-ai-2.0/00-READ-FIRST.md` | 7778 | `96ff3b0217b63753a82517567de7d0822216d60e` | `599fa46380c745155612bfb28503e442bdb7028cd67947cf417dc49c239f3c92` |
| `docs/spec/heating-ai-2.0/01-Audit-and-feature-register.md` | 23194 | `6c59f609376abd9654d59022f2e7f4d0b948e166` | `94681a8e753502e6bc556735cc55205c153479a70321e5411078f2cf94d63d29` |
| `docs/spec/heating-ai-2.0/02-Architecture.md` | 23491 | `9143aa4517b3a8c51d20564082fbe0a487309b93` | `18cdb6226ae4e25c97747668409d75bb22f1daad11c11a584206e71dbcde74fe` |
| `docs/spec/heating-ai-2.0/03-Codex-specification.md` | 27235 | `70b022d69b9f580636c22827178a0104c5d327e0` | `4a34e5bdfc4cc7b5691df58b5c2542c247a559de9acdf6e0ed797540580fe791` |
| `docs/spec/heating-ai-2.0/04-Test-strategy.md` | 15261 | `54fbfc69a557c9cfe904e46d655aeaf1ddaf4649` | `afaffd6509c70ac97820b9aa575436b17e80aa3d061e5d52ee37045a45244a26` |
| `docs/spec/heating-ai-2.0/05-UI-design.md` | 13338 | `00aac0920fa035a83a667d2e565e2e908fbee322` | `2b18fd3dfa949987dd13661fea4f7ff1bc39d6fa458222cdfd095a303f64db3b` |
| `docs/spec/heating-ai-2.0/06-Migration-and-acceptance.md` | 14283 | `5efa403f31cbc2c4085eda5577d8c8bd8f409b02` | `da59bf0044e4d8eaac03753974b68ae7dd5140260423d627d229457ba4e40467` |
| `docs/spec/heating-ai-2.0/APPROVAL-2026-11-03.md` | 5230 | `057fa3039a2c7055d33711440610d3dcc416a25f` | `df9e5172ee9f9d2159e50c38e325b3190adf00ae7157029996029490603c312e` |
| `docs/spec/heating-ai-2.0/CODEX-WP0.md` | 12868 | `217f044510a4ca38e9458cc334cbce70e5645d38` | `b80fb2d43cb9079fad379ec5d28f8988979da36de4dd4b0cd259c5dc15f03042` |
| `docs/spec/heating-ai-2.0/HANDOFF.md` | 3500 | `2242620a0f620e8613684fb9936d10db30e79d41` | `8d7a8153bd34d5d6184e74bbd5bd9f956ce618693cb6a045bb17fdf120692938` |
| `docs/spec/heating-ai-2.0/handoff-manifest.sha256` | 1369 | `e9d23ae5ccb45047e57b54fed52ce51ad17e04af` | `bbf755025379b389b13aa4287335e016b0795c009762ff228cdba30253a42ad0` |
| `docs/spec/heating-ai-2.0/manifest.sha256` | 1042 | `b0fee6e347d9191facf1caabedf906f2f879fef8` | `62af14969f4c68985c791ed9b0cfe13a5bd2af0e6410d29e8eabe568dab46398` |
| `docs/spec/heating-ai-2.0/requirements.csv` | 20484 | `47f2a522c7ca3c05d86284b62703412859dc2a48` | `fa8a758fe10ddf52d611d52d27f2f2a54c8a797a83536772abd39b317d75c757` |
| `docs/spec/heating-ai-2.0/test-scenarios.csv` | 8092 | `5741dc93f91195874911059b17c978ac16d9ec4b` | `24a762da1f3d6ad7163d0a37f263376ed46172b5ce2f06124a4587d33480f4f3` |
| `docs/spec/heating-ai-2.0/ui-concept.png` | 111366 | `a69daba8f6117c603d4c8b31115619523c624a33` | `662f0d2371dd42b8ab2c0ffe0422f6e7f4d6222dde7144882391ed80a22493b5` |
| `docs/spec/heating-ai-2.0/ui-concept.svg` | 13309 | `ccd1742467a16d160d43e4a4a2ced16cf35c3a0c` | `0c1842da9eac3253343b5ddc563c18cc434407ca47d8462f2fa95cd276da5428` |
| `docs/spec/heating-ai-2.0/validation-summary.md` | 4122 | `2c84d2fbb6503440d5db937e6e293d1eca0626bd` | `2abcfca400f3086a34e878da2706b1ebea9bcc56a5d3029dfa4f10e89adef378` |

## Complete legacy inventory

SHA-1 is Git object identity; SHA-256 is byte checksum. This list contains public code metadata only.

| Legacy file | Bytes | Git blob SHA-1 | SHA-256 |
|---|---:|---|---|
| `.github/workflows/release.yml` | 1135 | `5e3e541de58124152d91d5ef52127c33b0536502` | `5aa529093f2aa2949a69f0b06e5597537aee37372f0c8486186742e24f8350ec` |
| `.github/workflows/test.yml` | 1522 | `13823bc7645fcd03bf5e1818af99a04e7c0163d9` | `726be332f50e9f7f42d4e6dea2e9b05975383dbe05c3b610ee98bdd09e8d1088` |
| `.gitignore` | 139 | `7c94f3a7158aee66cd7e1aaefd8c71ce29e1dc89` | `fa7e2faf0d21fa71aa81857a4248c4dde56c02e142e1686dfe0742415591b185` |
| `AGENTS.md` | 3240 | `173de805018a1399e882c36a07468af34c0863dc` | `607302ce460e01db2a4602aeaad16592b63d60c531011b95c5f45fb0cfdfed36` |
| `CHANGELOG.md` | 56687 | `603d3bf01e087308aa3f479450d41c9eee9d992d` | `4d1094acab32b98a436cb02417ef277e2a73ac8c2f1be2f467caaeb421ecef69` |
| `Makefile` | 456 | `45934a75a6d4ed264f2648cae68c574f317f7357` | `dfb640fcce2d96495c36481f9dc20dfc2745b521f251aec7e40d7bff6396a955` |
| `README.md` | 7185 | `bcef40a4ab9f4947fa1d37025c90dd6702d70f79` | `fead5222f5efd4e5c9d8c37c04bc0827deb4cdf68b94bd10ef88d5970fafc756` |
| `VERSION` | 7 | `f9a4b5f993c4cf98337519a029a6620a51cf8911` | `52f0f7238f6b810629ffd4feb4abfd7c5bc147dbd1372191f8843b2016db5c39` |
| `apps/heating_ai/heating_climate.py` | 146133 | `9d1af08bef14b2d85ac35263559cf3146481bfcc` | `3da2678508afda4fe11703f62141fbb2e7ed574f89a84d7597a6d3b3dfeb1df9` |
| `apps/heating_ai/heating_environment.py` | 15336 | `d808ffd448b2a4fecf0989a47c07714463e0b0d8` | `e9f7af927a35e93dc66f94614f9a865d195486bd0c7fe5951103713dbb4707b8` |
| `apps/heating_ai/heating_fallback.py` | 28335 | `7f24b9473b78677762cb016cb81c8f3284fd6b16` | `da872cbf269bbae62eb2ee79dd2b4ace6fe00cce9e23f8a2a792024ac8c34389` |
| `apps/heating_ai/heating_model.py` | 67160 | `5dd99bd097af40f7796a65ff8495e7ae8162193f` | `9028b4bd811d37052b4c4b01b226d0ddb6f8d88871479483c07bd547a20bdc5a` |
| `apps/heating_ai/heating_outages.py` | 6730 | `9ca4bd13365107559d61daab96bf59e3b11f076f` | `f3b410c68fb60e2cffd1430ffbc0b66a77c505fafebe51fadfce04ca839bc163` |
| `apps/heating_ai/heating_recovery.py` | 121443 | `0e0107753d8f39f7a4c115b8ffa58dab0cb882a1` | `5ac38b1b98bc69ab3b2b3e7b09d4278b3bf31edbc3b14063a2ee1ba661b93ec7` |
| `apps/heating_ai/heating_stability.py` | 22675 | `7357aed2c654337084c6504615396d006d382633` | `3d2c3afcc0a82cc089715920c7bf0444b8d2963e56e6ddf24be27d8ab88887b4` |
| `apps/heating_ai/heating_ui.py` | 30530 | `19c261803ec78644ce690ce9a235f4444a59a7de` | `96797163342cf797681526e36c416d4187dee672f7e5a954f5ff1140aec7d926` |
| `apps/heating_ai/heating_ui_assets.py` | 201454 | `9bcada5fbab45345e0a9f986ae445c51c87933b3` | `b7565ce0e73d48af828319eabb57f23e337e44c8ca02b97a9d706b5001da10d3` |
| `apps/heating_ai/release.json` | 900 | `687b7d94f684da8956e6933d1f2cad9bdaa323be` | `8778b0420767f3c52f18d0f00aa7ce5ec9894e6fb0289799b010501e1d2a7d1c` |
| `docs/audit-2026-10-27.md` | 8982 | `f50951c57d36c5c9a63e9bc474d48a31bc6cc544` | `d4a9ace7997ff51d733bc8c01648732f8c279549fb73c2ab1aa405def3a16b30` |
| `docs/automatic-updates.md` | 8885 | `7c1bac13ddd2ff9e52b88950b1cc129de4fddfc7` | `c01168e84c3da8d2dc977c074020562f6de09c7c14f0ee88ff5014705c493b4f` |
| `docs/boiler-control-incident-2026-11-03.md` | 7575 | `69fc67e1b3974c73b2542c4abdfd82a04f975d27` | `fdb4e83fdc310e55ec91cfaffa62c6a01fff52a4ac13f5980cc3b3641eed7a9f` |
| `docs/comprehensive-validation.md` | 14385 | `50e40f68f138286daf140fe963861362e118679d` | `31bb1da14bf4ffada9bee0361d051d8a2ec78f7f24953f72ca0e163b85713015` |
| `docs/dual-power-accounting.md` | 6736 | `ed1d5bf089f51893f211987da39656b8a315ec17` | `a0e486ae9f843e344886d7005af21c9db900a6f4cfa8f301bff241d05295b1bf` |
| `docs/fireplace-circulation.md` | 5464 | `538da6c3fdc180e18120eb0303a09b39396fce0f` | `40d3778637d09e5bf8e6c6db3dd4fac606e9ef6a749410ba044dfe3cbdbf6902` |
| `docs/installation.md` | 13776 | `ec5b2d5c062ec532b7eaeaec92ce7c8890d2c033` | `50e693ff37a744455df83cf06e74ac2e275b4f0f4eebad8540923e2579501f3c` |
| `docs/long-forecast-validation.md` | 11813 | `18d99cae8b8e8c978c2094efe0437abb7ef0a963` | `e4c27efb7e393ba1e50c6b657b0960c7e319a6119bb2c1a14d48dc4760f99506` |
| `docs/morning-reserve.md` | 15235 | `03658575bebae5aeefbeaebfe69f22b854567570` | `74e4227b7cbbbf830d91e8235ce55c2f124bc2d05d11773617b5ae564053e17a` |
| `docs/outage-schedule.md` | 5944 | `51ebba43b6872ab140a28cfe1ddd76e68e1f76f4` | `a15479c71f7c19f2bde8a6bdb2a363cb444e68199ddbccd4c2deee13be435960` |
| `docs/plan-execution-accountability.md` | 5007 | `c932505ec7098ad5165edc5cac0c50dd7c4ad3dc` | `4326a8724151c806c31cda00766aef0f225e2149ee067ad35b8ea507d026424d` |
| `docs/power-ventilation.md` | 13676 | `b4d51f1709dc9460da536621b0a52bb1c39feb7b` | `bed7ef04ae075e70329c01fb44130857eee67ab836350fd8e65361ab14458f0c` |
| `docs/qa-audit-2026-11-01.md` | 34138 | `71811d6571c473ef8c4c81e2ad2994a954d38117` | `29675aa26e102f383df9f68bb42ff6b4dd9c051765baa99ec10d4f332b0804da` |
| `docs/ui-design.md` | 3911 | `1fe490170f9f8e7d10076cc54aa29d4f2090c51b` | `3af73aa25a71db800ba34e6d3a325a8b7635b04893955cc826124954b4f75cde` |
| `docs/web-panel.md` | 17129 | `9878efa6859da923334ba23593a5c9cfc08ad59d` | `014d79c23d40b5eec2431e5195da1f831145f7d67ed1cda310d89bf220c25641` |
| `examples/heating_climate.yaml.example` | 2805 | `1dc3b1b327510721104a083904450a803769ed87` | `fd36f302c19ea173954f10d8f2e334e9bc13029d84bdf11ac45815a05f22a4ad` |
| `frontend/heating-panel.js` | 196899 | `603ecf770d85a20070fcaff84faf4d20269fd936` | `b9de8259d5448df4c124ccd7bc088fe6dc0da8cb880006054d645f8209baaad9` |
| `hacs.json` | 66 | `c01e395778c2e0c68553bf8356d4c575fd09c5bc` | `df7bf66db85e01fbcbb9345630b555780ea317ba23cfe564bca4931c6a896198` |
| `package.json` | 98 | `8b0b01dbe48c5ef917342e31102e28fa20ecd4af` | `e0ca96945969ab5ec6b2d9fc41ea0bf9d1521a885b24b7ef2f16332395455596` |
| `tests/audit_case.json` | 2547 | `8e1b56e299478671cdc3a52a3830512b6ded6efc` | `4840238510baa228d3eb840e0ce704fa43dfb194708a80ba1bff2a3b00c1664d` |
| `tests/browser-fixture.html` | 14225 | `949a5b064faa3c3d8ba7ea9fba8ba2ef23ab329a` | `f64df360740c56aea1d285129c3a38831763901f1b08688bebb359770096c871` |
| `tests/environment_live_case.json` | 3933 | `eb18e3604584941d49fe6e9c6bad3ac0b0abd7fe` | `a26a504aa708e04617c2536a1cc695070ba7de1ccc8e40e7a4c60689b7bf02ca` |
| `tests/frontend.test.mjs` | 33175 | `e29a624afee9fcd7ae5a6c30f36c38e193a73d0c` | `e7c754d33be2be769328f2bd59e3da4516e89b814f4979f44514adecc0b3c519` |
| `tests/insufficient_morning_case.json` | 2315 | `b9481e088602f81c0cdf04e827c81897090cd6fc` | `35aa027586b6f18bee43f6295ad732c190e0abea5169400e981ce7169598a2da` |
| `tests/live_case.json` | 2495 | `f52472d162a389973205687cb485034bb6e502a7` | `ad93584fd6e2dc9d26fb9b4098307e2379d6711919949c1c0277152c75a61b68` |
| `tests/requirements.txt` | 50 | `35552fbebf85a75abca4e250529baf09d0e948f4` | `37e2c22ebfacf369982891c8963f2c1e3d591c70bf149b59ec8d700162654381` |
| `tests/test_adapter_modulation.py` | 3735 | `8de2d8e15a0253bcbdc15f3feba1df133051a3c4` | `16ab268db4cda6e6b5a078aabbf4edc144e89f2ddde2b7b3e99d5002718702e8` |
| `tests/test_ai_summary.py` | 7328 | `299c105ff88bd52e15225b185b425ad92e9d3577` | `8b4eb215a94fd173d7fbb60f1eb9e9851a6f99200a80b8e5087999b800a0420e` |
| `tests/test_archive_capacity.py` | 3926 | `e8acb86decd8eb326079765497dca5f3cda25d16` | `2523fc141252dd7c1130050dbcc7ec3ebefe92b4913a867ec85f43bdf112e7c6` |
| `tests/test_audit_20261027.py` | 20196 | `ea2a9e61a9c0fc1d4aaafd573a0e9bd8c3417cd5` | `5062f93192272b28ec9c4528c57fba8c6da45f59258ddd062d173737351d71be` |
| `tests/test_audited_grid_presence.py` | 2443 | `22682a30adecdd657f57d53475fcd8a03513a29d` | `c7bdf3333de85164c0759b8f1aa6f0125f84ec1581b29d82206f39c581ebde28` |
| `tests/test_background_control.py` | 8868 | `90c7bd8489394009f2f84c78938c985bc57f28ab` | `de1ccb4cb13f2a98c3f1ee648859c450f795677e1d04c55e666e5c7564450cd8` |
| `tests/test_circulation.py` | 13100 | `70bc388a557e5d5c46d79f686a376d02e692d529` | `8ad60ccd352b6ea8a3efc7bb42867140befdd4e1622c4ab1ec09c93b59a173a5` |
| `tests/test_daynight.py` | 5159 | `f5b5b58a3e3d720f85c17ea2d510cde438d5c4c0` | `8fba319bf8244444b526b54eafe540713b832234b694bf810627d324bd6771b4` |
| `tests/test_decision_history.py` | 18754 | `0068eec1cf6d864d3c1c3f4ac72295d9c004d33b` | `4b71fd8a1a855aa27c004f99410c4131c786e0ce11b54cfaf9f597cd97f212fa` |
| `tests/test_dual_power_accounting.py` | 6575 | `c5de537c32aa3a1656e61925a005c1c913cf75bb` | `6d2b1104a5a943ad634cccdf661bc82f3ae2b124c8d8b0cd948ab42a5b0b85f4` |
| `tests/test_energy_reconciliation.py` | 4296 | `27a3def9289f8acb6f8e0c5918ac556b324083e1` | `a44929243969c269cd9c53523db0050d7a5dd703832b32a74053be7d525b7f0f` |
| `tests/test_environment.py` | 7293 | `e138a181dce9bbbe6cc7b6f720b1f6443bf4930e` | `7a6a7b90f4bed9dd698acfd986cccb2c8b9858ed86aae85bd9fc3767322225ac` |
| `tests/test_fallback_recovery.py` | 10660 | `f3a2ca8861b893b6dd1d2d26f2a14d9c51cc6e0b` | `5ab60b3d5bd58b35399af6a5e615e76b4b52c0a89f50226333ece7083f3dbfc8` |
| `tests/test_fireplace_circulation.py` | 5427 | `5dbd7abcc546bd69b7ba5915bfcb25683148887e` | `88061b95fde9dcf77dd65d8908059993c70030a8bc7a3295677cccbba7386c0f` |
| `tests/test_forecast24.py` | 2261 | `9829de6622ec73a906418bfb16947b45a5012cf6` | `caa66f94cefd16c4007d24b8f6bf6492eda2f0510193ee61d9c7073fda12ccb8` |
| `tests/test_hacs_workflow.py` | 9879 | `bd75b7d30bfefd58d9bcc346e7f763ab92a32a56` | `89c3727d2fb7e75e25f082231a11801885ab8aa8935bac0630211f2aa3eee7e8` |
| `tests/test_heating_model.py` | 2459 | `cc9f49ec39ed8f4aba760a14d6570933986d1889` | `10d9967a0674f3a02a5ba4e554d2e6047ffb61f770d3ce51daf50bd592b4e098` |
| `tests/test_heating_outages.py` | 4475 | `490661c574a1f52a9ab6d9aaccec74e30453d510` | `df052c4a17936c2abcb1d72fbf08309c548c9cee65f44dcd86316ba87bc76a7f` |
| `tests/test_history_async_dispatch.py` | 2458 | `c31487a61254ded258610762bf62e2ecfa52295f` | `d2f9dab2ad7d969ab4e05a6eca0cc44ed5aec96254df0b0f58be22580079cc9b` |
| `tests/test_incident_20261029.py` | 8998 | `87df2e0cd353bf801d63b3dfd562e1d91bc6ffd1` | `ff747431ca70d9f3b3b2f9a9d92363ff030716c1ba02169c8c67179742b36b58` |
| `tests/test_inlet_accounting.py` | 15593 | `2aaa1f75337fc6320ccf13b184611814aabdf8d5` | `d158a271d1e984ec7f560bce09ac81ca6404a427dcca0d95b59d83c2bd942d93` |
| `tests/test_input_recovery.py` | 5691 | `8655327232c770859d242a7080d3c967161b5805` | `dc7ff7f0f1f547debb6206a499d71dce77c9cbbf88c2d9adf7cc2f7e5ca39628` |
| `tests/test_learning_limits.py` | 15143 | `18d8ca5ba7e177e68ee02cfe1ff05f0fde874dec` | `cd314de67ee4a68fd0075e0e4208ad65756a4a51dfe9abb5532be6b9ec6295d1` |
| `tests/test_long_forecast_fix.py` | 9279 | `7cc5ff3e97b38e92b2e3a4e1b95199f16cb80699` | `54b46ee17a61e02c0a7351e0e50b047c31a479ab8a43b473f68642bc62b9fe3a` |
| `tests/test_migration.py` | 3295 | `8a1f0451f933e01156a9eeeef2a6c80317ed54ff` | `819439599174152299abe75902119692cb5c556eb353d0e1a788d95494de009c` |
| `tests/test_modulation.py` | 7882 | `f51f0cd574f1af48cc20e9ad90014f84891c6c18` | `b67ad589a1b3c4f8bfae7b62b8a8c8aacca5adca56e550e57764e481ca76a8f3` |
| `tests/test_morning_comfort.py` | 2862 | `e9179be039d17bf3017cbe52fd45d2d48446eaba` | `d537f665d801853ead2445cecd8379af3bbd98f676ab3668a516b8ce7a90b4d7` |
| `tests/test_morning_min30.py` | 2691 | `3fd70fe369141806698c0297a389dff71a553b12` | `77610887c5f51a2e5c9859dcc438102732d877b690659b97c9ffbc6bc99db934` |
| `tests/test_morning_priority.py` | 4531 | `d31888977025f0fc93a74de15a130f3ce82f6645` | `2c534ec9f029f23dbc3fb239041a07b726f5a91091bd631ddf777eebc2c7a9b4` |
| `tests/test_morning_reserve.py` | 7771 | `42d2ce111c35bb57ebc31703d0be128afa29b81f` | `1cb73b3725ef0a4192bdb28f06fe1ec9f361c54eb6b69c287ebb223ea32116cb` |
| `tests/test_outage_forecast_continuity.py` | 3610 | `aeeef2f5c26ea2da43ed5a00e5015814ed17215e` | `f96307543bca610beba4c05b18aea4e2dfd077474d388dbed07f5d981e2ac3c0` |
| `tests/test_outage_modes.py` | 7375 | `b92233c4a1daa3916f4a7cbc469a95b44c67a597` | `4fe44846de14fb745c75e9d2e54a9d5482f8d8d5bcec176471f9dcf73aab2242` |
| `tests/test_partial_power_reserve.py` | 7946 | `b2136518709ce8ddf5255f96d8cfe71eae8cac3d` | `62ea64de2ecc0ae1728e44a5bf404b485d14e542f796f146d958f001c414047b` |
| `tests/test_plan_accountability.py` | 8459 | `4fd73dd3861106d1b45e2aed6cb954a4b975677d` | `cfb4008f0d238c126754572926706b003277b8658711bcf07654822a09999094` |
| `tests/test_planned_execution.py` | 8331 | `1b076329f8e24e74cdefde006a49b7c2eb38650b` | `89fe6af01d8f967f5a05f44d22df5da1ba1d50156503fe52bfc27b4ff195bd51` |
| `tests/test_power_provenance.py` | 3304 | `6303451c5d1eb5c44ffd43b8c9285849984ca4ec` | `d4aaa257c243eced7ce0e34515158731b60580c78fa41dfacda28614ab2b4ba4` |
| `tests/test_power_ventilation.py` | 22050 | `8265450eb7332aed8fe852aca349f65a89de9a2d` | `fdc2a18e7f16a7b917eb6f1860aab9be81d389f73d9592e4c54da95febc25595` |
| `tests/test_qa_energy_quality.py` | 6912 | `000ceb7675f29b4fb9fd60f012d1f9da6551ccf0` | `9a7c8a4dd3097b9f608413f2b27bc71f5c1af88f07fb6df83b0224e4b80becff` |
| `tests/test_qa_history_transport.py` | 4736 | `136bf934cfc9ad64fec6a298d6521b8728a4b378` | `111e246f14228e7845a0b702e0176951f2da9db49557cf95435cb56f1936c948` |
| `tests/test_qa_outage_safety.py` | 1125 | `02d5e283cdd4843388a1c377f74a316efca2141f` | `3409800933d674205d24a7e040b273d3e1c84aca6a7a45288f34c83f3fff0232` |
| `tests/test_qa_properties.py` | 5038 | `4e880587697d8a5b6b2db843468c8d118bdd00ec` | `a18e347ca0168f1ffdde9e3a0d0f71b36d1ea616144776f2448e0274880bc67c` |
| `tests/test_qa_truthfulness.py` | 16355 | `abc5eb8d42a75d1f5368f2553dafdc24a2699c8d` | `28319507ab90b54fa18ad624dc2deef8bffaaba3fb9a16a77bf09aad87201c8f` |
| `tests/test_stability.py` | 4136 | `eb74b62e6600462be6f341397de3a220949cf828` | `e7b1fa9cf7fb9c2a3823881f6f5b48636fc16b94050fbda218c7e4d9263e832b` |
| `tests/test_sufficiency_search.py` | 12426 | `598c8d4f8f11d4516b58a98e07b0ade5d37587c7` | `66e8029f75803ee24ef3635f60a9667c6d6f0daf5fc85e4a76c28c55a73f9e30` |
| `tests/test_system_settings.py` | 7844 | `b21feb0c87224d0b917efe692ebdbe26b749366b` | `bed7cb6580bfccd78ce9c52e2d6371bc173bc550de84f01c294adcb0a5a6e890` |
| `tests/test_temperature_comparison.py` | 7700 | `02f9ab4b849ad89a7b46ba0f28f883f23568da6a` | `60e215469436596fa591777d93205c807586db6fc466260fc7f7f70be0d27919` |
| `tests/test_ui.py` | 3619 | `913d0126834371003f22be8cff3b7dcba1316786` | `d2997fb2956c00ccf320636a693433540916da0f3b547ef74b4faa9255e82262` |
| `tests/test_update_guards.py` | 2305 | `a2ab25910ce781d2469c95bde8c51da167425504` | `511a8866c5a2ccaa0eb8f3d0d3412f86e5fb4ad0d0cf5b3e27ed6bd2652379c1` |
| `tests/test_validation_matrix.py` | 3785 | `d9169b07010927b80388dc0ff38334e6888d51fa` | `fd1b7c75918701e4568774ace7aefa9c1331fc2ad623cac2d65ab4200a50e5ba` |
| `tests/test_watchdog_safety.py` | 3468 | `57a0c8f3d36dc9349a7cebec5e09ae77735cca8e` | `78cb05853fdb542a5ac48ef67566e4ad4cc4a9f0615854a1d4abe2e73eea75ce` |
| `tests/test_weather_coverage.py` | 2329 | `d19306cb5b2959ff7a8e09a8d66f08cf3e96af25` | `b2a9a7ae5210d801c7da6d04421818834bb60da868729a7b613238f4eb30becb` |
| `tools/build_ui.py` | 2476 | `995b89a258f73b304bbabdd4f9e852fb31263790` | `e5977d6033550a5c857f467f9df3b3e5e661f8a4fc4de41c8819e18c9a610e46` |
| `tools/check_power_ventilation.py` | 7384 | `9144b4153bbf3e772da76b605cd2103a8164760b` | `09211e76838d3bef770c7e34fea52cf81b1a24885027c6fcc0a6249ed0ea7000` |
| `tools/check_ui_accessibility.py` | 4651 | `91d5c7fd8f1ceb4f0f65ed3350f367e62aad0b32` | `cfee2d35ca9a2333e69d339a355a7336f810cc9676750cc650c4081eaa7f376f` |
| `tools/check_ui_browser.py` | 66759 | `ff5381a1b10b1f55e22bd866208da18ab79525ff` | `6bfa5753254990557445cec11ef2a387b9f9250ae93cb541aaa7d20fb2ff804c` |
| `tools/check_validation.py` | 2900 | `8e3e5e1a7d74773a6673e81a8c8ee19899295e1d` | `8bd7aab5a8182b15a151604df3dfbbe578ad1bcbd36783f22fa9fcab7b6d7f26` |
| `tools/hacs_workflow.py` | 8891 | `fa4ec0d6b1568ed6ebba8eb8fe3309a9098ee9c4` | `011a988f5a4007c2a4890d2627cd3e55c8204412fb9af5ce150be010ba1f5115` |
| `tools/migrate_hacs.py` | 7078 | `2de5037694f2122ba8951dfa66265cfb5c11d65d` | `06e56a961856111679545f4541abbf6922eea8dab177f58b65eeda85a009bf12` |
| `tools/replay_decision.py` | 1502 | `4bf8885ac0c260545fa1fc256e41cc6500b4bddf` | `e509e9459d259efb0176044d1b73814dcfa2f09553483ba1081082b1e499ff61` |
