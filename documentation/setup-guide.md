# Local Setup and Execution

This guide runs the FastAPI and React/Vite applications with a local PostgreSQL/PostGIS database. It does not create seed/demo records. Compose exposes PostGIS on host port `5433` by default so it stays separate from any PostgreSQL service already using `5432`.

## Prerequisites

- Python 3.12 or newer
- Node.js 22.12 or newer and npm
- Docker Desktop with Docker Compose v2
- Git

## Install

From the repository root in PowerShell:

```powershell
Copy-Item .env.example .env
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env
# Change POSTGRES_PASSWORD in .env and use the same password in backend/.env DATABASE_URL.
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install --upgrade pip
backend/.venv/Scripts/python.exe -m pip install -e "backend[dev]"
Set-Location frontend
npm.cmd install
Set-Location ..
```

Set a private local password in both environment files. `.env` files are ignored by Git; `.env.example` files remain tracked. Set a private random `SECRET_KEY` of at least 32 characters in `backend/.env` before using authentication. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"` and keep it out of Git.

## Start PostgreSQL/PostGIS and migrate

Run from the repository root:

```powershell
docker compose up -d db
docker compose ps
Set-Location backend
.venv\Scripts\python.exe -m alembic upgrade head
```

The Compose service uses `postgis/postgis:16-3.4-alpine`, a named persistent volume, environment-provided credentials/port, and a `pg_isready` health check. Never remove the volume for routine shutdown. `docker compose down` stops the service while retaining its data.

Verify PostGIS and migration state:

```powershell
docker compose exec db psql -U jalrakshak -d jalrakshak_db -c "SELECT PostGIS_Full_Version(), PostGIS_Version();"
Set-Location backend
.venv\Scripts\python.exe -m alembic current
```

## Run the applications

In separate terminals from the repository root:

```powershell
Set-Location backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```powershell
Set-Location frontend
npm.cmd run dev
```

Health endpoints: `http://127.0.0.1:8000/healthz`, `http://127.0.0.1:8000/api/v1/health`, and database readiness at `http://127.0.0.1:8000/api/v1/health/database`. The readiness endpoint returns versions and database name, never credentials.

## Test database

Create a dedicated database, separate from development, before integration tests. Never point `TEST_DATABASE_URL` to development or production. The test fixture accepts only `jalrakshak_test` on `localhost:5433`, rejects any other database, host, or port, and applies Alembic migrations to that test database.

```powershell
docker compose exec db createdb -U jalrakshak jalrakshak_test
$env:TEST_DATABASE_URL = "postgresql+psycopg://jalrakshak:<password>@localhost:5433/jalrakshak_test"
Set-Location backend
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check app tests
```

Without `TEST_DATABASE_URL`, PostgreSQL integration tests are skipped; existing API tests still run.

## Backup and restore basics

```powershell
$containerId = docker compose ps -q db
docker compose exec db pg_dump -U jalrakshak -Fc -f /tmp/jalrakshak.dump jalrakshak_db
docker cp "$($containerId):/tmp/jalrakshak.dump" .\jalrakshak.dump
docker cp .\jalrakshak.dump "$($containerId):/tmp/jalrakshak.dump"
docker compose exec db pg_restore -U jalrakshak -d jalrakshak_db /tmp/jalrakshak.dump
```

Restore operations can overwrite database contents. Confirm the target and preserve a backup before restoring. The command above is a local example, not a production backup policy.

## Import verified water-body boundaries later

Do not manufacture boundaries. Obtain authoritative GIS files, retain source/license metadata, validate topology, transform explicitly to WGS84, and load reviewed `MULTIPOLYGON` geometries with SRID 4326. For example, with a verified GeoPackage and GDAL installed:

```powershell
ogr2ogr -f PostgreSQL "PG:host=localhost dbname=jalrakshak_db user=jalrakshak" verified.gpkg water_bodies -nln reviewed_boundaries -t_srs EPSG:4326 -nlt MULTIPOLYGON
```

This imports to a staging table; it does not associate imported shapes with application records. Review provenance, geometry validity, extents, and identifiers before applying approved boundaries.

## Frontend checks

```powershell
Set-Location frontend
npm.cmd run lint
npm.cmd run build
```
