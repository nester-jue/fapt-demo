from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from database import Base, DATABASE_URL
from models.asset import Asset
from models.asset_review_log import AssetReviewLog
from models.audit_event import AuditEvent
from models.property_document import PropertyDocument
from models.property_verification import PropertyVerification
from models.property_valuation import PropertyValuation
from models.legal_review import LegalReview
from models.investor_compliance import ComplianceReviewHistory, InvestorCompliance
from models.tokenization_proposal import TokenizationApproval, TokenizationProposal
from models.token_holding import TokenHolding
from models.token_issuance import TokenIssuance
from models.token_transaction import TokenTransaction
from models.user import User
from models.notification import Notification, PropertyManagementRecord, PropertyManagerAssignment

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(DATABASE_URL, poolclass=NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
