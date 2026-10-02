import os
import tempfile
import unittest
from datetime import date

from tracker import create_app
from tracker.repositories import assignment_repository as repo
from tracker.services import assignment_service as service
from tracker.services import subject_service

TODAY = date(2026, 10, 1)


class FilterBase(unittest.TestCase):
    """Four assignments across two subjects.

    A  Lab report     Physics    high    pending      2026-11-01
    B  Quiz prep      Physics    low     in_progress  2026-10-05
    C  Étude de cas   Chemistry  medium  completed    2026-09-01  (description "analyse")
    D  Essay_100%     Chemistry  high    pending      2026-08-01  (overdue on TODAY)
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.tmp.name, "test.sqlite3")
        self.app = create_app({"DATABASE": db_path, "TESTING": True})
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

        self.physics = subject_service.create_subject("Physics", "")
        self.chemistry = subject_service.create_subject("Chemistry", "")
        self.ids = {}
        rows = [
            ("A", self.physics, "Lab report", "", "high", "pending", "2026-11-01"),
            ("B", self.physics, "Quiz prep", "", "low", "in_progress", "2026-10-05"),
            ("C", self.chemistry, "Étude de cas", "analyse", "medium", "completed", "2026-09-01"),
            ("D", self.chemistry, "Essay_100%", "", "high", "pending", "2026-08-01"),
        ]
        for key, subject, title, description, priority, status, deadline in rows:
            self.ids[key] = service.create_assignment({
                "subject_id": str(subject), "title": title, "description": description,
                "priority": priority, "status": status, "deadline": deadline,
            })
        self.by_id = {v: k for k, v in self.ids.items()}

    def tearDown(self):
        self.ctx.pop()
        self.tmp.cleanup()

    def keys(self, raw):
        """Letters (A-D) of the assignments returned for these query params."""
        assignments, _ = service.filter_assignments(raw, today=TODAY)
        return [self.by_id[a["id"]] for a in assignments]


class FilterServiceTests(FilterBase):
    def test_no_filters_returns_everything_in_default_order(self):
        self.assertEqual(self.keys({}), ["D", "B", "A", "C"])

    def test_filter_by_subject(self):
        self.assertEqual(sorted(self.keys({"subject": str(self.physics)})), ["A", "B"])
        self.assertEqual(sorted(self.keys({"subject": str(self.chemistry)})), ["C", "D"])

    def test_filter_by_status(self):
        self.assertEqual(sorted(self.keys({"status": "pending"})), ["A", "D"])
        self.assertEqual(self.keys({"status": "in_progress"}), ["B"])
        self.assertEqual(self.keys({"status": "completed"}), ["C"])

    def test_filter_by_priority(self):
        self.assertEqual(sorted(self.keys({"priority": "high"})), ["A", "D"])
        self.assertEqual(self.keys({"priority": "low"}), ["B"])

    def test_filters_combine_with_and(self):
        self.assertEqual(self.keys({"subject": str(self.physics), "status": "pending"}), ["A"])
        self.assertEqual(
            self.keys({"subject": str(self.chemistry), "priority": "high", "status": "pending"}),
            ["D"],
        )
        self.assertEqual(self.keys({"subject": str(self.physics), "status": "completed"}), [])

    def test_keyword_search_is_case_insensitive(self):
        self.assertEqual(self.keys({"q": "LAB"}), ["A"])
        self.assertEqual(self.keys({"q": "quiz"}), ["B"])

    def test_keyword_search_ignores_accents_both_ways(self):
        self.assertEqual(self.keys({"q": "etude"}), ["C"])
        self.assertEqual(self.keys({"q": "ÉTUDE"}), ["C"])
        self.assertEqual(self.keys({"q": "étude"}), ["C"])

    def test_keyword_search_covers_description(self):
        self.assertEqual(self.keys({"q": "ANALYSE"}), ["C"])

    def test_keyword_wildcards_are_treated_literally(self):
        self.assertEqual(self.keys({"q": "%"}), ["D"])       # only "Essay_100%"
        self.assertEqual(self.keys({"q": "_"}), ["D"])       # only "Essay_100%"
        self.assertEqual(self.keys({"q": "100%"}), ["D"])
        self.assertEqual(self.keys({"q": "\\"}), [])

    def test_keyword_is_trimmed_and_whitespace_collapsed(self):
        self.assertEqual(self.keys({"q": "  lab   report "}), ["A"])

    def test_overdue_filter(self):
        # D is pending and past due; C is past due but completed.
        self.assertEqual(self.keys({"overdue": "1"}), ["D"])
        self.assertEqual(self.keys({"overdue": "on"}), ["D"])
        self.assertEqual(sorted(self.keys({"overdue": "0"})), ["A", "B", "C", "D"])

    def test_overdue_combines_with_other_filters(self):
        self.assertEqual(self.keys({"overdue": "1", "priority": "low"}), [])
        self.assertEqual(self.keys({"overdue": "1", "priority": "high"}), ["D"])

    def test_invalid_filter_values_are_ignored(self):
        junk = {
            "subject": "abc", "status": "done", "priority": "urgent",
            "sort": "title; DROP TABLE assignments", "q": "bad\x00text",
            "overdue": "maybe",
        }
        assignments, filters = service.filter_assignments(junk, today=TODAY)
        self.assertEqual(len(assignments), 4)
        self.assertEqual(
            filters,
            {"subject_id": None, "status": "", "priority": "", "q": "",
             "overdue": False, "sort": "default", "active": False},
        )

    def test_unknown_and_oversized_subject_ignored(self):
        self.assertEqual(len(self.keys({"subject": "999"})), 4)
        self.assertEqual(len(self.keys({"subject": "9" * 40})), 4)
        self.assertEqual(len(self.keys({"subject": "-1"})), 4)

    def test_non_string_values_are_ignored(self):
        self.assertEqual(len(self.keys({"status": None, "q": None, "sort": 5})), 4)

    def test_long_keyword_is_truncated(self):
        _, filters = service.filter_assignments({"q": "a" * 500}, today=TODAY)
        self.assertEqual(len(filters["q"]), service.SEARCH_MAX_LENGTH)

    def test_filters_active_flag(self):
        self.assertFalse(service.parse_filters({})["active"])
        self.assertTrue(service.parse_filters({"status": "pending"})["active"])
        self.assertTrue(service.parse_filters({"sort": "title_asc"})["active"])
        self.assertTrue(service.parse_filters({"overdue": "1"})["active"])

    def test_sql_injection_in_keyword_matches_nothing_and_breaks_nothing(self):
        self.assertEqual(self.keys({"q": "' OR 1=1 --"}), [])
        self.assertEqual(self.keys({"q": "x'); DROP TABLE assignments; --"}), [])
        self.assertEqual(len(self.keys({})), 4)

    def test_sort_orders(self):
        expected = {
            "default": ["D", "B", "A", "C"],
            "deadline_asc": ["D", "C", "B", "A"],
            "deadline_desc": ["A", "B", "C", "D"],
            "priority_desc": ["D", "A", "C", "B"],
            "priority_asc": ["B", "C", "D", "A"],
            "title_asc": ["D", "C", "A", "B"],      # Essay, Étude, Lab, Quiz
            "title_desc": ["B", "A", "C", "D"],
            "subject_asc": ["D", "C", "B", "A"],    # Chemistry then Physics
            "status_asc": ["D", "A", "B", "C"],
            "created_desc": ["D", "C", "B", "A"],
        }
        for sort, keys in expected.items():
            with self.subTest(sort=sort):
                self.assertEqual(self.keys({"sort": sort}), keys)

    def test_every_sort_choice_has_sql_and_vice_versa(self):
        self.assertEqual(service.SORT_KEYS, set(repo.SORT_ORDERS))

    def test_repository_ignores_unknown_sort_key(self):
        rows = repo.search(sort="nonsense; DROP TABLE assignments")
        self.assertEqual(len(rows), 4)

    def test_sort_and_filter_together(self):
        self.assertEqual(
            self.keys({"priority": "high", "sort": "deadline_desc"}), ["A", "D"]
        )

    def test_count_assignments_ignores_filters(self):
        self.assertEqual(service.count_assignments(), 4)


class FilterRouteTests(FilterBase):
    def test_status_filter_shows_matching_rows_and_summary(self):
        page = self.client.get("/assignments/?status=pending").data
        self.assertIn(b"Lab report", page)
        self.assertIn(b"Essay_100%", page)
        self.assertNotIn(b"Quiz prep", page)
        self.assertIn(b"Showing 2 of 4 assignments", page)

    def test_no_filters_shows_all_and_no_reset_link(self):
        page = self.client.get("/assignments/").data
        self.assertIn(b"Showing 4 of 4 assignments", page)
        self.assertNotIn(b">Reset<", page)

    def test_reset_link_appears_when_filtered(self):
        page = self.client.get("/assignments/?priority=low").data
        self.assertIn(b">Reset<", page)

    def test_no_match_message(self):
        page = self.client.get("/assignments/?q=zzzz").data
        self.assertIn(b"No assignments match your filters.", page)
        self.assertIn(b"Showing 0 of 4 assignments", page)

    def test_empty_database_shows_original_message_without_filter_bar(self):
        for key in "ABCD":
            service.delete_assignment(self.ids[key])
        page = self.client.get("/assignments/").data
        self.assertIn(b"No assignments yet", page)
        self.assertNotIn(b'class="filters"', page)

    def test_selected_options_are_preserved(self):
        page = self.client.get(
            f"/assignments/?subject={self.physics}&status=pending&priority=high&sort=title_asc&overdue=1"
        ).data
        self.assertIn(f'value="{self.physics}" selected'.encode(), page)
        self.assertIn(b'value="pending" selected', page)
        self.assertIn(b'value="high" selected', page)
        self.assertIn(b'value="title_asc" selected', page)
        self.assertIn(b"checked", page)

    def test_search_text_is_escaped(self):
        page = self.client.get("/assignments/?q=%3Cscript%3Ealert(1)%3C/script%3E").data
        self.assertNotIn(b"<script>alert(1)", page)
        self.assertIn(b"&lt;script&gt;", page)

    def test_overdue_badge_class_on_overdue_row(self):
        page = self.client.get("/assignments/?q=essay").data
        self.assertIn(b"badge-overdue", page)

    def test_junk_query_does_not_break_page(self):
        resp = self.client.get("/assignments/?status=%00&sort=%27&subject=%FF&q=%00")
        self.assertEqual(resp.status_code, 200)

    def test_status_update_returns_to_filtered_list(self):
        resp = self.client.post(
            f"/assignments/{self.ids['A']}/status",
            data={"status": "completed", "origin": "list",
                  "return_query": "status=pending&sort=title_asc&evil=1"},
        )
        self.assertEqual(resp.status_code, 302)
        location = resp.headers["Location"]
        self.assertTrue(location.startswith("/assignments/?"))
        self.assertIn("status=pending", location)
        self.assertIn("sort=title_asc", location)
        self.assertNotIn("evil", location)

    def test_delete_returns_to_filtered_list(self):
        resp = self.client.post(
            f"/assignments/{self.ids['B']}/delete", data={"return_query": "priority=low"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.headers["Location"].endswith("/assignments/?priority=low"))

    def test_bad_return_query_falls_back_to_plain_list(self):
        many = "&".join(f"status=pending" for _ in range(60))
        for value in [many, "", "http://evil.example/&status=x", "%%%"]:
            with self.subTest(value=value[:30]):
                resp = self.client.post(
                    f"/assignments/{self.ids['A']}/status",
                    data={"status": "pending", "return_query": value},
                )
                self.assertEqual(resp.status_code, 302)
                self.assertTrue(resp.headers["Location"].startswith("/assignments/"))
                self.assertNotIn("evil", resp.headers["Location"])

    def test_list_forms_carry_the_current_query(self):
        page = self.client.get("/assignments/?status=pending").data
        self.assertIn(b'name="return_query" value="status=pending"', page)


if __name__ == "__main__":
    unittest.main()