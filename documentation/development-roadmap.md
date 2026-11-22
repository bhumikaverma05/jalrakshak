# Development Roadmap

**Target:** Functional, connected 60% MVP described in the JalRakshak blueprint. Each stage ends with a reviewable result and verification before the next dependent stage begins.

| Stage | Scope | Exit check |
| --- | --- | --- |
| 0. Blueprint and architecture review | Confirm requirements, architecture, folder layout, data decisions, demo-data policy, and MVP boundaries. | Architecture proposal accepted; open decisions are recorded. |
| 1. Project initialization | Initialize Git in this empty project, create React/Vite and FastAPI application skeletons, add environment examples, dependency manifests, lint/format configuration, and setup docs. | Both apps start locally; configuration contains placeholders only; no prior project assets or data. |
| 2. Database foundation | Create a fresh `jalrakshak_db`, verify PostgreSQL/PostGIS availability, implement SQLAlchemy setup and Alembic, migrate the approved MVP schema and add spatial fields/indexes. | Migration on clean DB; PostGIS and spatial indexes verified; database integration suite passes. |
| 3. Backend identity and core records | Implement registration/login/current-user, password hashing/JWT, role dependencies, user admin functions, and water body CRUD/search/filter/pagination. | API tests cover auth, role denial, and CRUD; OpenAPI is accurate. |
| 4. Monitoring workflows | Add assessments and review, field observations and verification, evidence upload, citizen reports and status workflow, water quality records, manually managed satellite records, and audit events. | Domain tests cover validation, permissions, history, uploads, and synthetic/real provenance. |
| 5. Frontend foundation and records | Build responsive app shell, auth and role-aware navigation, water body list/detail/forms, assessment and observation workflows, citizen portal, quality and satellite screens, loading/empty/error states. | Frontend component/workflow checks and API integration checks pass for implemented flows. |
| 6. Dashboard and GIS | Build Leaflet map, marker popups and filters, show only stored locations and valid boundaries, connect data-backed summary/charts and historical views. | Map and dashboard render API records; no fabricated boundaries or metrics; spatial API checks pass. |
| 7. Integration and hardening | Complete end-to-end role workflows, safe error handling, CORS/config review, upload validation, accessibility/responsive pass, docs, and demo seed process. | End-to-end tests cover registration/bootstrap, monitoring, complaint tracking, and role boundaries; run instructions work from a clean setup. |
| 8. MVP acceptance review | Review acceptance checklist, test report, known limitations, progress ledger, and remaining 40% roadmap. | Only verified functionality is marked complete; unresolved items are listed. |

## Proposed first implementation increment

After architecture review, Stage 1 should create only the repository/app skeleton and local development configuration. Database tables, migrations, backend business endpoints, and seed records belong to later gated stages. The 3 Bhopal demonstration locations should be independently checked or visibly tagged as unverified demonstration coordinates before they appear in a map. Do not create fake water-quality readings or claim automated satellite analysis.

## Future 40% work

AI image assessment, automated Sentinel-2 retrieval and processing, cloud masking/index calculations, historical spread analysis and alerts, IoT integration, predictive analytics, advanced GIS/watershed analysis, notifications, production object storage, cloud hosting, CI/CD, backups, monitoring, and performance/security hardening are future capabilities. The MVP should expose no fake controls or success states for them.

## Progress checklist

- [x] Blueprint reviewed; requirements summarized.
- [x] Architecture proposal documented.
- [x] Database architecture proposal documented; no schema implemented.
- [x] Milestones and stage exit checks documented.
- [x] User approved modular monolith, technology stack, and unregistered-location citizen reports.
- [x] Git, frontend and backend skeletons, environment examples, routing, CORS, health checks, and setup documentation created (Milestone 2).
- [x] Milestone 2 verification report reviewed by user; user supplied implementation instruction for Milestone 3.
- [ ] Stage 2 database foundation (schema and test suite implemented; runtime migration verification pending Docker/PostGIS availability).
- [ ] Stages 3–8 implementation, verification, and acceptance.
