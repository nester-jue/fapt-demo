from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session, aliased

from database import get_db
from decimal import Decimal
from models.user import User
from models.asset import Asset
from models.token_issuance import TokenIssuance
from models.token_transaction import TokenTransaction
from routes.auth import get_current_user, require_admin


router = APIRouter(tags=["Token Portfolio and Ledger"])


# --------------------------------------------------
# INVESTOR TOKEN HOLDINGS
# --------------------------------------------------

@router.get("/tokens/holdings")
def get_my_holdings(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "investor":
        raise HTTPException(
            status_code=403,
            detail="Investor access required."
        )

    credits = func.coalesce(
        func.sum(
            case(
                (TokenTransaction.to_user_id == current_user.id, TokenTransaction.amount),
                else_=0,
            )
        ),
        0,
    )
    debits = func.coalesce(
        func.sum(
            case(
                (TokenTransaction.from_user_id == current_user.id, TokenTransaction.amount),
                else_=0,
            )
        ),
        0,
    )
    balances = (
        db.query(TokenTransaction.issuance_id, credits, debits)
        .filter(
            (TokenTransaction.from_user_id == current_user.id)
            | (TokenTransaction.to_user_id == current_user.id),
            TokenTransaction.status.in_(("COMPLETED", "DEMO_ALLOCATED")),
        )
        .group_by(TokenTransaction.issuance_id)
        .order_by(TokenTransaction.issuance_id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    holdings = []
    for issuance_id, credited, debited in balances:
        balance = (Decimal(str(credited)) - Decimal(str(debited))).quantize(
            Decimal("0.00000001")
        )
        if balance <= 0:
            continue
        result = (
            db.query(TokenIssuance, Asset)
            .join(Asset, TokenIssuance.asset_id == Asset.id)
            .filter(TokenIssuance.id == issuance_id)
            .first()
        )
        if result:
            issuance, asset = result
            holdings.append((balance, issuance, asset))

    results = []

    for balance, issuance, asset in holdings:
        results.append({
            "issuance_id": issuance.id,
            "asset_id": asset.id,
            "asset_code": asset.asset_code,
            "asset_name": asset.name,
            "token_name": issuance.token_name,
            "token_symbol": issuance.token_symbol,
            "currency": issuance.currency,
            "token_price": issuance.token_price,
            "balance": format(balance, "f"),
            "holding_value": format(
                (balance * issuance.token_price).quantize(Decimal("0.01")), "f"
            ),
            "updated_at": db.query(func.max(TokenTransaction.created_at))
            .filter(
                TokenTransaction.issuance_id == issuance.id,
                (TokenTransaction.from_user_id == current_user.id)
                | (TokenTransaction.to_user_id == current_user.id),
            )
            .scalar()
        })

    return results


@router.get("/tokens/portfolio")
def get_portfolio_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "investor":
        raise HTTPException(status_code=403, detail="Investor access required.")
    holdings = []
    skip = 0
    while True:
        page = get_my_holdings(skip=skip, limit=100, db=db, current_user=current_user)
        holdings.extend(page)
        if len(page) < 100:
            break
        skip += 100
    value_by_currency = {}
    for holding in holdings:
        currency = holding["currency"]
        value_by_currency[currency] = (
            Decimal(value_by_currency.get(currency, "0"))
            + Decimal(holding["holding_value"])
        )
    return {
        "investor": current_user.full_name,
        "account_status": "ACTIVE" if current_user.is_active else "SUSPENDED",
        "total_tokens_held": sum(
            (Decimal(item["balance"]) for item in holdings), start=Decimal("0")
        ).quantize(Decimal("0.00000001")),
        "total_investment_value_by_currency": {
            currency: format(value.quantize(Decimal("0.01")), "f")
            for currency, value in value_by_currency.items()
        },
        "available_balance": sum(
            (Decimal(item["balance"]) for item in holdings), start=Decimal("0")
        ).quantize(Decimal("0.00000001")),
        "restricted_balance": 0,
        "holdings_by_property": holdings,
        "calculation_source": "Token issuance, purchase and transfer ledger records",
    }


# --------------------------------------------------
# INVESTOR TRANSACTION HISTORY
# --------------------------------------------------

@router.get("/tokens/transactions")
def get_my_transactions(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "investor":
        raise HTTPException(
            status_code=403,
            detail="Investor access required."
        )

    sender = aliased(User)
    recipient = aliased(User)

    transactions = (
        db.query(
            TokenTransaction,
            TokenIssuance,
            Asset,
            sender,
            recipient
        )
        .join(
            TokenIssuance,
            TokenTransaction.issuance_id == TokenIssuance.id
        )
        .join(
            Asset,
            TokenIssuance.asset_id == Asset.id
        )
        .outerjoin(
            sender,
            TokenTransaction.from_user_id == sender.id
        )
        .join(
            recipient,
            TokenTransaction.to_user_id == recipient.id
        )
        .filter(
            (TokenTransaction.from_user_id == current_user.id)
            | (TokenTransaction.to_user_id == current_user.id)
        )
        .order_by(TokenTransaction.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    results = []

    for transaction, issuance, asset, from_user, to_user in transactions:
        results.append({
            "transaction_ref": transaction.transaction_ref,
            "transaction_type": transaction.transaction_type,
            "issuance_id": issuance.id,
            "asset_name": asset.name,
            "token_symbol": issuance.token_symbol,
            "amount": transaction.amount,
            "status": transaction.status,
            "payment_status": transaction.payment_status,
            "purchase_value": transaction.purchase_value,
            "currency": transaction.currency,
            "from_balance_before": transaction.from_balance_before,
            "from_balance_after": transaction.from_balance_after,
            "to_balance_before": transaction.to_balance_before,
            "to_balance_after": transaction.to_balance_after,
            "previous_hash": transaction.previous_hash,
            "transaction_hash": transaction.transaction_hash,
            "from_user": (
                {
                    "id": from_user.id,
                    "full_name": from_user.full_name
                }
                if from_user else None
            ),
            "to_user": {
                "id": to_user.id,
                "full_name": to_user.full_name
            },
            "direction": (
                "RECEIVED"
                if transaction.to_user_id == current_user.id
                else "SENT"
            ),
            "created_at": transaction.created_at
        })

    return results


# --------------------------------------------------
# ADMIN COMPLETE TRANSACTION LEDGER
# --------------------------------------------------

@router.get("/admin/token-transactions")
def get_all_token_transactions(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin)
):
    sender = aliased(User)
    recipient = aliased(User)

    transactions = (
        db.query(
            TokenTransaction,
            TokenIssuance,
            Asset,
            sender,
            recipient
        )
        .join(
            TokenIssuance,
            TokenTransaction.issuance_id == TokenIssuance.id
        )
        .join(
            Asset,
            TokenIssuance.asset_id == Asset.id
        )
        .outerjoin(
            sender,
            TokenTransaction.from_user_id == sender.id
        )
        .join(
            recipient,
            TokenTransaction.to_user_id == recipient.id
        )
        .order_by(TokenTransaction.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    results = []

    for transaction, issuance, asset, from_user, to_user in transactions:
        results.append({
            "transaction_ref": transaction.transaction_ref,
            "transaction_type": transaction.transaction_type,
            "issuance_id": issuance.id,
            "asset_name": asset.name,
            "token_symbol": issuance.token_symbol,
            "amount": transaction.amount,
            "status": transaction.status,
            "payment_status": transaction.payment_status,
            "purchase_value": transaction.purchase_value,
            "currency": transaction.currency,
            "from_balance_before": transaction.from_balance_before,
            "from_balance_after": transaction.from_balance_after,
            "to_balance_before": transaction.to_balance_before,
            "to_balance_after": transaction.to_balance_after,
            "previous_hash": transaction.previous_hash,
            "transaction_hash": transaction.transaction_hash,
            "from_user": (
                {
                    "id": from_user.id,
                    "full_name": from_user.full_name
                }
                if from_user else None
            ),
            "to_user": {
                "id": to_user.id,
                "full_name": to_user.full_name
            },
            "created_at": transaction.created_at
        })

    return results