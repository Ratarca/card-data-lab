# Execute Project — How to Run

> Practical guide to running card-data-lab: prerequisites, every taskipy command, what happens under the hood, and troubleshooting.
> The plan behind these commands lives in [EXECUTION_PLAN.md](../EXECUTION_PLAN.md).

---

## 1. Prerequisites

| Tool | Check | Used for |
|---|---|---|
| Docker | `docker ps` | PostgreSQL (OLTP) |
| uv | `uv --version` | Python env + dependency lock |
| Python ≥ 3.12 | handled by uv | runtime |

First-time setup (one command each):

```bash
uv sync          # create .venv + install exact versions from uv.lock
uv run task infra   # start postgres container
```

## 2. Environment variables

Defaults work out of the box; override via env if needed:

| Variable | Default | Meaning |
|---|---|---|
| `PGHOST` | `localhost` | Postgres host |
| `PGPORT` | `5433` | ⚠️ **5433**, not 5432 — host port 5432 is occupied by the Airflow stack's postgres |
| `PGUSER` / `PGPASSWORD` | `cardlab` / `cardlab` | credentials from docker-compose.yml |
| `PGDATABASE` | `cardlab` | database name |

## 3. Taskipy commands reference

Run everything as `uv run task <name>` (defined in `[tool.taskipy.tasks]` in `pyproject.toml`). taskipy just shells out to the command — same behavior on every machine and CI.

### Infrastructure

| Command | What it does |
|---|---|
| `uv run task infra` | `docker compose up -d` → starts `cardlab-postgres` (postgres:16, port **5433**), with healthcheck + persistent volume `pgdata` |
| `uv run task infra-down` | Stops and removes the container (data survives in the named volume; add `-v` manually to wipe) |

### Database

| Command | What it does |
|---|---|
| `uv run task migrate` | Runs `oltp/run_migrations.py`: applies every `.sql` in `oltp/migrations/` in filename order. All DDL is idempotent (`IF NOT EXISTS`), so re-running is safe. Creates the per-context schemas (`client`, `eligibility`, `limits`, `card`, `purchase`, `billing`, `benefits`) + shared `event_outbox`. |

### Application & simulation *(stages 2+; stubs until implemented)*

| Command | What it does |
|---|---|
| `uv run task api` | Starts the FastAPI modular monolith with auto-reload (`services/main.py`). Each bounded context is a module router under `services/modules/`. |
| `uv run task simulate` | Runs the pandas journey generator (`simulator/run.py`): creates N synthetic clients and replays onboarding + purchase journeys through the API. |
| `uv run task lake` | Runs the outbox worker (`worker/outbox_to_duckdb.py`): reads unpublished rows from `event_outbox` and appends them to the DuckDB lake, deduplicating by `event_id`. Marks rows `published_at = now()`. |

### Quality gates

| Command | What it does |
|---|---|
| `uv run task test` | `pytest -q` — full suite in default order (cheap → expensive). DB tests **auto-skip** if Postgres is unreachable. |
| `uv run task test-unit` | Only unit tests (`-m unit`, schemas) — no DB needed, <1s. First feedback loop while coding. |
| `uv run task test-fast` | Schemas + database + service tests — skips slow data-generation suites (simulator/lake). The everyday iteration command. |
| `uv run task test-db` | Only the database tests (`tests/test_database.py`) — migrations idempotency, outbox constraints, FK/check enforcement. |
| `uv run task test-all-ordered` | Explicit cheap→expensive order: schemas → database → service → simulator → lake. Use before pushing. |
| `uv run task check` | Gate runner: `test-fast` then `migrate` — the minimum bar before pushing (Gate G0/G1). |
| `uv run task dbt-build` / `dbt-test` | *(stage 4+)* build/test the dbt project against DuckDB. |

### Layered suite strategy (fast iteration)

Tests are tagged with markers so you can run exactly the layer you're working on:

```text
unit  (schemas)          ~1s   no dependencies — run constantly
db    (database/service) ~1s   needs Postgres
slow  (simulator/lake)   ~2s   generates volumes — run before push
```

- Files declare their layer via `pytestmark` (`tests/test_schemas.py` = unit; database/service = db; simulator/lake = db + slow).
- Select by marker: `pytest -m unit`, `pytest -m "db and not slow"`.
- Ordered execution means a failure in an early (cheap) layer stops noise from later layers: fix what fails first.

## 4. Typical workflows

### Daily loop (development)

```bash
uv run task infra        # ensure DB is up
uv run task test         # fast feedback (DB tests skip if DB down)
```

### Full pipeline end-to-end

```bash
uv run task infra
uv run task migrate      # fresh schema
uv run task simulate     # generate events into event_outbox
uv run task lake         # export to duckdb lake
# stage 4+: uv run task dbt-build && uv run task dbt-test
```

### Before opening a PR

```bash
uv run task check        # tests + migrations must pass
```

## 5. Test suite map

| File | Scope | Needs DB? |
|---|---|---|
| `tests/test_schemas.py` | Event catalog completeness (10 types), pydantic validation, envelope fields | No |
| `tests/test_database.py` | Migrations apply cleanly, all tables exist, outbox PK/indexes, FK & CHECK violations rejected, one-purchase-per-authorization rule | Yes (auto-skip) |
| `tests/conftest.py` | Fixtures: session DB connection, outbox truncation, skip logic | — |

The DB-skip mechanism: `conftest.py` probes the connection at import time; if it fails, `@requires_db` marks those tests as skipped. So `task test-fast` never fails just because Docker isn't running.

**Hermeticity rule**: tests must create their own events rather than depend on outbox volume left by other suites — this prevents cross-suite destruction of data (a real bug we hit: one suite's truncate emptied another's fixtures).

## 6. Project layout (what runs where)

```text
pyproject.toml            # deps + taskipy tasks (source of truth for commands)
docker-compose.yml        # postgres:16 @ host port 5433
oltp/
├── migrations/*.sql      # idempotent DDL, applied by migrate
└── run_migrations.py     # migration runner (psycopg2)
services/
├── main.py               # FastAPI app entrypoint (stage 2)
├── shared/
│   ├── events.py         # BaseEvent envelope (ts_event, dt_event, header...)
│   └── catalog.py        # 10 event types + pydantic payload models
simulator/                # pandas journey generator (stage 2B)
worker/                   # outbox → duckdb (stage 3)
warehouse/                # dbt project (stage 4–5)
tests/                    # pytest suite (see §5)
learn-diary/              # study notes (data_modelling.md)
```

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `port is already allocated` on `infra` | Airflow's postgres owns 5432 | Already solved: lab uses **5433**. If you change compose ports, also set `PGPORT`. |
| `Connection refused ... port 5433` right after `infra` | Container still starting | Wait a few seconds or check `docker ps --filter name=cardlab-postgres` until `(healthy)` |
| DB tests skipped in pytest | Postgres down or wrong `PGPORT` | `uv run task infra && uv run task migrate`, re-run tests |
| `Failed to initialize cache at ~/.cache/uv` (sandboxed terminals) | read-only `$HOME/.cache` | prefix commands with `UV_CACHE_DIR=$TMPDIR/uv-cache` |
| Migration fails mid-way | partial DDL | All statements are `IF NOT EXISTS`; fix the SQL and re-run `migrate` |
| Duplicate events after re-running `lake` | worker dedup broken | Stage 3 gate: dedup by `event_id` (PK prevents dupes in OLTP; enforce in DuckDB append) |

## 8. Where to go next

- Stage 2A: implement `services/main.py` + first module router (purchase → authorization → outbox write in one transaction).
- Stage 2B: implement `simulator/run.py` (≥100 clients, ≥1 month).
- Study notes for the modeling work ahead: [data_modelling.md](data_modelling.md).
