from models.investor_compliance import InvestorCompliance
from models.user import User
from sqlalchemy.orm import Session


def is_eligible_investor(db: Session, user_id: int) -> bool:
    record = (
        db.query(InvestorCompliance)
        .filter(InvestorCompliance.user_id == user_id)
        .first()
    )
    return bool(
        record
        and record.is_eligible
        and record.eligibility_status == "APPROVED"
        and record.kyc_status == "APPROVED"
        and record.aml_status == "APPROVED"
        and record.identity_verification_status == "APPROVED"
    )


def require_eligible_investor(db: Session, user: User) -> bool:
    return bool(
        user.is_active
        and user.role == "investor"
        and is_eligible_investor(db, user.id)
    )
