# Heating AI2.0 — локальна симуляція WP2B

Три вкладки: Дім, Історія, Налаштування; модель і діагностика вкладені. Усі значення вигадані. Жодного підключення до Home Assistant, обладнання, старого контролера чи зовнішнього API.

Потрібен Node24.19+ і npm11.9+. Залежності й браузери завантажуються тільки під час підготовки середовища. Готовий demo не потребує інтернету, CDN або зовнішніх шрифтів.

```sh
cd frontend
npm ci
npm run build
npm run preview
# Відкрийте http://127.0.0.1:4173 лише локально.
```

Прив’язка лише до loopback. Не публікувати сервер. Зміни зберігаються тільки в IndexedDB цього origin (`synthetic-heating-ui-v1`), без токенів чи приватних даних. Це транзакційне сховище налаштувань симуляції, не production control-store. При недоступному сховищі кнопки змін блокуються. Інше вікно на тому ж origin створює справжній CAS-конфлікт; чернетка лишається на екрані.

```sh
npm run typecheck
npm run format:check
npm run test:coverage
npx playwright install --with-deps chromium webkit
npm run test:browser
```

Browser tests запускають build preview на127.0.0.1:4173; спочатку виконайте build. Chromium/WebKit ×390/1440, додатково320/700/1100, light/dark, 200% текст, axe/клавіатура, touch, CAS/fault/reconnect. Screenshot baselines — тільки синтетичні. Оновлюйте їх лише після перегляду зміни дизайну: `npm run test:browser -- --update-snapshots`.

`tools/wp2b/export_contracts.py --check` перевіряє canonical JSON, згенерований чинними Python-контрактами WP2A. StatusView/APIReceipt/ForecastRecord/BudgetReceipt проходять справжній codec roundtrip. UI1 history/settings projections — нова офлайн-межа для демо, не твердження про наявний native HA API. Actual physical state завжди не перевірений; fake ACK не означає нагрів/зупинку.

Сценарії й відмови відкриваються внизу сторінки. Зміна сценарію — новий синтетичний приклад, не переписування реального архіву. Одноразові/модельні запити працюють тільки в пам’яті демо й не replay після перезавантаження. Довговічність справжнього керування перевіряють незмінені Python suites.

G1/B01–B08 BLOCKED. Native HA themes/auth/WebSocket, реальна метрологія, фізичний STOP, Android WebView/телефон власника, N100 і WP2C не перевірені/не дозволені. Деталі й evidence — `docs/wp2b/REPORT.md`.


При конфлікті порівнюються всі12 параметрів: основа, ваша чернетка й нова збережена версія. Зміни різних полів поєднуються; для різних змін одного поля оберіть своє або нове значення, тоді збережіть явно. Незбережена чернетка блокує швидку зміну цілі на «Дім»; поверніться до налаштувань, щоб завершити її.

Історія читає весь вибраний період через сторінки й показує обмежений огляд з початком, останнім фактом, мінімумами, максимумами та прогалинами. Таблиця містить точки огляду, а не повний експорт. Ліміт100000 вихідних вимірів на запит означає явну помилку з пропозицією скоротити період. Непідтверджені інтервали не з’єднуються. Частки різниці лічильника між днями й тарифами показуються як оцінки; відсутня ціна означає неповну вартість. Демо «Щільна історія та межі обліку» відтворює ці випадки лише на вигаданих даних.

## WP2C native panel — disposable isolated HA only

`npm run build` preserves the standalone demo and emits `dist/assets/panel.js` plus shared local assets. The package collector copies **all** of `dist/assets/`; importing the module registers `heating-ai-panel`. HA injects `hass` and `panel.config.entry_id`; the element renders the accepted UI in its own Shadow DOM. Its only transport is the injected `hass.callWS` and `hass.connection.subscribeMessage`. It never creates a connection, handles a token, calls device services or uses IndexedDB as native settings authority. Read failures show unknown/archive errors; backend status and permissions remain authoritative. All mutations carry boot/generation/owner epoch and explicit request IDs; saved settings need independent server readback.

Source qualification target: HA Core **2026.10.4**, whose official frontend manifest pins **20260930.5** and whose frontend pins `home-assistant-js-websocket` **9.7.1**. Reviewed sources: [Core panel registration](https://github.com/home-assistant/core/blob/2026.10.4/homeassistant/components/panel_custom/__init__.py), [frontend session types](https://github.com/home-assistant/frontend/blob/20260930.5/src/types.ts), [custom panel property injection](https://github.com/home-assistant/frontend/blob/20260930.5/src/util/custom-panel/set-custom-panel-properties.ts), [connection subscription/lifecycle](https://github.com/home-assistant/home-assistant-js-websocket/blob/9.7.1/lib/connection.ts). Source review and unit tests are distinct from actual isolated-HA browser qualification.

`npm run test:browser:native` uses `playwright.native.config.ts`, Chromium/WebKit × mobile/desktop. Run it **inside the disposable HA container network namespace**, with no published ports and no route to user networks, after the synthetic harness has provisioned the entry. Supply generated synthetic `TEST_HA_USER` and `TEST_HA_PASSWORD` through the environment; optional `TEST_HA_BASE_URL` defaults to loopback port 8123 and `TEST_HA_PANEL_PATH` defaults to `/heating-ai`. Tests use normal HA login and the real HA options flow to toggle test simulation. Native tracing is off so HA session tokens do not enter trace artifacts. Only synthetic screenshots and sanitized assertions are evidence. The standalone 202-unit/80-browser regressions, privacy tests and quality thresholds are preserved; native modules also participate in coverage.

Native compatibility remains confined to the new disposable synthetic HA. G1/B01–B08 remain BLOCKED; home/production/LAN/device access, physical qualification and WP2D are outside this package.


Native logical STOP has its own current-session/admin admission path and does not wait for qualified source readings, ordinary mutation permission or settings/history storage. It remains a synthetic intent; the backend independently rejects disabled, unauthorized or stale requests. Normal edits use the backend's configured source-age qualification rather than a second UI age threshold. Native browser setup explicitly toggles disposable simulation, proves that a new boot starts without a source assertion, then sends the accepted typed own-source event through authenticated HA `fire_event`. Accessibility scopes resolve every actual HA Shadow DOM boundary through axe's `fromShadowDom` context; no rules are disabled.
