"""Evidence-based WordPress and GitHub novice journeys, including DB writes.

No external connections, installations, site writes or deployments occur here.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import User, Project, ProjectMemory
from app import main
from app.services.project_journeys import (
    WORDPRESS_TYPE, DEVELOPMENT_TYPE, FRESH_CORE_PRODUCT_URL,
    selected_project_type, project_mode, journey_for_project, validate_site_url,
)


class JourneyPresentationTests(unittest.TestCase):
    def test_type_selection_and_legacy_detection(self):
        self.assertEqual(selected_project_type('wordpress'), WORDPRESS_TYPE)
        self.assertEqual(selected_project_type('github'), DEVELOPMENT_TYPE)
        self.assertEqual(project_mode('WordPress / WooCommerce'), 'wordpress')
        self.assertEqual(project_mode('Vývoj aplikace / GitHub'), 'github')
        self.assertEqual(project_mode('', github_linked=True), 'github')
        self.assertEqual(project_mode('', github_linked=False), 'general')

    def test_wordpress_source_installation_does_not_claim_connection(self):
        journey = journey_for_project(project_id=18, mode='wordpress',
            github={'kind':'synced'}, has_business_goal=True,
            has_site_url=True)
        self.assertEqual(journey['name'], 'Můj WordPress web')
        self.assertEqual(journey['steps'][1]['href'], FRESH_CORE_PRODUCT_URL)
        self.assertEqual(journey['steps'][2]['status'], 'next')
        self.assertEqual(journey['steps'][3]['status'], 'planned')
        self.assertNotIn('připojeno', journey['steps'][1]['body'].lower())
        self.assertIn('neověřili', journey['steps'][0]['body'])

    def test_github_snapshot_only_marks_real_sync_done(self):
        pending = journey_for_project(project_id=8, mode='github',
            github={'kind':'pending'}, has_business_goal=False, has_site_url=False)
        self.assertEqual(pending['steps'][1]['status'], 'done')
        self.assertNotEqual(pending['steps'][2]['status'], 'done')
        done = journey_for_project(project_id=8, mode='github',
            github={'kind':'synced'}, has_business_goal=False, has_site_url=False)
        self.assertEqual(done['steps'][2]['status'], 'done')
        self.assertEqual(done['steps'][3]['status'], 'planned')

    def test_url_is_only_declared_and_credentials_rejected(self):
        self.assertEqual(validate_site_url('www.example.cz'), 'https://www.example.cz')
        self.assertEqual(validate_site_url('https://example.cz/sluzby/'), 'https://example.cz/sluzby')
        for value in ['https://admin:secret@example.cz', 'javascript:alert(1)',
                      'https://example.cz/?token=secret', 'https://example.cz:9999/path',
                      '://invalid', '']:
            if not value:
                self.assertEqual(validate_site_url(value), '')
            else:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    validate_site_url(value)


class BeginnerProjectRoutesTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite+pysqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db=sessionmaker(bind=self.engine)()
        user=User(email='starter@example.com',password_hash='test',role='user')
        self.db.add(user)
        self.db.commit()
        self.user=user

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_create_wordpress_project_saves_type_url_without_web_connection(self):
        with patch('app.main.require_user',return_value=self.user):
            response=main.create_project(
                SimpleNamespace(), name='Moje kavárna', description='Více poptávek',
                project_mode_choice='wordpress', website_url='kavarna.example.cz', db=self.db)
        self.assertEqual(response.status_code,303)
        self.assertIn('guide=wp-start',response.headers['location'])
        p=self.db.scalars(select(Project)).one()
        entries=self.db.scalars(select(ProjectMemory).where(ProjectMemory.project_id==p.id)).all()
        spec={m.kind:m for m in entries}
        self.assertEqual(spec['project_type'].content, WORDPRESS_TYPE)
        self.assertEqual(spec['wordpress_site_url'].content,'https://kavarna.example.cz')
        self.assertFalse(spec['wordpress_site_url'].verified)
        self.assertEqual(self.db.scalar(select(func.count(Project.id))),1)

    def test_existing_project_mode_and_url_can_change_without_erasing_goal(self):
        p=Project(owner_id=self.user.id,name='Můj web',description='Web')
        self.db.add(p)
        self.db.flush()
        main.save_project_spec_value(self.db,p.id,'business_goal','Získat více zákazníků')
        self.db.commit()
        with patch('app.main.require_user',return_value=self.user):
            changed=main.choose_existing_project_mode(
                SimpleNamespace(),p.id,project_mode_choice='wordpress',db=self.db)
            updated=main.save_declared_website_url(
                SimpleNamespace(),p.id,website_url='example.cz',db=self.db)
        self.assertEqual(changed.status_code,303)
        self.assertEqual(updated.status_code,303)
        spec=main.project_spec(self.db,p.id)
        self.assertEqual(spec['business_goal'],'Získat více zákazníků')
        self.assertEqual(spec['project_type'],WORDPRESS_TYPE)
        memory=self.db.scalar(select(ProjectMemory).where(
            ProjectMemory.project_id==p.id,ProjectMemory.kind=='wordpress_site_url'))
        self.assertEqual(memory.content,'https://example.cz')
        self.assertFalse(memory.verified)

    def test_cross_user_cannot_reclassify_or_edit_url(self):
        other=User(email='foreign@example.com',password_hash='test',role='user')
        self.db.add(other)
        self.db.flush()
        p=Project(owner_id=other.id,name='Private web')
        self.db.add(p);self.db.commit()
        from fastapi import HTTPException
        with patch('app.main.require_user',return_value=self.user):
            with self.assertRaises(HTTPException) as changed:
                main.choose_existing_project_mode(
                    SimpleNamespace(),p.id,project_mode_choice='wordpress',db=self.db)
            with self.assertRaises(HTTPException) as updated:
                main.save_declared_website_url(
                    SimpleNamespace(),p.id,website_url='site.example',db=self.db)
        self.assertIn(changed.exception.status_code,(403,404))
        self.assertIn(updated.exception.status_code,(403,404))

    def test_reject_invalid_site_url_before_project_creation(self):
        from fastapi import HTTPException
        with patch('app.main.require_user',return_value=self.user):
            with self.assertRaises(HTTPException):
                main.create_project(SimpleNamespace(),name='Risky',description='',
                    project_mode_choice='wordpress',
                    website_url='https://admin:pass@example.cz',db=self.db)
        self.assertEqual(self.db.scalar(select(func.count(Project.id))),0)


if __name__=='__main__':
    unittest.main()
