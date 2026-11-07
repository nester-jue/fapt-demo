from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.sql import func

from database import Base


class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)

    asset_code = Column(String(50), unique=True, nullable=False, index=True)

    name = Column(String(150), nullable=False)

    category = Column(String(100), nullable=False)

    description = Column(Text, nullable=True)

    location = Column(String(200), nullable=True)

    country = Column(String(100), nullable=True)

    jurisdiction = Column(String(100), nullable=True)

    registration_number = Column(String(100), nullable=True)

    registration_number_key = Column(String(100), nullable=True)

    property_size = Column(Numeric(18, 2), nullable=True)

    property_size_unit = Column(String(30), nullable=True)

    estimated_value = Column(Numeric(18, 2), nullable=False)

    currency = Column(String(10), default="USD", nullable=False)

    owner_name = Column(String(150), nullable=False)

    status = Column(String(50), default="Pending Review", nullable=False)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    reviewed_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True
    )

    reviewed_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    rejection_reason = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


Index(
    "uq_assets_registration_number_key",
    Asset.registration_number_key,
    unique=True,
)