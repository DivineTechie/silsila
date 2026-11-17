# Production readiness

**In short.** The code is built to run in production once a pilot has been done: the same images, with
`SILSILA_DEMO=0`, run on PostgreSQL across several replicas, sign people in through OpenID Connect (UAE PASS
for families, the provider's staff directory with MFA for counsellors), refuse to start if misconfigured, and
log nothing personal. What is left before live use is not more prototype code. It is the approvals, reviews
and integrations that need a partner: clinical and native-language review, UAE PASS onboarding, the
provider's security review, and the pilot itself. Both lists are below, with how each item was checked.

No patient has used Silsila. "Production-ready after a pilot" means the software side is done and tested; it
does not mean it has been shown to help families. Only the pilot can show that.

## Two modes, one image

| | Demo (`SILSILA_DEMO=1`, default) | Production (`SILSILA_DEMO=0`) |
|---|---|---|
| Data | Fictional families, recreated on every start | Never seeded; nothing fictional |
| Storage | SQLite file, one replica | PostgreSQL (`SILSILA_DATABASE_URL`), any number of replicas |
| Sign-in | One-click demo roles and demo passwords | OIDC only: UAE PASS (families), staff directory with MFA (counsellors); demo password variables must not be set |
| Demo tools (reset, audit tampering, gate injection, guided story) | On | Every demo endpoint returns 404 |
| API docs (`/docs`, `/openapi.json`) | On | Off |
| Start-up check | Warnings only | Refuses to start, listing every problem |

## Built and checked

| Area | What is in place | How it was checked |
|---|---|---|
| Storage for several replicas | PostgreSQL store with a connection pool next to SQLite; the same public interface and the same audit hashes. Schema created idempotently under an advisory lock, so replicas can start together | Contract tests on both backends; 3 stores (as replicas) × 4 threads × 100 audit events end with an intact chain and sequence 1 to 1,200; the whole backend suite (305 tests) passes on PostgreSQL 17 (`backend/tests/test_store_postgres.py`; CI job "Store and API tests on PostgreSQL") |
| Tamper-evident audit across replicas | Each audit write takes a transaction-scoped PostgreSQL advisory lock, reads the chain head and appends; SQLite uses `BEGIN IMMEDIATE` | Concurrency test above; `backend/scripts/verify_audit.py` exits 1 if the chain is broken (for a nightly job) |
| Safe start-up | `check_production()` refuses to start without a 32+ character signing secret, an explicit web origin, a PostgreSQL URL, and with any demo password set | `backend/tests/test_production.py`; container run with a bad configuration exits with all three messages |
| Identity | OIDC authorization-code flow with PKCE, state and nonce in a signed cookie (works across replicas), full ID-token validation against the provider's keys, counsellors limited to an allow-list checked at every sign-in, audit entries for every sign-in. The web app's `/signed-in` page completes the session | 21 tests against a standards-compliant mock provider (`backend/tests/test_oidc.py`). **Not yet tested against UAE PASS or Entra ID**: see [`identity-oidc.md`](identity-oidc.md) |
| Tokens | HS256 with issuer and audience checked, 8-hour lifetime, secret from the environment only in production | `test_production.py` |
| Logging without personal data | One JSON line per request: method, route template (a relative's link token is replaced by `:token`), status, time, request id, a 10-character hash of the client address. No query strings, bodies or Authorization headers. uvicorn's own access log is off in the container because it prints full paths | Tests with log capture; container run shows `/api/r/:token/...` and the token appears 0 times in the logs |
| Request tracing | `X-Request-ID` accepted or generated, returned on every response | Tests; container probe |
| Security headers | API: `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, HSTS in production, `no-store` on authenticated responses. Web: the same set plus `Permissions-Policy` | Container probes of both services |
| Abuse limits | Request body cap (2 MB; returns 413); per-client rate limits on password sign-in (10 a minute) and relatives' links (30 a minute in production) returning 429 with `Retry-After`. These are per replica; a pilot puts Azure Front Door with WAF rate rules in front | `test_production.py` |
| Health probes | `/api/live` (process up), `/api/ready` (database reachable; 503 if not), `/api/health` (unchanged) | Probes in production mode against PostgreSQL |
| Containers | Non-root users in both images, a Docker `HEALTHCHECK`, the seed runs only in demo mode, `SILSILA_WORKERS` for more processes per replica | Container runs: user `silsila`, ready 200 |
| Try production locally | `docker-compose.prod.yml`: PostgreSQL 17, the API in production mode, the web app | Run on 17 Nov 2026: ready 200, docs 404, demo endpoints 404, password sign-in 401, guide answers, audit chain intact on PostgreSQL |
| Continuous integration | Backend tests on SQLite and on PostgreSQL, the benchmark harness, web lint, types and build, and a secret scan of the full history | `.github/workflows/ci.yml` |
| Interoperability | FHIR R4B import of an index result (refused with the reason when unsafe) and export of a case | `backend/tests/test_fhir_import.py`: 22 malformed records and 116 single-field deletions, 0 silent failures |
| Capacity | Measured on the hosted demo (one replica, 2 vCPU, SQLite): 0 errors at 25 clients; 382 link opens a second; about 1.5 full 61-person recalculations a second | [`deployment.md`](deployment.md), [`evidence/load_hosted.json`](evidence/load_hosted.json). Not yet measured with several replicas on PostgreSQL |

## Configuration (production)

| Variable | Required | Purpose |
|---|---|---|
| `SILSILA_DEMO=0` | yes | Production mode |
| `SILSILA_SECRET` | yes | Token and sign-in cookie signing key, 32+ random characters, from Key Vault |
| `SILSILA_CORS` | yes | The web app's origin(s), comma-separated; never `*` |
| `SILSILA_DATABASE_URL` | yes | `postgresql://user:password@host:5432/silsila?sslmode=require` |
| `SILSILA_DB_POOL_MAX` | no | Connections per replica (default 10) |
| `SILSILA_WORKERS` | no | uvicorn worker processes per replica (default 1) |
| `SILSILA_MAX_BODY_BYTES`, `SILSILA_LOGIN_PER_MIN`, `SILSILA_INVITE_PER_MIN` | no | Body cap and rate limits |
| `SILSILA_OIDC_*` | for sign-in | One set per identity provider: see [`identity-oidc.md`](identity-oidc.md) |
| `AZURE_OPENAI_*` | no | Optional triage labels; off unless set (labels only, never replies) |

## Target deployment for a pilot

All in Azure UAE North, so data stays in the UAE:

- Azure Container Apps: the API with two or more replicas and the web app; liveness on `/api/live`,
  readiness on `/api/ready`.
- Azure Database for PostgreSQL (Flexible Server): private network access, encryption at rest, zone-redundant
  high availability, point-in-time restore. A nightly job runs `scripts/verify_audit.py`.
- Azure Key Vault for `SILSILA_SECRET`, the database password and the identity providers' client secrets.
- Azure Front Door with WAF in front of both apps: TLS, rate rules, and blocking by country if required.
- Log Analytics for the JSON access logs and alerts on readiness failures and audit-chain breaks.
- Identity: UAE PASS (families) and the provider's Entra ID tenant with Conditional Access requiring MFA
  (counsellors).
- Index results through the provider's integration engine from Malaffi feeds, mapped to the FHIR import.

`deploy/azure-deploy.sh` deploys the demo today. The production topology above is a plan, not yet deployed.

## Not yet done: what only a pilot partner can provide

| Gate before live use | Why it needs a partner | Owner |
|---|---|---|
| Native-speaking clinical review of all Arabic text and genetic counsellor review of every template | Patient-facing wording must be approved by clinicians; today it is the team's wording and machine translation | Provider's genetics service |
| UAE PASS onboarding and a test against UAE PASS staging | Requires registration with UAE PASS; scopes and claims are theirs | Provider with TDRA |
| Entra ID app registration with MFA by Conditional Access | The provider's tenant | Provider IT |
| ADHICS-aligned security review and a penetration test | Assessed against the provider's controls | Provider security team |
| DoH approval under the AI Risk Management Protocol (risk class High) and the pilot's ethics approval | Regulatory | Provider with DoH |
| Mapping to the real Malaffi or laboratory result profile | No published profile was available to the team | Provider integration team |
| Managed PostgreSQL, Key Vault, Front Door and monitoring in the provider's subscription | Their subscription and network | Provider IT |
| Load test with several replicas on PostgreSQL in that environment | Needs the target environment | Team, during the pilot |
| The pilot: shadow mode beside counsellors, then counsellor-approved invitations | The only way to measure uptake, comprehension and harm | See [`pilot-protocol.md`](pilot-protocol.md) |

Also outside the software: a data-processing agreement, clinical safety case sign-off, and a named clinical
safety officer at the provider.
