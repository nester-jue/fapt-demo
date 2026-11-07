import json
from uuid import uuid4

from sqlalchemy.orm import Session

from models.tokenization_proposal import TokenizationApproval
from models.user import User
from services.audit import record_audit_event


APPROVAL_STAGES = (
    "REGISTRATION",
    "PROPERTY_VERIFICATION",
    "VALUATION",
    "LEGAL_REVIEW",
    "COMPLIANCE",
    "AGREEMENTS_DISCLOSURES",
    "TOKENISATION_PROPOSAL",
    "FINAL_AUTHORIZATION",
)


def record_approval(
    db: Session,
    *,
    asset_id: int,
    user_id: int,
    stage: str,
    decision: str,
    comments: str,
    supporting_document_ids: list[int] | None = None,
) -> TokenizationApproval:
    approval = TokenizationApproval(
        approval_ref=f"NEXA-APR-{uuid4().hex[:16].upper()}",
        asset_id=asset_id,
        responsible_user_id=user_id,
        stage=stage,
        decision=decision,
        comments=comments,
        supporting_document_ids=json.dumps(supporting_document_ids or []),
    )
    db.add(approval)
    db.flush()
    responsible_user = db.query(User).filter(User.id == user_id).first()
    record_audit_event(
        db,
        user=responsible_user,
        action=f"APPROVAL_{stage}_{decision}",
        entity_type="property",
        entity_id=asset_id,
        new_value={
            "approval_ref": approval.approval_ref,
            "stage": stage,
            "decision": decision,
            "supporting_document_ids": supporting_document_ids or [],
        },
    )
    return approval


def latest_approval(db: Session, asset_id: int, stage: str):
    return (
        db.query(TokenizationApproval)
        .filter(
            TokenizationApproval.asset_id == asset_id,
            TokenizationApproval.stage == stage,
        )
        .order_by(TokenizationApproval.created_at.desc(), TokenizationApproval.id.desc())
        .first()
    )
