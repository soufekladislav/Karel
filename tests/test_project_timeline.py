"""Regression tests for dated milestone Pipeline and truthful approval state."""
import json
import unittest
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Project, ProjectMemory, User
from app.services.project_timeline import (
    DRAFT_PATH, parse_checked_in_schedule, normalize_milestones,
    timeline_view, load_project_timeline,
)


class ProjectTimelineTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        user = User(email="test@example.cz", password_hash="hash", role="superadmin")
        self.db.add(user)
        self.db.flush()
        self.project = Project(owner_id=user.id, name="Karel")
        self.other = Project(owner_id=user.id, name="Jiná aplikace")
        self.db.add_all((self.project, self.other))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_real_schedule_document_has_seven_dated_milestones(self):
        self.assertTrue(DRAFT_PATH.is_file())
        rows = normalize_milestones(
            parse_checked_in_schedule(DRAFT_PATH.read_text(encoding="utf-8"))
        )
        self.assertEqual([row["id"] for row in rows],
                         ["M0", "M1", "M2", "M3", "M4", "M5", "M6"])
        self.assertEqual(rows[0]["due_date"], "2026-11-25")
        self.assertEqual(rows[-1]["due_date"], "2027-01-29")
        self.assertIn(20, rows[2]["issue_numbers"])
        self.assertIn("M3", rows[4]["dependencies"])

    def test_draft_is_never_reported_overdue_even_after_deadline(self):
        snapshot = load_project_timeline(
            self.db, self.project, is_admin=True, linked_repo="soufekladislav/Karel"
        )
        self.assertFalse(snapshot["approved"])
        self.assertEqual(snapshot["source"], "checked_in_draft")
        later = timeline_view(snapshot["items"], approved=False,
                              today=date(2027, 2, 10))
        self.assertEqual(later["overdue"], 0)
        self.assertTrue(all(x["view_status"] == "planned" for x in later["items"]))

    def test_draft_is_not_leaked_to_unrelated_projects_or_users(self):
        self.assertFalse(load_project_timeline(
            self.db, self.other, is_admin=True)["items"])
        self.assertFalse(load_project_timeline(
            self.db, self.project, is_admin=False)["items"])
        self.assertFalse(load_project_timeline(
            self.db, self.project, is_admin=True,
            linked_repo="other-person/OtherProject")["items"])

    def test_approved_plan_overrides_checked_in_document(self):
        payload = {"version": 1, "milestones": [{
            "id": "M9", "title": "Nový schválený milník",
            "start_date": "2026-12-01", "due_date": "2026-12-04",
            "acceptance": "Uživatelsky ověřeno", "dependencies": "",
            "issue_numbers": [12], "status": "planned"
        }]}
        self.db.add(ProjectMemory(
            project_id=self.project.id, kind="project_schedule",
            title="Schválený harmonogram",
            content=json.dumps(payload), verified=True,
        ))
        self.db.commit()
        snapshot = load_project_timeline(self.db, self.project, is_admin=True)
        self.assertTrue(snapshot["approved"])
        self.assertEqual(snapshot["source"], "approved")
        self.assertEqual(len(snapshot["items"]), 1)
        self.assertEqual(snapshot["items"][0]["id"], "M9")
        later = timeline_view(snapshot["items"], approved=True,
                              today=date(2026, 12, 5))
        self.assertEqual(later["overdue"], 1)

    def test_invalid_approved_dates_do_not_render_false_timeline(self):
        self.db.add(ProjectMemory(
            project_id=self.other.id, kind="project_schedule",
            title="Nesprávný harmonogram",
            content='{"milestones":[{"id":"M1","title":"x","start_date":"2026-12-08","due_date":"2026-12-02"}]}',
            verified=True,
        ))
        self.db.commit()
        result = load_project_timeline(self.db, self.other, is_admin=False)
        self.assertEqual(result["items"], [])
        self.assertFalse(result["approved"])

    def test_frontend_contains_timeline_in_pipeline_not_a_new_page(self):
        template = (Path(__file__).resolve().parents[1] /
                    "app" / "templates" / "project.html").read_text(encoding="utf-8")
        fragment = (Path(__file__).resolve().parents[1] /
                    "app" / "templates" / "_project_timeline.html").read_text(
                        encoding="utf-8")
        self.assertIn("{% include '_project_timeline.html' %}", template)
        self.assertIn("Harmonogram projektu", fragment)
        self.assertIn("Návrh – čeká na schválení", fragment)
        self.assertIn("item.date_label", fragment)
        self.assertIn("project_timeline.approved", fragment)


if __name__ == "__main__":
    unittest.main()
