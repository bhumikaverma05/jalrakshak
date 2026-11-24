# JalRakshak REST API

The versioned API is served at `/api/v1`. Interactive Swagger UI is at `/docs`; the OpenAPI document is at `/openapi.json`. Swagger supports the configured OAuth2 password form and JWT Bearer security scheme.

## Authentication

See [authentication and authorization](./authentication.md) for password rules, JWT configuration, role dependencies, and curl examples.

| Method | Path | Access | Result |
| --- | --- | --- | --- |
| POST | `/api/v1/auth/register` | Public | Create a citizen account; returns a safe profile (`201`) |
| POST | `/api/v1/auth/login` | Public | OAuth2 form fields `username` (email) and `password`; returns bearer token and profile |
| GET | `/api/v1/auth/me` | Bearer token | Return the active user's safe profile |
| GET | `/api/v1/water-bodies` | Public read | Paginated water-body collection |
| GET | `/api/v1/water-bodies/{water_body_id}` | Public read | One water body, or `404` |

The existing health checks remain at `/healthz`, `/api/v1/health`, and `/api/v1/health/database`.

## Water-body collection

`GET /api/v1/water-bodies?page=1&page_size=20` returns `{ "items": [], "total": 0, "page": 1, "page_size": 20 }` when the registry is empty. `page` starts at 1; `page_size` is limited to 1–100. Ordering is stable by name and ID. Each item contains its ID, code, name, type, village, district, state, description, area, responsible authority, status, and spatial values. `location` is GeoJSON Point; `boundary` is GeoJSON MultiPolygon or explicit `null` when no boundary is stored.

```powershell
curl.exe "http://127.0.0.1:8000/api/v1/water-bodies?page=1&page_size=20"
curl.exe "http://127.0.0.1:8000/api/v1/water-bodies/<water_body_uuid>"
```

Invalid UUIDs or pagination parameters return `422`; unknown valid UUIDs return `404`. Database failures return a generic `503` without SQL details. The implementation selects spatial GeoJSON in the same query as record metadata and does not invent missing geometry or seed registry records.

## Citizen reports

Reports are served at `/api/v1/reports`. Submission requires an authenticated citizen. A caller cannot choose `reporter_id` or initial status; the API records the caller and starts reports as `submitted`.

| Method | Path | Access | Result |
| --- | --- | --- | --- |
| POST | `/api/v1/reports` | Citizen | Submit a report; `201`, or `409` for a recent same-category nearby report |
| GET | `/api/v1/reports` | Citizen, officer, engineer, administrator | Citizen sees own reports; staff can list all; supports `page`, `page_size`, `status`, and `water_body_id` filters |
| GET | `/api/v1/reports/{report_id}` | Authenticated | Citizen sees own report; staff can read reports |
| PATCH | `/api/v1/reports/{report_id}` | Officer, engineer, administrator | Set status, assignee, or water-body association |
| GET | `/api/v1/reports/{report_id}/audit` | Officer, engineer, administrator | Return report audit history |
| POST | `/api/v1/reports/{report_id}/evidence` | Report owner or staff | Upload JPEG, PNG, or WebP photo evidence as multipart form data |
| GET | `/api/v1/reports/{report_id}/evidence/{evidence_id}` | Report owner or staff | Download a private report evidence file |

Category values are `garbage_dumping`, `plastic_pollution`, `unusual_colour`, `foul_smell`, `encroachment`, and `other`. Report locations use GeoJSON Point coordinates in `[longitude, latitude]` WGS84 order. `water_body_id` is optional.

The duplicate rule defaults to a 100 metre radius, a 24 hour lookback, and exact category match. Configure it with `REPORT_DUPLICATE_RADIUS_M` and `REPORT_DUPLICATE_WINDOW_HOURS`. Rejected reports do not block a new submission. A duplicate attempt returns a generic `409` and is audit logged.

Evidence uploads are size limited by `EVIDENCE_MAX_SIZE_BYTES` (default 10 MB), decoded and re-encoded to remove embedded image metadata, stored under the private `EVIDENCE_STORAGE_DIR` (default `uploads/reports`), and addressed through authenticated download routes. If photo GPS is omitted, the report location is stored as the evidence GPS location. `captured_at` is optional; `uploaded_at` is server generated.

Allowed workflow transitions are `submitted → under_review` or `rejected`, `under_review → verified` or `rejected`, and `verified → resolved`. Assignment uses `assigned_to` and requires an active officer or engineer. Report creation, duplicate detection, evidence upload, assignment/association changes, and status changes write audit rows in the same database transaction.

The Alembic revision `20261124_0002` converts legacy `assigned` reports to `under_review` while preserving `assigned_to`, then updates `ck_citizen_reports_status_valid` to allow only the five workflow statuses above. Apply the migration before enabling the `verified` transition in an environment still at the prior schema revision.

## OpenAPI schemas

Request and response models are defined in the backend domain modules and appear in `/openapi.json`. Authenticated operations declare the `JWT Bearer` OAuth2 scheme and reference the login token URL. Password hashes are not part of any response schema.

## Local API startup

Use the commands in the [backend setup guide](../backend/README.md). The backend connects using `DATABASE_URL`; integration tests are restricted to `jalrakshak_test` through host port `5433`.
