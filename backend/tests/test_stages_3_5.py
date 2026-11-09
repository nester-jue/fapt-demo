import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ["JWT_SECRET_KEY"] = "test-only-secret-key-with-at-least-32-bytes"
os.environ["DATABASE_URL"] = "sqlite://"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from models.asset import Asset
from models.audit_event import AuditEvent
from models.property_document import PropertyDocument
from models.property_verification import PropertyVerification
from models.user import User
from routes import assets as assets_routes
from services.dependencies import get_current_user


class StageThreeToFiveApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )
        db = self.session_factory()
        self.owner = User(
            full_name="Property Owner",
            email="owner@example.test",
            hashed_password="test-hash",
            role="property_owner",
            is_active=True,
        )
        self.verifier = User(
            full_name="Property Verifier",
            email="verifier@example.test",
            hashed_password="test-hash",
            role="property_verifier",
            is_active=True,
        )
        self.investor = User(
            full_name="Investor",
            email="investor@example.test",
            hashed_password="test-hash",
            role="investor",
            is_active=True,
        )
        self.admin = User(
            full_name="Platform Admin",
            email="admin@example.test",
            hashed_password="test-hash",
            role="admin",
            is_active=True,
        )
        db.add_all([self.owner, self.verifier, self.investor, self.admin])
        db.commit()
        self.owner_id = self.owner.id
        self.verifier_id = self.verifier.id
        self.investor_id = self.investor.id
        self.admin_id = self.admin.id
        db.close()

        self.current_user = self.owner
        self.temp_documents = tempfile.mkdtemp()
        self.previous_documents_dir = assets_routes.DOCUMENTS_DIR
        assets_routes.DOCUMENTS_DIR = Path(self.temp_documents)

        def override_db():
            session = self.session_factory()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: self.current_user
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        assets_routes.DOCUMENTS_DIR = self.previous_documents_dir
        shutil.rmtree(self.temp_documents)
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    @staticmethod
    def property_payload(registration_number="REG-TEST-100"):
        return {
            "name": "Nexa Test Property",
            "category": "Real Estate",
            "description": "A test property used for workflow verification.",
            "location": "Harare",
            "country": "Zimbabwe",
            "jurisdiction": "Zimbabwe",
            "registration_number": registration_number,
            "property_size": "120.50",
            "property_size_unit": "sqm",
            "estimated_value": "100000.00",
            "currency": "USD",
            "owner_name": "Property Owner",
        }

    def register_property(self):
        response = self.client.post(
            "/assets/",
            json=self.property_payload(),
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_property_registration_requires_complete_information_and_unique_reference(self):
        missing_fields = self.client.post(
            "/assets/",
            json={"name": "Incomplete property"},
        )
        self.assertEqual(missing_fields.status_code, 422)

        self.register_property()
        duplicate = self.client.post(
            "/assets/",
            json=self.property_payload("  reg-test-100  "),
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.text)

        whitespace_reference = self.client.post(
            "/assets/",
            json=self.property_payload("   "),
        )
        self.assertEqual(whitespace_reference.status_code, 422)

    def test_property_document_upload_rejects_bad_types_and_oversized_content(self):
        property_record = self.register_property()
        asset_id = property_record["id"]

        unsupported = self.client.post(
            f"/assets/{asset_id}/documents",
            files={
                "document": (
                    "script.exe",
                    b"MZinvalid",
                    "application/octet-stream",
                )
            },
        )
        self.assertEqual(unsupported.status_code, 415)

        invalid_signature = self.client.post(
            f"/assets/{asset_id}/documents",
            files={"document": ("fake.pdf", b"not a PDF", "application/pdf")},
        )
        self.assertEqual(invalid_signature.status_code, 415)

        oversized = self.client.post(
            f"/assets/{asset_id}/documents",
            files={
                "document": (
                    "large.pdf",
                    b"%PDF-1.7\n" + b"x" * (10 * 1024 * 1024),
                    "application/pdf",
                )
            },
        )
        self.assertEqual(oversized.status_code, 413)

    def attach_document(self, asset_id):
        return self.client.post(
            f"/assets/{asset_id}/documents",
            files={
                "document": (
                    "ownership.pdf",
                    b"%PDF-1.7\nNEXA test ownership document",
                    "application/pdf",
                )
            },
        )

    def test_owner_must_attach_document_before_submission_and_verification(self):
        property_record = self.register_property()
        self.assertEqual(property_record["status"], "DRAFT")

        missing_document = self.client.post(
            f"/assets/{property_record['id']}/submit"
        )
        self.assertEqual(missing_document.status_code, 409)

        uploaded = self.attach_document(property_record["id"])
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        submitted = self.client.post(
            f"/assets/{property_record['id']}/submit"
        )
        self.assertEqual(submitted.status_code, 200, submitted.text)
        self.assertEqual(submitted.json()["status"], "SUBMITTED")

        self.current_user = self.investor
        denied = self.client.get("/admin/assets/pending")
        self.assertEqual(denied.status_code, 403)

        self.current_user = self.verifier
        detail = self.client.get(f"/admin/assets/{property_record['id']}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(len(detail.json()["documents"]), 1)

        approved = self.client.post(
            f"/admin/assets/{property_record['id']}/approve",
            json={"reason": "Ownership evidence checked."},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["status"], "Verified")

        with self.session_factory() as db:
            verification = db.query(PropertyVerification).one()
            self.assertEqual(verification.verifier_user_id, self.verifier_id)
            self.assertEqual(verification.previous_status, "SUBMITTED")
            self.assertEqual(verification.new_status, "Verified")
            self.assertGreater(
                db.query(AuditEvent)
                .filter(AuditEvent.action == "PROPERTY_VERIFICATION_APPROVED")
                .count(),
                0,
            )

    def test_verifier_rejection_is_persisted_and_audited(self):
        property_record = self.register_property()
        self.assertEqual(self.attach_document(property_record["id"]).status_code, 201)
        submitted = self.client.post(f"/assets/{property_record['id']}/submit")
        self.assertEqual(submitted.status_code, 200, submitted.text)

        self.current_user = self.verifier
        rejected = self.client.post(
            f"/admin/assets/{property_record['id']}/reject",
            json={"reason": "The ownership reference could not be confirmed."},
        )
        self.assertEqual(rejected.status_code, 200, rejected.text)
        self.assertEqual(rejected.json()["status"], "Verification Rejected")
        with self.session_factory() as db:
            verification = db.query(PropertyVerification).one()
            self.assertEqual(verification.decision, "REJECTED")
            self.assertEqual(verification.verifier_user_id, self.verifier_id)

    def test_document_access_is_limited_to_owner_and_verifier(self):
        property_record = self.register_property()
        uploaded = self.attach_document(property_record["id"])
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        document_id = uploaded.json()["id"]

        self.current_user = self.investor
        denied = self.client.get(
            f"/assets/documents/{document_id}/download"
        )
        self.assertEqual(denied.status_code, 404)

        self.current_user = self.verifier
        allowed = self.client.get(
            f"/assets/documents/{document_id}/download"
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertTrue(allowed.content.startswith(b"%PDF-"))

    def test_verifier_cannot_review_their_own_property(self):
        property_record = self.register_property()
        self.assertEqual(self.attach_document(property_record["id"]).status_code, 201)
        self.assertEqual(
            self.client.post(
                f"/assets/{property_record['id']}/submit"
            ).status_code,
            200,
        )
        self.owner.role = "property_verifier"
        self.current_user = self.owner
        denied = self.client.post(
            f"/admin/assets/{property_record['id']}/approve",
            json={"reason": "Attempt to self-approve."},
        )
        self.assertEqual(denied.status_code, 403)
        with self.session_factory() as db:
            asset = db.query(Asset).filter_by(id=property_record["id"]).one()
            self.assertEqual(asset.status, "SUBMITTED")

    def test_super_admin_can_change_roles_but_not_their_own(self):
        self.current_user = self.admin
        changed = self.client.patch(
            f"/admin/users/{self.investor_id}/role",
            json={"role": "property_verifier"},
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()["role"], "property_verifier")

        self_denied = self.client.patch(
            f"/admin/users/{self.admin_id}/role",
            json={"role": "investor"},
        )
        self.assertEqual(self_denied.status_code, 403)

        with self.session_factory() as db:
            event = (
                db.query(AuditEvent)
                .filter(
                    AuditEvent.action == "USER_ROLE_CHANGED",
                    AuditEvent.entity_id == str(self.investor_id),
                )
                .one()
            )
            self.assertEqual(event.user_id, self.admin_id)


if __name__ == "__main__":
    unittest.main()
