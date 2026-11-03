# Heating AI 2.0 — міграція та приймання

**Статус:** майбутній runbook. Жоден крок встановлення/перемикання зараз не виконувати. Погодження цього документа не означає, що tests/physical commissioning уже пройдені. У кожного gate є результат pass/fail/blocked та evidence; перехід при fail заборонений.

## Обсяг, відповідальність і незмінні речі

Codex готує реалізацію/стенд/звіт, власник погоджує архітектуру та окреме конкретне перемикання. Фізичну топологію й OEM safety підтверджує власник або компетентний спеціаліст. Імпорт має зберегти model coefficients/версії, energy origin/totals, historical evidence, comfort/day/night/window settings, manual pause, armed semantics, fan speeds/permissions і pending one-shots із їхньою справжньою семантикою.

Не змінювати Zigbee2MQTT, загальний grid detection/Telegram alerts, Sky Radar, Deye, Svitlo integration, Tuya таймери, автоматику рекуператора/витяжок. Перенесення heating-specific watchdog/weather/night circulation є явно визначеною частиною майбутньої міграції й виконується тільки в cutover. Основна домашня панель не редагується: новий UI на окремому маршруті.

## Етапи та gates

| Етап | Дії | Критерій переходу |
|---|---|---|
| G0 — погодження | Обговорити ADR01–07, режими fallback, limits, design concept | Явне погодження архітектури; до цього тільки документи |
| G1 — read-only baseline | Актуальний export app YAML, runtime settings/state/telemetry/archive, helpers/automations/UI resources, counters і автори команд | Повна карта bindings, checksums і закриті прогалини документа 01 |
| G2 — backup/restore rehearsal | Private backup з кодом/даними/config, перевірка hashes; відновлення лише на ізольованому стенді | Повний restore на стенді, continuity totals/model/receipts; не просто «архів створений» |
| G3 — реалізація/стенд | P0/P1 suites, fault injection, real SQLite/processes, UI matrix | Усі обов'язкові automated checks pass, конкретний commit/version |
| G4 — import dry-run | Читання legacy, schema conversion у нову директорію; жодного overwrite | Idempotent rerun; total parity≤10⁻⁶ кВт·год; frozen checksum match; report exceptions=0 або погоджені mapping |
| G5 — shadow | Новий компонент без права commands; старий залишається sole active writer | ≥7 діб і ≥3 повних heating cycles, write count=0, no safety violations, measured SLO/coverage |
| G6 — physical commissioning | Погоджене вікно: перевірити схему, mode, OEM fallback/відключення, ON/OFF та power response | Practical checklist pass; shadow відхилення пояснені; rollback готовий |
| G7 — cutover | Нижче наведена атомарна процедура ownership transfer | Один активний automatic writer, fresh state/commands/receipt |
| G8 — probation | Перші 24 год + 3 цикли з доступним ручним поверненням | Немає P0/P1 runtime defects; real actual/desired/plan узгоджені |
| G9 — quality acceptance | ≥10 кваліфікованих циклів і ≥7 незалежних днів для потрібного горизонту | Energy/temperature/overshoot gates документа 04 або чесний статус «не доведено» |

Час сам по собі не завершує G5/G9: якщо немає нагріву, якісних вимірів, потрібної погоди чи повних forecast horizons, gate залишається pending. Не обіцяти 48 годин до «навчено». За відсутнього морозного regime його coverage лишається неперевіреним і керування консервативним.

## Перед cutover — конкретний checklist

1. Зафіксувати baseline timestamp, current thermostat actual/target/mode, room/return/outside, physical power profile, actual power і coverage, mode/armed/fan, pending one-shot, energy total/day/month/year, model/config/topology versions.
2. Переконатися, що немає in-progress HACS update, journal=idle. Заморозити **оновлення лише heating** на час transfer; не зупиняти загальний AppDaemon, Sky Radar чи HA.
3. Мати restore-tested backup й offline копію rollback procedure; новий runtime ще SHADOW, hard-disabled gateway.
4. Перевірити current HA version і сумісність integration/compute/front API. Нову integration спочатку завантажити без device authority, не вимагати HA restart у самому transfer. Якщо початкове встановлення таки потребує restart, винести його в окремо погоджене підготовче вікно.
5. Власник бачить concrete cutover report: що зміниться, які heating-specific writers вимкнуться, які показники й невизначеності збережуться, як повернути назад.

## Cutover без двох виконавців

1. Новий gateway лишається SHADOW. Зупинити тільки legacy heating command authority: armed/fan-control pause й відключення саме старого heating app через підтримуваний app-level lifecycle; не весь AppDaemon. Збережені попередні mode/armed/fan settings не втратити.
2. Вимкнути legacy прямий watchdog writer і direct fan branch нічної automation, замінити погодженими intent routes. Погодний cache або зберігається як read-only adapter, або переходить у compute adapter; не повинно лишитися двох sources, які удавано подвоюють свіжість прогнозу.
3. Дочекатися завершення/cancel усіх старих thermostat/fan command callbacks. Перечитати actual state й лог service calls; не покладатися тільки на armed=off. Якщо неможливо довести quiescence — cutover blocked.
4. Зробити фінальний ledger delta import від baseline seq до freeze seq. Legacy дані — read-only; новий DB має migration_id, source hashes, import offset. Якщо після freeze були нові дані — зафіксувати gap, не вдавати повний import.
5. Імпортовані utility_meter consumers не перемикати через reset/recreate. Compatibility publisher спочатку видає той самий canonical total, без приросту. Перевірити перший нульовий delta; далі відповідність усіх downstream counters.
6. Новий gateway отримує новий owner_epoch тільки після fresh snapshot, DB integrity й усіх permits. Перенести бажаний режим/armed/manual pause; імпорт не має автоматично озброювати систему, яка була призупинена власником.
7. Обрати safe initial desired state, reconcile, і лише потім почати виконання валідного near-term plan. Не replay старого pending HEAT. One-shot з unknown_outcome не запускати вдруге.
8. Прочитати actual thermostat echo, незалежну power evidence, fan actual state, next session, heartbeat/deadlines, model/config/energy totals і settings receipt. Успішний service call без фізичного доказу позначити partial, не завершеним G7.

Перенесення legacy entity IDs потребує підтримуваного registry/API ownership mapping, а не видалення/перестворення. Динамічні AppDaemon states можуть бути без registry unique_id: докладно перевірити це в G1 і видати compatibility table. Старий і новий publisher не можуть одночасно писати canonical IDs. Якщо reuse ID неможливий без ризику statistics continuity, зберегти старі IDs як compatibility entities й переприв'язати consumer через підтримуваний API у погодженому кроці. Не редагувати `.storage` або Recorder DB напряму.

## Тригери rollback

- Непідтверджений safety stop; unexpected automatic HEAT; manual ownership порушено.
- Два автоматичні writers/суперечливі commands; command stale/duplicate поза контрактом.
- Втрачена continuity counters/історії, зниження total, corruption, phantom recovered energy.
- Control lag max>1 с для safety event при responsive HA у кваліфікованому тесті; repeated kernel/runtime faults.
- Persisted settings receipt бреше, power unknown показано як 0, frozen forecast переписаний.

При погодженому G7 ці умови дають дозвіл на підготовлений scoped rollback у межах цього перемикання; не використовувати їх як дозвіл на інші непогоджені зміни HA. Погіршення лише точності forecast зберігає evidence й переводить у консервативний fallback до рішення, якщо це безпечніше за миттєве повернення.

## Процедура rollback

1. Новий gateway припиняє нові HEAT, надсилає доступний safe stop, фіксує failed/unknown outcome. Зняти нову authority, disarm новий автоматичний writer.
2. Експортувати **лише нові** energy/command/settings/one-shot events після migration freeze seq. Старий backup даних не відновлювати поверх нових вимірів.
3. Повернути перевірений legacy code commit і config у heating app, не весь AppDaemon/HA. Якщо app-level reload неможливий — зупинити процедуру й погодити конкретний необхідний lifecycle impact.
4. Legacy importer bridge приймає нові ledger deltas і consumed one-shots ідемпотентно. Якщо формат несумісний, залишити контроль у native qualified fallback до repair; не запускати legacy з меншими totals або повторним one-shot.
5. Повернути scoped watchdog/night routes тільки після зняття нового gateway. Відновити попередній бажаний manual/mode/armed/fan state, звірити actual device й свіжий цикл. Хибно вважати armed on до transfer автоматичним дозволом, якщо власник змінив його під час cutover.
6. Зберегти обидва code/data snapshots і incident report; не видаляти нову історію, не редагувати original forecast/counters для косметики.

Мета commissioning rollback time ≤5 хв після виявлення проблеми за наявного HA/зв'язку, але це треба виміряти rehearsal. Без успішного bridge rehearsal G7 blocked. Для незалежного compute App update control fallback продовжує працювати; mismatch major protocol не надсилає heat proposal.

## Приймання власником

| Gate | Конкретний доказ |
|---|---|
| Безпека | Усі S01–S15; physically verified stop/restore у погодженому тесті |
| Функціональна повнота | Кожен рядок feature register має перенесений ID і pass; нічого не «забули» в UI |
| Достовірність | Null/quality/coverage; 12h immutable; energy baseline/actual одним scope |
| Стійкість | Kill/restart/disk/CPU/Internet scenarios; один gateway; bounded fallback/recovery |
| UI | Затверджений SVG напрям, browser/phone checks, практичні задачі ≤10 с |
| Міграція | Totals/model/config/forecast hashes до/після, idempotent rerun, rollback evidence |
| Якість прогнозу | Фактичні 12/24h prospective metrics по режимах/днях; не short MAE як заміна |

У фінальному acceptance report окремі стани: software accepted, physical control accepted, forecast quality accepted by horizon, energy metrology limited. Один загальний «все працює» не приховує невиконану довгу перевірку. Архітектурне погодження зараз дозволяє наступну фазу підготовки коду, але не саме введення у керування.
