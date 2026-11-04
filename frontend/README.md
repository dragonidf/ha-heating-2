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
