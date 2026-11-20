"""Regression: an old project-manifest form must route Fresh Core safely."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import main
from app.config import settings
from app.database import Base
from app.models import Project, ProjectMemory, User
from app.services.fresh_core_reader import FreshCoreError


SITE = "https://shop.example.cz"
TOKEN = "T" * 56
FRESH_URL = (SITE + "/wp-content/uploads/fresh-core-connector/"
             + TOKEN + "/manifest.json")


class LegacyManifestFormTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.user = User(email="owner@example.cz", password_hash="hash", role="user")
        self.db.add(self.user)
        self.db.flush()
        self.project = Project(owner_id=self.user.id, name="Starý WordPress")
        self.db.add(self.project)
        self.db.commit()
        self.session = patch("app.main.require_user", return_value=self.user)
        self.session.start()

    def tearDown(self):
        self.session.stop()
        self.db.close()
        self.engine.dispose()

    def test_old_manifest_form_uses_fresh_core_connector_not_generic_loader(self):
        # The screenshot used this old action, leading to MANIFEST_ALLOWED_HOSTS
        # and a redirect to chat. Verify it routes to the new handler instead.
        with patch.object(settings, "manifest_allowed_hosts", ""), \
             patch("app.main.fetch_public_manifest",
                   side_effect=AssertionError("Generic loader must NOT fetch secret URLs")), \
             patch("app.main.connect_manifest",
                   return_value={"site_url": SITE}) as connector:
            response = main.project_manifest_save(
                SimpleNamespace(), self.project.id, url=FRESH_URL, db=self.db
            )
        connector.assert_called_once_with(
            self.db, self.project.id, self.user.id, FRESH_URL, None
        )
        self.assertEqual(response.status_code, 303)
        self.assertIn("view=website", response.headers["location"])
        self.assertIn("#fresh-core-pripojeni", response.headers["location"])
        self.assertNotIn("MANIFEST_ALLOWED_HOSTS", response.headers["location"])
        self.assertNotIn(TOKEN, response.headers["location"])
        self.assertFalse(self.db.scalars(select(ProjectMemory).where(
            ProjectMemory.kind == "manifest")).all())

    def test_failed_manifest_connection_returns_to_wordpress_without_secret(self):
        with patch("app.main.fetch_public_manifest",
                   side_effect=AssertionError("Generic import unexpectedly called")), \
             patch("app.main.connect_manifest",
                   side_effect=FreshCoreError("Kontrolní součet exportu nesouhlasí.")):
            response = main.project_manifest_save(
                SimpleNamespace(), self.project.id, url=FRESH_URL, db=self.db
            )
        self.assertEqual(response.status_code, 303)
        self.assertIn("view=website", response.headers["location"])
        self.assertIn("error=", response.headers["location"])
        self.assertNotIn(TOKEN, response.headers["location"])
        self.assertNotIn("MANIFEST_ALLOWED_HOSTS", response.headers["location"])
        self.assertFalse(self.db.scalars(select(ProjectMemory).where(
            ProjectMemory.kind == "manifest")).all())

    def test_regular_app_manifest_still_uses_original_generic_flow(self):
        url = "https://docs.example.cz/app/manifest.json"
        with patch("app.main.fetch_public_manifest",
                   return_value={"app": "Another project", "version": 1}) as fetch, \
             patch("app.main.connect_manifest",
                   side_effect=AssertionError("Should not be Fresh Core")):
            response = main.project_manifest_save(
                SimpleNamespace(), self.project.id, url=url, db=self.db
            )
        fetch.assert_called_once_with(url)
        self.assertEqual(response.status_code, 303)
        self.assertNotIn("view=website", response.headers["location"])
        memory = self.db.scalar(select(ProjectMemory).where(
            ProjectMemory.project_id == self.project.id,
            ProjectMemory.kind == "manifest"))
        self.assertIsNotNone(memory)
        self.assertEqual(memory.title, url)

    def test_wordpress_technical_sources_form_points_to_fresh_core(self):
        from pathlib import Path
        template = (Path(__file__).resolve().parents[1] /
                    "app" / "templates" / "project.html").read_text(encoding="utf-8")
        self.assertIn('name="manifest_url"', template)
        self.assertIn('action="/projects/{{ project.id }}/fresh-core/manifest-connect"', template)
        self.assertIn("project_mode == 'wordpress'", template)


if __name__ == "__main__":
    unittest.main()
