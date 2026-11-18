"""Tests for first-stage GitHub portfolio mapping and idempotent import."""
import unittest

import httpx
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Chat, GitHubRepoLink, Project, User
from app.services.github_connector import GitHubReader, GitHubSyncError
from app.services.github_bulk_import import (
    discover_repositories, prepare_import_plan, apply_import_plan,
)


class BulkDiscoveryTests(unittest.TestCase):
    def test_token_repository_discovery_filters_owners(self):
        def responder(request):
            if request.url.path == '/user/repos':
                if request.url.params.get('page') != '1':
                    return httpx.Response(200, json=[])
                return httpx.Response(200, json=[
                    {'full_name': 'soufekladislav/Karel', 'name': 'Karel', 'id': 1},
                    {'full_name': 'someoneelse/private', 'name': 'private', 'id': 2},
                    {'full_name': 'soufekladislav/Boban', 'name': 'Boban', 'id': 3},
                ])
            return httpx.Response(404)
        client = httpx.Client(transport=httpx.MockTransport(responder))
        reader = GitHubReader(token='dummy', client=client)
        data, partial = discover_repositories(reader, 'soufekladislav')
        self.assertEqual([i['full_name'] for i in data], [
            'soufekladislav/Boban', 'soufekladislav/Karel'])
        self.assertFalse(partial)
        client.close()

    def test_allowlist_required(self):
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404))) as client:
            reader = GitHubReader(client=client)
            with self.assertRaises(GitHubSyncError):
                discover_repositories(reader, '')


class BulkImportDbTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite+pysqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        user = User(email='admin@example.com', password_hash='test', role='superadmin')
        self.db.add(user)
        self.db.flush()
        self.user_id = user.id
        original = Project(owner_id=user.id, name='Karel', description='Původní zadání se musí zachovat.')
        self.db.add(original)
        self.db.commit()
        self.original_id = original.id

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def repos(self):
        return [
            {'full_name': 'soufekladislav/Karel', 'name': 'Karel', 'description': 'Karel'},
            {'full_name': 'soufekladislav/Boban', 'name': 'Boban', 'description': 'SEO'},
            {'full_name': 'soufekladislav/Boban', 'name': 'Boban', 'description': 'Duplicate'},
        ]

    def test_preview_links_exact_name_and_prevents_duplicates(self):
        plan = prepare_import_plan(self.db, self.user_id, self.repos())
        self.assertEqual(len(plan), 2)
        self.assertEqual([p['action'] for p in plan], ['attach', 'create'])
        self.assertEqual(plan[0]['local_project_id'], self.original_id)
        result = apply_import_plan(self.db, self.user_id, plan,
                                   ['soufekladislav/Karel', 'soufekladislav/Boban'])
        self.assertEqual(result['created'], 1)
        self.assertEqual(result['attached'], 1)
        self.assertEqual(self.db.scalar(select(func.count(Project.id))), 2)
        self.assertEqual(self.db.scalar(select(func.count(GitHubRepoLink.id))), 2)
        self.assertEqual(self.db.get(Project, self.original_id).description,
                         'Původní zadání se musí zachovat.')
        self.assertEqual(self.db.scalar(select(func.count(Chat.id))), 1)

        plan2 = prepare_import_plan(self.db, self.user_id, self.repos())
        self.assertEqual([p['action'] for p in plan2], ['linked', 'linked'])
        result2 = apply_import_plan(self.db, self.user_id, plan2,
                                    ['soufekladislav/Karel', 'soufekladislav/Boban'])
        self.assertEqual(result2['created'], 0)
        self.assertEqual(result2['attached'], 0)
        self.assertEqual(self.db.scalar(select(func.count(Project.id))), 2)

    def test_unknown_repository_is_rejected_before_writes(self):
        plan = prepare_import_plan(self.db, self.user_id, self.repos())
        with self.assertRaises(ValueError):
            apply_import_plan(self.db, self.user_id, plan, ['stranger/secret'])
        self.assertEqual(self.db.scalar(select(func.count(GitHubRepoLink.id))), 0)


if __name__ == '__main__':
    unittest.main()
