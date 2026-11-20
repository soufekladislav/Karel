"""Project management UX: discoverable and backed by existing guarded write routes."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import main
from app.database import Base
from app.models import Project, ProjectMemory, ProjectEvent, User, Chat, Task, GitHubRepoLink

ROOT=Path(__file__).resolve().parents[1]
TPL=ROOT/'app'/'templates'


class ManagementUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env=Environment(loader=FileSystemLoader(str(TPL)),
                            autoescape=select_autoescape(['html']))

    def render(self,status='active',can_edit=True,can_manage=True):
        project=SimpleNamespace(id=42,name='Můj web',description='Testovací projekt',status=status)
        return self.env.get_template('_project_manage.html').render(
            project=project,can_edit=can_edit,can_manage=can_manage)

    def test_active_owner_can_find_rename_archive_not_permanent_delete(self):
        html=self.render()
        self.assertIn('Název projektu',html)
        self.assertIn('name="name"',html)
        self.assertIn('name="description"',html)
        self.assertIn('action="/projects/42/edit"',html)
        self.assertIn('action="/projects/42/archive"',html)
        self.assertIn('Archivovat projekt',html)
        self.assertNotIn('action="/projects/42/delete"',html)

    def test_archived_owner_can_restore_or_delete_with_exact_name(self):
        html=self.render(status='archived')
        self.assertIn('Archivovaný projekt',html)
        self.assertIn('Obnovit projekt z archivu',html)
        self.assertIn('name="confirmation_name"',html)
        self.assertIn('action="/projects/42/delete"',html)
        self.assertIn('Můj web',html)

    def test_viewer_cannot_edit_or_archive(self):
        html=self.render(can_edit=False,can_manage=False)
        self.assertNotIn('action="/projects/42/edit"',html)
        self.assertNotIn('action="/projects/42/archive"',html)
        self.assertNotIn('action="/projects/42/delete"',html)

    def test_navigation_and_project_cards_have_management_entrypoints(self):
        sidebar=(TPL/'_sidebar.html').read_text(encoding='utf-8')
        mobile=(TPL/'_project_mobile_nav.html').read_text(encoding='utf-8')
        dashboard=(TPL/'dashboard.html').read_text(encoding='utf-8')
        project=(TPL/'project.html').read_text(encoding='utf-8')
        github=(TPL/'github.html').read_text(encoding='utf-8')
        source=(ROOT/'app'/'main.py').read_text(encoding='utf-8')
        self.assertIn('Správa projektu',sidebar)
        self.assertIn('?view=manage',mobile)
        self.assertIn('Spravovat projekt',dashboard)
        self.assertIn('id="archiv-projektu"',dashboard)
        self.assertIn('archived_management.get(p.id)',dashboard)
        self.assertIn("include '_project_manage.html'",project)
        self.assertIn('?view=manage',github)
        self.assertIn("'website','manage'",source)
        self.assertIn('view=manage&notice',source)


class ManagementDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite+pysqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db=sessionmaker(bind=self.engine)()
        self.user=User(email='owner@example.com',password_hash='x',role='user')
        self.db.add(self.user);self.db.flush()
        self.project=Project(owner_id=self.user.id,name='Původní název',description='Původní popis')
        self.db.add(self.project);self.db.flush()
        self.chat=Chat(project_id=self.project.id,title='Hlavní chat')
        self.db.add(self.chat);self.db.flush()
        self.db.add_all([
            Task(project_id=self.project.id,chat_id=self.chat.id,title='Úkol'),
            ProjectMemory(project_id=self.project.id,kind='business_goal',
                          title='Obchodní cíl',content='Nabírat zákazníky'),
            GitHubRepoLink(project_id=self.project.id,
                           repository_full_name='soufekladislav/Karel'),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close();self.engine.dispose()

    def test_rename_preserves_tasks_chats_and_github_link(self):
        with patch('app.main.require_user',return_value=self.user):
            response=main.edit_project(SimpleNamespace(),self.project.id,
                name='Přejmenovaný projekt',description='Nový popis',db=self.db)
        self.assertIn('view=manage&notice',response.headers['location'])
        self.assertEqual(self.db.get(Project,self.project.id).name,'Přejmenovaný projekt')
        self.assertEqual(self.db.get(Project,self.project.id).description,'Nový popis')
        self.assertEqual(self.db.scalars(select(Task)).one().title,'Úkol')
        self.assertEqual(self.db.scalars(select(Chat)).one().title,'Hlavní chat')
        self.assertEqual(self.db.scalars(select(GitHubRepoLink)).one().repository_full_name,'soufekladislav/Karel')
        self.assertEqual(self.db.scalars(select(ProjectMemory).where(
            ProjectMemory.kind=='business_goal')).one().content,'Nabírat zákazníky')

    def test_empty_name_rejected_without_data_loss(self):
        with patch('app.main.require_user',return_value=self.user):
            response=main.edit_project(SimpleNamespace(),self.project.id,name='   ',
                                       description='neukládat',db=self.db)
        self.assertIn('error=',response.headers['location'])
        self.assertEqual(self.db.get(Project,self.project.id).name,'Původní název')
        self.assertEqual(self.db.get(Project,self.project.id).description,'Původní popis')

    def test_archive_restore_keep_data_and_redirect_to_management(self):
        with patch('app.main.require_user',return_value=self.user):
            archived=main.archive_project(SimpleNamespace(),self.project.id,archived=1,db=self.db)
            self.assertIn('view=manage&notice',archived.headers['location'])
            self.assertEqual(self.db.get(Project,self.project.id).status,'archived')
            self.assertEqual(self.db.scalars(select(GitHubRepoLink)).one().repository_full_name,'soufekladislav/Karel')
            restored=main.archive_project(SimpleNamespace(),self.project.id,archived=0,db=self.db)
        self.assertIn('view=manage&notice',restored.headers['location'])
        self.assertEqual(self.db.get(Project,self.project.id).status,'active')
        self.assertIsNotNone(self.db.get(Chat,self.chat.id))
        event_types=[e.event_type for e in self.db.scalars(select(ProjectEvent)).all()]
        self.assertIn('project_archived',event_types)
        self.assertIn('project_restored',event_types)


if __name__=='__main__':
    unittest.main()
