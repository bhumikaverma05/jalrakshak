# JalRakshak Architecture Proposal

**Status:** Approved MVP architecture. The Milestone 3 persistence layer and migrations implement the database portion described below.

## 1. Requirements understood

JalRakshak is a new geospatial monitoring platform for lakes, ponds, wetlands, reservoirs, rivers, and other water bodies. Its 60% MVP should connect water body registration and mapping with preliminary assessments, field observations and evidence, citizen complaints, water quality records, manually managed satellite observation records, role-aware dashboards, and audit history.

The four roles are administrator, officer, citizen, and engineer. Authorization must be enforced by the API. Historical records, verification state, provenance, and distinction between demonstrated/simulated and real measurements must be visible. The MVP must not claim automated satellite analysis, AI detection, IoT feeds, or other future work as implemented.

## 2. Proposed system shape

Use a single repository with two deployable applications and a database:

```text
React/Vite browser client  ── JSON/HTTP ──>  FastAPI modular monolith  ──> PostgreSQL + PostGIS
              │                                      │
              └── Leaflet map                        └── local evidence storage (development)
```

The browser communicates only with the API for application data. FastAPI owns validation, authorization, scoring, workflow transitions, and dashboard aggregation. PostgreSQL is the authoritative store. PostGIS handles water body locations and optional boundaries. Evidence files are stored outside the database; the database stores safe metadata and a storage key/path. Milestone 3 adds SQLAlchemy 2.x, GeoAlchemy2, Alembic, a request session dependency, and a readiness check at `/api/v1/health/database`; startup remains independent of database availability.

## 3. Decisions and rationale

### Modular monolith for the API

Organize FastAPI by business domain, with routers, schemas, services, and persistence models kept separate. One application and one database are simpler to develop and deploy for the MVP while preserving clear boundaries for later extraction if load or team structure requires it. Do not introduce microservices or a message broker before asynchronous workloads exist.

### Keep business rules on the server

The server calculates assessment totals, validates parameter ranges, checks role and ownership rules, applies verification/status transitions, and computes dashboard values from stored records. The client may preview a total for usability, but the API result is authoritative.

### Spatial data uses PostGIS

Store a water body representative location as a `Point` and an optional surveyed boundary as a `MultiPolygon`, both using SRID 4326. Validate geometries and serialize coordinates consistently for Leaflet. A boundary remains absent until supplied and checked; the map must not invent one. Where the blueprint also asks for latitude/longitude fields, treat the spatial point as canonical and expose latitude/longitude in the API representation to avoid competing sources of truth.

### Citizen reports may precede registration

Citizens can submit location-based reports for unregistered sites. Store a required geographic point and optional location description, with a nullable `water_body_id`; support image evidence, administrator review and officer assignment, and later association with a registered water body. Review and association changes should be auditable.

### Provenance is part of the data model

Keep source, creator, timestamps, verification state, and relevant review information on records. Mark synthetic demonstration records and simulated measurements explicitly. Use the three Bhopal examples only as clearly labeled demonstration records with coordinates identified as unverified until checked; never seed fabricated environmental readings as real observations.

### Local file storage behind a service boundary

For development, save uploads under a controlled backend upload root using generated names, validated content type/extension/size, and database metadata. Routes should call a storage service rather than constructing paths. This keeps traversal checks and permissions centralized and permits future object storage without changing domain APIs. The MVP does not need public file hosting or automated image analysis.

### JWT and role-based authorization

Hash passwords with a maintained Argon2 or bcrypt implementation. Issue short-lived JWT access tokens, validate them through shared FastAPI dependencies, and enforce permissions in every protected operation. Public administrator registration is prohibited; first-admin creation must be an explicit local bootstrap command or one-time setup path that cannot silently create a public privilege-escalation route.

### API and frontend boundaries

Expose versioned-under-prefix REST endpoints under `/api`. Use Pydantic request/response contracts and FastAPI OpenAPI docs. Keep Axios calls in a typed-by-convention API client layer and organize the UI by feature. Role-aware navigation improves usability, but is never treated as authorization.

## 4. Proposed repository structure

```text
Jalrakshak/
├── backend/
│   ├── app/
│   │   ├── api/                 # router composition and shared dependencies
│   │   ├── core/                # settings, security, logging, errors
│   │   ├── db/                  # engine, session, base metadata
│   │   ├── domains/
│   │   │   ├── auth/
│   │   │   ├── water_bodies/
│   │   │   ├── assessments/
│   │   │   ├── observations/
│   │   │   ├── evidence/
│   │   │   ├── reports/
│   │   │   ├── water_quality/
│   │   │   ├── satellite/
│   │   │   ├── dashboard/
│   │   │   └── audit/
│   │   ├── main.py
│   │   └── storage/              # upload storage interface and local adapter
│   ├── alembic/
│   ├── tests/
│   ├── uploads/                  # ignored, local development data only
│   ├── pyproject.toml
│   └── .env.example
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── app/                  # router, providers, shell
│   │   ├── components/           # shared controls and layout
│   │   ├── features/             # dashboard, map, records, reports, etc.
│   │   ├── services/             # Axios client and API modules
│   │   ├── hooks/
│   │   ├── utils/
│   │   └── main.jsx
│   ├── tests/
│   ├── package.json
│   └── .env.example
├── documentation/
│   ├── architecture.md
│   ├── database-design.md
│   ├── development-roadmap.md
│   ├── api-documentation.md       # added with API implementation
│   ├── setup-guide.md             # completed as local setup is implemented
│   └── user-workflows.md          # completed alongside the workflows
├── .gitignore
└── README.md
```

The supplied blueprint's separation of frontend, backend, database design, and documentation is retained. Domain modules and app/feature groupings are more explicit to keep a growing MVP understandable. `pyproject.toml` gives Python dependencies and tooling one managed configuration; Alembic owns schema evolution rather than a manually maintained production schema script. A separate database folder is unnecessary when migrations are the executable schema history; schema documentation belongs in `documentation/`.

## 5. Cross-cutting quality requirements

- Keep secrets in environment variables; commit placeholder-only `.env.example` files.
- Use database transactions around multi-record changes and workflow transitions.
- Return safe, consistent API errors and configure development CORS narrowly.
- Record security-relevant changes in audit history without logging credentials or tokens.
- Use migrations for every schema change and a separate test database for tests.
- Keep UI loading, empty, validation, and failure states explicit.
- Use actual API data for dashboard cards and charts; distinguish no data from zero.
- Keep generated uploads, local databases, caches, and credentials out of version control.

## 6. Explicitly deferred

Automated Sentinel imagery retrieval and processing, cloud masking and index calculation, AI-based image/scoring, IoT and live sensor ingestion, predictive analytics, notifications, watershed analysis, production object storage, CI/CD, and cloud deployment are future roadmap items. Interfaces should not pretend these features work in the MVP.
