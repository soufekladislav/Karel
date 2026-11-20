"""GitHub code reader must actually fetch source, resume and compare branches."""
import base64, json, unittest
from unittest.mock import patch
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.config import settings
from app.models import Project, User, GitHubRepoLink, ProjectMemory
from app.services.github_snapshot_store import upsert_snapshot
from app.services.github_deep_audit import (
    scan_code, review_branches, is_branches_request, is_code_request, PROGRESS_KIND,
)

REPO = "soufekladislav/Karel"
SHA = "a" * 40

class FakeReader:
    calls = []
    def __init__(self, token=""):
        self.token = token
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def _request(self, method, endpoint, *, params=None, optional=False, **kwargs):
        self.calls.append((method, endpoint, params))
        if endpoint == "/repos/" + REPO:
            return {"default_branch": "main"}
        if "/compare/" in endpoint:
            return {"status": "behind", "ahead_by": 0, "behind_by": 4, "files": []}
        filename = endpoint.rsplit("/", 1)[-1]
        if filename in ("main.py", "helpers.py"):
            data = ("def run():\n    return 'ready'\n" if filename == "main.py" else
                    "def helper():\n    return 2\n").encode()
            return {"type": "file", "size": len(data), "encoding": "base64",
                    "content": base64.b64encode(data).decode()}
        return None
    def pages(self, endpoint, *, limit=100, **kwargs):
        return [{"name":"main"},{"name":"develop/karel-platform"}]

class GitHubDeepTests(unittest.TestCase):
    def setUp(self):
        FakeReader.calls = []
        self.engine=create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db=sessionmaker(bind=self.engine)()
        self.user=User(email="owner@example.cz",password_hash="x",role="superadmin")
        self.db.add(self.user); self.db.flush()
        self.project=Project(owner_id=self.user.id,name="Developer Karel")
        self.db.add(self.project); self.db.flush()
        snap={"repository":REPO,"source_commit_sha":SHA,
              "default_branch":"main",
              "source_tree":["app/main.py","app/helpers.py","storage/secrets.py"],
              "partial":{"tree":False}}
        upsert_snapshot(self.db,self.project.id,self.user.id,snap)

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def test_requests_are_understood(self):
        self.assertTrue(is_branches_request(
            "Projdi repozitáře a podívej se co tam máme za nesloučené větve."))
        self.assertTrue(is_code_request(
            "Karle, projdi celý GitHub a přečti zdrojový kód aplikace."))
        self.assertFalse(is_code_request("Ahoj!"))

    def test_real_file_reads_and_complete_resume_status(self):
        with patch.object(settings,"github_allowed_owners",""), \
             patch.object(settings,"github_read_token",""):
            reply, status=scan_code(self.db,self.project,self.user,
                                    reader_factory=FakeReader)
        self.assertEqual(status,"complete_index")
        self.assertIn("def run()",reply)
        self.assertIn("def helper()",reply)
        self.assertNotIn("storage/secrets.py",reply)
        progress=self.db.scalar(select(ProjectMemory).where(
            ProjectMemory.project_id==self.project.id,
            ProjectMemory.kind==PROGRESS_KIND))
        self.assertEqual(json.loads(progress.content)["index"],2)
        self.assertEqual(len(FakeReader.calls),2)
        reply,status=scan_code(self.db,self.project,self.user,
                               reader_factory=FakeReader)
        self.assertEqual(status,"indexed_end")

    def test_branch_compare_is_real_not_cached_markdown(self):
        with patch.object(settings,"github_allowed_owners",""), \
             patch.object(settings,"github_read_token",""):
            report,status=review_branches(self.db,self.project,self.user,
                                          reader_factory=FakeReader)
        self.assertEqual(status,"live_branch_comparison")
        self.assertIn("develop/karel-platform",report)
        self.assertIn("ahead 0",report)
        self.assertTrue(any("/compare/" in c[1] for c in FakeReader.calls))

if __name__ == "__main__":
    unittest.main()
