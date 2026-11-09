from __future__ import annotations

import json
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..models import Project, Task, ProjectMemory, ProjectEvent, ProjectFile, LibraryItem, Message

PROJECT_SPEC_KINDS = {
    'purpose': 'Účel projektu',
    'project_type': 'Typ projektu',
    'business_goal': 'Obchodní cíl',
    'functional_goal': 'Hlavní funkce / zadání',
    'project_scope': 'Rozsah projektu',
    'project_deadline': 'Cílový termín',
    'project_plan': 'Plán projektu',
}

ALLOWED_TASK_STATUS = {'todo','working','waiting_user','testing','done','failed','archived'}
ALLOWED_ACTIONS = {
    'update_workflow_stage','choose_project_map_field','update_project','update_project_map','create_task','update_task','archive_task','delete_task','save_decision','save_note','save_library_item','update_library_item'
}


def _spec_value(db: Session, project_id: int, kind: str) -> str:
    row = db.scalar(select(ProjectMemory).where(ProjectMemory.project_id==project_id, ProjectMemory.kind==kind).order_by(ProjectMemory.id.desc()))
    return row.content if row else ''


def _save_spec_value(db: Session, project_id: int, kind: str, value: str) -> None:
    if kind not in PROJECT_SPEC_KINDS:
        return
    row = db.scalar(select(ProjectMemory).where(ProjectMemory.project_id==project_id, ProjectMemory.kind==kind).order_by(ProjectMemory.id.desc()))
    value = (value or '').strip()
    if row:
        row.title = PROJECT_SPEC_KINDS[kind]
        row.content = value
        row.verified = True
    elif value:
        db.add(ProjectMemory(project_id=project_id,kind=kind,title=PROJECT_SPEC_KINDS[kind],content=value,verified=True))


def normalize_action(action: dict) -> dict | None:
    if not isinstance(action, dict):
        return None
    atype = str(action.get('type') or '').strip()
    if atype not in ALLOWED_ACTIONS:
        return None
    payload = action.get('payload') if isinstance(action.get('payload'), dict) else {}
    title = str(action.get('title') or atype).strip()[:255]
    return {'type': atype, 'title': title, 'payload': payload}


def create_pending_action(db: Session, project_id: int, action: dict, source_message_id: int | None = None) -> ProjectMemory | None:
    item = normalize_action(action)
    if not item:
        return None
    data = {
        'state': 'pending',
        'type': item['type'],
        'payload': item['payload'],
        'source_message_id': source_message_id,
        'created_at': datetime.utcnow().isoformat(),
    }
    content = json.dumps(data, ensure_ascii=False, sort_keys=True)
    existing = db.scalar(select(ProjectMemory).where(ProjectMemory.project_id==project_id, ProjectMemory.kind=='pending_action', ProjectMemory.content==content))
    if existing:
        return existing
    row = ProjectMemory(project_id=project_id, kind='pending_action', title=item['title'], content=content, verified=False)
    db.add(row)
    db.flush()
    return row


def parse_pending(row: ProjectMemory) -> dict:
    try:
        data = json.loads(row.content or '{}')
    except Exception:
        data = {}
    return data if isinstance(data, dict) else {}




def pending_group(db: Session, project_id: int, chat_id: int | None = None) -> list[ProjectMemory]:
    """Return the newest still-pending action group. Actions created from one AI answer
    share source_message_id and are confirmed together by one user confirmation.
    """
    rows = db.scalars(select(ProjectMemory).where(
        ProjectMemory.project_id==project_id,
        ProjectMemory.kind=='pending_action',
        ProjectMemory.verified==False,
    ).order_by(ProjectMemory.id.desc())).all()
    pending=[]
    for row in rows:
        data=parse_pending(row)
        if data.get('state')!='pending':
            continue
        if chat_id is not None:
            source_id=data.get('source_message_id')
            source=db.get(Message, source_id) if source_id else None
            if not source or source.chat_id != chat_id:
                continue
        pending.append((row,data))
    if not pending:
        return []
    newest_row,newest_data=pending[0]
    source_id=newest_data.get('source_message_id')
    if source_id is None:
        return [newest_row]
    grouped=[row for row,data in pending if data.get('source_message_id')==source_id]
    return list(reversed(grouped))



def dismiss_pending_for_chat(db: Session, project_id: int, chat_id: int, reason: str = 'discussion_continued') -> list[ProjectMemory]:
    """Close all still-pending actions in one chat when the discussion continues.

    This keeps approval UX deterministic: an approval button is valid only for the
    current proposal. Any new non-confirmation user message supersedes it.
    """
    rows = db.scalars(select(ProjectMemory).where(
        ProjectMemory.project_id==project_id,
        ProjectMemory.kind=='pending_action',
        ProjectMemory.verified==False,
    ).order_by(ProjectMemory.id.desc())).all()
    dismissed=[]
    now=datetime.utcnow().isoformat()
    for row in rows:
        data=parse_pending(row)
        if data.get('state')!='pending':
            continue
        source_id=data.get('source_message_id')
        source=db.get(Message, source_id) if source_id else None
        if not source or source.chat_id != chat_id:
            continue
        _set_state(row, data, 'dismissed', dismissed_at=now, dismiss_reason=reason)
        row.verified=True
        dismissed.append(row)
    return dismissed


FIELD_TARGET_LABELS = {
    'short_description':'Stručný popis projektu',
    'purpose':'Účel projektu',
    'business_goal':'Obchodní cíl',
    'functional_goal':'Hlavní funkce / zadání',
    'project_scope':'Rozsah projektu',
    'project_plan':'Plán projektu',
}

def choose_pending_field(row: ProjectMemory, field: str) -> dict:
    data=parse_pending(row)
    if data.get('state')!='pending' or data.get('type')!='choose_project_map_field':
        raise ValueError('Tato volba už není aktuální.')
    candidates=data.get('payload',{}).get('candidates') or []
    if field not in FIELD_TARGET_LABELS or field not in candidates:
        raise ValueError('Toto cílové pole není pro návrh dostupné.')
    content=str(data.get('payload',{}).get('content') or '').strip()
    if not content:
        raise ValueError('Chybí obsah k uložení.')
    if field=='short_description':
        compact=' '.join(content.split())
        if len(compact)>360:
            compact=compact[:357].rstrip()+'…'
        data['type']='update_project'; data['payload']={'description':compact}
    else:
        data['type']='update_project_map'; data['payload']={field:content}
    row.title='Uložit: '+FIELD_TARGET_LABELS[field]
    row.content=json.dumps(data,ensure_ascii=False,sort_keys=True)
    return data

def execute_pending_group(db: Session, project: Project, rows: list[ProjectMemory], user_id: int | None) -> dict:
    results=[]; errors=[]
    for row in rows:
        try:
            results.append(execute_pending_action(db, project, row, user_id))
        except Exception as exc:
            errors.append({'action_id': row.id, 'title': row.title, 'error': str(exc)})
    return {'results': results, 'errors': errors, 'ok': bool(results) and not errors, 'partial': bool(results) and bool(errors)}


def _set_state(row: ProjectMemory, data: dict, state: str, **extra) -> None:
    data = dict(data)
    data['state'] = state
    data.update(extra)
    row.content = json.dumps(data, ensure_ascii=False, sort_keys=True)


def execute_pending_action(db: Session, project: Project, row: ProjectMemory, user_id: int | None) -> dict:
    data = parse_pending(row)
    if row.project_id != project.id or row.kind != 'pending_action' or data.get('state') != 'pending':
        raise ValueError('Akce už není ve stavu čekajícím na potvrzení.')
    atype = data.get('type')
    payload = data.get('payload') if isinstance(data.get('payload'), dict) else {}
    if atype not in ALLOWED_ACTIONS:
        raise ValueError('Neznámý typ akce.')

    _set_state(row, data, 'confirmed', confirmed_at=datetime.utcnow().isoformat(), confirmed_by=user_id)
    db.flush()
    _set_state(row, parse_pending(row), 'executing', executing_at=datetime.utcnow().isoformat())
    db.flush()

    result: dict = {'type': atype}
    if atype == 'choose_project_map_field':
        raise ValueError('Nejprve vyber cílovou část Projektové mapy.')

    if atype == 'update_project':
        if 'name' in payload and str(payload.get('name') or '').strip():
            project.name = str(payload['name']).strip()[:255]
        if 'description' in payload:
            project.description = str(payload.get('description') or '').strip() or None
        project.updated_at = datetime.utcnow()
        db.flush()
        check = db.get(Project, project.id)
        result.update({'project_id': project.id, 'name': check.name, 'description': check.description or '', 'target_url': f'/projects/{project.id}?view=settings'})

    elif atype == 'update_project_map':
        changed = {}
        for kind in PROJECT_SPEC_KINDS:
            if kind in payload:
                _save_spec_value(db, project.id, kind, str(payload.get(kind) or ''))
                changed[kind] = str(payload.get(kind) or '')
        db.flush()
        verified = {kind: _spec_value(db, project.id, kind) for kind in changed}
        anchors = {
            'purpose':'project-map-purpose','business_goal':'project-map-business-goal',
            'functional_goal':'project-map-main-functions','project_scope':'project-map-scope',
            'project_plan':'project-map-plan','project_type':'project-map','project_deadline':'project-map'
        }
        anchor = anchors.get(next(iter(changed))) if len(changed)==1 else 'project-map'
        result.update({'project_id': project.id, 'fields': verified, 'target_url': f'/projects/{project.id}?view=development#{anchor}'})

    elif atype == 'update_workflow_stage':
        from .workflow import get_stages, STATUSES
        stage_no=int(payload.get('stage_no') or 0)
        if stage_no not in range(1,8):
            raise ValueError('Neplatná etapa workflow.')
        stages=get_stages(db,project.id)
        st=stages[stage_no-1]
        status=str(payload.get('status') or st.status)
        if status not in STATUSES:
            raise ValueError('Neplatný stav etapy.')
        if status in ('active','completed') and any(prev.status!='completed' for prev in stages[:stage_no-1]):
            raise ValueError('Předchozí etapy nejsou schválené.')
        def parsed_date(value):
            if value in (None,''): return None
            try: return datetime.strptime(str(value),'%Y-%m-%d')
            except ValueError: raise ValueError('Datum musí být ve formátu YYYY-MM-DD.')
        start=parsed_date(payload.get('start_date')) if 'start_date' in payload else st.start_date
        due=parsed_date(payload.get('due_date')) if 'due_date' in payload else st.due_date
        if start and due and start>due: raise ValueError('Začátek je po termínu.')
        objective=str(payload.get('objective',st.objective or '')).strip()[:10000]
        acceptance=str(payload.get('acceptance',st.acceptance or '')).strip()[:10000]
        if status=='completed' and not (objective and acceptance):
            raise ValueError('Pro schválení chybí výstup nebo podmínky převzetí.')
        before={'status':st.status,'due_date':str(st.due_date) if st.due_date else None}
        st.objective=objective;st.acceptance=acceptance;st.start_date=start;st.due_date=due
        st.note=str(payload.get('note',st.note or '')).strip()[:10000]
        st.status=status;st.updated_at=datetime.utcnow()
        st.completed_at=datetime.utcnow() if status=='completed' else None
        project.updated_at=datetime.utcnow()
        db.flush()
        db.add(ProjectEvent(project_id=project.id,user_id=user_id,event_type='workflow_stage_updated',detail=json.dumps({'stage':stage_no,'before':before,'after':{'status':status,'due_date':str(due) if due else None}},ensure_ascii=False)))
        result.update({'stage_no':stage_no,'status':status,'target_url':f'/projects/{project.id}?view=development#workflow'})

    elif atype == 'create_task':
        title = str(payload.get('title') or '').strip()
        if not title:
            raise ValueError('Chybí název úkolu.')
        status = str(payload.get('status') or 'todo')
        if status not in ALLOWED_TASK_STATUS or status == 'archived':
            status = 'todo'
        task = Task(project_id=project.id, chat_id=payload.get('chat_id'), source_message_id=data.get('source_message_id'), title=title[:255], description=str(payload.get('description') or '').strip() or None, status=status, priority=int(payload.get('priority') or 50))
        db.add(task); db.flush()
        result.update({'task_id': task.id, 'title': task.title, 'status': task.status, 'target_url': f'/projects/{project.id}?view=tasks'})

    elif atype == 'update_task':
        task_id = int(payload.get('task_id') or 0)
        task = db.get(Task, task_id)
        if not task or task.project_id != project.id:
            raise ValueError('Úkol nebyl nalezen v tomto projektu.')
        if 'title' in payload and str(payload.get('title') or '').strip(): task.title = str(payload['title']).strip()[:255]
        if 'description' in payload: task.description = str(payload.get('description') or '').strip() or None
        if 'priority' in payload:
            try: task.priority = int(payload['priority'])
            except Exception: pass
        if 'status' in payload:
            status = str(payload.get('status') or '')
            if status in ALLOWED_TASK_STATUS: task.status = status
        task.updated_at = datetime.utcnow()
        task.completed_at = datetime.utcnow() if task.status == 'done' else None
        db.flush(); check = db.get(Task, task.id)
        result.update({'task_id': check.id, 'title': check.title, 'status': check.status, 'target_url': f'/projects/{project.id}?view=tasks'})

    elif atype == 'archive_task':
        task_id = int(payload.get('task_id') or 0)
        task = db.get(Task, task_id)
        if not task or task.project_id != project.id: raise ValueError('Úkol nebyl nalezen v tomto projektu.')
        task.status = 'archived'; task.updated_at = datetime.utcnow(); db.flush()
        result.update({'task_id': task.id, 'status': task.status, 'target_url': f'/projects/{project.id}?view=tasks'})

    elif atype == 'delete_task':
        task_id = int(payload.get('task_id') or 0)
        task = db.get(Task, task_id)
        if not task or task.project_id != project.id: raise ValueError('Úkol nebyl nalezen v tomto projektu.')
        snapshot = {'task_id': task.id, 'title': task.title, 'status': task.status}
        for pf in db.scalars(select(ProjectFile).where(ProjectFile.task_id==task.id)).all():
            pf.task_id = None
        db.flush()
        db.delete(task); db.flush()
        check = db.get(Task, task_id)
        result.update(snapshot); result['deleted'] = check is None; result['target_url'] = f'/projects/{project.id}?view=tasks'

    elif atype in {'save_decision','save_note'}:
        kind = 'decision' if atype == 'save_decision' else 'note'
        title = str(payload.get('title') or ('Rozhodnutí' if kind=='decision' else 'Poznámka')).strip()[:255]
        content = str(payload.get('content') or '').strip()
        if not content: raise ValueError('Chybí obsah k uložení.')
        memory = ProjectMemory(project_id=project.id, kind=kind, title=title, content=content, verified=True)
        db.add(memory); db.flush()
        result.update({'memory_id': memory.id, 'kind': kind, 'title': title, 'target_url': f'/projects/{project.id}?view=history'})

    elif atype == 'save_library_item':
        title = str(payload.get('title') or '').strip()
        if not title: raise ValueError('Chybí název položky knihovny.')
        category = str(payload.get('category') or 'other').strip()[:80] or 'other'
        description = str(payload.get('description') or payload.get('content') or '').strip() or None
        item = LibraryItem(owner_id=user_id, title=title[:255], category=category, description=description, is_public=False)
        db.add(item); db.flush()
        check=db.get(LibraryItem,item.id)
        result.update({'library_item_id':check.id,'title':check.title,'category':check.category,'target_url':'/library'})

    elif atype == 'update_library_item':
        item_id = int(payload.get('item_id') or 0)
        item = db.get(LibraryItem,item_id)
        if not item or (item.owner_id is not None and item.owner_id != user_id):
            raise ValueError('Položka knihovny nebyla nalezena v tomto účtu.')
        if 'title' in payload and str(payload.get('title') or '').strip(): item.title=str(payload['title']).strip()[:255]
        if 'category' in payload and str(payload.get('category') or '').strip(): item.category=str(payload['category']).strip()[:80]
        if 'description' in payload: item.description=str(payload.get('description') or '').strip() or None
        db.flush(); check=db.get(LibraryItem,item.id)
        result.update({'library_item_id':check.id,'title':check.title,'category':check.category,'target_url':'/library'})

    db.add(ProjectEvent(project_id=project.id,user_id=user_id,event_type='karel_action_executed',detail=json.dumps(result,ensure_ascii=False)[:1800]))
    final_data = parse_pending(row)
    _set_state(row, final_data, 'done', completed_at=datetime.utcnow().isoformat(), result=result)
    row.verified = True
    db.flush()
    return result


def dismiss_pending_action(row: ProjectMemory) -> None:
    data = parse_pending(row)
    _set_state(row, data, 'dismissed', dismissed_at=datetime.utcnow().isoformat())
    row.verified = True
