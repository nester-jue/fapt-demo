import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models.asset import Asset
from models.notification import (
    Notification,
    PropertyManagementRecord,
    PropertyManagerAssignment,
)
from models.property_document import PropertyDocument
from models.user import User
from routes import assets as assets_routes
from routes.auth import get_current_user
from schemas.marketplace import PropertyManagerAssignmentCreate, PropertyManagementRecordCreate
from services.audit import record_audit_event
from services.authorization import require_roles


router = APIRouter(tags=["Property Management"])
ALLOWED_DOCUMENTS = {
    ".pdf": ("application/pdf", lambda data: data.startswith(b"%PDF-")),
    ".png": ("image/png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    ".jpg": ("image/jpeg", lambda data: data.startswith(b"\xff\xd8\xff")),
    ".jpeg": ("image/jpeg", lambda data: data.startswith(b"\xff\xd8\xff")),
}
MAX_DOCUMENT_SIZE = 10 * 1024 * 1024


def _assigned_property(db: Session, asset_id: int, manager: User) -> Asset:
    asset = (
        db.query(Asset)
        .join(PropertyManagerAssignment)
        .filter(
            PropertyManagerAssignment.asset_id == asset_id,
            PropertyManagerAssignment.manager_user_id == manager.id,
            PropertyManagerAssignment.is_active.is_(True),
            Asset.id == asset_id,
        )
        .first()
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="Assigned property not found.")
    return asset


@router.post(
    "/admin/properties/{asset_id}/managers",
    status_code=status.HTTP_201_CREATED,
)
def assign_property_manager(
    asset_id: int,
    assignment: PropertyManagerAssignmentCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("super_admin")),
):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    manager = db.query(User).filter(User.id == assignment.manager_user_id).first()
    if asset is None or manager is None:
        raise HTTPException(status_code=404, detail="Property or manager not found.")
    if manager.role != "property_manager" or not manager.is_active:
        raise HTTPException(status_code=422, detail="An active property manager account is required.")
    current = (
        db.query(PropertyManagerAssignment)
        .filter(
            PropertyManagerAssignment.asset_id == asset_id,
            PropertyManagerAssignment.manager_user_id == manager.id,
            PropertyManagerAssignment.is_active.is_(True),
        )
        .first()
    )
    if current:
        raise HTTPException(status_code=409, detail="This manager is already assigned.")
    record = PropertyManagerAssignment(
        asset_id=asset_id,
        manager_user_id=manager.id,
        assigned_by_user_id=admin.id,
        is_active=True,
    )
    db.add(record)
    db.add(
        Notification(
            user_id=manager.id,
            event_type="PROPERTY_MANAGER_ASSIGNED",
            message=f"You have been assigned to manage {asset.name}.",
            entity_type="property",
            entity_id=str(asset.id),
        )
    )
    record_audit_event(
        db,
        user=admin,
        action="PROPERTY_MANAGER_ASSIGNED",
        entity_type="property",
        entity_id=asset.id,
        request=request,
        new_value={"manager_user_id": manager.id},
    )
    db.commit()
    db.refresh(record)
    return {
        "id": record.id,
        "asset_id": asset.id,
        "manager_user_id": manager.id,
        "is_active": record.is_active,
        "created_at": record.created_at,
    }


@router.get("/admin/properties/{asset_id}/managers")
def list_property_managers(
    asset_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles("super_admin")),
):
    rows = (
        db.query(PropertyManagerAssignment, User)
        .join(User, User.id == PropertyManagerAssignment.manager_user_id)
        .filter(
            PropertyManagerAssignment.asset_id == asset_id,
            PropertyManagerAssignment.is_active.is_(True),
        )
        .order_by(User.full_name)
        .all()
    )
    return [
        {
            "assignment_id": assignment.id,
            "manager_user_id": manager.id,
            "manager_name": manager.full_name,
            "email": manager.email,
        }
        for assignment, manager in rows
    ]


@router.get("/property-management/properties")
def assigned_properties(
    db: Session = Depends(get_db),
    manager: User = Depends(require_roles("property_manager")),
):
    rows = (
        db.query(Asset)
        .join(PropertyManagerAssignment)
        .filter(
            PropertyManagerAssignment.manager_user_id == manager.id,
            PropertyManagerAssignment.is_active.is_(True),
        )
        .order_by(Asset.name)
        .all()
    )
    return [
        {
            "id": asset.id,
            "asset_code": asset.asset_code,
            "name": asset.name,
            "location": asset.location,
            "country": asset.country,
            "category": asset.category,
            "status": asset.status,
        }
        for asset in rows
    ]


@router.get("/property-management/properties/{asset_id}/records")
def list_management_records(
    asset_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    manager: User = Depends(require_roles("property_manager")),
):
    asset = _assigned_property(db, asset_id, manager)
    record_query = db.query(PropertyManagementRecord).filter(
        PropertyManagementRecord.asset_id == asset.id
    )
    income = dict(
        db.query(
            PropertyManagementRecord.currency,
            func.coalesce(func.sum(PropertyManagementRecord.amount), 0),
        )
        .filter(
            PropertyManagementRecord.asset_id == asset.id,
            PropertyManagementRecord.record_type == "RENTAL_INCOME",
            PropertyManagementRecord.currency.is_not(None),
        )
        .group_by(PropertyManagementRecord.currency)
        .all()
    )
    expenses = dict(
        db.query(
            PropertyManagementRecord.currency,
            func.coalesce(func.sum(PropertyManagementRecord.amount), 0),
        )
        .filter(
            PropertyManagementRecord.asset_id == asset.id,
            PropertyManagementRecord.record_type == "OPERATING_EXPENSE",
            PropertyManagementRecord.currency.is_not(None),
        )
        .group_by(PropertyManagementRecord.currency)
        .all()
    )
    currencies = set(income) | set(expenses)
    maintenance_count = (
        record_query.filter(
            PropertyManagementRecord.record_type == "MAINTENANCE"
        ).count()
    )
    total = record_query.count()
    records = (
        record_query
        .order_by(PropertyManagementRecord.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return {
        "asset": {"id": asset.id, "name": asset.name},
        "performance": {
            "rental_income_by_currency": {
                currency: format(Decimal(str(income.get(currency, 0))), "f")
                for currency in currencies
            },
            "operating_expenses_by_currency": {
                currency: format(Decimal(str(expenses.get(currency, 0))), "f")
                for currency in currencies
            },
            "net_operating_result_by_currency": {
                currency: format(
                    Decimal(str(income.get(currency, 0)))
                    - Decimal(str(expenses.get(currency, 0))),
                    "f",
                )
                for currency in currencies
            },
            "maintenance_count": maintenance_count,
        },
        "skip": skip,
        "limit": limit,
        "total": total,
        "records": [
            {
                "id": record.id,
                "record_type": record.record_type,
                "description": record.description,
                "amount": record.amount,
                "currency": record.currency,
                "document_ids": json.loads(record.document_ids),
                "created_at": record.created_at,
            }
            for record in records
        ],
    }


@router.post(
    "/property-management/properties/{asset_id}/records",
    status_code=status.HTTP_201_CREATED,
)
def create_management_record(
    asset_id: int,
    data: PropertyManagementRecordCreate,
    request: Request,
    db: Session = Depends(get_db),
    manager: User = Depends(require_roles("property_manager")),
):
    asset = _assigned_property(db, asset_id, manager)
    requires_amount = data.record_type in {"RENTAL_INCOME", "OPERATING_EXPENSE"}
    if requires_amount and (data.amount is None or data.currency is None):
        raise HTTPException(status_code=422, detail="Income and expense records require amount and currency.")
    documents = (
        db.query(PropertyDocument)
        .filter(
            PropertyDocument.asset_id == asset.id,
            PropertyDocument.id.in_(data.document_ids),
            PropertyDocument.document_type == "MAINTENANCE",
        )
        .all()
        if data.document_ids
        else []
    )
    if len(documents) != len(set(data.document_ids)):
        raise HTTPException(status_code=422, detail="Documents must be maintenance files for this assigned property.")
    record = PropertyManagementRecord(
        asset_id=asset.id,
        manager_user_id=manager.id,
        record_type=data.record_type,
        description=data.description.strip(),
        amount=data.amount,
        currency=data.currency.upper() if data.currency else None,
        document_ids=json.dumps(data.document_ids),
    )
    db.add(record)
    record_audit_event(
        db,
        user=manager,
        action=f"PROPERTY_MANAGEMENT_{data.record_type}",
        entity_type="property",
        entity_id=asset.id,
        request=request,
        new_value={
            "record_type": data.record_type,
            "amount": str(data.amount) if data.amount is not None else None,
            "currency": data.currency,
        },
    )
    db.commit()
    db.refresh(record)
    return {"id": record.id, "record_type": record.record_type, "created_at": record.created_at}


@router.post(
    "/property-management/properties/{asset_id}/documents",
    status_code=status.HTTP_201_CREATED,
)
async def upload_maintenance_document(
    asset_id: int,
    request: Request,
    document: UploadFile = File(...),
    db: Session = Depends(get_db),
    manager: User = Depends(require_roles("property_manager")),
):
    asset = _assigned_property(db, asset_id, manager)
    filename = Path((document.filename or "").replace("\\", "/")).name.strip()
    expected = ALLOWED_DOCUMENTS.get(Path(filename).suffix.lower())
    if not filename or len(filename) > 255 or expected is None:
        raise HTTPException(status_code=415, detail="Only PDF, PNG and JPEG files are accepted.")
    content_type, validate_signature = expected
    if document.content_type != content_type:
        raise HTTPException(status_code=415, detail="Document type does not match file extension.")
    storage_key = f"{uuid4().hex}{Path(filename).suffix.lower()}"
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
                    raise HTTPException(status_code=413, detail="Documents must be 10 MB or smaller.")
                if len(signature) < 16:
                    signature += chunk[: 16 - len(signature)]
                digest.update(chunk)
                target.write(chunk)
        if not file_size or not validate_signature(signature):
            raise HTTPException(status_code=415, detail="The file is empty or invalid.")
        os.replace(temporary_path, stored_path)
        os.chmod(stored_path, 0o600)
        record = PropertyDocument(
            asset_id=asset.id,
            uploaded_by_user_id=manager.id,
            document_type="MAINTENANCE",
            storage_key=storage_key,
            original_filename=filename,
            content_type=content_type,
            file_size=file_size,
            sha256=digest.hexdigest(),
        )
        db.add(record)
        record_audit_event(
            db,
            user=manager,
            action="PROPERTY_MAINTENANCE_DOCUMENT_UPLOADED",
            entity_type="property",
            entity_id=asset.id,
            request=request,
            new_value={"document_type": "MAINTENANCE"},
        )
        db.commit()
        db.refresh(record)
        return {
            "id": record.id,
            "document_type": record.document_type,
            "original_filename": record.original_filename,
            "sha256": record.sha256,
        }
    except Exception:
        db.rollback()
        if stored_path.exists():
            stored_path.unlink()
        raise
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
        await document.close()


@router.get("/property-management/documents/{document_id}/download")
def download_maintenance_document(
    document_id: int,
    db: Session = Depends(get_db),
    manager: User = Depends(require_roles("property_manager")),
):
    document = (
        db.query(PropertyDocument)
        .join(
            PropertyManagerAssignment,
            PropertyManagerAssignment.asset_id == PropertyDocument.asset_id,
        )
        .filter(
            PropertyDocument.id == document_id,
            PropertyDocument.document_type == "MAINTENANCE",
            PropertyManagerAssignment.manager_user_id == manager.id,
            PropertyManagerAssignment.is_active.is_(True),
        )
        .first()
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Assigned maintenance document not found.")
    root = assets_routes.DOCUMENTS_DIR.resolve()
    path = (root / document.storage_key).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(status_code=404, detail="Stored document is unavailable.")
    return FileResponse(path, media_type=document.content_type, filename=document.original_filename)
