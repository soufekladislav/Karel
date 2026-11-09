from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

class Settings:
    app_name = os.getenv('APP_NAME', 'Karel 2.0')
    app_url = os.getenv('APP_URL', 'http://localhost:8000').rstrip('/')
    secret = os.getenv('APP_SECRET', 'change-me')
    database_url = os.getenv('DATABASE_URL', f"sqlite:///{BASE_DIR / 'storage/karel2.db'}")
    admin_email = os.getenv('ADMIN_EMAIL', '')
    admin_password = os.getenv('ADMIN_PASSWORD', '')
    admin_name = os.getenv('ADMIN_NAME', 'Administrátor')
    superadmin_email = os.getenv('SUPERADMIN_EMAIL', 'soufek@freshcrackers.cz').strip().lower()
    engine_url = os.getenv('FRESH_AI_ENGINE_URL', '').rstrip('/')
    engine_chat_path = os.getenv('FRESH_AI_ENGINE_CHAT_PATH', '/v1/engine/run')
    engine_health_path = os.getenv('FRESH_AI_ENGINE_HEALTH_PATH', '/v1/health')
    engine_api_key = os.getenv('FRESH_AI_ENGINE_API_KEY', '')
    engine_model = os.getenv('FRESH_AI_ENGINE_MODEL', 'karel')
    engine_mode = os.getenv('FRESH_AI_ENGINE_MODE', 'fresh').lower()
    engine_timeout = int(os.getenv('FRESH_AI_ENGINE_TIMEOUT', '180'))
    engine_retries = int(os.getenv('FRESH_AI_ENGINE_RETRIES', '3'))
    max_upload_mb = int(os.getenv('MAX_UPLOAD_MB', '100'))
    https_only = os.getenv('SESSION_HTTPS_ONLY', 'true').lower() in ('1','true','yes','on')
    storage_dir = BASE_DIR / 'storage'
    uploads_dir = storage_dir / 'uploads'
    workspaces_dir = storage_dir / 'workspaces'
    outputs_dir = storage_dir / 'outputs'

settings = Settings()
for p in (settings.storage_dir, settings.uploads_dir, settings.workspaces_dir, settings.outputs_dir):
    p.mkdir(parents=True, exist_ok=True)
