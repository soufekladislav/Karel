"""Regression tests for safe handling of manifest URLs and uploaded files."""
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.config import settings
from app.services.security_selfcheck import collect_security_checks
from app.main import healthz
from app.services.source_resolver import require_allowed_manifest_host, _validate_public_url, fetch_public_manifest, _can_read_internal_manifest
from app.services.files import create_bundle
from app.services.attachment_reader import _read_docx


class ManifestSecurityTests(unittest.TestCase):
    def test_manifest_allowlist_is_fail_closed(self):
        with patch.object(settings, 'manifest_allowed_hosts', ''):
            with self.assertRaisesRegex(ValueError, 'MANIFEST_ALLOWED_HOSTS'):
                require_allowed_manifest_host('https://www.freshcrackers.cz/manifest.json')

    def test_host_must_match_explicit_domain_or_approved_subdomain(self):
        with patch.object(settings, 'manifest_allowed_hosts', 'freshcrackers.cz,*.freshcrackers.cz'):
            require_allowed_manifest_host('https://freshcrackers.cz/manifest.json')
            require_allowed_manifest_host('https://ai-coder.freshcrackers.cz/manifest.json')
            for bad in (
                'https://freshcrackers.cz.evil.invalid/manifest.json',
                'https://evil.invalid/manifest.json',
                'http://freshcrackers.cz/manifest.json',
                'https://user:password@freshcrackers.cz/manifest.json',
                'https://freshcrackers.cz:8080/manifest.json',
            ):
                with self.subTest(url=bad), self.assertRaises(ValueError):
                    require_allowed_manifest_host(bad)

    def test_public_url_rejects_private_loopback(self):
        with self.assertRaises(ValueError):
            _validate_public_url('http://127.0.0.1/private')

    def test_manifest_requires_json_object(self):
        with patch('app.services.source_resolver._fetch_public_text', return_value=('[]', 'application/json')):
            with self.assertRaisesRegex(ValueError, 'JSON objekt'):
                fetch_public_manifest('https://freshcrackers.cz/manifest.json')

    def test_admin_selfcheck_reports_status_without_exposing_secrets(self):
        fake = SimpleNamespace(secret='change-me', https_only=False, manifest_allowed_hosts='')
        result = collect_security_checks(fake, {'database': False, 'schema': False, 'error': 'sensitive db url'})
        self.assertTrue(any(x['state'] == 'warning' for x in result['checks']))
        self.assertTrue(any(x['state'] == 'unverified' for x in result['checks']))
        self.assertNotIn('sensitive db url', str(result))
        self.assertNotIn('change-me', str(result))

    def test_internal_manifest_remains_superadmin_only(self):
        self.assertFalse(_can_read_internal_manifest(SimpleNamespace(role='user', email='any@example.com')))
        self.assertTrue(_can_read_internal_manifest(SimpleNamespace(role='superadmin', email='admin@example.com')))

    def test_healthz_does_not_leak_internal_exception(self):
        with patch('app.main.bootstrap_state', return_value={'ok': False, 'error': 'db password = hidden'}):
            response = healthz()
        self.assertEqual(response.status_code, 503)
        self.assertFalse(json.loads(response.body)['ok'])
        self.assertNotIn('password', response.body.decode())
        self.assertNotIn('database', response.body.decode())


class AttachmentSafetyTests(unittest.TestCase):
    def test_bundle_flattens_user_supplied_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '1').mkdir()
            (root / '1' / 'a.txt').write_text('safe', encoding='utf-8')
            with patch.object(settings, 'uploads_dir', root):
                pf = SimpleNamespace(id=5, name='../../escape.txt', stored_name='1/a.txt')
                target, _ = create_bundle(1, [pf])
            with zipfile.ZipFile(target) as zf:
                self.assertEqual(zf.namelist(), ['escape.txt'])

    def test_docx_rejects_unbounded_document_xml(self):
        from app.services import attachment_reader as reader
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('word/document.xml', 'A' * 120)
        with patch.object(reader, 'MAX_ARCHIVE_UNCOMPRESSED', 100):
            with self.assertRaisesRegex(ValueError, 'příliš velký'):
                _read_docx(buffer.getvalue())


if __name__ == '__main__':
    unittest.main()
