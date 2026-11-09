import os
import shutil
import tempfile
import unittest
from datetime import date, timedelta
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
from models.investor_compliance import ComplianceReviewHistory, InvestorCompliance
from models.legal_review import LegalReview
from models.property_valuation import PropertyValuation
from models.token_holding import TokenHolding
from models.token_issuance import TokenIssuance
from models.token_transaction import TokenTransaction
from models.tokenization_proposal import TokenizationApproval, TokenizationProposal
from models.user import User
from routes import assets as assets_routes
from services.dependencies import get_current_user


class StageSixToTenApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.session_factory() as db:
            self.owner = self.make_user(db, "owner", "property_owner")
            self.verifier = self.make_user(db, "verifier", "property_verifier")
            self.valuer = self.make_user(db, "valuer", "property_valuer")
            self.legal = self.make_user(db, "legal", "legal_advisor")
            self.compliance_officer = self.make_user(
                db, "compliance", "compliance_officer"
            )
            self.token_officer = self.make_user(
                db, "token-officer", "tokenization_officer"
            )
            self.proposal_reviewer = self.make_user(
                db, "reviewer", "super_admin"
            )
            self.final_authorizer = self.make_user(
                db, "authorizer", "super_admin"
            )
            self.investor = self.make_user(db, "investor", "investor")
            db.commit()
            self.owner_id = self.owner.id
            self.verifier_id = self.verifier.id
            self.valuer_id = self.valuer.id
            self.legal_id = self.legal.id
            self.compliance_officer_id = self.compliance_officer.id
            self.token_officer_id = self.token_officer.id
            self.proposal_reviewer_id = self.proposal_reviewer.id
            self.final_authorizer_id = self.final_authorizer.id
            self.investor_id = self.investor.id

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

    @staticmethod
    def make_user(db, prefix, role):
        user = User(
            full_name=f"Test {prefix}",
            email=f"{prefix}@example.test",
            hashed_password="test-hash",
            role=role,
            is_active=True,
        )
        db.add(user)
        db.flush()
        return user

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        assets_routes.DOCUMENTS_DIR = self.previous_documents_dir
        shutil.rmtree(self.temp_documents)
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def upload_workflow_document(self, asset_id, document_type):
        return self.client.post(
            f"/workflow/properties/{asset_id}/documents",
            data={"document_type": document_type},
            files={
                "document": (
                    f"{document_type.lower()}.pdf",
                    b"%PDF-1.7\nNEXA workflow test document",
                    "application/pdf",
                )
            },
        )

    def prepare_verified_property(self):
        created = self.client.post(
            "/assets/",
            json={
                "name": "Harare Commercial Centre",
                "category": "Real Estate",
                "description": "A test commercial property for staged approval.",
                "location": "Harare",
                "country": "Zimbabwe",
                "jurisdiction": "Zimbabwe",
                "registration_number": "REG-PHASE-610",
                "property_size": "1200.00",
                "property_size_unit": "sqm",
                "estimated_value": "100000.00",
                "currency": "USD",
                "owner_name": "Test owner",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        asset = created.json()
        support = self.client.post(
            f"/assets/{asset['id']}/documents",
            files={
                "document": (
                    "title.pdf",
                    b"%PDF-1.7\nOwnership support",
                    "application/pdf",
                )
            },
        )
        self.assertEqual(support.status_code, 201, support.text)
        submitted = self.client.post(f"/assets/{asset['id']}/submit")
        self.assertEqual(submitted.status_code, 200, submitted.text)
        self.current_user = self.verifier
        approved = self.client.post(
            f"/admin/assets/{asset['id']}/approve",
            json={"reason": "Property ownership evidence checked."},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        return asset

    def test_end_to_end_valuation_legal_compliance_approval_and_issuance(self):
        asset = self.prepare_verified_property()
        asset_id = asset["id"]

        self.current_user = self.final_authorizer
        skipped = self.client.post(
            f"/workflow/properties/{asset_id}/final-authorization",
            json={"decision": "APPROVED", "comments": "Attempt to skip stages."},
        )
        self.assertEqual(skipped.status_code, 409)

        self.current_user = self.valuer
        report = self.upload_workflow_document(asset_id, "VALUATION_REPORT")
        self.assertEqual(report.status_code, 201, report.text)
        today = date.today()
        valuation_response = self.client.post(
            f"/workflow/properties/{asset_id}/valuations",
            json={
                "amount": "100000.00",
                "currency": "USD",
                "valuation_date": today.isoformat(),
                "valid_until": (today + timedelta(days=365)).isoformat(),
                "methodology": "Comparable market analysis and income approach.",
                "report_document_ids": [report.json()["id"]],
            },
        )
        self.assertEqual(valuation_response.status_code, 201, valuation_response.text)
        valuation_id = valuation_response.json()["id"]
        self.assertEqual(valuation_response.json()["status"], "PENDING_REVIEW")

        self.current_user = self.proposal_reviewer
        decision = self.client.post(
            f"/workflow/valuations/{valuation_id}/decision",
            json={"decision": "APPROVED", "comments": "Independent valuation reviewed."},
        )
        self.assertEqual(decision.status_code, 200, decision.text)

        self.current_user = self.legal
        agreement = self.upload_workflow_document(asset_id, "LEGAL_AGREEMENT")
        self.assertEqual(agreement.status_code, 201, agreement.text)
        legal_decision = self.client.post(
            f"/workflow/properties/{asset_id}/legal-reviews",
            json={
                "jurisdiction": "Zimbabwe",
                "jurisdiction_requirements": (
                    "Applicable local company, securities and property laws "
                    "must be reviewed by qualified counsel."
                ),
                "proposed_tokenisation_arrangements": (
                    "One hundred thousand transferable units, each priced at "
                    "USD one, subject to investor eligibility restrictions."
                ),
                "token_rights_description": (
                    "The token represents only the contractual rights defined "
                    "in the attached agreement, not direct ownership of land."
                ),
                "legal_risks": "Regulatory classification and enforceability risks.",
                "comments": "The agreement and rights wording were reviewed.",
                "decision": "APPROVED",
                "supporting_document_ids": [agreement.json()["id"]],
            },
        )
        self.assertEqual(legal_decision.status_code, 201, legal_decision.text)

        self.current_user = self.owner
        not_eligible = self.client.get("/workflow/compliance/me")
        self.assertEqual(not_eligible.status_code, 200)
        self.assertEqual(not_eligible.json()["eligibility_status"], "NOT_STARTED")
        owner_user_id = asset["user_id"]
        self.current_user = self.compliance_officer
        incomplete_compliance = self.client.post(
            f"/workflow/compliance/users/{owner_user_id}/decision",
            json={
                "decision": "APPROVE",
                "kyc_status": "APPROVED",
                "aml_status": "APPROVED",
                "identity_verification_status": "APPROVED",
                "required_documents": [
                    {"name": "Identity evidence", "status": "SUBMITTED"}
                ],
                "comments": "Attempt approval before all evidence is accepted.",
            },
        )
        self.assertEqual(incomplete_compliance.status_code, 422)
        approved_compliance = self.client.post(
            f"/workflow/compliance/users/{owner_user_id}/decision",
            json={
                "decision": "APPROVE",
                "kyc_status": "APPROVED",
                "aml_status": "APPROVED",
                "identity_verification_status": "APPROVED",
                "required_documents": [
                    {"name": "Identity evidence", "status": "ACCEPTED"},
                    {"name": "Proof of address", "status": "ACCEPTED"},
                ],
                "comments": "Manual demonstration review completed.",
            },
        )
        self.assertEqual(approved_compliance.status_code, 200, approved_compliance.text)
        self.assertTrue(approved_compliance.json()["is_eligible"])

        self.current_user = self.token_officer
        disclosure = self.upload_workflow_document(asset_id, "PROPOSAL_DISCLOSURE")
        self.assertEqual(disclosure.status_code, 201, disclosure.text)
        proposal_response = self.client.post(
            f"/workflow/properties/{asset_id}/proposals",
            json={
                "token_name": "Harare Commercial Centre Token",
                "token_symbol": "HCC",
                "token_price": "1.00",
                "total_supply": "100000",
                "decimal_precision": 0,
                "currency": "USD",
                "minimum_investment": "1.00",
                "maximum_investment": "10000.00",
                "issuance_date": today.isoformat(),
                "issuance_terms": "The simulated tokens follow the approved legal agreement.",
                "restrictions": "Only compliance-approved participants may transfer tokens.",
                "disclosures": "This is a database-backed demonstration, not a blockchain issuance.",
                "proposed_tokenisation_arrangements": (
                    "One hundred thousand transferable units, each priced at "
                    "USD one, subject to investor eligibility restrictions."
                ),
                "token_rights_description": (
                    "The token represents only the contractual rights defined "
                    "in the attached agreement, not direct ownership of land."
                ),
            },
        )
        self.assertEqual(proposal_response.status_code, 201, proposal_response.text)
        proposal_id = proposal_response.json()["id"]

        self.current_user = self.proposal_reviewer
        returned = self.client.post(
            f"/workflow/proposals/{proposal_id}/decision",
            json={
                "decision": "REQUEST_CHANGES",
                "comments": "Clarify the disclosure and return the proposal.",
            },
        )
        self.assertEqual(returned.status_code, 200, returned.text)
        blocked_final = self.client.post(
            f"/workflow/properties/{asset_id}/final-authorization",
            json={"decision": "APPROVED", "comments": "Cannot skip proposal changes."},
        )
        self.assertEqual(blocked_final.status_code, 409)

        self.current_user = self.token_officer
        replacement_disclosure = self.upload_workflow_document(
            asset_id, "PROPOSAL_DISCLOSURE"
        )
        self.assertEqual(replacement_disclosure.status_code, 201)
        revised_proposal = self.client.post(
            f"/workflow/properties/{asset_id}/proposals",
            json={
                "token_name": "Harare Commercial Centre Token",
                "token_symbol": "HCC",
                "token_price": "1.00",
                "total_supply": "100000",
                "decimal_precision": 0,
                "currency": "USD",
                "minimum_investment": "1.00",
                "maximum_investment": "10000.00",
                "issuance_date": today.isoformat(),
                "issuance_terms": "The simulated tokens follow the approved legal agreement.",
                "restrictions": "Only compliance-approved participants may transfer tokens.",
                "disclosures": "This is a database-backed demonstration, not a blockchain issuance.",
                "proposed_tokenisation_arrangements": (
                    "One hundred thousand transferable units, each priced at "
                    "USD one, subject to investor eligibility restrictions."
                ),
                "token_rights_description": (
                    "The token represents only the contractual rights defined "
                    "in the attached agreement, not direct ownership of land."
                ),
            },
        )
        self.assertEqual(revised_proposal.status_code, 201, revised_proposal.text)
        self.assertEqual(revised_proposal.json()["id"], proposal_id)

        self.current_user = self.proposal_reviewer
        proposal_decision = self.client.post(
            f"/workflow/proposals/{proposal_id}/decision",
            json={"decision": "APPROVED", "comments": "Proposal matches approved documents."},
        )
        self.assertEqual(proposal_decision.status_code, 200, proposal_decision.text)
        self_denied = self.client.post(
            f"/workflow/properties/{asset_id}/final-authorization",
            json={"decision": "APPROVED", "comments": "Same reviewer cannot finalize."},
        )
        self.assertEqual(self_denied.status_code, 403)

        self.current_user = self.final_authorizer
        ready = self.client.get(f"/workflow/properties/{asset_id}/readiness")
        self.assertEqual(ready.status_code, 200, ready.text)
        self.assertTrue(all(stage["complete"] for stage in ready.json()["stages"][:-1]))
        final = self.client.post(
            f"/workflow/properties/{asset_id}/final-authorization",
            json={"decision": "APPROVED", "comments": "Final authorization granted."},
        )
        self.assertEqual(final.status_code, 200, final.text)

        self.current_user = self.token_officer
        issuance_data = {
            "token_name": "Harare Commercial Centre Token",
            "token_symbol": "HCC",
            "token_price": "1.00",
            "total_supply": "100000",
            "decimal_precision": 0,
            "currency": "USD",
            "minimum_investment": "1.00",
            "maximum_investment": "10000.00",
            "issuance_date": today.isoformat(),
            "issuance_terms": "The simulated tokens follow the approved legal agreement.",
            "restrictions": "Only compliance-approved participants may transfer tokens.",
            "proposed_tokenisation_arrangements": (
                "One hundred thousand transferable units, each priced at "
                "USD one, subject to investor eligibility restrictions."
            ),
            "token_rights_description": (
                "The token represents only the contractual rights defined "
                "in the attached agreement, not direct ownership of land."
            ),
        }
        issued = self.client.post(
            f"/admin/token-issuances/{asset_id}",
            json=issuance_data,
        )
        self.assertEqual(issued.status_code, 201, issued.text)
        self.assertIsNone(issued.json()["blockchain_transaction"])
        self.assertEqual(len(issued.json()["approval_references"]), 8)
        duplicate = self.client.post(
            f"/admin/token-issuances/{asset_id}",
            json=issuance_data,
        )
        self.assertEqual(duplicate.status_code, 409)

        with self.session_factory() as db:
            self.assertEqual(db.query(PropertyValuation).one().status, "APPROVED")
            self.assertEqual(db.query(LegalReview).one().decision, "APPROVED")
            self.assertEqual(db.query(InvestorCompliance).one().eligibility_status, "APPROVED")
            self.assertEqual(db.query(ComplianceReviewHistory).count(), 1)
            self.assertEqual(db.query(TokenizationProposal).one().status, "APPROVED")
            self.assertEqual(db.query(TokenizationApproval).count(), 13)
            issuance = db.query(TokenIssuance).one()
            self.assertEqual(issuance.valuation_id, valuation_id)
            self.assertEqual(db.query(TokenHolding).one().balance, 100000)
            self.assertEqual(db.query(TokenTransaction).count(), 1)
            property_record = db.query(Asset).filter_by(id=asset_id).one()
            self.assertEqual(property_record.status, "Tokenised")

    def test_investor_cannot_transfer_without_approved_compliance(self):
        self.current_user = self.investor
        denied = self.client.get("/tokens/investors")
        self.assertEqual(denied.status_code, 403)

    def test_invalid_valuation_and_legal_compliance_rejections_block_issuance(self):
        asset = self.prepare_verified_property()
        asset_id = asset["id"]
        today = date.today()
        self.current_user = self.valuer

        invalid_valuation = self.client.post(
            f"/workflow/properties/{asset_id}/valuations",
            json={
                "amount": "0",
                "currency": "USD",
                "valuation_date": today.isoformat(),
                "valid_until": (today + timedelta(days=180)).isoformat(),
                "methodology": "Comparable market approach.",
                "report_document_ids": [],
            },
        )
        self.assertEqual(invalid_valuation.status_code, 422)

        report = self.upload_workflow_document(asset_id, "VALUATION_REPORT")
        self.assertEqual(report.status_code, 201, report.text)
        missing_report = self.client.post(
            f"/workflow/properties/{asset_id}/valuations",
            json={
                "amount": "100000",
                "currency": "USD",
                "valuation_date": today.isoformat(),
                "valid_until": (today + timedelta(days=180)).isoformat(),
                "methodology": "Comparable market approach.",
                "report_document_ids": [],
            },
        )
        self.assertEqual(missing_report.status_code, 422)

        valuation = self.client.post(
            f"/workflow/properties/{asset_id}/valuations",
            json={
                "amount": "100000",
                "currency": "USD",
                "valuation_date": today.isoformat(),
                "valid_until": (today + timedelta(days=180)).isoformat(),
                "methodology": "Comparable market approach.",
                "report_document_ids": [report.json()["id"]],
            },
        )
        self.assertEqual(valuation.status_code, 201, valuation.text)
        self.current_user = self.proposal_reviewer
        valuation_approval = self.client.post(
            f"/workflow/valuations/{valuation.json()['id']}/decision",
            json={
                "decision": "APPROVED",
                "comments": "Report independently reviewed.",
            },
        )
        self.assertEqual(
            valuation_approval.status_code, 200, valuation_approval.text
        )

        self.current_user = self.legal
        agreement = self.upload_workflow_document(asset_id, "LEGAL_AGREEMENT")
        self.assertEqual(agreement.status_code, 201, agreement.text)
        legal_rejection = self.client.post(
            f"/workflow/properties/{asset_id}/legal-reviews",
            json={
                "jurisdiction": "Zimbabwe",
                "jurisdiction_requirements": (
                    "Qualified local legal review is required."
                ),
                "proposed_tokenisation_arrangements": (
                    "Contractual investment units only."
                ),
                "token_rights_description": (
                    "Rights are limited to the attached agreement."
                ),
                "legal_risks": "The proposed structure is not approved.",
                "comments": "Correct the proposed rights before proceeding.",
                "decision": "REJECTED",
                "supporting_document_ids": [agreement.json()["id"]],
            },
        )
        self.assertEqual(legal_rejection.status_code, 201, legal_rejection.text)

        self.current_user = self.compliance_officer
        compliance_rejection = self.client.post(
            f"/workflow/compliance/users/{asset['user_id']}/decision",
            json={
                "decision": "REJECT",
                "kyc_status": "REJECTED",
                "aml_status": "UNDER_REVIEW",
                "identity_verification_status": "REJECTED",
                "required_documents": [
                    {"name": "Identity evidence", "status": "REJECTED"}
                ],
                "comments": "The submitted evidence did not satisfy the review.",
            },
        )
        self.assertEqual(
            compliance_rejection.status_code, 200, compliance_rejection.text
        )
        self.assertFalse(compliance_rejection.json()["is_eligible"])

        self.current_user = self.final_authorizer
        blocked = self.client.post(
            f"/workflow/properties/{asset_id}/final-authorization",
            json={
                "decision": "APPROVED",
                "comments": "Blocked after legal rejection.",
            },
        )
        self.assertEqual(blocked.status_code, 409)

        self.current_user = self.token_officer
        issuance_data = {
            "token_name": "Test Property Token",
            "token_symbol": "TPT",
            "token_price": "1.00",
            "total_supply": "100000",
            "decimal_precision": 0,
            "currency": "USD",
            "minimum_investment": "1.00",
            "maximum_investment": None,
            "issuance_date": today.isoformat(),
            "issuance_terms": "Demonstration terms for a blocked issuance.",
            "restrictions": "Eligible participants only.",
            "proposed_tokenisation_arrangements": (
                "Contractual investment units only."
            ),
            "token_rights_description": (
                "Only rights in approved legal documentation."
            ),
        }
        for field, invalid_value in (
            ("token_price", "0"),
            ("total_supply", "0"),
        ):
            invalid_issuance = self.client.post(
                f"/admin/token-issuances/{asset_id}",
                json={**issuance_data, field: invalid_value},
            )
            self.assertEqual(invalid_issuance.status_code, 422)

        unapproved_issuance = self.client.post(
            f"/admin/token-issuances/{asset_id}",
            json=issuance_data,
        )
        self.assertEqual(unapproved_issuance.status_code, 409)


if __name__ == "__main__":
    unittest.main()
