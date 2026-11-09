"""Quick deployment diagnostic. Run from the application root with the venv active."""
import sys
from sqlalchemy import text, inspect

try:
    from app.config import settings
    from app.database import engine
    from app.bootstrap import initialize_app
except Exception as exc:
    print(f'IMPORT ERROR: {type(exc).__name__}: {exc}')
    sys.exit(2)

print('Karel 2.0 deployment check')
print('APP_URL:', settings.app_url)
print('DB driver:', settings.database_url.split(':',1)[0])
print('Engine URL configured:', bool(settings.engine_url))
print('Engine API key configured:', bool(settings.engine_api_key))

state = initialize_app()
print('Bootstrap:', state)
if not state.get('ok'):
    sys.exit(3)

with engine.connect() as conn:
    print('DB SELECT 1:', conn.execute(text('SELECT 1')).scalar())

names = sorted(inspect(engine).get_table_names())
print('Tables:', ', '.join(names))
print('OK')
