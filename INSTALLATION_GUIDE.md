# Installation Guide

## Docker Compose (recommended)

1. Install Docker Desktop with Compose.
2. Copy `.env.example` to `.env` only if no `.env` exists. If one already exists, merge keys instead of overwriting it.
3. Replace all placeholder credentials. `JWT_SECRET_KEY` must be a unique random value of at least 32 bytes; `DB_PASSWORD` must be unique. Keep the `.env` file private.
4. Build and start:

   ```powershell
   docker compose up --build -d
   docker compose ps
   ```

5. Use the frontend at `http://localhost:5173`; API health is at `http://localhost:8301/health`. PostgreSQL is available only on the private Compose network.
6. Stop with `docker compose down`, which retains named volumes. Do not add `-v` if data must be retained.

To start only PostgreSQL for local backend development, with the required `.env` configuration in place:

```powershell
docker compose up -d database
docker compose logs database
```

The API connects to this service using `DB_HOST=database` inside Compose.

## Manual backend

Requirements: Python 3.13 (or a compatible Python version), PostgreSQL 18, and a frontend-capable Node.js LTS installation.

In PowerShell, from `backend`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DB_HOST = "127.0.0.1"
$env:DB_PORT = "5432"
$env:DB_USER = "<database-user>"
$env:DB_PASSWORD = "<database-password>"
$env:DB_NAME = "<database-name>"
$env:JWT_SECRET_KEY = "<unique-random-secret-at-least-32-bytes>"
$env:CORS_ORIGINS = "http://localhost:5173"
$env:PROPERTY_DOCUMENTS_DIR = "C:\nexa-data\property_documents"
alembic upgrade head
uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

Alternatively set a SQLAlchemy `DATABASE_URL` instead of the `DB_*` fields. The URL must use the `postgresql+psycopg` driver. The backend fails at startup if database settings or the JWT secret are missing/invalid.

## Manual frontend

From `frontend`, configure the API URL before launching Vite:

```powershell
npm ci
$env:VITE_API_URL = "http://localhost:8001"
npm run dev
```

For a production build:

```powershell
npm run build
```

The `VITE_API_URL` value is public frontend configuration, not a secret. The API's `CORS_ORIGINS` must contain the browser origin exactly.

## Tests and schema

Run backend tests from `backend` with `python -m unittest discover -s tests -v`. Run `alembic check` to detect model/schema drift after configuring the database. Back up existing data before migration. Migration history is additive and the property-reference index migration refuses to continue if it finds duplicate references.
