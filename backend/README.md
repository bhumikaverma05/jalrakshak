# JalRakshak API

FastAPI modular monolith with environment-backed configuration, SQLAlchemy 2.x sessions, GeoAlchemy2 spatial models, Alembic schema history, CORS, health endpoints, JWT authentication, role dependencies, and water-body read APIs. Milestone 4 reuses the nine-table Milestone 3 schema and adds no tables or migration.

## Install and start locally

From the repository root in PowerShell:

```powershell
Copy-Item .env.example .env
Copy-Item backend/.env.example backend/.env
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install --upgrade pip
backend/.venv/Scripts/python.exe -m pip install -e "backend[dev]"
python -c "import secrets; print(secrets.token_urlsafe(48))"
# Put the generated private value in backend/.env as SECRET_KEY.
docker compose up -d db
Set-Location backend
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Configure the same local database password in root `.env` and `backend/.env`. Set a private `SECRET_KEY` of at least 32 characters. `JWT_ALGORITHM` is fixed to `HS256`; `ACCESS_TOKEN_EXPIRE_MINUTES` defaults to 30. Never commit `.env` or production secrets.

`GET /healthz` is process liveness. `GET /api/v1/health` checks the API. `GET /api/v1/health/database` verifies PostgreSQL/PostGIS and returns safe database metadata.

## Milestone 4 endpoints

- `POST /api/v1/auth/register` creates citizen accounts only.
- `POST /api/v1/auth/login` accepts form fields `username` (email) and `password`, then returns a JWT bearer token and safe profile.
- `GET /api/v1/auth/me` returns the authenticated user's safe profile.
- `GET /api/v1/water-bodies` and `GET /api/v1/water-bodies/{uuid}` return stored metadata and GeoJSON.

See [API docs](../documentation/api-documentation.md) and [authentication docs](../documentation/authentication.md) for curl examples and role behavior.

## Migrations

```powershell
Set-Location backend
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m alembic current
```

The database schema remains the existing migration `20261122_0001_database_foundation.py`. Milestone 4 uses the existing `users` and `water_bodies` tables.

## Tests, lint, and dependencies

All integration tests use the isolated `jalrakshak_test` database through host port `5433`. The fixture refuses a different database, host, or port and applies Alembic migrations.

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://jalrakshak:<password>@localhost:5433/jalrakshak_test"
$env:DATABASE_URL = $env:TEST_DATABASE_URL
Set-Location backend
.venv\Scripts\python.exe -m pytest -v
.venv\Scripts\python.exe -m ruff check app tests alembic
.venv\Scripts\python.exe -m ruff format --check app tests alembic
.venv\Scripts\python.exe -m pip check
```

See [local setup](../documentation/setup-guide.md) and [database architecture](../documentation/database-design.md) for Docker, PostGIS, test database setup, backup/restore, and verified GIS import guidance.
