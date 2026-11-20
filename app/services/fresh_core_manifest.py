"""Existing Fresh Core 0.7.7/0.7.8 static manifest -> verified READ inventory.

Uses the tokenized manifest URL exactly like Boban, but stores it encrypted
and never exposes it in the template, chat context, diagnostics or logs.
All network targets must stay inside the *same* HTTPS token directory.
No WordPress writes, no generic source URL fetch, no customer order contents.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from .fresh_core_reader import (
    FreshCoreError, sanitize_snapshot, validate_fresh_core_site,
)
from .source_resolver import _validate_public_url

MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_MANIFEST_FILES = 5000
_TOKEN_DIRECTORY = re.compile(
    r"^(/(?:[A-Za-z0-9._-]+/)*wp-content/uploads/fresh-core-connector/"
    r"[A-Za-z0-9_-]{40,110}/)manifest\.json$"
)
_READ_FILES = (
    "structure.json", "elementor.json", "fresh-modules.json",
    "diagnostics.json", "plugins/registry.json",
)


def checked_manifest_url(raw_url: str, site_url: str | None = None) -> tuple[str, str]:
    candidate = str(raw_url or "").strip()
    if len(candidate) > 1700 or any(ord(ch) < 33 for ch in candidate):
        raise FreshCoreError("Manifest URL musí být platná úplná HTTPS adresa.")
    parsed = urlsplit(candidate)
    if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment or (
        parsed.port not in (None, 443) or parsed.username or parsed.password
    ):
        raise FreshCoreError("Manifest URL musí být HTTPS bez parametrů a přihlašovacích údajů.")
    if any(part in (".", "..") for part in parsed.path.split("/")):
        raise FreshCoreError("Neplatná cesta manifestu.")
    found = _TOKEN_DIRECTORY.fullmatch(parsed.path)
    if not found:
        raise FreshCoreError("Použij URL manifest.json z Fresh Core → statický konektor.")
    site = validate_fresh_core_site(site_url or ("https://" + parsed.hostname))
    if parsed.hostname.lower().removeprefix("www.") != urlsplit(site).hostname.lower().removeprefix("www."):
        raise FreshCoreError("Manifest nepatří k adrese tohoto WordPress webu.")
    return candidate, found.group(1)


def _read_json(client: httpx.Client, url: str, expected_host: str,
               *, size: int | None = None, digest: str | None = None) -> dict:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != expected_host or parsed.query or parsed.fragment:
        raise FreshCoreError("Soubor manifestu odkazuje mimo ověřenou HTTPS doménu.")
    try:
        _validate_public_url(url)
        with client.stream("GET", url, follow_redirects=False, timeout=15,
                           headers={"Accept": "application/json",
                                    "User-Agent": "Fresh-Karel-Manifest/1.0"}) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                raise FreshCoreError("Manifest přesměrovává na jinou adresu.")
            if response.status_code != 200:
                raise FreshCoreError(
                    "Fresh Core manifest není dostupný (HTTP " + str(response.status_code) + ")."
                )
            if "json" not in (response.headers.get("content-type") or "").lower():
                raise FreshCoreError("Fresh Core nevrátil JSON.")
            raw = bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > MAX_JSON_BYTES:
                    raise FreshCoreError("Soubor Fresh Core je nad povoleným limitem 2 MB.")
    except FreshCoreError:
        raise
    except (httpx.HTTPError, OSError, ValueError) as exc:
        raise FreshCoreError("Soubor Fresh Core se nepodařilo bezpečně načíst.") from exc
    if size is not None and len(raw) != size:
        raise FreshCoreError("Soubor exportu má jinou délku než uvádí manifest.")
    if digest and hashlib.sha256(raw).hexdigest() != digest.lower():
        raise FreshCoreError("Kontrolní součet exportu Fresh Core nesouhlasí.")
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise FreshCoreError("Soubor Fresh Core neobsahuje platný JSON.") from exc
    if not isinstance(value, dict):
        raise FreshCoreError("Fresh Core export má neočekávanou strukturu.")
    return value


def _safe_diagnostics(data: dict) -> dict:
    output = {}
    for tax, stats in (data.get("taxonomies") or {}).items():
        if isinstance(stats, dict) and len(output) < 12:
            output[str(tax)[:60]] = {
                "total": int(stats.get("total") or 0),
                "empty_count": int(stats.get("empty_count") or 0),
                "duplicate_group_count": len(stats.get("duplicate_name_groups") or []),
            }
    return output


class FreshCoreManifestReader:
    def __init__(self, manifest_url: str, site_url: str | None = None,
                 client: httpx.Client | None = None):
        self.url, self.prefix = checked_manifest_url(manifest_url, site_url)
        self.site = validate_fresh_core_site(site_url or (
            "https://" + urlsplit(self.url).hostname))
        self.host = urlsplit(self.url).hostname
        self.client = client or httpx.Client(
            timeout=15, follow_redirects=False, trust_env=False)
        self.owns_client = client is None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        if self.owns_client:
            self.client.close()

    def _get(self, path: str, *, size: int | None = None,
             digest: str | None = None) -> dict:
        if not path.startswith(self.prefix):
            raise FreshCoreError("Neplatná cesta exportu.")
        url = "https://" + self.host + path
        return _read_json(self.client, url, self.host, size=size, digest=digest)

    def read_snapshot(self) -> dict:
        manifest = _read_json(self.client, self.url, self.host)
        site = manifest.get("site") or {}
        if not isinstance(site, dict) or not isinstance(site.get("url"), str):
            raise FreshCoreError("Manifest neidentifikuje WordPress web.")
        actual = validate_fresh_core_site(site["url"])
        if urlsplit(actual).hostname.lower().removeprefix("www.") != (
                urlsplit(self.site).hostname.lower().removeprefix("www.")):
            raise FreshCoreError("Manifest patří jinému WordPress webu.")

        version = str(manifest.get("fresh_core_version") or "").strip()
        files = manifest.get("files")
        if not version or not isinstance(files, list) or not files or len(files) > MAX_MANIFEST_FILES:
            raise FreshCoreError("Manifest Fresh Core není úplný.")
        batch = manifest.get("batch_delivery")
        if batch is not None:
            if not isinstance(batch, dict) or batch.get("status") != "complete" or (
                batch.get("is_last") is not True or
                int(batch.get("total_parts") or 0) <= 0 or
                int(batch.get("completed_parts") or 0) != int(batch["total_parts"])
            ):
                raise FreshCoreError("Dávkový manifest Fresh Core ještě není dokončen.")

        registry = {}
        hashes = {}
        for row in files:
            if not isinstance(row, dict):
                raise FreshCoreError("Neplatná položka exportu Fresh Core.")
            name, uri = row.get("file"), row.get("url")
            size, digest = row.get("bytes"), row.get("sha256")
            if not isinstance(name, str) or not isinstance(uri, str) or (
                not isinstance(size, int) or not 0 <= size <= 150 * 1024 * 1024
                or not isinstance(digest, str) or
                not re.fullmatch(r"[0-9a-fA-F]{64}", digest)
            ):
                raise FreshCoreError("Manifest obsahuje neověřitelnou položku.")
            parsed = urlsplit(uri)
            if (parsed.scheme != "https" or parsed.hostname != self.host or
                parsed.query or parsed.fragment or
                not parsed.path.startswith(self.prefix)):
                raise FreshCoreError("Manifest odkazuje mimo vlastní bezpečnou složku.")
            if name in registry:
                raise FreshCoreError("Manifest obsahuje duplicitní soubor.")
            registry[name] = (parsed.path, size, digest)
            if name in _READ_FILES or name in ("seo/index.json", "elementor/index.json"):
                hashes[name] = digest.lower()

        if "structure.json" not in registry:
            raise FreshCoreError("Manifest nemá povinný soubor structure.json.")
        if batch is not None:
            snapshot_id = str(manifest.get("snapshot_id") or "")
            if not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", snapshot_id):
                raise FreshCoreError("Dávkový manifest nemá platné ID snímku.")
            for name, (path, _, _) in registry.items():
                if not path.startswith(self.prefix + "snapshots/" + snapshot_id + "/"):
                    raise FreshCoreError("Dávkový manifest míchá různé snímky.")

        fetched = {}
        for name in _READ_FILES:
            if name in registry:
                path, size, digest = registry[name]
                if size > MAX_JSON_BYTES:
                    # Explicitly signal partial coverage instead of claiming a
                    # full inventory when the source exceeds safe size limits.
                    continue
                fetched[name] = self._get(path, size=size, digest=digest)
        if "structure.json" not in fetched:
            raise FreshCoreError("Struktura webu je nad limitem 2 MB; export nebyl načten.")

        structure = fetched["structure.json"]
        structure["elementor_overview"] = (fetched.get("elementor.json") or {}).get("overview") or {}
        structure["elementor_templates"] = (fetched.get("elementor.json") or {}).get("templates") or []
        structure["fresh_modules"] = (fetched.get("fresh-modules.json") or {}).get("modules") or {}
        output = sanitize_snapshot(structure, actual, version)
        output["source"] = "Fresh Core static manifest (READ only)"
        stamp = str(manifest.get("generated_at_gmt") or "")[:48]
        output["manifest_generated_at_gmt"] = stamp
        try:
            generated = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if generated.tzinfo is None:
                generated = generated.replace(tzinfo=timezone.utc)
            age_seconds = (datetime.now(timezone.utc) - generated).total_seconds()
            stale = age_seconds > 48 * 3600 or age_seconds < -300
        except (ValueError, OverflowError):
            stale = True
        output["snapshot_id"] = str(manifest.get("snapshot_id") or "")[:65]
        output["manifest_batch_complete"] = batch is None or batch.get("status") == "complete"
        output["manifest_legacy"] = batch is None
        output["manifest_file_count"] = len(files)
        output["manifest_hashes"] = hashes
        output["diagnostics"] = _safe_diagnostics(fetched.get("diagnostics.json") or {})
        output["coverage"]["manifest_stale"] = stale
        output["coverage"]["templates_partial"] = (
            output["coverage"].get("templates_partial") or "elementor.json" not in fetched
        )
        output["coverage"]["fresh_modules_partial"] = "fresh-modules.json" not in fetched
        output["coverage"]["manifest_file_count"] = len(files)
        output["coverage"]["verified_file_count"] = len(fetched)
        output["coverage"]["diagnostics_read"] = "diagnostics.json" in fetched
        output["coverage"]["registry_read"] = "plugins/registry.json" in fetched
        output["fetched_at"] = datetime.now(timezone.utc).isoformat()
        return output


def verify_write_access(site_url: str, write_key: str,
                        client: httpx.Client | None = None) -> dict:
    """GET-only verification; never send a mutation to WordPress."""
    site = validate_fresh_core_site(site_url)
    key = str(write_key or "").strip()
    if len(key) < 32 or len(key) > 300 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise FreshCoreError("Zadej platný Fresh Core Write Key.")
    own = client is None
    session = client or httpx.Client(timeout=15, follow_redirects=False, trust_env=False)
    try:
        endpoint = site + "/wp-json/fresh-core/v1/write/ping"
        _validate_public_url(endpoint)
        with session.stream(
            "GET", endpoint, follow_redirects=False, timeout=15,
            headers={"X-Fresh-Core-Write-Key": key,
                     "Accept": "application/json", "User-Agent": "Fresh-Karel-WritePing/1.0"},
        ) as resp:
            if resp.status_code != 200:
                raise FreshCoreError(
                    "Fresh Core Write Key není ověřený (HTTP " + str(resp.status_code) + ")."
                )
            raw = bytearray()
            for chunk in resp.iter_bytes():
                raw.extend(chunk)
                if len(raw) > 65536:
                    raise FreshCoreError("Odezva Write bridge je příliš velká.")
        result = json.loads(raw)
        data = result.get("data") or {}
        if result.get("success") is not True or not data.get("ok") or (
            data.get("write_enabled") is not True
        ):
            raise FreshCoreError("Fresh Core nepotvrdil aktivní zapisovací bridge.")
        return {"checked_at": datetime.now(timezone.utc).isoformat(),
                "plugin_version": str(data.get("version") or "")[:30],
                "write_enabled": True}
    except FreshCoreError:
        raise
    except (httpx.HTTPError, OSError, ValueError, TypeError) as exc:
        raise FreshCoreError("Zápisový bridge se nepodařilo ověřit.") from exc
    finally:
        if own:
            session.close()
