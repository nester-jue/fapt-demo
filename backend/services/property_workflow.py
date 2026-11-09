import json
from datetime import datetime, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from models.asset import Asset
from models.asset_review_log import AssetReviewLog
from models.property_document import PropertyDocument
from models.property_verification import PropertyVerification
from models.user import User
from services.audit import record_audit_event
from services.tokenization_workflow import record_approval


REVIEWABLE_STATUSES = {
    "SUBMITTED",
    "UNDER_VERIFICATION",
    "Pending Review",
    "Submitted",
    "Under Verification",
}


def decide_property_verification(
    db: Session,
    *,
    asset: Asset,
    verifier: User,
    decision: str,
    comments: str,
    supporting_references: list[str] | None = None,
    request: Request | None = None,
) -> Asset:
    if asset.user_id == verifier.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verifiers cannot review their own property submissions.",
        )

    if asset.status not in REVIEWABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This property is not awaiting verification.",
        )

    if decision in {"APPROVED", "REJECTED"}:
        document_count = (
            db.query(PropertyDocument)
            .filter(PropertyDocument.asset_id == asset.id)
            .count()
        )
        if document_count < 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="At least one supporting property document is required.",
            )

    previous_status = asset.status
    status_by_decision = {
        "APPROVED": "Verified",
        "REJECTED": "Verification Rejected",
        "ADDITIONAL_INFORMATION_REQUIRED": "Additional Information Required",
    }
    new_status = status_by_decision[decision]
    asset.status = new_status
    if decision in {"APPROVED", "REJECTED"}:
        asset.reviewed_by = verifier.id
        asset.reviewed_at = datetime.now(timezone.utc)
        asset.rejection_reason = comments.strip() if decision == "REJECTED" else None

    normalized_comments = comments.strip()
    verification = PropertyVerification(
        asset_id=asset.id,
        verifier_user_id=verifier.id,
        decision=decision,
        comments=normalized_comments,
        previous_status=previous_status,
        new_status=new_status,
        supporting_references=json.dumps(supporting_references or []),
    )
    db.add(verification)
    db.add(
        AssetReviewLog(
            asset_id=asset.id,
            admin_user_id=verifier.id,
            action=decision,
            reason=normalized_comments,
        )
    )
    record_approval(
        db,
        asset_id=asset.id,
        user_id=verifier.id,
        stage="PROPERTY_VERIFICATION",
        decision=decision,
        comments=normalized_comments,
    )
    record_audit_event(
        db,
        user=verifier,
        action=f"PROPERTY_VERIFICATION_{decision}",
        entity_type="property",
        entity_id=asset.id,
        request=request,
        previous_value={"status": previous_status},
        new_value={"status": new_status, "comments": normalized_comments},
        details={"supporting_references": supporting_references or []},
    )

    try:
        db.commit()
        db.refresh(asset)
    except Exception:
        db.rollback()
        raise

    return asset
