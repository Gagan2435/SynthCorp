# SynthCorp
live : https://synth-corp.vercel.app/

**Describe a company. Get its data.**

SynthCorp turns a short YAML description of a company into a realistic, *connected* relational dataset: every invoice belongs to a real customer, invoice amounts follow the customer's plan, and customers who churn file more support tickets in the weeks before they leave. The data is stored in MySQL, checked by an automated data-quality engine, and can be downloaded (CSV / SQL) or served as a small REST API that an AI agent can practise against.

Why it exists: training and evaluating AI agents on real software needs realistic data, and real company data is private. Random fake data isn't good enough because it has no relationships or behaviour.

```
Next.js + TypeScript UI ──► FastAPI ──► Generator engine ──► MySQL
 (schema editor, table map,   (REST API,   (dependency order,     (one set of
  preview, quality report)     background   patterns, seeds)        tables per run)
                               runs)              │
                                                  ▼
                                        Quality engine (SQL checks)
```

## Run it

### Everything with Docker (MySQL + backend + UI)

```bash
docker compose up --build
# UI:  http://localhost:3000     API docs: http://localhost:8000/docs
```

### Locally without Docker (SQLite, zero setup)

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload            # http://localhost:8000

cd ../frontend
npm install
npm run dev                              # http://localhost:3000  (proxies /api to :8000)
```

To use your own MySQL locally, set `DATABASE_URL=mysql+pymysql://user:pass@localhost:3306/synthcorp` before `alembic upgrade head`.

### Tests

```bash
cd backend && python -m pytest -q        # 39 tests
cd frontend && npm run typecheck && npm run build
```

## The schema language

```yaml
name: saas_company
seed: 42                # same seed + schema = identical data
locale: en_IN           # Faker locale for names, cities, phones
tables:
  - name: customers
    rows: 1000
    columns:
      - {name: id, type: id}                          # every table needs exactly one id
      - {name: email, type: email, unique: true}
      - {name: signup_date, type: date, start: "2023-01-01", end: "2025-06-30",
         seasonality: {peak_months: [1, 2, 9], strength: 0.6}}
      - {name: churn_date, type: date_after, after: signup_date, min_days: 60,
         max_days: 700, max_date: "2025-12-31", null_rate: 0.6}
```

Any column also accepts `null_rate` (0-1) and `unique: true`.

| type | what it makes | options |
|---|---|---|
| `id` | 1..N primary key | none |
| `uuid`, `person_name`, `email`, `company`, `phone`, `city` | fake values (Faker, seeded) | none |
| `text` | a sentence | `words` |
| `choice` | one of `values`, optionally weighted | `values`, `weights` |
| `cycle` | `values` in order, repeating | `values` |
| `int`, `float` | number in a range | `min`, `max` (+ `decimals`) |
| `bool` | true/false | `p` |
| `date` | a date in a range, optional busy months | `start`, `end`, `seasonality` |
| `date_after` | a date after another column of the same row | `after`, `max_days`, `min_days`, `max_date` |
| `fk` | id of a row in another table | `ref: table.id`, `distribution` (`uniform`, `zipf`, `one_to_one`), `zipf_s`, `boost` |
| `lookup` | copy a value by following foreign keys | `path: [fk_column, column, ...]` |
| `parent_flag` | a label that depends on whether a parent column is empty | `fk`, `parent_column`, `if_null`, `if_not_null` |
| `date_from_parent` | a date after the parent's date, optionally before its end date | `fk`, `parent_column`, `max_days`, `min_days`, `until_column`, `max_date` |
| `date_around_event` | dates clustering just before a parent's event | `fk`, `start_column`, `event_column`, `window_days`, `probability`, `max_date` |

Unknown types, misspelled options, missing tables, circular dependencies and bad references are all reported together with the table and column named.

## How it works, and why

**Dependency order.** Tables are sorted so parents are generated before children (Kahn's algorithm; circular references are reported). Ids are 1..N, so a child row finds its parent row by list index in O(1), which is what makes lookups and parent-aware dates cheap.

**Reproducible.** Each table gets its own random stream derived from `sha256(seed:table_name)`. The same seed gives identical data, and adding or editing one table does not change the data of the others (tested).

**Realistic behaviour, not just valid values.**
- `zipf` picks parents with power-law weights, so a few customers produce most invoices. Which parents are "heavy" is shuffled, not just the first ids.
- `boost` multiplies the weight of parents that have a column set (churned customers get 3x the tickets).
- `date_around_event` puts a share of dates just before a parent's event (tickets before churn).
- `date_from_parent` with `until_column` keeps dates inside the parent's lifetime (no invoice after the customer churned).
- `lookup` and `parent_flag` keep derived values consistent (invoice amount = customer's plan price; subscription status follows churn).

**Quality checks run as SQL on the stored tables**, not on the Python objects, so they verify what is really in MySQL: row counts, empty values, uniqueness, foreign-key integrity (`LEFT JOIN ... WHERE parent IS NULL`), ranges, allowed values and date ordering. Failures include sample ids. The "damage a few rows" option corrupts a handful of rows on purpose to prove the checks catch real problems.

**No FOREIGN KEY / UNIQUE constraints on generated tables, on purpose.** The quality engine is the thing that verifies integrity, and datasets are exported to systems that may not enforce constraints. (The app's own `runs` table is managed by Alembic.)

**Runs are isolated.** Each run gets its own tables (`r12_customers`, ...) and can be deleted independently.

**Speed.** Rows are generated in memory (about 300k rows in ~2 seconds on the dev machine) and inserted in batches of 5,000 with `executemany`. Per-table and total row caps (`MAX_ROWS_PER_TABLE`, `MAX_TOTAL_ROWS`) keep memory bounded.

## API

| | |
|---|---|
| `GET /api/templates` | built-in schemas |
| `POST /api/schema/validate` | validate a schema and get its table graph |
| `POST /api/runs` | start a run (`config_yaml`, optional `seed`, `inject_defects`) |
| `GET /api/runs`, `GET /api/runs/{id}` | history, status and progress |
| `GET /api/runs/{id}/quality` | quality report |
| `GET /api/runs/{id}/tables/{table}` | paged preview |
| `GET /api/runs/{id}/tables/{table}/csv`, `/dump.sql` | exports |
| `GET /api/mock/{id}`, `/{table}`, `/{table}/{item_id}` | the dataset as a REST API, filter by any column |
| `DELETE /api/runs/{id}` | drop a run and its tables |

## Known limits

- Data is generated in memory, so very large runs are capped (default 200k rows per table, 500k total).
- Foreign keys always point at an `id` column, one hop at a time. Self-references are not supported.
- Background runs use FastAPI's in-process background tasks; a production setup would use a job queue.
- There is no authentication.

## Project layout

```
backend/app/engine/       schema parsing, generators, planner, generator loop
backend/app/quality/      SQL data-quality checks
backend/app/services/     run pipeline, table building/loading, exports, defect injection
backend/app/api/          FastAPI routes and models
backend/app/templates/    built-in schemas (saas, ecommerce)
backend/tests/            39 tests
backend/alembic/          migration for the runs table
frontend/                 Next.js + TypeScript UI
docker-compose.yml        MySQL + backend + frontend
```
