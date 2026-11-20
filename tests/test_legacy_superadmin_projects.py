"""P0 legacy project permissions and safe type conversion.

is_superadmin must be identical throughout UI, dashboard and access control:
the configured superadmin_email is authoritative even for a legacy role value.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import main
from app.config import settings
from app.database import Base
from app.models import Project, User, ProjectMemory, Chat, GitHubRepoLink, Task
from app.services.project_journeys import project_mode


class LegacyProjectAccessTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite+pysqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db=sessionmaker(bind=self.engine)()
        self.privileged=User(email='superadmin@local.test',password_hash='x',role='user')
        self.owner=User(email='legacy@local.test',password_hash='x',role='user')
        self.other=User(email='other@local.test',password_hash='x',role='user')
        self.db.add_all([self.privileged,self.owner,self.other]);self.db.flush()
        self.project=Project(owner_id=self.owner.id,name='Web Fresh Develop',status='active')
        self.db.add(self.project);self.db.flush()
        self.chat=Chat(project_id=self.project.id,title='Původní historie')
        self.db.add(self.chat);self.db.flush()
        self.db.add_all([
            Task(project_id=self.project.id,chat_id=self.chat.id,title='Zachovat práci'),
            GitHubRepoLink(project_id=self.project.id,repository_full_name='soufekladislav/Karel'),
        ])
        self.db.commit()
        self.patch=patch.object(settings,'superadmin_email','superadmin@local.test')
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.db.close()
        self.engine.dispose()

    def test_email_superadmin_can_edit_old_project_even_with_legacy_role(self):
        self.assertTrue(main.is_superadmin(self.privileged))
        self.assertTrue(main.can_access(self.db,self.privileged,self.project))
        self.assertTrue(main.can_manage_project(self.db,self.privileged,self.project))
        self.assertIs(main.get_project_or_404(
            self.db,self.privileged,self.project.id,manage=True),self.project)
        with patch('app.main.require_user',return_value=self.privileged):
            resp=main.edit_project(SimpleNamespace(),self.project.id,
                                   name='Fresh Develop – web',description='Opraveno',db=self.db)
        self.assertIn('view=manage&notice',resp.headers['location'])
        self.assertEqual(self.db.get(Project,self.project.id).name,'Fresh Develop – web')
        self.assertIsNotNone(self.db.get(Chat,self.chat.id))
        self.assertEqual(self.db.scalars(select(Task)).one().title,'Zachovat práci')

    def test_superadmin_can_change_legacy_project_to_wordpress_without_data_loss(self):
        with patch('app.main.require_user',return_value=self.privileged):
            resp=main.choose_existing_project_mode(
                SimpleNamespace(),self.project.id,project_mode_choice='wordpress',db=self.db)
        self.assertEqual(resp.status_code,303)
        row=self.db.scalar(select(ProjectMemory).where(
            ProjectMemory.project_id==self.project.id, ProjectMemory.kind=='project_type'))
        self.assertIn('WordPress',row.content)
        self.assertEqual(project_mode(row.content,github_linked=True),'wordpress')
        self.assertEqual(self.db.scalars(select(GitHubRepoLink)).one().repository_full_name,
                         'soufekladislav/Karel')
        self.assertIsNotNone(self.db.get(Chat,self.chat.id))

    def test_other_user_without_access_still_denied(self):
        self.assertFalse(main.is_superadmin(self.other))
        self.assertFalse(main.can_access(self.db,self.other,self.project))
        with self.assertRaises(HTTPException) as denied:
            main.get_project_or_404(self.db,self.other,self.project.id,write=True)
        self.assertEqual(denied.exception.status_code,404)

    def test_invalid_type_change_has_no_side_effect(self):
        with patch('app.main.require_user',return_value=self.privileged):
            with self.assertRaises(HTTPException):
                main.choose_existing_project_mode(
                    SimpleNamespace(),self.project.id,
                    project_mode_choice='invalid',db=self.db)
        self.assertFalse(self.db.scalars(select(ProjectMemory).where(
            ProjectMemory.kind=='project_type')).all())


if __name__=='__main__':
    unittest.main()
