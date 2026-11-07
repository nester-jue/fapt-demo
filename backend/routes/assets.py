import hashlib
import os
from pathlib import Path
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    status,
    Body,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from database import get_db
from models.asset import Asset
from models.user import User
from models.asset_review_log import AssetReviewLog
from models.property_document import PropertyDocument
from schemas.asset import AssetCreate, AssetResponse
from schemas.user_admin import PropertyDocumentResponse
from routes.auth import get_current_user, require_admin
from services.audit import record_audit_event
from services.authorization import has_role, require_roles
from services.property_workflow import decide_property_verification
from services.tokenization_workflow import record_approval


router = APIRouter(prefix="/assets", tags=["Assets"])
DOCUMENTS_DIR = Path(
    os.getenv(
        "PROPERTY_DOCUMENTS_DIR",
        str(Path(__file__).resolve().parents[1] / "property_documents"),
    )
)
MAX_DOCUMENT_SIZE = 10 * 1024 * 1024
ALLOWED_DOCUMENTS = {
    ".pdf": ("application/pdf", lambda data: data.startswith(b"%PDF-")),
    ".png": ("image/png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    ".jpg": ("image/jpeg", lambda data: data.startswith(b"\xff\xd8\xff")),
    ".jpeg": ("image/jpeg", lambda data: data.startswith(b"\xff\xd8\xff")),
}


def generate_asset_code():
    return f"NEXA-AST-{uuid4().hex[:8].upper()}"


def _owned_property(
    db: Session,
    asset_id: int,
    user: User,
) -> Asset:
    asset = (
        db.query(Asset)
        .filter(Asset.id == asset_id, Asset.user_id == user.id)
        .first()
    )
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found.",
        )
    return asset


def _property_document_access(
    db: Session,
    document_id: int,
    user: User,
) -> tuple[PropertyDocument, Asset]:
    result = (
        db.query(PropertyDocument, Asset)
        .join(Asset, PropertyDocument.asset_id == Asset.id)
        .filter(PropertyDocument.id == document_id)
        .first()
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property document not found.",
        )
    document, asset = result
    if document.document_type != "PROPERTY_SUPPORT":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property document not found.",
        )
    if (
        asset.user_id != user.id
        and not has_role(user, "property_verifier", "super_admin")
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property document not found.",
        )
    return document, asset


# REGISTER ASSET

@router.post(
    "/",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED
)
def register_asset(
    asset_data: AssetCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("investor", "property_owner")),
):
    registration_number = asset_data.registration_number.strip()
    registration_number_key = registration_number.lower()
    existing_property = (
        db.query(Asset.id)
        .filter(Asset.registration_number_key == registration_number_key)
        .first()
    )
    if existing_property is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A property with this registration reference already exists.",
        )

    new_asset = Asset(
        asset_code=generate_asset_code(),
        name=asset_data.name,
        category=asset_data.category,
        description=asset_data.description,
        location=asset_data.location,
        country=asset_data.country.strip(),
        jurisdiction=asset_data.jurisdiction.strip(),
        registration_number=registration_number,
        registration_number_key=registration_number_key,
        property_size=asset_data.property_size,
        property_size_unit=asset_data.property_size_unit.strip(),
        estimated_value=asset_data.estimated_value,
        currency=asset_data.currency,
        owner_name=asset_data.owner_name,
        status="DRAFT",
        user_id=current_user.id
    )

    try:
        db.add(new_asset)
        db.flush()
        record_audit_event(
            db,
            user=current_user,
            action="PROPERTY_DRAFT_CREATED",
            entity_type="property",
            entity_id=new_asset.id,
            request=request,
            new_value={"asset_code": new_asset.asset_code, "status": new_asset.status},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A property with this registration reference already exists.",
        ) from None
    db.refresh(new_asset)

    return new_asset


@router.post("/{asset_id}/documents", status_code=status.HTTP_201_CREATED)
async def upload_property_document(
    asset_id: int,
    request: Request,
    document: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("investor", "property_owner")),
):
    asset = _owned_property(db, asset_id, current_user)
    if asset.status not in {"DRAFT", "Additional Information Required"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Documents can only be uploaded to a draft or returned property.",
        )

    original_filename = Path(
        (document.filename or "").replace("\\", "/")
    ).name.strip()
    extension = Path(original_filename).suffix.lower()
    expected = ALLOWED_DOCUMENTS.get(extension)
    if not original_filename or len(original_filename) > 255 or expected is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF, PNG, and JPEG documents are accepted.",
        )

    expected_type, validate_signature = expected
    if document.content_type != expected_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The uploaded document type does not match its file extension.",
        )

    storage_key = f"{uuid4().hex}{extension}"
    temporary_path = DOCUMENTS_DIR / f"{uuid4().hex}.tmp"
    stored_path = DOCUMENTS_DIR / storage_key
    digest = hashlib.sha256()
    file_size = 0
    signature = b""

    try:
        DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(DOCUMENTS_DIR, 0o700)
        with temporary_path.open("wb") as target:
            while chunk := await document.read(64 * 1024):
                file_size += len(chunk)
                if file_size > MAX_DOCUMENT_SIZE:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Property documents must be 10 MB or smaller.",
                    )
                if len(signature) < 16:
                    signature += chunk[: 16 - len(signature)]
                digest.update(chunk)
                target.write(chunk)

        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Empty documents cannot be uploaded.",
            )
        if not validate_signature(signature):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="The uploaded file content is not a valid supported document.",
            )

        os.replace(temporary_path, stored_path)
        os.chmod(stored_path, 0o600)
        record = PropertyDocument(
            asset_id=asset.id,
            uploaded_by_user_id=current_user.id,
            storage_key=storage_key,
            original_filename=original_filename,
            content_type=expected_type,
            file_size=file_size,
            sha256=digest.hexdigest(),
        )
        db.add(record)
        db.flush()
        record_audit_event(
            db,
            user=current_user,
            action="PROPERTY_DOCUMENT_UPLOADED",
            entity_type="property_document",
            entity_id=record.id,
            request=request,
            new_value={
                "asset_id": asset.id,
                "file_size": file_size,
                "sha256": record.sha256,
            },
        )
        db.commit()
        db.refresh(record)
        return {
            "id": record.id,
            "asset_id": record.asset_id,
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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The property document could not be stored.",
        ) from error
    except SQLAlchemyError as error:
        db.rollback()
        if stored_path.exists():
            stored_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The property document could not be recorded.",
        ) from error
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
        await document.close()


@router.post("/{asset_id}/submit", response_model=AssetResponse)
def submit_property(
    asset_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("investor", "property_owner")),
):
    asset = _owned_property(db, asset_id, current_user)
    if asset.status not in {"DRAFT", "Additional Information Required"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft or returned properties can be submitted.",
        )
    if db.query(PropertyDocument).filter(
        PropertyDocument.asset_id == asset.id
    ).count() < 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Upload at least one supporting document before submission.",
        )

    previous_status = asset.status
    asset.status = "SUBMITTED"
    record_approval(
        db,
        asset_id=asset.id,
        user_id=current_user.id,
        stage="REGISTRATION",
        decision="COMPLETED",
        comments="Required property registration fields and supporting documents submitted.",
    )
    record_audit_event(
        db,
        user=current_user,
        action="PROPERTY_SUBMITTED",
        entity_type="property",
        entity_id=asset.id,
        request=request,
        previous_value={"status": previous_status},
        new_value={"status": asset.status},
    )
    db.commit()
    db.refresh(asset)
    return asset


@router.get(
    "/{asset_id}/documents",
    response_model=list[PropertyDocumentResponse],
)
def list_property_documents(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if asset is None or (
        asset.user_id != current_user.id
        and not has_role(current_user, "property_verifier", "super_admin")
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found.",
        )
    documents = (
        db.query(PropertyDocument)
        .filter(
            PropertyDocument.asset_id == asset_id,
            PropertyDocument.document_type == "PROPERTY_SUPPORT",
        )
        .order_by(PropertyDocument.created_at.desc())
        .all()
    )
    return [
        {
            "id": item.id,
            "asset_id": item.asset_id,
            "uploaded_by_user_id": item.uploaded_by_user_id,
            "original_filename": item.original_filename,
            "content_type": item.content_type,
            "file_size": item.file_size,
            "sha256": item.sha256,
        }
        for item in documents
    ]


@router.get("/documents/{document_id}/download")
def download_property_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record, _asset = _property_document_access(db, document_id, current_user)
    storage_root = DOCUMENTS_DIR.resolve()
    file_path = (storage_root / record.storage_key).resolve()
    if file_path.parent != storage_root or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored property document is unavailable.",
        )
    return FileResponse(
        path=file_path,
        media_type=record.content_type,
        filename=record.original_filename,
    )


# ADMIN: VIEW ALL ASSETS

@router.get(
    "/admin/all",
    response_model=list[AssetResponse]
)
def admin_list_assets(
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin)
):
    return (
        db.query(Asset)
        .order_by(Asset.created_at.desc())
        .all()
    )


# ADMIN: APPROVE ASSET

@router.post(
    "/admin/{asset_id}/approve",
    response_model=AssetResponse
)
def approve_asset(
    asset_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_roles("property_verifier", "super_admin")),
):
    asset = db.query(Asset).filter(
        Asset.id == asset_id
    ).first()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found."
        )

    return decide_property_verification(
        db,
        asset=asset,
        verifier=current_admin,
        decision="APPROVED",
        comments="Verification approved.",
        request=request,
    )


# ADMIN: REJECT ASSET

@router.post(
    "/admin/{asset_id}/reject",
    response_model=AssetResponse
)
def reject_asset(
    asset_id: int,
    request: Request,
    reason: str = Body(..., embed=True, min_length=3),
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_roles("property_verifier", "super_admin")),
):
    if len(reason.strip()) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Rejection reason must contain at least 3 characters."
        )

    asset = db.query(Asset).filter(
        Asset.id == asset_id
    ).first()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found."
        )

    return decide_property_verification(
        db,
        asset=asset,
        verifier=current_admin,
        decision="REJECTED",
        comments=reason,
        request=request,
    )


# INVESTOR: VIEW OWN ASSETS

@router.get(
    "/",
    response_model=list[AssetResponse]
)
def list_assets(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("investor", "property_owner")),
):
    return (
        db.query(Asset)
        .filter(Asset.user_id == current_user.id)
        .order_by(Asset.created_at.desc())
        .all()
    )


# INVESTOR: VIEW INDIVIDUAL ASSET

@router.get(
    "/{asset_id}",
    response_model=AssetResponse
)
def get_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("investor", "property_owner")),
):
    asset = (
        db.query(Asset)
        .filter(
            Asset.id == asset_id,
            Asset.user_id == current_user.id
        )
        .first()
    )

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found."
        )

    return asset