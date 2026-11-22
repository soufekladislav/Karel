"""Prevent free-form AI text from impersonating execution evidence."""
from __future__ import annotations

import re

WRITE_INTENT = (
    "zaprac", "zapiš", "zapis", "ulož", "uloz", "nastav",
    "proveď", "proved", "přidej", "pridej", "aktualiz", "změň",
    "zmen", "zaimplementuj", "upravit do", "oprav v",
)
CLAIM = re.compile(
    r"(?i)\b(?:zapracováno|uloženo|provedeno|"
    r"uložil jsem|zapsal jsem|upravil jsem|provedl jsem|"
    r"změnil jsem|změna byla provedena)\b"
)


def qualify_unverified_reply(user_message: str, reply: str, *,
                             pending_actions: bool) -> str:
    """Only a real action result can assert a verified modification.

    This is called solely on the fallback AI route where no action executes.
    Keep analysis useful but put a deterministic, truthful state first.
    """
    content = str(reply or "").strip()
    wants_write = any(term in (user_message or "").casefold()
                      for term in WRITE_INTENT)
    if not wants_write:
        return content
    status = (
        "**STAV: Připraven návrh ke schválení. Zatím nic nebylo změněno.**"
        if pending_actions else
        "**STAV: Neprovedeno – zatím nevznikl žádný ověřený zápis "
        "ani schvalovací akce.**"
    )
    if CLAIM.search(content):
        content = CLAIM.sub("připraveno jako návrh (neověřeno)", content)
    return status + "\n\n" + content
