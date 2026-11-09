from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class TokenIssuanceCreate(BaseModel):
    token_name: str = Field(
        min_length=2,
        max_length=150
    )

    token_symbol: str = Field(
        min_length=2,
        max_length=20,
        pattern=r"^[A-Z0-9_-]+$"
    )

    token_price: Decimal = Field(
        gt=0,
        max_digits=18,
        decimal_places=8
    )
    total_supply: Decimal = Field(gt=0, max_digits=28, decimal_places=8)
    decimal_precision: int = Field(ge=0, le=8)
    currency: str = Field(min_length=3, max_length=10)
    minimum_investment: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    maximum_investment: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=2
    )
    issuance_date: date
    issuance_terms: str = Field(min_length=10, max_length=10000)
    restrictions: str = Field(min_length=3, max_length=10000)
    proposed_tokenisation_arrangements: str = Field(min_length=10, max_length=10000)
    token_rights_description: str = Field(min_length=10, max_length=5000)


class TokenTransferCreate(BaseModel):
    issuance_id: int = Field(
        gt=0
    )

    recipient_user_id: int = Field(
        gt=0
    )

    amount: Decimal = Field(
        gt=0,
        max_digits=28,
        decimal_places=8
    )
    idempotency_key: str = Field(min_length=8, max_length=100)