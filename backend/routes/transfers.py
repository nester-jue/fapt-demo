from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models.notification import Notification
from models.token_holding import TokenHolding
from models.token_issuance import TokenIssuance
from models.token_transaction import TokenTransaction
from models.user import User
from routes.auth import get_current_user
from schemas.token import TokenTransferCreate
from services.audit import record_audit_event
from services.investor import is_eligible_investor, require_eligible_investor
from services.ledger import ledger_balance, stamp_transaction


router = APIRouter(prefix="/tokens", tags=["Investor Token Transfers"])


def _transfer_confirmation(transaction: TokenTransaction, issuance: TokenIssuance, replayed=False):
    return {
        "message": "Tokens transferred successfully.",
        "transaction_ref": transaction.transaction_ref,
        "issuance_id": issuance.id,
        "token_symbol": issuance.token_symbol,
        "amount": transaction.amount,
        "transaction_type": "TRANSFER",
        "status": transaction.status,
        "idempotent_replay": replayed,
        "blockchain_transaction": None,
    }


@router.get("/investors")
def list_investors(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not require_eligible_investor(db, current_user):
        raise HTTPException(
            status_code=403,
            detail="Approved active investor eligibility is required for token transfers.",
        )
    investors = (
        db.query(User)
        .filter(
            User.role == "investor",
            User.is_active.is_(True),
            User.id != current_user.id,
        )
        .order_by(User.full_name)
        .all()
    )
    return [
        {"id": investor.id, "full_name": investor.full_name}
        for investor in investors
        if is_eligible_investor(db, investor.id)
    ]


@router.post("/transfers", status_code=status.HTTP_201_CREATED)
def transfer_tokens(
    transfer_data: TokenTransferCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not require_eligible_investor(db, current_user):
        raise HTTPException(
            status_code=403,
            detail="Approved active investor eligibility is required for token transfers.",
        )
    if transfer_data.recipient_user_id == current_user.id:
        raise HTTPException(status_code=422, detail="Sender and recipient must be different.")

    try:
        issuance = (
            db.query(TokenIssuance)
            .filter(TokenIssuance.id == transfer_data.issuance_id)
            .with_for_update()
            .first()
        )
        if issuance is None or issuance.status != "ISSUED":
            raise HTTPException(status_code=404, detail="Token issuance not found.")
        if "non-transferable" in issuance.restrictions.casefold():
            raise HTTPException(status_code=403, detail="This issuance restricts token transfers.")

        duplicate = (
            db.query(TokenTransaction)
            .filter(
                TokenTransaction.idempotency_key
                == transfer_data.idempotency_key
            )
            .first()
        )
        if duplicate:
            if (
                duplicate.transaction_type != "TRANSFER"
                or duplicate.from_user_id != current_user.id
                or duplicate.to_user_id != transfer_data.recipient_user_id
                or duplicate.issuance_id != issuance.id
                or duplicate.amount != transfer_data.amount
            ):
                raise HTTPException(
                    status_code=409,
                    detail="This idempotency key was already used for a different transaction.",
                )
            db.rollback()
            return JSONResponse(
                status_code=200,
                content=jsonable_encoder(
                    _transfer_confirmation(duplicate, issuance, replayed=True)
                ),
            )

        recipient = (
            db.query(User)
            .filter(User.id == transfer_data.recipient_user_id)
            .with_for_update()
            .first()
        )
        if recipient is None:
            raise HTTPException(status_code=404, detail="Recipient account not found.")
        if not require_eligible_investor(db, recipient):
            raise HTTPException(
                status_code=403,
                detail="Recipient must have an active account and approved investor eligibility.",
            )

        sender_holding = (
            db.query(TokenHolding)
            .filter(
                TokenHolding.issuance_id == issuance.id,
                TokenHolding.user_id == current_user.id,
            )
            .with_for_update()
            .first()
        )
        sender_balance = ledger_balance(db, issuance.id, current_user.id)
        if sender_balance <= 0:
            raise HTTPException(status_code=409, detail="You do not hold this token.")
        if sender_holding is None:
            sender_holding = TokenHolding(
                issuance_id=issuance.id,
                user_id=current_user.id,
                balance=sender_balance,
            )
            db.add(sender_holding)
            db.flush()
        if sender_balance < transfer_data.amount:
            raise HTTPException(status_code=409, detail="Insufficient available token balance.")

        recipient_holding = (
            db.query(TokenHolding)
            .filter(
                TokenHolding.issuance_id == issuance.id,
                TokenHolding.user_id == recipient.id,
            )
            .with_for_update()
            .first()
        )
        if recipient_holding is None:
            recipient_holding = TokenHolding(
                issuance_id=issuance.id,
                user_id=recipient.id,
                balance=Decimal("0"),
            )
            db.add(recipient_holding)
            db.flush()

        recipient_balance = ledger_balance(db, issuance.id, recipient.id)
        sender_holding.balance = sender_balance - transfer_data.amount
        recipient_holding.balance = recipient_balance + transfer_data.amount
        transaction = TokenTransaction(
            transaction_ref=f"NEXA-TRF-{uuid4().hex[:16].upper()}",
            issuance_id=issuance.id,
            from_user_id=current_user.id,
            to_user_id=recipient.id,
            amount=transfer_data.amount,
            transaction_type="TRANSFER",
            status="COMPLETED",
            payment_status="NOT_APPLICABLE",
            idempotency_key=transfer_data.idempotency_key,
            from_balance_before=sender_balance,
            from_balance_after=sender_holding.balance,
            to_balance_before=recipient_balance,
            to_balance_after=recipient_holding.balance,
        )
        stamp_transaction(db, transaction)
        db.add(transaction)
        record_audit_event(
            db,
            user=current_user,
            action="TOKEN_TRANSFER_COMPLETED",
            entity_type="token_transaction",
            entity_id=transaction.transaction_ref,
            request=request,
            new_value={
                "issuance_id": issuance.id,
                "recipient_user_id": recipient.id,
                "amount": str(transfer_data.amount),
                "transaction_ref": transaction.transaction_ref,
            },
        )
        db.add_all(
            [
                Notification(
                    user_id=current_user.id,
                    event_type="TOKEN_TRANSFER_COMPLETED",
                    message=f"Your transfer of {transfer_data.amount} {issuance.token_symbol} was recorded.",
                    entity_type="token_transaction",
                    entity_id=transaction.transaction_ref,
                ),
                Notification(
                    user_id=recipient.id,
                    event_type="TOKEN_TRANSFER_COMPLETED",
                    message=f"You received {transfer_data.amount} {issuance.token_symbol}.",
                    entity_type="token_transaction",
                    entity_id=transaction.transaction_ref,
                ),
            ]
        )
        db.commit()
        db.refresh(transaction)
        return _transfer_confirmation(transaction, issuance)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This transaction was already processed or conflicts with another update.",
        ) from error
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
