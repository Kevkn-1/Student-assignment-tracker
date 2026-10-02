import os
import sqlite3
import tempfile
import unittest

from tracker import create_app
from tracker.db import get_db, init_db


class SetupTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # Nested, non-existent folder: proves auto-creation of dir + file.
        self.db_path = os.path.join(self.tmp.name, "nested", "test.sqlite3")
        self.app = create_app({"DATABASE": self.db_path, "TESTING": True})
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def _add_subject(self, db, name="Mathematics"):
        cur = db.execute("INSERT INTO subjects (name) VALUES (?)", (name,))
        return cur.lastrowid

    def test_database_created_automatically(self):
        self.assertTrue(os.path.exists(self.db_path))

    def test_tables_exist(self):
        data = self.client.get("/health").get_json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["tables"], ["assignments", "subjects"])

    def test_index_page(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Student Assignment Tracker", resp.data)

    def test_init_db_is_idempotent_and_keeps_data(self):
        with self.app.app_context():
            db = get_db()
            self._add_subject(db)
            db.commit()
            init_db()
            count = db.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]
        self.assertEqual(count, 1)

    def test_assignment_defaults(self):
        with self.app.app_context():
            db = get_db()
            sid = self._add_subject(db)
            db.execute(
                "INSERT INTO assignments (subject_id, title, deadline) VALUES (?, ?, ?)",
                (sid, "Essay", "2026-11-30"),
            )
            row = db.execute("SELECT * FROM assignments").fetchone()
        self.assertEqual(row["priority"], "medium")
        self.assertEqual(row["status"], "pending")

    def test_subject_name_unique_case_insensitive(self):
        with self.app.app_context():
            db = get_db()
            self._add_subject(db, "Physics")
            with self.assertRaises(sqlite3.IntegrityError):
                self._add_subject(db, "physics")

    def test_foreign_key_enforced(self):
        with self.app.app_context():
            db = get_db()
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    "INSERT INTO assignments (subject_id, title, deadline) VALUES (?, ?, ?)",
                    (999, "Orphan", "2026-11-30"),
                )

    def test_subject_with_assignments_cannot_be_deleted(self):
        with self.app.app_context():
            db = get_db()
            sid = self._add_subject(db)
            db.execute(
                "INSERT INTO assignments (subject_id, title, deadline) VALUES (?, ?, ?)",
                (sid, "Essay", "2026-11-30"),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("DELETE FROM subjects WHERE id = ?", (sid,))

    def test_check_constraints_reject_bad_values(self):
        bad_rows = [
            ("Ok", "urgent", "pending", "2026-11-30"),    # bad priority
            ("Ok", "low", "done", "2026-11-30"),          # bad status
            ("Ok", "low", "pending", "30/11/2026"),       # bad date format
            ("Ok", "low", "pending", "2026-02-30"),       # impossible date
            ("   ", "low", "pending", "2026-11-30"),      # blank title
        ]
        with self.app.app_context():
            db = get_db()
            sid = self._add_subject(db)
            for title, priority, status, deadline in bad_rows:
                with self.subTest(row=(title, priority, status, deadline)):
                    with self.assertRaises(sqlite3.IntegrityError):
                        db.execute(
                            "INSERT INTO assignments "
                            "(subject_id, title, priority, status, deadline) "
                            "VALUES (?, ?, ?, ?, ?)",
                            (sid, title, priority, status, deadline),
                        )


if __name__ == "__main__":
    unittest.main()