# Property-to-Tokenisation Workflow

This workflow describes the platform's database-backed demonstration. It is not legal advice and does not assert that a token is a deed, security, share, or direct ownership interest.

## 1. Registration and verification

An owner creates a draft with property registry details and required data. A case-insensitive unique database index prevents reusing the same non-empty registry reference. The owner uploads evidence, then submits the property. A verifier independently reviews the property and evidence, approves/rejects it, or requests more documents. Ownership, file access, and self-review are restricted.

## 2. Valuation and legal review

A valuer can submit a dated valuation only for a verified property, with methodology, validity period, and supporting report. A separate reviewer approves or rejects the valuation. A legal advisor reviews ownership, verification outcomes, valuation, jurisdiction requirements, legal risks, agreements, and proposed arrangements. Legal documentation must explicitly define the rights represented by tokens; the application does not equate tokens with land title.

## 3. Compliance and eligibility

A compliance officer records KYC, AML, identity, required-document, and eligibility statuses. This is manual demonstration tracking, not identity verification or sanctions screening. Only eligible active investors can take part in restricted investment and transfer actions.

## 4. Tokenisation proposal and approvals

The tokenisation officer proposes name/symbol, supply/price/precision, currency, investment limits, issuance date, terms, restrictions, disclosures, and rights wording. Reviewers assess the proposal and can approve, reject, request changes, or require additional documents. Final authorisation is recorded only after mandatory gates are complete:

1. Property registration completed.
2. Verification approved.
3. Current valuation approved.
4. Legal review approved.
5. Required compliance approved.
6. Agreements and disclosures recorded.
7. Tokenisation proposal reviewed.
8. Final authorisation recorded.

The API rechecks gates before issuance, prevents duplicate issuance, and records approval references.

## 5. Issuance

An authorised tokenisation officer records the approved token definition in the database. Issuance validates positive supply/price, valuation, completed approvals, and economic consistency. Database transaction records and hash links are created; the API does not submit a blockchain transaction and returns no public-chain hash.

## 6. Marketplace, purchase, and transfer

Only approved, current offerings are listed. Investors can see terms, valuation, available supply, legal disclosures, risks, and eligibility requirements. A purchase validates account status, investor eligibility, restrictions, quantity, limits, and supply; it updates cached holdings and appends a transaction atomically using an idempotency key. The status is clearly `DEMO_ALLOCATED` and payment is `NOT_PROCESSED`: no payment is claimed.

Transfers require eligible active sender and recipient accounts, positive quantity, distinct accounts, sufficient ledger-derived balance, and an unused idempotency key. Failed operations roll back. Portfolio balances and property token distribution are derived from the transaction ledger.

## 7. Ongoing property operations and audit

Super administrators assign property managers. Managers record maintenance, rent, expenses, updates, and maintenance documents only for assigned properties. Important workflows and transactions emit in-app notifications and audit entries. Audit/transaction hash chains can detect modification or chain breaks, but are not database immutability or decentralised consensus.

## Legal ownership and token rights

The relationship among property title, any legal vehicle/contract, and token-holder rights must be defined by qualified counsel for the relevant jurisdiction. A database row, token symbol, token balance, or hash chain does not convey legal ownership. The platform's disclosures must not represent otherwise.

