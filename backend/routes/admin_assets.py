from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from database import get_db
from models.asset import Asset
from models.asset_review_log import AssetReviewLog
from models.property_document import PropertyDocument
from models.user import User
from schemas.asset import AssetResponse
from schemas.asset_review import AssetApproveRequest, AssetRejectRequest
from schemas.user_admin import VerificationDecisionRequest
from services.authorization import require_roles
from services.property_workflow import decide_property_verification


router = APIRouter(
    prefix="/admin/assets",
    tags=["Administrator - Property Verification"],
)

require_verifier = require_roles("property_verifier", "super_admin")


def _load_property(db: Session, asset_id: int) -> Asset:
    asset = db.query(Asset).filter(Asset.id == asset_id).with_for_update().first()
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found.",
        )
    return asset


@router.get("/pending", response_model=list[AssetResponse])
def get_pending_properties(
    db: Session = Depends(get_db),
    _verifier: User = Depends(require_verifier),
):
    return (
        db.query(Asset)
        .filter(
            Asset.status.in_(
                [
                    "SUBMITTED",
                    "UNDER_VERIFICATION",
                    "Pending Review",
                    "Submitted",
                    "Under Verification",
                ]
            )
        )
        .order_by(Asset.created_at.asc())
        .all()
    )


@router.get("/{asset_id}")
def get_property_for_verification(
    asset_id: int,
    db: Session = Depends(get_db),
    _verifier: User = Depends(require_verifier),
):
    asset = _load_property(db, asset_id)
    documents = (
        db.query(PropertyDocument)
        .filter(
            PropertyDocument.asset_id == asset.id,
            PropertyDocument.document_type == "PROPERTY_SUPPORT",
        )
        .order_by(PropertyDocument.created_at.desc())
        .all()
    )
    return {
        "property": AssetResponse.model_validate(asset),
        "documents": [
            {
                "id": item.id,
                "original_filename": item.original_filename,
                "content_type": item.content_type,
                "file_size": item.file_size,
                "sha256": item.sha256,
                "download_url": f"/assets/documents/{item.id}/download",
            }
            for item in documents
        ],
    }


@router.post("/{asset_id}/approve", response_model=AssetResponse)
def approve_property(
    asset_id: int,
    review_data: AssetApproveRequest,
    request: Request,
    db: Session = Depends(get_db),
    verifier: User = Depends(require_verifier),
):
    asset = _load_property(db, asset_id)
    return decide_property_verification(
        db,
        asset=asset,
        verifier=verifier,
        decision="APPROVED",
        comments=review_data.reason or "Verification approved.",
        request=request,
    )


@router.post("/{asset_id}/reject", response_model=AssetResponse)
def reject_property(
    asset_id: int,
    review_data: AssetRejectRequest,
    request: Request,
    db: Session = Depends(get_db),
    verifier: User = Depends(require_verifier),
):
    asset = _load_property(db, asset_id)
    return decide_property_verification(
        db,
        asset=asset,
        verifier=verifier,
        decision="REJECTED",
        comments=review_data.reason,
        request=request,
    )


@router.post(
    "/{asset_id}/request-documents",
    response_model=AssetResponse,
)
def request_additional_documents(
    asset_id: int,
    review_data: VerificationDecisionRequest,
    request: Request,
    db: Session = Depends(get_db),
    verifier: User = Depends(require_verifier),
):
    asset = _load_property(db, asset_id)
    return decide_property_verification(
        db,
        asset=asset,
        verifier=verifier,
        decision="ADDITIONAL_INFORMATION_REQUIRED",
        comments=review_data.comments,
        supporting_references=review_data.supporting_references,
        request=request,
    )


@router.get("/{asset_id}/history")
def get_property_verification_history(
    asset_id: int,
    db: Session = Depends(get_db),
    _verifier: User = Depends(require_verifier),
):
    _load_property(db, asset_id)
    logs = (
        db.query(AssetReviewLog, User)
        .join(User, AssetReviewLog.admin_user_id == User.id)
        .filter(AssetReviewLog.asset_id == asset_id)
        .order_by(AssetReviewLog.created_at.desc())
        .all()
    )

    return [
        {
            "id": log.id,
            "asset_id": log.asset_id,
            "verifier_user_id": log.admin_user_id,
            "verifier_name": reviewer.full_name,
            "decision": log.action,
            "comments": log.reason,
            "created_at": log.created_at,
        }
        for log, reviewer in logs
    ]
