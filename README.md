
# data-analytics-platform

Takes a raw Excel report of open work orders, puts it in a source Postgres database, transforms it into a star schema in a warehouse, then shows it with a FastAPI backend and a Streamlit dashboard.

## Databases
Two Postgres instances:
- **source** (`source_db`, port 5433) - table `raw_monthly_report`, same wide columns as the CSV (`name`, `code`, `year`, `month` and category/status columns).
- **warehouse** (`dwh_db`, port 5434) - star schema:
  - `dim_office` (`name`, `code`)
  - `dim_date` (`year`, `month`)
  - `dim_category` (`cat1` .. `cat7`)
  - `dim_status`
  - `fact_work_order_status` - grain: name x month x category x status, measure `order_count`
Excel total columns are not stored in the fact table. Totals are `SUM(order_count)` in the API.

## API
Base URL: http://localhost:8000  
Swagger: http://localhost:8000/docs
The API only connects to the warehouse, not to source or Excel.
| Method | Path | What it returns |
|---|---|---|
| GET | `/health` | `{ "status": "ok" }` if the warehouse is up |
| GET | `/api/filters` | lists for the dashboard: `periods` (`year`, `month`, `month_name`), `offices` (`name`, `code`), `categories` (`category_code`), `statuses` (`status_code`, `name_fa`) |
| GET | `/api/kpis` | `total_open`, `office_count`, `top_category`, `top_category_total` |
| GET | `/api/metrics/trend` | `year`, `month`, `month_name`, `total` per month |
| GET | `/api/metrics/by-office` | `name`, `code`, `total` |
| GET | `/api/metrics/by-category` | `category_code`, `total` |
| GET | `/api/metrics/by-status` | `status_code`, `name_fa`, `total` |
| GET | `/api/metrics/matrix` | `name`, `category_code`, `total` (office x category) |
All metric endpoints (and `/api/kpis`) take the same optional query params. Skip a param to mean "all":
| Param | Example |
|---|---|
| `year` | `1401` |
| `month` | `7` |
| `code` | `6010` (office code from the Excel file) |
| `category_code` | `cat1` .. `cat7` |
| `status_code` | `in_progress`, `invoice_prep`, `at_consultant`, `at_hq`, `at_finance` |


Examples:
```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/kpis
curl "http://localhost:8000/api/kpis?month=7"
curl "http://localhost:8000/api/metrics/by-category?code=6010"
```

## Quick start
Copy `.env` values (user/password/db names) and then:
```bash
docker compose up --build
```