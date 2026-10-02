import os
import tempfile
import unittest
from datetime import date, timedelta

from tracker import create_app
from tracker.services import assignment_service, dashboard_service as dash, subject_service

TODAY = date(2026, 10, 1)


def iso(offset_days, base=TODAY):
    return (base + timedelta(days=offset_days)).isoformat()


class DashboardBase(unittest.TestCase):
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

    def add(self, subject_id, title, priority="medium", status="pending", deadline="2026-12-01"):
        return assignment_service.create_assignment({
            "subject_id": str(subject_id), "title": title, "description": "",
            "priority": priority, "status": status, "deadline": deadline,
        })


class DashboardServiceTests(DashboardBase):
    def setUp(self):
        super().setUp()
        self.physics = subject_service.create_subject("Physics", "")
        self.chemistry = subject_service.create_subject("Chemistry", "")
        self.maths = subject_service.create_subject("Maths", "")  # stays empty
        # Physics
        self.add(self.physics, "A", "high", "pending", "2026-10-01")       # due today
        self.add(self.physics, "B", "low", "in_progress", "2026-10-05")    # in 4 days
        # Chemistry
        self.add(self.chemistry, "C", "medium", "completed", "2026-09-01")  # done, in the past
        self.add(self.chemistry, "D", "high", "pending", "2026-08-01")      # overdue
        self.add(self.chemistry, "E", "medium", "pending", "2026-10-20")    # later

    def test_status_counts_and_totals(self):
        stats = dash.get_dashboard(TODAY)
        self.assertEqual(stats["total"], 5)
        self.assertEqual(stats["counts"], {"pending": 3, "in_progress": 1, "completed": 1})
        self.assertEqual(stats["open"], 4)
        self.assertTrue(stats["has_data"])
        self.assertEqual(
            [(s["value"], s["count"]) for s in stats["status_counts"]],
            [("pending", 3), ("in_progress", 1), ("completed", 1)],
        )

    def test_completion_rate(self):
        self.assertEqual(dash.get_dashboard(TODAY)["completion_rate"], 20)

    def test_overdue_excludes_completed(self):
        stats = dash.get_dashboard(TODAY)
        self.assertEqual(stats["overdue"], 1)  # D only; C is completed
        self.assertEqual([a["title"] for a in stats["overdue_list"]], ["D"])
        self.assertEqual(stats["overdue_list"][0]["due_label"], "61 days overdue")

    def test_due_today_and_due_this_week(self):
        stats = dash.get_dashboard(TODAY)
        self.assertEqual(stats["due_today"], 1)
        self.assertEqual(stats["due_this_week"], 2)   # A (today) and B (+4 days)
        self.assertEqual([a["title"] for a in stats["due_soon"]], ["A", "B"])
        self.assertEqual([a["due_label"] for a in stats["due_soon"]], ["Due today", "In 4 days"])

    def test_priority_breakdown_counts_only_open_work(self):
        stats = dash.get_dashboard(TODAY)
        self.assertEqual(
            [(p["value"], p["count"], p["percent"]) for p in stats["priorities"]],
            [("high", 2, 50), ("medium", 1, 25), ("low", 1, 25)],
        )

    def test_subject_breakdown_includes_empty_subjects_sorted_by_name(self):
        rows = {s["name"]: s for s in dash.get_dashboard(TODAY)["subjects"]}
        self.assertEqual(
            [s["name"] for s in dash.get_dashboard(TODAY)["subjects"]],
            ["Chemistry", "Maths", "Physics"],
        )
        self.assertEqual(
            (rows["Chemistry"]["total"], rows["Chemistry"]["completed"],
             rows["Chemistry"]["open"], rows["Chemistry"]["percent"]),
            (3, 1, 2, 33),
        )
        self.assertEqual((rows["Maths"]["total"], rows["Maths"]["percent"]), (0, 0))
        self.assertEqual((rows["Physics"]["total"], rows["Physics"]["percent"]), (2, 0))

    def test_stats_follow_status_changes(self):
        for item in assignment_service.list_assignments():
            assignment_service.update_status(item["id"], "completed")
        stats = dash.get_dashboard(TODAY)
        self.assertEqual(stats["completion_rate"], 100)
        self.assertEqual((stats["open"], stats["overdue"], stats["due_this_week"]), (0, 0, 0))
        self.assertEqual(stats["due_soon"], [])
        self.assertEqual(stats["overdue_list"], [])
        self.assertTrue(all(p["count"] == 0 and p["percent"] == 0 for p in stats["priorities"]))


class DashboardEdgeCaseTests(DashboardBase):
    def test_empty_database(self):
        stats = dash.get_dashboard(TODAY)
        self.assertFalse(stats["has_data"])
        self.assertEqual((stats["total"], stats["open"], stats["completion_rate"]), (0, 0, 0))
        self.assertEqual(stats["counts"], {"pending": 0, "in_progress": 0, "completed": 0})
        self.assertEqual((stats["overdue"], stats["due_today"], stats["due_this_week"]), (0, 0, 0))
        self.assertEqual(stats["subjects"], [])
        self.assertEqual(stats["due_soon"], [])

    def test_subjects_without_assignments_do_not_crash(self):
        subject_service.create_subject("Physics", "")
        stats = dash.get_dashboard(TODAY)
        self.assertFalse(stats["has_data"])
        self.assertEqual(len(stats["subjects"]), 1)

    def test_lists_are_limited_but_counts_are_not(self):
        sid = subject_service.create_subject("Physics", "")
        for i in range(8):
            self.add(sid, f"Late {i}", deadline=iso(-1 - i))
        for i in range(7):
            self.add(sid, f"Soon {i}", deadline=iso(i))
        stats = dash.get_dashboard(TODAY)
        self.assertEqual(stats["overdue"], 8)
        self.assertEqual(len(stats["overdue_list"]), dash.LIST_LIMIT)
        self.assertEqual(stats["due_this_week"], 7)
        self.assertEqual(len(stats["due_soon"]), dash.LIST_LIMIT)
        # oldest deadline first
        self.assertEqual(stats["overdue_list"][0]["title"], "Late 7")
        self.assertEqual(stats["due_soon"][0]["title"], "Soon 0")

    def test_week_window_boundaries(self):
        sid = subject_service.create_subject("Physics", "")
        self.add(sid, "Yesterday", deadline=iso(-1))
        self.add(sid, "Day 7", deadline=iso(7))
        self.add(sid, "Day 8", deadline=iso(8))
        stats = dash.get_dashboard(TODAY)
        self.assertEqual([a["title"] for a in stats["due_soon"]], ["Day 7"])
        self.assertEqual(stats["due_this_week"], 1)
        self.assertEqual([a["title"] for a in stats["overdue_list"]], ["Yesterday"])

    def test_completed_work_never_listed(self):
        sid = subject_service.create_subject("Physics", "")
        self.add(sid, "Old done", status="completed", deadline=iso(-5))
        self.add(sid, "Soon done", status="completed", deadline=iso(2))
        stats = dash.get_dashboard(TODAY)
        self.assertEqual((stats["overdue"], stats["due_this_week"]), (0, 0))
        self.assertEqual((stats["overdue_list"], stats["due_soon"]), ([], []))

    def test_percent_rounding(self):
        self.assertEqual(dash.percent(2, 3), 67)
        self.assertEqual(dash.percent(1, 3), 33)
        self.assertEqual(dash.percent(1, 2), 50)
        self.assertEqual(dash.percent(1, 8), 13)   # 12.5 rounds up
        self.assertEqual(dash.percent(5, 5), 100)
        self.assertEqual(dash.percent(0, 5), 0)
        self.assertEqual(dash.percent(0, 0), 0)

    def test_due_label_wording(self):
        cases = {-1: "1 day overdue", -3: "3 days overdue", 0: "Due today",
                 1: "Due tomorrow", 5: "In 5 days"}
        for days, label in cases.items():
            with self.subTest(days=days):
                self.assertEqual(dash.due_label(days), label)


class DashboardRouteTests(DashboardBase):
    def test_home_page_is_the_dashboard_and_shows_empty_state(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Dashboard", resp.data)
        self.assertIn(b"Your dashboard is ready", resp.data)
        self.assertIn(b"Student Assignment Tracker", resp.data)

    def test_health_still_works(self):
        data = self.client.get("/health").get_json()
        self.assertEqual(data["tables"], ["assignments", "subjects"])

    def test_dashboard_shows_statistics(self):
        today = date.today()
        sid = subject_service.create_subject("Physics", "")
        self.add(sid, "Due now", "high", "pending", today.isoformat())
        self.add(sid, "Late one", "low", "pending", (today - timedelta(days=1)).isoformat())
        self.add(sid, "Finished", "medium", "completed", (today - timedelta(days=9)).isoformat())
        page = self.client.get("/").data.decode()
        self.assertIn("Due today", page)
        self.assertIn("1 day overdue", page)
        self.assertIn("Due now", page)
        self.assertIn("Late one", page)
        self.assertIn("33%", page)                    # 1 of 3 completed
        self.assertIn("Progress by subject", page)
        self.assertIn("Physics", page)

    def test_stat_cards_link_to_filtered_lists(self):
        sid = subject_service.create_subject("Physics", "")
        self.add(sid, "Task")
        page = self.client.get("/").data.decode()
        self.assertIn("/assignments/?status=pending", page)
        self.assertIn("/assignments/?status=in_progress", page)
        self.assertIn("/assignments/?status=completed", page)
        self.assertIn("/assignments/?overdue=1", page)
        self.assertIn(f"/assignments/?subject={sid}", page)

    def test_titles_are_escaped(self):
        sid = subject_service.create_subject("<b>Sub</b>", "")
        self.add(sid, "<script>alert(1)</script>", deadline=date.today().isoformat())
        page = self.client.get("/").data
        self.assertNotIn(b"<script>alert(1)</script>", page)
        self.assertNotIn(b"<b>Sub</b>", page)

    def test_nav_links_present(self):
        page = self.client.get("/").data.decode()
        for target in ["/subjects/", "/assignments/"]:
            self.assertIn(f'href="{target}"', page)


if __name__ == "__main__":
    unittest.main()