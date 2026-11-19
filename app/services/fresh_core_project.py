"""Per-project Fresh Core read-only state; no schema migration required.

Only project owner/manager can connect or disconnect in app/main.py. This
module never exposes the stored encrypted key in template data or AI context.
"""
from __future__ import annotations

import json
from sqlalchemy import select

from ..models import ProjectMemory, ProjectEvent
from .fresh_core_reader import (
    CREDENTIAL_KIND, SNAPSHOT_KIND, FreshCoreReader, FreshCoreError,
    seal_key, unseal_key, vault_ready,
)

def _memory(db, project_id: int, kind: str):
    return db.scalar(select(ProjectMemory).where(
        ProjectMemory.project_id == project_id, ProjectMemory.kind == kind
    ).order_by(ProjectMemory.id.desc()))


def connection_state(db, project_id: int) -> dict:
    """Fresh Core state from verified persistence, not a claimed install."""
    credential = _memory(db, project_id, CREDENTIAL_KIND)
    snapshot_row = _memory(db, project_id, SNAPSHOT_KIND)
    snapshot = {}
    if snapshot_row and snapshot_row.verified:
        try:
            snapshot = json.loads(snapshot_row.content)
            if not isinstance(snapshot, dict) or snapshot.get("schema") != "karel.fresh-core.readonly.v1":
                snapshot = {}
        except (ValueError, TypeError):
            snapshot = {}
    if not credential:
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
        "has_key": bool(credential),
        "last_synced_at": snapshot.get("fetched_at"),
        "snapshot": snapshot,
        "vault_ready": vault_ready(),
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


def disconnect_readonly(db, project_id: int, actor_id: int) -> None:
    """Local revoke; users must still revoke the credential in WordPress."""
    for kind in (CREDENTIAL_KIND, SNAPSHOT_KIND):
        for row in db.scalars(select(ProjectMemory).where(
                ProjectMemory.project_id == project_id, ProjectMemory.kind == kind)).all():
            db.delete(row)
    db.add(ProjectEvent(
        project_id=project_id, user_id=actor_id,
        event_type="fresh_core_disconnected",
        detail="Vazba a její uložená čtecí data odstraněna z Karla; revokaci klíče je nutné provést také ve WordPressu.",
    ))
    db.commit()
