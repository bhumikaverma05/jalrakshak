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

## OpenAPI schemas

Request and response models are defined in the backend domain modules and appear in `/openapi.json`. Authenticated operations declare the `JWT Bearer` OAuth2 scheme and reference the login token URL. Password hashes are not part of any response schema.

## Local API startup

Use the commands in the [backend setup guide](../backend/README.md). The backend connects using `DATABASE_URL`; integration tests are restricted to `jalrakshak_test` through host port `5433`.
