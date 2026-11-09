import hashlib
import json
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models.asset import Asset
from models.investor_compliance import ComplianceReviewHistory, InvestorCompliance
from models.legal_review import LegalReview
from models.property_document import PropertyDocument
from models.property_valuation import PropertyValuation
from models.property_verification import PropertyVerification
from models.token_issuance import TokenIssuance
from models.tokenization_proposal import TokenizationApproval, TokenizationProposal
from models.user import User
from routes import assets as assets_routes
from schemas.workflow import (
    ComplianceDecision,
    FinalAuthorization,
    LegalReviewCreate,
    ProposalDecision,
    TokenizationProposalCreate,
    ValuationCreate,
    ValuationDecision,
)
from services.audit import record_audit_event
from services.authorization import has_role, require_roles
from services.tokenization_workflow import (
    APPROVAL_STAGES,
    latest_approval,
    record_approval,
)


router = APIRouter(prefix="/workflow", tags=["Property Valuation, Legal, Compliance and Tokenisation"])

require_valuer = require_roles("property_valuer", "super_admin")
require_legal_advisor = require_roles("legal_advisor", "super_admin")
require_compliance_officer = require_roles("compliance_officer", "super_admin")
require_tokenization_officer = require_roles("tokenization_officer", "super_admin")
require_super_admin = require_roles("super_admin")

MAX_DOCUMENT_SIZE = 10 * 1024 * 1024
ALLOWED_DOCUMENTS = {
    ".pdf": ("application/pdf", lambda data: data.startswith(b"%PDF-")),
    ".png": ("image/png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    ".jpg": ("image/jpeg", lambda data: data.startswith(b"\xff\xd8\xff")),
    ".jpeg": ("image/jpeg", lambda data: data.startswith(b"\xff\xd8\xff")),
}
DOCUMENT_ROLE = {
    "VALUATION_REPORT": (
        "property_valuer",
        "legal_advisor",
        "tokenization_officer",
        "super_admin",
    ),
    "LEGAL_AGREEMENT": ("legal_advisor", "super_admin"),
    "PROPOSAL_DISCLOSURE": ("tokenization_officer", "super_admin"),
}
def _property(db: Session, asset_id: int) -> Asset:
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if asset is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    return asset


def _document_ids_for_asset(
    db: Session,
    *,
    asset_id: int,
    document_ids: list[int],
    document_type: str,
) -> list[PropertyDocument]:
    records = (
        db.query(PropertyDocument)
        .filter(
            PropertyDocument.asset_id == asset_id,
            PropertyDocument.id.in_(document_ids),
            PropertyDocument.document_type == document_type,
        )
        .all()
    )
    if len(records) != len(set(document_ids)):
        raise HTTPException(
            status_code=422,
            detail=f"All attached documents must be {document_type.lower()} files for this property.",
        )
    return records


def _latest_valuation(db: Session, asset_id: int) -> PropertyValuation | None:
    return (
        db.query(PropertyValuation)
        .filter(PropertyValuation.asset_id == asset_id)
        .order_by(PropertyValuation.created_at.desc(), PropertyValuation.id.desc())
        .first()
    )


def _approved_valuation(db: Session, asset_id: int) -> PropertyValuation | None:
    latest = _latest_valuation(db, asset_id)
    if (
        latest is None
        or latest.status != "APPROVED"
        or latest.valid_until < date.today()
    ):
        return None
    return latest


def _latest_legal_review(db: Session, asset_id: int) -> LegalReview | None:
    return (
        db.query(LegalReview)
        .filter(LegalReview.asset_id == asset_id)
        .order_by(LegalReview.created_at.desc(), LegalReview.id.desc())
        .first()
    )


def _compliance_record(db: Session, user_id: int) -> InvestorCompliance | None:
    return (
        db.query(InvestorCompliance)
        .filter(InvestorCompliance.user_id == user_id)
        .first()
    )


def _compliance_summary(record: InvestorCompliance | None, user_id: int) -> dict:
    if record is None:
        return {
            "user_id": user_id,
            "kyc_status": "NOT_STARTED",
            "aml_status": "NOT_STARTED",
            "identity_verification_status": "NOT_STARTED",
            "eligibility_status": "NOT_STARTED",
            "is_eligible": False,
            "required_documents": [],
        }
    return {
        "user_id": record.user_id,
        "kyc_status": record.kyc_status,
        "aml_status": record.aml_status,
        "identity_verification_status": record.identity_verification_status,
        "eligibility_status": record.eligibility_status,
        "is_eligible": record.is_eligible,
        "required_documents": json.loads(record.required_documents),
    }


def _approval_statuses(
    db: Session,
    asset: Asset,
    proposal: TokenizationProposal | None = None,
) -> list[dict]:
    verification = (
        db.query(PropertyVerification)
        .filter(PropertyVerification.asset_id == asset.id)
        .order_by(PropertyVerification.created_at.desc(), PropertyVerification.id.desc())
        .first()
    )
    valuation = _approved_valuation(db, asset.id)
    latest_valuation = _latest_valuation(db, asset.id)
    legal = _latest_legal_review(db, asset.id)
    owner_compliance = _compliance_summary(
        _compliance_record(db, asset.user_id), asset.user_id
    )
    legal_agreement_exists = (
        db.query(PropertyDocument.id)
        .filter(
            PropertyDocument.asset_id == asset.id,
            PropertyDocument.document_type == "LEGAL_AGREEMENT",
        )
        .first()
        is not None
    )
    disclosure_document_exists = (
        db.query(PropertyDocument.id)
        .filter(
            PropertyDocument.asset_id == asset.id,
            PropertyDocument.document_type == "PROPOSAL_DISCLOSURE",
        )
        .first()
        is not None
    )
    registration_approval = latest_approval(db, asset.id, "REGISTRATION")
    agreements_approval = latest_approval(
        db, asset.id, "AGREEMENTS_DISCLOSURES"
    )
    registration_ok = bool(
        registration_approval
        and registration_approval.decision == "COMPLETED"
        and asset.registration_number
        and asset.jurisdiction
        and asset.estimated_value > 0
        and asset.status not in {"DRAFT", "SUBMITTED", "UNDER_VERIFICATION"}
    )
    verification_ok = bool(
        verification
        and verification.decision == "APPROVED"
        and asset.status in {"Verified", "Tokenised"}
    )
    valuation_ok = bool(
        valuation is not None
        and latest_valuation is not None
        and latest_valuation.id == valuation.id
    )
    legal_ok = bool(legal and legal.decision == "APPROVED")
    compliance_ok = bool(
        owner_compliance["eligibility_status"] == "APPROVED"
        and owner_compliance["is_eligible"]
    )
    agreements_ok = bool(
        legal_agreement_exists
        and disclosure_document_exists
        and proposal
        and proposal.disclosures.strip()
        and agreements_approval
        and agreements_approval.decision == "COMPLETED"
    )
    proposal_review = latest_approval(db, asset.id, "TOKENISATION_PROPOSAL")
    proposal_ok = bool(
        proposal
        and proposal.status == "APPROVED"
        and proposal_review
        and proposal_review.decision == "APPROVED"
    )
    final_authorization = latest_approval(db, asset.id, "FINAL_AUTHORIZATION")
    final_ok = bool(
        final_authorization and final_authorization.decision == "APPROVED"
    )

    return [
        {
            "stage": "REGISTRATION",
            "status": "COMPLETED" if registration_ok else "PENDING",
            "complete": registration_ok,
        },
        {
            "stage": "PROPERTY_VERIFICATION",
            "status": verification.decision if verification else "PENDING",
            "complete": verification_ok,
        },
        {
            "stage": "VALUATION",
            "status": (
                "APPROVED"
                if valuation_ok
                else "EXPIRED"
                if latest_valuation
                and latest_valuation.status == "APPROVED"
                and latest_valuation.valid_until < date.today()
                else latest_valuation.status
                if latest_valuation
                else "PENDING"
            ),
            "complete": valuation_ok,
            "valuation_id": valuation.id if valuation else None,
            "amount": (
                valuation.amount
                if valuation
                else latest_valuation.amount
                if latest_valuation
                else None
            ),
            "currency": (
                valuation.currency
                if valuation
                else latest_valuation.currency
                if latest_valuation
                else None
            ),
        },
        {
            "stage": "LEGAL_REVIEW",
            "status": legal.decision if legal else "PENDING",
            "complete": legal_ok,
        },
        {
            "stage": "COMPLIANCE",
            "status": owner_compliance["eligibility_status"],
            "complete": compliance_ok,
        },
        {
            "stage": "AGREEMENTS_DISCLOSURES",
            "status": (
                "COMPLETED"
                if agreements_ok
                else "PENDING"
            ),
            "complete": agreements_ok,
        },
        {
            "stage": "TOKENISATION_PROPOSAL",
            "status": (
                proposal.status
                if proposal
                else "PENDING"
            ),
            "complete": proposal_ok,
        },
        {
            "stage": "FINAL_AUTHORIZATION",
            "status": (
                final_authorization.decision
                if final_authorization
                else "PENDING"
            ),
            "complete": final_ok,
        },
    ]


def _assert_pre_proposal_stages_complete(db: Session, asset: Asset) -> None:
    stages = _approval_statuses(db, asset)
    incomplete = [
        item["stage"]
        for item in stages[:5]
        if not item["complete"]
    ]
    legal_documents_exist = (
        db.query(PropertyDocument.id)
        .filter(
            PropertyDocument.asset_id == asset.id,
            PropertyDocument.document_type == "LEGAL_AGREEMENT",
        )
        .first()
        is not None
    )
    disclosure_document_exists = (
        db.query(PropertyDocument.id)
        .filter(
            PropertyDocument.asset_id == asset.id,
            PropertyDocument.document_type == "PROPOSAL_DISCLOSURE",
        )
        .first()
        is not None
    )
    if incomplete:
        raise HTTPException(
            status_code=409,
            detail=f"Mandatory stages must be completed first: {', '.join(incomplete)}.",
        )
    if not legal_documents_exist or not disclosure_document_exists:
        raise HTTPException(
            status_code=409,
            detail="A legal agreement and disclosure document are required before tokenisation proposal submission.",
        )


def _validate_proposal_economics(
    proposal_data: TokenizationProposalCreate,
    valuation: PropertyValuation,
) -> None:
    if proposal_data.currency.upper() != valuation.currency.upper():
        raise HTTPException(
            status_code=422,
            detail="Proposal currency must match the approved valuation currency.",
        )
    if proposal_data.token_price * proposal_data.total_supply != valuation.amount:
        raise HTTPException(
            status_code=422,
            detail="Token price multiplied by supply must equal the approved valuation.",
        )
    quantized_supply = proposal_data.total_supply.quantize(
        Decimal(1).scaleb(-proposal_data.decimal_precision)
    )
    if quantized_supply != proposal_data.total_supply:
        raise HTTPException(
            status_code=422,
            detail="Token supply exceeds the configured decimal precision.",
        )
    if (
        proposal_data.maximum_investment is not None
        and proposal_data.maximum_investment < proposal_data.minimum_investment
    ):
        raise HTTPException(
            status_code=422,
            detail="Maximum investment cannot be below minimum investment.",
        )
    if (
        proposal_data.minimum_investment > valuation.amount
        or (
            proposal_data.maximum_investment is not None
            and proposal_data.maximum_investment > valuation.amount
        )
    ):
        raise HTTPException(
            status_code=422,
            detail="Investment limits cannot exceed the approved valuation.",
        )


def _approval_dict(item: TokenizationApproval) -> dict:
    return {
        "approval_ref": item.approval_ref,
        "asset_id": item.asset_id,
        "responsible_user_id": item.responsible_user_id,
        "stage": item.stage,
        "decision": item.decision,
        "comments": item.comments,
        "supporting_document_ids": json.loads(item.supporting_document_ids or "[]"),
        "created_at": item.created_at,
    }


@router.post(
    "/properties/{asset_id}/documents",
    status_code=status.HTTP_201_CREATED,
)
async def upload_workflow_document(
    asset_id: int,
    document_type: str = Form(...),
    document: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(
        "property_valuer",
        "legal_advisor",
        "tokenization_officer",
        "super_admin",
    )),
):
    asset = _property(db, asset_id)
    if document_type not in DOCUMENT_ROLE or not has_role(
        current_user, *DOCUMENT_ROLE.get(document_type, ())
    ):
        raise HTTPException(status_code=403, detail="You cannot upload this document type.")

    filename = Path((document.filename or "").replace("\\", "/")).name.strip()
    extension = Path(filename).suffix.lower()
    expected = ALLOWED_DOCUMENTS.get(extension)
    if not filename or len(filename) > 255 or expected is None:
        raise HTTPException(
            status_code=415,
            detail="Only PDF, PNG, and JPEG workflow documents are accepted.",
        )
    content_type, validate_signature = expected
    if document.content_type != content_type:
        raise HTTPException(status_code=415, detail="Document type does not match file extension.")

    storage_key = f"{uuid4().hex}{extension}"
    directory = assets_routes.DOCUMENTS_DIR
    temporary_path = directory / f"{uuid4().hex}.tmp"
    stored_path = directory / storage_key
    digest = hashlib.sha256()
    file_size = 0
    signature = b""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        with temporary_path.open("wb") as target:
            while chunk := await document.read(64 * 1024):
                file_size += len(chunk)
                if file_size > MAX_DOCUMENT_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="Workflow documents must be 10 MB or smaller.",
                    )
                if len(signature) < 16:
                    signature += chunk[: 16 - len(signature)]
                digest.update(chunk)
                target.write(chunk)
        if file_size == 0 or not validate_signature(signature):
            raise HTTPException(
                status_code=415,
                detail="The uploaded file is empty or is not a valid supported document.",
            )
        os.replace(temporary_path, stored_path)
        os.chmod(stored_path, 0o600)
        record = PropertyDocument(
            asset_id=asset.id,
            uploaded_by_user_id=current_user.id,
            document_type=document_type,
            storage_key=storage_key,
            original_filename=filename,
            content_type=content_type,
            file_size=file_size,
            sha256=digest.hexdigest(),
        )
        db.add(record)
        db.flush()
        record_audit_event(
            db,
            user=current_user,
            action="WORKFLOW_DOCUMENT_UPLOADED",
            entity_type="property_document",
            entity_id=record.id,
            new_value={"asset_id": asset.id, "document_type": document_type},
        )
        db.commit()
        db.refresh(record)
        return {
            "id": record.id,
            "asset_id": record.asset_id,
            "document_type": record.document_type,
            "original_filename": record.original_filename,
            "content_type": record.content_type,
            "file_size": record.file_size,
            "sha256": record.sha256,
        }
    except HTTPException:
        db.rollback()
        if stored_path.exists():
            stored_path.unlink()
        raise
    except OSError as error:
        db.rollback()
        if stored_path.exists():
            stored_path.unlink()
        raise HTTPException(
            status_code=500, detail="The workflow document could not be stored."
        ) from error
    except IntegrityError as error:
        db.rollback()
        if stored_path.exists():
            stored_path.unlink()
        raise HTTPException(
            status_code=500, detail="The workflow document could not be recorded."
        ) from error
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
        await document.close()


@router.get("/documents/{document_id}/download")
def download_workflow_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(
        "property_valuer",
        "legal_advisor",
        "tokenization_officer",
        "super_admin",
    )),
):
    document = db.query(PropertyDocument).filter(
        PropertyDocument.id == document_id
    ).first()
    if document is None:
        raise HTTPException(status_code=404, detail="Workflow document not found.")
    allowed_roles = DOCUMENT_ROLE.get(document.document_type, ())
    if not has_role(current_user, *allowed_roles):
        raise HTTPException(status_code=403, detail="You cannot access this document.")
    root = assets_routes.DOCUMENTS_DIR.resolve()
    path = (root / document.storage_key).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(status_code=404, detail="Stored workflow document is unavailable.")
    return FileResponse(
        path=path,
        media_type=document.content_type,
        filename=document.original_filename,
    )


@router.get("/valuations/pending")
def list_properties_for_valuation(
    db: Session = Depends(get_db),
    _valuer: User = Depends(require_valuer),
):
    rows = (
        db.query(Asset)
        .filter(Asset.status == "Verified")
        .order_by(Asset.created_at.asc())
        .all()
    )
    result = []
    for asset in rows:
        latest = _latest_valuation(db, asset.id)
        if latest is None or latest.status in {
            "REJECTED",
            "REQUEST_CHANGES",
            "ADDITIONAL_DOCUMENTATION",
        }:
            result.append(asset)
    return result


@router.get("/valuations/history")
def list_valuation_history(
    db: Session = Depends(get_db),
    _valuer: User = Depends(require_roles("property_valuer", "super_admin")),
):
    rows = (
        db.query(PropertyValuation, Asset)
        .join(Asset, PropertyValuation.asset_id == Asset.id)
        .order_by(PropertyValuation.created_at.desc(), PropertyValuation.id.desc())
        .all()
    )
    return [
        {
            "id": valuation.id,
            "asset_id": asset.id,
            "asset_name": asset.name,
            "asset_code": asset.asset_code,
            "amount": valuation.amount,
            "currency": valuation.currency,
            "valuation_date": valuation.valuation_date,
            "valid_until": valuation.valid_until,
            "methodology": valuation.methodology,
            "report_document_ids": json.loads(valuation.report_document_ids or "[]"),
            "status": valuation.status,
            "review_comments": valuation.review_comments,
            "created_at": valuation.created_at,
        }
        for valuation, asset in rows
    ]


@router.get("/valuations/review-queue")
def valuation_review_queue(
    db: Session = Depends(get_db),
    _reviewer: User = Depends(require_super_admin),
):
    valuations = (
        db.query(PropertyValuation)
        .filter(PropertyValuation.status == "PENDING_REVIEW")
        .order_by(PropertyValuation.created_at.asc())
        .all()
    )
    return [
        {
            "id": item.id,
            "asset_id": item.asset_id,
            "valuer_user_id": item.valuer_user_id,
            "amount": item.amount,
            "currency": item.currency,
            "valuation_date": item.valuation_date,
            "valid_until": item.valid_until,
            "methodology": item.methodology,
            "status": item.status,
            "report_document_ids": (
                json.loads(latest_approval(db, item.asset_id, "VALUATION").supporting_document_ids)
                if latest_approval(db, item.asset_id, "VALUATION")
                else []
            ),
        }
        for item in valuations
    ]


@router.post("/properties/{asset_id}/valuations", status_code=201)
def submit_valuation(
    asset_id: int,
    valuation_data: ValuationCreate,
    db: Session = Depends(get_db),
    valuer: User = Depends(require_valuer),
):
    asset = _property(db, asset_id)
    if asset.status != "Verified":
        raise HTTPException(status_code=409, detail="Only verified properties can be valued.")
    if valuation_data.valuation_date > date.today():
        raise HTTPException(status_code=422, detail="Valuation date cannot be in the future.")
    if valuation_data.valid_until < valuation_data.valuation_date:
        raise HTTPException(status_code=422, detail="Valuation validity must end on or after its valuation date.")
    reports = _document_ids_for_asset(
        db,
        asset_id=asset.id,
        document_ids=valuation_data.report_document_ids,
        document_type="VALUATION_REPORT",
    )
    valuation = PropertyValuation(
        asset_id=asset.id,
        valuer_user_id=valuer.id,
        amount=valuation_data.amount,
        currency=valuation_data.currency.strip().upper(),
        valuation_date=valuation_data.valuation_date,
        valid_until=valuation_data.valid_until,
        methodology=valuation_data.methodology.strip(),
        report_document_ids=json.dumps([item.id for item in reports]),
        status="PENDING_REVIEW",
    )
    db.add(valuation)
    db.flush()
    record_approval(
        db,
        asset_id=asset.id,
        user_id=valuer.id,
        stage="VALUATION",
        decision="SUBMITTED",
        comments="Valuation submitted for independent review.",
        supporting_document_ids=[item.id for item in reports],
    )
    db.commit()
    db.refresh(valuation)
    return {
        "id": valuation.id,
        "asset_id": valuation.asset_id,
        "valuer_user_id": valuation.valuer_user_id,
        "amount": valuation.amount,
        "currency": valuation.currency,
        "valuation_date": valuation.valuation_date,
        "valid_until": valuation.valid_until,
        "methodology": valuation.methodology,
        "report_document_ids": [item.id for item in reports],
        "status": valuation.status,
        "created_at": valuation.created_at,
    }


@router.get("/properties/{asset_id}/valuations")
def valuation_history(
    asset_id: int,
    db: Session = Depends(get_db),
    _valuer: User = Depends(require_roles(
        "property_valuer", "legal_advisor", "tokenization_officer", "super_admin"
    )),
):
    _property(db, asset_id)
    valuations = (
        db.query(PropertyValuation)
        .filter(PropertyValuation.asset_id == asset_id)
        .order_by(PropertyValuation.created_at.desc(), PropertyValuation.id.desc())
        .all()
    )
    return [
        {
            "id": item.id,
            "asset_id": item.asset_id,
            "valuer_user_id": item.valuer_user_id,
            "amount": item.amount,
            "currency": item.currency,
            "valuation_date": item.valuation_date,
            "valid_until": item.valid_until,
            "methodology": item.methodology,
            "report_document_ids": json.loads(item.report_document_ids or "[]"),
            "status": item.status,
            "review_comments": item.review_comments,
            "reviewed_by_user_id": item.reviewed_by_user_id,
            "reviewed_at": item.reviewed_at,
            "created_at": item.created_at,
        }
        for item in valuations
    ]


@router.post("/valuations/{valuation_id}/decision")
def decide_valuation(
    valuation_id: int,
    decision_data: ValuationDecision,
    db: Session = Depends(get_db),
    reviewer: User = Depends(require_super_admin),
):
    valuation = db.query(PropertyValuation).filter(
        PropertyValuation.id == valuation_id
    ).with_for_update().first()
    if valuation is None:
        raise HTTPException(status_code=404, detail="Valuation not found.")
    if valuation.valuer_user_id == reviewer.id:
        raise HTTPException(status_code=403, detail="Valuers cannot approve their own valuation.")
    if valuation.status != "PENDING_REVIEW":
        raise HTTPException(status_code=409, detail="This valuation is not awaiting review.")
    if decision_data.decision == "APPROVED" and valuation.valid_until < date.today():
        raise HTTPException(status_code=409, detail="Expired valuations cannot be approved.")
    valuation.status = decision_data.decision
    valuation.review_comments = decision_data.comments.strip()
    valuation.reviewed_by_user_id = reviewer.id
    valuation.reviewed_at = datetime.now(timezone.utc)
    record_approval(
        db,
        asset_id=valuation.asset_id,
        user_id=reviewer.id,
        stage="VALUATION",
        decision=decision_data.decision,
        comments=decision_data.comments.strip(),
    )
    record_audit_event(
        db,
        user=reviewer,
        action=f"VALUATION_{decision_data.decision}",
        entity_type="property_valuation",
        entity_id=valuation.id,
    )
    db.commit()
    db.refresh(valuation)
    return {"id": valuation.id, "status": valuation.status, "reviewed_at": valuation.reviewed_at}


@router.get("/legal/pending")
def list_properties_for_legal_review(
    db: Session = Depends(get_db),
    _advisor: User = Depends(require_legal_advisor),
):
    assets = (
        db.query(Asset)
        .filter(Asset.status == "Verified")
        .order_by(Asset.created_at.asc())
        .all()
    )
    return [
        {
            "property": asset,
            "valuation": _approved_valuation(db, asset.id),
            "latest_legal_review": _latest_legal_review(db, asset.id),
        }
        for asset in assets
        if _approved_valuation(db, asset.id) is not None
        and (
            _latest_legal_review(db, asset.id) is None
            or _latest_legal_review(db, asset.id).decision
            != "APPROVED"
        )
    ]


@router.get("/properties/{asset_id}/review-details")
def legal_review_details(
    asset_id: int,
    db: Session = Depends(get_db),
    _advisor: User = Depends(require_legal_advisor),
):
    asset = _property(db, asset_id)
    if asset.status not in {"Verified", "Tokenised"}:
        raise HTTPException(status_code=409, detail="Property verification must be approved first.")
    verification_history = (
        db.query(PropertyVerification)
        .filter(PropertyVerification.asset_id == asset_id)
        .order_by(PropertyVerification.created_at.desc())
        .all()
    )
    legal_documents = (
        db.query(PropertyDocument)
        .filter(
            PropertyDocument.asset_id == asset_id,
            PropertyDocument.document_type == "LEGAL_AGREEMENT",
        )
        .order_by(PropertyDocument.created_at.desc())
        .all()
    )
    return {
        "property": asset,
        "verification_history": verification_history,
        "valuation": _approved_valuation(db, asset_id),
        "valuation_history": db.query(PropertyValuation)
        .filter(PropertyValuation.asset_id == asset_id)
        .order_by(PropertyValuation.created_at.desc())
        .all(),
        "legal_documents": legal_documents,
        "legal_review_history": db.query(LegalReview)
        .filter(LegalReview.asset_id == asset_id)
        .order_by(LegalReview.created_at.desc())
        .all(),
    }


@router.post("/properties/{asset_id}/legal-reviews", status_code=201)
def submit_legal_review(
    asset_id: int,
    review_data: LegalReviewCreate,
    db: Session = Depends(get_db),
    reviewer: User = Depends(require_legal_advisor),
):
    asset = _property(db, asset_id)
    if asset.status != "Verified":
        raise HTTPException(status_code=409, detail="Only verified properties can receive legal review.")
    if _approved_valuation(db, asset.id) is None:
        raise HTTPException(status_code=409, detail="An approved, current valuation is required for legal review.")
    if asset.user_id == reviewer.id:
        raise HTTPException(status_code=403, detail="Legal advisors cannot review their own property.")
    docs = _document_ids_for_asset(
        db,
        asset_id=asset.id,
        document_ids=review_data.supporting_document_ids,
        document_type="LEGAL_AGREEMENT",
    ) if review_data.supporting_document_ids else []
    if review_data.decision == "APPROVED" and not docs:
        raise HTTPException(status_code=409, detail="Upload and attach a legal agreement before approval.")
    review = LegalReview(
        asset_id=asset.id,
        reviewer_user_id=reviewer.id,
        jurisdiction=review_data.jurisdiction.strip(),
        jurisdiction_requirements=review_data.jurisdiction_requirements.strip(),
        proposed_tokenisation_arrangements=(
            review_data.proposed_tokenisation_arrangements.strip()
        ),
        token_rights_description=review_data.token_rights_description.strip(),
        legal_risks=review_data.legal_risks.strip(),
        comments=review_data.comments.strip(),
        decision=review_data.decision,
        supporting_document_ids=json.dumps([item.id for item in docs]),
    )
    db.add(review)
    db.flush()
    record_approval(
        db,
        asset_id=asset.id,
        user_id=reviewer.id,
        stage="LEGAL_REVIEW",
        decision=review_data.decision,
        comments=review_data.comments.strip(),
        supporting_document_ids=[item.id for item in docs],
    )
    record_audit_event(
        db,
        user=reviewer,
        action=f"LEGAL_REVIEW_{review_data.decision}",
        entity_type="legal_review",
        entity_id=review.id,
        new_value={"jurisdiction": review.jurisdiction},
    )
    db.commit()
    db.refresh(review)
    return review


@router.get("/compliance/me")
def get_my_compliance_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("investor", "property_owner")),
):
    return _compliance_summary(_compliance_record(db, current_user.id), current_user.id)


@router.get("/compliance/users")
def list_compliance_cases(
    db: Session = Depends(get_db),
    _officer: User = Depends(require_compliance_officer),
):
    users = (
        db.query(User)
        .filter(
            User.role.in_(["investor", "property_owner"]),
            User.is_active.is_(True),
        )
        .order_by(User.created_at.desc())
        .all()
    )
    return [
        {
            "user_id": user.id,
            "full_name": user.full_name,
            "role": user.role,
            **_compliance_summary(_compliance_record(db, user.id), user.id),
        }
        for user in users
    ]


@router.get("/compliance/users/{user_id}/history")
def compliance_history(
    user_id: int,
    db: Session = Depends(get_db),
    _officer: User = Depends(require_compliance_officer),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or user.role not in {"investor", "property_owner"}:
        raise HTTPException(status_code=404, detail="Eligible account not found.")
    history = (
        db.query(ComplianceReviewHistory)
        .filter(ComplianceReviewHistory.user_id == user_id)
        .order_by(ComplianceReviewHistory.created_at.desc())
        .all()
    )
    return [
        {
            "id": item.id,
            "reviewer_user_id": item.reviewer_user_id,
            "decision": item.decision,
            "comments": item.comments,
            "status_snapshot": json.loads(item.status_snapshot),
            "created_at": item.created_at,
        }
        for item in history
    ]


@router.post("/compliance/users/{user_id}/decision")
def decide_compliance(
    user_id: int,
    decision_data: ComplianceDecision,
    db: Session = Depends(get_db),
    reviewer: User = Depends(require_compliance_officer),
):
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if user is None or user.role not in {"investor", "property_owner"}:
        raise HTTPException(status_code=404, detail="Eligible account not found.")
    all_accepted = all(
        item.status == "ACCEPTED" for item in decision_data.required_documents
    )
    if decision_data.decision == "APPROVE" and not (
        decision_data.kyc_status == "APPROVED"
        and decision_data.aml_status == "APPROVED"
        and decision_data.identity_verification_status == "APPROVED"
        and bool(decision_data.required_documents)
        and all_accepted
    ):
        raise HTTPException(
            status_code=422,
            detail="KYC, AML, identity status and all required documents must be approved before eligibility.",
        )
    status_by_decision = {
        "APPROVE": "APPROVED",
        "REJECT": "REJECTED",
        "REQUEST_CHANGES": "PENDING",
        "SUSPEND": "SUSPENDED",
        "EXPIRE": "EXPIRED",
    }
    eligibility = status_by_decision[decision_data.decision]
    record = _compliance_record(db, user.id)
    if record is None:
        record = InvestorCompliance(user_id=user.id)
        db.add(record)
    record.kyc_status = decision_data.kyc_status
    record.aml_status = decision_data.aml_status
    record.identity_verification_status = decision_data.identity_verification_status
    record.eligibility_status = eligibility
    record.is_eligible = eligibility == "APPROVED"
    record.required_documents = json.dumps(
        [item.model_dump() for item in decision_data.required_documents],
        sort_keys=True,
    )
    record.updated_by_user_id = reviewer.id
    record.updated_at = datetime.now(timezone.utc)
    db.flush()
    snapshot = _compliance_summary(record, user.id)
    db.add(
        ComplianceReviewHistory(
            user_id=user.id,
            reviewer_user_id=reviewer.id,
            decision=decision_data.decision,
            comments=decision_data.comments.strip(),
            status_snapshot=json.dumps(snapshot, sort_keys=True),
        )
    )
    affected_assets = db.query(Asset).filter(Asset.user_id == user.id).all()
    for asset in affected_assets:
        record_approval(
            db,
            asset_id=asset.id,
            user_id=reviewer.id,
            stage="COMPLIANCE",
            decision=eligibility,
            comments=decision_data.comments.strip(),
        )
    record_audit_event(
        db,
        user=reviewer,
        action=f"COMPLIANCE_{decision_data.decision}",
        entity_type="investor_compliance",
        entity_id=user.id,
        new_value={"eligibility_status": eligibility},
        details={"required_document_statuses": snapshot["required_documents"]},
    )
    db.commit()
    return snapshot


@router.get("/approvals")
def approval_dashboard(
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles(
        "property_valuer",
        "legal_advisor",
        "compliance_officer",
        "tokenization_officer",
        "super_admin",
    )),
):
    assets = db.query(Asset).order_by(Asset.created_at.desc()).all()
    result = []
    for asset in assets:
        proposal = db.query(TokenizationProposal).filter(
            TokenizationProposal.asset_id == asset.id
        ).first()
        result.append(
            {
                "property": asset,
                "proposal": proposal,
                "approved_valuation": _approved_valuation(db, asset.id),
                "legal_review": _latest_legal_review(db, asset.id),
                "stages": _approval_statuses(db, asset, proposal),
                "approvals": [
                    _approval_dict(item)
                    for item in db.query(TokenizationApproval)
                    .filter(TokenizationApproval.asset_id == asset.id)
                    .order_by(TokenizationApproval.created_at.asc())
                    .all()
                ],
            }
        )
    return result


@router.get("/properties/{asset_id}/readiness")
def property_readiness(
    asset_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles(
        "property_valuer",
        "legal_advisor",
        "compliance_officer",
        "tokenization_officer",
        "super_admin",
    )),
):
    asset = _property(db, asset_id)
    proposal = db.query(TokenizationProposal).filter(
        TokenizationProposal.asset_id == asset.id
    ).first()
    return {
        "asset_id": asset.id,
        "asset_code": asset.asset_code,
        "approved_valuation": _approved_valuation(db, asset.id),
        "legal_review": _latest_legal_review(db, asset.id),
        "stages": _approval_statuses(db, asset, proposal),
        "approvals": [
            _approval_dict(item)
            for item in db.query(TokenizationApproval)
            .filter(TokenizationApproval.asset_id == asset.id)
            .order_by(TokenizationApproval.created_at.asc())
            .all()
        ],
    }


@router.post("/properties/{asset_id}/proposals", status_code=201)
def submit_tokenization_proposal(
    asset_id: int,
    proposal_data: TokenizationProposalCreate,
    db: Session = Depends(get_db),
    officer: User = Depends(require_tokenization_officer),
):
    asset = _property(db, asset_id)
    if asset.status != "Verified":
        raise HTTPException(status_code=409, detail="Only verified, not-yet-issued properties can be proposed.")
    _assert_pre_proposal_stages_complete(db, asset)
    valuation = _approved_valuation(db, asset.id)
    if valuation is None:
        raise HTTPException(status_code=409, detail="A current approved valuation is required.")
    _validate_proposal_economics(proposal_data, valuation)
    if proposal_data.issuance_date < date.today():
        raise HTTPException(status_code=422, detail="Issuance date cannot be in the past.")
    legal_review = _latest_legal_review(db, asset.id)
    if legal_review is None or legal_review.decision != "APPROVED":
        raise HTTPException(status_code=409, detail="An approved legal review is required.")
    if (
        proposal_data.proposed_tokenisation_arrangements.strip()
        != legal_review.proposed_tokenisation_arrangements.strip()
        or proposal_data.token_rights_description.strip()
        != legal_review.token_rights_description.strip()
    ):
        raise HTTPException(
            status_code=409,
            detail="Token rights and proposed arrangements must exactly match the latest approved legal review.",
        )

    proposal = db.query(TokenizationProposal).filter(
        TokenizationProposal.asset_id == asset.id
    ).with_for_update().first()
    if proposal and proposal.status == "APPROVED":
        prior_final = latest_approval(db, asset.id, "FINAL_AUTHORIZATION")
        if prior_final is None or prior_final.decision == "APPROVED":
            raise HTTPException(status_code=409, detail="An approved proposal cannot be changed.")
    if proposal is None:
        proposal = TokenizationProposal(
            asset_id=asset.id,
            submitted_by_user_id=officer.id,
        )
        db.add(proposal)
    for field, value in proposal_data.model_dump().items():
        setattr(proposal, field, value)
    proposal.token_symbol = proposal.token_symbol.upper()
    proposal.currency = proposal.currency.upper()
    proposal.submitted_by_user_id = officer.id
    proposal.status = "PENDING_REVIEW"
    proposal.review_comments = None
    proposal.reviewed_by_user_id = None
    proposal.reviewed_at = None
    db.flush()
    docs = (
        db.query(PropertyDocument)
        .filter(
            PropertyDocument.asset_id == asset.id,
            PropertyDocument.document_type.in_(
                ["LEGAL_AGREEMENT", "PROPOSAL_DISCLOSURE"]
            ),
        )
        .all()
    )
    record_approval(
        db,
        asset_id=asset.id,
        user_id=officer.id,
        stage="AGREEMENTS_DISCLOSURES",
        decision="COMPLETED",
        comments="Legal agreement and proposal disclosures are attached.",
        supporting_document_ids=[item.id for item in docs],
    )
    record_approval(
        db,
        asset_id=asset.id,
        user_id=officer.id,
        stage="TOKENISATION_PROPOSAL",
        decision="SUBMITTED",
        comments="Tokenisation proposal submitted for review.",
    )
    record_audit_event(
        db,
        user=officer,
        action="TOKENIZATION_PROPOSAL_SUBMITTED",
        entity_type="tokenization_proposal",
        entity_id=proposal.id,
        new_value={"asset_id": asset.id, "token_symbol": proposal.token_symbol},
    )
    db.commit()
    db.refresh(proposal)
    return proposal


@router.post("/proposals/{proposal_id}/decision")
def decide_tokenization_proposal(
    proposal_id: int,
    decision_data: ProposalDecision,
    db: Session = Depends(get_db),
    reviewer: User = Depends(require_super_admin),
):
    proposal = db.query(TokenizationProposal).filter(
        TokenizationProposal.id == proposal_id
    ).with_for_update().first()
    if proposal is None:
        raise HTTPException(status_code=404, detail="Tokenisation proposal not found.")
    if proposal.status != "PENDING_REVIEW":
        raise HTTPException(status_code=409, detail="Proposal is not awaiting review.")
    if proposal.submitted_by_user_id == reviewer.id:
        raise HTTPException(status_code=403, detail="Proposal submitters cannot approve their own proposal.")
    status_by_decision = {
        "APPROVED": "APPROVED",
        "REJECTED": "REJECTED",
        "REQUEST_CHANGES": "CHANGES_REQUESTED",
        "ADDITIONAL_DOCUMENTATION": "ADDITIONAL_DOCUMENTATION",
    }
    proposal.status = status_by_decision[decision_data.decision]
    proposal.review_comments = decision_data.comments.strip()
    proposal.reviewed_by_user_id = reviewer.id
    proposal.reviewed_at = datetime.now(timezone.utc)
    record_approval(
        db,
        asset_id=proposal.asset_id,
        user_id=reviewer.id,
        stage="TOKENISATION_PROPOSAL",
        decision=decision_data.decision,
        comments=decision_data.comments.strip(),
    )
    db.commit()
    return {"proposal_id": proposal.id, "status": proposal.status}


@router.post("/properties/{asset_id}/final-authorization")
def final_authorization(
    asset_id: int,
    authorization_data: FinalAuthorization,
    db: Session = Depends(get_db),
    authorizer: User = Depends(require_super_admin),
):
    asset = _property(db, asset_id)
    if asset.status != "Verified":
        raise HTTPException(status_code=409, detail="Property must be verified and not yet issued.")
    proposal = db.query(TokenizationProposal).filter(
        TokenizationProposal.asset_id == asset.id
    ).first()
    stages = _approval_statuses(db, asset, proposal)
    incomplete = [
        item["stage"]
        for item in stages[:-1]
        if not item["complete"]
    ]
    if incomplete:
        raise HTTPException(
            status_code=409,
            detail=f"Final authorization is blocked; incomplete stages: {', '.join(incomplete)}.",
        )
    if authorization_data.decision == "APPROVED":
        if db.query(TokenIssuance).filter(TokenIssuance.asset_id == asset.id).first():
            raise HTTPException(status_code=409, detail="This property already has a token issuance.")
        if proposal.reviewed_by_user_id == authorizer.id:
            raise HTTPException(
                status_code=403,
                detail="The proposal reviewer cannot grant final authorization.",
            )
    elif proposal is not None:
        proposal.status = (
            "REJECTED"
            if authorization_data.decision == "REJECTED"
            else "CHANGES_REQUESTED"
            if authorization_data.decision == "REQUEST_CHANGES"
            else "ADDITIONAL_DOCUMENTATION"
        )
        proposal.review_comments = authorization_data.comments.strip()
    record_approval(
        db,
        asset_id=asset.id,
        user_id=authorizer.id,
        stage="FINAL_AUTHORIZATION",
        decision=authorization_data.decision,
        comments=authorization_data.comments.strip(),
    )
    record_audit_event(
        db,
        user=authorizer,
        action=f"FINAL_TOKENIZATION_AUTHORIZATION_{authorization_data.decision}",
        entity_type="property",
        entity_id=asset.id,
    )
    db.commit()
    return {
        "asset_id": asset.id,
        "decision": authorization_data.decision,
        "message": (
            "Final authorisation recorded."
            if authorization_data.decision == "APPROVED"
            else "Decision recorded; the property must return to the relevant stage before proceeding."
        ),
    }
