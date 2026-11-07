from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AssetCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    category: str = Field(min_length=2, max_length=100)
    description: str = Field(min_length=1, max_length=5000)
    location: str = Field(min_length=2, max_length=200)
    country: str = Field(min_length=2, max_length=100)
    jurisdiction: str = Field(min_length=2, max_length=100)
    registration_number: str = Field(min_length=1, max_length=100)
    property_size: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    property_size_unit: str = Field(min_length=1, max_length=30)
    estimated_value: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(default="USD", max_length=10)
    owner_name: str = Field(min_length=2, max_length=150)

    @field_validator("registration_number")
    @classmethod
    def normalize_registration_number(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("A property registration reference is required.")
        return normalized


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_code: str
    name: str
    category: str
    description: str | None
    location: str | None
    country: str | None
    jurisdiction: str | None
    registration_number: str | None
    property_size: Decimal | None
    property_size_unit: str | None
    estimated_value: Decimal
    currency: str
    owner_name: str
    status: str
    user_id: int
    created_at: datetime | None