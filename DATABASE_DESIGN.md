# Database Design

PostgreSQL is the persistent operational store. SQLAlchemy models define entities and Alembic applies additive schema changes. The current migration head is `d4a9f2c781be`.

## Entities and relationships

| Entity/table | Purpose and relationships |
|---|---|
| `users` | Account identity, Argon2 password hash, assigned role, active/suspended state, and creation time. Email is unique. |
| `assets` | Property registry and review state; each property belongs to a user. `registration_number_key` stores the normalized registry reference under a unique index. |
| `property_documents` | Document metadata, uploader, MIME type, size, SHA-256, type, and opaque storage key; the file contents are in the private document volume. |
| `property_verifications`, `asset_review_logs` | Verification decisions/history and administrator review history. |
| `property_valuations` | Property, valuer, amount/currency, dates, methodology, report references, and review status. |
| `legal_reviews` | Jurisdiction requirements, proposed arrangements, explicit token-rights language, risks, supporting documents, decision, and reviewer. |
| `investor_compliance`, `compliance_review_history` | KYC/AML/identity demo statuses, eligibility, required-document checklist, and reviewer history. No identity document bytes are stored. |
| `tokenization_proposals`, `tokenization_approvals` | Proposed token structure/disclosures and staged approval decisions, references, users, comments, and documents. |
| `token_issuances` | Token definition, approved valuation, supply, price, precision, terms, restrictions, issuer, and approval references. |
| `token_transactions` | Issuance, purchase, and transfer ledger; users, amount, balances before/after, status, idempotency, and hash links. |
| `token_holdings` | Transactionally updated balance cache. Portfolio and marketplace supply are derived from ledger entries, not trusted as the sole source of truth. |
| `property_manager_assignments`, `property_management_records` | Active manager/property assignment and maintenance, rent, expense, updates, and document references. |
| `notifications` | User-scoped in-app event notifications and read state. |
| `audit_events` | User/action/entity/IP/metadata, previous/new values, and audit hash-chain fields. Failed login events also support the persistent IP rate limit. |

## Integrity and transaction boundaries

- Foreign keys link records to users, properties, issuances, and documents.
- User email, token references, idempotency keys, and the normalized property registration reference are protected by database uniqueness constraints/indexes.
- API schemas validate positive amounts, decimal precision, status enums, bounded strings, and list sizes before business logic.
- Purchase and transfer operations lock the issuance and relevant holdings, derive balances from the transaction ledger, then update cache rows and append transaction/audit/notification records within one database transaction.
- A failed operation rolls back its database writes; uploads remove partially stored files on failures before completing metadata persistence.
- Audit and transaction hashes form integrity chains. These chains reveal modification or broken links but cannot stop a sufficiently privileged database operator from rewriting the full history.

## Migration and data preservation

Migrations are forward/additive. `d4a9f2c781be` checks for existing duplicate registration references before creating its unique expression index; if duplicates are found it fails with an actionable error instead of removing or rewriting records. The live database was checked and had no duplicate references before the constraint was added.

Docker Compose retains the existing PostgreSQL and document named volumes. Normal `docker compose down` preserves both. **Do not use `docker compose down -v`** unless permanent deletion of those volumes and their data is intended. Back up the database before applying schema changes.
