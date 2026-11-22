# JalRakshak

JalRakshak is a greenfield water body monitoring and intelligence system. It combines geospatial registration, environmental monitoring workflows, and citizen reporting. This repository is independent; no prior project source or data is used.

## Milestone status

Milestone 2 initialized Git, React/Vite, and FastAPI and passed verification. Milestone 3 adds PostgreSQL/PostGIS models, database sessions, a readiness check, Alembic migrations, and Docker Compose configuration. Start the database using [the setup guide](documentation/setup-guide.md) before using database-backed operations. Authentication workflows and monitoring APIs remain future work. Use placeholder credentials only for local development.

## Start locally

See the [setup guide](documentation/setup-guide.md), [backend setup](backend/README.md), and [frontend setup](frontend/README.md). Start the backend on port 8000 and the frontend on port 5173 in separate terminals.

## Architecture and plan

- [Architecture](documentation/architecture.md)
- [Database design proposal](documentation/database-design.md)
- [Development roadmap](documentation/development-roadmap.md)
