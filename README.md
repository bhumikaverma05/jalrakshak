# JalRakshak

JalRakshak is a greenfield water body monitoring and intelligence system. It combines geospatial registration, environmental monitoring workflows, and citizen reporting. This repository is independent; no prior project source or data is used.

## Milestone status

Milestones 2 and 3 are implemented and verified. Milestone 4 adds citizen registration, Argon2 password hashing, JWT bearer authentication, reusable role authorization, and read-only paginated water-body APIs over the existing PostgreSQL/PostGIS schema. Start the isolated JalRakshak database on host port 5433 using [the setup guide](documentation/setup-guide.md). Monitoring workflows, frontend integration, and satellite/AI features remain future work.

## Start locally

See the [setup guide](documentation/setup-guide.md), [backend setup](backend/README.md), and [frontend setup](frontend/README.md). Start the backend on port 8000 and the frontend on port 5173 in separate terminals.

## Architecture and plan

- [Architecture](documentation/architecture.md)
- [Database design proposal](documentation/database-design.md)
- [Development roadmap](documentation/development-roadmap.md)
- [REST API](documentation/api-documentation.md)
- [Authentication and authorization](documentation/authentication.md)
