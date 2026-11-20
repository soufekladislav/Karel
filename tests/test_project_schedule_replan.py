"""Regression: user asks for earlier test build, then 'zapracuj to'.

A successful chat reply is NOT an approval. The timeline changes only after
the existing approval action writes a version to ProjectMemory.
"""
import json
import asyncio
import copy
import unittest
from datetime import date
from types import SimpleNamespace
from pathlib import Path
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.database import Base
from app.models import Project, Chat, User, Message, ProjectMemory
from app.services.project_schedule_replan import (
    is_replan_request, is_schedule_overview_request, prepare_replan, preview_replan, ReplanError, _request_date,
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
        self.assertTrue(is_replan_request(
            "Nový termín funkční testovací verze do 20.12.2026."))
        self.assertTrue(is_schedule_overview_request(
            "Potřeboval bych si potvrdit termíny v pipeline..."))
        self.assertTrue(is_schedule_overview_request(
            "Můžeš prosím upravit projekt v pipeline?"))
        self.assertFalse(is_schedule_overview_request(
            "Máme v pipeline do 29.1., chci opravit do 20.12.2026"))
        self.assertFalse(is_replan_request(
            "Podívej se do Githubu a připrav časovou osu projektu Karel."))

    def test_exact_regression_old_date_is_not_the_new_target(self):
        original = (
            "Máme v pipeline nastaveno do 29.1., chtěl bych to "
            "rozvrhnout a opravit do 20.12. 2026"
        )
        self.assertTrue(is_replan_request(original))
        self.assertEqual(_request_date(original, today=NOW), date(2026, 12, 20))
        self.assertEqual(
            _request_date(
                "V současné Pipeline máme 29.01.2027, nový termín "
                "chci stanovit na 20.12.2026.", today=NOW),
            date(2026, 12, 20))
        self.assertEqual(
            _request_date(
                "Původně do 29.1., nově do 20.12.", today=NOW),
            date(2026, 12, 20))

    def test_date_roles_do_not_select_old_date(self):
        self.assertIsNone(_request_date(
            "V pipeline máme nastaveno do 29.1.", today=NOW))
        for ambiguous in (
            "Chci testovací verzi do 20.12. nebo do 27.12.",
            "Chci změnit termíny 29.1. a 20.12., nejsem rozhodnutý.",
        ):
            with self.subTest(ambiguous=ambiguous), self.assertRaises(ReplanError):
                _request_date(ambiguous, today=NOW)
        self.assertEqual(_request_date(
            "Chci testovací verzi do 20.12.2026", today=NOW),
            date(2026, 12, 20))

    def test_invalid_legacy_proposal_approval_redirects_pipeline_with_error(self):
        from app import main
        msg = self._say(
            "Máme v pipeline nastaveno do 29.1., chtěl bych to "
            "opravit do 20.12.2026.")
        payload = prepare_replan(
            self.db, self.project, self.chat, self.user, msg, today=NOW)
        payload["target_test_date"] = "2027-01-29"
        for item in payload["milestones"]:
            if item["id"] == "M4":
                item["due_date"] = "2027-01-29"
        create_pending_action(self.db, self.project.id, {
            "type":"approve_project_schedule",
            "title":"Nesprávný starý návrh",
            "payload":payload}, source_message_id=msg.id)
        self.db.commit()
        with patch("app.main.require_user", return_value=self.user):
            res = main.approve_chat_actions(
                SimpleNamespace(), self.project.id, self.chat.id,
                return_view="development", db=self.db)
        self.assertEqual(res.status_code, 303)
        self.assertIn("view=development&error=", res.headers["location"])
        self.assertEqual(self.db.scalars(select(ProjectMemory).where(
            ProjectMemory.kind == "project_schedule")).all(), [])

    def test_invalid_old_pending_has_no_approval_button(self):
        from app.services.project_schedule_replan import _chat_target
        from jinja2 import Environment, FileSystemLoader, select_autoescape
        original = self._say(
            "Máme v pipeline do 29.1., chtěl bych to opravit do 20.12.2026.")
        current_target = _chat_target(
            self.db, self.chat.id, original, today=NOW)
        self.assertEqual(current_target, date(2026, 12, 20))
        base = Path(__file__).resolve().parents[1] / "app" / "templates"
        template = Environment(
            loader=FileSystemLoader(str(base)),
            autoescape=select_autoescape(["html"]),
        ).get_template("_project_timeline.html")
        view = load_project_timeline(
            self.db, self.project, is_admin=True, linked_repo=REPO)
        html = template.render(
            project=self.project, project_timeline=view, can_edit=True,
            pending_schedule={
                "chat_id": self.chat.id, "target_date": "2027-01-29",
                "items": view["items"], "kind": "user_chat_replan",
                "valid": False,
            },
        )
        self.assertIn("Návrh je chybný", html)
        self.assertNotIn('type="submit">Schválit nové termíny', html)

    def test_exact_user_prompt_creates_20dec_plan_and_never_29jan(self):
        message = self._say(
            "Máme v pipeline nastaveno do 29.1., chtěl bych to "
            "rozvrhnout a opravit do 20.12. 2026"
        )
        payload, row = self._propose(message)
        self.assertEqual(payload["target_test_date"], "2026-12-20")
        self.assertEqual(next(x for x in payload["milestones"]
                              if x["id"]=="M4")["due_date"],"2026-12-20")
        answer = preview_replan(
            payload, load_project_timeline(
                self.db, self.project, is_admin=True,
                linked_repo=REPO)["items"])
        self.assertIn("**Funkční testovací verze do 20.12.2026.**", answer)
        self.assertNotIn("**Funkční testovací verze do 29.01.2027.**", answer)

    def test_preupgrade_wrong_29jan_proposal_is_not_approvable(self):
        msg = self._say(
            "Máme v pipeline nastaveno do 29.1., chtěl bych to "
            "rozvrhnout a opravit do 20.12. 2026")
        correct = prepare_replan(
            self.db, self.project, self.chat, self.user, msg, today=NOW)
        bad = copy.deepcopy(correct)
        bad["target_test_date"] = "2027-01-29"
        for milestone in bad["milestones"]:
            if milestone["id"] == "M4":
                milestone["due_date"] = "2027-01-29"
        row = create_pending_action(self.db, self.project.id, {
            "type": "approve_project_schedule", "title": "Starý chybný návrh",
            "payload": bad}, source_message_id=msg.id)
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "jiné datum"):
            execute_pending_action(self.db, self.project, row, self.user.id)
        self.assertEqual(
            self.db.scalars(select(ProjectMemory).where(
                ProjectMemory.kind == "project_schedule")).all(), [])
        self.assertEqual(json.loads(row.content)["state"], "pending")

    def test_real_chat_route_uses_date_intent_and_approves_current_timeline(self):
        from app import main
        query = ("Máme v pipeline nastaveno do 29.1., chtěl bych to "
                 "rozvrhnout a opravit do 20.12. 2026")
        with patch("app.main.require_user", return_value=self.user):
            sent = asyncio.run(main.send_message(
                SimpleNamespace(), self.project.id, self.chat.id,
                message=query, attachments=[], db=self.db))
        self.assertEqual(sent.status_code, 303)
        assistant = self.db.scalar(select(Message).where(
            Message.chat_id == self.chat.id,
            Message.role == "assistant").order_by(Message.id.desc()))
        self.assertIn("20.12.2026", assistant.content)
        self.assertNotIn(
            "Funkční testovací verze do 29.01.2027", assistant.content)
        pending = pending_group(self.db, self.project.id, chat_id=self.chat.id)
        self.assertEqual(len(pending), 1)
        self.assertEqual(
            json.loads(pending[0].content)["payload"]["target_test_date"],
            "2026-12-20")
        with patch("app.main.require_user", return_value=self.user):
            approved = main.approve_chat_actions(
                SimpleNamespace(), self.project.id, self.chat.id,
                return_view="development", db=self.db)
        self.assertEqual(approved.status_code, 303)
        self.assertIn("view=development", approved.headers["location"])
        self.assertIn("#project-timeline", approved.headers["location"])
        data = load_project_timeline(
            self.db, self.project, is_admin=True, linked_repo=REPO)
        self.assertTrue(data["approved"])
        self.assertEqual(data["items"][4]["due_date"], "2026-12-20")

    def test_pipeline_overview_reads_actual_dates_without_ai_or_new_action(self):
        from app import main
        with patch("app.main.require_user", return_value=self.user), \
             patch("app.main.engine_chat", side_effect=AssertionError("No AI for overview")):
            response = asyncio.run(main.send_message(
                SimpleNamespace(), self.project.id, self.chat.id,
                message="Potřeboval bych si potvrdit termíny v pipeline...",
                attachments=[], db=self.db))
        self.assertEqual(response.status_code, 303)
        answer = self.db.scalar(select(Message).where(
            Message.chat_id == self.chat.id, Message.role == "assistant"))
        self.assertIn("2027-01-15", answer.content)
        self.assertIn("Předběžný", answer.content)
        self.assertFalse(pending_group(self.db, self.project.id,
                                       chat_id=self.chat.id))

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
        self.assertIn('name="return_view" value="development"', html)
        self.assertIn("Návrh – čeká na schválení", html)
        self.assertIn("Zápis do GitHub Issues", html)

if __name__ == "__main__":
    unittest.main()
