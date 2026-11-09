from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..bootstrap import bootstrap_state
from ..config import settings
from ..database import engine
from ..models import User, Project, Chat, Message, Task, ProjectFile, LibraryItem, ProjectMemory, ProjectEvent
from . import fresh_key


def build_app_manifest(db: Session, version: str) -> dict:
    counts = {
        'users': db.scalar(select(func.count(User.id))) or 0,
        'projects': db.scalar(select(func.count(Project.id))) or 0,
        'active_projects': db.scalar(select(func.count(Project.id)).where(Project.status != 'archived')) or 0,
        'archived_projects': db.scalar(select(func.count(Project.id)).where(Project.status == 'archived')) or 0,
        'chats': db.scalar(select(func.count(Chat.id))) or 0,
        'archived_chats': db.scalar(select(func.count(Chat.id)).where(Chat.is_archived == True)) or 0,
        'messages': db.scalar(select(func.count(Message.id))) or 0,
        'tasks': db.scalar(select(func.count(Task.id))) or 0,
        'open_tasks': db.scalar(select(func.count(Task.id)).where(Task.status.in_(['todo','working','waiting_user','testing','failed']))) or 0,
        'files': db.scalar(select(func.count(ProjectFile.id))) or 0,
        'library_items': db.scalar(select(func.count(LibraryItem.id))) or 0,
        'memories': db.scalar(select(func.count(ProjectMemory.id))) or 0,
    }
    file_bytes = db.scalar(select(func.coalesce(func.sum(ProjectFile.size_bytes), 0))) or 0
    recent = db.scalars(select(ProjectEvent).order_by(ProjectEvent.id.desc()).limit(50)).all()
    recent_ops = [
        {
            'time': e.created_at.isoformat() if e.created_at else None,
            'project_id': e.project_id,
            'type': e.event_type,
            'detail': e.detail,
        }
        for e in recent
    ]
    errors = [x for x in recent_ops if any(k in str(x['type']).lower() for k in ['error','failed','failure'])][:15]
    state = bootstrap_state()
    payload = {
        'schema': 'karel.manifest.v2',
        'app': {'name': 'Karel', 'version': version, 'role': 'virtual_project_specialist', 'status': 'alpha'},
        'purpose': 'Řízení projektového kontextu, komunikace, úkolů, výstupů a postupně automatizovaného vývoje.',
        'capabilities': {
            'project_dashboard': 'active', 'project_chat': 'active', 'chat_archive': 'active', 'chat_delete': 'active',
            'brain_configuration': 'active', 'project_workflow_profiles': 'active', 'hybrid_orchestrator': 'active', 'tool_layer': 'active', 'chat_history_search': 'active', 'account_history_search': 'active', 'deterministic_reads': 'active', 'project_action_engine': 'active', 'project_write_confirmation': 'active', 'single_confirmation_execution': 'active', 'single_approval_button': 'active', 'semantic_field_routing': 'active', 'approval_result_link': 'active', 'proposal_supersede_on_discussion': 'active', 'authoritative_task_read': 'active', 'project_save_proposals': 'active', 'library_write_actions': 'active', 'chat_activity_loader': 'active',
            'project_archive': 'active', 'project_map': 'active', 'task_management': 'active', 'project_history': 'active',
            'attachment_content_extraction': 'active', 'zip_source_inspection': 'active', 'project_files': 'active', 'manifest_analysis': 'active', 'manifest_hash': 'active', 'account_library': 'active',
            'context_retrieval': 'active', 'source_priority': 'active', 'implicit_manifest_refresh': 'active', 'url_source_resolver': 'active', 'cross_project_reuse': 'testing',
            'fresh_key': 'active' if fresh_key.configured() else 'available',
            'fresh_core_context': 'planned', 'task_history': 'testing', 'release_management': 'planned',
            'workspace_build': 'planned', 'autonomous_coding': 'planned', 'image_vision_analysis': 'planned',
        },
        'project_management': {
            'project_map_fields': {
                'purpose': 'Účel projektu',
                'business_goal': 'Obchodní cíl',
                'functional_goal': 'Hlavní funkce / zadání',
                'project_scope': 'Rozsah projektu',
                'project_plan': 'Plán projektu',
                'project_type': 'Typ projektu',
                'project_deadline': 'Cílový termín',
            },
            'sidebar_description_policy': 'short_only',
            'ambiguous_write_policy': 'offer_field_choices',
        },
        'tools': {
            'read': ['get_project','get_project_map','list_tasks','list_library','search_library','search_chat_history','search_project_history','search_account_history','search_project_memory'],
            'write': ['update_project','update_project_map','create_task','update_task','archive_task','delete_task','save_decision','save_note','save_library_item','update_library_item'],
            'direct_sql_for_ai': False,
        },
        'action_engine': {
            'enabled': True,
            'approval_ui': 'single_button',
            'confirmation_policy': 'one_approval_per_current_proposal',
            'discussion_supersedes_pending': True,
            'verification_required': True,
            'result_link_required': True,
            'semantic_field_routing': True,
            'ambiguous_field_choice': True,
        },
        'runtime': {
            'database_driver': engine.url.drivername,
            'database_ok': bool(state.get('database')),
            'schema_ok': bool(state.get('schema')),
            'ai_engine_configured': bool(settings.engine_url),
            'fresh_key_configured': bool(fresh_key.configured()),
            'python': platform.python_version(),
        },
        'data': {**counts, 'project_file_bytes': int(file_bytes)},
        'operations': {'recent': recent_ops, 'recent_errors': errors},
        'storage_policy': {
            'project_files': 'metadata + referenced files',
            'source_code': 'external repository/workspace planned',
            'temporary_artifacts': 'retention planned',
            'deduplication': 'planned',
        },
        'limitations': ['fresh_core_live_context_not_active','release_workspace_not_active','autonomous_build_not_active'],
        'superadmin_console': {'restricted': True, 'superadmin': settings.superadmin_email},
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    payload['integrity'] = {'algorithm': 'sha256', 'hash': hashlib.sha256(canonical).hexdigest()}
    payload['generated_at'] = datetime.utcnow().isoformat() + 'Z'
    return payload
