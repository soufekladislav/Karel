from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from sqlalchemy.orm import Session

from ..models import Project, Chat, User
from .tool_layer import (
    get_project, get_project_map, list_tasks, list_library, search_library,
    search_chat_history, search_project_history, search_account_history, search_project_memory,
)

@dataclass
class OrchestrationResult:
    mode: str = 'ai'  # ai | direct
    direct_response: str | None = None
    context_blocks: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)


def _low(text: str) -> str:
    return (text or '').strip().lower()


def _is_simple_task_list(q: str) -> bool:
    return bool(re.search(r'\b(ukaž|ukaz|vypiš|vypis|jaké|jake|seznam)\b.*\b(úkol|ukol|task)', q)) and not any(x in q for x in ('reviz','které','ktere','smysl','priorit','vyřad','vyrad','smaz','archiv','analyz'))


def _is_simple_project_map(q: str) -> bool:
    return ('projektov' in q and 'map' in q) and any(x in q for x in ('ukaž','ukaz','vypiš','vypis','co je','jaká je','jaka je')) and not any(x in q for x in ('uprav','doplň','dopln','změň','zmen','zapiš','zapis'))


def _is_simple_library(q: str) -> bool:
    return ('knihovn' in q) and any(x in q for x in ('ukaž','ukaz','vypiš','vypis','co mám','co mam','seznam')) and not any(x in q for x in ('ulož','uloz','zapiš','zapis','najdi','hledej','podob'))


def _history_intent(q: str) -> bool:
    return any(x in q for x in (
        'histor', 'posílal jsem', 'posilal jsem', 'poslal jsem', 'posílal', 'posilal', 'poslal', 'už jsem ti', 'uz jsem ti',
        'řešili jsme', 'resili jsme', 'říkal jsem', 'rikal jsem', 'psal jsem', 'před chvílí', 'pred chvili',
        'předtím', 'predtim', 'pamatuješ', 'pamatujes', 'najdi v chatu', 'najdi v historii'
    ))


def _account_history_intent(q: str) -> bool:
    return any(x in q for x in ('historie účtu','historii účtu','historie uctu','napříč projekty','napric projekty','jiném projektu','jinem projektu','někde jinde','nekde jinde'))


def _task_intent(q: str) -> bool:
    return any(x in q for x in ('úkol','ukol','task','backlog','fronta'))


def _project_map_intent(q: str) -> bool:
    return ('projektov' in q and 'map' in q) or any(x in q for x in ('účel projektu','ucel projektu','zadání projektu','zadani projektu','obchodní cíl','obchodni cil'))


def _library_intent(q: str) -> bool:
    return 'knihovn' in q or 'znovupoužit' in q or 'znovupouzit' in q


def _format_tasks(tasks: list[dict]) -> str:
    if not tasks:
        return 'Projekt aktuálně nemá žádné aktivní úkoly.'
    lines=[]
    for t in tasks:
        lines.append(f"- TASK-{t['id']} · {t['status_label']} · priorita {t['priority']} · {t['title']}")
    return 'Aktuální úkoly z databáze:\n' + '\n'.join(lines)


def _format_map(spec: dict) -> str:
    if not spec:
        return 'Projektová mapa zatím nemá uložený obsah.'
    labels={
        'purpose':'Účel projektu','project_type':'Typ projektu','business_goal':'Obchodní cíl','functional_goal':'Hlavní funkce / zadání',
        'project_scope':'Rozsah projektu','project_deadline':'Cílový termín','project_plan':'Plán projektu'
    }
    return '\n'.join(f"**{labels.get(k,k)}:** {v}" for k,v in spec.items() if v)


def _format_library(items: list[dict]) -> str:
    if not items:
        return 'Knihovna účtu je zatím prázdná.'
    return 'Knihovna účtu:\n' + '\n'.join(f"- LIB-{x['id']} · {x['category']} · {x['title']}" for x in items)


def _json_block(title: str, data) -> str:
    return title + '\n' + json.dumps(data, ensure_ascii=False, indent=2)


def orchestrate(db: Session, project: Project, chat: Chat, user: User, query: str, current_message_id: int | None = None) -> OrchestrationResult:
    q=_low(query)
    result=OrchestrationResult()

    # Cheap deterministic reads: no LLM call needed.
    if _is_simple_task_list(q):
        tasks=list_tasks(db,project.id,include_archived=False)
        result.mode='direct'; result.direct_response=_format_tasks(tasks); result.tools_used=['list_tasks']
        return result
    if _is_simple_project_map(q):
        spec=get_project_map(db,project.id)
        result.mode='direct'; result.direct_response=_format_map(spec); result.tools_used=['get_project_map']
        return result
    if _is_simple_library(q):
        items=list_library(db,user.id,limit=60)
        result.mode='direct'; result.direct_response=_format_library(items); result.tools_used=['list_library']
        return result

    # Baseline authoritative snapshot is deliberately small.
    result.context_blocks.append(_json_block('TOOL:get_project — autoritativní data', get_project(db,project)))
    result.tools_used.append('get_project')

    if _task_intent(q):
        tasks=list_tasks(db,project.id,include_archived=True)
        result.context_blocks.append(_json_block('TOOL:list_tasks — autoritativní seznam úkolů', tasks))
        result.tools_used.append('list_tasks')

    if _project_map_intent(q):
        spec=get_project_map(db,project.id)
        result.context_blocks.append(_json_block('TOOL:get_project_map — autoritativní Projektová mapa', spec))
        result.tools_used.append('get_project_map')

    if _history_intent(q):
        current=search_chat_history(db,chat.id,query,before_message_id=current_message_id,limit=14)
        result.context_blocks.append(_json_block('TOOL:search_chat_history — výsledky z CELÉ historie aktuálního chatu', current))
        result.tools_used.append('search_chat_history')
        # If current chat is weak, search sibling chats of the project too.
        if len(current) < 3 or _account_history_intent(q):
            project_hist=search_project_history(db,project.id,query,exclude_chat_id=chat.id,limit=10)
            result.context_blocks.append(_json_block('TOOL:search_project_history — další chaty aktuálního projektu', project_hist))
            result.tools_used.append('search_project_history')
        if _account_history_intent(q):
            account=search_account_history(db,user,query,current_project_id=project.id,limit=14)
            result.context_blocks.append(_json_block('TOOL:search_account_history — historie dostupných projektů účtu', account))
            result.tools_used.append('search_account_history')

    if _library_intent(q):
        lib=search_library(db,user.id,query,limit=12)
        result.context_blocks.append(_json_block('TOOL:search_library — relevantní položky knihovny účtu', lib))
        result.tools_used.append('search_library')

    # Decisions/notes are useful when user asks what was agreed, even without saying "history".
    if any(x in q for x in ('rozhod','domluv','pravidl','dohod','platí','plati')):
        mem=search_project_memory(db,project.id,query,limit=12)
        result.context_blocks.append(_json_block('TOOL:search_project_memory — schválená projektová paměť', mem))
        result.tools_used.append('search_project_memory')

    # When the user explicitly refers to previous content but search found nothing useful,
    # still surface recent longer user messages from the full chat via search_chat_history fallback.
    return result
