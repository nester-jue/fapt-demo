# Testing and Quality Report

**Run date:** 2026-11-07  
**Backend command:** `python -m unittest discover -s tests -v` (from `backend`)

## Final automated test results

| Result | Count |
|---|---:|
| Tests executed | 34 |
| Passed | 34 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 0 |

**Exact failure messages:** None. The final test run completed with `Ran 34 tests` and `OK`.

The test modules exercise:

- Registration validation, restricted public roles, unique accounts, password hashing/redaction, login success/failure, suspended accounts, expired JWTs, and login throttling.
- Role checks for all ten roles, unauthenticated access, protected purchase/transfer endpoints, auditor read-only access, origin-scoped CORS, request-size rejection, and credential-safe database URL construction.
- Property required fields, case-insensitive duplicate registry references, supported document types/signatures/size, owner/verifier document access, approval/rejection, and self-review restrictions.
- Valuation input and report requirements, approved valuation, legal approval/rejection, compliance approval/rejection, staged issuance gates, invalid/duplicate issuance, and end-to-end approval.
- Eligible/ineligible purchases, non-positive quantities, insufficient supply, idempotent retries, demo payment labeling, transfers, invalid recipients/self-transfer, non-positive/insufficient transfers, rollback behavior, holdings/history, and audit/transaction hash verification/tampering.
- Empty-schema and existing-schema migration behavior, including the normalized unique property reference index.

The suite uses isolated SQLite test databases and temporary document directories. It does not substitute for production PostgreSQL concurrency/load tests, fuzzing, penetration testing, or independent security review.

## Build and deployment checks

- `npm run build` (from `frontend`): passed; Vite produced the production bundle.
- Python AST parse: passed for all 59 backend Python source/test files.
- `docker compose --env-file .env.example config --quiet`: passed.
- Isolated production Compose smoke test: backend healthy, frontend HTTP 200, OpenAPI available, backend ran as UID 10001, migration `d4a9f2c781be` applied, and `alembic check` reported no drift. Its isolated QA volumes were removed afterward; the existing NEXA volumes were not touched.
- Existing NEXA API health: healthy; frontend HTTP 200; live OpenAPI contains 61 paths.
- Existing PostgreSQL database: migration head `d4a9f2c781be`; `alembic check` reports no new operations.
- Existing record counts after migration: 4 users, 2 assets, 2 issuances, and 4 token transactions.

## Warnings and remaining validation

The test environment emits a non-fatal Starlette deprecation warning about its `httpx`-based `TestClient` and the newer `httpx2` option. It did not cause test failures. Dependency versions are pinned; revisit this client warning when upgrading FastAPI/Starlette.

Concurrency safety is implemented with database transactions, issuance row locks, and unique idempotency constraints, but there is no multi-process race/load test in this suite. The failed-login throttle is database-backed by source-IP audit history; edge/WAF protection and trusted-proxy configuration remain deployment responsibilities.

KYC/AML, payment settlement, email/SMS, and public blockchain functionality require external integrations and are not represented as completed services.

