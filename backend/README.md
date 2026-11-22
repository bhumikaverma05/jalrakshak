# JalRakshak API

FastAPI service with environment-backed configuration, SQLAlchemy 2.x sessions, GeoAlchemy2 spatial models, Alembic schema history, CORS, and liveness/readiness endpoints. Application startup does not require the database to be online.

## Install and start locally

From the repository root in PowerShell, copy the local examples and configure the same password in root `.env` and `backend/.env`:

```powershell
Copy-Item .env.example .env
Copy-Item backend/.env.example backend/.env
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install --upgrade pip
backend/.venv/Scripts/python.exe -m pip install -e "backend[dev]"
docker compose up -d db
Set-Location backend
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

`GET /healthz` is process liveness. `GET /api/v1/health` checks the API. `GET /api/v1/health/database` verifies PostgreSQL/PostGIS and returns safe version/database metadata.

## Migrations

```powershell
Set-Location backend
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m alembic current
```

The schema starts with migration `20261122_0001_database_foundation.py`. It enables PostGIS and defines the nine MVP tables and indexes in a revision snapshot. Review each migration and back up before applying schema changes to a database containing data.

## Tests and lint

The API regression suite runs without PostgreSQL. Database integration tests require `TEST_DATABASE_URL` set to a disposable database ending in `_test`; they migrate that database and refuse any other database name.

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests
backend/.venv/Scripts/python.exe -m ruff check backend/app backend/tests
```

See [local setup](../documentation/setup-guide.md) and [database architecture](../documentation/database-design.md) for Docker, PostGIS verification, test database creation, backup/restore, and verified GIS import guidance.
