"""CRUD regressions: project cleanup, file archive, GitHub public-read scope."""
import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import create_engine, select, event, func
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from app import main
from app.config import settings
from app.database import Base
from app.models import (
    User, Project, ProjectStage, ProjectMemory, GitHubRepoLink, Chat,
    Message, Task, ProjectFile, ProjectEvent, LibraryItem,
)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine("sqlite+pysqlite:///:memory:")
        @event.listens_for(self.engine,"connect")
        def enable_fk(conn, _):
            conn.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        self.db=sessionmaker(bind=self.engine)()
        self.owner=User(email="owner@sample.cz",password_hash="x",role="user")
        self.other=User(email="other@sample.cz",password_hash="x",role="user")
        self.db.add_all([self.owner,self.other]);self.db.flush()
        self.project=Project(owner_id=self.owner.id,name="Karel",status="active")
        self.db.add(self.project);self.db.flush()
        chat=Chat(project_id=self.project.id,title="Zadání")
        self.db.add(chat);self.db.flush()
        self.db.add_all([
            Message(chat_id=chat.id,user_id=self.owner.id,role="user",content="Hello"),
            Task(project_id=self.project.id,chat_id=chat.id,title="Issue",status="todo"),
            ProjectMemory(project_id=self.project.id,kind="purpose",title="Cíl",content="Pomáhat"),
            GitHubRepoLink(project_id=self.project.id,repository_full_name="example/Karel"),
            ProjectStage(project_id=self.project.id,stage_no=1,title="Zadání"),
            ProjectEvent(project_id=self.project.id,user_id=self.owner.id,
                         event_type="project_created",detail="Test"),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close();self.engine.dispose()

    def test_project_delete_needs_archive_and_matching_title(self):
        with patch("app.main.require_user",return_value=self.owner):
            before=main.delete_project(SimpleNamespace(),self.project.id,confirmation_name="Karel",db=self.db)
            self.assertIn("projects/",before.headers["location"])
            main.archive_project(SimpleNamespace(),self.project.id,archived=1,db=self.db)
            denied=main.delete_project(SimpleNamespace(),self.project.id,confirmation_name="wrong",db=self.db)
            self.assertIn("error=",denied.headers["location"])
            self.assertIsNotNone(self.db.get(Project,self.project.id))
            success=main.delete_project(SimpleNamespace(),self.project.id,confirmation_name="Karel",db=self.db)
        self.assertEqual(success.status_code,303)
        for cls in (Project,ProjectStage,GitHubRepoLink,Task,ProjectMemory,
                    ProjectEvent,Chat,Message,ProjectFile):
            self.assertEqual(self.db.scalar(select(func.count()).select_from(cls)),0,
                             msg=cls.__tablename__)

    def test_foreign_user_cannot_archive_or_delete(self):
        with patch("app.main.require_user",return_value=self.other):
            with self.assertRaises(HTTPException):
                main.archive_project(SimpleNamespace(),self.project.id,archived=1,db=self.db)
            with self.assertRaises(HTTPException):
                main.delete_project(SimpleNamespace(),self.project.id,confirmation_name="Karel",db=self.db)

    def test_archive_project_file_then_delete_preserves_project(self):
        pf=ProjectFile(project_id=self.project.id,name="Doklad.txt",
            stored_name=f"{self.project.id}/not-a-real-upload.txt",status="current")
        self.db.add(pf);self.db.commit()
        with patch("app.main.require_user",return_value=self.owner):
            with self.assertRaises(HTTPException) as denied:
                main.delete_archived_project_file(SimpleNamespace(),pf.id,db=self.db)
            self.assertEqual(denied.exception.status_code,409)
            main.archive_project_file(SimpleNamespace(),pf.id,archived=1,db=self.db)
            self.assertEqual(self.db.get(ProjectFile,pf.id).status,"archived")
            main.archive_project_file(SimpleNamespace(),pf.id,archived=0,db=self.db)
            self.assertEqual(self.db.get(ProjectFile,pf.id).status,"current")
            main.archive_project_file(SimpleNamespace(),pf.id,archived=1,db=self.db)
            main.delete_archived_project_file(SimpleNamespace(),pf.id,db=self.db)
        self.assertIsNone(self.db.get(ProjectFile,pf.id))
        self.assertIsNotNone(self.db.get(Project,self.project.id))


class GitHubPublicReadTests(LifecycleTests):
    def public_snapshot(self,repo,private=False):
        return {
            "schema":"karel.github.snapshot.v1", "repository":repo,
            "fetched_at":datetime.now(timezone.utc).isoformat(),
            "private":private,"counts":{"issues_loaded":1,"open_issues":1,"prs_loaded":0},
            "issues":[{"number":1,"title":"Test"}],"pull_requests":[],
        }

    def test_ordinary_owner_fetches_public_repo_without_admin_private_token(self):
        calls=[]
        testcase=self
        class FakeReader:
            def __init__(self,token):
                calls.append(token)
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def snapshot(self,repo,allowed):
                testcase.assertEqual(repo,"otherowner/test-repo")
                testcase.assertEqual(allowed,"otherowner")
                return testcase.public_snapshot(repo)
        with patch("app.main.require_user",return_value=self.owner),\
             patch("app.main.GitHubReader",FakeReader),\
             patch.object(settings,"github_read_token","PRIVATE-ADMIN-SECRET"),\
             patch.object(settings,"github_allowed_owners","soufekladislav"):
            response=main.github_project_sync(
                SimpleNamespace(),self.project.id,repository="otherowner/test-repo",db=self.db)
        self.assertEqual(response.status_code,303)
        self.assertEqual(calls,[""])
        link=self.db.scalar(select(GitHubRepoLink).where(
            GitHubRepoLink.project_id==self.project.id))
        self.assertEqual(link.repository_full_name,"otherowner/test-repo")
        self.assertNotIn("PRIVATE-ADMIN-SECRET",link.snapshot_json)

    def test_private_repo_rejected_for_ordinary_user_even_with_shared_token(self):
        calls=[]
        testcase=self
        class FakeReader:
            def __init__(self,token):calls.append(token)
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def snapshot(self,repo,allowed):return testcase.public_snapshot(repo,private=True)
        with patch("app.main.require_user",return_value=self.owner),\
             patch("app.main.GitHubReader",FakeReader),\
             patch.object(settings,"github_read_token","PRIVATE-TOKEN"):
            response=main.github_project_sync(
                SimpleNamespace(),self.project.id,repository="public/private",db=self.db)
        self.assertIn("error=",response.headers["location"])
        self.assertEqual(calls,[""])
        link=self.db.scalar(select(GitHubRepoLink).where(
            GitHubRepoLink.project_id==self.project.id))
        self.assertEqual(link.repository_full_name,"example/Karel")

    def test_disconnect_only_affects_local_link(self):
        with patch("app.main.require_user",return_value=self.owner):
            with self.assertRaises(HTTPException):
                main.github_project_disconnect(SimpleNamespace(),self.project.id,confirmed="",db=self.db)
            resp=main.github_project_disconnect(
                SimpleNamespace(),self.project.id,confirmed="disconnect",db=self.db)
        self.assertEqual(resp.status_code,303)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(GitHubRepoLink)),0)

    def test_foreign_user_cannot_refresh_or_disconnect_github(self):
        with patch("app.main.require_user",return_value=self.other):
            with self.assertRaises(HTTPException):
                main.github_project_sync(SimpleNamespace(),self.project.id,
                                         repository="public/repo",db=self.db)
            with self.assertRaises(HTTPException):
                main.github_project_disconnect(SimpleNamespace(),self.project.id,
                                               confirmed="disconnect",db=self.db)


if __name__=="__main__":
    unittest.main()
