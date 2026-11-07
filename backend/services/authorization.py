from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from models.user import User
from services.dependencies import get_current_user


SUPER_ADMIN_ROLES = {"admin", "super_admin"}
AVAILABLE_ROLES = {
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
}


def has_role(user: User, *roles: str) -> bool:
    if user.role == "admin":
        return "super_admin" in roles
    return user.role in roles


def require_roles(*roles: str) -> Callable:
    def role_dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if not has_role(current_user, *roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return role_dependency
