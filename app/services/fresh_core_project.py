"""Per-project Fresh Core read-only state; no schema migration required.

Only project owner/manager can connect or disconnect in app/main.py. This
module never exposes the stored encrypted key in template data or AI context.
"""
from __future__ import annotations

import json
from sqlalchemy import select

from ..models import ProjectMemory, ProjectEvent
from ..config import settings
from .fresh_core_reader import (
    CREDENTIAL_KIND, SNAPSHOT_KIND, FreshCoreReader, FreshCoreError,
    seal_key, seal_secret, unseal_key, vault_ready,
)
from .fresh_core_manifest import FreshCoreManifestReader, verify_write_access

from .fresh_core_audit import compare_snapshots

AUDIT_KIND = "fresh_core_last_diff"
HISTORY_KIND = "fresh_core_read_history"
HISTORY_LIMIT = 10
MANIFEST_KIND = "fresh_core_manifest_credential"
WRITE_KIND = "fresh_core_write_credential"
WRITE_STATUS_KIND = "fresh_core_write_status"

def _memory(db, project_id: int, kind: str):
    return db.scalar(select(ProjectMemory).where(
        ProjectMemory.project_id == project_id, ProjectMemory.kind == kind
    ).order_by(ProjectMemory.id.desc()))


def _write_status_for_ui(row) -> dict:
    if not row or not row.verified:
        return {}
    try:
        data = json.loads(row.content)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def connection_state(db, project_id: int) -> dict:
    """Fresh Core state from verified persistence, not a claimed install."""
    credential = _memory(db, project_id, CREDENTIAL_KIND)
    manifest_credential = _memory(db, project_id, MANIFEST_KIND)
    write_credential = _memory(db, project_id, WRITE_KIND)
    write_status = _memory(db, project_id, WRITE_STATUS_KIND)
    snapshot_row = _memory(db, project_id, SNAPSHOT_KIND)
    snapshot = {}
    if snapshot_row and snapshot_row.verified:
        try:
            snapshot = json.loads(snapshot_row.content)
            if not isinstance(snapshot, dict) or snapshot.get("schema") != "karel.fresh-core.readonly.v1":
                snapshot = {}
        except (ValueError, TypeError):
            snapshot = {}
    audit_row = _memory(db, project_id, AUDIT_KIND)
    audit = {}
    if audit_row and audit_row.verified:
        try:
            audit = json.loads(audit_row.content)
            if not isinstance(audit, dict) or audit.get("site_url") != snapshot.get("site_url"):
                audit = {}
        except (ValueError, TypeError):
            audit = {}
    connected = bool(credential or manifest_credential)
    if not connected:
        status = "unlinked"
    elif snapshot:
        status = "synced" if vault_ready() else "key_unavailable"
    else:
        status = "pending"
    return {
        "kind": status,
        "label": {
            "unlinked": "Nepřipojeno", "synced": "Načteno z Fresh Core",
            "key_unavailable": "Chybí dešifrovací klíč",
            "pending": "Čeká na první ověření",
        }[status],
        "has_key": connected,
        "read_mode": "manifest" if manifest_credential else "rest" if credential else "none",
        "has_manifest": bool(manifest_credential),
        "write_verified": bool(write_credential and write_status and write_status.verified and vault_ready()),
        "write_status": _write_status_for_ui(write_status),
        "last_synced_at": snapshot.get("fetched_at"),
        "snapshot": snapshot,
        "audit": audit,
        "vault_ready": vault_ready(),
        "hosts_ready": bool(str(getattr(settings, "fresh_core_allowed_hosts", "") or "").strip()),
    }


def _upsert(db, project_id: int, kind: str, title: str, value: str, *, verified: bool):
    row = _memory(db, project_id, kind)
    if row:
        row.title = title
        row.content = value
        row.verified = verified
    else:
        db.add(ProjectMemory(
            project_id=project_id, kind=kind, title=title,
            content=value, verified=verified,
        ))


def _store_snapshot(db, project_id: int, actor_id: int, snapshot: dict):
    previous = _memory(db, project_id, SNAPSHOT_KIND)
    before = None
    if previous and previous.verified:
        try:
            candidate = json.loads(previous.content)
            if isinstance(candidate, dict) and candidate.get("schema") == "karel.fresh-core.readonly.v1":
                before = candidate
        except (ValueError, TypeError):
            pass
    audit = compare_snapshots(before, snapshot)
    # Only a completed handshake reaches here. Preserve the last verified
    # inventory on failed requests, and preserve the previous different state.
    if before and audit["change_count"]:
        db.add(ProjectMemory(project_id=project_id, kind=HISTORY_KIND,
                             title="Fresh Core – předchozí ověřený stav",
                             content=json.dumps(before, ensure_ascii=False),
                             verified=True))
        db.flush()
        old_rows = db.scalars(select(ProjectMemory).where(
            ProjectMemory.project_id == project_id,
            ProjectMemory.kind == HISTORY_KIND,
        ).order_by(ProjectMemory.id.desc()).offset(HISTORY_LIMIT)).all()
        for row in old_rows:
            db.delete(row)
    _upsert(db, project_id, AUDIT_KIND,
            "Fresh Core – změny proti předchozímu ověření",
            json.dumps(audit, ensure_ascii=False), verified=True)
    _upsert(db, project_id, SNAPSHOT_KIND,
            "Fresh Core – časově označená bezpečná čtecí data",
            json.dumps(snapshot, ensure_ascii=False), verified=True)
    db.add(ProjectEvent(
        project_id=project_id, user_id=actor_id,
        event_type="fresh_core_readonly_sync",
        detail="Fresh Core READ-only snapshot: " + str(snapshot.get("fetched_at", ""))[:50],
    ))


def connect_readonly(db, project_id: int, actor_id: int, site: str, new_key: str,
                     *, reader_factory=FreshCoreReader) -> dict:
    """Probe first; replace existing key ONLY on complete success."""
    # Seal before making any outbound request; fail closed on missing vault.
    encrypted = seal_key(new_key)
    with reader_factory(site, new_key) as reader:
        snapshot = reader.read_snapshot()
    old_manifest = _memory(db, project_id, MANIFEST_KIND)
    if old_manifest:
        db.delete(old_manifest)
    _upsert(db, project_id, CREDENTIAL_KIND,
            "Fresh Core Access Key (šifrováno; pouze pro čtení)",
            encrypted, verified=False)
    _store_snapshot(db, project_id, actor_id, snapshot)
    db.commit()
    return snapshot


def refresh_readonly(db, project_id: int, actor_id: int, site: str,
                     *, reader_factory=FreshCoreReader) -> dict:
    row = _memory(db, project_id, CREDENTIAL_KIND)
    if not row:
        raise FreshCoreError("Projekt nemá uložený čtecí Access Key.")
    read_key = unseal_key(row.content)
    with reader_factory(site, read_key) as reader:
        snapshot = reader.read_snapshot()
    _store_snapshot(db, project_id, actor_id, snapshot)
    db.commit()
    return snapshot


def connect_manifest(db, project_id: int, actor_id: int, manifest_url: str,
                     site: str | None = None,
                     *, reader_factory=FreshCoreManifestReader) -> dict:
    """Verify tokenized Fresh Core manifest first, then store only ciphertext."""
    encrypted = seal_secret(manifest_url, limit=1800)
    with reader_factory(manifest_url, site) as reader:
        snapshot = reader.read_snapshot()
    existing_url = _memory(db, project_id, "wordpress_site_url")
    if existing_url and existing_url.content:
        from .project_journeys import validate_site_url
        from urllib.parse import urlsplit
        existing_host = urlsplit(validate_site_url(existing_url.content)).hostname
        actual_host = urlsplit(snapshot["site_url"]).hostname
        if existing_host.lower().removeprefix("www.") != actual_host.lower().removeprefix("www."):
            raise FreshCoreError(
                "Manifest patří jinému webu než uložená adresa. Nejprve uprav adresu projektu."
            )
    _upsert(db, project_id, "wordpress_site_url", "Ověřená adresa WordPress webu",
            snapshot["site_url"], verified=True)
    old_rest = _memory(db, project_id, CREDENTIAL_KIND)
    if old_rest:
        db.delete(old_rest)
    _upsert(db, project_id, MANIFEST_KIND,
            "Fresh Core manifest URL (šifrovaná; neveřejná)",
            encrypted, verified=False)
    _store_snapshot(db, project_id, actor_id, snapshot)
    db.commit()
    return snapshot


def refresh_connected(db, project_id: int, actor_id: int, site: str,
                      *, manifest_reader_factory=FreshCoreManifestReader,
                      rest_reader_factory=FreshCoreReader) -> dict:
    if _memory(db, project_id, MANIFEST_KIND):
        row = _memory(db, project_id, MANIFEST_KIND)
        url = unseal_key(row.content)
        with manifest_reader_factory(url, site) as reader:
            snapshot = reader.read_snapshot()
        _store_snapshot(db, project_id, actor_id, snapshot)
        db.commit()
        return snapshot
    return refresh_readonly(db, project_id, actor_id, site,
                            reader_factory=rest_reader_factory)


def connect_write_key(db, project_id: int, actor_id: int, site: str,
                      write_key: str, *, verifier=verify_write_access) -> dict:
    """Verify permissions with GET /write/ping. Never execute any WRITE."""
    state = connection_state(db, project_id)
    if not state.get("snapshot") or state["snapshot"].get("site_url") != site:
        raise FreshCoreError("Nejdřív ověř čtecí propojení správného webu.")
    encrypted = seal_key(write_key)
    status = verifier(site, write_key)
    _upsert(db, project_id, WRITE_KIND,
            "Fresh Core Write Key (šifrovaný; zatím bez publikace)",
            encrypted, verified=False)
    _upsert(db, project_id, WRITE_STATUS_KIND,
            "Fresh Core – ověřené zapisovací oprávnění",
            json.dumps(status, ensure_ascii=False), verified=True)
    db.add(ProjectEvent(project_id=project_id, user_id=actor_id,
                        event_type="fresh_core_write_ping_verified",
                        detail="GET write/ping ověřen; žádná změna webu nebyla odeslána."))
    db.commit()
    return status


def disconnect_readonly(db, project_id: int, actor_id: int) -> None:
    """Local revoke; users must still revoke the credential in WordPress."""
    for kind in (CREDENTIAL_KIND, MANIFEST_KIND, WRITE_KIND, WRITE_STATUS_KIND,
                 SNAPSHOT_KIND, AUDIT_KIND, HISTORY_KIND):
        for row in db.scalars(select(ProjectMemory).where(
                ProjectMemory.project_id == project_id, ProjectMemory.kind == kind)).all():
            db.delete(row)
    db.add(ProjectEvent(
        project_id=project_id, user_id=actor_id,
        event_type="fresh_core_disconnected",
        detail="Vazba a její uložená čtecí data odstraněna z Karla; revokaci klíče je nutné provést také ve WordPressu.",
    ))
    db.commit()
