# Проверки проекта

## Точечная доработка ТН ВЭД: TENCEL и Excel — 08.09.2026

Полный `pytest -q`: **229 passed**, 109,09 с (5 предупреждений существующих зависимостей).
Ruff check и format --check прошли: 66 Python-файлов. Frontend: **4 tests passed**,
lint, typecheck, build прошли. Предупреждения jsdom и размера bundle не препятствуют сборке.

`backend/tests/test_tnved_export.py`: TENCEL/Tencel/тенсел, независимый деним,
производственные/обычные ветви 24–27, верх обуви из размеченного состава и отрицательные
неоднозначные примеры. Полный экспорт 57 строк проверяется с обычной и заранее существующей
пустой M: заголовок «Источник», прямой URL только у CONFIRMED, короткий комментарий только
у UNRESOLVED. Повторная обработка очищает прежние технические комментарии/ссылки и сохраняет
формулы/соседние данные. Полный engine и его строгие правила не изменены.

Живой запуск: `python -X utf8 scripts/run_real_tnved.py`, затем
`python -X utf8 scripts/verify_tnved_delivery.py`. Второй скрипт сверяет все 57 решений и ячейки
F/L/M, сравнивает комментарии/источники со Skill и проверяет OOXML. Снимок предыдущих 17 решений
и полных комментариев — `test-results/real-tnved/followup-before.json`; исторический baseline
13 решений остаётся неизменным. Итоговый протокол — `test-results/real-tnved/verification.json`.

## Предыдущая итерация ТН ВЭД — 08.09.2026

Полный `pytest -q`: **205 passed**, 93,43 с. В том числе 57 отдельных golden cases
и все прежние коммерческие regression-тесты. Ruff check и format --check прошли.
Frontend: **4 tests passed**, lint, typecheck, build прошли. Карточка кандидата
проверяется отдельным UI-тестом: UNRESOLVED, причина, отсутствие финального кода и ссылка Alta.

Новые тесты: `backend/tests/test_tnved_rules.py`; усиленные Excel-тесты в `test_tnved.py`.
Положительная классификация обуви проверяется во всех 6401–6405, включая границы 24 см
и 3 см. Для джемперов проверены 12 петель по двум направлениям и масса 600 г.
Проверки UNKNOWN, конкурентов, residual siblings, changed wording и missing input
не позволяют подменить неизвестность совпадением.

Постоянный набор: `backend/tests/fixtures/tnved/baseline.json`, `alta.json`, `expected.json`.
Baseline содержит исходный XLSX в base64 и SHA256, app_before и предыдущие файлы.
В `expected.json` зафиксировано подтверждённое пользователем происхождение Skill-файла с 23 кодами.
Каждое из 57 ожиданий имеет код либо причину, обязательные фрагменты комментария и объяснение.
Перегенерация ожиданий не выполняется автоматически.

```powershell
.venv\Scripts\python.exe -X utf8 -m pytest backend/tests/test_tnved.py backend/tests/test_tnved_rules.py -q
.venv\Scripts\python.exe -X utf8 scripts/inspect_tnved_regression.py
# После полного pytest, Ruff и frontend-проверок:
.venv\Scripts\python.exe -X utf8 scripts/run_real_tnved.py
.venv\Scripts\python.exe -X utf8 scripts/verify_tnved_delivery.py
```

`inspect_tnved_regression.py` использует snapshots исключительно для разработки и тестов.
`run_real_tnved.py` использует новую живую сессию Alta, без fixture/cache-кодов.
`verify_tnved_delivery.py` проверяет все 57 решений, уникальность кандидата,
SHA256 оригинала/Skill, состав ZIP, неизменность исходных ячеек и стилей,
формул/строк/merge/filter/freeze/drawings, тип строковых кодов и открытие XLSX;
создаёт `verification.json`, `differential-57.json`, `skill-comparison-57.md`.

Финальный live-прогон выполнен: **17 CONFIRMED / 40 UNRESOLVED / 0 ошибок Alta**.
Все 57 строк совпали с expected.json. `verify_tnved_delivery.py` завершился успешно:
исходный SHA256 сохранён, изменены только целевой worksheet и styles, файл открывается.
Изменённые строки и отличия от Skill перечислены в [ACCEPTANCE.md](ACCEPTANCE.md).

Дополнительный Excel-тест сохраняет настоящие drawing/image/relationship parts и custom XML
побайтно; для создания рисунка не нужна дополнительная зависимость Pillow.
Проверка существующего кода охватывает обычное значение, неопределённую классификацию
и формулу без cached value: формула остаётся формулой.

Покрытие разделов Skill и статусы IMPLEMENTED / PARTIAL / BLOCKED BY MISSING INPUT /
BLOCKED BY UNIMPLEMENTED RULE / BLOCKED BY SOURCE — [TNVED_RULES.md](TNVED_RULES.md).
Необработанная формулировка Alta — ограничение правила, недоступная Alta — ограничение источника;
их нельзя маскировать общим «недостаточно данных».

Оставшиеся предупреждения не являются падениями: прежние deprecation FastAPI/Starlette,
чтение расширений коммерческих книг, jsdom getComputedStyle и размер frontend-чанка.

## Предыдущая коммерческая итерация — 07.09.2026

## Команды

Из корня:

```powershell
.venv\Scripts\python.exe -X utf8 -m pytest -q
.venv\Scripts\ruff.exe check backend scripts
.venv\Scripts\ruff.exe format backend scripts --check
```

Из `frontend`:

```powershell
npm.cmd run test
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
```

Итог: **79 backend-тестов прошли** (полный прогон 97,83с); после усиления метаморфной проверки распределения повторно прошли все 28 тестов правил (0,08с). Ruff check и format --check — зелёные; frontend 3/3, lint, typecheck, build — зелёные.

Полный набор включает модульные расчёты, API, очередь, SQLite/историю/скачивание, ТН ВЭД, постоянную коммерческую регрессию и проверку всего экспорта. Проверки frontend: 3 теста; lint/typecheck/production build.

## Постоянная коммерческая регрессия

`backend/tests/fixtures/merchandise/inputs.json` содержит безопасную копию ячеек трёх реальных таблиц: без изображений и посторонних коллекций FACT, с сохранением исходных номеров строк, типов, форматов, SHA256 оригиналов. `expected.json` фиксирует 338 артикулов: база, target, сезонный объём, план%, плановые единицы, предсезон, сезонный факт/ST/выполнение, отклонения, темп, required, cover, forecast/ST, статус, оба диагноза, рекомендация, полный объект второй волны.

Тесты материализуют временные XLSX и выполняют настоящий `service.run`; Downloads и пользовательские исходники тестам не нужны. Ожидания никогда не генерируются автоматически в pytest. Весь тестовый прогон пишет только во временные каталоги.

| Проверка | Статус | Свидетельство |
|---|---|---|
| Каждый артикул, все golden-поля | IMPLEMENTED | `test_every_real_article_matches_golden` |
| Независимая арифметика на реальных значениях | IMPLEMENTED | `test_real_articles_independent_arithmetic`: без вызовов planning/metrics/decisions; 223 плана, 338 строк, факт/темп/покрытие/прогноз/вторая волна |
| Первая партия не влияет на расчёты | IMPLEMENTED | Полный повтор на реальной копии с 1e12 + прежний синтетический повтор |
| Предсезон/поздний вход не меняют официальное выполнение | IMPLEMENTED | `test_preseason_and_late_delivery_do_not_shift_official_execution` |
| Размеры/распределение меняют диагноз, не FACT ST | IMPLEMENTED | Агрегатные сценарии и сравнение исходного факта |
| Категорийный fallback только при отсутствии индивидуального норматива | IMPLEMENTED | Приоритет, пустая/частичная/некорректная кривая, семантическая перестановка колонок |
| Диапазоны не дают придуманное число | IMPLEMENTED | Срок реализации/наблюдения, лимит скидки, дата проверки, NOS |
| Плановая дата не доказывает фактическую партию | IMPLEMENTED | `test_planned_delivery_is_not_actual_party_evidence` |
| Все ячейки Excel против backend | IMPLEMENTED | `test_all_exported_values_and_compact_layout`: 8 листов, строки, значения/даты/null, отсутствие формул, заголовки, шрифт9, ширины≤45/высоты≤42, фильтры/закрепление |
| Экспертный независимый эталон статусов/действий | BLOCKED BY MISSING BUSINESS RULE | Snapshot — регрессия проверенной реализации; он не является независимым решением эксперта |
| Полная экономика партий/NOS и детализация магазина | BLOCKED BY MISSING INPUT DATA | Пустые поля и ограничения проверяются; отсутствующие данные не заменены синтетическими в реальном результате |

Обновление fixture — явная сопровождающая операция после проверки изменений правил:

```powershell
.venv\Scripts\python.exe -X utf8 scripts/merchandise_fixture.py --capture-inputs
.venv\Scripts\python.exe -X utf8 scripts/merchandise_fixture.py --accept-results
```

Не использовать `--accept-results` просто для устранения падения теста. В этой итерации ожидания второй волны пересмотрены после обнаружения недопустимого допущения: будущая плановая дата не подтверждает отсутствие досрочного поступления. Подтверждённые поля теперь пусты при неизвестной партии; условный прогноз хранится отдельно. Остальная арифметика и статусы совпали.

## Реальные входы и HTTP

```powershell
.venv\Scripts\python.exe -X utf8 scripts/run_real_merchandise.py
.venv\Scripts\python.exe -X utf8 scripts/smoke_merchandise.py
.venv\Scripts\python.exe -X utf8 scripts/verify_delivery.py
```

Первый сценарий непосредственно читает три подтверждённых Excel из Downloads. Второй требует локального проверочного backend на `127.0.0.1:8001`, выполняет реальный HTTP-запуск, получает все страницы, сравнивает каждую строку с golden, скачивает XLSX и сверяет SHA256 оригиналов. Последний проверяет неизменность 10 встроенных файлов относительно ZIP и ранее сохранённый результат ТН ВЭД; сеть не использует.

Старый файл W35 не читается. `test-results/real-merchandise/http-verification.json` содержит id запуска и хеши. Файлы исторических ресурсов открываются только для чтения.

## UI и ограничения

В браузере проверены последняя production-сборка, история реального запуска, сводка, таблица/карточка артикула, доказательства диагноза и нормативы. Расчётных формул на frontend не добавлено.

Известные предупреждения: openpyxl о расширениях исторических книг (книги не пересохраняются), deprecation Starlette/httpx/AnyIO в тестовом клиенте, размер JS-чанка более500КБ. Это не падения тестов. Корпоративное развёртывание, PostgreSQL, печать в Microsoft Excel и неформализованные экспертные решения вне границ этой проверки.
