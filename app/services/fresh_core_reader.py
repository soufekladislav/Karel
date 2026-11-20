"""Read-only Fresh Core v0.7.8 connector.

The credential is accepted via an authenticated HTTPS form, encrypted in the
existing project memory table, and sent only as X-Fresh-Core-Key over HTTPS.
Never persist raw key, public URL key, full WordPress snapshot or write key.
No redirects, private network targets or unapproved hosts.
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from ..config import settings
from .project_journeys import validate_site_url
from .source_resolver import _require_trusted_host, _validate_public_url

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
CREDENTIAL_KIND = "fresh_core_read_credential"
SNAPSHOT_KIND = "fresh_core_snapshot"
MAX_PLUGINS = 80
MAX_POST_TYPES = 35
MAX_TAXONOMIES = 30


class FreshCoreError(ValueError):
    """Safe to show to users; must not contain credentials or server URLs."""


def vault_ready() -> bool:
    """Explicit stable key, separate from session APP_SECRET and rotation."""
    raw = str(getattr(settings, "fresh_core_vault_key", "") or "").strip()
    if len(raw) != 44:
        return False
    try:
        return len(base64.urlsafe_b64decode(raw.encode("ascii"))) == 32
    except (UnicodeError, ValueError):
        return False


def _fernet():
    if not vault_ready():
        raise FreshCoreError(
            "Správce musí na serveru nastavit trvalý FRESH_CORE_VAULT_KEY "
            "a bezpečně ho zálohovat. Dokud chybí, přístupové klíče neukládáme."
        )
    from cryptography.fernet import Fernet
    return Fernet(settings.fresh_core_vault_key.strip().encode("ascii"))


def seal_key(read_key: str) -> str:
    value = (read_key or "").strip()
    if not value or len(value) > 300 or any(ord(c) < 33 or ord(c) > 126 for c in value):
        raise FreshCoreError("Zadej platný Fresh Core REST klíč (Access Key).")
    return _fernet().encrypt(value.encode("ascii")).decode("ascii")


def unseal_key(encrypted: str) -> str:
    from cryptography.fernet import InvalidToken
    try:
        return _fernet().decrypt((encrypted or "").encode("ascii")).decode("ascii")
    except (InvalidToken, ValueError, UnicodeError) as exc:
        raise FreshCoreError(
            "Uložený klíč nelze bezpečně přečíst. Ověř konfiguraci vaultu "
            "nebo obnov propojení Fresh Core."
        ) from exc


def validate_fresh_core_site(url: str) -> str:
    try:
        site = validate_site_url(url)
        if not site or not site.startswith("https://"):
            raise FreshCoreError("Fresh Core vyžaduje veřejný web přes HTTPS.")
        parsed = urlsplit(site)
        if parsed.path not in ("", "/"):
            raise FreshCoreError(
                "Pro první propojení zadej adresu WordPressu bez cesty, "
                "například https://mujweb.cz."
            )
        _require_trusted_host(
            site, getattr(settings, "fresh_core_allowed_hosts", ""),
            "FRESH_CORE_ALLOWED_HOSTS",
        )
        _validate_public_url(site)
        return site.rstrip("/")
    except FreshCoreError:
        raise
    except (ValueError, OSError) as exc:
        # Never re-emit a submitted URL, token, or DNS resolver details.
        raise FreshCoreError(
            "Web nemá bezpečně povolenou veřejnou HTTPS adresu. "
            "Ověř URL a seznam FRESH_CORE_ALLOWED_HOSTS u správce."
        ) from exc


def _check_identity(site: str, payload: dict) -> None:
    manifest = payload.get("manifest") or {}
    declared = (manifest.get("site") or {}).get("url") if isinstance(manifest, dict) else None
    if not isinstance(declared, str):
        raise FreshCoreError("Fresh Core nevrátil potvrzenou identitu WordPress webu.")
    try:
        reported = urlsplit(validate_site_url(declared))
        intended = urlsplit(site)
        if reported.hostname.lower().removeprefix("www.") != intended.hostname.lower().removeprefix("www."):
            raise FreshCoreError(
                "Fresh Core vrátil údaje jiného webu. Spojení neukládáme."
            )
    except (AttributeError, ValueError) as exc:
        if isinstance(exc, FreshCoreError):
            raise
        raise FreshCoreError("Identita WordPress webu nebyla ověřena.") from exc


def _safe_text(value, limit=130) -> str:
    return str(value or "").strip()[:limit]


def _menu_inventory(menus: list) -> list[dict]:
    """Retain only structural menu fingerprints; never persist link targets."""
    result = []
    for m in menus[:60]:
        if not isinstance(m, dict):
            continue
        items = m.get("items") or []
        if not isinstance(items, list):
            continue
        safe_items = [
            {"id": i.get("id"), "parent": i.get("parent"), "title": _safe_text(i.get("title"), 100),
             "object_id": i.get("object_id"), "order": i.get("order")}
            for i in items[:200] if isinstance(i, dict)
        ]
        fingerprint = hashlib.sha256(json.dumps(
            safe_items, ensure_ascii=False, sort_keys=True,
        ).encode("utf-8")).hexdigest()[:20]
        result.append({"id": m.get("id"), "name": _safe_text(m.get("name"), 90),
                       "item_count": len(items), "fingerprint": fingerprint,
                       "partial": len(items) > 200})
    return result


def _template_inventory(data: dict) -> tuple[list[dict], bool]:
    templates = data.get("elementor_templates") or []
    if not isinstance(templates, list):
        return [], True
    result = []
    for t in templates[:100]:
        if not isinstance(t, dict):
            continue
        result.append({"id": t.get("id"), "title": _safe_text(t.get("title"), 120),
                       "document_type": _safe_text(t.get("document_type"), 80),
                       "post_type": _safe_text(t.get("post_type"), 80)})
    return result, len(templates) > 100


def _category_inventory(data: dict) -> dict:
    categories = data.get("categories") or {}
    if not isinstance(categories, dict):
        return {}
    result = {}
    for key, value in list(categories.items())[:12]:
        if isinstance(value, dict):
            result[_safe_text(key, 64)] = {
                "count": max(0, int(value.get("count") or 0)),
                "partial": bool(value.get("truncated")),
            }
    return result


def sanitize_snapshot(data: dict, site: str, plugin_version: str) -> dict:
    """Only a small whitelisted site/technical summary enters Karel's DB/AI context."""
    if not isinstance(data, dict) or not isinstance(data.get("manifest"), dict):
        raise FreshCoreError("Fresh Core nevrátil čitelný snapshot dat.")
    _check_identity(site, data)
    m = data["manifest"]
    site_data, runtime, theme = (m.get("site") or {}), (m.get("runtime") or {}), (m.get("theme") or {})
    plugins = m.get("active_plugins") or []
    post_types = data.get("post_types") or []
    taxonomies = data.get("taxonomies") or []
    menus = data.get("menus") or []
    elementor = data.get("elementor_overview") or {}
    modules = data.get("fresh_modules") or {}
    templates, templates_partial = _template_inventory(data)
    if not isinstance(modules, dict):
        modules = {}
    if not all(isinstance(v, dict) for v in (site_data, runtime, theme, elementor)):
        raise FreshCoreError("Fresh Core vrátil neočekávaná data webu.")
    if not all(isinstance(v, list) for v in (plugins, post_types, taxonomies, menus)):
        raise FreshCoreError("Fresh Core vrátil neočekávané seznamy webu.")
    return {
        "schema": "karel.fresh-core.readonly.v1",
        "source": "Fresh Core REST /snapshot (READ only)",
        "site_url": site,
        "site_name": _safe_text(site_data.get("name"), 180),
        "site_language": _safe_text(site_data.get("language"), 30),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "plugin_version": _safe_text(plugin_version, 24),
        "manifest_generated_at_gmt": _safe_text(data.get("generated_at_gmt"), 48),
        "wordpress_version": _safe_text(runtime.get("wordpress"), 30),
        "php_version": _safe_text(runtime.get("php"), 30),
        "woocommerce_version": _safe_text(runtime.get("woocommerce"), 30),
        "elementor_version": _safe_text(runtime.get("elementor"), 30),
        "theme": {"name": _safe_text(theme.get("name")), "version": _safe_text(theme.get("version"), 30),
                  "stylesheet": _safe_text(theme.get("stylesheet"), 100)},
        "active_plugin_count": len(plugins),
        "active_plugins": [
            {"file": _safe_text(p.get("file"), 160),
             "name": _safe_text(p.get("name")), "version": _safe_text(p.get("version"), 40)}
            for p in plugins[:MAX_PLUGINS] if isinstance(p, dict)
        ],
        "post_types": [
            {"name": _safe_text(p.get("name"), 60), "label": _safe_text(p.get("label"), 110),
             "counts": {str(k)[:32]: max(0, int(v)) for k, v in (p.get("counts") or {}).items()
                        if isinstance(v, (int, float)) and not isinstance(v, bool)}}
            for p in post_types[:MAX_POST_TYPES] if isinstance(p, dict)
        ],
        "taxonomies": [
            {"name": _safe_text(t.get("name"), 80), "term_count": max(0, int(t.get("term_count") or 0))}
            for t in taxonomies[:MAX_TAXONOMIES] if isinstance(t, dict)
        ],
        "menu_count": len(menus),
        "menu_index": _menu_inventory(menus),
        "elementor_document_count": int(elementor.get("document_count") or 0),
        "elementor_templates": templates,
        "fresh_modules": {
            _safe_text(k, 50): {"detected": bool(v.get("detected")),
                                "version": _safe_text(v.get("version"), 30)}
            for k, v in list(modules.items())[:15] if isinstance(v, dict)
        },
        "category_inventory": _category_inventory(data),
        "coverage": {
            "menus_partial": len(menus) > 60 or any(
                bool(m.get("partial")) for m in _menu_inventory(menus)),
            "templates_partial": templates_partial,
            "plugins_partial": len(plugins) > MAX_PLUGINS,
            "post_types_partial": len(post_types) > MAX_POST_TYPES,
            "taxonomies_partial": len(taxonomies) > MAX_TAXONOMIES,
            "content_items": "not_read",
            "runtime_errors": "not_available",
        },
        "truncated": bool(len(plugins) > MAX_PLUGINS or len(post_types) > MAX_POST_TYPES
                          or len(taxonomies) > MAX_TAXONOMIES),
    }


class FreshCoreReader:
    def __init__(self, site_url: str, read_key: str, client: httpx.Client | None = None):
        self.site = validate_fresh_core_site(site_url)
        if not read_key or len(read_key) > 300 or "\n" in read_key or "\r" in read_key:
            raise FreshCoreError("Chybí platný Fresh Core Access Key.")
        self.read_key = read_key
        self.client = client or httpx.Client(timeout=15, follow_redirects=False, trust_env=False)
        self.owns_client = client is None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if self.owns_client:
            self.client.close()

    def _get(self, endpoint: str) -> dict:
        # Endpoint is a static constant; no user-provided HTTP path.
        if endpoint not in ("ping", "snapshot"):
            raise FreshCoreError("Nepovolený Fresh Core endpoint.")
        # Check address again before each independent HTTP request.
        validate_fresh_core_site(self.site)
        target = self.site + "/wp-json/fresh-core/v1/" + endpoint
        try:
            with self.client.stream(
                "GET", target,
                headers={"X-Fresh-Core-Key": self.read_key,
                         "Accept": "application/json",
                         "User-Agent": "Fresh-Karel-ReadOnly/1.0"},
                follow_redirects=False, timeout=15,
            ) as response:
                if response.status_code in (401, 403):
                    raise FreshCoreError(
                        "Fresh Core odmítl Access Key. Zkontroluj, zda je čtecí konektor zapnutý a klíč je správný."
                    )
                if response.status_code in (301, 302, 303, 307, 308):
                    raise FreshCoreError(
                        "WordPress přesměrovává REST API. Zadej přesnou finální HTTPS doménu."
                    )
                if response.status_code >= 400:
                    raise FreshCoreError(
                        "Fresh Core REST API neodpovídá úspěšně (HTTP " + str(response.status_code) + ")."
                    )
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise FreshCoreError(
                            "Fresh Core snapshot je příliš velký pro bezpečné načtení (limit 2 MB)."
                        )
                if "json" not in (response.headers.get("content-type") or "").lower():
                    raise FreshCoreError("Fresh Core nevrátil JSON odpověď.")
        except FreshCoreError:
            raise
        except (httpx.HTTPError, OSError) as exc:
            raise FreshCoreError(
                "WordPress REST API není dostupné. Ověř, že Fresh Core běží a web má veřejné HTTPS."
            ) from exc
        try:
            wrapper = json.loads(raw)
            if wrapper.get("success") is not True or not isinstance(wrapper.get("data"), dict):
                raise ValueError("Unsuccessful REST payload")
            return wrapper["data"]
        except (ValueError, TypeError, AttributeError) as exc:
            raise FreshCoreError("Fresh Core vrátil neplatnou nebo neúspěšnou REST odpověď.") from exc

    def read_snapshot(self) -> dict:
        ping = self._get("ping")
        if ping.get("ok") is not True or not ping.get("version"):
            raise FreshCoreError("Fresh Core nepotvrdil verzi ani funkční čtecí API.")
        snapshot = self._get("snapshot")
        return sanitize_snapshot(snapshot, self.site, str(ping["version"]))
