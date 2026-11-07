import os
import unittest
from datetime import date, timedelta
from decimal import Decimal

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
from models.investor_compliance import InvestorCompliance
from models.legal_review import LegalReview
from models.notification import PropertyManagerAssignment
from models.property_valuation import PropertyValuation
from models.token_holding import TokenHolding
from models.token_issuance import TokenIssuance
from models.token_transaction import TokenTransaction
from models.tokenization_proposal import TokenizationProposal
from models.user import User
from services.dependencies import get_current_user
from services.ledger import stamp_transaction


class StageElevenToTwentyApiTests(unittest.TestCase):
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
            self.investor = self.make_user(db, "investor", "investor")
            self.other_investor = self.make_user(db, "other", "investor")
            self.manager = self.make_user(db, "manager", "property_manager")
            self.unassigned_manager = self.make_user(
                db, "unassigned-manager", "property_manager"
            )
            self.admin = self.make_user(db, "admin", "super_admin")
            self.auditor = self.make_user(db, "auditor", "auditor")
            self.asset = Asset(
                asset_code="NEXA-MARKET-01",
                name="Marketplace Test Property",
                category="Commercial",
                description="Verified property for marketplace tests.",
                location="Harare",
                country="Zimbabwe",
                jurisdiction="Zimbabwe",
                registration_number="REG-MARKET-01",
                estimated_value=Decimal("1000"),
                currency="USD",
                owner_name=self.owner.full_name,
                status="Tokenised",
                user_id=self.owner.id,
            )
            db.add(self.asset)
            db.flush()
            self.valuation = PropertyValuation(
                asset_id=self.asset.id,
                valuer_user_id=self.admin.id,
                amount=Decimal("1000"),
                currency="USD",
                valuation_date=date.today(),
                valid_until=date.today() + timedelta(days=180),
                methodology="Comparable market approach.",
                status="APPROVED",
                report_document_ids="[]",
            )
            db.add(self.valuation)
            db.flush()
            self.issuance = TokenIssuance(
                asset_id=self.asset.id,
                valuation_id=self.valuation.id,
                issued_by_user_id=self.admin.id,
                token_name="Marketplace Token",
                token_symbol="MKT",
                currency="USD",
                token_price=Decimal("10"),
                total_supply=Decimal("100"),
                decimal_precision=2,
                minimum_investment=Decimal("10"),
                maximum_investment=Decimal("500"),
                issuance_terms="Demonstration terms for this property.",
                restrictions="Eligible investors only.",
                status="ISSUED",
                approval_references="[]",
            )
            db.add(self.issuance)
            db.flush()
            self.proposal = TokenizationProposal(
                asset_id=self.asset.id,
                submitted_by_user_id=self.admin.id,
                token_name=self.issuance.token_name,
                token_symbol=self.issuance.token_symbol,
                token_price=self.issuance.token_price,
                total_supply=self.issuance.total_supply,
                decimal_precision=self.issuance.decimal_precision,
                currency=self.issuance.currency,
                minimum_investment=self.issuance.minimum_investment,
                maximum_investment=self.issuance.maximum_investment,
                issuance_date=date.today(),
                issuance_terms=self.issuance.issuance_terms,
                restrictions=self.issuance.restrictions,
                disclosures="Investment risk disclosure.",
                proposed_tokenisation_arrangements="Separate contractual rights.",
                token_rights_description="Rights defined only by applicable agreements.",
                status="APPROVED",
                reviewed_by_user_id=self.admin.id,
            )
            db.add(self.proposal)
            db.add(
                LegalReview(
                    asset_id=self.asset.id,
                    reviewer_user_id=self.admin.id,
                    jurisdiction="Zimbabwe",
                    jurisdiction_requirements="Local registration and disclosure requirements.",
                    proposed_tokenisation_arrangements="Separate contractual rights.",
                    token_rights_description="Rights defined only by applicable agreements.",
                    legal_risks="Liquidity and market risks.",
                    comments="Reviewed for demonstration.",
                    decision="APPROVED",
                    supporting_document_ids="[]",
                )
            )
            self.compliance(db, self.owner)
            self.compliance(db, self.investor)
            self.compliance(db, self.other_investor)
            db.flush()
            db.add(
                TokenHolding(
                    issuance_id=self.issuance.id,
                    user_id=self.owner.id,
                    balance=Decimal("100"),
                )
            )
            initial = TokenTransaction(
                transaction_ref="NEXA-INITIAL-TEST",
                issuance_id=self.issuance.id,
                from_user_id=None,
                to_user_id=self.owner.id,
                amount=Decimal("100"),
                transaction_type="ISSUANCE",
                status="COMPLETED",
                payment_status="NOT_APPLICABLE",
                from_balance_before=Decimal("0"),
                from_balance_after=Decimal("0"),
                to_balance_before=Decimal("0"),
                to_balance_after=Decimal("100"),
            )
            stamp_transaction(db, initial)
            db.add(initial)
            db.add(
                PropertyManagerAssignment(
                    asset_id=self.asset.id,
                    manager_user_id=self.manager.id,
                    assigned_by_user_id=self.admin.id,
                    is_active=True,
                )
            )
            db.commit()
            self.owner_id = self.owner.id
            self.investor_id = self.investor.id
            self.other_investor_id = self.other_investor.id
            self.manager_id = self.manager.id
            self.unassigned_manager_id = self.unassigned_manager.id
            self.admin_id = self.admin.id
            self.auditor_id = self.auditor.id
            self.asset_id = self.asset.id
            self.issuance_id = self.issuance.id

        self.current_user = self.investor

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

    @staticmethod
    def compliance(db, user):
        db.add(
            InvestorCompliance(
                user_id=user.id,
                kyc_status="APPROVED",
                aml_status="APPROVED",
                identity_verification_status="APPROVED",
                eligibility_status="APPROVED",
                is_eligible=True,
                required_documents="[]",
            )
        )

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_marketplace_purchase_allocates_once_without_claiming_payment(self):
        listings = self.client.get("/marketplace/opportunities?location=Harare")
        self.assertEqual(listings.status_code, 200, listings.text)
        self.assertEqual(listings.json()["items"][0]["available_supply"], "100.00000000")
        purchase = {
            "issuance_id": self.issuance_id,
            "quantity": "10",
            "idempotency_key": "test-purchase-0001",
        }
        response = self.client.post("/marketplace/purchases", json=purchase)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["payment_status"], "NOT_PROCESSED")
        self.assertIn("no payment was processed", response.json()["message"].lower())
        duplicate = self.client.post("/marketplace/purchases", json=purchase)
        self.assertEqual(duplicate.status_code, 200, duplicate.text)
        self.assertTrue(duplicate.json()["idempotent_replay"])
        holdings = self.client.get("/tokens/holdings")
        self.assertEqual(holdings.json()[0]["balance"], "10.00000000")
        listings = self.client.get("/marketplace/opportunities")
        self.assertEqual(listings.json()["items"][0]["available_supply"], "90.00000000")

    def test_purchase_rejects_nonpositive_quantity_and_insufficient_supply_atomically(self):
        baseline_transactions = self._transaction_count()
        for quantity in ("0", "-1"):
            with self.subTest(quantity=quantity):
                response = self.client.post(
                    "/marketplace/purchases",
                    json={
                        "issuance_id": self.issuance_id,
                        "quantity": quantity,
                        "idempotency_key": f"invalid-purchase-{quantity}-key",
                    },
                )
                self.assertEqual(response.status_code, 422)

        with self.session_factory() as db:
            issuance = db.query(TokenIssuance).filter_by(id=self.issuance_id).one()
            issuance.maximum_investment = None
            db.commit()

        insufficient = self.client.post(
            "/marketplace/purchases",
            json={
                "issuance_id": self.issuance_id,
                "quantity": "101",
                "idempotency_key": "insufficient-supply-purchase",
            },
        )
        self.assertEqual(insufficient.status_code, 409, insufficient.text)
        self.assertEqual(self._transaction_count(), baseline_transactions)
        with self.session_factory() as db:
            self.assertEqual(
                Decimal(
                    db.query(TokenHolding)
                    .filter_by(issuance_id=self.issuance_id, user_id=self.owner_id)
                    .one()
                    .balance
                ),
                Decimal("100"),
            )

    def test_failed_transfer_inputs_do_not_change_either_balance(self):
        baseline_transactions = self._transaction_count()
        invalid_payloads = [
            ({"amount": "0", "recipient_user_id": self.other_investor_id}, 422),
            ({"amount": "-1", "recipient_user_id": self.other_investor_id}, 422),
            ({"amount": "1", "recipient_user_id": self.investor_id}, 422),
            ({"amount": "1", "recipient_user_id": 999999}, 404),
            ({"amount": "1", "recipient_user_id": self.other_investor_id}, 409),
        ]
        for index, (values, expected_status) in enumerate(invalid_payloads):
            payload = {
                "issuance_id": self.issuance_id,
                "idempotency_key": f"failed-transfer-case-{index:02d}",
                **values,
            }
            response = self.client.post("/tokens/transfers", json=payload)
            self.assertEqual(response.status_code, expected_status, response.text)

        self.assertEqual(self._transaction_count(), baseline_transactions)
        with self.session_factory() as db:
            holdings = (
                db.query(TokenHolding)
                .filter(TokenHolding.issuance_id == self.issuance_id)
                .all()
            )
            self.assertEqual(
                {holding.user_id: Decimal(holding.balance) for holding in holdings},
                {self.owner_id: Decimal("100")},
            )

    def test_transaction_history_and_hash_chain_detect_tampering(self):
        purchase = self.client.post(
            "/marketplace/purchases",
            json={
                "issuance_id": self.issuance_id,
                "quantity": "2",
                "idempotency_key": "history-chain-purchase-0001",
            },
        )
        self.assertEqual(purchase.status_code, 201, purchase.text)
        history = self.client.get("/tokens/transactions")
        self.assertEqual(history.status_code, 200, history.text)
        self.assertTrue(
            any(
                transaction["transaction_type"] == "PURCHASE"
                for transaction in history.json()
            )
        )

        with self.session_factory() as db:
            transaction = (
                db.query(TokenTransaction)
                .filter_by(transaction_type="PURCHASE")
                .one()
            )
            transaction.previous_hash = "invalid-chain-link"
            db.commit()

        self.current_user = self.auditor
        verification = self.client.get("/admin/ledger/verify")
        self.assertEqual(verification.status_code, 200, verification.text)
        self.assertEqual(verification.json()["integrity"], "FAILED")

    def _transaction_count(self):
        with self.session_factory() as db:
            return db.query(TokenTransaction).count()

    def test_manager_access_is_assignment_scoped(self):
        self.current_user = self.manager
        rows = self.client.get("/property-management/properties")
        self.assertEqual(rows.status_code, 200, rows.text)
        self.assertEqual([row["id"] for row in rows.json()], [self.asset_id])
        record = self.client.post(
            f"/property-management/properties/{self.asset_id}/records",
            json={
                "record_type": "MAINTENANCE",
                "description": "Repaired the main entrance lighting.",
                "document_ids": [],
            },
        )
        self.assertEqual(record.status_code, 201, record.text)
        self.current_user = self.unassigned_manager
        denied = self.client.get(
            f"/property-management/properties/{self.asset_id}/records"
        )
        self.assertEqual(denied.status_code, 404)

    def test_owner_distribution_is_ledger_derived_and_private(self):
        denied = self.client.get(f"/properties/{self.asset_id}/token-distribution")
        self.assertEqual(denied.status_code, 403)
        self.current_user = self.owner
        distribution = self.client.get(
            f"/properties/{self.asset_id}/token-distribution"
        )
        self.assertEqual(distribution.status_code, 200, distribution.text)
        self.assertEqual(
            Decimal(distribution.json()["distribution"][0]["balance"]),
            Decimal("100"),
        )

    def test_notification_and_hash_chain_are_user_scoped_and_verifiable(self):
        response = self.client.post(
            "/marketplace/purchases",
            json={
                "issuance_id": self.issuance_id,
                "quantity": "1",
                "idempotency_key": "test-purchase-0002",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        own_notifications = self.client.get("/notifications")
        self.assertGreaterEqual(own_notifications.json()["unread_count"], 1)
        self.current_user = self.other_investor
        self.assertEqual(self.client.get("/notifications").json()["items"], [])
        self.current_user = self.auditor
        verification = self.client.get("/admin/ledger/verify")
        self.assertEqual(verification.status_code, 200, verification.text)
        self.assertEqual(verification.json()["integrity"], "VALID")
        self.assertEqual(
            self.client.get("/admin/ledger/audit-events").status_code, 200
        )

    def test_transfer_uses_ledger_balance_and_idempotency(self):
        purchase = self.client.post(
            "/marketplace/purchases",
            json={
                "issuance_id": self.issuance_id,
                "quantity": "10",
                "idempotency_key": "test-purchase-transfer",
            },
        )
        self.assertEqual(purchase.status_code, 201, purchase.text)
        transfer_payload = {
            "issuance_id": self.issuance_id,
            "recipient_user_id": self.other_investor_id,
            "amount": "3",
            "idempotency_key": "test-transfer-0001",
        }
        transfer = self.client.post("/tokens/transfers", json=transfer_payload)
        self.assertEqual(transfer.status_code, 201, transfer.text)
        self.assertEqual(transfer.json()["status"], "COMPLETED")
        repeated = self.client.post("/tokens/transfers", json=transfer_payload)
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertTrue(repeated.json()["idempotent_replay"])
        self.assertEqual(
            self.client.get("/tokens/holdings").json()[0]["balance"],
            "7.00000000",
        )
        self.current_user = self.other_investor
        self.assertEqual(
            self.client.get("/tokens/holdings").json()[0]["balance"],
            "3.00000000",
        )

    def test_ineligible_investor_cannot_purchase_and_audit_tampering_is_detected(self):
        self.investor.is_active = False
        response = self.client.post(
            "/marketplace/purchases",
            json={
                "issuance_id": self.issuance_id,
                "quantity": "10",
                "idempotency_key": "test-purchase-blocked",
            },
        )
        self.assertEqual(response.status_code, 403, response.text)
        self.investor.is_active = True
        response = self.client.post(
            "/marketplace/purchases",
            json={
                "issuance_id": self.issuance_id,
                "quantity": "10",
                "idempotency_key": "test-purchase-tamper",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        with self.session_factory() as db:
            event = db.query(AuditEvent).first()
            event.action = "ALTERED_ACTION"
            db.commit()
        self.current_user = self.auditor
        verification = self.client.get("/admin/ledger/verify")
        self.assertEqual(verification.status_code, 200, verification.text)
        self.assertEqual(verification.json()["integrity"], "FAILED")


if __name__ == "__main__":
    unittest.main()
