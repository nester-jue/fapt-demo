from decimal import Decimal

from pydantic import BaseModel, Field


class TokenPurchaseCreate(BaseModel):
    issuance_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=28, decimal_places=8)
    idempotency_key: str = Field(min_length=8, max_length=100)


class PropertyManagementRecordCreate(BaseModel):
    record_type: str = Field(pattern=r"^(MAINTENANCE|RENTAL_INCOME|OPERATING_EXPENSE|PROPERTY_UPDATE)$")
    description: str = Field(min_length=3, max_length=5000)
    amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=10)
    document_ids: list[int] = Field(default_factory=list, max_length=20)


class PropertyManagerAssignmentCreate(BaseModel):
    manager_user_id: int = Field(gt=0)
