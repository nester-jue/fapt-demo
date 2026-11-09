from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ReviewDecision = Literal[
    "APPROVED",
    "REJECTED",
    "REQUEST_CHANGES",
    "ADDITIONAL_DOCUMENTATION",
]


class ValuationCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(min_length=3, max_length=10)
    valuation_date: date
    valid_until: date
    methodology: str = Field(min_length=10, max_length=5000)
    report_document_ids: list[int] = Field(min_length=1, max_length=20)


class ValuationDecision(BaseModel):
    decision: ReviewDecision
    comments: str = Field(min_length=3, max_length=4000)


class LegalReviewCreate(BaseModel):
    jurisdiction: str = Field(min_length=2, max_length=100)
    jurisdiction_requirements: str = Field(min_length=10, max_length=10000)
    proposed_tokenisation_arrangements: str = Field(min_length=10, max_length=10000)
    token_rights_description: str = Field(min_length=10, max_length=5000)
    legal_risks: str = Field(min_length=3, max_length=10000)
    comments: str = Field(min_length=3, max_length=4000)
    decision: ReviewDecision
    supporting_document_ids: list[int] = Field(default_factory=list, max_length=20)


ComplianceStatus = Literal[
    "NOT_STARTED",
    "PENDING",
    "UNDER_REVIEW",
    "APPROVED",
    "REJECTED",
    "SUSPENDED",
    "EXPIRED",
]


class RequiredDocumentStatus(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    status: Literal["REQUIRED", "SUBMITTED", "ACCEPTED", "REJECTED"]


class ComplianceDecision(BaseModel):
    decision: Literal["APPROVE", "REJECT", "REQUEST_CHANGES", "SUSPEND", "EXPIRE"]
    kyc_status: ComplianceStatus
    aml_status: ComplianceStatus
    identity_verification_status: ComplianceStatus
    required_documents: list[RequiredDocumentStatus] = Field(max_length=30)
    comments: str = Field(min_length=3, max_length=4000)


class TokenizationProposalCreate(BaseModel):
    token_name: str = Field(min_length=2, max_length=150)
    token_symbol: str = Field(min_length=2, max_length=20, pattern=r"^[A-Z0-9_-]+$")
    token_price: Decimal = Field(gt=0, max_digits=18, decimal_places=8)
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
    disclosures: str = Field(min_length=10, max_length=10000)
    proposed_tokenisation_arrangements: str = Field(min_length=10, max_length=10000)
    token_rights_description: str = Field(min_length=10, max_length=5000)


class ProposalDecision(BaseModel):
    decision: ReviewDecision
    comments: str = Field(min_length=3, max_length=4000)


class FinalAuthorization(BaseModel):
    decision: Literal["APPROVED", "REJECTED", "REQUEST_CHANGES", "ADDITIONAL_DOCUMENTATION"]
    comments: str = Field(min_length=3, max_length=4000)


class WorkflowDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    document_type: str
    original_filename: str
    content_type: str
    file_size: int
    sha256: str


class ComplianceStatusResponse(BaseModel):
    user_id: int
    kyc_status: str
    aml_status: str
    identity_verification_status: str
    eligibility_status: str
    is_eligible: bool
    required_documents: list[dict]
