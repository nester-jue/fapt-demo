import os
import unittest
from types import SimpleNamespace

os.environ["JWT_SECRET_KEY"] = "test-only-secret-key-with-at-least-32-bytes"
os.environ["DATABASE_URL"] = "sqlite://"

from fastapi import HTTPException
from starlette.requests import Request

from routes.assets import approve_asset, reject_asset


def make_request():
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "client": ("testclient", 1),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


class FakeQuery:
    def __init__(self, asset):
        self.asset = asset

    def filter(self, *_conditions):
        return self

    def first(self):
        return self.asset


class FakeDatabase:
    def __init__(self, asset):
        self.asset = asset

    def query(self, _model):
        return FakeQuery(self.asset)


class AssetReviewTests(unittest.TestCase):
    def setUp(self):
        self.asset = SimpleNamespace(
            id=10,
            user_id=7,
            status="Pending Review",
        )
        self.db = FakeDatabase(self.asset)
        self.owner_admin = SimpleNamespace(id=7)

    def test_admin_cannot_approve_own_asset_through_legacy_route(self):
        with self.assertRaises(HTTPException) as raised:
            approve_asset(
                10,
                request=make_request(),
                db=self.db,
                current_admin=self.owner_admin,
            )

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(self.asset.status, "Pending Review")

    def test_admin_cannot_reject_own_asset_through_legacy_route(self):
        with self.assertRaises(HTTPException) as raised:
            reject_asset(
                10,
                request=make_request(),
                reason="Insufficient documentation",
                db=self.db,
                current_admin=self.owner_admin,
            )

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(self.asset.status, "Pending Review")


if __name__ == "__main__":
    unittest.main()
