# Codex — WP0: read-only baseline, dependency audit and release blockers

**Проєкт:** Heating AI 2.0  
**Цільовий репозиторій:** `dragonidf/ha-heating-2`  
**Вихідний код для аудиту:** `dragonidf/ha-heating-ai`, commit `db7d7ce9c53e4e88c1c27ee10e1f53d6cce10426` (0.3.20).  
**Статус:** архітектура ADR01–07 погоджена 03.11.2026 з чотирма уточненнями з `APPROVAL-2026-11-03.md`. Це дозволяє WP0 та ізольовану розробку в GitHub, **не** зміни у production.

## Роль і завдання

Дій як Principal HA Architect, Reliability Engineer, QA Lead та Security-conscious Migration Engineer. Виконай **лише WP0**, тобто прочитай і верифікуй фактичну основу міграції Heating AI 2.0; виявляй відсутні докази й блокери до реалізації. Нове ядро, інтеграцію, compute app, UI, release або rollout на цьому етапі **не** створюй. Не обіцяй завершити WP1 у межах WP0.

## Джерела в порядку пріоритету

1. `docs/spec/heating-ai-2.0/HANDOFF.md` та `APPROVAL-2026-11-03.md`.
2. Усі **оригінальні** файли пакета Work у `docs/spec/heating-ai-2.0/`: `00-READ-FIRST.md`, `01-...06-...md`, `requirements.csv`, `test-scenarios.csv`, `validation-summary.md`, `manifest.sha256`, `ui-concept.svg/png`.
3. Публічний вихідний GitHub commit **зафіксованого SHA**, включно з `apps/heating_ai/`, `frontend/`, `tests/`, `docs/`, workflows, AGENTS, релізними маніфестами та існуючими регресіями. Не підміняй його рухомою гілкою `main`.
4. Home Assistant — лише живе **читання**, якщо доступний окремий read-only підключений інструмент. Дані GitHub та інші чати не є доказом поточного фізичного стану.

## Жорсткі обмеження

- **Production недоторканний.** Жодних HA service calls на керування, змін helper/automation/dashboard/integration, прав, файлових налаштувань, AppDaemon/HACS, log-level, рестартів, оновлень, backup-creation на production, тестів фізичного ON/OFF або зміни живих каталогів/БД. Якщо для отримання інформації треба розширити доступ, включити File editor чи створити backup на HA — не роби цього; зафіксуй `BLOCKED/NEEDS OWNER APPROVAL` із мінімально необхідним запитом.
- Не записуй в старий репозиторій `dragonidf/ha-heating-ai`; не вимикай чинний контролер та watchdog. Не запускай новий контролер як другий active writer. Тіньовий runtime та код — не в WP0.
- GitHub зміни — лише в `dragonidf/ha-heating-2` у новій гілці `audit/wp0-readonly`, PR без merge в `main` без явного погодження. Якщо Codex не має права push, підготуй лише локальні файли й diff/patch.
- `ha-heating-2` зараз public: **не коміть** credentials, tokens, локальні адреси/координати, приватні state.json, журнали, повні exports Home Assistant, Recorder DB, metadata фізичних локацій або сирі виміри. Приватні необхідні артефакти залишай у контрольованому локальному сховищі власника; в PR тільки sanitized summary з hashes і статусами. Не виводь секрети в prompt/output/log.
- Не вважай `unknown`, `unavailable`, stale або відсутній вимір нулем. Не об'єднуй aliases одного фізичного лічильника як незалежні вимірювання. Не змінюй source of truth.
- Не «закривай» прогалини припущеннями; зміни вимог/захистів — через явно описаний ADR, не приховано.

## Завдання WP0 по порядку

### WP0.1 — цілісність входів

Перевір архів Work за `manifest.sha256`; переліч усі файли та SHA; підтвердь commit baseline, атрибути останньої версії і чинну назву репозиторію. Якщо є розходження GitHub runtime vs pinned source, зафіксуй дати й не перезаписуй вихідні файли. Перевір, що чотири погоджені уточнення включено в acceptance matrix, а 86 вимог і 38 сценаріїв мають стабільні ID та стан `not implemented/planned`.

### WP0.2 — read-only аудит джерел і залежностей

Склади табличне зіставлення: physical purpose → HA entity_id/attribute → unit → physical_id/alias → origin/source/time freshness → quality/confidence → owner/consumer → fallback. Покрий кімнату, обратку, вулицю, `climate.kotel`, котел 3/6/9/AUTO, фазові лічильники/local + вхідний 220, Deye GRID, Svitlo 3.1, енергію, камін, циркуляцію, рекуператор/витяжки, погоду й одноразові intents. Звір актуальні наявні дані з таблицею в `01-Audit-and-feature-register.md`. Кожна непідтверджена схема фаз/підключення — **blocker**, не inferred wiring.

### WP0.3 — всі автори команд і межі безпеки

Знайди в коді, інтеграціях, автоматизаціях, допоміжних сценаріях та UI усі можливі `climate.*` і `fan.*` writers. Окремо опиши AppDaemon HeatingClimate, `heating_watchdog_v1`, нічну циркуляцію, HACS update coordinator, зовнішні ручні/Tuya writers (або unknown). Побудуй command/owner graph та список потрібних в майбутньому fencing/intent replacements. Не змінюй їх зараз. Зафіксуй поточну семантику modes/armed/manual pause/one-shot та факт, що OEM захисти котла не підтверджені фізично.

### WP0.4 — поточна модель, історія й лічильники

Переліч усі persistence assets та їх origin/format/version, critical state, model coefficients, candidate/rollback, immutable 12h forecasts, decision/command receipts, energy origin/totals/unknown windows і archive retention. Перевір доступність read-only й доступний спосіб контрольного експорту. Жодних копій приватного payload у публічному PR. Склади майбутній **dry-run** import plan і parity tests, але не імпортуй жодних даних, навіть у production directory. Якщо локальний `app YAML`, приватні logs/state/backup недоступні — познач `BLOCKED` із конкретним способом легального отримання.

### WP0.5 — сумісність, ресурсні ризики і вимірювані межі

За доступними даними визнач HA Core/Supervisor, Python API/runtime, AppDaemon/HACS, SQLite linked runtime, storage filesystem, SQLite WAL compatibility, штатні API інтеграції, auth, protocol/version boundaries, незалежність обчислень. Оціни, що вимагатиме restart при **майбутньому** первинному встановленні, але **не** виконуй його. Не роби benchmark на production; допустимо виконувати офлайн-тести на перевірених fixture в Codex sandbox. Визнач SLO й їх метод вимірювання (kernel, gateway, planner timeout, storage, UI) без фальшивих `pass`.

### WP0.6 — приватність, розбіжності, готовність до наступного етапу

Звір `requirements.csv` з кодом і документами, знайди дублікати, конфлікти й функції без критеріїв або тестів; не переписуй істинність старих регресій. Всі P0/P1 повинні мати trace `source → requirement → test → proposed module`, інакше познач missing. Усі невідомі — конкретні запити на owner evidence, без вигадування. Окремо підтвердь, що repo public та що жоден приватний ресурс не планується туди комітити.

## Обов'язкові вихідні файли (нові, в PR)

- `docs/wp0/00-source-and-integrity.md` — файлова інвентаризація й checksums; source SHA; зафіксовані версії та дати.
- `docs/wp0/01-bindings-topology.csv` — entity/physical map, units/quality/freshness, verified/assumed/blocked.
- `docs/wp0/02-command-owners.md` — всі thermostat/fan command writers, manual/outside ownership, cutover risks.
- `docs/wp0/03-storage-and-energy.md` — модель, immutable archives, total/unknown handling, приватні evidence references без payload.
- `docs/wp0/04-runtime-compatibility.md` — HA/Python/SQLite/FS/API, compatibility and limitations.
- `docs/wp0/05-requirements-traceability.csv` — all P0/P1 IDs, feature, old implementation location, planned 2.0 module, test, gap.
- `docs/wp0/06-open-questions-and-blockers.md` — пріоритети, owner actions, blocking evidence, recommendations.
- `docs/wp0/07-gate-G1-readiness.md` — PASS / FAIL / BLOCKED per gate з точними доказами, без здогадок.
- `docs/wp0/08-privacy-and-diff-report.md` — незмінність production та старого GitHub, список **лише** нових файлів у PR, перевірка secrets.

Зроби короткий executive summary: підтверджені факти, що саме блокує WP1/G1, які незалежні рішення можна почати без доступу до приватної інформації, що саме потрібно від власника, і список наступних безпечних робіт.

## Критерії готовності WP0

1. Усі файли в пакеті прочитані й checksums збігаються; зафіксований reference SHA без непомітної зміни.
2. Coverage всіх 86 requirements/38 scenarios перевірене; чотири уточнення власника відображені явно в trace.
3. Карта авторів команд і реальних входів, ризиків topology/quality сформована; кожен непідтверджений зв'язок має статус `BLOCKED`, не «факт».
4. Жодного production write, керування, deployment, HA restart або зміни старого репозиторію; аудит дій підтверджує read-only.
5. Жодного приватного payload у публічному GitHub; PR тільки документація й sanitized findings.
6. Готовий PR/patch із переліченими артефактами та gate report. **Не переходь автоматично до WP1** і не заявляй повну готовність G1, якщо блокери залишилися.

## Формат фінальної відповіді Codex

Повідом: `WP0: PASS / BLOCKED / FAIL`, source commit і git ref нового PR, список отриманих/недоступних доказів, кількість і пріоритет блокерів, результати перевірки privacy, точні посилання на створені файли, підтвердження нульових production writes та одну рекомендацію щодо WP1. Не запускати жодних physical tests, установки чи змін HA.
