"""Regression checks for read-only Fresh Core change analysis."""
import unittest

from app.services.fresh_core_audit import compare_snapshots


def sample():
    return {
        "schema": "karel.fresh-core.readonly.v1",
        "site_url": "https://shop.example.cz",
        "fetched_at": "2026-11-19T17:00:00Z",
        "wordpress_version": "6.9",
        "plugin_version": "0.7.8",
        "active_plugins": [
            {"file": "fresh-core/fresh-core.php", "name": "Fresh Core", "version": "0.7.8"},
            {"file": "example/plugin.php", "name": "Example", "version": "1.0"},
        ],
        "menu_count": 1,
        "menu_index": [{"id": 11, "name": "Hlavní", "item_count": 2, "fingerprint": "abc"}],
        "elementor_document_count": 2,
        "elementor_templates": [{"id": 7, "title": "Header", "document_type": "header"}],
        "post_types": [{"name": "page", "counts": {"publish": 4}}],
        "coverage": {"plugins_partial": False, "menus_partial": False, "templates_partial": False},
    }


class FreshCoreAuditTests(unittest.TestCase):
    def test_first_read_is_baseline_not_success_claim(self):
        audit = compare_snapshots(None, sample())
        self.assertEqual(audit["status"], "baseline")
        self.assertEqual(audit["change_count"], 0)
        self.assertIn("JavaScript", " ".join(audit["limitations"]))

    def test_detects_plugin_page_and_menu_change(self):
        old = sample()
        new = sample()
        new["fetched_at"] = "2026-11-19T19:00:00Z"
        new["active_plugins"][1]["version"] = "1.1"
        new["post_types"][0]["counts"]["publish"] = 5
        new["menu_index"][0]["fingerprint"] = "xyz"
        audit = compare_snapshots(old, new)
        self.assertEqual(audit["status"], "changed")
        self.assertTrue(any(c["area"] == "plugins" for c in audit["changes"]))
        self.assertTrue(any(c["area"] == "post_types" for c in audit["changes"]))
        self.assertTrue(any(c["area"] == "menus" for c in audit["changes"]))

    def test_partial_plugins_never_claim_removed(self):
        old = sample()
        new = sample()
        new["active_plugins"] = new["active_plugins"][:1]
        new["coverage"]["plugins_partial"] = True
        audit = compare_snapshots(old, new)
        self.assertEqual(audit["status"], "partial")
        self.assertFalse(any(c["severity"] == "warning" and c["area"] == "plugins"
                             for c in audit["changes"]))

    def test_old_legacy_snapshot_lacks_menu_evidence(self):
        old = sample()
        old.pop("menu_index")
        new = sample()
        new["menu_index"][0]["fingerprint"] = "xyz"
        self.assertFalse(any(c["area"] == "menus"
                             for c in compare_snapshots(old, new)["changes"]))

    def test_reject_foreign_project(self):
        new = sample()
        new["site_url"] = "https://wrong.example.cz"
        with self.assertRaises(ValueError):
            compare_snapshots(sample(), new)

    def test_ignore_timestamp_only(self):
        old, new = sample(), sample()
        new["fetched_at"] = "2026-11-19T20:00:00Z"
        audit = compare_snapshots(old, new)
        self.assertEqual(audit["status"], "unchanged")
        self.assertEqual(audit["change_count"], 0)


if __name__ == "__main__":
    unittest.main()
