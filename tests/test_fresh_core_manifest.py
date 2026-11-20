"""Fresh Core manifest and Write Key regression from 20 Nov user screenshots."""
import hashlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base
from app.models import Project, ProjectMemory, User
from app.services.fresh_core_manifest import (
    FreshCoreManifestReader, checked_manifest_url, verify_write_access,
)
from app.services.fresh_core_reader import FreshCoreError, seal_key, unseal_key, vault_ready
from app.services.fresh_core_project import (
    connect_manifest, connection_state, refresh_connected, connect_write_key,
)
from app.services import fresh_core_vault

SITE = "https://shop.example.cz"
TOKEN = "T" * 56
ROOT = SITE + "/wp-content/uploads/fresh-core-connector/" + TOKEN + "/"
MANIFEST_URL = ROOT + "manifest.json"
KEY = "fresh-core-write-key-for-tests-123456789"


def make_fixture(*, batch=True, malformed_sha=False, incomplete=False):
    structure = {
        "manifest": {
            "site": {"url": SITE + "/", "name": "Můj WordPress", "language": "cs_CZ"},
            "runtime": {"wordpress": "6.9", "php": "8.3", "woocommerce": "10.1"},
            "theme": {"name": "Hello", "version": "3.2"},
            "active_plugins": [{"file": "plugin/a.php", "name": "My Plugin", "version": "1.0"}],
        },
        "post_types": [{"name": "page", "label": "Stránky", "counts": {"publish": 7}}],
        "taxonomies": [{"name": "category", "term_count": 3}],
        "menus": [],
    }
    docs = {
        "structure.json": structure,
        "elementor.json": {"overview": {"document_count": 2}, "templates": []},
        "diagnostics.json": {
            "taxonomies": {
                "category": {
                    "total": 3,
                    "empty_count": 1,
                    "duplicate_name_groups": [],
                }
            },
        },
    }
    root = ROOT + ("snapshots/20261120000100-abcdef/" if batch else "")
    raw = {name: json.dumps(payload, ensure_ascii=False).encode("utf-8")
           for name, payload in docs.items()}
    files = [
        {"file": name, "url": root + name, "bytes": len(blob),
         "sha256": hashlib.sha256(blob).hexdigest() if not malformed_sha or name != "structure.json"
                   else "0" * 64}
        for name, blob in raw.items()
    ]
    manifest = {
        "site": {"url": SITE + "/", "name": "Můj WordPress"},
        "fresh_core_version": "0.7.8",
        "generated_at_gmt": "2026-11-20T09:00:00Z",
        "files": files,
    }
    if batch:
        manifest["snapshot_id"] = "20261120000100-abcdef"
        manifest["batch_delivery"] = {
            "mode": "snapshot", "total_parts": 8,
            "completed_parts": 7 if incomplete else 8,
            "is_last": not incomplete,
            "status": "running" if incomplete else "complete",
        }
    raw_manifest = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
    payloads = {"/wp-content/uploads/fresh-core-connector/" + TOKEN +
                "/manifest.json": raw_manifest}
    payloads.update({("/wp-content/uploads/fresh-core-connector/" + TOKEN + "/" +
                      ("snapshots/20261120000100-abcdef/" if batch else "") + name): blob
                     for name, blob in raw.items()})

    def handler(request):
        assert request.method == "GET", "Unexpected HTTP write!"
        assert request.url.host == "shop.example.cz"
        if request.url.path in payloads:
            return httpx.Response(200, content=payloads[request.url.path],
                                  headers={"content-type": "application/json"})
        return httpx.Response(404, json={"message": "missing"})
    return httpx.Client(transport=httpx.MockTransport(handler))


class ManifestContractTests(unittest.TestCase):
    def setUp(self):
        self.p1 = patch.object(settings, "fresh_core_allowed_hosts", "")
        self.p2 = patch("app.services.fresh_core_reader._validate_public_url")
        self.p3 = patch("app.services.fresh_core_manifest._validate_public_url")
        for p in (self.p1, self.p2, self.p3):
            p.start()

    def tearDown(self):
        for p in (self.p3, self.p2, self.p1):
            p.stop()

    def test_connect_with_no_website_url_and_no_read_key(self):
        with make_fixture() as client, FreshCoreManifestReader(
                MANIFEST_URL, client=client) as reader:
            snap = reader.read_snapshot()
        self.assertEqual(snap["site_url"], SITE)
        self.assertEqual(snap["active_plugins"][0]["name"], "My Plugin")
        self.assertEqual(snap["diagnostics"]["category"]["empty_count"], 1)
        self.assertEqual(snap["manifest_file_count"], 3)
        self.assertTrue(snap["manifest_batch_complete"])
        self.assertNotIn(TOKEN, json.dumps(snap))
        self.assertFalse(snap["coverage"]["manifest_stale"] is False and
                         snap["manifest_generated_at_gmt"] == "")

    def test_legacy_boban_manifest_works_without_batch_metadata(self):
        with make_fixture(batch=False) as client, FreshCoreManifestReader(
                MANIFEST_URL, client=client) as reader:
            snap = reader.read_snapshot()
        self.assertTrue(snap["manifest_legacy"])
        self.assertEqual(snap["wordpress_version"], "6.9")

    def test_corrupt_checksum_rejected(self):
        with make_fixture(malformed_sha=True) as client:
            with FreshCoreManifestReader(MANIFEST_URL, client=client) as reader:
                with self.assertRaisesRegex(FreshCoreError, "součet"):
                    reader.read_snapshot()

    def test_unfinished_batch_rejected(self):
        with make_fixture(incomplete=True) as client:
            with FreshCoreManifestReader(MANIFEST_URL, client=client) as reader:
                with self.assertRaisesRegex(FreshCoreError, "dokončen"):
                    reader.read_snapshot()

    def test_host_and_token_path_are_restricted(self):
        invalid = [
            "https://evil.example.cz/wp-content/uploads/fresh-core-connector/" +
            TOKEN + "/manifest.json",
            SITE + "/wp-json/wp/v2/posts",
            SITE + "/wp-content/uploads/fresh-core-connector/" + TOKEN +
            "/manifest.json?secret=1",
        ]
        for uri in invalid:
            with self.subTest(uri=uri), self.assertRaises(FreshCoreError):
                checked_manifest_url(uri, SITE)

    def test_redirect_never_followed(self):
        def redirected(_):
            return httpx.Response(302, headers={"location": "https://malicious.example/"})
        with httpx.Client(transport=httpx.MockTransport(redirected)) as client:
            with FreshCoreManifestReader(MANIFEST_URL, client=client) as reader:
                with self.assertRaisesRegex(FreshCoreError, "přesměrov"):
                    reader.read_snapshot()

    def test_persistence_site_encryption_and_reuse(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        try:
            user = User(email="owner@example.cz", password_hash="hash", role="user")
            db.add(user)
            db.flush()
            pr = Project(owner_id=user.id, name="Web – obchod")
            db.add(pr)
            db.commit()
            with patch.object(settings, "fresh_core_vault_key",
                              Fernet.generate_key().decode("ascii")):
                def rf(url, site):
                    return FreshCoreManifestReader(url, site, client=make_fixture())
                first = connect_manifest(db, pr.id, user.id, MANIFEST_URL,
                                         reader_factory=rf)
                state = connection_state(db, pr.id)
                self.assertEqual(state["kind"], "synced")
                self.assertEqual(state["read_mode"], "manifest")
                self.assertEqual(first["site_url"], SITE)
                website = db.scalar(select(ProjectMemory).where(
                    ProjectMemory.kind == "wordpress_site_url"))
                self.assertTrue(website.verified)
                self.assertEqual(website.content, SITE)
                all_rows = db.scalars(select(ProjectMemory)).all()
                self.assertNotIn(TOKEN, " ".join(x.content for x in all_rows))
                refresh_connected(db, pr.id, user.id, SITE, manifest_reader_factory=rf)
                self.assertEqual(connection_state(db, pr.id)["kind"], "synced")
        finally:
            db.close()
            engine.dispose()

    def test_write_access_ping_never_posts(self):
        def handler(req):
            self.assertEqual(req.method, "GET")
            self.assertEqual(req.headers["X-Fresh-Core-Write-Key"], KEY)
            self.assertTrue(req.url.path.endswith("/write/ping"))
            return httpx.Response(200, json={"success": True, "data": {
                "ok": True, "version": "0.7.8", "write_enabled": True}})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = verify_write_access(SITE, KEY, client=client)
        self.assertTrue(result["write_enabled"])
        self.assertEqual(result["plugin_version"], "0.7.8")

    def test_write_access_wrong_key_fails(self):
        with httpx.Client(transport=httpx.MockTransport(
                lambda _: httpx.Response(403, json={}))) as client:
            with self.assertRaises(FreshCoreError):
                verify_write_access(SITE, KEY, client=client)


class VaultFileTests(unittest.TestCase):
    def test_vault_file_created_private_and_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            key_file = Path(folder) / "private" / "vault.key"
            with patch.object(settings, "fresh_core_vault_key", ""), \
                 patch("app.services.fresh_core_vault._path", return_value=key_file):
                cipher = seal_key("this-is-test-credential")
                self.assertTrue(vault_ready())
                self.assertEqual(stat.S_IMODE(key_file.stat().st_mode), 0o600)
                self.assertEqual(unseal_key(cipher), "this-is-test-credential")
                self.assertEqual(seal_key("another") != cipher, True)
                self.assertEqual(unseal_key(cipher), "this-is-test-credential")
                self.assertNotIn("this-is-test-credential", key_file.read_text())
