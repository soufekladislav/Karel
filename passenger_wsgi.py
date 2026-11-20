"""Passenger WSGI entry point, compatible with Python 3.10–3.13.

The old imp.load_source was removed in Python 3.12 and can cause
a server-wide HTTP 500 before the FastAPI application starts.
"""
import os
import sys

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from startup import application
