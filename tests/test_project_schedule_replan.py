"""Regression: user asks for earlier test build, then 'zapracuj to'.

A successful chat reply is NOT an approval. The timeline changes only after
the existing approval action writes a version to ProjectMemory.
"""
import json
import unittest
from datetime import date
from pathlib import Path
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.database import Base
from app.models import Project, Chat, User, Message, ProjectMemory
from app.services.project_schedule_replan import (
    is_replan_request, prepare_replan, preview_replan, ReplanError,
)
from app.services.project_timeline import load_project_timeline
from app.services.actions import (
    create_pending_action, execute_pending_group, pending_group, execute_pending_action,
)

NOW = date(2026, 11, 20)
REPO = "soufekladislav/Karel"

class ReplanTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.user = User(email="user@example.cz", password_hash="hash", role="superadmin")
        self.db.add(self.user)
        self.db.flush()
        self.project = Project(name="Karel", owner_id=self.user.id)
        self.db.add(self.project)
        self.db.flush()
        self.chat = Chat(project_id=self.project.id, title="Harmonogram")
        self.db.add(self.chat)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _say(self, content):
        row = Message(chat_id=self.chat.id, user_id=self.user.id,
                      role="user", content=content)
        self.db.add(row); self.db.flush()
        return row

    def _propose(self, row):
        payload = prepare_replan(
            self.db, self.project, self.chat, self.user, row, today=NOW)
        proposal = create_pending_action(self.db, self.project.id, {
            "type": "approve_project_schedule",
            "title": "Schválit nové termíny harmonogramu",
            "payload": payload,
        }, source_message_id=row.id)
        self.db.commit()
        return payload, proposal

    def test_real_conversation_and_follow_up_are_routed_to_replan(self):
        self.assertTrue(is_replan_request(
            "Pojď si probrat termíny... ideálně do 20.12, delší dobu na testování."))
        self.assertTrue(is_replan_request("Fajn, zapracuj to prosím do harmonogramu."))
        self.assertTrue(is_replan_request(
            "Koukal jsem a není ten harmonogram aktualizovaný."))
        self.assertFalse(is_replan_request(
            "Podívej se do Githubu a připrav časovou osu projektu Karel."))

    def test_conversation_builds_full_plan_without_unrelated_task(self):
        self._say(
            "Pojď si probrat termíny... Chtěl bych to nastavit tak, "
            "abychom Karla dotáhli dříve - ideálně do 20.12, "
            "myslím, že by to mohlo být reálné a dát si delší dobu na testování.")
        row = self._say("Fajn, zapracuj to prosím do harmonogramu. Děkuji.")
        old = load_project_timeline(
            self.db, self.project, is_admin=True, linked_repo=REPO)
        payload, proposal = self._propose(row)
        self.assertIsNotNone(proposal)
        self.assertEqual(payload["target_test_date"], "2026-12-20")
        self.assertEqual(payload["base_source"], "checked_in_draft")
        dates = {m["id"]: m["due_date"] for m in payload["milestones"]}
        self.assertEqual(dates, {
            "M0": "2026-11-27", "M1": "2026-12-04",
            "M2": "2026-12-11", "M3": "2026-12-16",
            "M4": "2026-12-20", "M5": "2027-01-22",
            "M6": "2027-01-29",
        })
        self.assertEqual(old["items"][4]["due_date"], "2027-01-15")
        self.assertFalse(load_project_timeline(
            self.db, self.project, is_admin=True, linked_repo=REPO)["approved"])
        self.assertIn("20.12.2026", preview_replan(payload, old["items"]))
        self.assertEqual(
            self.db.scalars(select(ProjectMemory).where(
                ProjectMemory.kind == "project_schedule")).all(), [])
        self.assertEqual(
            self.db.scalars(select(ProjectMemory).where(
                ProjectMemory.kind == "pending_action")).all()[0].title,
            "Schválit nové termíny harmonogramu",
        )

        group = pending_group(self.db, self.project.id, chat_id=self.chat.id)
        self.assertEqual(len(group), 1)
        result = execute_pending_group(
            self.db, self.project, group, self.user.id)
        self.assertTrue(result["ok"], result)
        self.db.commit()
        self.assertEqual(result["results"][0]["github_write"], "not_performed")
        approved = load_project_timeline(
            self.db, self.project, is_admin=True, linked_repo=REPO)
        self.assertTrue(approved["approved"])
        self.assertEqual(approved["items"][4]["due_date"], "2026-12-20")
        self.assertEqual(approved["items"][5]["start_date"], "2026-12-21")
        self.assertEqual(approved["items"][5]["due_date"], "2027-01-22")
        saved = self.db.scalar(select(ProjectMemory).where(
            ProjectMemory.kind == "project_schedule"))
        content = json.loads(saved.content)
        self.assertEqual(content["version"], 1)
        self.assertEqual(content["source"], "user_chat_replan")
        self.assertEqual(content["github_sync_status"], "not_written")

    def test_stale_approval_is_rejected_after_another_plan_was_approved(self):
        msg1 = self._say("Chci termíny Karla ideálně do 20.12.2026.")
        payload1, pending1 = self._propose(msg1)
        # User later proposes a different target, without confirming old one.
        msg2 = self._say("Chci termín testovací verze do 27.12.2026.")
        payload2, pending2 = self._propose(msg2)
        r2 = execute_pending_action(self.db, self.project, pending2, self.user.id)
        self.db.commit()
        self.assertEqual(r2["version"], 1)
        with self.assertRaisesRegex(ValueError, "mezitím|změněn"):
            execute_pending_action(self.db, self.project, pending1, self.user.id)
        self.db.rollback()
        approved = load_project_timeline(
            self.db, self.project, is_admin=True, linked_repo=REPO)
        self.assertEqual(approved["items"][4]["due_date"], "2026-12-27")

    def test_missing_recent_target_fails_without_approval_proposal(self):
        row = self._say("Fajn, zapracuj to do harmonogramu.")
        with self.assertRaisesRegex(ReplanError, "termín"):
            prepare_replan(self.db, self.project, self.chat, self.user, row,
                           today=NOW)
        self.assertFalse(self.db.scalars(select(ProjectMemory).where(
            ProjectMemory.kind == "pending_action")).all())

    def test_date_rejects_unrealistic_and_invalid_deadlines(self):
        for value in ("Chci testovací verzi do 31.11.2026.",
                      "Posuň termín do 25.11.2026."):
            row = self._say(value)
            with self.assertRaises(ReplanError):
                prepare_replan(self.db, self.project, self.chat, self.user, row,
                               today=NOW)

    def test_unrelated_project_cannot_use_karel_calendar(self):
        other = Project(name="Jiný projekt", owner_id=self.user.id)
        self.db.add(other); self.db.flush()
        row = self._say("Chci termín testovací verze do 20.12.2026.")
        with self.assertRaises(ReplanError):
            prepare_replan(self.db, other, self.chat, self.user, row, today=NOW)

    def test_approval_card_renders_with_pending_proposal(self):
        row = self._say("Posuň termín testovací verze do 20.12.2026.")
        payload, pending = self._propose(row)
        draft = load_project_timeline(
            self.db, self.project, is_admin=True, linked_repo=REPO)
        base = Path(__file__).resolve().parents[1] / "app" / "templates"
        template = Environment(
            loader=FileSystemLoader(str(base)),
            autoescape=select_autoescape(["html"]),
        ).get_template("_project_timeline.html")
        html = template.render(
            project=self.project, project_timeline=draft, can_edit=True,
            pending_schedule={
                "chat_id": self.chat.id,
                "target_date": payload["target_test_date"],
                "items": payload["milestones"],
                "kind": payload["source"],
            },
        )
        self.assertIn("Schválit nové termíny", html)
        self.assertIn("2026-12-20", html)
        self.assertIn("actions/approve", html)
        self.assertIn("Návrh – čeká na schválení", html)
        self.assertIn("Zápis do GitHub Issues", html)

if __name__ == "__main__":
    unittest.main()
