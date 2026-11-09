# User Roles and Permissions

All permissions are enforced by the API. Frontend navigation is a usability layer only.

| Role | Responsibilities and principal access |
|---|---|
| Super Admin | Administers accounts/roles/status, reviews valuations and tokenisation proposals, performs final authorisation, assigns property managers, reviews administrative audit/ledger data. Cannot remove the last active super administrator or change/suspend their own account. |
| Property Owner | Registers and submits their own property, uploads supporting documents, receives workflow notifications, and views their own property/token distribution. Cannot approve their own verification. |
| Property Verifier | Reviews submitted property information and evidence, records approval/rejection/requests, and views verification history. Cannot review their own property. |
| Property Valuer | Views verified properties awaiting valuation, uploads valuation reports, enters value/date/methodology, and views valuation history. Approval is separately reviewed. |
| Legal Advisor | Reviews ownership/verification/valuation and proposed arrangements, records jurisdiction requirements, legal risks and explicit token rights, attaches/reviews agreements, and records a legal decision. |
| Compliance Officer | Records manual KYC/AML/identity statuses, required-document checklist, eligibility outcome and review history. These are demo statuses, not external identity checks. |
| Tokenization Officer | Submits tokenisation proposals and records issuance only after all approval gates pass. Cannot skip stages. |
| Investor | Views public approved offerings and their disclosures; eligible investors can record demo purchases, view their own holdings/history, and transfer to eligible recipients. Suspended or ineligible accounts cannot transact. |
| Property Manager | Views only actively assigned properties; records maintenance, rental income, expenses, updates and supporting documents. Cannot edit ownership, token supply or investor balances. |
| Auditor | Read-only access to audit events, token transactions, and hash-chain verification. |

Registration is intentionally limited to investor/property-owner roles. A super administrator must assign operational roles. Role-change operations are audited.

## Sensitive-data boundaries

Passwords are stored as Argon2 hashes. The platform does not collect/store identity document contents or claim real KYC/AML verification. Property documents are private, role/ownership/assignment-scoped, and excluded from marketplace listings. Public property opportunities contain approved investment disclosures, not confidential due-diligence files or owner personal details.

## Separation and business rights

Property verification, valuation review, legal review, compliance approval, proposal review, and final authorisation are distinct gates. Some stages enforce reviewer separation. Token issuance records do not themselves transfer legal ownership; the actual rights are defined by reviewed agreements and applicable law.

