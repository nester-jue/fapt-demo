import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ["JWT_SECRET_KEY"] = "test-only-secret-key-with-at-least-32-bytes"
os.environ["DATABASE_URL"] = "sqlite://"

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from models.user import User
from routes import auth as auth_routes
from services.auth import JWT_ALGORITHM, JWT_SECRET_KEY, create_access_token, hash_password
from services.dependencies import get_current_user


class SecurityApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.session_factory() as db:
            self.password_hash = hash_password("Correct horse battery staple 93!")
            self.users = {}
            for role in (
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
            ):
                user = User(
                    full_name=f"Test {role}",
                    email=f"{role}@example.com",
                    hashed_password=self.password_hash,
                    role=role,
                    is_active=True,
                )
                db.add(user)
                db.flush()
                self.users[role] = user.id
            db.commit()

        def override_db():
            db = self.session_factory()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides.pop(get_current_user, None)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def token_for(self, role):
        return create_access_token(self.users[role])

    def auth_headers(self, role):
        return {"Authorization": f"Bearer {self.token_for(role)}"}

    def test_registration_hashes_password_and_does_not_expose_hash(self):
        response = self.client.post(
            "/auth/register",
            json={
                "full_name": "New Investor",
                "email": "new-investor@example.com",
                "password": "Registration password 93!",
                "role": "investor",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertNotIn("hashed_password", response.json())
        with self.session_factory() as db:
            user = db.query(User).filter_by(email="new-investor@example.com").one()
            self.assertNotEqual(user.hashed_password, "Registration password 93!")

    def test_invalid_registration_and_privileged_role_escalation_are_rejected(self):
        invalid = self.client.post(
            "/auth/register",
            json={
                "full_name": "A",
                "email": "not-an-email",
                "password": "short",
                "role": "super_admin",
            },
        )
        self.assertEqual(invalid.status_code, 422)
        self.assertNotIn("not-an-email", invalid.text)

        escalation = self.client.post(
            "/auth/register",
            json={
                "full_name": "Privilege Escalation",
                "email": "escalation@example.com",
                "password": "Registration password 93!",
                "role": "super_admin",
            },
        )
        self.assertEqual(escalation.status_code, 422)

    def test_duplicate_account_is_rejected(self):
        payload = {
            "full_name": "Duplicate Investor",
            "email": "investor@example.com",
            "password": "Registration password 93!",
            "role": "investor",
        }
        response = self.client.post("/auth/register", json=payload)
        self.assertEqual(response.status_code, 409)

    def test_valid_login_returns_expiring_token_and_profile(self):
        response = self.client.post(
            "/auth/login",
            json={
                "email": "investor@example.com",
                "password": "Correct horse battery staple 93!",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["token_type"], "bearer")
        profile = self.client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {response.json()['access_token']}"},
        )
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertNotIn("hashed_password", profile.json())

    def test_incorrect_password_is_rejected(self):
        response = self.client.post(
            "/auth/login",
            json={"email": "investor@example.com", "password": "incorrect"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid email or password.")

    def test_suspended_account_cannot_log_in_or_use_existing_token(self):
        with self.session_factory() as db:
            user = db.get(User, self.users["investor"])
            user.is_active = False
            db.commit()

        login = self.client.post(
            "/auth/login",
            json={
                "email": "investor@example.com",
                "password": "Correct horse battery staple 93!",
            },
        )
        self.assertEqual(login.status_code, 403)
        profile = self.client.get(
            "/auth/me",
            headers=self.auth_headers("investor"),
        )
        self.assertEqual(profile.status_code, 401)

    def test_expired_authentication_token_is_rejected(self):
        expired = jwt.encode(
            {
                "sub": str(self.users["investor"]),
                "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
            },
            JWT_SECRET_KEY,
            algorithm=JWT_ALGORITHM,
        )
        response = self.client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {expired}"},
        )
        self.assertEqual(response.status_code, 401)

    def test_login_failures_are_rate_limited_per_client_ip(self):
        with patch.object(auth_routes, "LOGIN_FAILURE_LIMIT", 2):
            for _ in range(2):
                response = self.client.post(
                    "/auth/login",
                    json={
                        "email": "investor@example.com",
                        "password": "incorrect",
                    },
                )
                self.assertEqual(response.status_code, 401)

            limited = self.client.post(
                "/auth/login",
                json={
                    "email": "investor@example.com",
                    "password": "incorrect",
                },
            )
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.headers["Retry-After"], "900")

    def test_role_permissions_and_unauthenticated_access(self):
        unauthenticated = self.client.get("/admin/users")
        self.assertEqual(unauthenticated.status_code, 401)
        purchase_without_auth = self.client.post(
            "/marketplace/purchases",
            json={
                "issuance_id": 1,
                "quantity": "1",
                "idempotency_key": "unauthorized-purchase",
            },
        )
        self.assertEqual(purchase_without_auth.status_code, 401)
        transfer_without_auth = self.client.post(
            "/tokens/transfers",
            json={
                "issuance_id": 1,
                "recipient_user_id": 2,
                "amount": "1",
                "idempotency_key": "unauthorized-transfer",
            },
        )
        self.assertEqual(transfer_without_auth.status_code, 401)

        for role in self.users:
            with self.subTest(role=role):
                headers = self.auth_headers(role)
                self.assertEqual(self.client.get("/auth/me", headers=headers).status_code, 200)
                expected_admin_status = 200 if role == "super_admin" else 403
                self.assertEqual(
                    self.client.get("/admin/users", headers=headers).status_code,
                    expected_admin_status,
                )
                expected_audit_status = (
                    200 if role in {"super_admin", "auditor"} else 403
                )
                self.assertEqual(
                    self.client.get(
                        "/admin/ledger/audit-events",
                        headers=headers,
                    ).status_code,
                    expected_audit_status,
                )

    def test_cors_is_origin_scoped_and_oversized_requests_are_rejected(self):
        allowed = self.client.options(
            "/auth/login",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertEqual(
            allowed.headers.get("access-control-allow-origin"),
            "http://localhost:5173",
        )

        denied = self.client.options(
            "/auth/login",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertNotIn("access-control-allow-origin", denied.headers)

        too_large = self.client.post(
            "/auth/login",
            headers={"Content-Length": str(12 * 1024 * 1024)},
        )
        self.assertEqual(too_large.status_code, 413)

    def test_database_url_escapes_password_credentials(self):
        from database import _database_url

        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "",
                "DB_HOST": "db.example.test",
                "DB_USER": "nexa",
                "DB_PASSWORD": "safe@password/with:separators",
                "DB_NAME": "nexa",
                "DB_PORT": "5432",
            },
        ):
            parsed = make_url(_database_url())
        self.assertEqual(parsed.password, "safe@password/with:separators")


if __name__ == "__main__":
    unittest.main()
