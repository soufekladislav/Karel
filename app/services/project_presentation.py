"""Human-friendly summaries for Karel screens; never invent completion states.

All functions are pure and have no database or network side effects. Dashboard
and project detail must share these rules instead of producing competing status.
"""
from __future__ import annotations

import json
import re


def brief(text: str | None, limit: int = 190, fallback: str = "") -> str:
    """Preview a long legacy project brief without overwriting the real text."""
    if not text or not str(text).strip():
        return fallback
    lines = [
        re.sub(r"^[\s•*\-–\d.)]+", "", line).strip()
        for line in str(text).replace("\r", "\n").split("\n")
    ]
    skip = {
        "účel karla", "účel projektu", "obchodní cíl", "hlavní funkce",
        "funkční zadání", "poslání", "zadání projektu", "stav", "priorita",
        "závazné principy", "definice", "rozsah projektu",
    }
    chosen = ""
    for line in lines:
        if not line:
            continue
        heading = re.sub(r"\s*:\s*$", "", line).lower()
        if heading in skip or line.endswith(":"):
            continue
        chosen = line
        break
    if not chosen:
        return fallback
    chosen = re.sub(r"\s+", " ", chosen).strip()
    return chosen if len(chosen) <= limit else chosen[:max(1,limit-1)].rsplit(" ",1)[0].rstrip(".,;: ") + "…"


def github_connection_state(link, owners_configured: bool) -> dict[str, str]:
    """Differentiate unconfigured, unlinked, stale/error and truly synced."""
    if not owners_configured:
        return {
            "kind": "setup", "label": "Vyžaduje nastavení",
            "detail": "Správce dosud nepovolil vlastníky repozitářů.",
        }
    if link is None:
        return {
            "kind": "unlinked", "label": "Nepřipojeno",
            "detail": "Projekt zatím nemá přiřazený GitHub repozitář.",
        }
    if getattr(link, "last_error", None):
        return {
            "kind": "error", "label": "Chyba synchronizace",
            "detail": "Poslední pokus o načtení skončil chybou. Starší snímek může být neaktuální.",
        }
    if not getattr(link, "last_synced_at", None):
        return {
            "kind": "pending", "label": "Čeká na synchronizaci",
            "detail": "Repozitář je přiřazen, ale nemá potvrzený první snímek.",
        }
    try:
        snapshot = json.loads(getattr(link, "snapshot_json", "") or "{}")
        if not isinstance(snapshot, dict) or not snapshot.get("repository"):
            # Old snapshots may only contain html_url and counts; accept actual
            # loaded data but never mark an empty object as synchronized.
            if not isinstance(snapshot, dict) or not (
                snapshot.get("html_url") and isinstance(snapshot.get("counts"), dict)
            ):
                raise ValueError("Missing snapshot")
    except (ValueError, TypeError):
        return {
            "kind": "pending", "label": "Snímek není ověřen",
            "detail": "Záznam synchronizace existuje, ale chybí platný snímek dat.",
        }
    return {
        "kind": "synced", "label": "Synchronizováno",
        "detail": "Poslední úspěšný snímek byl uložen. Nejde o živý přenos.",
    }


def project_next_step(spec: dict, counts: dict, github: dict,
                      stage_alerts: list | None = None, *,
                      mode: str = "general", fresh_connected: bool = False) -> dict[str, str]:
    """One factual, actionable recommendation – no fabricated milestones."""
    if counts.get("waiting_user", 0):
        n = counts["waiting_user"]
        return {"label": f"Zkontrolovat úkoly čekající na tebe ({n})",
                "href": "tasks", "kind": "attention"}
    if counts.get("failed", 0):
        n = counts["failed"]
        return {"label": f"Prověřit úkoly s chybou ({n})",
                "href": "tasks", "kind": "attention"}
    for alert in stage_alerts or []:
        if alert.get("days", 0) < 0:
            return {"label": "Prověřit termín projektového workflow",
                    "href": "development", "kind": "attention"}
    if mode == "github" and github.get("kind") == "error":
        return {"label": "Prověřit chybu GitHub synchronizace",
                "href": "github", "kind": "attention"}
    if counts.get("working", 0) or counts.get("testing", 0) or counts.get("todo", 0):
        return {"label": "Projít aktuální úkoly a další postup",
                "href": "tasks", "kind": "normal"}
    if mode == "wordpress" and not fresh_connected:
        return {"label": "Připojit Fresh Core a načíst stav webu",
                "href": "website", "kind": "setup"}
    if mode == "wordpress" and not (spec.get("business_goal") or spec.get("purpose")):
        return {"label": "Navrhnout cíl z načtených dat webu",
                "href": "chat", "kind": "normal"}
    if mode == "github" and github.get("kind") != "synced":
        return {"label": "Připojit GitHub a načíst existující projekt",
                "href": "github", "kind": "setup"}
    if not (spec.get("business_goal") or spec.get("purpose")):
        return {"label": "Představit projekt Karlovi v chatu",
                "href": "chat", "kind": "setup"}
    if github.get("kind") == "error":
        return {"label": "Prověřit chybu GitHub synchronizace",
                "href": "github", "kind": "attention"}
    return {"label": "Probrat další krok s Karlem",
            "href": "chat", "kind": "normal"}
