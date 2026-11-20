"""Real chat -> project binding -> GitHub reader -> evidence -> safe answer."""
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base
from app.models import Chat, GitHubRepoLink, Project, User
from app.services.github_chat_audit import (
    audit_for_chat, capabilities_reply, is_audit_request,
    is_capabilities_question, repository_for_project,
)
from app.services.orchestrator import orchestrate

REPO = "soufekladislav/Karel"
SHA = "a" * 40


def snapshot(repo=REPO):
    return {
        "repository": repo,
        "description": "Projektový manažer pro vývoj a WordPress",
        "default_branch": "main",
        "source_commit_sha": SHA,
        "fetched_at": "2026-11-20T13:30:00Z",
        "documentation_status": "complete_selection",
        "documentation_excerpts": [{
            "path": "README.md", "sha": "b" * 40,
            "url": "https://github.com/" + repo + "/blob/" + SHA + "/README.md",
            "excerpt": "Karel má řídit vývoj přes Fresh AI Engine.",
            "excerpt_truncated": False,
        }],
        "counts": {
            "issues_loaded": 2, "open_issues": 1, "prs_loaded": 1,
            "open_prs": 0, "workflow_runs": 3,
        },
        "issues": [{"number": 9, "state": "open", "title": "GitHub zápisy",
                    "url": "https://github.com/" + repo + "/issues/9"},
                   {"number": 8, "state": "closed", "title": "Hotovo"}],
        "pull_requests": [{"number": 2, "state": "closed", "title": "Merged"}],
        "projects_v2_status": "requires_token",
        "source_tree": ["README.md", "app/main.py", "storage/old.sqlite"],
        "partial": {"issues": False, "prs": False, "tree": False},
    }


class Reader:
    calls = []
    raise_error = None
    def __init__(self, token=""):
        self.token = token
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return None
    def snapshot(self, repo, owner):
        self.calls.append((repo, owner, self.token))
        if self.raise_error:
            from app.services.github_connector import GitHubSyncError
            raise GitHubSyncError(self.raise_error)
        return snapshot(repo)


class GitHubAuditChatTests(unittest.TestCase):
    def setUp(self):
        Reader.calls = []
        Reader.raise_error = None
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.user = User(email="owner@example.cz", password_hash="hash", role="user")
        self.db.add(self.user)
        self.db.flush()
        self.project = Project(owner_id=self.user.id, name="Developer Karel")
        self.db.add(self.project)
        self.db.flush()
        self.chat = Chat(project_id=self.project.id, title="Hlavní chat")
        self.db.add(self.chat)
        self.db.commit()
        self.settings_patch = patch.object(settings, "superadmin_email", "owner@example.cz")
        self.settings_patch.start()

    def tearDown(self):
        self.settings_patch.stop()
        self.db.close()
        self.engine.dispose()

    def test_old_conversation_commands_actually_trigger_audit(self):
        self.assertTrue(is_audit_request(
            "Potřebuji projít GitHub a zkontrolovat celý projekt včetně repozitáře."))
        self.assertTrue(is_audit_request(
            "Karle, projdi aplikaci svou app Karel na GitHubu a vysvětli mi, co umí."))
        self.assertFalse(is_audit_request("Ahoj, co už umíš?"))

    def test_self_project_is_resolved_without_asking_url(self):
        repo, source = repository_for_project(self.db, self.project, self.user)
        self.assertEqual((repo, source), (REPO, "self_project"))
        with patch.object(settings, "github_read_token", ""), \
             patch.object(settings, "github_allowed_owners", ""):
            result, mode = audit_for_chat(self.db, self.project, self.user,
                                          reader_factory=Reader)
        self.assertEqual(mode, "live")
        self.assertEqual(Reader.calls, [(REPO, "soufekladislav", "")])
        self.assertIn("Karel má řídit vývoj", result)
        self.assertIn("GitHub zápisy", result)
        self.assertIn("storage/old.sqlite", result)
        self.assertNotIn("Pošli prosím URL", result)
        link = self.db.scalar(select(GitHubRepoLink).where(
            GitHubRepoLink.project_id == self.project.id))
        self.assertEqual(link.repository_full_name, REPO)
        self.assertIsNotNone(link.last_synced_at)

    def test_already_linked_project_is_loaded_without_manual_url(self):
        self.project.name = "Libovolný projekt"
        link = GitHubRepoLink(project_id=self.project.id,
                              repository_full_name="soufekladislav/Linda")
        self.db.add(link)
        self.db.commit()
        with patch.object(settings, "github_read_token", ""), \
             patch.object(settings, "github_allowed_owners", ""):
            out, mode = audit_for_chat(self.db, self.project, self.user,
                                       reader_factory=Reader)
        self.assertEqual(mode, "live")
        self.assertIn("soufekladislav/Linda", out)
        self.assertEqual(Reader.calls[0][0], "soufekladislav/Linda")

    def test_second_call_reuses_fresh_snapshot(self):
        with patch.object(settings, "github_read_token", ""), \
             patch.object(settings, "github_allowed_owners", ""):
            audit_for_chat(self.db, self.project, self.user, reader_factory=Reader)
            reply, mode = audit_for_chat(self.db, self.project, self.user,
                                         reader_factory=Reader)
        self.assertEqual(mode, "cached")
        self.assertEqual(len(Reader.calls), 1)
        self.assertIn("ověřený uložený snímek", reply)

    def test_live_failure_does_not_present_cache_as_current(self):
        with patch.object(settings, "github_read_token", ""), \
             patch.object(settings, "github_allowed_owners", ""):
            audit_for_chat(self.db, self.project, self.user, reader_factory=Reader)
            row = self.db.scalar(select(GitHubRepoLink))
            from datetime import datetime, timedelta
            row.last_synced_at = datetime.utcnow() - timedelta(minutes=15)
            self.db.commit()
            Reader.raise_error = "GitHub 429"
            reply, mode = audit_for_chat(self.db, self.project, self.user,
                                         reader_factory=Reader)
        self.assertEqual(mode, "stale")
        self.assertIn("starší snímek", reply)
        self.assertIn("GitHub 429", reply)

    def test_role_superadmin_bootstraps_even_with_different_configured_email(self):
        self.user.role = "superadmin"
        self.db.commit()
        with patch.object(settings, "superadmin_email", "different-admin@example.cz"):
            repo, source = repository_for_project(self.db, self.project, self.user)
        self.assertEqual(repo, REPO)
        self.assertEqual(source, "self_project")

    def test_non_admin_cannot_bootstrap_other_project_from_name(self):
        with patch.object(settings, "superadmin_email", "realadmin@example.cz"):
            repo, state = repository_for_project(self.db, self.project, self.user)
            self.assertIsNone(repo)
            self.assertEqual(state, "unlinked")
            message, state = audit_for_chat(self.db, self.project, self.user,
                                            reader_factory=Reader)
            self.assertEqual(state, "unlinked")
            self.assertFalse(Reader.calls)
            self.assertIn("nemá potvrzenou vazbu", message)

    def test_orchestrator_returns_tool_report_instead_of_asking_for_link(self):
        with patch("app.services.orchestrator.audit_for_chat",
                   return_value=("OVĚŘENÝ GITHUB AUDIT", "live")) as audit:
            out = orchestrate(self.db, self.project, self.chat, self.user,
                              "Karle, projdi svou app Karel na GitHubu", 1)
        audit.assert_called_once()
        self.assertEqual(out.mode, "ai")
        self.assertIn("OVĚŘENÝ GITHUB", "\n".join(out.context_blocks))
        self.assertIn("github_audit_live", out.tools_used)

    def test_self_capabilities_are_truthful_not_future_promises(self):
        self.assertTrue(is_capabilities_question("Ahoj, co už umíš?"))
        response = capabilities_reply()
        self.assertIn("zatím neumím", response)
        self.assertIn("Codexu", response)
        with patch("app.services.orchestrator.audit_for_chat") as no_audit:
            out = orchestrate(self.db, self.project, self.chat, self.user,
                              "Ahoj, co už umíš?")
        self.assertIn("zatím neumím", out.direct_response)
        no_audit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
