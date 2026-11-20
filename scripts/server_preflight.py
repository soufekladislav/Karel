"""Karel server preflight: safe diagnostics; never displays credentials."""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
required = (
    ("fastapi", "fastapi"), ("sqlalchemy", "SQLAlchemy"),
    ("pymysql", "PyMySQL"), ("httpx", "httpx"), ("jinja2", "Jinja2"),
    ("dotenv", "python-dotenv"), ("a2wsgi", "a2wsgi"),
    ("cryptography", "cryptography"), ("pypdf", "pypdf"),
)

def main() -> int:
    print("Karel – kontrola Python prostředí (žádné klíče se netisknou)")
    print("Python:", sys.version.split()[0])
    print("Spouštěč:", sys.executable)
    print("Root:", ROOT)
    print("Passenger WSGI:", (ROOT / "passenger_wsgi.py").is_file())
    print("Aplikace:", (ROOT / "app" / "main.py").is_file())
    print("Konfigurace .env:", "existuje" if (ROOT / ".env").exists() else "není v rootu")
    missing = []
    for module, package in required:
        try:
            importlib.import_module(module)
            print(f"  {package}: OK")
        except (ImportError, OSError) as exc:
            missing.append(package)
            print(f"  {package}: NEDOSTUPNÉ ({type(exc).__name__})")
    if missing:
        print("K nápravě použijte přímo Python stejného Passenger venv:")
        print("  python -m pip install -r requirements.txt")
        print("Poté restartujte aplikaci v cPanelu.")
        return 1
    print("Základní moduly: OK. Pokud server stále vrací 500, přečtěte stderr")
    print("aplikace v Passenger/cPanel; tento test neověřuje DB ani HTTP.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
