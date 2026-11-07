# Railway fictional demo

Deploy PostgreSQL, `api`, `web`, and `gateway` in one Railway project. Only
`gateway` gets a public HTTPS domain. Its shared password protects every page
and API request. This is a shared fictional-data demo, not a production portal.

Upload each directory as its service root (`railway up --path-as-root`). The
included `railway.toml` files select Docker builds:

| Service | Source directory | Configuration |
| --- | --- | --- |
| api | `apps/api` | `Dockerfile.railway`, private port 8000 |
| web | `apps/web` | `Dockerfile`, private port 3000 |
| gateway | `deploy/railway` | Caddy, public domain targeting port 8080 |

Use Railway PostgreSQL with a persistent volume and no public TCP proxy. The API
bootstrap creates `grok_demo_sample` and restricted application roles. Configure
API variables in Railway; generate independent passwords and never commit them:

```dotenv
APP_ENV=test
DEMO_FIXTURE=sample
API_HOST=::
DEMO_BOOTSTRAP_DATABASE_URL=${{Postgres.DATABASE_URL}}
GROK_APP_PASSWORD=<random alphanumeric password>
GROK_MIGRATOR_PASSWORD=<random alphanumeric password>
DATABASE_URL=postgresql+psycopg://grok_app:<app password>@<postgres private host>:5432/grok_demo_sample
MIGRATION_DATABASE_URL=postgresql+psycopg://grok_migrator:<migrator password>@<postgres private host>:5432/grok_demo_sample
SESSION_SECRET=<at least 32 random characters>
CONTACT_ENCRYPTION_KEY=<base64-encoded 32 random bytes>
PAYMENT_SIMULATOR=unset
MEDIA_SCANNER=unset
STEP_UP_MAX_AGE_SECONDS=0
APPROVAL_TTL_HOURS=0
```

Leave `WEBHOOK_SECRET` unset. The bootstrap refuses environments other than the
test sample, then invokes normal migration and seeding. Never use real data.

Set `API_INTERNAL_ORIGIN=http://api.railway.internal:8000` on `web` before its
build, using the API's actual private hostname. The browser uses same-origin
`/v1` requests. Railway's web start command listens on IPv6 for private networking.

On `gateway`, configure:

```dotenv
PORT=8080
WEB_INTERNAL_ORIGIN=http://web.railway.internal:3000
DEMO_USER=presenter
DEMO_PASSWORD_HASH=<bcrypt hash of the shared demo password>
```

Use the actual web private hostname. Generate the hash with
`docker run --rm -it caddy:2.10.2-alpine caddy hash-password` and keep the password
in a password manager. Railway terminates public HTTPS; Caddy listens internally
on HTTP. Only the gateway should have a public domain.

Before sharing, verify unauthenticated `/` and `/v1/health` requests return 401.
After logging in, check health and rehearse all five workflows in
[the walkthrough](DEMO_WALKTHROUGH.md). Confirm outbound switches remain false,
API and web have no public domains, and PostgreSQL has no public proxy.

Redeploys preserve fictional history; deleting the database volume erases it.
Update role passwords and database URLs together. Rebuild web after changing
its API origin. Monitor Railway usage and spending alerts: running services
incur ongoing charges.

Everyone with the shared password can switch roles. Live banking, payments,
messaging, external calendars, formal screening, and production identity/media
services remain disabled. This setup does not add per-person access controls or
a production backup policy.
