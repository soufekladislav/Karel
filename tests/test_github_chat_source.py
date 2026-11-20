"""GitHub URLs in Karel chat should reuse the project-bound connector.

Do not fetch arbitrary HTML or bypass SOURCE_ALLOWED_HOSTS. Preserve
historical source state and avoid claiming a cached snapshot is live.
"""
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Project, ProjectEvent, GitHubRepoLink, User
from app.services.github_snapshot_codec import encode_snapshot
from app.services.source_resolver import resolve_message_sources


class GithubProjectUrlTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db=sessionmaker(bind=self.engine)()
        self.user=User(email='owner@domain.test',role='user',password_hash='test')
        self.db.add(self.user);self.db.flush()
        self.project=Project(owner_id=self.user.id,name='Boban')
        self.db.add(self.project);self.db.flush()
        self.snapshot={
            "schema":"karel.github.snapshot.v1",
            "repository":"soufekladislav/Boban",
            "fetched_at":"2026-11-19T19:22:36Z",
            "default_branch":"main",
            "counts":{"issues_loaded":1,"prs_loaded":0},
            "projects_v2_status":"requires_token",
            "issues":[{"number":12,"state":"open","title":"Opravit worker",
                       "url":"https://github.com/soufekladislav/Boban/issues/12",
                       "body_excerpt":"Worker se zastavil u 250 produktů."}],
            "pull_requests":[]
        }
        self.link=GitHubRepoLink(project_id=self.project.id,
            repository_full_name='soufekladislav/Boban',
            snapshot_json=encode_snapshot(self.snapshot))
        self.db.add(self.link);self.db.commit()

    def tearDown(self):
        self.db.close();self.engine.dispose()

    def resolve(self, url):
        with patch("app.services.source_resolver.load_brain",return_value={}),\
             patch("app.services.source_resolver._fetch_public_text",
                   side_effect=AssertionError("Must not fetch GitHub HTML")):
            return resolve_message_sources(
                self.db,self.project,self.user,'Prober '+url,'alpha')

    def test_linked_repo_uses_readonly_snapshot_and_no_source_error(self):
        data=self.resolve('https://github.com/soufekladislav/Boban')
        self.assertEqual(len(data),1)
        self.assertIn('ULOŽENÝ PROJEKTOVÝ SNAPSHOT',data[0])
        self.assertIn('Opravit worker',data[0])
        self.assertNotIn('LIVE / právě načteno',data[0])
        errors=self.db.scalars(select(ProjectEvent).where(
            ProjectEvent.event_type=='source_load_error')).all()
        self.assertFalse(errors)

    def test_linked_specific_issue_is_included(self):
        data=self.resolve('https://github.com/soufekladislav/Boban/issues/12')
        self.assertIn('Worker se zastavil u 250 produktů.',data[0])
        self.assertIn('PŘÍMO ODKAZOVANÝ ISSUE #12',data[0])

    def test_unlinked_repo_does_not_leak_other_project_or_attempt_fetch(self):
        data=self.resolve('https://github.com/anotherowner/another')
        self.assertIn('není přiřazen aktuálnímu projektu',data[0])
        self.assertNotIn('Opravit worker',data[0])

    def test_invalid_local_snapshot_requests_refresh_without_fake_live_data(self):
        self.link.snapshot_json='{"repo":'
        self.db.commit()
        data=self.resolve('https://github.com/soufekladislav/Boban')
        self.assertIn('SNÍMEK JE NEDOSTUPNÝ',data[0])


if __name__=="__main__":
    unittest.main()
