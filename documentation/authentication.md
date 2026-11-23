# Authentication and authorization

Milestone 4 adds JWT bearer authentication to the existing FastAPI service. It reuses the `users` table from the Milestone 3 migration; it adds no table or migration.

## Configuration

Copy `backend/.env.example` to `backend/.env` and set a private random `SECRET_KEY` of at least 32 characters. Generate one with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

`JWT_ALGORITHM` is explicitly limited to `HS256`. `ACCESS_TOKEN_EXPIRE_MINUTES` defaults to 30 and can be set from 1 to 1440. Production configuration rejects placeholder database passwords and placeholder or short signing keys. Never commit `.env` or share its key.

## Registration and login

`POST /api/v1/auth/register` accepts an email, full name, and password. Passwords must be 12â€“128 characters, use at least three of lowercase, uppercase, digits, and symbols, and have no leading or trailing spaces. Email is normalized to lowercase and the existing functional unique index prevents case-insensitive duplicates. Public registration always assigns `citizen`; extra role fields are rejected. Trusted provisioning is required for engineer, officer, and administrator accounts.

`POST /api/v1/auth/login` uses OAuth2 form encoding. Put the email in the conventional `username` field and provide `password`. Successful login returns a bearer access token and a safe user profile. Wrong passwords, unknown accounts, and inactive accounts receive the same generic login response. Argon2 hashes are stored; plaintext passwords and hashes are never returned.

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/auth/register `
  -H "Content-Type: application/json" `
  -d '{"email":"citizen@example.com","full_name":"Example Citizen","password":"Strong-Example-Passphrase-2026!"}'

curl.exe -X POST http://127.0.0.1:8000/api/v1/auth/login `
  -H "Content-Type: application/x-www-form-urlencoded" `
  -d "username=citizen%40example.com&password=Strong-Example-Passphrase-2026%21"
```

## Using a token

Send the returned token in `Authorization: Bearer <access_token>`. `GET /api/v1/auth/me` returns the active account profile. Tokens contain the user UUID subject, issue time, and expiry; authorization always reads the current role and active status from PostgreSQL. The API verifies signature, algorithm, required claims, and expiration. There are no refresh tokens in this milestone.

```powershell
curl.exe http://127.0.0.1:8000/api/v1/auth/me `
  -H "Authorization: Bearer <access_token>"
```

## Role checks

Role dependencies are available for citizen, engineer, officer, administrator, and any combination passed to `require_roles`. The database's established role spelling is `administrator` (rather than `admin`). They return 401 for a missing/invalid/inactive identity and 403 when the authenticated user's stored role is not allowed. These dependencies are ready for future protected operations; this milestone does not add an issue workflow or admin mutation endpoint.

| Role | Current access | Future protected operations |
| --- | --- | --- |
| citizen | View water bodies; read own `/auth/me` profile | Own submissions only when a later workflow is implemented |
| engineer | View water bodies | Engineering operations when introduced |
| officer | View water bodies | Officer operations when introduced |
| administrator | View water bodies | Administrator operations when introduced |

## Error handling and boundaries

Validation responses omit submitted values, database exceptions return generic service errors, and login does not reveal whether an email exists. API authorization is enforced by FastAPI dependencies, not by frontend visibility. Account deactivation takes effect immediately for authenticated requests because each token use reloads the user. Access tokens remain bearer credentials until expiry; there is no refresh or revocation list in this milestone.
