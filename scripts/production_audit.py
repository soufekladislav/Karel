"""Read-only production inspection. Run from deployed Karel app root.
python scripts/production_audit.py > karel-audit.json
Never exports secrets, row contents, message bodies or filenames.
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

def main():
    result = {
        "audit_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "deployed_server_readonly",
        "cwd_is_app_root": Path.cwd().resolve() == BASE,
        "env_present": (BASE / ".env").is_file(),
        "storage_dir_present": (BASE / "storage").is_dir(),
    }
    try:
        from sqlalchemy import inspect, text
        from app.config import settings
        from app.database import engine
        from app.main import APP_VERSION
        result["app_version"] = APP_VERSION
        result["github_owners_configured"] = bool(settings.github_allowed_owners)
        result["github_token_configured"] = bool(settings.github_read_token)
        result["engine_configured"] = bool(settings.engine_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            inspector = inspect(conn)
            tables = set(inspector.get_table_names())
            result["database_connection"] = "ok"
            expected = ["users", "projects", "tasks", "chat_messages",
                        "project_memory", "project_stages", "github_repo_links"]
            result["tables_present"] = {t: t in tables for t in expected}
            counts = {}
            for t in expected:
                if t in tables:
                    try:
                        counts[t] = int(conn.execute(text("SELECT COUNT(*) FROM " + t)).scalar() or 0)
                    except Exception:
                        counts[t] = "read_unavailable"
            result["row_counts_only"] = counts
    except Exception as exc:
        result["audit_status"] = "incomplete"
        result["error_type"] = type(exc).__name__
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
