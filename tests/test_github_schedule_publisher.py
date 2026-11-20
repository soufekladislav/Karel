"""Approved Pipeline publication: never claim GitHub success without read-back."""
import base64
import hashlib
import json
import unittest
from unittest.mock import patch

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base
from app.models import Project, ProjectMemory, User
from app.services.github_schedule_publisher import (
    PATH, REPO, SCHEMA, ScheduleSyncError,
    latest_sync_status, publish_approved_schedule, sync_after_approved_action,
)
from app.services.project_timeline import (
    BUNDLED_KAREL_SCHEDULE, parse_checked_in_schedule,
)


class MockGitHub:
    def __init__(self):
        self.remote = None
        self.puts = 0
        self.commit = "b" * 40
        self.reject = False

    def handle(self, request):
        suffix = "/repos/" + REPO + "/contents/" + PATH
        if request.method == "GET" and request.url.path == "/repos/" + REPO:
            return httpx.Response(200, json={
                "full_name": REPO, "default_branch": "main"})
        if request.url.path == suffix:
            if request.method == "PUT":
                self.puts += 1
                if self.reject:
                    return httpx.Response(403, json={"message": "no permission"})
                payload = json.loads(request.content)
                assert payload["branch"] == "main"
                if self.remote:
                    assert payload["sha"] == self.remote["sha"]
                raw = base64.b64decode(payload["content"])
                sha = hashlib.sha1(
                    b"blob " + str(len(raw)).encode() + b"\x00" + raw
                ).hexdigest()
                self.remote = {
                    "type": "file", "sha": sha,
                    "content": payload["content"], "encoding": "base64",
                }
                return httpx.Response(200, json={"commit": {"sha": self.commit}})
            if request.method == "GET":
                if self.remote:
                    return httpx.Response(200, json=self.remote)
                return httpx.Response(404, json={"message": "not found"})
        return httpx.Response(404, json={"message": "unexpected route"})


class GitHubSchedulePublishingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.user = User(email="boss@freshcrackers.cz", role="superadmin",
                         password_hash="x")
        self.db.add(self.user); self.db.flush()
        self.project = Project(name="Karel", owner_id=self.user.id)
        self.db.add(self.project); self.db.flush()
        self.milestones = parse_checked_in_schedule(BUNDLED_KAREL_SCHEDULE)
        self.db.add(ProjectMemory(
            project_id=self.project.id, kind="project_schedule",
            title="Schválený harmonogram v1", verified=True,
            content=json.dumps({
                "version":1, "source":"user_chat_replan",
                "milestones":self.milestones,
                "approved_at":"2026-11-21T08:00:00",
                "approved_by_user_id":self.user.id,
            }),
        ))
        self.db.commit()
        self.mocks = [
            patch.object(settings,"github_allowed_owners","soufekladislav"),
            patch.object(settings,"github_schedule_write_enabled",True),
            patch.object(settings,"github_schedule_write_token","secret-with-write"),
        ]
        for m in self.mocks: m.start()

    def tearDown(self):
        for m in reversed(self.mocks): m.stop()
        self.db.close(); self.engine.dispose()

    def test_real_publication_content_created_and_verified(self):
        gh = MockGitHub()
        client = httpx.Client(transport=httpx.MockTransport(gh.handle))
        result = publish_approved_schedule(
            self.db,self.project,self.user,client=client)
        self.assertEqual(result["state"],"synced")
        self.assertEqual(result["commit_sha"],"b"*40)
        self.assertEqual(gh.puts,1)
        published = json.loads(base64.b64decode(gh.remote["content"]))
        self.assertEqual(published["schema"],SCHEMA)
        self.assertEqual(published["milestones"][4]["due_date"],"2027-01-15")
        self.assertEqual(published["version"],1)
        self.assertNotIn("secret-with-write", gh.remote["content"])
        self.assertEqual(publish_approved_schedule(
            self.db,self.project,self.user,client=client)["state"],"synced")
        self.assertEqual(gh.puts,1)
        client.close()

    def test_write_permission_rejection_is_not_reported_as_success(self):
        gh = MockGitHub()
        gh.reject = True
        with httpx.Client(transport=httpx.MockTransport(gh.handle)) as client:
            with self.assertRaisesRegex(ScheduleSyncError,"403"):
                publish_approved_schedule(
                    self.db,self.project,self.user,client=client)

    def test_same_version_conflict_fails_closed(self):
        gh = MockGitHub()
        other = {
            "schema": SCHEMA, "project_id": self.project.id,
            "repository": REPO, "version":1, "milestones":[],
        }
        raw = json.dumps(other).encode()
        gh.remote = {
            "type":"file",
            "sha":hashlib.sha1(
                b"blob "+str(len(raw)).encode()+b"\x00"+raw).hexdigest(),
            "content":base64.b64encode(raw).decode(), "encoding":"base64",
        }
        with httpx.Client(transport=httpx.MockTransport(gh.handle)) as client:
            with self.assertRaisesRegex(ScheduleSyncError,"jiný obsah"):
                publish_approved_schedule(
                    self.db,self.project,self.user,client=client)
        self.assertEqual(gh.puts,0)

    def test_missing_write_token_keeps_pipeline_and_records_blocker(self):
        with patch.object(settings,"github_schedule_write_token",""):
            result=sync_after_approved_action(
                self.db,self.project,self.user,
                [{"type":"approve_project_schedule"}])
        self.assertEqual(result["state"],"blocked")
        self.assertEqual(result["version"],1)
        self.assertIn("GITHUB_SCHEDULE_WRITE_TOKEN",result["reason"])
        self.assertEqual(latest_sync_status(self.db,self.project.id)["state"],"blocked")
        self.assertIsNotNone(self.db.scalar(select(ProjectMemory).where(
            ProjectMemory.kind=="project_schedule")))

    def test_unapproved_project_never_publishes(self):
        self.db.query(ProjectMemory).filter(
            ProjectMemory.kind == "project_schedule").delete()
        self.db.commit()
        gh=MockGitHub()
        with httpx.Client(transport=httpx.MockTransport(gh.handle)) as client:
            with self.assertRaisesRegex(ScheduleSyncError,"schválená"):
                publish_approved_schedule(
                    self.db,self.project,self.user,client=client)
        self.assertEqual(gh.puts,0)

    def test_no_schedule_action_means_no_external_write(self):
        self.assertIsNone(sync_after_approved_action(
            self.db,self.project,self.user,[{"type":"create_task"}]))
        self.assertEqual(latest_sync_status(self.db,self.project.id)["state"],
                         "not_attempted")


if __name__ == "__main__":
    unittest.main()
