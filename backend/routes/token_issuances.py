import json
from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models.asset import Asset
from models.investor_compliance import InvestorCompliance
from models.legal_review import LegalReview
from models.property_valuation import PropertyValuation
from models.property_verification import PropertyVerification
from models.token_holding import TokenHolding
from models.notification import Notification
from models.token_issuance import TokenIssuance
from models.token_transaction import TokenTransaction
from models.tokenization_proposal import TokenizationProposal
from models.user import User
from schemas.token import TokenIssuanceCreate
from services.authorization import require_roles
from services.tokenization_workflow import APPROVAL_STAGES, latest_approval
from services.audit import record_audit_event
from services.ledger import stamp_transaction


router = APIRouter(
    prefix="/admin/token-issuances",
    tags=["Administrator - Token Issuance"],
)

require_issuer = require_roles("tokenization_officer", "super_admin")


def _latest_approved_valuation(db: Session, asset_id: int) -> PropertyValuation | None:
    latest = (
        db.query(PropertyValuation)
        .filter(
            PropertyValuation.asset_id == asset_id,
        )
        .order_by(PropertyValuation.created_at.desc(), PropertyValuation.id.desc())
        .first()
    )
    if (
        latest is None
        or latest.status != "APPROVED"
        or latest.valid_until < date.today()
    ):
        return None
    return latest


@router.post("/{asset_id}", status_code=status.HTTP_201_CREATED)
def issue_tokens(
    asset_id: int,
    issuance_data: TokenIssuanceCreate,
    request: Request,
    db: Session = Depends(get_db),
    officer: User = Depends(require_issuer),
):
    asset = (
        db.query(Asset)
        .filter(Asset.id == asset_id)
        .with_for_update()
        .first()
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    if asset.status != "Verified":
        raise HTTPException(
            status_code=409,
            detail="Only verified properties with completed approval stages can be tokenised.",
        )
    if db.query(TokenIssuance).filter(TokenIssuance.asset_id == asset_id).first():
        raise HTTPException(status_code=409, detail="This property already has a token issuance.")

    valuation = _latest_approved_valuation(db, asset_id)
    if valuation is None:
        raise HTTPException(
            status_code=409,
            detail="A current approved property valuation is required.",
        )
    if issuance_data.currency.upper() != valuation.currency.upper():
        raise HTTPException(
            status_code=422,
            detail="Issuance currency must match the approved valuation.",
        )
    if issuance_data.token_price * issuance_data.total_supply != valuation.amount:
        raise HTTPException(
            status_code=422,
            detail="Token price multiplied by supply must equal the approved valuation.",
        )
    if issuance_data.total_supply.quantize(
        Decimal(1).scaleb(-issuance_data.decimal_precision)
    ) != issuance_data.total_supply:
        raise HTTPException(
            status_code=422,
            detail="Token supply exceeds the configured decimal precision.",
        )
    if (
        issuance_data.maximum_investment is not None
        and issuance_data.maximum_investment < issuance_data.minimum_investment
    ):
        raise HTTPException(
            status_code=422,
            detail="Maximum investment cannot be below minimum investment.",
        )
    if (
        issuance_data.minimum_investment > valuation.amount
        or (
            issuance_data.maximum_investment is not None
            and issuance_data.maximum_investment > valuation.amount
        )
    ):
        raise HTTPException(
            status_code=422,
            detail="Investment limits cannot exceed the approved valuation.",
        )
    if issuance_data.issuance_date < date.today():
        raise HTTPException(status_code=422, detail="Issuance date cannot be in the past.")

    proposal = (
        db.query(TokenizationProposal)
        .filter(TokenizationProposal.asset_id == asset_id)
        .first()
    )
    if proposal is None or proposal.status != "APPROVED":
        raise HTTPException(
            status_code=409,
            detail="An approved tokenisation proposal is required.",
        )
    proposal_fields = (
        "token_name",
        "token_symbol",
        "token_price",
        "total_supply",
        "decimal_precision",
        "currency",
        "minimum_investment",
        "maximum_investment",
        "issuance_date",
        "issuance_terms",
        "restrictions",
        "proposed_tokenisation_arrangements",
        "token_rights_description",
    )
    for field in proposal_fields:
        proposed = getattr(proposal, field)
        submitted = getattr(issuance_data, field)
        if isinstance(proposed, Decimal) and isinstance(submitted, Decimal):
            matches = proposed == submitted
        elif field == "token_symbol":
            matches = proposed == submitted.upper()
        elif field == "currency":
            matches = proposed == submitted.upper()
        else:
            matches = proposed == submitted
        if not matches:
            raise HTTPException(
                status_code=409,
                detail=f"Issuance {field.replace('_', ' ')} must match the approved proposal.",
            )

    verification = (
        db.query(PropertyVerification)
        .filter(
            PropertyVerification.asset_id == asset_id,
            PropertyVerification.decision == "APPROVED",
        )
        .order_by(PropertyVerification.created_at.desc(), PropertyVerification.id.desc())
        .first()
    )
    legal_review = (
        db.query(LegalReview)
        .filter(
            LegalReview.asset_id == asset_id,
            LegalReview.decision == "APPROVED",
        )
        .order_by(LegalReview.created_at.desc(), LegalReview.id.desc())
        .first()
    )
    compliance = (
        db.query(InvestorCompliance)
        .filter(InvestorCompliance.user_id == asset.user_id)
        .first()
    )
    required_conditions = {
        "REGISTRATION": latest_approval(db, asset_id, "REGISTRATION"),
        "PROPERTY_VERIFICATION": latest_approval(
            db, asset_id, "PROPERTY_VERIFICATION"
        ),
        "VALUATION": latest_approval(db, asset_id, "VALUATION"),
        "LEGAL_REVIEW": latest_approval(db, asset_id, "LEGAL_REVIEW"),
        "COMPLIANCE": latest_approval(db, asset_id, "COMPLIANCE"),
        "AGREEMENTS_DISCLOSURES": latest_approval(
            db, asset_id, "AGREEMENTS_DISCLOSURES"
        ),
        "TOKENISATION_PROPOSAL": latest_approval(
            db, asset_id, "TOKENISATION_PROPOSAL"
        ),
        "FINAL_AUTHORIZATION": latest_approval(
            db, asset_id, "FINAL_AUTHORIZATION"
        ),
    }
    incomplete = [
        stage
        for stage in APPROVAL_STAGES
        if required_conditions[stage] is None
        or required_conditions[stage].decision not in {"APPROVED", "COMPLETED"}
    ]
    if (
        verification is None
        or legal_review is None
        or compliance is None
        or not compliance.is_eligible
        or compliance.eligibility_status != "APPROVED"
        or proposal.reviewed_by_user_id is None
        or incomplete
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Mandatory property, verification, valuation, legal, compliance, "
                "agreement, proposal review and final authorisation stages must all be approved."
            ),
        )

    owner = db.query(User).filter(User.id == asset.user_id).first()
    if owner is None or not owner.is_active:
        raise HTTPException(status_code=409, detail="The registered property owner's account is unavailable.")

    approval_references = [
        required_conditions[stage].approval_ref for stage in APPROVAL_STAGES
    ]
    issuance = TokenIssuance(
        asset_id=asset.id,
        valuation_id=valuation.id,
        issued_by_user_id=officer.id,
        token_name=issuance_data.token_name.strip(),
        token_symbol=issuance_data.token_symbol.upper(),
        currency=issuance_data.currency.upper(),
        token_price=issuance_data.token_price,
        total_supply=issuance_data.total_supply,
        decimal_precision=issuance_data.decimal_precision,
        minimum_investment=issuance_data.minimum_investment,
        maximum_investment=issuance_data.maximum_investment,
        issuance_date=issuance_data.issuance_date,
        issuance_terms=issuance_data.issuance_terms.strip(),
        restrictions=issuance_data.restrictions.strip(),
        proposed_tokenisation_arrangements=(
            issuance_data.proposed_tokenisation_arrangements.strip()
        ),
        token_rights_description=issuance_data.token_rights_description.strip(),
        status="ISSUED",
        approval_references=json.dumps(approval_references),
    )
    try:
        db.add(issuance)
        db.flush()
        db.add(
            TokenHolding(
                issuance_id=issuance.id,
                user_id=owner.id,
                balance=issuance_data.total_supply,
            )
        )
        transaction = TokenTransaction(
            transaction_ref=f"NEXA-ISS-{uuid4().hex[:16].upper()}",
            issuance_id=issuance.id,
            from_user_id=None,
            to_user_id=owner.id,
            amount=issuance_data.total_supply,
            transaction_type="ISSUANCE",
            status="COMPLETED",
            payment_status="NOT_APPLICABLE",
            from_balance_before=Decimal("0"),
            from_balance_after=Decimal("0"),
            to_balance_before=Decimal("0"),
            to_balance_after=issuance_data.total_supply,
        )
        stamp_transaction(db, transaction)
        db.add(transaction)
        asset.status = "Tokenised"
        record_audit_event(
            db,
            user=officer,
            action="TOKEN_ISSUANCE_COMPLETED",
            entity_type="token_issuance",
            entity_id=issuance.id,
            request=request,
            new_value={
                "asset_id": asset.id,
                "total_supply": str(issuance.total_supply),
                "token_symbol": issuance.token_symbol,
                "transaction_ref": transaction.transaction_ref,
            },
        )
        db.add(
            Notification(
                user_id=owner.id,
                event_type="TOKEN_ISSUED",
                message=f"{issuance.total_supply} {issuance.token_symbol} were issued for {asset.name}.",
                entity_type="token_issuance",
                entity_id=str(issuance.id),
            )
        )
        db.commit()
        db.refresh(issuance)
        db.refresh(transaction)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Issuance conflicts with an existing property token issuance.",
        ) from error
    except Exception:
        db.rollback()
        raise

    return {
        "message": "Database-backed simulated token issuance recorded; no public blockchain transaction was submitted.",
        "issuance_id": issuance.id,
        "issuance_status": issuance.status,
        "asset_id": asset.id,
        "asset_name": asset.name,
        "valuation_id": valuation.id,
        "issued_by_user_id": officer.id,
        "token_name": issuance.token_name,
        "token_symbol": issuance.token_symbol,
        "currency": issuance.currency,
        "token_price": issuance.token_price,
        "total_supply": issuance.total_supply,
        "decimal_precision": issuance.decimal_precision,
        "minimum_investment": issuance.minimum_investment,
        "maximum_investment": issuance.maximum_investment,
        "issuance_date": issuance.issuance_date,
        "issued_at": issuance.created_at,
        "issuance_terms": issuance.issuance_terms,
        "restrictions": issuance.restrictions,
        "proposed_tokenisation_arrangements": (
            issuance.proposed_tokenisation_arrangements
        ),
        "token_rights_description": issuance.token_rights_description,
        "approval_references": approval_references,
        "allocated_to": {"user_id": owner.id, "full_name": owner.full_name},
        "transaction_ref": transaction.transaction_ref,
        "blockchain_transaction": None,
    }
