import os
import tempfile
import unittest
from datetime import date

from tracker import create_app
from tracker.db import get_db
from tracker.services import assignment_service as service
from tracker.services import subject_service
from tracker.services.errors import ConflictError, NotFoundError, ValidationError


def valid_data(subject_id, **overrides):
    data = {
        "subject_id": str(subject_id),
        "title": "Lab report",
        "description": "Write up the experiment.",
        "priority": "high",
        "status": "pending",
        "deadline": "2026-11-30",
    }
    data.update(overrides)
    return data


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.tmp.name, "test.sqlite3")
        self.app = create_app({"DATABASE": db_path, "TESTING": True})
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.subject_id = subject_service.create_subject("Physics", "PHY101")

    def tearDown(self):
        self.ctx.pop()
        self.tmp.cleanup()

    def make(self, **overrides):
        return service.create_assignment(valid_data(self.subject_id, **overrides))


class AssignmentServiceTests(BaseCase):
    def test_create_and_get(self):
        aid = self.make()
        a = service.get_assignment(aid)
        self.assertEqual(a["title"], "Lab report")
        self.assertEqual(a["subject_name"], "Physics")
        self.assertEqual(a["priority"], "high")
        self.assertEqual(a["status"], "pending")
        self.assertEqual(a["deadline"], "2026-11-30")

    def test_title_trimmed_and_collapsed(self):
        aid = self.make(title="   Lab    report  ")
        self.assertEqual(service.get_assignment(aid)["title"], "Lab report")

    def test_empty_description_stored_as_null(self):
        aid = self.make(description="   ")
        self.assertIsNone(service.get_assignment(aid)["description"])

    def test_multiline_description_kept(self):
        aid = self.make(description="Line one\r\nLine two")
        self.assertEqual(service.get_assignment(aid)["description"], "Line one\nLine two")

    def test_title_validation(self):
        for bad in ["", "   ", None, "x" * 151, "Bad\x00Title"]:
            with self.subTest(title=bad):
                with self.assertRaises(ValidationError) as ctx:
                    self.make(title=bad)
                self.assertIn("title", ctx.exception.errors)
        self.make(title="x" * 150)  # exactly at the limit

    def test_description_too_long(self):
        with self.assertRaises(ValidationError) as ctx:
            self.make(description="x" * 2001)
        self.assertIn("description", ctx.exception.errors)

    def test_priority_validation(self):
        for bad in ["", "urgent", "HIGH", None]:
            with self.subTest(priority=bad):
                with self.assertRaises(ValidationError) as ctx:
                    self.make(priority=bad)
                self.assertIn("priority", ctx.exception.errors)

    def test_status_validation(self):
        for bad in ["", "done", "Pending", None]:
            with self.subTest(status=bad):
                with self.assertRaises(ValidationError) as ctx:
                    self.make(status=bad)
                self.assertIn("status", ctx.exception.errors)

    def test_subject_validation(self):
        for bad in ["", "abc", "-1", "1.5", "999", "9" * 30, None, "1; DROP TABLE subjects"]:
            with self.subTest(subject_id=bad):
                with self.assertRaises(ValidationError) as ctx:
                    service.create_assignment(valid_data(bad))
                self.assertIn("subject_id", ctx.exception.errors)

    def test_deadline_validation(self):
        bad_values = [
            "", "   ", None, "30/11/2026", "2026-02-30", "2026-13-01", "2026-1-5",
            "20261130", "2026-W48-1", "2026-11-30 10:00", "1999-12-31", "2101-01-01",
            "0000-01-01", "abcd-ef-gh",
        ]
        for bad in bad_values:
            with self.subTest(deadline=bad):
                with self.assertRaises(ValidationError) as ctx:
                    self.make(deadline=bad)
                self.assertIn("deadline", ctx.exception.errors)

    def test_deadline_accepts_valid_and_surrounding_spaces(self):
        aid = self.make(deadline=" 2028-02-29 ")  # leap day
        self.assertEqual(service.get_assignment(aid)["deadline"], "2028-02-29")

    def test_all_errors_reported_together(self):
        with self.assertRaises(ValidationError) as ctx:
            service.create_assignment({})
        self.assertEqual(
            set(ctx.exception.errors),
            {"subject_id", "title", "priority", "status", "deadline"},
        )

    def test_invalid_create_stores_nothing(self):
        with self.assertRaises(ValidationError):
            self.make(title="")
        self.assertEqual(service.list_assignments(), [])

    def test_update(self):
        aid = self.make()
        other = subject_service.create_subject("Chemistry", "")
        service.update_assignment(aid, valid_data(
            other, title="New title", priority="low", status="in_progress",
            deadline="2027-01-15", description="",
        ))
        a = service.get_assignment(aid)
        self.assertEqual(
            (a["subject_name"], a["title"], a["priority"], a["status"], a["deadline"], a["description"]),
            ("Chemistry", "New title", "low", "in_progress", "2027-01-15", None),
        )

    def test_invalid_update_leaves_row_unchanged(self):
        aid = self.make()
        with self.assertRaises(ValidationError):
            service.update_assignment(aid, valid_data(self.subject_id, title=""))
        self.assertEqual(service.get_assignment(aid)["title"], "Lab report")

    def test_update_missing_assignment(self):
        with self.assertRaises(NotFoundError):
            service.update_assignment(999, valid_data(self.subject_id))

    def test_update_status(self):
        aid = self.make()
        for status in ["in_progress", "completed", "pending"]:
            service.update_status(aid, status)
            self.assertEqual(service.get_assignment(aid)["status"], status)

    def test_update_status_invalid_and_missing(self):
        aid = self.make()
        for bad in ["", "done", None]:
            with self.subTest(status=bad):
                with self.assertRaises(ValidationError):
                    service.update_status(aid, bad)
        self.assertEqual(service.get_assignment(aid)["status"], "pending")
        with self.assertRaises(NotFoundError):
            service.update_status(999, "completed")

    def test_delete(self):
        aid = self.make()
        service.delete_assignment(aid)
        with self.assertRaises(NotFoundError):
            service.get_assignment(aid)
        with self.assertRaises(NotFoundError):
            service.delete_assignment(aid)

    def test_overdue_flag(self):
        today = date(2026, 10, 1)
        past = self.make(title="Past", deadline="2026-09-30")
        past_done = self.make(title="Past done", deadline="2026-09-30", status="completed")
        due_today = self.make(title="Today", deadline="2026-10-01")
        future = self.make(title="Future", deadline="2026-12-01")
        flags = {a["title"]: a["overdue"] for a in service.list_assignments(today=today)}
        self.assertEqual(
            flags,
            {"Past": True, "Past done": False, "Today": False, "Future": False},
        )
        self.assertTrue(service.get_assignment(past, today=today)["overdue"])

    def test_default_ordering(self):
        self.make(title="Late low", deadline="2026-12-01", priority="low")
        self.make(title="Done early", deadline="2026-10-01", status="completed")
        self.make(title="Soon high", deadline="2026-11-01", priority="high")
        self.make(title="Soon low", deadline="2026-11-01", priority="low")
        titles = [a["title"] for a in service.list_assignments()]
        self.assertEqual(titles, ["Soon high", "Soon low", "Late low", "Done early"])

    def test_sql_injection_text_is_stored_literally(self):
        payload = "x'); DROP TABLE assignments; --"
        aid = self.make(title=payload)
        self.assertEqual(service.get_assignment(aid)["title"], payload)
        self.assertEqual(len(service.list_assignments()), 1)

    def test_subject_delete_blocked_by_assignment(self):
        self.make()
        with self.assertRaises(ConflictError):
            subject_service.delete_subject(self.subject_id)

    def test_subject_delete_allowed_after_assignment_removed(self):
        aid = self.make()
        service.delete_assignment(aid)
        subject_service.delete_subject(self.subject_id)

    def test_filter_by_subject(self):
        other_subject = subject_service.create_subject("Chemistry", "CHEM")
        self.make(title="Physics task")
        service.create_assignment(valid_data(other_subject, title="Chemistry task"))

        phys_rows = service.list_assignments(subject_id=self.subject_id)
        self.assertEqual(len(phys_rows), 1)
        self.assertEqual(phys_rows[0]["title"], "Physics task")

        chem_rows = service.list_assignments(subject_id=other_subject)
        self.assertEqual(len(chem_rows), 1)
        self.assertEqual(chem_rows[0]["title"], "Chemistry task")

    def test_filter_by_status(self):
        self.make(title="Pending task", status="pending")
        self.make(title="Active task", status="in_progress")
        self.make(title="Finished task", status="completed")

        pending = service.list_assignments(status="pending")
        self.assertEqual([a["title"] for a in pending], ["Pending task"])

        active = service.list_assignments(status="in_progress")
        self.assertEqual([a["title"] for a in active], ["Active task"])

        completed = service.list_assignments(status="completed")
        self.assertEqual([a["title"] for a in completed], ["Finished task"])

    def test_filter_by_priority(self):
        self.make(title="Low task", priority="low")
        self.make(title="High task", priority="high")

        high = service.list_assignments(priority="high")
        self.assertEqual([a["title"] for a in high], ["High task"])

        low = service.list_assignments(priority="low")
        self.assertEqual([a["title"] for a in low], ["Low task"])

    def test_combined_filters(self):
        other_subject = subject_service.create_subject("Math", "MTH")
        self.make(title="Target", priority="high", status="in_progress")
        self.make(title="Wrong status", priority="high", status="pending")
        self.make(title="Wrong priority", priority="low", status="in_progress")
        service.create_assignment(valid_data(other_subject, title="Wrong subject", priority="high", status="in_progress"))

        results = service.list_assignments(
            subject_id=self.subject_id, priority="high", status="in_progress"
        )
        self.assertEqual([a["title"] for a in results], ["Target"])

    def test_sort_by_deadline_asc_and_desc(self):
        self.make(title="Middle", deadline="2026-11-15")
        self.make(title="Earliest", deadline="2026-10-01")
        self.make(title="Latest", deadline="2026-12-31")

        asc = service.list_assignments(sort="deadline_asc")
        self.assertEqual([a["title"] for a in asc], ["Earliest", "Middle", "Latest"])

        desc = service.list_assignments(sort="deadline_desc")
        self.assertEqual([a["title"] for a in desc], ["Latest", "Middle", "Earliest"])

    def test_sort_by_priority(self):
        self.make(title="Med", priority="medium", deadline="2026-11-01")
        self.make(title="Low", priority="low", deadline="2026-10-01")
        self.make(title="High", priority="high", deadline="2026-12-01")

        prio_sorted = service.list_assignments(sort="priority")
        self.assertEqual([a["title"] for a in prio_sorted], ["High", "Med", "Low"])



class AssignmentRouteTests(BaseCase):
    def post_new(self, **overrides):
        return self.client.post("/assignments/new", data=valid_data(self.subject_id, **overrides))

    def test_list_page_empty_state(self):
        resp = self.client.get("/assignments/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"No assignments yet", resp.data)

    def test_new_page_with_subject_shows_form(self):
        resp = self.client.get("/assignments/new")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Create assignment", resp.data)
        self.assertIn(b"Physics", resp.data)

    def test_new_page_without_subjects_asks_to_add_one(self):
        subject_service.delete_subject(self.subject_id)
        resp = self.client.get("/assignments/new")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"at least one subject", resp.data)
        self.assertNotIn(b"Create assignment", resp.data)

    def test_create_valid_redirects_to_detail(self):
        resp = self.post_new()
        self.assertEqual(resp.status_code, 302)
        page = self.client.get(resp.headers["Location"])
        self.assertIn(b"Assignment created.", page.data)
        self.assertIn(b"Lab report", page.data)
        self.assertIn(b"2026-11-30", page.data)

    def test_create_invalid_shows_errors_and_keeps_input(self):
        resp = self.post_new(title="", deadline="2026-02-30", priority="urgent")
        self.assertEqual(resp.status_code, 400)
        self.assertIn(b"Title is required.", resp.data)
        self.assertIn(b"Deadline must be a valid date", resp.data)
        self.assertIn(b"Priority must be low, medium or high.", resp.data)
        self.assertIn(b'value="2026-02-30"', resp.data)
        self.assertEqual(service.list_assignments(), [])

    def test_list_shows_assignment_subject_and_overdue(self):
        self.make(title="Old task", deadline="2020-01-01")
        resp = self.client.get("/assignments/")
        self.assertIn(b"Old task", resp.data)
        self.assertIn(b"Physics", resp.data)
        self.assertIn(b"Overdue", resp.data)

    def test_detail_and_404(self):
        aid = self.make()
        self.assertEqual(self.client.get(f"/assignments/{aid}").status_code, 200)
        self.assertEqual(self.client.get("/assignments/999").status_code, 404)

    def test_edit_flow(self):
        aid = self.make()
        page = self.client.get(f"/assignments/{aid}/edit")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'value="Lab report"', page.data)
        resp = self.client.post(
            f"/assignments/{aid}/edit",
            data=valid_data(self.subject_id, title="Final report"),
            follow_redirects=True,
        )
        self.assertIn(b"Assignment updated.", resp.data)
        self.assertIn(b"Final report", resp.data)

    def test_edit_invalid_and_404(self):
        aid = self.make()
        resp = self.client.post(
            f"/assignments/{aid}/edit", data=valid_data(self.subject_id, title="")
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn(b"Title is required.", resp.data)
        self.assertEqual(self.client.get("/assignments/999/edit").status_code, 404)
        self.assertEqual(
            self.client.post("/assignments/999/edit", data=valid_data(self.subject_id)).status_code, 404
        )

    def test_status_update_from_list(self):
        aid = self.make()
        resp = self.client.post(
            f"/assignments/{aid}/status", data={"status": "completed"}, follow_redirects=True
        )
        self.assertIn(b"Status updated.", resp.data)
        self.assertEqual(service.get_assignment(aid)["status"], "completed")

    def test_status_update_from_detail_returns_to_detail(self):
        aid = self.make()
        resp = self.client.post(
            f"/assignments/{aid}/status", data={"status": "in_progress", "origin": "detail"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.headers["Location"].endswith(f"/assignments/{aid}"))

    def test_status_update_invalid_and_404(self):
        aid = self.make()
        resp = self.client.post(
            f"/assignments/{aid}/status", data={"status": "done"}, follow_redirects=True
        )
        self.assertIn(b"Status must be pending, in progress or completed.", resp.data)
        self.assertEqual(service.get_assignment(aid)["status"], "pending")
        self.assertEqual(
            self.client.post("/assignments/999/status", data={"status": "pending"}).status_code, 404
        )

    def test_delete_flow(self):
        aid = self.make()
        resp = self.client.post(f"/assignments/{aid}/delete", follow_redirects=True)
        self.assertIn(b"Assignment deleted.", resp.data)
        self.assertNotIn(b"Lab report", resp.data)

    def test_delete_404_and_requires_post(self):
        aid = self.make()
        self.assertEqual(self.client.post("/assignments/999/delete").status_code, 404)
        self.assertEqual(self.client.get(f"/assignments/{aid}/delete").status_code, 405)

    def test_html_is_escaped(self):
        aid = self.make(title="<script>alert(1)</script>", description="<b>bold</b>")
        for url in ["/assignments/", f"/assignments/{aid}", f"/assignments/{aid}/edit"]:
            with self.subTest(url=url):
                data = self.client.get(url).data
                self.assertNotIn(b"<script>alert(1)</script>", data)
                self.assertNotIn(b"<b>bold</b>", data)

    def test_subject_list_shows_assignment_count_and_blocks_delete(self):
        self.make()
        page = self.client.get("/subjects/")
        self.assertIn(b"<td>1</td>", page.data)
        resp = self.client.post(f"/subjects/{self.subject_id}/delete", follow_redirects=True)
        self.assertIn(b"still has assignments", resp.data)

    def test_list_with_filters_in_query_string(self):
        self.make(title="Physics essay", priority="high", status="pending")
        other_sub = subject_service.create_subject("History", "HIST")
        service.create_assignment(valid_data(other_sub, title="History reading", priority="low", status="completed"))

        # Filter by subject
        resp = self.client.get(f"/assignments/?subject_id={self.subject_id}")
        self.assertIn(b"Physics essay", resp.data)
        self.assertNotIn(b"History reading", resp.data)

        # Filter by status
        resp = self.client.get("/assignments/?status=completed")
        self.assertNotIn(b"Physics essay", resp.data)
        self.assertIn(b"History reading", resp.data)

        # Filter by priority
        resp = self.client.get("/assignments/?priority=high")
        self.assertIn(b"Physics essay", resp.data)
        self.assertNotIn(b"History reading", resp.data)

    def test_list_filtered_empty_state_shows_clear_filters(self):
        self.make(title="Physics essay", status="pending")
        resp = self.client.get("/assignments/?status=completed")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"No assignments match your filters", resp.data)
        self.assertIn(b"Clear filters", resp.data)

    def test_filter_bar_renders_options(self):
        resp = self.client.get("/assignments/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"All subjects", resp.data)
        self.assertIn(b"All statuses", resp.data)
        self.assertIn(b"All priorities", resp.data)
        self.assertIn(b"Deadline (Soonest first)", resp.data)


if __name__ == "__main__":
    unittest.main()