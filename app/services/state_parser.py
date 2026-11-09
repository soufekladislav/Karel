import json, re
from sqlalchemy.orm import Session
from .actions import create_pending_action

PATTERN = re.compile(r'<KAREL_STATE>(.*?)</KAREL_STATE>', re.S | re.I)


def apply_state(db: Session, project_id: int, chat_id: int, raw: str, source_message_id: int | None = None, allow_actions: bool = True) -> str:
    m = PATTERN.search(raw or '')
    if not m:
        return raw
    visible = (raw[:m.start()] + raw[m.end():]).strip()
    try:
        state = json.loads(m.group(1).strip())
    except Exception:
        return visible

    # Complex intake is a discussion, not a write. Discard proposed actions until follow-up.
    if not allow_actions:
        return visible

    # New unified action format. Nothing is written before user confirmation.
    for item in state.get('actions', [])[:20]:
        create_pending_action(db, project_id, item, source_message_id=source_message_id)

    # Backward compatibility: old task/memory/proposal payloads are converted to pending actions.
    for item in state.get('tasks', [])[:20]:
        if not isinstance(item, dict) or not str(item.get('title') or '').strip():
            continue
        create_pending_action(db, project_id, {
            'type': 'create_task',
            'title': f"Vytvořit úkol: {str(item.get('title') or '').strip()}",
            'payload': {
                'title': str(item.get('title') or '').strip(),
                'description': item.get('description') or '',
                'status': item.get('status') or 'todo',
            },
        }, source_message_id=source_message_id)

    for item in state.get('memory', [])[:20]:
        if not isinstance(item, dict): continue
        content = str(item.get('content') or '').strip()
        if not content: continue
        action_type = 'save_decision' if str(item.get('kind') or '') == 'decision' else 'save_note'
        create_pending_action(db, project_id, {
            'type': action_type,
            'title': str(item.get('title') or 'Uložit informaci'),
            'payload': {'title': item.get('title') or 'Informace', 'content': content},
        }, source_message_id=source_message_id)

    for item in state.get('proposals', [])[:10]:
        if not isinstance(item, dict): continue
        ptype = str(item.get('type') or '').strip().lower()
        payload = item.get('payload') if isinstance(item.get('payload'), dict) else {}
        if ptype == 'project_map':
            create_pending_action(db, project_id, {'type':'update_project_map','title':str(item.get('title') or 'Doplnit Projektovou mapu'),'payload':payload}, source_message_id=source_message_id)
        elif ptype == 'memory':
            kind = str(payload.get('kind') or 'note')
            create_pending_action(db, project_id, {'type':'save_decision' if kind=='decision' else 'save_note','title':str(item.get('title') or 'Uložit informaci'),'payload':payload}, source_message_id=source_message_id)

    db.flush()
    return visible
