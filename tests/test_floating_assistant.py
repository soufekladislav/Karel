"""Regression: Karel works from every screen and proves committed actions."""
import asyncio
import json
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Project, ProjectMemory, User, Chat, Message, Task
from app.services.assistant_work_context import screen_evidence, clean_screen
from app.services.schedule_feasibility import selected_scope
from app.services.project_schedule_replan import is_replan_request
from app.services.project_timeline import load_project_timeline


NOW = date(2026, 11, 22)


class AssistantFlowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.user = User(email="owner@example.cz", password_hash="hash",
                         role="superadmin")
        self.db.add(self.user); self.db.flush()
        self.project = Project(name="Karel", owner_id=self.user.id)
        self.other = Project(name="Ostatní projekt", owner_id=self.user.id)
        self.db.add_all([self.project, self.other]); self.db.flush()
        self.chat = Chat(project_id=self.project.id, title="Pracovní chat")
        self.db.add(self.chat); self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def test_screen_context_is_server_verified_and_project_scoped(self):
        self.db.add(Task(project_id=self.project.id,chat_id=self.chat.id,
                         title="Ověřit schválené termíny", status="todo"))
        self.db.add(Task(project_id=self.other.id,title="Cizí důvěrný úkol",
                         status="working"))
        self.db.add(ProjectMemory(
            project_id=self.project.id,
            kind="fresh_core_read_credential", title="SECRET",
            content="SECRET_WRITE_KEY_SHOULD_NEVER_LEAK",
            verified=True,
        ))
        self.db.commit()
        tasks = screen_evidence(self.db,self.project,self.user,"tasks")
        self.assertIn("Ověřit schválené termíny",tasks["context"])
        self.assertNotIn("Cizí důvěrný úkol",tasks["context"])
        self.assertNotIn("SECRET_WRITE_KEY_SHOULD_NEVER_LEAK",tasks["context"])
        plan = screen_evidence(self.db,self.project,self.user,"development")
        self.assertIn("M4",plan["context"])
        self.assertIn("2027-01-15",plan["context"])
        self.assertIn("Pipeline",plan["label"])
        self.assertEqual(clean_screen("not_real_screen"),"chat")

    def test_exact_user_phrase_is_executable_and_selects_limited_scope(self):
        message = ("Vzhledem k tomu, že testujeme na reálném provozu Karla, "
                   "souhlasím s úpravou plánu při omezeném testování. "
                   "Tudíž mi zapracuj do pipeline plán do 20.12.")
        self.assertTrue(is_replan_request(message))
        self.assertEqual(selected_scope(message),"limited_mvp")
        from app.services.project_schedule_replan import _request_date
        self.assertEqual(_request_date(message,today=NOW),
                         date(2026,12,20))

    def test_widget_send_uses_real_chat_and_context_in_engine(self):
        from app import main
        model = AsyncMock(return_value="Na obrazovce Pipeline ověřím milníky.")
        with patch("app.main.require_user",return_value=self.user), \
             patch("app.main.engine_chat",model):
            response = asyncio.run(main.floating_assistant_send(
                SimpleNamespace(),self.project.id,chat_id=self.chat.id,
                message="Co mám na této obrazovce teď řešit?",
                screen_context="development", db=self.db))
        self.assertEqual(response.status_code,200)
        data = json.loads(response.body)
        self.assertEqual(data["chat_id"],self.chat.id)
        self.assertEqual(data["context_label"],"Pipeline projektu")
        self.assertEqual(data["messages"][-1]["role"],"assistant")
        self.assertIn("Na obrazovce Pipeline",data["messages"][-1]["content"])
        self.assertTrue(model.await_count)
        system = model.await_args.args[0]
        self.assertIn("VIDITELNÁ OBRAZOVKA: Pipeline projektu",system)
        self.assertIn("M4",system)
        self.assertIn("ověřené backendové akce",system)

    def test_conversation_schedule_approval_returns_verified_receipt(self):
        from app import main
        text = ("Souhlasím s úpravou plánu při omezeném testování. "
                "Tudíž mi zapracuj do pipeline plán do 20.12.")
        with patch("app.main.require_user",return_value=self.user), \
             patch("app.main.date",wraps=date) as fake_date:
            fake_date.today.return_value = NOW
            result = asyncio.run(main.floating_assistant_send(
                SimpleNamespace(),self.project.id,chat_id=self.chat.id,
                message=text,screen_context="development",db=self.db))
        self.assertEqual(result.status_code,200)
        staged=json.loads(result.body)
        self.assertEqual(len(staged["pending"]),1)
        self.assertEqual(staged["pending"][0]["type"],"approve_project_schedule")
        self.assertIn("2026-12-20",staged["pending"][0]["description"])
        self.assertIsNone(staged["receipt"])
        with patch("app.main.require_user",return_value=self.user), \
             patch("app.main.settings.github_schedule_write_enabled",False):
            approved=main.floating_assistant_approve(
                SimpleNamespace(),self.project.id,
                chat_id=self.chat.id,db=self.db)
        self.assertEqual(approved.status_code,200)
        final=json.loads(approved.body)
        self.assertEqual(len(final["pending"]),0)
        self.assertIn("Schváleno",final["approval_notice"])
        self.assertIn("verze",final["receipt"]["text"])
        self.assertIn("blocked",final["receipt"]["text"])
        plan=load_project_timeline(
            self.db,self.project,is_admin=True,
            linked_repo="soufekladislav/Karel")
        self.assertTrue(plan["approved"])
        self.assertEqual(plan["items"][4]["due_date"],"2026-12-20")
        content=self.db.scalar(select(ProjectMemory).where(
            ProjectMemory.kind=="project_schedule"))
        self.assertIsNotNone(content)
        self.assertEqual(json.loads(content.content)["version"],1)
        last_answer=self.db.scalars(select(Message).where(
            Message.chat_id==self.chat.id,
            Message.role=="assistant").order_by(Message.id.desc())).first()
        self.assertNotIn("GitHub synchronizace: synced",last_answer.content)

    def test_ai_cannot_claim_an_unverified_write(self):
        from app.services.action_claim_guard import qualify_unverified_reply
        result = qualify_unverified_reply(
            "Zapracuj změny do pipeline.",
            "Zapracováno do projektu. Vytvořil jsem harmonogram.",
            pending_actions=False,
        )
        self.assertIn("STAV: Neprovedeno",result)
        self.assertNotIn("Zapracováno do projektu",result)
        staged = qualify_unverified_reply(
            "Ulož harmonogram", "Uloženo", pending_actions=True,
        )
        self.assertIn("Připraven návrh",staged)
        self.assertIn("Zatím nic nebylo změněno",staged)
        self.assertEqual(qualify_unverified_reply(
            "Jaká je adresa webu?", "Adresa není ověřena.",
            pending_actions=False), "Adresa není ověřena.")

    def test_component_is_shared_and_scroll_jumps_are_removed(self):
        templates=Path(__file__).resolve().parents[1]/"app"/"templates"
        base=(templates/"base.html").read_text(encoding="utf-8")
        proj=(templates/"project.html").read_text(encoding="utf-8")
        drawer=(templates/"_assistant_drawer.html").read_text(encoding="utf-8")
        self.assertIn("{% include '_assistant_drawer.html' %}",base)
        self.assertNotIn('<aside class="karel-quick-panel"',proj)
        self.assertIn('id="karel-assistant-launcher"',drawer)
        self.assertIn('id="karel-assistant-drawer"',drawer)
        self.assertIn("box.scrollTop=box.scrollHeight",proj)
        self.assertNotIn("requestAnimationFrame(()=>{box.scrollTop",proj)
        self.assertNotIn('placeholder="Napiš Karlovi…" autofocus',proj)

    def test_selected_chat_must_belong_to_selected_project(self):
        from app.services.assistant_panel_state import assistant_state
        foreign = Chat(project_id=self.other.id,title="Cizí chat")
        second = Chat(project_id=self.project.id,title="Druhý chat")
        self.db.add_all([foreign,second])
        self.db.commit()
        own = assistant_state(
            self.db,self.project,self.user,screen="chat",
            chat_id=self.chat.id,can_edit=True)
        self.assertEqual(own["chat_id"],self.chat.id)
        guarded = assistant_state(
            self.db,self.project,self.user,screen="chat",
            chat_id=foreign.id,can_edit=True)
        self.assertNotEqual(guarded["chat_id"],foreign.id)
        self.assertEqual(guarded["project_id"],self.project.id)

    def test_api_state_uses_authorized_project(self):
        from app import main
        with patch("app.main.require_user",return_value=self.user):
            response=main.floating_assistant_state(
                SimpleNamespace(),self.project.id,screen="tasks",db=self.db)
        self.assertEqual(response.status_code,200)
        data=json.loads(response.body)
        self.assertEqual(data["project_id"],self.project.id)
        self.assertEqual(data["chat_id"],self.chat.id)
        self.assertEqual(data["context_label"],"Úkoly")


if __name__=="__main__":
    unittest.main()
