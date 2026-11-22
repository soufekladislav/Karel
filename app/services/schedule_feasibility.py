"""Scope-and-risk gate for Karel's dated project commitments.

A fast requested deadline is not proof that all integrations are finished.
Source data may be incomplete: never treat open issues as verified feature
completion, and never claim to have measured engineer capacity.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from sqlalchemy import select

from ..models import GitHubRepoLink
from .github_snapshot_codec import decode_snapshot, GitHubSnapshotCodecError


def _normalize(text: str) -> str:
    return " ".join(str(text or "").casefold().split())


def selected_scope(text: str) -> str:
    q = _normalize(text)
    if any(w in q for w in (
        "kompletní", "kompletni", "celý karel", "cely karel",
        "plnou verzi", "hotovou aplikaci", "všechny funkce",
        "vsechny funkce", "bez omezení", "bez omezeni",
        "variantu b", "varianta b", "variantou b",
    )):
        return "full"
    if any(w in q for w in (
        "variantu a", "varianta a", "variantou a", "omezené mvp", "omezene mvp",
        "omezenou testovací", "omezenou testovaci",
        "mvp", "minimální verzi", "minimalni verzi",
        "jen základ", "jen zaklad", "základní verzi",
        "funkční testovací verze", "funkcni testovaci verze",
        "funkční testovací verzi", "funkcni testovaci verzi",
        "omezeném testování", "omezenem testovani",
        "omezeným testováním", "omezenym testovanim",
        "omezeném předprodukčním", "omezenem predprodukcnim",
    )):
        return "limited_mvp"
    return "unspecified"


def is_scope_choice(text: str) -> bool:
    q = _normalize(text)
    return (selected_scope(q) in ("limited_mvp", "full") and
            any(w in q for w in (
                "volím", "volim", "beru ", "vybírám", "vybiram",
                "souhlasím", "souhlasim", "chci variantu", "potvrzuji variantu",
            )))


def _weekday_count(start: date, end: date) -> int:
    """Monday–Friday only; holidays and absences make this an upper bound."""
    if end < start:
        return 0
    cursor = start
    days = 0
    while cursor <= end:
        if cursor.weekday() < 5:
            days += 1
        cursor += timedelta(days=1)
    return days


def _snapshot_issue_context(db, project_id: int) -> dict:
    row = db.scalar(select(GitHubRepoLink).where(
        GitHubRepoLink.project_id == project_id))
    if not row or row.repository_full_name != "soufekladislav/Karel":
        return {"issue_count": None, "source_date": None, "verified": False}
    try:
        snapshot = decode_snapshot(row.snapshot_json)
    except (ValueError, TypeError, GitHubSnapshotCodecError):
        snapshot = {}
    if snapshot.get("repository") != "soufekladislav/Karel":
        return {"issue_count": None, "source_date": None, "verified": False}
    count = (snapshot.get("counts") or {}).get("open_issues")
    if not isinstance(count, int) or count < 0:
        count = None
    return {
        "issue_count": count,
        "source_date": row.last_synced_at.isoformat() if row.last_synced_at else None,
        "verified": bool(row.last_synced_at and count is not None),
    }


def assess_replan(db, project_id: int, target: date, today: date) -> dict:
    """Evidence-limited risk report; decision belongs to the human."""
    working_days = _weekday_count(today, target)
    issue_context = _snapshot_issue_context(db, project_id)
    items = [
        "Zkrácení kalendáře není zkrácením práce. "
        "Pro každý milník chybí ověřená kapacita, odhad zbývající práce a výsledek přejímky.",
        "GitHub Issues/Projects zapisování a přenos termínů nejsou v aktuálním "
        "Karlově konektoru dokončené; samotný GitHub snapshot je jen čtení.",
        "End-to-end Codex → CI → staging → uživatelská přejímka → produkce "
        "není doložený jako plně provozně ověřený proces.",
    ]
    if target.weekday() >= 5:
        previous_workday = target
        while previous_workday.weekday() >= 5:
            previous_workday -= timedelta(days=1)
        items.insert(0, "Požadované datum připadá na víkend. "
                     "Vývojový výstup musí být připraven nejpozději "
                     + previous_workday.strftime("%d.%m.%Y") + ".")
    if issue_context["issue_count"] is not None:
        items.append(
            "Poslední lokální GitHub snapshot eviduje " +
            str(issue_context["issue_count"]) + " otevřených Issues "
            "(neprokazuje jejich pracnost ani aktuální stav).")
    else:
        items.append("Aktuální počet otevřených GitHub Issues nemám v "
                     "tomto projektovém snapshotu spolehlivě ověřený.")
    if working_days <= 25:
        items.append(
            "Zbývá nanejvýš " + str(working_days) +
            " pracovních dnů bez odečtu svátků, dovolených a oprav. "
            "Úplnou funkčnost proto nelze pro tento termín označit za ověřeně reálnou.")
    return {
        "risk": "high" if working_days <= 30 else "unverified",
        "working_days_upper_bound": working_days,
        "issues": issue_context,
        "warnings": items,
        "mvp_scope": [
            "Spolehlivý projektový chat, zadání a schvalování změn",
            "Závazná datumovaná Pipeline v Karlovi a verzovaná historie",
            "Ověřené čtení GitHubu a zveřejnění schválené časové osy do GitHub dokumentu",
            "Základní testy a předání uživateli k pilotnímu ověření",
        ],
        "mvp_exclusions": [
            "Plný GitHub Projects v2/Issues obousměrný zápis",
            "Samostatné programování Codexu bez ověřené fronty a výsledku",
            "Autonomní nasazení do testovacího i ostrého prostředí",
        ],
        "assessment_basis": "deadline_and_known_integration_gaps",
    }


def risk_dialogue(target: date, assessment: dict, *,
                  requested_scope: str = "unspecified") -> str:
    days = assessment["working_days_upper_bound"]
    lines = [
        "## Termín " + target.strftime("%d.%m.%Y") + " – posouzení proveditelnosti",
        "Rozumím požadavku zkrátit projekt. Než změníme závaznou Pipeline, "
        "musíme se shodnout, **co přesně v termínu skutečně převezmeš**.",
        "Do požadovaného termínu zbývá nanejvýš " + str(days) +
        " pracovních dnů (zatím bez svátků a rezerv).",
        "",
        "**Rizika, která nemohu zamlčet:**",
    ]
    for w in assessment["warnings"]:
        lines.append("- " + w)
    lines.extend([
        "",
        "**Varianta A – omezené testovací MVP do " +
        target.strftime("%d.%m.%Y") + ".**",
        "Obsah: " + "; ".join(assessment["mvp_scope"]) + ".",
        "Mimo tuto přejímku: " + "; ".join(assessment["mvp_exclusions"]) + ".",
        "Je to **ambiciózní pracovní cíl**, ne potvrzená realistická kapacita.",
        "",
        "**Varianta B – kompletní Karel.**",
        "Termín nelze poctivě určit, dokud neověříme rozsah "
        "otevřených Issues, práci Codexu, testovací prostředí a "
        "rychlost skutečného vývoje. Připravíme nejprve odhady a kritickou cestu.",
        "",
        "Nyní **není žádný nový plán připravený ke schválení ani uložený**.",
        "Napiš například **„Volím variantu A (omezené MVP)“**, "
        "nebo **„Chci variantu B – celý projekt“**. "
        "Podle rozhodnutí připravím harmonogram s přejímkami a dopady.",
    ])
    if requested_scope == "full":
        lines.insert(3, "**Kompletní rozsah do tohoto data nyní nemohu doložit jako proveditelný.**")
        # The user has already chosen full scope. Do not loop through
        # A/B choices again; move into an evidence gathering step.
        lines = [line for line in lines if not line.startswith(
            "Napiš například **„Volím variantu A")]
        lines.extend([
            "Zvolil jsi celý rozsah. Nyní je potřeba z GitHubu převzít "
            "ověřené úkoly, odhady a kritickou cestu. Níže uvedu živý "
            "GitHub přehled a jeho omezení; termín plné verze zatím neukládám.",
        ])
    return "\n".join(lines)
