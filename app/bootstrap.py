from __future__ import annotations

import traceback
from datetime import datetime, timezone
from sqlalchemy import select, text, inspect

from .config import settings
from .database import Base, engine, SessionLocal
from .models import User
from .auth import hash_password

_bootstrap_state = {
    'ok': False,
    'database': False,
    'schema': False,
    'admin': False,
    'error': None,
    'checked_at': None,
}


def initialize_app() -> dict:
    """Initialize DB/schema in a way that works under both ASGI and Passenger/WSGI.

    Never lets an initialization exception kill module import. The error is exposed by
    /healthz so a fresh deployment can be diagnosed without access to application logs.
    """
    state = {
        'ok': False,
        'database': False,
        'schema': False,
        'admin': False,
        'error': None,
        'checked_at': datetime.now(timezone.utc).isoformat(),
    }
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        state['database'] = True

        Base.metadata.create_all(engine)
        # Additive migration for installations created before Fresh Key project sharing.
        columns = {c['name'] for c in inspect(engine).get_columns('project_members')}
        if 'relationship' not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE project_members ADD COLUMN relationship VARCHAR(24) NOT NULL DEFAULT 'member'"))
        state['schema'] = True

        if settings.admin_email and settings.admin_password:
            with SessionLocal() as db:
                email = settings.admin_email.strip().lower()
                user = db.scalar(select(User).where(User.email == email))
                if not user:
                    db.add(User(
                        email=email,
                        name=settings.admin_name,
                        role='superadmin',
                        password_hash=hash_password(settings.admin_password),
                    ))
                    db.commit()
            state['admin'] = True
        else:
            # App can run without seed credentials, but /login will have no user yet.
            state['admin'] = False

        state['ok'] = True
    except Exception as exc:
        state['error'] = f'{type(exc).__name__}: {exc}'
        # Keep detailed traceback in stderr/server log, but not in public endpoint.
        traceback.print_exc()

    _bootstrap_state.clear()
    _bootstrap_state.update(state)
    return dict(_bootstrap_state)


def bootstrap_state() -> dict:
    return dict(_bootstrap_state)
