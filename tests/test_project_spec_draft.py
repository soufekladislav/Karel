"""End-to-end draft contract: conversation + GitHub -> proposed existing action.

No AI-generated text is ever mistaken for an approved, stored Project Map.
"""
import json
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import Project, User, Chat, Message, ProjectMemory, GitHubRepoLink
from app.services.project_spec_draft import (
    is_spec_request, sources, parse, preview, existing_spec, SpecDraftError,
)
from app.services.actions import create_pending_action, execute_pending_group, pending_group

SAMPLE = {
    "purpose": "Řídit skutečný vývoj projektů Fresh Crackers.",
    "business_goal": "Snížit počet chybných realizací a potřebu správy GitHubu.",
    "functional_goal": "Karel vede rozhovor, čte GitHub, eviduje návrhy a předává práci AI Engine.",
    "project_scope": "Projektová mapa, Issue workflow, testování. Ne autonomní produkční nasazení.",
    "project_plan": "M1: schválená mapa; M2: čtecí GitHub audit; M3: Issue schválení a testy.",
}

class ProjectSpecDraftTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.engine = engine
        self.db = sessionmaker(bind=engine)()
        user = User(email="owner@example.cz", password_hash="none")
        self.db.add(user); self.db.flush()
        self.user = user
        self.project = Project(name="Karel", owner_id=user.id)
        self.db.add(self.project); self.db.flush()
        self.chat = Chat(project_id=self.project.id, title="Projektový chat")
        self.other_chat = Chat(project_id=self.project.id, title="Obchodní cíle")
        self.db.add_all([self.chat, self.other_chat]); self.db.flush()
        self.db.add(Message(chat_id=self.other_chat.id, user_id=user.id,
                            role="user", content="Chci, aby Karel řídil celý vývoj přes AI Engine a GitHub."))
        self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def test_original_user_command_triggers_structured_draft(self):
        self.assertTrue(is_spec_request("Sestav a ulož zadání Karla, ať máme popsán cílový stav."))
        self.assertTrue(is_spec_request("Připrav vývojový plán projektu."))
        self.assertTrue(is_spec_request("Sestav mi priority projektu a milníky."))
        self.assertFalse(is_spec_request("Ukaž mi seznam úkolů."))

    def test_collects_other_project_chats(self):
        self.assertIn("řídil celý vývoj", sources(self.db, self.project))

    def test_reuses_assistant_draft_only_as_unverified_proposal(self):
        self.db.add(Message(chat_id=self.other_chat.id, user_id=None,
                            role="assistant", content="### Návrh zadání projektu: "
                            + "Prioritou je řídit pipeline, GitHub a testování. " * 7))
        self.db.commit()
        source = sources(self.db, self.project)
        self.assertIn("PŘEDCHOZÍ NÁVRH ASISTENTA", source)
        self.assertIn("NEOVĚŘENÝ", source)

    def test_rejects_unstructured_or_incomplete_engine_output(self):
        for raw in ("Všechno jsem uložil", '{"purpose":"x"}', "[]"):
            with self.assertRaises(SpecDraftError):
                parse(raw)
        self.assertEqual(existing_spec(self.db, self.project.id), {})

    def test_approval_saves_each_field_and_preserves_prior_versions(self):
        self.db.add(ProjectMemory(project_id=self.project.id, kind="purpose",
                                  title="Účel", content="Původní účel", verified=True))
        self.db.commit()
        changes = parse(json.dumps(SAMPLE, ensure_ascii=False),
                        existing=existing_spec(self.db, self.project.id))
        msg = Message(chat_id=self.chat.id, user_id=self.user.id,
                      role="user", content="Sestav a ulož zadání Karla.")
        self.db.add(msg); self.db.flush()
        action = create_pending_action(
            self.db, self.project.id,
            {"type": "update_project_map", "title": "Schválit projektové zadání",
             "payload": changes}, source_message_id=msg.id)
        self.db.commit()
        self.assertIsNotNone(action)
        self.assertIn("nic ještě není", preview(changes).lower())
        self.assertEqual(existing_spec(self.db, self.project.id)["purpose"], "Původní účel")
        approved = execute_pending_group(
            self.db, self.project, pending_group(self.db, self.project.id,
                                                 chat_id=self.chat.id), self.user.id)
        self.db.commit()
        self.assertFalse(approved.get("errors"))
        saved = existing_spec(self.db, self.project.id)
        for k, v in SAMPLE.items():
            self.assertEqual(saved[k], v)
        history = self.db.query(ProjectMemory).filter(
            ProjectMemory.project_id == self.project.id,
            ProjectMemory.kind == "purpose").all()
        self.assertEqual(len(history), 2)
        self.assertIn("Původní účel", [x.content for x in history])

    def test_no_duplicate_revision_when_value_unchanged(self):
        from app.services.actions import _save_spec_value
        _save_spec_value(self.db, self.project.id, "purpose", SAMPLE["purpose"])
        self.db.commit()
        _save_spec_value(self.db, self.project.id, "purpose", SAMPLE["purpose"])
        self.db.commit()
        rows = self.db.query(ProjectMemory).filter_by(
            project_id=self.project.id, kind="purpose").all()
        self.assertEqual(len(rows), 1)

if __name__ == "__main__":
    unittest.main()
