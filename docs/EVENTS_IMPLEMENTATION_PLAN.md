# План внедрения: Вариант 1 + Вариант 3 (события и аналитика)

## Фазы

### Фаза 1 — Данные и бэкенд
1. Конфиг: Event Calendar spreadsheet ID и gid листа.
2. Загрузка событий: fetch из Google (CSV export) → сохранение в `data/events.csv`; парсинг дат и полей (название, дата начала/конца, Sales target, Product Type, бюджет/затраты при наличии).
3. Модуль `events_data.py`: загрузка событий из CSV; фильтр «события, пересекающиеся с периодом»; для каждого события — период пересечения с «7 дней» или «4 недели».
4. В `report_data.py`: хелпер «продажи за период [date_from, date_to] с опциональным фильтром по Sales channel и Product Type» → `{ total_revenue, orders_count }`.
5. В `events_data.py`: для каждого события — продажи по целевой группе за период пересечения (вариант 1); для варианта 3 — продажи за N дней до старта события и за N дней во время, разница, %, затраты, ROI.

### Фаза 2 — REST API
6. `GET /api/events?date=YYYY-MM-DD&period=7d|4w` — события за период + продажи по целевой группе за период пересечения (вариант 1).
7. `GET /api/events-analysis?date=YYYY-MM-DD&period=7d|4w` — то же список событий + для каждого: до/во время, прирост, затраты, ROI (вариант 3).
8. При «Обновить данные» (POST /api/refresh) дополнительно подтягивать события и сохранять в `data/events.csv`.

### Фаза 3 — UI
9. Блок «События за период» на главном экране (вариант 1): после сводки «За 7 дней / За 4 недели» — секция со списком событий; под каждым — карточка «Продажи по целевой группе: X ₾, N заказов».
10. Новая вкладка «Аналитика по событиям» (вариант 3): выбор периода (7d/4w), список событий с карточками «Во время: X ₾», «До: Y ₾», «+Z%», при наличии «Затраты / ROI».

---

## REST API (спецификация)

### GET `/api/events`

**Назначение:** События, активные в выбранном периоде, и продажи по целевой группе каждого события (Вариант 1).

**Query:**
- `date` (optional) — дата в формате YYYY-MM-DD; по умолчанию сегодня.
- `period` (optional) — `7d` (последние 7 дней) или `4w` (4 недели); по умолчанию `7d`.

**Response 200:**
```json
{
  "reference_date": "2026-02-24",
  "period": "7d",
  "period_start": "2026-02-18",
  "period_end": "2026-02-24",
  "events": [
    {
      "name": "название кампании",
      "date_start": "2026-02-11",
      "date_end": "2026-02-20",
      "campaign_type": "тип рекламной компании",
      "sales_target": "Facebook",
      "product_type": "Coffee",
      "budget_per_day": "5",
      "cost_total": 123.45,
      "overlap_start": "2026-02-18",
      "overlap_end": "2026-02-20",
      "sales_during": {
        "total_revenue": 1500.00,
        "orders_count": 12
      }
    }
  ]
}
```
- Если у события нет Sales target / Product Type — в ответе пустая строка или null; `sales_during` тогда считаем по всем продажам за период пересечения.

---

### GET `/api/events-analysis`

**Назначение:** Аналитика до/во время и ROI по каждому событию за период (Вариант 3).

**Query:**
- `date` (optional) — YYYY-MM-DD; по умолчанию сегодня.
- `period` (optional) — `7d` или `4w`; по умолчанию `7d`.

**Response 200:**
```json
{
  "reference_date": "2026-02-24",
  "period": "7d",
  "events": [
    {
      "name": "название кампании",
      "date_start": "2026-02-11",
      "date_end": "2026-02-20",
      "sales_target": "Facebook",
      "product_type": "Coffee",
      "cost_total": 123.45,
      "overlap_start": "2026-02-18",
      "overlap_end": "2026-02-20",
      "days_count": 3,
      "sales_during": { "total_revenue": 1500.00, "orders_count": 12 },
      "sales_before": { "total_revenue": 800.00, "orders_count": 6 },
      "revenue_change": 700.00,
      "revenue_change_pct": 87.5,
      "roi": 5.67
    }
  ]
}
```
- `sales_before` — продажи по целевой группе за N дней до `date_start` (N = длина периода пересечения, т.е. сколько дней событие реально попало в 7d/4w).
- `roi` — только если `cost_total > 0`: `(revenue_during - revenue_before) / cost_total`. Иначе не передаём или null.

---

### POST `/api/refresh`

**Расширение:** Помимо обновления `data/online_sales.csv`, при вызове обновлять и `data/events.csv` (загрузка листа Event Calendar). Ответ без изменений: `{ "ok": true, "report": ... }`.

---

## Файлы

| Файл | Действие |
|------|----------|
| `config.py` | Добавить EVENT_CALENDAR_SPREADSHEET_ID, EVENT_CALENDAR_SHEET_GID |
| `fetch_events.py` | Новый: загрузка Event Calendar по CSV export, сохранение в data/events.csv |
| `events_data.py` | Новый: парсинг events.csv, пересечение с периодом, продажи по событию, до/во время/ROI |
| `report_data.py` | Добавить функцию sales_in_period(date_from, date_to, channel?, product_type?) → { total_revenue, orders_count } |
| `app.py` | Роуты GET /api/events, GET /api/events-analysis; в api_refresh вызывать загрузку событий |
| `static/index.html` | Блок «События за период»; вкладка «Аналитика по событиям» |

---

## Маппинг колонок Event Calendar

По структуре таблицы (A, B, C, D, E, G, H, …):

- A — название компании → `name`
- B — дата начала → `date_start` (парсим как в report_data: dd.mm.yyyy, d.m.yy)
- C — дата конца → `date_end`
- D — бюджет на день → `budget_per_day` (строка или число)
- E — тип рекламной компании → `campaign_type`
- G — Sales target → `sales_target` (канал)
- H — Product Type → `product_type`
- Сумма затрат: ищем колонку по подстроке «сумма затрат» / «Сумма затрат» (возможно две такие — берём первую или суммируем) → `cost_total`

При экспорте в CSV заголовки могут быть с пробелами/другой кодировкой — нормализуем пробелы и ищем по ключевым словам (дата начала, дата конца, sales target, product type, сумма затрат).
