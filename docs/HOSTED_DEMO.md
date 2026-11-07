# Host the fictional demo

This is a hosted version of the fictional walkthrough, not a production tenant
portal. Everyone with the shared site password can switch roles and modify the
same fictional records. Payments, messaging, and external calendars remain off.

Use a dedicated Linux server with Docker Engine, Docker Compose 2.24.4 or newer,
and enough disk space for the images and database. Point a hostname's DNS A record
to the server (and publish an AAAA record only if IPv6 also works). Allow inbound
TCP 80 and 443. Keep database and application ports closed to the internet.

For a new DigitalOcean Droplet, use Ubuntu 24.04 LTS and SSH-key authentication.
A 4 GB RAM server gives the web build room to complete. Confirm the displayed
monthly price before creating the server. Optional User Data is provided in
[`cloud-init.yaml`](../deploy/hosted-demo/cloud-init.yaml); it installs Docker,
opens SSH/HTTP/HTTPS in the host firewall, and clones the repo into
`/opt/property-management-bot`. Wait for `cloud-init status --wait` after signing
in, then `cd /opt/property-management-bot` and skip the clone command below.
This file is intended for a fresh dedicated server, not an existing host.

Clone the repository on the server and create a private `.env` file:

```sh
git clone https://github.com/tylerxia8/property-management-bot.git
cd property-management-bot
umask 077
python3 - <<'PY'
import base64
import pathlib
import secrets
p = pathlib.Path('.env')
if p.exists():
    raise SystemExit('Existing .env preserved; edit it instead.')
p.write_text('\n'.join([
    'POSTGRES_PASSWORD=' + secrets.token_hex(24),
    'GROK_APP_PASSWORD=' + secrets.token_hex(24),
    'GROK_MIGRATOR_PASSWORD=' + secrets.token_hex(24),
    'SESSION_SECRET=' + secrets.token_hex(32),
    'CONTACT_ENCRYPTION_KEY=' + base64.b64encode(secrets.token_bytes(32)).decode(),
]) + '\n')
PY
```

Generate a password hash interactively. Keep the password in a password manager:

```sh
docker run --rm -it caddy:2.10.2-alpine caddy hash-password
```

Append the following settings to `.env`, replacing the examples. Single quotes
around the hash prevent Compose from interpreting its dollar signs:

```dotenv
DEMO_DOMAIN=demo.example.com
DEMO_USER=presenter
DEMO_PASSWORD_HASH='$2a$14$REPLACE_WITH_THE_GENERATED_HASH'
```

Start the stack:

```sh
docker compose -f compose.demo.yaml -f compose.hosted-demo.yaml config --quiet
docker compose -f compose.demo.yaml -f compose.hosted-demo.yaml up --build -d
docker compose -f compose.demo.yaml -f compose.hosted-demo.yaml ps
```

Caddy obtains and renews HTTPS certificates automatically. The override removes
the direct port 3000 binding and protects every page and API endpoint with the
shared password. Neither the API nor PostgreSQL publishes a host port.

Before sharing the URL, verify an unauthenticated HTTPS request returns 401;
then log in and rehearse all five workflows in [the walkthrough](DEMO_WALKTHROUGH.md).
Check `/v1/health` after logging in. Verify HTTP redirects to HTTPS. Preserve
`.env`, the PostgreSQL volume, and the Caddy volumes across updates. Run the same
Compose command after pulling changes; do not use `down -v` unless intentionally
erasing the demo database and certificates.

The site needs its server running continuously. This setup does not add backups,
per-person access controls, production identity, or live integrations. Use only
fictional data.
