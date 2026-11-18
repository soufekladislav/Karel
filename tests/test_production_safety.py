"""Regression tests for read-only production audit and explicit backup-gated migrations."""
import io
import json
import os
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, inspect

from app.database import Base
from app import models  # register ORM definitions
from app import bootstrap
from scripts.schema_migration import inspect_schema, ensure_backup_file
from scripts import production_audit


class SchemaManagementTests(unittest.TestCase):
    def test_schema_preflight_does_not_create_tables(self):
        engine = create_engine('sqlite+pysqlite:///:memory:')
        try:
            plan = inspect_schema(engine, Base.metadata)
            self.assertFalse(plan['ready'])
            self.assertIn('github_repo_links', plan['missing_tables'])
            self.assertEqual(inspect(engine).get_table_names(), [])
            Base.metadata.create_all(engine)
            ready = inspect_schema(engine, Base.metadata)
            self.assertTrue(ready['ready'])
            self.assertEqual(ready['missing_tables'], [])
        finally:
            engine.dispose()

    def test_production_boot_will_not_auto_migrate_empty_db(self):
        engine = create_engine('sqlite+pysqlite:///:memory:')
        try:
            with patch.object(bootstrap.settings, 'environment', 'production'), \
                 patch.object(bootstrap, 'engine', engine), redirect_stderr(io.StringIO()):
                state = bootstrap.initialize_app()
            self.assertFalse(state['ok'])
            self.assertTrue(state['database'])
            self.assertFalse(state['schema'])
            self.assertEqual(inspect(engine).get_table_names(), [])
        finally:
            engine.dispose()

    def test_migration_requires_real_recent_external_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'backup.sql'
            with self.assertRaises(ValueError):
                ensure_backup_file(str(p))
            p.write_bytes(b'A' * 2048)
            ensure_backup_file(str(p))
            os.utime(p, (time.time() - 90000, time.time() - 90000))
            with self.assertRaises(ValueError):
                ensure_backup_file(str(p))


class ReadOnlyAuditTests(unittest.TestCase):
    def test_audit_imports_no_application_startup_and_never_echoes_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'app').mkdir()
            (root / 'app' / 'main.py').write_text("APP_VERSION = 'audit-test-version'\n",
                                                  encoding='utf-8')
            with patch.object(production_audit, 'BASE', root), \
                 patch.dict(os.environ, {
                     'DATABASE_URL': '', 'APP_SECRET': 'TOP_SECRET_123456789012345678901234',
                     'KAREL_ENV': 'production', 'APP_URL': 'https://example.test',
                     'SESSION_HTTPS_ONLY': 'true',
                 }, clear=True):
                report = production_audit.run_audit()
            self.assertEqual(report['application_version_on_disk'], 'audit-test-version')
            self.assertEqual(report['database_status'], 'NOT_CONFIGURED')
            self.assertTrue(report['read_only'])
            self.assertNotIn('TOP_SECRET', json.dumps(report))

    def test_apache_protection_keeps_passenger_configuration(self):
        source = (Path(__file__).resolve().parents[1] / '.htaccess').read_text()
        self.assertIn('PassengerAppRoot', source)
        self.assertIn('PassengerPython', source)
        self.assertIn('RewriteRule', source)
        self.assertIn('storage', source)


if __name__ == '__main__':
    unittest.main()
