import hashlib
import json
from datetime import timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from models.audit_event import AuditEvent
from models.token_transaction import TokenTransaction


def _chain_hash(previous_hash: str | None, payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{previous_hash or ''}\n{canonical}".encode()).hexdigest()


def _decimal_text(value) -> str | None:
    if value is None:
        return None
    return format(Decimal(value).quantize(Decimal("0.00000001")), "f")


def _currency_value_text(value) -> str | None:
    if value is None:
        return None
    return format(Decimal(value).quantize(Decimal("0.0000000000000001")), "f")


def transaction_hash_payload(transaction: TokenTransaction) -> dict:
    return {
        "transaction_ref": transaction.transaction_ref,
        "issuance_id": transaction.issuance_id,
        "from_user_id": transaction.from_user_id,
        "to_user_id": transaction.to_user_id,
        "amount": _decimal_text(transaction.amount),
        "transaction_type": transaction.transaction_type,
        "status": transaction.status,
        "payment_status": transaction.payment_status,
        "purchase_value": _currency_value_text(transaction.purchase_value),
        "currency": transaction.currency,
        "from_balance_before": _decimal_text(transaction.from_balance_before),
        "from_balance_after": _decimal_text(transaction.from_balance_after),
        "to_balance_before": _decimal_text(transaction.to_balance_before),
        "to_balance_after": _decimal_text(transaction.to_balance_after),
    }


def stamp_transaction(db: Session, transaction: TokenTransaction) -> None:
    latest = (
        db.query(TokenTransaction)
        .filter(TokenTransaction.issuance_id == transaction.issuance_id)
        .order_by(TokenTransaction.id.desc())
        .first()
    )
    transaction.previous_hash = latest.transaction_hash if latest else None
    transaction.transaction_hash = _chain_hash(
        transaction.previous_hash, transaction_hash_payload(transaction)
    )


def audit_hash_payload(event: AuditEvent) -> dict:
    created_at = event.created_at
    if created_at and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return {
        "event_uuid": event.event_uuid,
        "user_id": event.user_id,
        "action": event.action,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "previous_value": event.previous_value,
        "new_value": event.new_value,
        "ip_address": event.ip_address,
        "details": event.details,
        "created_at": created_at.astimezone(timezone.utc).isoformat()
        if created_at
        else None,
    }


def stamp_audit_event(db: Session, event: AuditEvent) -> None:
    if db.bind and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(734921804)"))
    latest = db.query(AuditEvent).order_by(AuditEvent.id.desc()).with_for_update().first()
    event.previous_hash = latest.event_hash if latest else None
    event.event_hash = _chain_hash(event.previous_hash, audit_hash_payload(event))


def verify_hash(previous_hash: str | None, payload: dict, expected_hash: str) -> bool:
    return _chain_hash(previous_hash, payload) == expected_hash


def ledger_balance(db: Session, issuance_id: int, user_id: int) -> Decimal:
    credited = func.coalesce(
        func.sum(
            case(
                (TokenTransaction.to_user_id == user_id, TokenTransaction.amount),
                else_=0,
            )
        ),
        0,
    )
    debited = func.coalesce(
        func.sum(
            case(
                (TokenTransaction.from_user_id == user_id, TokenTransaction.amount),
                else_=0,
            )
        ),
        0,
    )
    incoming, outgoing = (
        db.query(credited, debited)
        .filter(
            TokenTransaction.issuance_id == issuance_id,
            TokenTransaction.status.in_(("COMPLETED", "DEMO_ALLOCATED")),
        )
        .one()
    )
    return Decimal(str(incoming)) - Decimal(str(outgoing))
