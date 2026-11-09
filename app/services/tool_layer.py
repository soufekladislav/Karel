from __future__ import annotations

import re
from dataclasses import dataclass
from sqlalchemy import select, or_, and_
from sqlalchemy.orm import Session

from ..models import Project, ProjectMember, Chat, Message, Task, ProjectMemory, LibraryItem, User

STATUS_LABELS = {
    'todo': 'Nezahájeno', 'working': 'Ve vývoji', 'waiting_user': 'Čeká na uživatele',
    'testing': 'V testování', 'done': 'Dokončeno', 'failed': 'Chyba', 'archived': 'Archivováno'
}

PROJECT_SPEC_KINDS = {
    'purpose': 'Účel projektu',
    'project_type': 'Typ projektu',
    'business_goal': 'Obchodní cíl',
    'functional_goal': 'Hlavní funkce / zadání',
    'project_scope': 'Rozsah projektu',
    'project_deadline': 'Cílový termín',
    'project_plan': 'Plán projektu',
}

STOP = {
    'jsem','jsi','karel','karle','projekt','projektu','projektem','prosím','prosim','můžeš','muzes','může','muze',
    'chci','potřebuji','potrebuji','jako','ještě','jeste','tedy','tak','jen','už','uz','co','jak','kde','kdy','proč','proc',
    'nebo','ale','aby','zde','mám','mam','ho','ji','je','se','si','do','na','v','ve','z','ze','a','i','s','u','mi','to','toto',
    'ten','tahle','tady','tam','které','ktere','který','ktery','kterou','byl','byla','bylo','bych','jsme','jste','něco','neco',
    'posílal','posilal','poslal','říkal','rikal','psal','zadání','zadani'
}


def _terms(text: str, limit: int = 12) -> list[str]:
    words = re.findall(r"[\wá-žÁ-Ž_-]+", (text or '').lower(), flags=re.UNICODE)
    out=[]
    for w in words:
        if len(w) < 3 or w in STOP or w in out:
            continue
        out.append(w)
        if len(out) >= limit:
            break
    return out


def _score(text: str, terms: list[str]) -> int:
    low=(text or '').lower()
    return sum(4 if t in low else 0 for t in terms)


def _clip(text: str, limit: int = 1800) -> str:
    text=text or ''
    return text if len(text) <= limit else text[:limit] + '…'


def accessible_project_ids(db: Session, user: User) -> list[int]:
    member_ids = select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
    return list(db.scalars(select(Project.id).where(or_(Project.owner_id == user.id, Project.id.in_(member_ids)))).all())


def get_project(db: Session, project: Project) -> dict:
    return {
        'id': project.id,
        'name': project.name,
        'description': project.description or '',
        'status': project.status,
        'updated_at': project.updated_at.isoformat() if project.updated_at else None,
    }


def get_project_map(db: Session, project_id: int) -> dict:
    rows=db.scalars(select(ProjectMemory).where(
        ProjectMemory.project_id==project_id,
        ProjectMemory.kind.in_(list(PROJECT_SPEC_KINDS.keys())),
        ProjectMemory.verified==True,
    ).order_by(ProjectMemory.id.desc())).all()
    data={}
    for row in rows:
        if row.kind not in data:
            data[row.kind]=row.content or ''
    return data


def list_tasks(db: Session, project_id: int, include_archived: bool = False) -> list[dict]:
    stmt=select(Task).where(Task.project_id==project_id)
    if not include_archived:
        stmt=stmt.where(Task.status!='archived')
    rows=db.scalars(stmt.order_by(Task.status=='done', Task.priority.asc(), Task.id.asc())).all()
    return [{
        'id': t.id, 'title': t.title, 'description': t.description or '', 'status': t.status,
        'status_label': STATUS_LABELS.get(t.status,t.status), 'priority': t.priority,
        'updated_at': t.updated_at.isoformat() if t.updated_at else None,
    } for t in rows]


def list_library(db: Session, user_id: int, limit: int = 100) -> list[dict]:
    rows=db.scalars(select(LibraryItem).where(LibraryItem.owner_id==user_id).order_by(LibraryItem.id.desc()).limit(limit)).all()
    return [{'id': x.id,'title':x.title,'category':x.category,'description':x.description or ''} for x in rows]


def search_library(db: Session, user_id: int, query: str, limit: int = 12) -> list[dict]:
    terms=_terms(query)
    rows=db.scalars(select(LibraryItem).where(LibraryItem.owner_id==user_id).order_by(LibraryItem.id.desc()).limit(300)).all()
    ranked=sorted(rows,key=lambda x:(_score(' '.join([x.title,x.category,x.description or '']),terms),x.id),reverse=True)
    selected=[x for x in ranked if _score(' '.join([x.title,x.category,x.description or '']),terms)>0][:limit]
    if not selected and not terms:
        selected=ranked[:limit]
    return [{'id':x.id,'title':x.title,'category':x.category,'description':_clip(x.description or '',1000)} for x in selected]


def _message_dict(m: Message, chat: Chat, project: Project | None = None) -> dict:
    return {
        'message_id': m.id,
        'chat_id': chat.id,
        'chat_title': chat.title,
        'project_id': project.id if project else chat.project_id,
        'project_name': project.name if project else None,
        'role': m.role,
        'content': _clip(m.content, 2600),
        'created_at': m.created_at.isoformat() if m.created_at else None,
    }


def _term_condition(terms: list[str]):
    if not terms:
        return None
    return or_(*[Message.content.ilike(f'%{t}%') for t in terms])


def search_chat_history(db: Session, chat_id: int, query: str, before_message_id: int | None = None, limit: int = 12) -> list[dict]:
    chat=db.get(Chat,chat_id)
    if not chat:
        return []
    terms=_terms(query)
    stmt=select(Message).where(Message.chat_id==chat_id)
    if before_message_id:
        stmt=stmt.where(Message.id < before_message_id)
    cond=_term_condition(terms)
    if cond is not None:
        matched=db.scalars(stmt.where(cond).order_by(Message.id.desc()).limit(250)).all()
        ranked=sorted(matched,key=lambda m:(_score(m.content,terms),m.id),reverse=True)
        selected=[m for m in ranked if _score(m.content,terms)>0][:limit]
        if selected:
            return [_message_dict(m,chat) for m in selected]
    # For vague references such as "to, co jsem posílal" inspect older long user messages.
    recent=db.scalars(stmt.where(Message.role=='user').order_by(Message.id.desc()).limit(500)).all()
    selected=[m for m in recent if len((m.content or '').strip())>=120][:min(limit,10)]
    return [_message_dict(m,chat) for m in selected]


def search_project_history(db: Session, project_id: int, query: str, exclude_chat_id: int | None = None, limit: int = 12) -> list[dict]:
    terms=_terms(query)
    stmt=select(Message,Chat).join(Chat,Message.chat_id==Chat.id).where(Chat.project_id==project_id)
    if exclude_chat_id:
        stmt=stmt.where(Chat.id!=exclude_chat_id)
    cond=_term_condition(terms)
    if cond is not None:
        stmt=stmt.where(cond)
    rows=db.execute(stmt.order_by(Message.id.desc()).limit(500)).all()
    candidates=[]
    for m,chat in rows:
        score=_score(m.content,terms) if terms else 1
        if score>0:
            candidates.append((score,m.id,m,chat))
    candidates.sort(key=lambda x:(x[0],x[1]),reverse=True)
    return [_message_dict(m,chat) for _,_,m,chat in candidates[:limit]]


def search_account_history(db: Session, user: User, query: str, current_project_id: int | None = None, limit: int = 14) -> list[dict]:
    project_ids=accessible_project_ids(db,user)
    if not project_ids:
        return []
    projects={p.id:p for p in db.scalars(select(Project).where(Project.id.in_(project_ids))).all()}
    terms=_terms(query)
    stmt=(select(Message,Chat)
          .join(Chat,Message.chat_id==Chat.id)
          .where(Chat.project_id.in_(project_ids)))
    cond=_term_condition(terms)
    if cond is not None:
        stmt=stmt.where(cond)
    rows=db.execute(stmt.order_by(Message.id.desc()).limit(900)).all()
    candidates=[]
    for m,chat in rows:
        score=_score(m.content,terms) if terms else 1
        if current_project_id and chat.project_id==current_project_id:
            score += 1
        if score>0:
            candidates.append((score,m.id,m,chat,projects.get(chat.project_id)))
    candidates.sort(key=lambda x:(x[0],x[1]),reverse=True)
    return [_message_dict(m,chat,project) for _,_,m,chat,project in candidates[:limit]]


def search_project_memory(db: Session, project_id: int, query: str, limit: int = 12) -> list[dict]:
    terms=_terms(query)
    rows=db.scalars(select(ProjectMemory).where(
        ProjectMemory.project_id==project_id,
        ProjectMemory.verified==True,
        ProjectMemory.kind!='pending_action',
    ).order_by(ProjectMemory.id.desc()).limit(500)).all()
    ranked=sorted(rows,key=lambda x:(_score(' '.join([x.kind,x.title,x.content]),terms),x.id),reverse=True)
    selected=[x for x in ranked if _score(' '.join([x.kind,x.title,x.content]),terms)>0][:limit]
    return [{'id':x.id,'kind':x.kind,'title':x.title,'content':_clip(x.content,1800),'created_at':x.created_at.isoformat() if x.created_at else None} for x in selected]
