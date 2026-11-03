# Фактично виконана перевірка

03.11.2026. Перевірявся **чинний старий код 0.3.20**, а не майбутня реалізація 2.0. GitHub/HA не змінювалися.

| Перевірка | Результат | Межа |
|---|---|---|
| 103 source files | Bytes звірені з Git blob SHA pinned commit db7d7ce9c53e4e88c1c27ee10e1f53d6cce10426 | Отримання всього коду не означає доказ кожного фізичного сценарію |
| Runtime modules | Дев'ять SHA-256 збіглися з pinned кодом після появи runtime0.3.20 | Runtime змінився з0.3.19 під час читань іншою стороною |
| make check | Compileall, generated assets/release manifest, JS syntax і HACS JSON checks пройшли | Перший downloaded text мав transport trailing newline; до запуску baseline відновлено точні bytes за blob hashes, source не виправляли |
| Python tests | 535 тестів, OK; Python3.12;78.407с | Fake HA/числові fixtures, не relay tests |
| Node tests | 50 тестів,50pass,0fail | Без повного browser harness у цьому локальному запуску |
| Початковий test attempt | 519 завантажених тестів,3import errors через відсутні Jinja2/Hypothesis | Установлено declared test dependencies й повторено весь suite; це проблема середовища, не дефект baseline |
| GitHub CI | Tests41596297272 success, release41596985478 success на тому самому SHA | CI source містить Python3.12/3.13 і Chromium/WebKit; локально цей browser suite повторно не запускався |
| HA entity search | 71 heating entity, partial=false; отримані states | Послідовні API snapshots не є одним атомарним моментом |
| Automations | Чотири повні чинні configs прочитано; точні references thermostat/fan перевірені | Не виключає локальний external/Tuya код |
| Helper dependencies | Template35 і utility_meter21 отримані; релевантні source chains перевірено | Повний YAML alive/local app не отримано |
| Recorder incident | 06:30–09:37; entity counts25/3/4/161/27/5,has_more=false | Power3.20 після reload не має довгого prospective спостереження |
| Long statistics | 27.10–03.11,8temperature daily rows; energy_total лише2rows | Повернуті +33.05recovery не названо споживанням саме02.11 |
| Logs | Бounded supervisor window,100filtered lines | Не весь архів журналу, offset зіставляється окремо |
| Dashboard config search | Відповідь INVALID_ARGUMENT | Не отримано живий render/config панелі; UI-аудит за source/попередніми звітами |
| Physical tests | Не виконувались | Це свідоме дотримання заборони змін |
| Heating AI2.0 tests | Не виконувались: коду ще немає | 86вимог й38сценаріїв мають статус specified/planned,не pass |

Виконані read-only HA requests: state/search/history/template render/get automation/list helpers/get logs/get app/get dashboard search. Не було service calls/event writes/helper edits, restart/start/stop, GitHub mutation, встановлення плагінів або змін production-файлів. Залежності тестів установлювалися лише в тимчасовому робочому середовищі.

Нормативні SLO, forecast/energy targets і rollout gates — критерії майбутньої реалізації. Цей аудит не сертифікує фізичну безпеку, економію чи точність нової системи.
