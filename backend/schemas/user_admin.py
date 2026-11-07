from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ManagedRole = Literal[
    "super_admin",
    "property_owner",
    "property_verifier",
    "property_valuer",
    "legal_advisor",
    "compliance_officer",
    "tokenization_officer",
    "investor",
    "property_manager",
    "auditor",
]


class UserRoleUpdate(BaseModel):
    role: ManagedRole


class UserStatusUpdate(BaseModel):
    is_active: bool


class ManagedUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    role: str
    is_active: bool


class PropertyDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    uploaded_by_user_id: int
    original_filename: str
    content_type: str
    file_size: int
    sha256: str


class VerificationDecisionRequest(BaseModel):
    comments: str = Field(min_length=3, max_length=4000)
    supporting_references: list[str] = Field(default_factory=list, max_length=20)
