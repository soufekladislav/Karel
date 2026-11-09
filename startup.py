import os
import sys

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(APP_ROOT)

if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(APP_ROOT, ".env"))

from app.main import app as asgi_app

_wsgi_app = None

def application(environ, start_response):
    global _wsgi_app

    if _wsgi_app is None:
        from a2wsgi import ASGIMiddleware
        _wsgi_app = ASGIMiddleware(asgi_app)

    return _wsgi_app(environ, start_response)