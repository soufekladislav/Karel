"""Read-only Exon production inspection. No app.main import, no create_all/migrations.

Run from deployed application root:
    python scripts/production_audit.py > karel-audit.json

The JSON contains only configuration booleans, table names/statuses, and counts.
Never copy .env, token values, database rows, or private attachments to issues.
"""
from __future__ import annotations

import ast
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
EXPECTED_TABLES = (
    'users', 'projects', 'project_members', 'project_files', 'chats',
    'tasks', 'chat_messages', 'project_memory', 'project_stages',
    'github_repo_links',
)


def source_app_version() -> str | None:
    """Extract literal version from AST; importing app.main would MODIFY DB."""
    try:
        root = ast.parse((BASE / 'app' / 'main.py').read_text(encoding='utf-8'))
        for node in root.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == 'APP_VERSION' for t in node.targets
            ):
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    return node.value.value
    except (OSError, SyntaxError):
        pass
    return None


def is_readable_by_others(path: Path) -> bool | None:
    if not path.exists():
        return None
    return bool(stat.S_IMODE(path.stat().st_mode) & 0o077)


def run_audit() -> dict:
    result = {
        'audit_at_utc': datetime.now(timezone.utc).isoformat(),
        'read_only': True,
        'application_version_on_disk': source_app_version(),
        'root_matches_cwd': Path.cwd().resolve() == BASE,
        'env_present': (BASE / '.env').is_file(),
        'storage_present': (BASE / 'storage').is_dir(),
        'env_group_or_world_access': is_readable_by_others(BASE / '.env'),
        'storage_group_or_world_access': is_readable_by_others(BASE / 'storage'),
        'external_http_storage_access': 'NOT_TESTED',
        'backup_restore_test': 'NOT_TESTED',
        'production_login_test': 'NOT_TESTED',
        'browser_acceptance_test': 'NOT_TESTED',
    }

    try:
        from dotenv import dotenv_values
        from sqlalchemy import create_engine, inspect, text
        from sqlalchemy.engine import make_url
        config = dict(dotenv_values(BASE / '.env')) if (BASE / '.env').is_file() else {}
        config.update(os.environ)
        secret = config.get('APP_SECRET') or ''
        result['production_mode'] = config.get('KAREL_ENV') == 'production'
        result['https_app_url'] = str(config.get('APP_URL') or '').startswith('https://')
        result['https_only_sessions'] = str(config.get('SESSION_HTTPS_ONLY', 'true')).lower() in ('true', '1', 'yes', 'on')
        result['session_secret_configured'] = (
            len(secret) >= 32 and secret not in ('change-me', 'CHANGE_ME_TO_A_LONG_RANDOM_SECRET')
        )
        result['github_owner_allowlist_configured'] = bool(config.get('GITHUB_ALLOWED_OWNERS'))
        result['github_read_token_configured'] = bool(config.get('GITHUB_READ_TOKEN'))
        result['manifest_host_allowlist_configured'] = bool(config.get('MANIFEST_ALLOWED_HOSTS'))
        result['source_host_allowlist_configured'] = bool(config.get('SOURCE_ALLOWED_HOSTS'))

        database_url = config.get('DATABASE_URL') or ''
        if not database_url:
            result['database_status'] = 'NOT_CONFIGURED'
            return result
        url = make_url(database_url)
        result['database_driver'] = url.get_backend_name()
        if url.get_backend_name() == 'sqlite':
            path = Path(url.database or '')
            if str(path) in ('', ':memory:') or not path.is_file():
                result['database_status'] = 'SQLITE_FILE_NOT_FOUND'
                return result
        engine = create_engine(database_url, pool_pre_ping=True)
        try:
            with engine.connect() as connection:
                if url.get_backend_name() == 'sqlite':
                    connection.exec_driver_sql('PRAGMA query_only = ON')
                connection.execute(text('SELECT 1'))
                tables = set(inspect(connection).get_table_names())
                result['database_status'] = 'CONNECTED'
                result['expected_tables_present'] = {name: name in tables for name in EXPECTED_TABLES}
                result['row_counts_only'] = {
                    name: int(connection.execute(text('SELECT COUNT(*) FROM ' + name)).scalar() or 0)
                    for name in EXPECTED_TABLES if name in tables
                }
        finally:
            engine.dispose()
    except Exception as exc:
        # Do not include any exception string: DB drivers may echo credentials/hosts.
        result['audit_error_class'] = type(exc).__name__
        result['database_status'] = 'ERROR'

    return result


if __name__ == '__main__':
    print(json.dumps(run_audit(), ensure_ascii=False, indent=2))
