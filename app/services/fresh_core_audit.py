"""Evidence-only comparison of two verified Fresh Core REST inventories.

No writes to WordPress. Structural differences are NOT proof of runtime errors.
Old alpha.33 snapshots lack newer fields; missing coverage must never be
reported as a removed plugin/menu/template.
"""
from __future__ import annotations

from datetime import datetime, timezone

MAX_CHANGES = 60


def _index(items, key):
    out = {}
    for item in items or []:
        if isinstance(item, dict):
            name = str(item.get(key) or "").strip().casefold()
            if name:
                out[name] = item
    return out


def compare_snapshots(before: dict | None, after: dict) -> dict:
    if not isinstance(after, dict) or not after.get("site_url"):
        raise ValueError("New Fresh Core snapshot is invalid.")
    if before and before.get("site_url") != after.get("site_url"):
        raise ValueError("Cannot compare different WordPress websites.")

    audit = {
        "schema": "karel.fresh-core.audit.v1",
        "site_url": after["site_url"],
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "previous_at": (before or {}).get("fetched_at"),
        "current_at": after.get("fetched_at"),
        "status": "baseline" if not before else "unchanged",
        "change_count": 0, "changes": [],
        "limitations": [
            "Strukturální rozdíl není důkaz PHP/JavaScript chyby nebo nefunkčnosti webu.",
            "Fresh Core REST snapshot neověřuje veřejné HTML, jednotlivé funkcionality ani obsah všech stránek.",
        ],
    }
    if after.get("manifest_legacy"):
        audit["limitations"].append("Statický export nemá potvrzení úplné dávky.")
    if (after.get("coverage") or {}).get("manifest_stale"):
        audit["limitations"].append(
            "Manifest je starší než 48 hodin; aktualizované webové změny v něm nemusejí být."
        )
    if not before:
        return audit

    changes = []
    partial = False

    def add(area, name, previous, current, severity="info"):
        changes.append({"area": area, "name": str(name)[:130],
                        "before": str(previous)[:150], "after": str(current)[:150],
                        "severity": severity})

    for key, label in (
        ("wordpress_version", "WordPress"),
        ("plugin_version", "Fresh Core"),
        ("php_version", "PHP"),
        ("woocommerce_version", "WooCommerce"),
        ("elementor_version", "Elementor"),
    ):
        if key in before and key in after and before[key] != after[key]:
            add("runtime", label, before[key], after[key])

    a, b = before.get("theme") or {}, after.get("theme") or {}
    for key, label in (("name", "Šablona"), ("version", "Verze šablony"),
                       ("stylesheet", "Aktivní motiv")):
        if key in a and key in b and a[key] != b[key]:
            add("theme", label, a[key], b[key])

    old_plugins = _index(before.get("active_plugins"), "name")
    new_plugins = _index(after.get("active_plugins"), "name")
    if "active_plugins" in before and "active_plugins" in after:
        for key, entry in new_plugins.items():
            if key not in old_plugins:
                add("plugins", entry.get("name"), "není ve starém snímku",
                    entry.get("version"), "info")
            elif entry.get("version") != old_plugins[key].get("version"):
                add("plugins", entry.get("name"), old_plugins[key].get("version"),
                    entry.get("version"))
        for key, entry in old_plugins.items():
            if key not in new_plugins:
                if before.get("truncated") or after.get("truncated") or (
                    (before.get("coverage") or {}).get("plugins_partial") or
                    (after.get("coverage") or {}).get("plugins_partial")
                ):
                    partial = True
                else:
                    add("plugins", entry.get("name"), entry.get("version"),
                        "není v novém snímku", "warning")

    for key, label in (
        ("post_types", "Typ obsahu"),
        ("category_inventory", "Taxonomie"),
        ("fresh_modules", "Fresh modul"),
    ):
        if key not in before or key not in after:
            continue
        old_index = (_index(before[key], "name") if isinstance(before[key], list)
                     else before[key] if isinstance(before[key], dict) else {})
        new_index = (_index(after[key], "name") if isinstance(after[key], list)
                     else after[key] if isinstance(after[key], dict) else {})
        for item_key in sorted(set(old_index) | set(new_index)):
            if item_key not in old_index or item_key not in new_index:
                add(key, item_key, "přítomen" if item_key in old_index else "chybí",
                    "přítomen" if item_key in new_index else "chybí", "warning")
            elif old_index[item_key] != new_index[item_key]:
                add(key, item_key, old_index[item_key], new_index[item_key])

    # Compare only covered inventories; absence in the old alpha snapshot
    # is UNKNOWN rather than evidence of deletion.
    for key, area, index_key, coverage_key in (
        ("menu_index", "menus", "id", "menus_partial"),
        ("elementor_templates", "elementor", "id", "templates_partial"),
    ):
        if key not in before or key not in after:
            continue
        old_partial = bool((before.get("coverage") or {}).get(coverage_key))
        new_partial = bool((after.get("coverage") or {}).get(coverage_key))
        old_map = {str(x.get(index_key)): x for x in before[key]
                   if isinstance(x, dict) and x.get(index_key) is not None}
        new_map = {str(x.get(index_key)): x for x in after[key]
                   if isinstance(x, dict) and x.get(index_key) is not None}
        for item_id in sorted(set(old_map) | set(new_map)):
            if item_id not in old_map or item_id not in new_map:
                if old_partial or new_partial:
                    partial = True
                else:
                    add(area, item_id, "přítomen" if item_id in old_map else "chybí",
                        "přítomen" if item_id in new_map else "chybí", "warning")
            elif old_map[item_id] != new_map[item_id]:
                add(area, item_id, old_map[item_id], new_map[item_id])

    if "manifest_hashes" in before and "manifest_hashes" in after:
        for filename, digest in (after["manifest_hashes"] or {}).items():
            previous = (before["manifest_hashes"] or {}).get(filename)
            if previous and previous != digest:
                add("manifest", filename, previous[:16], str(digest)[:16],
                    "info")

    if "diagnostics" in before and "diagnostics" in after:
        for taxonomy, info in (after["diagnostics"] or {}).items():
            old = (before["diagnostics"] or {}).get(taxonomy)
            if isinstance(old, dict) and old != info:
                add("diagnostics", taxonomy, old, info, "warning")

    for key, label in (
        ("menu_count", "Počet menu"),
        ("elementor_document_count", "Elementor dokumenty"),
    ):
        if key in before and key in after and before[key] != after[key]:
            add("counts", label, before[key], after[key])

    if after.get("manifest_legacy"):
        audit["limitations"].append(
            "Statický manifest nemá dávkovou značku dokončení; ověřena jen dostupná metadata a jednotlivé soubory."
        )
    if (after.get("coverage") or {}).get("manifest_stale"):
        audit["limitations"].append(
            "Statický manifest je starší než 48 hodin; aktuální nasazené změny v něm nemusí být."
        )
    audit["change_count"] = len(changes)
    audit["changes"] = changes[:MAX_CHANGES]
    if len(changes) > MAX_CHANGES:
        partial = True
        audit["limitations"].append("Výpis změn je omezen na prvních 60 položek.")
    if partial:
        audit["limitations"].append(
            "Některé seznamy jsou zkrácené; chybějící položku nelze prohlásit za smazanou."
        )
    audit["status"] = ("partial" if partial else "changed" if changes else "unchanged")
    return audit
