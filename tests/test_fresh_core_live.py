"""Fresh Core 0.7.8 READ contract + encrypted per-project state.

Uses real HTTPX MockTransport and real in-memory DB; never reaches a website.
"""
import json
import unittest
from unittest.mock import patch

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base
from app.models import Project, ProjectMemory, User
from app.services.fresh_core_reader import (
    FreshCoreReader, FreshCoreError, seal_key, unseal_key, validate_fresh_core_site,
)
from app.services.fresh_core_project import (
    connect_readonly, refresh_readonly, disconnect_readonly, connection_state,
)


SITE = "https://shop.example.cz"
READ_KEY = "fresh-core-read-key-for-test"


def wordpress_reply(site=SITE):
    return {
        "manifest": {
            "site": {"url": site + "/", "name": "Můj obchod", "language": "cs_CZ"},
            "runtime": {"wordpress": "6.9", "php": "8.3", "woocommerce": "10.1", "elementor": "3.6"},
            "theme": {"name": "Hello", "version": "3.0"},
            "active_plugins": [
                {"name": "Fresh Core", "version": "0.7.8", "file": "fresh-core/fresh-core.php"},
                {"name": "WooCommerce", "version": "10.1", "file": "woo/woo.php"},
            ],
            "routes": {"write_ping": "/write/ping"},
            "secret_that_must_not_be_saved": "DO_NOT_STORE_ME",
        },
        "post_types": [{"name": "product", "label": "Produkty",
                        "counts": {"publish": 42, "draft": 3}}],
        "taxonomies": [{"name": "product_cat", "term_count": 7}],
        "menus": [{"name": "Hlavní menu", "items": [{"url": SITE + "/osobni-data"}]}],
        "elementor_overview": {"document_count": 5},
        "database_tables": [{"name": "wp_users", "rows": 90}],
    }


def transport(responder=None):
    def handle(request):
        assert request.method == "GET"
        assert request.headers["x-fresh-core-key"] == READ_KEY
        assert request.url.host == "shop.example.cz"
        assert request.url.path.startswith("/wp-json/fresh-core/v1/")
        if responder:
            return responder(request)
        if request.url.path.endswith("/ping"):
            payload = {"success": True, "data": {
                "ok": True, "version": "0.7.8", "time_gmt": "2026-11-19T18:00:00Z",
            }}
        else:
            payload = {"success": True, "data": wordpress_reply()}
        return httpx.Response(200, json=payload)
    return httpx.Client(transport=httpx.MockTransport(handle))


class FreshCoreReaderTests(unittest.TestCase):
    def setUp(self):
        self.allowed = patch.object(settings, "fresh_core_allowed_hosts", "shop.example.cz")
        self.dns = patch("app.services.fresh_core_reader._validate_public_url")
        self.allowed.start()
        self.dns.start()

    def tearDown(self):
        self.dns.stop()
        self.allowed.stop()

    def test_full_ping_and_snapshot_are_read_only_and_sanitized(self):
        with transport() as client:
            with FreshCoreReader(SITE, READ_KEY, client=client) as reader:
                result = reader.read_snapshot()
        self.assertEqual(result["site_name"], "Můj obchod")
        self.assertEqual(result["wordpress_version"], "6.9")
        self.assertEqual(result["active_plugin_count"], 2)
        self.assertEqual(result["post_types"][0]["counts"]["publish"], 42)
        self.assertIn("fetched_at", result)
        self.assertNotIn("routes", result)
        self.assertNotIn("database_tables", result)
        self.assertNotIn("secret_that_must_not_be_saved", json.dumps(result))
        self.assertNotIn("osobni-data", json.dumps(result))

    def test_rejects_foreign_snapshot(self):
        def responder(request):
            if request.url.path.endswith("/ping"):
                return httpx.Response(200, json={"success": True, "data": {"ok": True, "version": "0.7.8"}})
            return httpx.Response(200, json={
                "success": True, "data": wordpress_reply("https://other.example.cz"),
            })
        with transport(responder) as client, FreshCoreReader(SITE, READ_KEY, client=client) as reader:
            with self.assertRaisesRegex(FreshCoreError, "jiného webu"):
                reader.read_snapshot()

    def test_access_key_failure_and_redirect_do_not_leak_secret(self):
        for status in (403, 302):
            def responder(_request):
                return httpx.Response(status, headers={"location": "https://malicious.example"} if status==302 else {})
            with self.subTest(status=status), transport(responder) as client:
                with FreshCoreReader(SITE, READ_KEY, client=client) as reader:
                    with self.assertRaises(FreshCoreError) as failure:
                        reader.read_snapshot()
                self.assertNotIn(READ_KEY, str(failure.exception))
                self.assertNotIn("malicious", str(failure.exception))

    def test_private_network_and_unapproved_host_fail_closed(self):
        with patch("app.services.fresh_core_reader._validate_public_url",
                   side_effect=ValueError("Private IP")):
            with self.assertRaises(FreshCoreError):
                validate_fresh_core_site(SITE)
        with self.assertRaises(FreshCoreError):
            validate_fresh_core_site("https://evil.example.net")

    def test_large_snapshot_is_bounded_after_decompression(self):
        def responder(request):
            if request.url.path.endswith("/ping"):
                return httpx.Response(200, json={"success": True, "data": {"ok":True, "version":"0.7.8"}})
            return httpx.Response(200, json={"success":True,"data":{"large":"X"*(2*1024*1024)}})
        with transport(responder) as client, FreshCoreReader(SITE,READ_KEY,client=client) as reader:
            with self.assertRaisesRegex(FreshCoreError, "2 MB"):
                reader.read_snapshot()


class FreshCoreVaultAndProjectTests(unittest.TestCase):
    def setUp(self):
        self.allowed = patch.object(settings, "fresh_core_allowed_hosts", "shop.example.cz")
        self.vault = patch.object(settings, "fresh_core_vault_key", Fernet.generate_key().decode("ascii"))
        self.dns = patch("app.services.fresh_core_reader._validate_public_url")
        for p in (self.allowed, self.vault, self.dns):
            p.start()
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        user=User(email="owner@sample.cz",password_hash="hash",role="user")
        self.db.add(user);self.db.flush()
        p=Project(owner_id=user.id,name="Můj web")
        self.db.add(p);self.db.commit()
        self.project_id=p.id
        self.user_id=user.id

    def tearDown(self):
        self.db.close();self.engine.dispose()
        for p in (self.dns,self.vault,self.allowed):
            p.stop()

    def _reader(self, site, key):
        return FreshCoreReader(site,key,client=transport())

    def test_round_trip_key_encrypted_at_rest(self):
        encrypted=seal_key(READ_KEY)
        self.assertNotIn(READ_KEY, encrypted)
        self.assertEqual(unseal_key(encrypted), READ_KEY)

    def test_connect_refresh_and_revoke(self):
        snap=connect_readonly(self.db,self.project_id,self.user_id,SITE,READ_KEY,
                              reader_factory=self._reader)
        state=connection_state(self.db,self.project_id)
        self.assertEqual(state["kind"],"synced")
        self.assertEqual(snap["plugin_version"],"0.7.8")
        rows=self.db.scalars(select(ProjectMemory).where(
            ProjectMemory.project_id==self.project_id)).all()
        self.assertEqual(len(rows),3)  # credential, verified snapshot and baseline audit
        self.assertNotIn(READ_KEY," ".join(x.content for x in rows))
        self.assertFalse(next(x for x in rows if x.kind=="fresh_core_read_credential").verified)
        refresh_readonly(self.db,self.project_id,self.user_id,SITE,reader_factory=self._reader)
        self.assertEqual(connection_state(self.db,self.project_id)["kind"],"synced")
        disconnect_readonly(self.db,self.project_id,self.user_id)
        self.assertEqual(connection_state(self.db,self.project_id)["kind"],"unlinked")
        self.assertFalse(self.db.scalars(select(ProjectMemory)).all())

    def test_bad_new_key_never_erases_previous_valid_connection(self):
        connect_readonly(self.db,self.project_id,self.user_id,SITE,READ_KEY,
                         reader_factory=self._reader)
        before=connection_state(self.db,self.project_id)["snapshot"]
        with self.assertRaises(FreshCoreError):
            connect_readonly(self.db,self.project_id,self.user_id,SITE,"wrong-key",
                reader_factory=lambda s,k: FreshCoreReader(
                    s,k,client=httpx.Client(transport=httpx.MockTransport(
                        lambda _request:httpx.Response(403)))))
        self.assertEqual(connection_state(self.db,self.project_id)["snapshot"],before)
        self.assertEqual(len(self.db.scalars(select(ProjectMemory)).all()),3)

    def test_refresh_detects_changes_and_preserves_old_inventory(self):
        from app.services.fresh_core_project import HISTORY_KIND
        initial=connect_readonly(self.db,self.project_id,self.user_id,SITE,READ_KEY,
                                 reader_factory=self._reader)
        changed=json.loads(json.dumps(initial))
        changed["fetched_at"]="2026-11-20T00:30:00Z"
        changed["active_plugins"][0]["version"]="0.7.9"

        class Reader:
            def __init__(self, site, key):
                assert site == SITE and key == READ_KEY
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return None
            def read_snapshot(self):
                return changed

        refresh_readonly(self.db,self.project_id,self.user_id,SITE,
                         reader_factory=Reader)
        state=connection_state(self.db,self.project_id)
        self.assertEqual(state["audit"]["status"],"changed")
        self.assertTrue(any(
            c["area"] == "plugins" for c in state["audit"]["changes"]))
        history=self.db.scalars(select(ProjectMemory).where(
            ProjectMemory.kind == HISTORY_KIND)).all()
        self.assertEqual(len(history),1)
        self.assertEqual(json.loads(history[0].content)["plugin_version"], "0.7.8")
        self.assertNotIn(READ_KEY,history[0].content)

    def test_vault_misconfiguration_rejects_key(self):
        with patch.object(settings,"fresh_core_vault_key",""):
            with self.assertRaisesRegex(FreshCoreError,"VAULT_KEY"):
                seal_key(READ_KEY)
            state=connection_state(self.db,self.project_id)
            self.assertFalse(state["vault_ready"])


if __name__=="__main__":
    unittest.main()
