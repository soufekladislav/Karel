"""Regression tests for safe handling of manifest URLs and uploaded files."""
import io
import json
import asyncio
import httpx
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.config import settings
from app.services.security_selfcheck import collect_security_checks
from app.services.request_security import allow_browser_mutation, secure_production_configuration
from app.main import healthz, require_chat_in_project, app
from app.services.source_resolver import require_allowed_manifest_host, require_allowed_source_host, _validate_public_url, fetch_public_manifest, _can_read_internal_manifest, _fetch_public_text, MAX_SOURCE_BYTES
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
        fake = SimpleNamespace(secret='change-me', https_only=False, manifest_allowed_hosts='', environment='development', source_allowed_hosts='')
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


class CrossProjectSecurityTests(unittest.TestCase):
    def test_project_foreign_chat_id_is_rejected(self):
        from fastapi import HTTPException
        db = SimpleNamespace(get=lambda model, id: SimpleNamespace(id=id, project_id=44))
        with self.assertRaises(HTTPException) as context:
            require_chat_in_project(db, 55, 123)
        self.assertEqual(context.exception.status_code, 404)

    def test_same_project_chat_id_is_valid(self):
        db = SimpleNamespace(get=lambda model, id: SimpleNamespace(id=id, project_id=55))
        self.assertEqual(require_chat_in_project(db, 55, 123).id, 123)


class BrowserMutationSecurityTests(unittest.TestCase):
    def test_cross_origin_and_missing_provenance_are_rejected(self):
        target = 'https://ai-coder.freshcrackers.cz'
        bad = [
            {'origin': 'https://attacker.example'},
            {'origin': 'https://other.freshcrackers.cz', 'sec-fetch-site': 'same-site'},
            {'origin': 'null'},
            {'referer': 'https://ai-coder.freshcrackers.cz.evil.invalid/form'},
            {'sec-fetch-site': 'cross-site'},
            {},
        ]
        for headers in bad:
            with self.subTest(headers=headers):
                self.assertFalse(allow_browser_mutation(headers, target))

    def test_same_origin_browser_submission_is_allowed(self):
        target = 'https://ai-coder.freshcrackers.cz'
        self.assertTrue(allow_browser_mutation({'origin': target}, target))
        self.assertTrue(allow_browser_mutation(
            {'referer': target + '/projects/1?view=docs'}, target))
        self.assertTrue(allow_browser_mutation(
            {'sec-fetch-site': 'same-origin'}, target))

    def test_weak_production_secret_fails_closed(self):
        self.assertFalse(secure_production_configuration(
            'https://ai-coder.freshcrackers.cz', 'change-me', True))
        self.assertFalse(secure_production_configuration(
            'http://ai-coder.freshcrackers.cz', 'a' * 50, True))
        self.assertFalse(secure_production_configuration(
            'https://ai-coder.freshcrackers.cz', 'a' * 50, False))
        self.assertTrue(secure_production_configuration(
            'https://ai-coder.freshcrackers.cz', 'a' * 50, True))

    def test_browser_rejects_foreign_post_before_login(self):
        async def request():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport,
                                          base_url='http://localhost:8000') as client:
                return await client.post('/login', data={'email':'x@example.com','password':'x'},
                                         headers={'origin':'https://malicious.invalid'})
        response = asyncio.run(request())
        self.assertEqual(response.status_code, 403)

    def test_insecure_production_mode_returns_503(self):
        async def request():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport,
                                          base_url='http://localhost:8000') as client:
                return await client.get('/healthz')
        with patch.object(settings, 'environment', 'production'), \
             patch.object(settings, 'app_url', 'https://ai-coder.freshcrackers.cz'), \
             patch.object(settings, 'secret', 'change-me'):
            response = asyncio.run(request())
        self.assertEqual(response.status_code, 503)


class SourceDownloadSecurityTests(unittest.TestCase):
    def test_general_url_sources_are_fail_closed_without_allowlist(self):
        with patch.object(settings, 'source_allowed_hosts', ''):
            with self.assertRaisesRegex(ValueError, 'SOURCE_ALLOWED_HOSTS'):
                require_allowed_source_host('https://github.com/example/abc')

    def test_wildcard_cannot_match_unrelated_or_apex(self):
        with patch.object(settings, 'source_allowed_hosts', '*.freshcrackers.cz'):
            require_allowed_source_host('https://docs.freshcrackers.cz/')
            for url in ('https://freshcrackers.cz/', 'https://freshcrackers.cz.evil.test/',
                        'http://docs.freshcrackers.cz/', 'https://docs.freshcrackers.cz:8080/'):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    require_allowed_source_host(url)

    def test_streaming_abort_on_large_decoded_response(self):
        original_client = httpx.Client
        transport = httpx.MockTransport(lambda req: httpx.Response(
            200, headers={'Content-Type': 'text/plain'}, content=b'x' * (MAX_SOURCE_BYTES + 1)))
        with patch.object(settings, 'source_allowed_hosts', 'trusted.example'), \
             patch('app.services.source_resolver._validate_public_url', return_value=None), \
             patch('app.services.source_resolver.httpx.Client',
                   side_effect=lambda **kwargs: original_client(transport=transport)):
            with self.assertRaisesRegex(ValueError, 'větší než 1 MB'):
                _fetch_public_text('https://trusted.example/large', False)

    def test_redirect_to_other_domain_is_rejected_before_fetch(self):
        original_client = httpx.Client
        urls = []
        def responder(req):
            urls.append(str(req.url))
            return httpx.Response(302, headers={'Location': 'https://evil.invalid/private'})
        transport = httpx.MockTransport(responder)
        with patch.object(settings, 'source_allowed_hosts', 'trusted.example'), \
             patch('app.services.source_resolver._validate_public_url', return_value=None), \
             patch('app.services.source_resolver.httpx.Client',
                   side_effect=lambda **kwargs: original_client(transport=transport)):
            with self.assertRaisesRegex(ValueError, 'není povolena'):
                _fetch_public_text('https://trusted.example/start', False)
        self.assertEqual(urls, ['https://trusted.example/start'])


if __name__ == '__main__':
    unittest.main()
