# Heating AI 2.0 — повне технічне завдання для Codex

**Версія:** 1.0 від 03.11.2026. **Виконання зараз заборонене:** цей пакет є проєктом для погодження. Після погодження архітектури створити окремий branch/PR; до окремого погодженого rollout production залишається без змін. Не переносити весь старий monolith як є під новими назвами.

## Канонічний контракт

Документ 02 задає архітектуру й типи, `requirements.csv` — кожну нормативну вимогу з пріоритетом, джерелом, acceptance і test ID. Документ 04 і `test-scenarios.csv` описують перевірки; документ 06 — rollout gates. Якщо текст і CSV розходяться, зафіксувати conflict в ADR до реалізації, не обирати зручніше послаблення. Усі P0/P1 повинні мати `implemented_by`, `verified_by`, artifact hash і статус pass/fail/blocked в майбутньому release evidence.

Ціль: зберегти функції з документа 01, усунути спільне блокування керування та важких робіт, зробити чесними облік/прогноз/приймання команд, спростити щоденний UI. Не створювати нові сервери Redis/PostgreSQL, інтернет-залежність або автоматичне перемикання фізичних ступенів, якого обладнання не підтверджує.

## Майбутня структура проєкту

| Шлях | Вміст |
|---|---|
| `packages/contracts/` | Typed dataclasses/enums/schema, serializers і units |
| `packages/control/` | Pure safety reducer, ownership, fallback, command policy |
| `packages/thermal/` | Baseline model, observer, power calibration, bounded learning |
| `custom_components/heating_ai/` | HA config/options flow, sensors, services/intents, gateway, authenticated WS |
| `compute_app/` | Локальний App, planner subprocess supervisor, evidence DB/history API |
| `frontend/` | Окремі presentation components, chart adapter, design tokens |
| `tests/unit/`, `tests/contracts/` | Pure/serialization/invariant tests |
| `tests/integration/`, `tests/replay/`, `tests/faults/` | Реальний event order, локальні сховища, fault injection |
| `tests/e2e/`, `tests/fixtures/` | Browser, sanitized versioned fixtures, provenance |
| `tools/migration/` | Read-only inspect/dry-run/import/rollback reports |
| `docs/adr/`, `docs/runbooks/` | Рішення, контракт оператора, відновлення |

Python 3.12/3.13 сумісні pure modules; версію HA runtime перевірити перед складанням integration. Не фіксувати неперевірену майбутню версію HA. Frontend зберігає HA authentication/theming, без CDN; конкретний bundler обирається після перевірки мінімального build. Основна логіка з typed inputs і явними errors, без bare except, magic globals, mutable shared dict. Приклад контракту, не реалізація:

```python
@dataclass(frozen=True)
class HeatPermit:
    allowed: bool
    reason: str
    snapshot_id: str
    owner_epoch: int
    expires_at: float
```

Планові verification entrypoints створюються разом із першою реалізацією: `make check`, `make test-unit`, `make test-contracts`, `make test-faults`, `make test-replay`, `make test-browser`, `make benchmark`, `make migration-dry-run FIXTURE=<private-path>`. Зараз ці нові команди не існують і не виконані. Чинні старі `make check test` залишаються regression baseline, поки відповідні поведінкові контракти не перенесені.

## Дані, якість і фізична схема (D01–D10)

1. Mapping конфігурується entity selectors через HA flow; локальні aliases одного physical_id використовуються альтернативно. Перед активацією кожен required binding має unit/capability validation. Missing sensor не створюється з припущеним ID.
2. Свіжість температури визначається temperature reading report. Humidity/device availability можуть підтверджувати зв'язок, але не нову температуру. Cadence thresholds спочатку імпортуються чинні; зміна максимумів — окреме збережене налаштування з поясненням. Резервний thermostat bias має власну давність/похибку.
3. Snapshot включає фактичні source timestamps й skew. Немає штучної «атомарності» одночасним fetch даних різного віку. У conflict не усереднювати local/cloud одного приладу мовчки; обрати придатне джерело за policy або unknown.
4. Баланс A = ввід − три групи − signed Deye GRID; баланс B = ввід − неперекривні окремі навантаження − signed GRID. Не змішувати groups і їхні loads в одному відніманні. Не додавати Deye LOAD/battery/CT повторно. Значення A/B не незалежні, confidence не множиться від їхньої згоди.
5. Великі негативні residual чи перевищення фізичного діапазону → conflicting, а не clip до 0/9 кВт. Допуск шуму — commissioning setting; у raw evidence зберегти original residual. 9 кВт — nominal, фактичні 9,237 кВт не автоматично invalid; граничну max потужність пов'язати з перевіреним обладнанням/напругою.
6. Ступінь за потужністю фільтрується окремо від енергії: короткий імпульс насоса не стає сеансом ТЕНів. Чистий time integration з known sources не округляє кожний вимір до 3/6/9. При gap left hold максимум 45 с переноситься як явно задокументований метод; довша невідома частина — unknown, не nominal.
7. Weather adapter має provider-issued/received/valid times, actual vs interpolated/extended points. Повторення останньої години не збільшує підтверджений provider horizon. Без Інтернету current outside + bounded scenario дають conditional plan; safety не залежить від погоди з API.
8. Svitlo відрізняє normal/scheduled/unknown/emergency, дату region/queue, payload updated й coverage. `No data`, пусте tomorrow або failure не normal. Фактична мережа окрема; 3.1 не визначається лише friendly_name. Однаковий content hash не переплановується від зміни публікації.
9. Фізичні фази/імпорт signed GRID проходять commissioning. Порожній `power_phase_topology.phases=[]` не вважати перевіреною топологією. Контролер споживає чинний upstream grid contract і не переписує Telegram/Z2M/global grid automations.

## Safety, команди й режими (S01–S15)

Ядро — чиста функція: snapshot + policy + runtime state + event → next state + intents. Зовнішні services, I/O, sleep, planner, AI й disk access у kernel заборонені імпортними тестами. Event-driven safety updates доповнюються 1-секундним deadline tick. Backlog звичайних sensor updates coalesces latest per entity, але переходи safety/manual/grid зберігають event order/sequence.

Керування термостатом: demand ON через heat і поточну **температуру самого термостата** +2 °C, OFF demand через −2 °C; округлення до його step і clamp min/max. Кімнатна comfort target — інший параметр. Якщо actuator current_temperature непридатна, не рахувати offset із старого значення; обрати кваліфікований safe/off mode або SAFE_HOLD. Режим Off не повинен відключати насос/антизамерзання в неперевірений спосіб.

Перевірка команди має рівні: queued → prepared → sent → service_accepted → echoed → physically_observed або unknown/failed. Для ON фізична перевірка — придатна незалежна/розрахункова power evidence з provenance й time window; за неповного виміру не писати «реле ввімкнулось». Для OFF потребуються low measured power/відсутність heat demand з діагностикою остаточного тепла; термостат echo не дорівнює зупинці ТЕНів. Max echo deadline 10 с; physical response deadline початково 120 с, обидва окремі commissioning settings. Повтори не більше двох із reconcile між ними; deadline не продовжувати безмежно.

Manual pause від actual external state change зберігається durable. UI «Продовжити автоматично» — явний intent нового ownership epoch. «Спостереження» hard-disables automatic HEAT; не маскує фактичну сторонню роботу котла. «Штатний auto» має локальні guards/уставку, а не віддає безконтрольний heating demand до наступного запуску planner.

One-shot існує як типізований intent із `kind`, `created_at`, `expires_at`, `armed_grid_epoch`, `consumed_at`, `outcome`. Legacy `restore_once` імпортувати як наявну фактичну дію з R0, не мовчки міняти на «вимкнення». Якщо потрібна дія «вимкнути при наступній подачі», створити окремий kind і явну назву. Безпека/upper/ручний pause мають пріоритет. Після restart consumed intent не повторюється. Невідомий результат показується користувачу.

## Планування, ранок і енергобюджет (P01–P12)

Дискретизація розрахунку — 5 хв; execution зберігає абсолютні segment boundaries і не очікує чергового повного recompute. Для near-term переходів перевіряється реальний UTC час без накопичення похибки від округлення хвилин. Дані для UI можуть бути рідшими, але fine safety trajectory зберігається в evidence. Horizon покриває 24 год як стандарт і резерв до наступного дозволеного/прогнозно доступного тепла плюс response delay, capped 72 год; невідомі погодні частини умовні.

Модель вибирає доступні 3/6/9/AUTO **сценарії**, але не змінює ступінь котла апаратно. Recommendations містять deadline зміни, очікуваний дефіцит і calibration status. Недостатність 9 кВт за чинною моделлю не є безумовним доказом фізичної неможливості, коли сама модель/погода/топологія невизначені.

Ранковий алгоритм:

1. Визначити cycle до конкретної локальної дати 07:00, а не «сьогодні» за годиною запиту. Day/sleep schedules та DST обчислювати ZoneInfo, зіставляти тривалості в UTC.
2. Спершу оцінити потрібну теплову енергію й запас до наступного дозволеного сеансу. Виділити ранкову частку, а решту — економним нічним/вечірнім вікнам.
3. Якщо сеанс потрібний: ≥30 безперервних хв у 05:00–07:00, за відключень дозволене раніше зміщення в межах `outage_advance_limit` (чинне 180 хв) та стратегії. Уже підтверджені хвилини не запускають мінімум заново.
4. 30 хв на 3 кВт = 1,5 кВт·год, на 9 кВт = 4,5 кВт·год лише за повної duty; AUTO вимагає calibrated effective power. Мінімум тривалості не замінює енергетичну достатність.
5. Дефіцит/upper/повний камін/немає живлення/недостатньо часу → явна причина skipped/shortfall, не приховане скасування. Safety може урвати сеанс раніше мінімуму.

Збереження плану: новий forecast не перезаписує immutable initial cycle reference, prestart reference та 12h evidence. Latest estimate зберігається окремо. Решта бюджету = початковий reference − known accounted spend, unknown coverage не скасовує початковий reference. Не віднімати nominal heat demand як фактичну енергію. Коли комфорт потребує більше, план містить changed inputs, projected overrun і reason; немає вигаданої точної causal частки кВт·год.

План може бути retained при малих змінах, але тільки після replay поточного стану. Сигнатура включає settings/model/equipment/topology/grid/outages й істотні weather/thermal updates. Застарілий result не застосовується навіть якщо завершився останнім. Перезапуск worker не скидає команди й не створює duplicate session. Немає знайденого feasible candidate → safe fallback із чітким статусом, а не обіцянка підтримати недосяжну температуру.

## Модель і навчання (M01–M09)

Baseline — поточна двостанна модель room/stored-heat з versioned coefficients та bounded фізичними діапазонами. Не змінювати одиниці коефіцієнтів без converter і replay parity report. Return proxy/observer не називати «температура поверхні підлоги». Коли power unknown, observer має interval uncertainty, а не нульову фактичну енергію. Без trustworthy return під час outage можна продовжити saved cooling observer з видимою давністю, але не вдавати свіжий probe.

Features: outside, confirmed/derived energy, fireplace thermal proxy, ventilation on/off/unknown duty, зовнішній невизначений heat gain. Recup relay не airflow/ККД. Відсутній вітер/сонце не відтворюється точно з назви weather condition. Confidence — доказова якість, а не відсоткова гарантія без калібрування.

Champion/challenger: fit у compute; часовий holdout незалежних днів, без витоку майбутніх вимірів; метрики окремо 1/3/6/12/24/36/48h та режим/сезон/vent/fire/outage. Не рахувати тисячі суміжних 5-хв точок як тисячі незалежних днів. Мінімальні критерії промоції: ≥7 незалежних train днів, ≥3 holdout днів, не гірше champion на 24h MAE більш ніж 0,05 °C, MAE≤0,3 °C на наявних кваліфікованих горизонтах, worst underprediction of peak не погіршується >0,1 °C; фізичні bounds й денні limits з R0 зберігаються до перевіреного нового обґрунтування. Якщо даних не вистачає — кандидат pending, чинний champion працює. Ці пороги — проєктні цілі, не заява про вже доведену точність.

AI не пише commands, model coefficients або trusted config напряму. При дозволеному legacy auto_apply AI-кандидат проходить ту саму schema/bounds/holdout/receipt процедуру; default нової установки AI auto_apply off, імпорт існуючого on зберігається з явним показом семантики. Report може оновитися без thermal recompute. Timeout/невалідний текст AI не змінює план. Rollback повертає попередню model revision, не лічильники/історію.

Зберегти local learning schedule чинного коду: 10:00 та20:45 Europe/Kyiv, durable dedup за локальною датою/слотом, пропущений запуск після restart не виконується багаторазово. Це інший механізм, ніж зовнішні заплановані кліматичні аналізи/звіти. Їхній актуальний prompt/дозволи треба перевірити до міграції, не переписувати автоматично; compatibility summary має лишитися читабельним для наявного звіту. Нові довірені параметри приймаються лише через candidate gate, навіть якщо старий зовнішній аналіз просив auto-apply.

## Енергія й історія прогнозів (E01–E08)

Ledger окремо зберігає observed-derived, estimated, recovered й unknown coverage. «Виміряне» позначає provenance компонентів, а не незалежний котловий лічильник. При method switch немає нового origin/дубля. Counter reset/jump обробляється явною continuity подією; energy_total не зменшується через restart. Recovery — адміністративна операція з evidence hash, dry-run, expected total, durable backup й idempotency; не автоматична реконструкція пропуску.

Для циклу показувати initial plan, last prestart, latest projected total, known actual із quality coverage, unknown minutes, deviation й scope timezone. При unknown negative difference не називати економією. Вартість за dated тарифом відповідного інтервалу; не застосовувати поточну ціну до всієї історії.

Для зафіксованого 12h прогнозу: reference — локальний calendar heating cycle start; physical edge окрема додаткова прив'язка. Обрати latest original issue ≤reference−12h, яка реально покриває reference/відповідні цільові точки. Зберегти actual lead, plan/model IDs, source timestamp, checksum. Якщо не існує — missing. Не робити retrospective replay для заповнення лінії. Історичний forecast може покривати лише частину вибраного періоду; actual продовжується незалежно.

Для проспективних 24/36/48h checks використовувати curve issued before target, реальні reported values або явно позначену bounded interpolation; не extend curve і не використовувати derived recovery energy як незалежну мітку. Прогалини розривають графік. Історія й порівняння переживають reload/restart, архів читається worker з indexed range queries/cursor й не створює великих sensor attributes.

## Камін, циркуляція й вентиляція (F01–F06)

Зберегти поточні thresholds/hysteresis, джерела trend і three fan levels із документа 01/R6: ignition Δ≥2 і slope>0,8; start Δ≥5; intense Δ≥10 без fading; keep Δ≥3; off Δ<3 безперервно 300 с; fast off Δ<4 і slope≤−2. Unknown/stale sensor забирає fireplace demand, а не видає вигадане згасання. Trend continuity gap понад 90 с скидає безперервний countdown. Після restart duration відновлюється лише за придатним збереженим evidence.

Arbiter об'єднує fireplace й night requests; завершення нічних 900 с не вимикає активний fireplace request. Ніч 23–07 обмежує percentage; чинні імпортовані 38/42/50 зберегти. Auto володіє вентилятором за правилом demand exists→on, none→off; Manual Run не гаситься тільки через відсутній автоматичний demand; Stop — явне вимкнення автоматичного fan request. Глобальний armed/fan permissions і verified backup contract мають явну семантику в кожному режимі. Невідоме живлення не стає дозволом запуску.

Рекуператор/витяжки — read-only inputs до теплової моделі. Жодного самовільного вимкнення вентиляції для економії, зміни Tuya timer, нового fan speed у реле або перенесення інших автоматизацій.

## API, UI та безпека (U01–U10/O01–O07)

Запропоновані versioned API через автентифікований HA WebSocket:

| Команда | Доступ | Контракт відповіді |
|---|---|---|
| `heating_ai/status` | read | status_seq, snapshot age, actual/desired/control status, compact summary |
| `heating_ai/subscribe` | read | seq updates; reconnect з full snapshot при gap |
| `heating_ai/history` | read | start/end UTC, timezone, cursor, series[], provenance, coverage |
| `heating_ai/settings/get` | read | schema_version, revision, values, persisted_revision |
| `heating_ai/settings/save` | admin | request_id, expected_revision, typed patch → durable receipt/conflict |
| `heating_ai/control` | control permission | typed intent + expires, gateway receipt; без arbitrary service |
| `heating_ai/model/candidate`, `/rollback` | admin | staged candidate/rollback, metrics і receipt |
| `heating_ai/diagnostics` | admin | sanitized bounded diagnostics, без secrets/full config |

Імена — контракт проєкту, не чинні HA services. Local compute transport автентифікований, прив'язаний до конкретної установки, не публічний порт. API відхиляє replay/прострочений sequence й body >256 КіБ; history page ≤64 КіБ, sensors attributes ≤8 КіБ serialized default JSON з ensure_ascii=True. У browser немає довгострокового HA token; використовувати існуючу HA session. Валідувати права в backend, не лише ховати кнопку.

UI докладно описаний у документі 05. Стан зберігання: editing→saving→saved/persisted або failed/conflict. Optimistic UI дозволений для pending, не для підтвердженого стану котла. Від'єднана панель показує останній час і блокує control до reconnect; історія лишається доступною як cached із позначкою.

## Робочі пакети після погодження

| WP | Зміст | Передумова | Приймальний результат |
|---|---|---|---|
| 0 | Read-only commissioning/export, private backup, source matrix | Погоджена архітектура | Усі G01 blockers знятті |
| 1 | contracts + pure kernel + test model | WP0 | S/D contract tests, no I/O imports |
| 2 | HA integration/gateway + control-store | WP1 | Fault tests, shadow writes=0, crash reconcile |
| 3 | Isolated compute + bounded planner | WP1 | Deadline/stale results/feasible regressions |
| 4 | Ledger/evidence importer/history | WP1/2 | Parity totals/checksums, immutable comparisons |
| 5 | Models/learning/fire/fan policies | WP2/3/4 | Replay + ownership/inertia/validation tests |
| 6 | Native UI, all status/error states | WP2/4 | Browser/theme/text/a11y and usability tasks |
| 7 | Shadow comparison + fault soak | WP2–6 | Документ 06 gate report без actual commands |
| 8 | Controlled activation і спостереження | Явно погоджене перемикання | Physical acceptance + rollback rehearsal |

Порядок не є дорученням почати зараз. Не прибирати старі regression cases заради green CI. Якщо старий тест кодує помилкову вимогу, змінити тільки з документованим contract change й traceability, а не xfail/skip. Розробка завершена лише за пройденими P0/P1, відсутністю відкритих critical defects і окремим звітом про фізичні обмеження.
