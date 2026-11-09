# API Documentation

The running FastAPI service exposes interactive OpenAPI at `/docs` and a generated schema at `/openapi.json`. The list below reflects implemented routes, not a promise of third-party integrations.

## Conventions

- Protected routes accept `Authorization: Bearer <JWT>`. Tokens expire after 30 minutes. Inactive users are denied even if their token has not expired.
- JSON request bodies are Pydantic-validated. Typical responses are `401` (missing/invalid authentication), `403` (role/eligibility denied), `404` (not found or intentionally hidden object), `409` (workflow/duplicate/conflict), `413` (request too large), and `422` (invalid input).
- Paginated endpoints expose `skip`/`limit` where implemented. Limits are capped by endpoint validation.
- Error responses do not include stack traces. Unexpected server errors are logged and returned as a generic `500`.
- File upload endpoints accept PDF, PNG, and JPEG only, enforce signatures and size bounds, and do not expose stored paths.

## Authentication and account management

| Method | Path | Access |
|---|---|---|
| `POST` | `/auth/register` | Public; only investor/property-owner registration roles are accepted. |
| `POST` | `/auth/login` | Public; IP-based failed-login throttle. |
| `GET` | `/auth/me` | Authenticated account profile. |
| `GET` | `/admin/users` | Super administrator. |
| `PATCH` | `/admin/users/{user_id}/role` | Super administrator. |
| `PATCH` | `/admin/users/{user_id}/status` | Super administrator; activates/suspends account. |
| `GET` | `/admin/users/audit-events` | Super administrator. |

## Property registration and verification

| Method | Path | Access |
|---|---|---|
| `GET`, `POST` | `/assets/` | Authenticated property owner/investor; list own assets or create a draft. |
| `GET` | `/assets/{asset_id}` | Authenticated, object-scoped property access. |
| `POST` | `/assets/{asset_id}/documents` | Owner of a draft/returned property. |
| `GET` | `/assets/{asset_id}/documents` | Authorized property participants. |
| `GET` | `/assets/documents/{document_id}/download` | Owner/verifier/authorized workflow reviewer as defined by the route. |
| `POST` | `/assets/{asset_id}/submit` | Property owner. |
| `GET` | `/admin/assets/pending` | Property verifier/authorized administrator. |
| `GET` | `/admin/assets/{asset_id}` | Property verifier/authorized administrator. |
| `POST` | `/admin/assets/{asset_id}/approve` | Property verifier; self-review is blocked. |
| `POST` | `/admin/assets/{asset_id}/reject` | Property verifier; self-review is blocked. |
| `POST` | `/admin/assets/{asset_id}/request-documents` | Property verifier. |
| `GET` | `/admin/assets/{asset_id}/history` | Property verifier/authorized administrator. |
| `GET` | `/assets/admin/all` | Super administrator. |
| `POST` | `/assets/admin/{asset_id}/approve` | Legacy administrator review; owner self-approval is blocked. |
| `POST` | `/assets/admin/{asset_id}/reject` | Legacy administrator review; owner self-rejection is blocked. |

## Valuation, legal, compliance, and staged approvals

| Method | Path | Access |
|---|---|---|
| `GET` | `/workflow/valuations/pending` | Property valuer. |
| `GET` | `/workflow/valuations/history` | Property valuer or super administrator. |
| `GET` | `/workflow/valuations/review-queue` | Super administrator. |
| `POST` | `/workflow/properties/{asset_id}/valuations` | Property valuer; supporting report required. |
| `GET` | `/workflow/properties/{asset_id}/valuations` | Authorized property participants/reviewers. |
| `POST` | `/workflow/valuations/{valuation_id}/decision` | Independent authorized reviewer. |
| `GET` | `/workflow/legal/pending` | Legal advisor. |
| `GET` | `/workflow/properties/{asset_id}/review-details` | Legal advisor/authorized reviewer. |
| `POST` | `/workflow/properties/{asset_id}/legal-reviews` | Legal advisor. |
| `POST` | `/workflow/properties/{asset_id}/documents` | Role-matched valuer, legal advisor, tokenisation officer, or administrator; document type is checked against role. |
| `GET` | `/workflow/documents/{document_id}/download` | Authorized reviewer based on document/property access. |
| `GET` | `/workflow/compliance/me` | Current investor/owner. |
| `GET` | `/workflow/compliance/users` | Compliance officer. |
| `GET` | `/workflow/compliance/users/{user_id}/history` | Compliance officer/authorized administrator. |
| `POST` | `/workflow/compliance/users/{user_id}/decision` | Compliance officer. |
| `GET` | `/workflow/approvals` | Authorized tokenisation workflow participants. |
| `GET` | `/workflow/properties/{asset_id}/readiness` | Authorized property/workflow participants. |
| `POST` | `/workflow/properties/{asset_id}/proposals` | Tokenisation officer. |
| `POST` | `/workflow/proposals/{proposal_id}/decision` | Independent proposal reviewer. |
| `POST` | `/workflow/properties/{asset_id}/final-authorization` | Final authorizer; preceding gates and separation of duties are enforced. |

## Issuance, marketplace, investment, and portfolio

| Method | Path | Access |
|---|---|---|
| `POST` | `/admin/token-issuances/{asset_id}` | Tokenisation officer after all mandatory approvals. |
| `GET` | `/marketplace/opportunities` | Public approved listings; supports search/location/type and pagination filters. |
| `POST` | `/marketplace/purchases` | Authenticated, eligible investor; requires idempotency key. This is a demo allocation, not payment processing. |
| `GET` | `/tokens/holdings` | Authenticated investor. |
| `GET` | `/tokens/portfolio` | Authenticated investor. |
| `GET` | `/tokens/transactions` | Authenticated investor; own transaction history. |
| `GET` | `/tokens/investors` | Eligible investor; eligible recipient list. |
| `POST` | `/tokens/transfers` | Eligible investor; requires positive amount, eligible recipient, and idempotency key. |
| `GET` | `/properties/{asset_id}/token-distribution` | Owner of the property. |
| `GET` | `/admin/token-transactions` | Super administrator. |

## Property management, notifications, and integrity

| Method | Path | Access |
|---|---|---|
| `GET`, `POST` | `/admin/properties/{asset_id}/managers` | Super administrator; view/assign managers. |
| `GET` | `/property-management/properties` | Property manager; active assignments only. |
| `GET`, `POST` | `/property-management/properties/{asset_id}/records` | Assigned property manager. |
| `POST` | `/property-management/properties/{asset_id}/documents` | Assigned property manager. |
| `GET` | `/property-management/documents/{document_id}/download` | Manager with active assignment to the document's property. |
| `GET` | `/notifications` | Authenticated user; own notifications. |
| `POST` | `/notifications/{notification_id}/read` | Owner of the notification. |
| `GET` | `/admin/ledger/verify` | Super administrator/auditor; verifies hash chains. |
| `GET` | `/admin/ledger/audit-events` | Super administrator/auditor; paginated read-only events. |
| `GET` | `/health` | Health probe; includes database connectivity. |

## Integration truth

The API does not provide payment settlement, external KYC/AML verification, email/SMS delivery, or public-chain transactions. Related workflow records are stored in the application database, and responses explicitly identify demonstration allocations and absent blockchain hashes.
