"""Passenger startup must not crash if optional Fresh Core crypto is missing."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PassengerStartupTests(unittest.TestCase):
    def test_import_passenger_when_cryptography_is_not_installed(self):
        # Simulates a developer copying code to Exon without pip installing
        # the *new* dependency. The site must still start and the connector
        # must explain how to complete the Python environment.
        script = """
import builtins
original_import = builtins.__import__

def no_crypto(name, *args, **kwargs):
    if name == 'cryptography' or name.startswith('cryptography.'):
        raise ModuleNotFoundError("No module named 'cryptography'")
    return original_import(name, *args, **kwargs)

builtins.__import__ = no_crypto
from passenger_wsgi import application
assert callable(application), 'Passenger entrypoint is unavailable'
from app.services.fresh_core_vault import _fernet_class, VaultUnavailable
try:
    _fernet_class()
except VaultUnavailable as exc:
    assert 'cryptography' in str(exc)
else:
    raise AssertionError('Missing dependency was not detected')
print('PASS: Passenger imports without optional Fresh Core dependency')
"""
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, DATABASE_URL="sqlite:///" + tmp + "/boot.sqlite",
                       APP_URL="http://localhost:8000", KAREL_ENV="development",
                       SESSION_HTTPS_ONLY="false")
            completed = subprocess.run([sys.executable, "-c", script], cwd=ROOT,
                                       env=env, capture_output=True, text=True,
                                       timeout=35)
        self.assertEqual(completed.returncode, 0,
                         completed.stdout[-1600:] + "\n" + completed.stderr[-4500:])

    def test_passenger_entrypoint_does_not_import_removed_imp(self):
        script = (ROOT / "passenger_wsgi.py").read_text(encoding="utf-8")
        self.assertNotIn("import imp", script)
        self.assertIn("from startup import application", script)


if __name__ == "__main__":
    unittest.main()
