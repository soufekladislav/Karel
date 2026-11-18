"""Explicit schema migration with mandatory, recent backup evidence.

DEFAULT: read-only inspection. Never imports app.main or runs application startup.

Preview:
    python scripts/schema_migration.py
Apply only after a real, restorable backup of the exact Exon database:
    python scripts/schema_migration.py --apply --backup-file /secure/backups/karel-db-backup.sql

This script creates only missing SQLAlchemy tables and adds the previously
supported relationship field; it does not drop tables or delete rows.
DDL can auto-commit in MariaDB, so a verified backup and rollback procedure
are mandatory before using --apply.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def inspect_schema(engine, metadata) -> dict:
    from sqlalchemy import inspect
    inspector = inspect(engine)
    present = set(inspector.get_table_names())
    missing = sorted(set(metadata.tables) - present)
    project_member_columns = (
        {c['name'] for c in inspector.get_columns('project_members')}
        if 'project_members' in present else set()
    )
    return {
        'missing_tables': missing,
        'add_relationship': 'project_members' in present and 'relationship' not in project_member_columns,
        'has_existing_tables': bool(present),
        'ready': not missing and ('project_members' not in present or 'relationship' in project_member_columns),
    }


def ensure_backup_file(path: str) -> None:
    backup = Path(path)
    if not backup.is_file() or backup.stat().st_size < 1024:
        raise ValueError('Záloha databáze chybí nebo je prázdná.')
    if time.time() - backup.stat().st_mtime > 24 * 3600:
        raise ValueError('Záloha musí být vytvořena nejvýše před 24 hodinami.')
    if backup.resolve().is_relative_to(ROOT):
        raise ValueError('Záloha musí být mimo kořen aplikace a veřejný web.')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true', help='Explicitně povolit změnu schématu')
    parser.add_argument('--backup-file', default='', help='Cesta k aktuální záloze mimo web root')
    args = parser.parse_args()

    from app.database import engine, Base
    from app import models  # noqa: F401 – register model tables, no app.main import
    from sqlalchemy import inspect, text

    plan = inspect_schema(engine, Base.metadata)
    result = {'mode': 'APPLY' if args.apply else 'PREVIEW_READ_ONLY',
              'plan': plan, 'backup_restore_verified': False}
    if not args.apply:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    try:
        ensure_backup_file(args.backup_file)
        # Even if an actual backup file exists, this cannot verify restorability.
        if plan['missing_tables']:
            Base.metadata.create_all(engine, checkfirst=True)
        if plan['add_relationship']:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE project_members ADD COLUMN relationship "
                    "VARCHAR(24) NOT NULL DEFAULT 'member'"
                ))
        result['after'] = inspect_schema(engine, Base.metadata)
        result['completed'] = bool(result['after']['ready'])
    except Exception as exc:
        result['completed'] = False
        # Avoid leaking credentials, hostnames or SQL in driver exception text.
        result['error_class'] = type(exc).__name__
    finally:
        engine.dispose()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get('completed') else 2


if __name__ == '__main__':
    raise SystemExit(main())
