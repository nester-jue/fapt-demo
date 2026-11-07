# NEXA Real Estate Tokenisation Demonstration

NEXA is a database-backed demonstration of a property-to-tokenisation workflow. It combines a React/Vite user interface, a FastAPI API, SQLAlchemy/Alembic persistence, and PostgreSQL. Role-specific screens cover property owners, verifiers, valuers, legal and compliance reviewers, tokenisation officers, investors, property managers, administrators, and auditors.

The application records property review, valuation, legal and compliance decisions, staged tokenisation approval, simulated issuance, demo allocations, transfers, portfolio activity, management records, notifications, and hash-chained audit/transaction records. Tokens in this application are internal database records, not public blockchain transactions or legal title to real estate.

## Quick start with Docker Compose

Requirements: Docker Desktop with the Compose plugin and Python 3 for generating a secret.

1. Copy [.env.example](./.env.example) to `.env` **only if `.env` does not already exist**. If it already exists, merge the missing keys into it without replacing existing values. Keep `.env` private and untracked.
2. Replace the `replace_*` placeholders with a unique database user, password, database name, and a random `JWT_SECRET_KEY` of at least 32 bytes. Set `CORS_ORIGINS` and `VITE_API_URL` to the exact browser origin and API URL for the environment.

   Generate a development signing key in PowerShell:

   ```powershell
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

3. Build and start the application:

   ```powershell
   docker compose up --build -d
   docker compose ps
   ```

4. Open the frontend at [http://localhost:5173](http://localhost:5173/). Check [http://localhost:8301/health](http://localhost:8301/health) for API and database health.
5. View container logs with `docker compose logs -f backend`. Stop without removing stored data with:

   ```powershell
   docker compose down
   ```

Compose binds the frontend and API to localhost by default and does not publish PostgreSQL. It preserves the `fapt_postgres_data` and `fapt_property_documents` named volumes. Do not run `docker compose down -v` if the database or uploaded documents must be retained. See [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) for deployment configuration and data backup cautions.

## Local development and validation

For manual service setup, use a PostgreSQL database and follow [INSTALLATION_GUIDE.md](./INSTALLATION_GUIDE.md). Configure `DATABASE_URL` or the `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME` variables before importing or starting the backend. Apply migrations with `alembic upgrade head`.

Run backend tests from `backend`:

```powershell
python -m unittest discover -s tests -v
```

Build the frontend from `frontend`:

```powershell
npm ci
npm run build
```

The actual test results and known coverage gaps are recorded in [TESTING_REPORT.md](./TESTING_REPORT.md).

## Technical guides

- [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md) — application boundaries and security model.
- [DATABASE_DESIGN.md](./DATABASE_DESIGN.md) — persisted entities, relationships, and migration policy.
- [API_DOCUMENTATION.md](./API_DOCUMENTATION.md) — implemented route inventory and authorization notes.
- [USER_ROLES_AND_PERMISSIONS.md](./USER_ROLES_AND_PERMISSIONS.md) — participant responsibilities and access boundaries.
- [TOKENISATION_WORKFLOW.md](./TOKENISATION_WORKFLOW.md) — property review through issuance and investor activity.
- [INSTALLATION_GUIDE.md](./INSTALLATION_GUIDE.md) — local and Docker setup.
- [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) — production configuration, health, logging, and operations.

## Important limitations

- KYC, AML, and identity checks are manually recorded demonstration statuses. No external identity or screening provider is integrated.
- Purchases record `DEMO_ALLOCATED` / `NOT_PROCESSED`; no payment gateway or settlement is configured.
- Token issuance and transfers are database-backed. No public blockchain, wallet, or consensus integration is configured.
- Token ownership does not automatically transfer legal ownership of the underlying property. Rights depend on the approved legal agreements and jurisdiction-specific structure.
- Audit and transaction hash chains detect inconsistent data but do not prevent an administrator with database write access from rewriting the full database.
- The frontend currently holds short-lived bearer tokens in browser storage. A production deployment should add a reviewed XSS/CSRF strategy, HTTPS, secret rotation, monitoring, backups, and independent legal/security review before handling real assets or funds.

