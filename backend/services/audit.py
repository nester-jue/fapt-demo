import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Request
from sqlalchemy.orm import Session

from models.audit_event import AuditEvent
from models.asset import Asset
from models.investor_compliance import InvestorCompliance
from models.legal_review import LegalReview
from models.notification import Notification
from models.property_valuation import PropertyValuation
from models.tokenization_proposal import TokenizationProposal
from models.user import User
from services.ledger import stamp_audit_event


def record_audit_event(
    db: Session,
    *,
    user: User | None,
    action: str,
    entity_type: str,
    entity_id: int | str | None,
    request: Request | None = None,
    previous_value: object | None = None,
    new_value: object | None = None,
    details: dict | None = None,
) -> None:
    event = AuditEvent(
        event_uuid=str(uuid4()),
        user_id=user.id if user else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        previous_value=(
            json.dumps(previous_value, sort_keys=True)
            if previous_value is not None
            else None
        ),
        new_value=(
            json.dumps(new_value, sort_keys=True)
            if new_value is not None
            else None
        ),
        ip_address=request.client.host if request and request.client else None,
        details=json.dumps(details, sort_keys=True) if details else None,
        created_at=datetime.now(timezone.utc),
    )
    stamp_audit_event(db, event)
    db.add(event)

    messages = {
        "PROPERTY_SUBMITTED": "Your property was submitted for verification.",
        "PROPERTY_VERIFICATION_APPROVED": "Your property verification was approved.",
        "PROPERTY_VERIFICATION_REJECTED": "Your property verification was rejected.",
        "VALUATION_APPROVED": "The property valuation review was approved.",
        "VALUATION_REJECTED": "The property valuation review was rejected.",
        "LEGAL_REVIEW_APPROVED": "The property legal review was approved.",
        "LEGAL_REVIEW_REJECTED": "The property legal review was rejected.",
        "COMPLIANCE_APPROVED": "The compliance review was approved.",
        "COMPLIANCE_REJECTED": "The compliance review was rejected.",
        "TOKENIZATION_PROPOSAL_SUBMITTED": "A tokenisation proposal is ready for review.",
        "TOKEN_PURCHASE_DEMO_ALLOCATED": "A demonstration token allocation was recorded; no payment was processed.",
        "TOKEN_ISSUANCE_COMPLETED": "Tokens were issued for an approved property.",
        "PROPERTY_MANAGER_ASSIGNED": "You have been assigned to manage a property.",
        "USER_SUSPENDED": "Your account access was suspended by an administrator.",
    }
    notification_message = messages.get(action)
    next_role_by_approval = {
        "PROPERTY_VERIFICATION_APPROVED": (
            "property_valuer",
            "Property verification is complete; valuation may begin.",
        ),
        "VALUATION_SUBMITTED": (
            "super_admin",
            "A property valuation is awaiting independent review.",
        ),
        "VALUATION_APPROVED": (
            "legal_advisor",
            "A current property valuation was approved; legal review can proceed.",
        ),
        "LEGAL_REVIEW_APPROVED": (
            "compliance_officer",
            "Legal review was approved; investor compliance can proceed.",
        ),
        "COMPLIANCE_APPROVED": (
            "tokenization_officer",
            "Compliance was approved; the tokenisation proposal can proceed.",
        ),
        "TOKENISATION_PROPOSAL_APPROVED": (
            "super_admin",
            "The proposal was reviewed; final authorisation is required.",
        ),
        "FINAL_AUTHORIZATION_APPROVED": (
            "tokenization_officer",
            "Final authorisation is complete; token issuance may proceed.",
        ),
    }
    next_reviewer = next_role_by_approval.get(
        action.removeprefix("APPROVAL_")
    )
    if action.startswith("APPROVAL_"):
        decision = next(
            (
                candidate
                for candidate in (
                    "ADDITIONAL_DOCUMENTATION",
                    "REQUEST_CHANGES",
                    "SUBMITTED",
                    "APPROVED",
                    "COMPLETED",
                    "REJECTED",
                    "SUSPENDED",
                    "EXPIRED",
                )
                if action.endswith(f"_{candidate}")
            ),
            "",
        )
        stage = action[len("APPROVAL_") : -(len(decision) + 1)] if decision else ""
        stage_name = stage.lower().replace("_", " ")
        decision_name = decision.lower().replace("_", " ")
        if decision == "SUBMITTED":
            notification_message = f"A {stage_name.lower()} review is required."
        elif decision in {"APPROVED", "COMPLETED"}:
            notification_message = f"The {stage_name.lower()} approval stage was completed."
        elif decision in {"REJECTED", "REQUEST_CHANGES", "ADDITIONAL_DOCUMENTATION"}:
            notification_message = (
                f"The {stage_name.lower()} stage requires attention: {decision_name}."
            )
    if entity_type == "property_valuation" and action.startswith("VALUATION_"):
        notification_message = f"The property valuation review was {action.removeprefix('VALUATION_').lower().replace('_', ' ')}."
    elif entity_type == "legal_review" and action.startswith("LEGAL_REVIEW_"):
        notification_message = f"The property legal review was {action.removeprefix('LEGAL_REVIEW_').lower().replace('_', ' ')}."
    elif entity_type == "investor_compliance" and action.startswith("COMPLIANCE_"):
        notification_message = f"The compliance review was {action.removeprefix('COMPLIANCE_').lower().replace('_', ' ')}."
    if notification_message:
        recipient_ids: set[int] = set()
        if entity_type == "user" and entity_id is not None:
            recipient_ids.add(int(entity_id))
        elif entity_type in {"asset", "property"} and entity_id is not None:
            asset = db.query(Asset).filter(Asset.id == int(entity_id)).first()
            if asset is not None:
                recipient_ids.add(asset.user_id)
        elif entity_id is not None and entity_type == "property_valuation":
            valuation = db.query(PropertyValuation).filter(
                PropertyValuation.id == int(entity_id)
            ).first()
            if valuation:
                asset = db.query(Asset).filter(Asset.id == valuation.asset_id).first()
                if asset:
                    recipient_ids.add(asset.user_id)
        elif entity_id is not None and entity_type == "legal_review":
            review = db.query(LegalReview).filter(
                LegalReview.id == int(entity_id)
            ).first()
            if review:
                asset = db.query(Asset).filter(Asset.id == review.asset_id).first()
                if asset:
                    recipient_ids.add(asset.user_id)
        elif entity_id is not None and entity_type == "tokenization_proposal":
            proposal = db.query(TokenizationProposal).filter(
                TokenizationProposal.id == int(entity_id)
            ).first()
            if proposal:
                asset = db.query(Asset).filter(Asset.id == proposal.asset_id).first()
                if asset:
                    recipient_ids.add(asset.user_id)
        elif entity_id is not None and entity_type == "investor_compliance":
            compliance = db.query(InvestorCompliance).filter(
                InvestorCompliance.user_id == int(entity_id)
            ).first()
            if compliance:
                recipient_ids.add(compliance.user_id)
        if next_reviewer:
            role, notification_message = next_reviewer
            recipient_ids.update(
                user_id
                for (user_id,) in db.query(User.id).filter(
                    User.role == role,
                    User.is_active.is_(True),
                ).all()
            )
        if action == "PROPERTY_SUBMITTED":
            recipient_ids.update(
                user_id
                for (user_id,) in db.query(User.id).filter(
                    User.role == "property_verifier",
                    User.is_active.is_(True),
                ).all()
            )
        if action == "TOKENIZATION_PROPOSAL_SUBMITTED":
            recipient_ids.update(
                user_id
                for (user_id,) in db.query(User.id).filter(
                    User.role.in_(("super_admin", "admin")),
                    User.is_active.is_(True),
                ).all()
            )
        if user and action == "TOKEN_PURCHASE_DEMO_ALLOCATED":
            recipient_ids.add(user.id)
        for recipient_id in recipient_ids:
            db.add(
                Notification(
                    user_id=recipient_id,
                    event_type=action,
                    message=notification_message,
                    entity_type=entity_type,
                    entity_id=str(entity_id) if entity_id is not None else None,
                )
            )
