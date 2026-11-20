"""Conversational milestone replanning with deterministic calendar dates.

The user negotiates the target in chat; the backend derives a bounded,
testable proposal. Approval is a separate action and never mutates GitHub.
This first workflow is scoped to Karel's established seven-milestone roadmap.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from sqlalchemy import select
from ..models import Message, ProjectMemory
from .project_timeline import load_project_timeline, normalize_milestones
from .github_chat_audit import repository_for_project, _superadmin

class ReplanError(ValueError):
    pass

DATE_REQUEST = re.compile(
    r"(?<!\d)(\d{1,2})\s*\.\s*(\d{1,2})(?:\s*\.\s*((?:20)?\d{2}))?(?!\d)"
)

def is_replan_request(message: str) -> bool:
    q = (message or "").casefold()
    subject = any(x in q for x in (
        "harmonogram", "časov", "casov", "termín", "termin", "milník", "milnik",
        "testovací verz", "testovaci verz", "do 20.12",
    ))
    intent = any(x in q for x in (
        "probr", "nastav", "zaprac", "aktualiz", "změn", "zmen",
        "posu", "přeplán", "preplan", "chtěl", "chtel", "chci",
        "dokonč", "dokonc", "dotáhl", "dotahl", "zkrát", "zkrat",
        "není", "neni", "uprav",
    ))
    return subject and intent

def _request_date(message: str, *, today: date) -> date | None:
    # A free-standing date is too ambiguous: only accept a target after
    # a deadline/time-to-completion expression, never a date in an unrelated
    # imported README or issue number.
    text = (message or "").casefold()
    match = DATE_REQUEST.search(text)
    if not match:
        return None
    prefix = text[max(0, match.start() - 100): match.start()]
    if not any(x in prefix for x in (
        "do ", "k ", "nejpozději ", "ideálně ", "idealne ",
        "termín ", "termin ", "testovací ", "testovaci ",
    )):
        return None
    day, month = int(match.group(1)), int(match.group(2))
    year_part = match.group(3)
    if year_part:
        yr = int(year_part)
        yr = yr + 2000 if yr < 100 else yr
    else:
        yr = today.year
        try:
            if date(yr, month, day) < today:
                yr += 1
        except ValueError as exc:
            raise ReplanError("Uvedené datum není platné.") from exc
    try:
        return date(yr, month, day)
    except ValueError as exc:
        raise ReplanError("Uvedené datum není platné.") from exc

def _chat_target(db, chat_id: int, message: Message, *, today: date) -> date:
    direct = _request_date(message.content, today=today)
    if direct:
        return direct
    # Resolve anaphora in "Fajn, zapracuj to do harmonogramu" from *recent*
    # user messages in THIS same chat, never from assistant's invented dates.
    history = db.scalars(select(Message).where(
        Message.chat_id == chat_id, Message.id < message.id,
        Message.role == "user",
    ).order_by(Message.id.desc()).limit(12)).all()
    for prior in history:
        target = _request_date(prior.content, today=today)
        if target and is_replan_request(prior.content):
            return target
    raise ReplanError(
        "V poslední domluvě nevidím konkrétní cílový termín. "
        "Napiš například: Funkční testovací verze do 20.12.2026.")

def _next_weekday(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d

def _prev_weekday(d: date) -> date:
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d

def _date_string(d: date) -> str:
    return d.strftime("%d.%m.%Y")

def _generate_milestones(milestones: list[dict], target: date, today: date) -> list[dict]:
    by_id = {m["id"]: dict(m) for m in milestones}
    required = {f"M{i}" for i in range(7)}
    if set(by_id) != required:
        raise ReplanError(
            "Aktuální harmonogram má jinou strukturu. "
            "Nechci automaticky přeplánovat neznámé milníky.")
    if target <= today + timedelta(days=20):
        raise ReplanError(
            "Na nový termín nezbývá prostor pro jednotlivé přejímky. "
            "Nejdřív musíme schválit menší rozsah nebo navýšit kapacitu.")
    start = date.fromisoformat(by_id["M0"]["start_date"])
    d0 = _prev_weekday(target - timedelta(days=23))
    d1 = _prev_weekday(target - timedelta(days=16))
    d2 = _prev_weekday(target - timedelta(days=9))
    d3 = _prev_weekday(target - timedelta(days=4))
    if not start <= d0 < d1 < d2 < d3 < target:
        raise ReplanError("Zvolený termín nedovoluje zachovat závislosti plánu.")
    long_test_end = _prev_weekday(target + timedelta(days=33))
    prod_start = _next_weekday(long_test_end + timedelta(days=1))
    prod_end = _next_weekday(long_test_end + timedelta(days=7))
    timeline = [
        (start, d0),
        (_next_weekday(d0 + timedelta(days=1)), d1),
        (_next_weekday(d1 + timedelta(days=1)), d2),
        (_next_weekday(d2 + timedelta(days=1)), d3),
        (_next_weekday(d3 + timedelta(days=1)), target),
        (_next_weekday(target + timedelta(days=1)), long_test_end),
        (prod_start, prod_end),
    ]
    if any(a > b for a, b in timeline):
        raise ReplanError("Přeplánování by vytvořilo neplatnou návaznost.")
    for i, (start_date, end_date) in enumerate(timeline):
        m = by_id[f"M{i}"]
        m["start_date"], m["due_date"] = start_date.isoformat(), end_date.isoformat()
        m["status"] = "planned" if m.get("status") not in ("completed",) else "completed"
        if i == 4:
            m["title"] = "Funkční testovací verze Karla"
            m["acceptance"] = (
                "Hlavní vývojové scénáře Karel → GitHub → Fresh AI Engine / Codex "
                "musí projít funkčními testy. Vývoj připravit nejpozději "
                + _date_string(_prev_weekday(target)) +
                "; " + _date_string(target) +
                " je cílový termín předání testerovi, nikoli potvrzený produkční release.")
            m["dependencies"] = "M3"
        if i == 5:
            m["title"] = "Rozšířené testování a stabilizace"
            m["acceptance"] = (
                "Dlouhodobé scénářové a regresní testy s uživatelem, "
                "evidence chyb, opravy, opakované ověření; během Vánoc "
                "počítat s omezenou kapacitou. Release blokují neúspěšné testy.")
            m["dependencies"] = "M4"
        if i == 6:
            m["title"] = "Produkční pilot po schválení"
            m["acceptance"] = (
                "Pouze po převzetí M5: záloha, kontrolované nasazení, "
                "health, ověření a možnost rollbacku.")
            m["dependencies"] = "M5"
        if i == 3:
            m["acceptance"] = (
                "Schválené operace v GitHub Issues, řízení stavů "
                "a konkrétní ověřený zápis. Bez CI a schválení neprovádět merge.")
        if i == 0:
            m["acceptance"] = (
                "Uzavření rozsahu MVP, skutečný audit bezpečnosti, GitHubu "
                "a produkčního Exonu, rozlišení hotových a neověřených funkcí.")
    return normalize_milestones([by_id[f"M{i}"] for i in range(7)])

def prepare_replan(db, project, chat, user, message: Message,
                   *, today: date | None = None) -> dict:
    today = today or date.today()
    if " ".join((project.name or "").casefold().split()) not in (
            "karel", "developer karel"):
        raise ReplanError(
            "Přeplánování jiných projektů zatím není ověřené. "
            "Nemohu automaticky použít časovou osu Karla.")
    repo, _ = repository_for_project(db, project, user)
    if not _superadmin(user) or repo != "soufekladislav/Karel":
        raise ReplanError("Nemáš ověřený přístup k harmonogramu tohoto projektu.")
    target = _chat_target(db, chat.id, message, today=today)
    approved_row = db.scalar(select(ProjectMemory).where(
        ProjectMemory.project_id == project.id,
        ProjectMemory.kind == "project_schedule",
        ProjectMemory.verified == True,
    ).order_by(ProjectMemory.id.desc()))
    base = load_project_timeline(
        db, project, is_admin=True, linked_repo="soufekladislav/Karel"
    )
    if not base["items"]:
        raise ReplanError("V projektu nemám ani ověřený, ani návrhový harmonogram.")
    source = "approved" if approved_row else base["source"]
    milestones = _generate_milestones(base["items"], target, today)
    # Trust model is explicit: this is a USER-NEGOTIATED change, never
    # a claim that an external GitHub document or Issues were updated.
    return {
        "source": "user_chat_replan",
        "repo": "soufekladislav/Karel",
        "base_source": source,
        "baseline_approved_row_id": approved_row.id if approved_row else 0,
        "target_test_date": target.isoformat(),
        "source_commit_sha": "",
        "milestones": milestones,
    }

def preview_replan(payload: dict, old_items: list[dict]) -> str:
    older = {x["id"]: x for x in old_items}
    target = date.fromisoformat(payload["target_test_date"])
    text = [
        "## Návrh změny harmonogramu ke schválení",
        "**Funkční testovací verze do " + _date_string(target) + ".** "
        "Pokud termín vychází na víkend, poslední vývojové změny "
        "musí být připravené v předchozí pracovní den.",
        "Následné delší testování a stabilizace zůstávají samostatným milníkem.",
        "",
        "| Milník | Původní termín | Nový termín |",
        "|---|---|---|",
    ]
    for m in payload["milestones"]:
        old = older.get(m["id"], {})
        text.append("| " + m["id"] + " – " + m["title"] +
                    " | " + str(old.get("due_date") or "bez termínu") +
                    " | **" + m["due_date"] + "** |")
    text += [
        "",
        "**Zatím jsem nezměnil uloženou Pipeline ani GitHub Issues.**",
        "Schval tento konkrétní návrh. Po potvrzení ho zapíšu do "
        "Projektové paměti jako novou verzi a ověřím skutečné datumy v Pipeline.",
        "GitHub zápisy do Issues/Projects nejsou hotové a nebudu je předstírat.",
        "Termíny jsou cíl s předpokladem jednoho vývojového proudu, "
        "nikoli záruka kapacity či výsledku.",
    ]
    return "\n".join(text)
