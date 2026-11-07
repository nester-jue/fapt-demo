# System Architecture

## Components and trust boundaries

```text
Browser
  ├─ React/Vite production build served by Nginx
  └─ Bearer-token API requests
        │ exact CORS origin
        ▼
FastAPI / Uvicorn
  ├─ Pydantic request/response validation
  ├─ Authentication, RBAC, ownership and assignment checks
  ├─ Workflow, investment, transfer and audit services
  ├─ SQLAlchemy sessions and Alembic migrations
  └─ private property-document filesystem volume
        │ private Compose network
        ▼
PostgreSQL 18
```

The browser is untrusted. Authorization is enforced by backend dependencies and object-scoped database queries; hiding a UI control is not an access control. PostgreSQL and uploaded documents are not published as public host services by the supplied Compose configuration.

## Backend layers

- `routes/` implements HTTP endpoints and composes dependencies.
- `schemas/` validates requests and shapes responses.
- `services/` contains authentication, authorization, property workflow, ledger, audit, and investor eligibility logic.
- `models/` defines persisted SQLAlchemy entities.
- `migrations/versions/` contains additive schema changes.
- `frontend/src/` contains the role-oriented React screens. `VITE_API_URL` is a public build-time API URL, never a secret.

## Authentication and authorization

Passwords are hashed with Argon2 via `pwdlib`. The API issues signed HS256 JWT bearer tokens with a 30-minute expiry. The secret is required at startup and must be at least 32 bytes. The current-user dependency validates signature/expiry, loads the user, and denies inactive accounts. Role checks and owner/assigned-property filters are applied server-side.

Failed login counts are read from persisted audit events for the source IP over a 15-minute window; after ten failures the API returns `429` with `Retry-After`. When deployed behind a proxy, configure trusted client-IP handling at that proxy and avoid trusting arbitrary forwarded headers. This application-level limit is not a substitute for edge/WAF controls against distributed abuse.

The UI currently stores bearer tokens in browser storage. That supports the existing API interaction pattern but exposes tokens to successful same-origin script execution. Production use requires an explicit XSS/CSRF review and secure browser-session strategy.

## Data and document flows

SQL statements use SQLAlchemy-bound parameters. Financial/token operations commit database changes and transaction records together, use idempotency keys, and serialize issuance-level updates. Portfolio balances are calculated from issuance/purchase/transfer records; the holdings table is a cache.

Uploaded PDF, PNG, and JPEG documents are type/signature checked, limited to 10 MiB per file and 11 MiB per declared request, assigned random storage keys, and kept outside the web root. The filesystem directory is owner-only on POSIX systems. Downloads require role, owner, or active property-assignment authorization.

## Deployment and operations

Docker Compose builds a static Nginx frontend and runs the API as a non-root user. PostgreSQL and property documents use named volumes; an initialization service adjusts the existing document-volume directory permissions without deleting stored files. The backend runs Alembic migrations before starting Uvicorn. `/health` performs `SELECT 1` and returns HTTP 503 when the database is unavailable.

Application logs go to container stdout/stderr. Configure collection, redaction, retention, alerting, backups, TLS termination, and firewall rules in the hosting environment. The Compose ports bind to localhost by default; changing that for external access requires a protected reverse proxy and matching `CORS_ORIGINS`/`VITE_API_URL`.

## External integrations not present

No payment processor, KYC/AML service, email/SMS gateway, public blockchain, wallet custody, or decentralized consensus is configured. Related status values and allocation/issuance records are explicitly demonstration/database-backed functionality.

