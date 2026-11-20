"""End-to-end Karel schedule: GitHub verified source -> approval -> Pipeline."""
import base64
import hashlib
import json
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base
from app.models import Project, ProjectMemory, User, Chat, Message
from app.services.actions import create_pending_action, pending_group, execute_pending_group
from app.services.github_schedule import (
    is_schedule_request, read_live_karel_schedule, preview_schedule,
    ScheduleReadError,
)
from app.services.project_timeline import (
    BUNDLED_KAREL_SCHEDULE, DRAFT_PATH, load_project_timeline,
    normalize_milestones, parse_checked_in_schedule,
)

REPO = "soufekladislav/Karel"
HEAD = "a" * 40

class FakeReader:
    calls = []
    corrupt_blob = False
    available = True
    def __init__(self, token=""):
        self.token = token
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def _request(self, method, endpoint, *, params=None, optional=False):
        self.calls.append((method, endpoint, params))
        if endpoint == "/repos/" + REPO:
            return {"full_name": REPO, "default_branch": "main"}
        if endpoint == "/repos/" + REPO + "/branches/main":
            return {"commit": {"sha": HEAD}}
        if endpoint == "/repos/" + REPO + "/contents/docs/PROJECT_SCHEDULE.md":
            if not self.available:
                return None
            self.checked_ref = params["ref"]
            text = DRAFT_PATH.read_text(encoding="utf-8")
            raw = text.encode("utf-8")
            blob = hashlib.sha1(
                b"blob " + str(len(raw)).encode() + b"\x00" + raw).hexdigest()
            if self.corrupt_blob:
                blob = "0" * 40
            return {"type": "file", "size": len(raw), "sha": blob,
                    "encoding": "base64",
                    "content": base64.b64encode(raw).decode("ascii")}
        raise AssertionError("Unexpected GitHub endpoint: " + endpoint)

class ProjectSchedulePilotTests(unittest.TestCase):
    def setUp(self):
        FakeReader.calls = []
        FakeReader.corrupt_blob = False
        FakeReader.available = True
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.user = User(email="owner@example.cz", role="superadmin",
                         password_hash="hash")
        self.db.add(self.user)
        self.db.flush()
        self.project = Project(owner_id=self.user.id, name="Karel")
        self.unrelated = Project(owner_id=self.user.id, name="Cizí projekt")
        self.db.add_all((self.project, self.unrelated))
        self.db.flush()
        self.chat = Chat(project_id=self.project.id, title="Projektový chat")
        self.db.add(self.chat)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_real_user_phrase_triggers_github_schedule(self):
        self.assertTrue(is_schedule_request(
            "Podívej se do Githubu a připravo prosím časovou osu projektu Karel."))
        self.assertTrue(is_schedule_request(
            "Karle, sestav harmonogram projektu s konkrétními termíny."))
        self.assertFalse(is_schedule_request("Jaké jsou otevřené Issues?"))

    def test_pipeline_still_displays_draft_if_exon_omits_docs_directory(self):
        from app.services import project_timeline
        with patch.object(project_timeline, "DRAFT_PATH",
                          Path("/nonexistent-karel-schedule-folder/schedule.md")):
            result = load_project_timeline(
                self.db, self.project, is_admin=True,
                linked_repo=REPO)
        self.assertFalse(result["approved"])
        self.assertEqual(result["source"], "bundled_draft")
        self.assertEqual(len(result["items"]), 7)
        self.assertEqual(result["items"][0]["id"], "M0")
        self.assertEqual(result["items"][-1]["due_date"], "2027-01-29")
        self.assertEqual(result["overdue"], 0)

    def test_live_github_to_user_approval_to_pipeline(self):
        with patch.object(settings, "github_allowed_owners", ""), \
             patch.object(settings, "github_read_token", ""):
            proposal = read_live_karel_schedule(
                self.db, self.project, self.user, reader_factory=FakeReader)
        self.assertEqual(len(proposal["milestones"]), 7)
        self.assertEqual(proposal["source_commit_sha"], HEAD)
        self.assertIn("M0", preview_schedule(proposal))
        self.assertIn("Návrh", preview_schedule(proposal))
        self.assertEqual(FakeReader.calls[-1][2], {"ref": HEAD})
        msg = Message(chat_id=self.chat.id, user_id=self.user.id, role="user",
                      content="Podívej se do GitHubu a připrav časovou osu.")
        self.db.add(msg)
        self.db.flush()
        row = create_pending_action(self.db, self.project.id, {
            "type": "approve_project_schedule",
            "title": "Schválit harmonogram",
            "payload": proposal,
        }, source_message_id=msg.id)
        self.assertIsNotNone(row)
        self.db.commit()
        # No writes to the approved schedule before the user agrees.
        self.assertEqual(self.db.scalars(select(ProjectMemory).where(
            ProjectMemory.kind == "project_schedule")).all(), [])
        batch = execute_pending_group(
            self.db, self.project,
            pending_group(self.db, self.project.id, chat_id=self.chat.id),
            self.user.id)
        self.assertTrue(batch["ok"], batch)
        self.db.commit()
        self.assertEqual(batch["results"][0]["github_write"], "not_performed")
        self.assertEqual(batch["results"][0]["milestones_saved"], 7)
        approved = load_project_timeline(self.db, self.project,
                                         is_admin=True, linked_repo=REPO)
        self.assertTrue(approved["approved"])
        self.assertEqual(approved["source"], "approved")
        self.assertEqual(len(approved["items"]), 7)
        self.assertIn("github", json.loads(self.db.scalar(select(
            ProjectMemory).where(ProjectMemory.kind == "project_schedule")
        ).content)["source"])

    def test_unverified_blob_does_not_create_project_changes(self):
        FakeReader.corrupt_blob = True
        with patch.object(settings, "github_allowed_owners", ""), \
             patch.object(settings, "github_read_token", ""):
            with self.assertRaises(ScheduleReadError):
                read_live_karel_schedule(
                    self.db, self.project, self.user, reader_factory=FakeReader)
        self.assertFalse(self.db.scalars(select(ProjectMemory).where(
            ProjectMemory.kind == "project_schedule")).all())

    def test_foreign_project_cannot_receive_karel_schedule(self):
        with self.assertRaises(ScheduleReadError):
            read_live_karel_schedule(
                self.db, self.unrelated, self.user, reader_factory=FakeReader)
        self.assertFalse(FakeReader.calls)

    def test_normalize_bundled_matches_github_baseline_milestone_dates(self):
        doc = normalize_milestones(
            parse_checked_in_schedule(DRAFT_PATH.read_text(encoding="utf-8")))
        bundled = normalize_milestones(
            parse_checked_in_schedule(BUNDLED_KAREL_SCHEDULE))
        self.assertEqual(
            [(i["id"], i["start_date"], i["due_date"]) for i in doc],
            [(i["id"], i["start_date"], i["due_date"]) for i in bundled])

    def test_rendering_draft_in_real_jinja_when_docs_missing(self):
        from jinja2 import Environment, FileSystemLoader, select_autoescape
        from app.services import project_timeline
        template_dir = Path(__file__).resolve().parents[1] / "app" / "templates"
        template = Environment(loader=FileSystemLoader(str(template_dir)),
                               autoescape=select_autoescape(["html"])).get_template(
                                   "_project_timeline.html")
        with patch.object(project_timeline, "DRAFT_PATH",
                          Path("/nonexistent-karel-schedule-folder/schedule.md")):
            plan = load_project_timeline(
                self.db, self.project, is_admin=True, linked_repo=REPO)
        html = template.render(project=self.project, project_timeline=plan)
        self.assertIn("M0", html)
        self.assertIn("29.01.2027", html)
        self.assertIn("Návrh – čeká na schválení", html)


if __name__ == "__main__":
    unittest.main()
