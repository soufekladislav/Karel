"""Stable private encryption key for Fresh Core (not a WordPress credential).

Prefer FRESH_CORE_VAULT_KEY from the server environment. For a single-tenant
Passenger development install, an explicit first connection can create a
0600 Fernet key in a 0700 directory in the *user's home*, outside the app
DocumentRoot and Git checkout. Never regenerate an existing invalid vault.
"""
from __future__ import annotations
import os
import stat
from pathlib import Path

from ..config import settings


class VaultUnavailable(ValueError):
    pass


def _fernet_class():
    """Import the optional connector dependency only when needed.

    A server that has not installed cryptography must still start Karel and
    show its normal UI rather than returning HTTP 500 on every request.
    """
    try:
        from cryptography.fernet import Fernet
        return Fernet
    except ImportError as exc:
        raise VaultUnavailable(
            "Na serveru chybí knihovna cryptography. Správce musí spustit "
            "pip install -r requirements.txt v Python prostředí Karla."
        ) from exc


def _validate_key(value: str) -> str:
    try:
        raw = value.strip().encode("ascii")
        _fernet_class()(raw)
        if len(raw) != 44:
            raise ValueError()
        return raw.decode("ascii")
    except VaultUnavailable:
        raise
    except (ValueError, TypeError, UnicodeError) as exc:
        raise VaultUnavailable("Fresh Core vault key má neplatný formát.") from exc


def _path() -> Path:
    # Home is outside the Passenger application root, not /storage under the
    # URL-served application folder. A production administrator should still
    # verify DocumentRoot containment and back up this file.
    return Path.home() / ".freshcrackers-karel-private" / "fresh-core-vault.key"


def active_key(*, create: bool = False) -> str:
    configured = str(getattr(settings, "fresh_core_vault_key", "") or "").strip()
    if configured:
        return _validate_key(configured)
    p = _path()
    if create:
        try:
            p.parent.mkdir(mode=0o700, parents=False, exist_ok=True)
            if p.parent.is_symlink() or not p.parent.is_dir():
                raise VaultUnavailable("Adresář trezoru není bezpečný.")
            os.chmod(p.parent, 0o700)
            try:
                descriptor = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                     getattr(os, "O_NOFOLLOW", 0), 0o600)
            except FileExistsError:
                descriptor = None
            if descriptor is not None:
                try:
                    with os.fdopen(descriptor, "wb") as handle:
                        handle.write(_fernet_class().generate_key())
                        handle.flush()
                        os.fsync(handle.fileno())
                except BaseException:
                    p.unlink(missing_ok=True)
                    raise
        except VaultUnavailable:
            raise
        except OSError as exc:
            raise VaultUnavailable(
                "Na serveru se nepodařilo připravit bezpečný trezor. "
                "Správce může nastavit FRESH_CORE_VAULT_KEY v .env."
            ) from exc
    try:
        if p.parent.is_symlink():
            raise VaultUnavailable("Adresář trezoru nesmí být symbolický odkaz.")
        details = p.lstat()
        if not stat.S_ISREG(details.st_mode) or details.st_mode & 0o077:
            raise VaultUnavailable("Soubor trezoru nemá soukromá oprávnění (0600).")
        if hasattr(os, "getuid") and details.st_uid != os.getuid():
            raise VaultUnavailable("Soubor trezoru nepatří uživateli aplikace.")
        return _validate_key(p.read_text(encoding="ascii"))
    except (OSError, UnicodeError) as exc:
        raise VaultUnavailable(
            "Fresh Core vault není připraven. Vytvoří se při prvním připojení "
            "nebo jej správce nastaví v .env."
        ) from exc


def is_ready() -> bool:
    try:
        active_key()
        return True
    except VaultUnavailable:
        return False
