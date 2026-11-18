import unittest
import httpx

from app.services.github_connector import GitHubReader, GitHubSyncError, validate_repository, prompt_summary


def make_handler(*, private=False, projects_error=False):
    def handler(request):
        path = request.url.path
        if path == "/graphql":
            if projects_error:
                return httpx.Response(403, json={"message": "Resource not accessible"})
            return httpx.Response(200, json={"data": {"repository": {"projectsV2": {"nodes": [
                {"id": "P_1", "number": 11, "title": "Roadmap", "url": "https://github.com/users/demo/projects/11",
                 "items": {"pageInfo": {"hasNextPage": False}, "nodes": [
                     {"id": "PVTI_1", "content": {"number": 7, "title": "Improve sync", "repository": {"nameWithOwner": "demo/Karel"}},
                      "fieldValues": {"nodes": [{"name": "In progress", "field": {"name": "Status"}}]}}
                 ]}}
            ]}}}})
        if path == "/repos/demo/Karel":
            return httpx.Response(200, json={"id": 10, "full_name": "demo/Karel", "html_url": "https://github.com/demo/Karel",
                "private": private, "default_branch": "main"})
        if path.endswith("/issues"):
            return httpx.Response(200, json=[
                {"id": 10, "number": 7, "node_id": "I_7", "title": "Improve sync", "state": "open",
                 "html_url": "https://github.com/demo/Karel/issues/7", "labels": [], "assignees": []},
                {"id": 11, "number": 8, "pull_request": {"url": "https://api.github.com/a"}, "state": "open"}])
        if path.endswith("/pulls"):
            return httpx.Response(200, json=[{"id": 11, "number": 8, "title": "PR", "state": "open",
                                                "html_url": "https://github.com/demo/Karel/pull/8"}])
        if path.endswith("/commits"):
            return httpx.Response(200, json=[])
        if "/git/trees/" in path:
            return httpx.Response(200, json={"tree": [{"path": "README.md", "type": "blob"}]})
        if path.endswith("/actions/runs"):
            return httpx.Response(403, json={"message": "Actions inaccessible"})
        return httpx.Response(404)
    return handler


class GitHubReadTests(unittest.TestCase):
    def test_validation_and_owner_allowlist(self):
        self.assertEqual(validate_repository("demo/Karel", "demo"), "demo/Karel")
        for invalid in ["https://github.com/demo/Karel", "../../secret", "other/Karel", "demo/repo/other", "demo/repo?foo"]:
            with self.assertRaises(GitHubSyncError):
                validate_repository(invalid, "demo")

    def test_public_snapshot_no_token_graceful_permissions(self):
        client = httpx.Client(transport=httpx.MockTransport(make_handler()))
        with GitHubReader(client=client) as api:
            snap = api.snapshot("demo/Karel", "demo")
        self.assertEqual(snap["counts"]["issues_loaded"], 1)
        self.assertEqual(snap["counts"]["prs_loaded"], 1)
        self.assertEqual(snap["projects_v2_status"], "requires_token")
        self.assertEqual(snap["actions_status"], "unavailable")
        self.assertTrue(any("README.md" in v for v in snap["documentation_paths"]))
        self.assertIn("Issue #7", prompt_summary(snap))

    def test_projects_read_only_with_graphql_and_status(self):
        calls = []
        def handler(req):
            calls.append(req.method)
            return make_handler()(req)
        client = httpx.Client(transport=httpx.MockTransport(handler))
        with GitHubReader(token="test-token", client=client) as api:
            snap = api.snapshot("demo/Karel", "demo")
        self.assertEqual(snap["projects_v2_status"], "ok")
        self.assertEqual(snap["projects_v2"][0]["items"][0]["fields"]["Status"], "In progress")
        self.assertNotIn("PATCH", calls)
        self.assertNotIn("PUT", calls)
        self.assertNotIn("DELETE", calls)

    def test_project_api_access_denied_does_not_fake_board(self):
        client = httpx.Client(transport=httpx.MockTransport(make_handler(projects_error=True)))
        with GitHubReader(token="test-token", client=client) as api:
            snap = api.snapshot("demo/Karel", "demo")
        self.assertEqual(snap["projects_v2_status"], "unavailable")
        self.assertEqual(snap["projects_v2"], [])

    def test_upsert_snapshot_twice_keeps_one_link_and_no_local_tasks(self):
        from sqlalchemy import create_engine, select, func
        from sqlalchemy.orm import Session
        from app.database import Base
        from app.models import Project, GitHubRepoLink, Task, ProjectEvent
        from app.services.github_snapshot_store import upsert_snapshot

        dbengine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(dbengine)
        with Session(dbengine) as db:
            db.add(Project(id=1, owner_id=1, name="Test project"))
            db.commit()
            for n in (1, 2):
                upsert_snapshot(db, project_id=1, user_id=1, snapshot={
                    "repository": "demo/Karel", "fetched_at": "2026-11-18T12:00:00Z",
                    "counts": {"issues_loaded": n}})
            self.assertEqual(db.scalar(select(func.count(GitHubRepoLink.id))), 1)
            self.assertEqual(db.scalar(select(func.count(Task.id))), 0)
            self.assertEqual(db.scalar(select(func.count(ProjectEvent.id))), 2)
            link = db.scalar(select(GitHubRepoLink))
            import json
            self.assertEqual(json.loads(link.snapshot_json)["counts"]["issues_loaded"], 2)



if __name__ == "__main__":
    unittest.main()
