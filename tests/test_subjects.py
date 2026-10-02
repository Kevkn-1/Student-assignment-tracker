import os
import tempfile
import unittest

from tracker import create_app
from tracker.db import get_db
from tracker.services import subject_service as service
from tracker.services.errors import ConflictError, NotFoundError, ValidationError


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.tmp.name, "test.sqlite3")
        self.app = create_app({"DATABASE": db_path, "TESTING": True})
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()
        self.tmp.cleanup()

    def add_assignment(self, subject_id):
        db = get_db()
        db.execute(
            "INSERT INTO assignments (subject_id, title, deadline) VALUES (?, ?, ?)",
            (subject_id, "Essay", "2026-11-30"),
        )
        db.commit()


class SubjectServiceTests(BaseCase):
    def test_create_and_get(self):
        sid = service.create_subject("Mathematics", "math101")
        subject = service.get_subject(sid)
        self.assertEqual(subject["name"], "Mathematics")
        self.assertEqual(subject["code"], "MATH101")  # code is upper-cased

    def test_name_is_trimmed_and_whitespace_collapsed(self):
        sid = service.create_subject("   Data    Structures  ", "")
        self.assertEqual(service.get_subject(sid)["name"], "Data Structures")

    def test_empty_code_is_stored_as_null(self):
        sid = service.create_subject("Physics", "   ")
        self.assertIsNone(service.get_subject(sid)["code"])

    def test_name_required(self):
        for bad in ["", "    ", None]:
            with self.subTest(name=bad):
                with self.assertRaises(ValidationError) as ctx:
                    service.create_subject(bad, "")
                self.assertIn("name", ctx.exception.errors)

    def test_name_too_long(self):
        with self.assertRaises(ValidationError) as ctx:
            service.create_subject("x" * 101, "")
        self.assertIn("name", ctx.exception.errors)
        service.create_subject("x" * 100, "")  # exactly at the limit is fine

    def test_name_rejects_control_characters(self):
        with self.assertRaises(ValidationError):
            service.create_subject("Bad\x00Name", "")

    def test_code_validation(self):
        for bad in ["A" * 21, "CS#101", "<b>", "-CS"]:
            with self.subTest(code=bad):
                with self.assertRaises(ValidationError) as ctx:
                    service.create_subject("Subject", bad)
                self.assertIn("code", ctx.exception.errors)

    def test_duplicate_name_rejected_case_insensitive(self):
        service.create_subject("Physics", "")
        with self.assertRaises(ValidationError) as ctx:
            service.create_subject("  physics ", "")
        self.assertIn("name", ctx.exception.errors)

    def test_update(self):
        sid = service.create_subject("Physics", "PHY1")
        service.update_subject(sid, "Applied Physics", "phy2")
        subject = service.get_subject(sid)
        self.assertEqual(subject["name"], "Applied Physics")
        self.assertEqual(subject["code"], "PHY2")

    def test_update_can_change_own_name_case(self):
        sid = service.create_subject("physics", "")
        service.update_subject(sid, "Physics", "")  # not a duplicate of itself
        self.assertEqual(service.get_subject(sid)["name"], "Physics")

    def test_update_to_other_subjects_name_rejected(self):
        service.create_subject("Physics", "")
        other = service.create_subject("Chemistry", "")
        with self.assertRaises(ValidationError):
            service.update_subject(other, "PHYSICS", "")

    def test_update_and_get_missing_subject(self):
        with self.assertRaises(NotFoundError):
            service.get_subject(999)
        with self.assertRaises(NotFoundError):
            service.update_subject(999, "Anything", "")

    def test_delete(self):
        sid = service.create_subject("Physics", "")
        service.delete_subject(sid)
        with self.assertRaises(NotFoundError):
            service.get_subject(sid)

    def test_delete_missing_subject(self):
        with self.assertRaises(NotFoundError):
            service.delete_subject(999)

    def test_delete_blocked_when_subject_has_assignments(self):
        sid = service.create_subject("Physics", "")
        self.add_assignment(sid)
        with self.assertRaises(ConflictError):
            service.delete_subject(sid)
        self.assertEqual(service.get_subject(sid)["name"], "Physics")

    def test_list_includes_assignment_count_sorted_by_name(self):
        b = service.create_subject("biology", "")
        service.create_subject("Algebra", "")
        self.add_assignment(b)
        self.add_assignment(b)
        rows = service.list_subjects()
        self.assertEqual([r["name"] for r in rows], ["Algebra", "biology"])
        self.assertEqual([r["assignment_count"] for r in rows], [0, 2])

    def test_sql_injection_text_is_stored_literally(self):
        payload = "'; DROP TABLE subjects; --"
        sid = service.create_subject(payload, "")
        self.assertEqual(service.get_subject(sid)["name"], payload)
        self.assertEqual(len(service.list_subjects()), 1)  # table still exists


class SubjectRouteTests(BaseCase):
    def test_list_page_empty_state(self):
        resp = self.client.get("/subjects/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"No subjects yet", resp.data)

    def test_new_form_page(self):
        self.assertEqual(self.client.get("/subjects/new").status_code, 200)

    def test_create_valid_subject(self):
        resp = self.client.post(
            "/subjects/new", data={"name": "Networks", "code": "net201"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Subject created.", resp.data)
        self.assertIn(b"Networks", resp.data)
        self.assertIn(b"NET201", resp.data)

    def test_create_invalid_subject_shows_errors_and_keeps_input(self):
        resp = self.client.post("/subjects/new", data={"name": "  ", "code": "CS#1"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn(b"Subject name is required.", resp.data)
        self.assertIn(b"Subject code may only contain", resp.data)
        self.assertIn(b'value="CS#1"', resp.data)

    def test_duplicate_name_shows_error(self):
        self.client.post("/subjects/new", data={"name": "Networks", "code": ""})
        resp = self.client.post("/subjects/new", data={"name": "networks", "code": ""})
        self.assertEqual(resp.status_code, 400)
        self.assertIn(b"already exists", resp.data)

    def test_edit_flow(self):
        sid = service.create_subject("Networks", "")
        page = self.client.get(f"/subjects/{sid}/edit")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'value="Networks"', page.data)
        resp = self.client.post(
            f"/subjects/{sid}/edit", data={"name": "Computer Networks", "code": ""},
            follow_redirects=True,
        )
        self.assertIn(b"Subject updated.", resp.data)
        self.assertIn(b"Computer Networks", resp.data)

    def test_edit_invalid_input(self):
        sid = service.create_subject("Networks", "")
        resp = self.client.post(f"/subjects/{sid}/edit", data={"name": "", "code": ""})
        self.assertEqual(resp.status_code, 400)
        self.assertIn(b"Subject name is required.", resp.data)

    def test_edit_unknown_subject_is_404(self):
        self.assertEqual(self.client.get("/subjects/999/edit").status_code, 404)
        resp = self.client.post("/subjects/999/edit", data={"name": "X", "code": ""})
        self.assertEqual(resp.status_code, 404)

    def test_delete_flow(self):
        sid = service.create_subject("Networks", "")
        resp = self.client.post(f"/subjects/{sid}/delete", follow_redirects=True)
        self.assertIn(b"Subject deleted.", resp.data)
        self.assertNotIn(b"Networks", resp.data)

    def test_delete_blocked_shows_message(self):
        sid = service.create_subject("Networks", "")
        self.add_assignment(sid)
        resp = self.client.post(f"/subjects/{sid}/delete", follow_redirects=True)
        self.assertIn(b"still has assignments", resp.data)
        self.assertIn(b"Networks", resp.data)

    def test_delete_unknown_subject_is_404(self):
        self.assertEqual(self.client.post("/subjects/999/delete").status_code, 404)

    def test_delete_requires_post(self):
        sid = service.create_subject("Networks", "")
        self.assertEqual(self.client.get(f"/subjects/{sid}/delete").status_code, 405)

    def test_html_in_names_is_escaped(self):
        service.create_subject("<script>alert(1)</script>", "")
        resp = self.client.get("/subjects/")
        self.assertNotIn(b"<script>alert(1)</script>", resp.data)
        self.assertIn(b"&lt;script&gt;", resp.data)


if __name__ == "__main__":
    unittest.main()
    