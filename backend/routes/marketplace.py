from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from database import get_db
from models.asset import Asset
from models.investor_compliance import InvestorCompliance
from models.legal_review import LegalReview
from models.notification import Notification
from models.property_valuation import PropertyValuation
from models.token_holding import TokenHolding
from models.token_issuance import TokenIssuance
from models.token_transaction import TokenTransaction
from models.tokenization_proposal import TokenizationProposal
from models.user import User
from routes.auth import get_current_user
from schemas.marketplace import TokenPurchaseCreate
from services.audit import record_audit_event
from services.investor import is_eligible_investor, require_eligible_investor
from services.ledger import ledger_balance, stamp_transaction


router = APIRouter(tags=["Investor Marketplace"])


@router.get("/marketplace/opportunities")
def list_opportunities(
    search: str | None = Query(default=None, max_length=100),
    location: str | None = Query(default=None, max_length=200),
    property_type: str | None = Query(default=None, max_length=100),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Asset, TokenIssuance, TokenizationProposal)
        .join(TokenIssuance, TokenIssuance.asset_id == Asset.id)
        .join(TokenizationProposal, TokenizationProposal.asset_id == Asset.id)
        .filter(Asset.status == "Tokenised", TokenIssuance.status == "ISSUED")
    )
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            Asset.name.ilike(term)
            | Asset.description.ilike(term)
            | Asset.location.ilike(term)
            | Asset.country.ilike(term)
        )
    if location:
        query = query.filter(Asset.location.ilike(f"%{location.strip()}%"))
    if property_type:
        query = query.filter(Asset.category.ilike(f"%{property_type.strip()}%"))

    opportunities = (
        query.order_by(Asset.id.desc()).offset(skip).limit(limit + 1).all()
    )
    has_more = len(opportunities) > limit
    opportunities = opportunities[:limit]
    results = []
    for asset, issuance, proposal in opportunities:
        valuation = (
            db.query(PropertyValuation)
            .filter(PropertyValuation.asset_id == asset.id)
            .order_by(PropertyValuation.created_at.desc(), PropertyValuation.id.desc())
            .first()
        )
        if (
            valuation is None
            or valuation.id != issuance.valuation_id
            or valuation.status != "APPROVED"
            or valuation.valid_until < date.today()
            or proposal.status != "APPROVED"
        ):
            continue
        available_supply = ledger_balance(db, issuance.id, asset.user_id)
        legal_review = (
            db.query(LegalReview)
            .filter(LegalReview.asset_id == asset.id)
            .order_by(LegalReview.created_at.desc(), LegalReview.id.desc())
            .first()
        )
        compliance = (
            db.query(InvestorCompliance)
            .filter(InvestorCompliance.user_id == asset.user_id)
            .first()
        )
        owner = db.query(User).filter(User.id == asset.user_id).first()
        if (
            legal_review is None
            or legal_review.decision != "APPROVED"
            or compliance is None
            or not compliance.is_eligible
            or compliance.eligibility_status != "APPROVED"
            or compliance.kyc_status != "APPROVED"
            or compliance.aml_status != "APPROVED"
            or compliance.identity_verification_status != "APPROVED"
            or owner is None
            or not owner.is_active
        ):
            continue
        results.append(
            {
                "asset_id": asset.id,
                "asset_code": asset.asset_code,
                "name": asset.name,
                "property_type": asset.category,
                "description": asset.description,
                "location": asset.location,
                "country": asset.country,
                "valuation": {
                    "amount": valuation.amount,
                    "currency": valuation.currency,
                    "valuation_date": valuation.valuation_date,
                    "valid_until": valuation.valid_until,
                },
                "issuance_id": issuance.id,
                "token_name": issuance.token_name,
                "token_symbol": issuance.token_symbol,
                "token_price": issuance.token_price,
                "currency": issuance.currency,
                "total_supply": issuance.total_supply,
                "available_supply": format(
                    available_supply.quantize(Decimal("0.00000001")),
                    "f",
                ),
                "investment_terms": issuance.issuance_terms,
                "minimum_investment": issuance.minimum_investment,
                "maximum_investment": issuance.maximum_investment,
                "restrictions": issuance.restrictions,
                "disclosures": proposal.disclosures,
                "legal_rights": legal_review.token_rights_description,
                "legal_risks": legal_review.legal_risks,
                "eligibility_requirements": (
                    "Active investor account with approved KYC, AML and identity "
                    "eligibility status; additional issuance restrictions apply."
                ),
                "payment_notice": (
                    "Demonstration allocation only. No payment is processed or confirmed."
                ),
            }
        )
    return {"items": results, "skip": skip, "limit": limit, "has_more": has_more}


@router.post("/marketplace/purchases", status_code=status.HTTP_201_CREATED)
def purchase_tokens(
    purchase: TokenPurchaseCreate,
    request: Request,
    db: Session = Depends(get_db),
    investor: User = Depends(get_current_user),
):
    if not require_eligible_investor(db, investor):
        raise HTTPException(
            status_code=403,
            detail="An active account with approved investor eligibility is required.",
        )

    try:
        issuance = (
            db.query(TokenIssuance)
            .filter(TokenIssuance.id == purchase.issuance_id)
            .with_for_update()
            .first()
        )
        if issuance is None or issuance.status != "ISSUED":
            raise HTTPException(status_code=404, detail="Opportunity not found.")

        duplicate = (
            db.query(TokenTransaction)
            .filter(TokenTransaction.idempotency_key == purchase.idempotency_key)
            .first()
        )
        if duplicate:
            if (
                duplicate.transaction_type != "PURCHASE"
                or duplicate.to_user_id != investor.id
                or duplicate.issuance_id != issuance.id
                or duplicate.amount != purchase.quantity
            ):
                raise HTTPException(
                    status_code=409,
                    detail="This idempotency key was already used for a different transaction.",
                )
            db.rollback()
            return JSONResponse(
                status_code=200,
                content=jsonable_encoder(
                    _purchase_confirmation(duplicate, issuance, replayed=True)
                ),
            )

        asset = db.query(Asset).filter(Asset.id == issuance.asset_id).first()
        proposal = (
            db.query(TokenizationProposal)
            .filter(TokenizationProposal.asset_id == issuance.asset_id)
            .first()
        )
        valuation = (
            db.query(PropertyValuation)
            .filter(
                PropertyValuation.id == issuance.valuation_id,
                PropertyValuation.status == "APPROVED",
                PropertyValuation.valid_until >= date.today(),
            )
            .first()
        )
        if (
            asset is None
            or asset.status != "Tokenised"
            or proposal is None
            or proposal.status != "APPROVED"
            or valuation is None
        ):
            raise HTTPException(status_code=409, detail="This opportunity is not currently eligible for investment.")
        if investor.id == asset.user_id:
            raise HTTPException(status_code=403, detail="Property owners cannot purchase their own issuance.")

        seller = (
            db.query(User)
            .filter(User.id == asset.user_id, User.is_active.is_(True))
            .first()
        )
        if seller is None or not is_eligible_investor(db, seller.id):
            raise HTTPException(status_code=409, detail="The investment offering is unavailable.")

        step = Decimal(1).scaleb(-issuance.decimal_precision)
        if purchase.quantity.quantize(step) != purchase.quantity:
            raise HTTPException(status_code=422, detail="Purchase quantity exceeds token precision.")
        purchase_value = purchase.quantity * issuance.token_price
        if purchase_value < issuance.minimum_investment:
            raise HTTPException(status_code=422, detail="Purchase value is below the minimum investment.")
        if (
            issuance.maximum_investment is not None
            and purchase_value > issuance.maximum_investment
        ):
            raise HTTPException(status_code=422, detail="Purchase value exceeds the maximum investment.")

        seller_holding = (
            db.query(TokenHolding)
            .filter(
                TokenHolding.issuance_id == issuance.id,
                TokenHolding.user_id == seller.id,
            )
            .with_for_update()
            .first()
        )
        seller_balance = ledger_balance(db, issuance.id, seller.id)
        if seller_balance < purchase.quantity:
            raise HTTPException(status_code=409, detail="Insufficient available token supply.")
        if seller_holding is None:
            seller_holding = TokenHolding(
                issuance_id=issuance.id,
                user_id=seller.id,
                balance=seller_balance,
            )
            db.add(seller_holding)
            db.flush()
        buyer_holding = (
            db.query(TokenHolding)
            .filter(
                TokenHolding.issuance_id == issuance.id,
                TokenHolding.user_id == investor.id,
            )
            .with_for_update()
            .first()
        )
        if buyer_holding is None:
            buyer_holding = TokenHolding(
                issuance_id=issuance.id, user_id=investor.id, balance=Decimal("0")
            )
            db.add(buyer_holding)
            db.flush()

        seller_before = seller_balance
        buyer_before = ledger_balance(db, issuance.id, investor.id)
        seller_holding.balance = seller_balance
        buyer_holding.balance = buyer_before
        seller_holding.balance -= purchase.quantity
        buyer_holding.balance += purchase.quantity
        transaction = TokenTransaction(
            transaction_ref=f"NEXA-BUY-{uuid4().hex[:16].upper()}",
            issuance_id=issuance.id,
            from_user_id=seller.id,
            to_user_id=investor.id,
            amount=purchase.quantity,
            transaction_type="PURCHASE",
            status="DEMO_ALLOCATED",
            payment_status="NOT_PROCESSED",
            purchase_value=purchase_value,
            currency=issuance.currency,
            idempotency_key=purchase.idempotency_key,
            from_balance_before=seller_before,
            from_balance_after=seller_holding.balance,
            to_balance_before=buyer_before,
            to_balance_after=buyer_holding.balance,
        )
        stamp_transaction(db, transaction)
        db.add(transaction)
        record_audit_event(
            db,
            user=investor,
            action="TOKEN_PURCHASE_DEMO_ALLOCATED",
            entity_type="token_issuance",
            entity_id=issuance.id,
            request=request,
            new_value={
                "quantity": str(purchase.quantity),
                "purchase_value": str(purchase_value),
                "payment_status": "NOT_PROCESSED",
                "transaction_ref": transaction.transaction_ref,
            },
        )
        db.add_all(
            [
                Notification(
                    user_id=investor.id,
                    event_type="INVESTMENT_DEMO_ALLOCATED",
                    message=(
                        f"Demonstration allocation: {purchase.quantity} {issuance.token_symbol} "
                        f"for {issuance.currency} {purchase_value}. No payment was processed."
                    ),
                    entity_type="token_transaction",
                    entity_id=transaction.transaction_ref,
                ),
                Notification(
                    user_id=seller.id,
                    event_type="INVESTMENT_DEMO_ALLOCATED",
                    message=f"A demonstration allocation of {purchase.quantity} {issuance.token_symbol} was recorded.",
                    entity_type="token_transaction",
                    entity_id=transaction.transaction_ref,
                ),
            ]
        )
        db.commit()
        db.refresh(transaction)
        return _purchase_confirmation(transaction, issuance, purchase_value=purchase_value)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This purchase was already processed or conflicts with another update.",
        ) from error
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def _purchase_confirmation(
    transaction: TokenTransaction,
    issuance: TokenIssuance,
    *,
    purchase_value: Decimal | None = None,
    replayed: bool = False,
) -> dict:
    value = purchase_value or transaction.amount * issuance.token_price
    return {
        "message": "Demonstration allocation recorded; no payment was processed or confirmed.",
        "transaction_ref": transaction.transaction_ref,
        "issuance_id": issuance.id,
        "quantity": transaction.amount,
        "purchase_value": format(value, "f"),
        "currency": issuance.currency,
        "status": transaction.status,
        "payment_status": transaction.payment_status,
        "idempotent_replay": replayed,
        "blockchain_transaction": None,
    }


@router.get("/properties/{asset_id}/token-distribution")
def property_token_distribution(
    asset_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if asset is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    if current_user.role not in {"super_admin", "admin"} and asset.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Property owner access required.")
    issuance = db.query(TokenIssuance).filter(TokenIssuance.asset_id == asset_id).first()
    if issuance is None:
        return {"asset_id": asset_id, "total_supply": "0", "distribution": []}
    credited = func.coalesce(
        func.sum(
            case(
                (TokenTransaction.to_user_id == User.id, TokenTransaction.amount),
                else_=0,
            )
        ),
        0,
    )
    debited = func.coalesce(
        func.sum(
            case(
                (TokenTransaction.from_user_id == User.id, TokenTransaction.amount),
                else_=0,
            )
        ),
        0,
    )
    distribution_query = (
        db.query(User, credited, debited)
        .join(
            TokenTransaction,
            (TokenTransaction.to_user_id == User.id)
            | (TokenTransaction.from_user_id == User.id),
        )
        .filter(
            TokenTransaction.issuance_id == issuance.id,
            TokenTransaction.status.in_(("COMPLETED", "DEMO_ALLOCATED")),
        )
        .group_by(User.id)
        .order_by(User.full_name)
    )
    total = distribution_query.count()
    holdings = distribution_query.offset(skip).limit(limit).all()
    return {
        "asset_id": asset.id,
        "total_supply": issuance.total_supply,
        "skip": skip,
        "limit": limit,
        "total_holders": total,
        "distribution": [
            {
                "user_id": user.id,
                "investor_name": user.full_name,
                "balance": format(
                    Decimal(str(balance)).quantize(Decimal("0.00000001")), "f"
                ),
            }
            for user, incoming, outgoing in holdings
            if (balance := incoming - outgoing) > 0
        ],
    }
