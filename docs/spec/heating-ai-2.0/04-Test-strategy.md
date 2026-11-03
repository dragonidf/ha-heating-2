# Heating AI 2.0 — тестова стратегія

**Статус:** план перевірок майбутньої реалізації, не звіт про вже створений контролер. Фактично виконані перевірки старої 0.3.20 наведені в validation-summary.md. У production у цьому аудиті не симулювали outage, відмови, температуру й не надсилали жодних команд пристроям.

## Модель доказів

| Рівень | Що перевіряє | Чого не доводить |
|---|---|---|
| Unit/property | Pure kernel, units, алгоритми, invariant | Реальний HA event order і фізичне реле |
| Contract | JSON versions/null/false/0, I/O capabilities, auth | Фізичну топологію й точність датчиків |
| Integration/fault | Реальні SQLite, subprocess, restart, async HA lifecycle | Економію чи тепло конкретного будинку |
| Historical replay | Відтворення оригінальних входів/рішень, regression | Що counterfactual план дав би саме таку фізичну температуру |
| Browser | Справжні компоненти, interaction, доступність | Точність моделі й фактичне вмикання котла |
| Shadow | Роботу на реальних даних без команд | Фізичну реакцію на нові команди |
| Commissioning | Підтверджене виконання OFF/ON, вимір і фактична схема | Працездатність у мороз, якого ще не було |
| Prospective cycles | Реальні відхилення, інерція, 12/24h/сезонні помилки | Гарантовану точність у всіх майбутніх сценаріях |

Кожен requirements.csv test ID отримує executable test або підписаний practical checklist із evidence. Неперевірений сценарій залишається blocked, не pass. Усі артефакти мають commit/config/model/topology hashes, seed, timezone, environment і start/end times.

## Інваріанти, які повинні бути формалізовані

1. HEAT не надсилається при armed off, manual pause, observation, grid off/unknown, непридатній room temperature, невалідній конфігурації, простроченому intent/plan або неправильному owner epoch.
2. Safety OFF може перервати min-on; жодна черга/планувальник/compaction/disk timeout не затримує створення stop intent понад SLO.
3. Один автоматичний gateway на пристрій; дублікати intent не створюють новий side effect. Фізичний direct manual change лишається зовнішнім owner.
4. Plan segments sorted, half-open, nonoverlapping, finite, в межах capability/strategy/outage masks; сумарна енергія узгоджена з інтегралом їхньої effective power в заданому scope.
5. Missing/stale/conflicting не дорівнює zero. False, numeric 0, None, empty list і missing key зберігають різну семантику після transport.
6. Незмінний initial plan/12h forecast не змінюється після нового forecast, model update, reload, recovery correction або вибору іншого UI range.
7. Known+estimated+recovered totals не дублюють один інтервал; recovered не стає training label; gaps не зникають через restart.
8. Model candidate ніколи не замінює champion до повної валідації/commit; rejected candidate не вимикає придатне чинне керування.

Property генератор: ≥1 000 фіксованих/збережених прикладів на ключовий інваріант; seed у звіті, shrink failing example у fixture. Mutation checks мають виявляти принаймні видалення кожного safety guard, підміну unknown на 0, ігнорування epoch і зміну frozen baseline. 100% transition coverage для safety/ownership state machine; coverage загального коду не підміняє перевірку небезпечних переходів.

## Матриця умов

| Вісь | Значення |
|---|---|
| Надворі | −25/−15/−5/0/+5/+15/+25 °C; різка зміна ±5 °C |
| Кімната | нижче lower, рівно lower/target/upper, upper+0,1; missing/stale/conflict |
| Обратка/запас | 15/20/25/30/35/40/50/65 °C; cold pipe/warm inventory; unknown |
| Фізичний профіль | 3/6/9/AUTO/unconfirmed; фактична duty 0–100%; wrong selected mode |
| Живлення | усі фази; одна втрачена; high-voltage protection; grid unknown; Deye stale; grid flicker |
| Outage | scheduled/normal/unknown/emergency; немає завтра; зміна під час нагріву; stale payload |
| Комфорт | обидві стратегії; day/night boundaries; strict hours; warm/fire no need |
| Камін/вентилятор | ignition/burning/intense/fading/cold/unknown; three speeds; night overlap/manual |
| Вентиляція | on/off/unknown для кожного реле; непідтверджена supply/airflow |
| Час | 22:59/23:00/04:59/05:00/06:30/07:00; midnight/month/year; DST spring/fall |
| Відмови | CPU hang, disk full/slow/corrupt, process kill, HA restart, MQTT/Tuya/Internet unavailable |
| UI | 320/390/430/768/1440/1920 px; 100/125/200% text; dark/light; touch/keyboard; offline/reconnect |

Застосувати pairwise до повної матриці й автоматично перевіряти покриття пар. Для критичних перетинів використовувати обов'язкові комбінації, а не сподіватися на pairwise: (1) grid loss + heat + planner busy; (2) manual + delayed command echo + restart; (3) upper + min-on + disk hang; (4) morning outage + 3 кВт + already heated minutes; (5) missing room + plausible thermostat stale bias; (6) Deye frozen while LOAD/АКБ online + fresh input voltages; (7) daylight thermal gain + room infrequent reports + nominal power assumption.

## Конкретні відмови й очікувана поведінка

| Відмова | Injection у стенді | Обов'язковий результат |
|---|---|---|
| Planner CPU 100%/infinite search | Controlled busy loop/subprocess stop | Kernel/gateway SLO pass; hard kill ≤10 с; stale result не застосований |
| Learner завис | Worker sleep/CPU, large dataset | Чинний champion і керування працюють; один pending learner |
| Slow disk / SQLITE_BUSY | Writer delay і lock | HEAT prepare timeout→не запускати; OFF dispatch без очікування |
| ENOSPC | Квотований temp filesystem | Settings receipt failure, старі values чинні; safety/evidence gap visible |
| Crash у command transaction | Kill після prepare/send/echo | No blind replay; actual-state reconcile; owner epoch новий |
| Пошкоджений state/schema | Truncate/checksum/version mismatch | Quarantine, SAFE_HOLD, no empty successful reset |
| HA restart під час heat | Локальний HA test instance | STARTING→reconcile; не запускати через boot stale cache |
| Late stale event | Затримати auto event, потім власний heat echo | Немає false manual pause; actual manual change все одно діє |
| Duplicate intents / two UI clients | Resend IDs/concurrent CAS saves | Один effect; другий save conflict, жодного lost update |
| App transport offline | Drop connection, reconnect reorder | Expired proposal відкинуто; FALLBACK самостійний |
| Frozen source timestamps | Перепублікувати old value з new received_at | Не оновлювати measurement age |
| Wrong units/topology | W↔kW, aliases, signed reverse, overlap | Відмова або explicit conflict, без тихого коригування |
| Outage metadata storm | 10 000 однакових updates | Coalescing, bounded memory, no replanning storm |
| History query storm | Два клієнти, 30/90 днів, cancel/reconnect | Bounded cache, auth, max payload, керування не чекає |
| Unsafe UI payload | arbitrary service/model NaN/oversize/stale rev | Відхилено backend, state unchanged, sanitized error |

Повні кроки, test ID й вимоги є у test-scenarios.csv. Майбутній `tests/faults` використовує реальні subprocess і SQLite, не тільки monkeypatch у fake HA.

## Історичні регресії, які не можна втратити

| Епізод | Яку властивість відтворити | Evidence source |
|---|---|---|
| 21.10 пропущений 06:30–07:00 | Правильна дата cycle, резерв до наступного вікна, нічне доповнення до 05 | R3, старі morning fixtures |
| 29.10 observed:null | Nested schema/null не вбиває control loop | tests/test_incident_20261029.py |
| 31.10→01.11 +23,2% known overrun | Immutable reference не зникає при unknown; повнота й attribution чесні | R1, тільки checksum-verified original snapshots |
| 01.11 room freshness/oversize attributes | Температуру не освіжає вологість, bounded transport | tests/test_qa_*.py |
| 02.11 outage forecast disappears | Thermal scenario може існувати без права HEAT; unknown watts не нуль | R5, test_outage_forecast_continuity |
| 03.11 blocking/control race | Planner busy + watchdog + stale event + profile save | R2, test_background_control |

Старий код містить >500 тестів, але це не покриття всіх фізичних умов. У replay імпортувати старі fixtures і результати baseline без переписування historical output. Відхилення нової моделі/політики пояснювати через decision report, не підміняти «очікуваний результат» під нову реалізацію.

## Браузер і UX

Chromium і WebKit; Android WebView practical check у телефоні власника. Browser harness використовує справжні components/API contracts і synthetic data, включно з 0/unknown/null. Усі навігації, Save/Undo/conflict, one-shot, manual pause/resume, range changes, actual-only/frozen-missing graph й offline state перевіряються кліками/клавіатурою. Screenshot comparison для затвердженого дизайну; DOM checks overflow, контраст/labels/focus та touch targets ≥44 px. Перевірити без fonts/CDN/internet.

Практичні задачі власника: за ≤10 с визначити чи гріє котел, чому, коли наступний сеанс, чи є дефіцит і наскільки надійний факт; за ≤2 дії змінити comfort target; за ≤3 знайти 7-денний expected/fact; відрізнити «збережено налаштування» від «режим на котлі фізично перемкнуто». Протокол не повинен підказувати правильну відповідь.

## Числові acceptance gates

- Control: всі SLO документа 02 у 24-годинному стендовому soak з CPU/I/O/history stress, без пропуску safety event; loop-lag deadline failures видимі.
- Energy: математична похибка інтегратора ≤0,1% на еталонних синтетичних траєкторіях; migration totals within 10⁻⁶ кВт·год; фізичну точність балансу оцінювати окремо.
- Validated stable cycles: 10 завершених циклів, ≥95% quality coverage, відсутні manual/outage confounders для оцінки саме планової похибки. Медіана |fact−last-prestart|/reference ≤10%, P90≤15%; initial reference показувати окремо. Невдалий gate не приховувати новим poststart baseline.
- Forecast: ≥7 незалежних днів для конкретного горизонту/режиму, 12/24h MAE≤0,3 °C і P90 absolute error≤0,5 °C; за неповного доказу відповідний horizon «перевіряється». Це цілі, не гарантія на майбутній мороз.
- Overheat: safety stop command своєчасний у всіх fixtures; у практичних кваліфікованих циклах інерційний overshoot≤0,3 °C від comfort upper. Fire/manual/outside disturbances маркуються; не називати викидання незручних циклів успіхом — загальна статистика з ними також зберігається.

Якщо фізичного незалежного energy reference немає, 10/15% gate характеризує узгодженість плану з чинним derived методом, а не метрологічну точність котла. Введення обмеженого fallback може бути безпечним раніше за доказову точність повного MPC; UI й acceptance status повинні це чітко розрізняти.

## Випуск і звітність

CI на кожен PR: lint/type/compile, contracts/unit/properties, SQLite/subprocess fault suite, replay, frontend syntax/unit, Chromium/WebKit. Nightly стенд — soak/bench/mutation. Release — конкретний commit, artifacts checksums, dependency lock/SBOM, сумісність HA/compute protocol, migration dry-run. Не запускати deployment або device fault tests автоматично від GitHub CI.

Не допускаються skipped/xfail P0/P1 без статусу release blocked, зниження порогів після невдалого тесту, вилучення історії, редагування production-сенсорів для красивого тесту. Практичні перевірки обладнання проводяться лише в погодженому commissioning вікні; цей документ не є дозволом негайно їх почати.
