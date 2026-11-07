from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models.audit_event import AuditEvent
from models.token_transaction import TokenTransaction
from models.user import User
from services.authorization import require_roles
from services.ledger import audit_hash_payload, transaction_hash_payload, verify_hash


router = APIRouter(prefix="/admin/ledger", tags=["Audit and Ledger Integrity"])


@router.get("/verify")
def verify_ledger_integrity(
    db: Session = Depends(get_db),
    _auditor: User = Depends(require_roles("super_admin", "auditor")),
):
    audit_count = 0
    audit_failures = []
    previous_audit_hash = None
    for event in db.query(AuditEvent).order_by(AuditEvent.id).yield_per(1000):
        if (
            event.previous_hash != previous_audit_hash
            or not event.event_hash
            or not verify_hash(
                event.previous_hash, audit_hash_payload(event), event.event_hash or ""
            )
        ):
            audit_failures.append(event.event_uuid or str(event.id))
        previous_audit_hash = event.event_hash
        audit_count += 1

    transaction_count = 0
    transaction_failures = []
    previous_by_issuance = defaultdict(lambda: None)
    transactions = (
        db.query(TokenTransaction)
        .order_by(TokenTransaction.issuance_id, TokenTransaction.id)
        .yield_per(1000)
    )
    for transaction in transactions:
        previous_hash = previous_by_issuance[transaction.issuance_id]
        if (
            transaction.previous_hash != previous_hash
            or not transaction.transaction_hash
            or not verify_hash(
                transaction.previous_hash,
                transaction_hash_payload(transaction),
                transaction.transaction_hash or "",
            )
        ):
            transaction_failures.append(transaction.transaction_ref)
        previous_by_issuance[transaction.issuance_id] = transaction.transaction_hash
        transaction_count += 1

    return {
        "integrity": "VALID" if not audit_failures and not transaction_failures else "FAILED",
        "audit_chain": {
            "records_checked": audit_count,
            "failure_count": len(audit_failures),
            "failed_event_references": audit_failures[:100],
        },
        "transaction_chains": {
            "records_checked": transaction_count,
            "failure_count": len(transaction_failures),
            "failed_transaction_references": transaction_failures[:100],
        },
        "limitations": (
            "Hash chaining detects inconsistent records but does not prevent an administrator "
            "with database write access from rewriting the entire chain. This is not "
            "decentralised blockchain consensus."
        ),
    }


@router.get("/audit-events")
def list_audit_events(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    _auditor: User = Depends(require_roles("super_admin", "auditor")),
):
    limit = min(max(limit, 1), 100)
    events = (
        db.query(AuditEvent)
        .order_by(AuditEvent.id.desc())
        .offset(max(skip, 0))
        .limit(limit)
        .all()
    )
    return [
        {
            "event_id": event.event_uuid,
            "user_id": event.user_id,
            "action": event.action,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "previous_hash": event.previous_hash,
            "event_hash": event.event_hash,
            "created_at": event.created_at,
        }
        for event in events
    ]
