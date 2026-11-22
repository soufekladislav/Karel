"""Read-only state projection for Karel's floating assistant.

Evidence is derived from committed action results and project records, never
from an AI assertion that something was "zapracováno".
"""
from __future__ import annotations

import json
from sqlalchemy import select

from ..models import Chat, Message, ProjectEvent, ProjectMemory
from .actions import pending_group, parse_pending
from .assistant_work_context import screen_evidence
from .github_schedule_publisher import latest_sync_status


def _receipt(db, project_id: int) -> dict | None:
    events = db.scalars(select(ProjectEvent).where(
        ProjectEvent.project_id == project_id,
        ProjectEvent.event_type.in_(
            ("karel_action_approved", "karel_action_batch_confirmed")),
    ).order_by(ProjectEvent.id.desc()).limit(5)).all()
    for event in events:
        try:
            batch = json.loads(event.detail)
            rows = batch.get("results") or []
            if not isinstance(rows, list) or not rows:
                continue
            results = [row for row in rows if isinstance(row, dict)]
        except (TypeError, ValueError, AttributeError):
            continue
        if not results:
            continue
        first = results[0]
        if first.get("type") == "approve_project_schedule":
            version = first.get("version")
            planned = first.get("milestones_saved")
            sync = latest_sync_status(db, project_id)
            return {
                "title": "Zápis ověřen – Pipeline",
                "text": "Schválená verze " + str(version) + ", " +
                        str(planned) + " milníků ověřených z databáze. " +
                        "GitHub publikování: " +
                        str(sync.get("state") or "neověřeno") + ".",
                "url": "/projects/" + str(project_id) +
                       "?view=development#project-timeline",
            }
        first_id = first.get("task_id")
        if first_id and first.get("type") in ("create_task", "update_task"):
            return {
                "title": "Zápis ověřen – úkol",
                "text": "V projektové databázi byl zpracován TASK-" +
                        str(first_id) + ".",
                "url": "/projects/" + str(project_id) + "?view=tasks",
            }
        return {
            "title": "Akce v projektu byla provedena",
            "text": "Ověřený interní výsledek: " + str(
                first.get("type") or "projektová změna") +
                ". Podrobnosti a případné chyby jsou v projektové historii.",
            "url": "/projects/" + str(project_id) + "?view=development",
        }
    return None


def assistant_state(db, project, user, *,
                    screen="chat", can_edit=False, chat_id=None) -> dict:
    # Honor the conversation that the user is actually viewing. Never
    # reuse a chat ID belonging to a different project.
    active = db.get(Chat,chat_id) if isinstance(chat_id,int) and chat_id>0 else None
    if active and (active.project_id != project.id or active.is_archived):
        active = None
    if active is None:
        active = db.scalar(select(Chat).where(
            Chat.project_id == project.id, Chat.is_archived == False,
        ).order_by(Chat.updated_at.desc(), Chat.id.desc()))
    context = screen_evidence(db, project, user, screen)
    if not active:
        return {
            "project_id": project.id, "chat_id": None,
            "messages": [], "messages_truncated": False,
            "pending": [], "receipt": _receipt(db, project.id),
            "can_edit": bool(can_edit),
            "context_label": context["label"],
            "context_summary": context["summary"],
        }
    rows = db.scalars(select(Message).where(
        Message.chat_id == active.id,
    ).order_by(Message.id.desc()).limit(18)).all()
    rows = list(reversed(rows))
    pending = []
    for row in pending_group(db, project.id, chat_id=active.id):
        item = parse_pending(row)
        if item.get("state") != "pending":
            continue
        payload = item.get("payload") or {}
        description = ""
        if item.get("type") == "approve_project_schedule":
            target = str(payload.get("target_test_date") or "")
            scope = str(payload.get("scope") or "nezadaný")
            description = "Cíl: " + target + " · Rozsah: " + scope
        pending.append({
            "id": row.id,
            "title": str(item.get("title") or row.title)[:200],
            "type": str(item.get("type") or ""),
            "description": description[:240],
        })
    return {
        "project_id": project.id, "chat_id": active.id,
        "messages": [{
            "id": item.id, "role": item.role,
            "content": (
                "AI služba je momentálně nedostupná, zpráva zůstala uložená."
                if (item.content or "").startswith("[[ENGINE_UNAVAILABLE]]")
                else (item.content or "")[:3300]),
        } for item in rows],
        "messages_truncated": len(rows) == 18,
        "pending": pending,
        "receipt": _receipt(db, project.id),
        "can_edit": bool(can_edit),
        "context_label": context["label"],
        "context_summary": context["summary"],
    }
