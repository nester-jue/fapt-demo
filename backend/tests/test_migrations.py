import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


BACKEND_DIR = Path(__file__).resolve().parents[1]


class AlembicMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "migration-test.db"
        self.database_url = f"sqlite:///{self.database_path.as_posix()}"
        self.environment = os.environ.copy()
        self.environment["DATABASE_URL"] = self.database_url

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_alembic_upgrade(self, revision="head"):
        return subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", revision],
            cwd=BACKEND_DIR,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def test_initial_migration_creates_empty_database_schema(self):
        result = self.run_alembic_upgrade()

        self.assertEqual(result.returncode, 0, result.stderr)
        connection = sqlite3.connect(self.database_path)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        finally:
            connection.close()

        self.assertTrue(
            {
                "users",
                "assets",
                "asset_review_logs",
                "token_issuances",
                "token_holdings",
                "token_transactions",
                "audit_events",
                "property_documents",
                "property_verifications",
                "property_valuations",
                "legal_reviews",
                "investor_compliance",
                "compliance_review_history",
                "tokenization_proposals",
                "tokenization_approvals",
                "notifications",
                "property_manager_assignments",
                "property_management_records",
                "alembic_version",
            }.issubset(tables)
        )

    def test_initial_migration_adopts_matching_database_without_data_loss(self):
        baseline = self.run_alembic_upgrade("53cbc3c9657c")
        self.assertEqual(baseline.returncode, 0, baseline.stderr)

        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute(
                "INSERT INTO users "
                "(id, full_name, email, hashed_password, role, is_active) "
                "VALUES (1, 'Existing User', 'existing@example.test', "
                "'test-hash', 'investor', 1)"
            )
            connection.execute("DROP INDEX ix_assets_user_id")
            connection.execute("DROP TABLE alembic_version")
            connection.commit()
        finally:
            connection.close()

        setup = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sqlite3; "
                f"connection=sqlite3.connect({str(self.database_path)!r}); "
                "assert connection.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 1; "
                "connection.close()",
            ],
            cwd=BACKEND_DIR,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(setup.returncode, 0, setup.stderr)

        result = self.run_alembic_upgrade()

        self.assertEqual(result.returncode, 0, result.stderr)
        connection = sqlite3.connect(self.database_path)
        try:
            user_count = connection.execute(
                "SELECT COUNT(*) FROM users"
            ).fetchone()[0]
            revision = connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()[0]
            owner_index_count = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type='index' AND name='ix_assets_user_id'"
            ).fetchone()[0]
            property_reference_index_count = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type='index' AND name='uq_assets_registration_number_key'"
            ).fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(user_count, 1)
        self.assertEqual(revision, "d4a9f2c781be")
        self.assertEqual(owner_index_count, 1)
        self.assertEqual(property_reference_index_count, 1)


if __name__ == "__main__":
    unittest.main()
