from __future__ import annotations

import re
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..models import Project, Chat, Message, User
from .actions import create_pending_action
from .tool_layer import search_chat_history

def is_complex_project_brief(text: str) -> bool:
    """A long, multi-topic project brief needs analysis, not a keyword-based write."""
    q=(text or '').strip()
    if len(q) >= 480 or q.count('\n') >= 7:
        return True
    headings=('zadání:', 'cíle:', 'funkcionality:', 'architektura:', 'ux:', 'etapy:', 'požadavky:')
    return sum(1 for h in headings if h in q.lower()) >= 3


WRITE_WORDS = ('zapiš','zapis','ulož','uloz','doplň','dopln','přidej','pridej','vytvoř','vytvor','změň','zmen','uprav')

FIELD_LABELS = {
    'short_description':'Stručný popis projektu',
    'purpose':'Účel projektu',
    'business_goal':'Obchodní cíl',
    'functional_goal':'Hlavní funkce / zadání',
    'project_scope':'Rozsah projektu',
    'project_plan':'Plán projektu',
}

def _low(text: str) -> str:
    return (text or '').strip().lower()

def _is_write(q: str) -> bool:
    return any(w in q for w in WRITE_WORDS)

def _extract_after_colon(text: str) -> str:
    if ':' in (text or ''):
        return text.split(':',1)[1].strip()
    return ''

def _previous_referenced_message(db: Session, chat_id: int, before_message_id: int, query: str) -> Message | None:
    hits = search_chat_history(db, chat_id, query, before_message_id=before_message_id, limit=16)
    q=_low(query)
    wants_assistant=any(x in q for x in ('jsi připravil','jsi pripravil','jsi navrhl','tvůj návrh','tvuj navrh','co jsi sepsal','které jsi','ktere jsi'))
    preferred_role='assistant' if wants_assistant else 'user'
    ids = [h.get('message_id') for h in hits if h.get('role') == preferred_role and h.get('message_id')]
    if not ids:
        ids = [h.get('message_id') for h in hits if h.get('message_id')]
    if ids:
        rows = db.scalars(select(Message).where(Message.id.in_(ids))).all()
        by_id = {m.id:m for m in rows}
        ranked = [by_id[i] for i in ids if i in by_id and len((by_id[i].content or '').strip()) >= 120]
        if ranked:
            return ranked[0]
    fallback=db.scalar(select(Message).where(Message.chat_id==chat_id, Message.role==preferred_role, Message.id < before_message_id).order_by(Message.id.desc()))
    if fallback: return fallback
    return db.scalar(select(Message).where(Message.chat_id==chat_id, Message.id < before_message_id).order_by(Message.id.desc()))

def _content_for_write(db: Session, chat: Chat, message: Message) -> str:
    inline=_extract_after_colon(message.content or '')
    if len(inline)>=40:
        return inline
    prev=_previous_referenced_message(db,chat.id,message.id,message.content or '')
    return (prev.content or '').strip() if prev else inline

def _explicit_field(q: str) -> str | None:
    # Exact semantic routing. AI does not guess database fields.
    if any(x in q for x in ('stručný popis','strucny popis','krátký popis','kratky popis')):
        return 'short_description'
    if any(x in q for x in ('hlavní funkce','hlavni funkce','funkční zadání','funkcni zadani','zadání projektu','zadani projektu')):
        return 'functional_goal'
    if any(x in q for x in ('obchodní cíl','obchodni cil')):
        return 'business_goal'
    if any(x in q for x in ('rozsah projektu','co do projektu patří','co do projektu patri')):
        return 'project_scope'
    if any(x in q for x in ('plán projektu','plan projektu','časová osa','casova osa','milníky','milniky')):
        return 'project_plan'
    if any(x in q for x in ('účel projektu','ucel projektu','proč projekt','proc projekt')):
        return 'purpose'
    return None

def _candidate_fields(q: str) -> list[str]:
    # Keep choices short and useful.
    if any(x in q for x in ('cíl','cil','cíle','cile')):
        return ['purpose','business_goal','functional_goal']
    if any(x in q for x in ('zadání','zadani','funkc','co má umět','co ma umet')):
        return ['functional_goal','purpose','project_scope']
    if any(x in q for x in ('plán','plan','postup','fáze','faze')):
        return ['project_plan','project_scope','functional_goal']
    return ['short_description','purpose','business_goal','functional_goal','project_scope','project_plan']

def _create_field_action(db, project, message, field: str, content: str):
    if field == 'short_description':
        # Sidebar is intentionally concise. Never dump a long document there.
        compact=' '.join(content.split())
        if len(compact)>360:
            compact=compact[:357].rstrip()+'…'
        return create_pending_action(db, project.id, {
            'type':'update_project','title':'Uložit stručný popis projektu','payload':{'description':compact},
        }, source_message_id=message.id)
    return create_pending_action(db, project.id, {
        'type':'update_project_map','title':f'Uložit: {FIELD_LABELS[field]}','payload':{field:content},
    }, source_message_id=message.id)

def plan_write_request(db: Session, project: Project, chat: Chat, user: User, message: Message) -> list:
    text=(message.content or '').strip(); q=_low(text)
    if not _is_write(q) or is_complex_project_brief(text):
        return []
    actions=[]

    # Project/map write. Explicit field -> proposal. Ambiguous destination -> choice buttons.
    project_write = ('projekt' in q or 'map' in q or any(x in q for x in ('hlavní funkce','hlavni funkce','obchodní cíl','obchodni cil','rozsah','účel','ucel','plán','plan'))) and any(x in q for x in WRITE_WORDS)
    if project_write and _explicit_field(q):
        content=_content_for_write(db,chat,message)
        if content:
            field=_explicit_field(q)
            if field:
                row=_create_field_action(db,project,message,field,content)
            else:
                candidates=_candidate_fields(q)
                row=create_pending_action(db, project.id, {
                    'type':'choose_project_map_field',
                    'title':'Vyber, kam změnu uložit',
                    'payload':{'content':content,'candidates':candidates},
                }, source_message_id=message.id)
            if row: actions.append(row)
            return actions

    if any(x in q for x in ('vytvoř úkol','vytvor ukol','přidej úkol','pridej ukol')):
        title=_extract_after_colon(text)
        if not title:
            m=re.search(r'(?:vytvoř|vytvor|přidej|pridej)\s+(?:mi\s+)?(?:nový\s+|novy\s+)?(?:úkol|ukol)\s+(.+)$', text, re.I)
            title=(m.group(1).strip() if m else '')
        if title:
            row=create_pending_action(db, project.id, {'type':'create_task','title':f'Vytvořit úkol: {title[:120]}','payload':{'title':title}}, source_message_id=message.id)
            if row: actions.append(row)
            return actions

    if 'knihovn' in q and any(x in q for x in ('ulož','uloz','zapiš','zapis','přidej','pridej')):
        content=_content_for_write(db,chat,message)
        if content:
            first=(content.splitlines()[0] or '').strip()
            row=create_pending_action(db, project.id, {'type':'save_library_item','title':'Uložit do Knihovny účtu','payload':{'title':first[:120] or 'Uložená znalost','category':'knowledge','description':content}}, source_message_id=message.id)
            if row: actions.append(row)
            return actions

    if any(x in q for x in ('rozhodnutí','rozhodnuti','poznámku','poznamku')) and any(x in q for x in ('ulož','uloz','zapiš','zapis')):
        content=_content_for_write(db,chat,message)
        if content:
            typ='save_decision' if 'rozhod' in q else 'save_note'
            row=create_pending_action(db, project.id, {'type':typ,'title':'Uložit rozhodnutí' if typ=='save_decision' else 'Uložit poznámku','payload':{'title':'Rozhodnutí projektu' if typ=='save_decision' else 'Poznámka projektu','content':content}}, source_message_id=message.id)
            if row: actions.append(row)
    return actions
