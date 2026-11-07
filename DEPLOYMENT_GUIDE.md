# Deployment Guide

The supplied Compose file is a safer demonstration deployment, not a complete production platform. Obtain security, operational, legal, and regulatory review before handling real assets or funds.

## Configuration and launch

Start from `.env.example`. Copy it to `.env` only when there is no existing `.env`; otherwise merge the missing entries without replacing current values. Replace all `replace_*` values. Required settings include:

- `DB_USER`, `DB_PASSWORD`, `DB_NAME`, and `DB_HOST` (`database` inside Compose).
- `JWT_SECRET_KEY`: unique, random, at least 32 bytes; rotate using an operational plan that accounts for invalidating existing JWTs.
- `CORS_ORIGINS`: comma-separated, exact browser origins; wildcard origins are rejected.
- `VITE_API_URL`: public API URL embedded in the frontend build.
- `APP_BIND_ADDRESS`, `FRONTEND_PORT`, and `BACKEND_PORT`: defaults bind to localhost.

Commands:

```powershell
docker compose config --quiet
docker compose up --build -d
docker compose ps
docker compose logs -f backend
docker compose exec backend alembic current
```

The backend runs `alembic upgrade head` before serving. To apply migrations as an explicit maintenance step, stop the backend service, run `docker compose run --rm backend alembic upgrade head`, then start it again. The backend container runs as non-root; a small initialization service fixes ownership/mode of the existing document-volume root without deleting files.

The frontend is built into static assets and served by Nginx. The API runs Uvicorn without development reload. PostgreSQL is private to the Compose network and is not published to a host port. `/health` executes a database probe and returns `503` if unavailable; the database also has its own `pg_isready` health check.

## Production environment

- Terminate TLS at a maintained reverse proxy/load balancer. Configure `VITE_API_URL` and `CORS_ORIGINS` for the public HTTPS origins, then rebuild the frontend.
- Keep PostgreSQL private; use a managed secret store, unique strong database credentials, least-privilege database users, network policy, encrypted backups, tested restoration, patching, and monitoring.
- If binding the Compose ports beyond localhost, restrict access with firewall/security-group rules and a reverse proxy. Do not trust unvalidated forwarded IP headers.
- `JWT_SECRET_KEY` and database passwords are container environment variables. Protect Docker daemon access, host access, deployment logs, backups, and CI logs. Do not pass real secrets as image build arguments.
- Persist `/data/property_documents` and PostgreSQL volumes. Test backup/restore before upgrades. Never run `docker compose down -v` for routine shutdown.
- Review CORS, token storage/XSS risk, rate limiting, request limits, database credentials, document malware scanning/retention, audit access, and incident response before production.

## Health, logging, and troubleshooting

The API logs through Python logging to stdout/stderr; inspect with `docker compose logs`. Generic server errors are returned to clients while stack traces remain in server logs. Do not log request bodies, passwords, bearer tokens, or sensitive documents. Configure log collection, retention, redaction, alerting, and metrics externally.

If Compose reports missing configuration, merge required keys from `.env.example` into `.env` and replace placeholders. Do not overwrite or print existing secrets. If migration reports duplicate property registration references, resolve the duplicate records after review and back up the database before retrying; the migration does not delete data.

