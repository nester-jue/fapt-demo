from pydantic import BaseModel, Field


class AssetRejectRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


class AssetApproveRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)