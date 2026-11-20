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
from .schedule_feasibility import assess_replan

class ReplanError(ValueError):
    pass

DATE_REQUEST = re.compile(
    r"(?<!\d)(\d{1,2})\s*\.\s*(\d{1,2})(?:\s*\.\s*((?:20)?\d{2}))?(?!\d)"
)

def is_replan_request(message: str) -> bool:
    """Project planning intent; never confuse a GitHub Actions CI pipeline."""
    q = (message or "").casefold()
    subject = any(x in q for x in (
        "harmonogram", "časov", "casov", "termín", "termin",
        "milník", "milnik", "testovací verz", "testovaci verz",
        "projekt v pipeline", "v pipeline", "plán projektu",
        "dokončení karla", "dokončení projektu", "dokonceni karla",
    ))
    intent = any(x in q for x in (
        "probr", "nastav", "zaprac", "aktualiz", "změn", "zmen",
        "posu", "přeplán", "preplan", "chtěl", "chtel", "chci",
        "dokonč", "dokonc", "dotáhl", "dotahl", "zkrát", "zkrat",
        "není", "neni", "uprav", "oprav", "rozvrhn", "potvr",
        "nový", "novy", "nově", "nove", "stanov",
    ))
    return subject and intent

# The previous implementation accepted the FIRST date matching "do", which
# silently confused the old value with the newly requested deadline:
# "Máme nastaveno do 29.1., chci opravit do 20.12.2026".
# Compare the local language surrounding *every* date, instead.
_TARGET_VERB = re.compile(
    r"\b(?:chci|chtěl\w*|chtel\w*|ideálně|idealne|nejpozději|"
    r"nově|nove|cílově|cilove|oprav\w*|uprav\w*|změn\w*|zmen\w*|"
    r"posu\w*|přesu\w*|presu\w*|přeplán\w*|preplan\w*|"
    r"rozvrhn\w*|dokonč\w*|dokonc\w*|dotáhn\w*|dotahn\w*|"
    r"nastav\w*|potřeb\w*|potreb\w*)\b"
)
_OLD_VALUE = re.compile(
    r"\b(?:máme|mame|původn\w*|puvodn\w*|dosud|nyní|nyni|"
    r"současn\w*|soucasn\w*|teď|ted|nastaven\w*|bylo|"
    r"aktuáln\w*|aktualn\w*|místo|misto)\b"
)
_DATE_PREFIX = re.compile(r"(?:\bdo|\bna|\bk)\s*$")
_DISJUNCTION = re.compile(r"\b(?:nebo|anebo|či)\b")


def is_schedule_overview_request(message: str) -> bool:
    """Answer general "show/confirm the Pipeline" questions from real DB.

    An explicit proposed date belongs to the replanning path instead.
    """
    q = (message or "").casefold()
    if DATE_REQUEST.search(q):
        return False
    topic = any(x in q for x in (
        "v pipeline", "projekt v pipeline", "harmonogram",
        "termíny v pipeline", "terminy v pipeline",
    ))
    request = any(x in q for x in (
        "potvrdit", "potvrd", "ukaž", "ukaz", "zobraz", "jaké",
        "jake", "můžeš", "muzes", "uprav", "probrat",
    ))
    return topic and request and not any(
        x in q for x in ("zapracuj", "zapiš", "zapis", "ulož", "uloz",
                        "posuň", "posun", "změň na", "zmen na"))


def preview_current_schedule(view: dict, *, project_id: int,
                             pending_target: str = "") -> str:
    """Compact answer backed by Pipeline data, not old Project Map prose."""
    if not view.get("items"):
        return (
            "V Pipeline tohoto projektu zatím není datumovaný harmonogram. "
            "Vytvořme návrh s konkrétními termíny a po schválení jej uložme.")
    title = ("Schválený harmonogram" if view.get("approved")
             else "Předběžný, dosud neschválený harmonogram")
    lines = [
        "## " + title + " v Pipeline",
        "Toto jsou skutečně zobrazované milníky. "
        "Textový plán v Projektové mapě není autoritou pro datumy.",
        "", "| Milník | Termín |", "|---|---|",
    ]
    for item in view["items"]:
        lines.append("| " + item["id"] + " – " + item["title"] +
                     " | " + item["due_date"] + " |")
    if pending_target:
        lines.extend([
            "", "**Čeká návrh nového termínu " + pending_target +
            " na schválení.** Dokud ho nepotvrdíš, Pipeline se nemění.",
        ])
    lines.extend([
        "", "Otevři /projects/" + str(project_id) +
        "?view=development#project-timeline.",
        "Chceš-li změnu, napiš například: "
        "**Nový termín funkční testovací verze do 20.12.2026.** "
        "Karel ukáže rozdíl a vyžádá si schválení.",
        "GitHub Issues/Projects se zatím automaticky nepřepisují.",
    ])
    return "\n".join(lines)


def _resolve_date(match: re.Match, today: date) -> date:
    day, month = int(match.group(1)), int(match.group(2))
    part = match.group(3)
    if part:
        year = int(part)
        year = year + 2000 if year < 100 else year
    else:
        year = today.year
    try:
        proposed = date(year, month, day)
    except ValueError as exc:
        raise ReplanError("V požadavku je neplatné datum.") from exc
    if not part and proposed < today:
        try:
            proposed = date(year + 1, month, day)
        except ValueError as exc:
            raise ReplanError("Neplatný termín v následujícím roce.") from exc
    return proposed


def _request_date(message: str, *, today: date) -> date | None:
    """Return the EXPLICITLY requested new deadline, never the previous one.

    With multiple dates, a distinct change verb must be closest to the chosen
    date; ambiguous alternatives require clarification instead of a proposal.
    """
    text = (message or "").casefold()
    matches = list(DATE_REQUEST.finditer(text))
    if not matches:
        return None
    # "do 20.12. nebo do 27.12." is a choice, not an approval.
    if len(matches) > 1 and _DISJUNCTION.search(text[matches[0].end():]):
        raise ReplanError(
            "Vidím více alternativních termínů. Který jediný je nový cíl?")
    candidates = []
    previous_end = 0
    for match in matches:
        # Date-to-date clauses are separate. Only local context carries roles.
        left = text[max(previous_end, match.start()-120):match.start()]
        has_preposition = bool(_DATE_PREFIX.search(left))
        target_mentions = list(_TARGET_VERB.finditer(left))
        old_mentions = list(_OLD_VALUE.finditer(left))
        target_position = target_mentions[-1].start() if target_mentions else -1
        old_position = old_mentions[-1].start() if old_mentions else -1
        # If the nearest assertion describes a previous/current deadline,
        # that date is not a new target, even if the message discusses change.
        if has_preposition and target_position > old_position:
            candidates.append((match, target_position))
        elif len(matches) == 1 and not old_mentions and target_mentions:
            # User may write "Chtěl bych Karla dokončit 20.12." without "do".
            candidates.append((match, target_position))
        previous_end = match.end()
    if not candidates:
        if len(matches) >= 2:
            raise ReplanError(
                "Ze zmíněných datumů neumím bezpečně poznat nový termín. "
                "Napiš například: Nový cíl testovací verze je 20.12.2026.")
        return None
    if len(candidates) != 1:
        raise ReplanError(
            "V požadavku je více možných nových termínů. "
            "Potvrď jeden konkrétní nový termín.")
    return _resolve_date(candidates[0][0], today)


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
            m["title"] = "Omezené testovací MVP Karla"
            m["acceptance"] = (
                "Omezené MVP: projektový chat, zadání, schvalování Pipeline, "
                "ověřený GitHub READ a publikování harmonogramu do GitHub dokumentu. "
                "Plná automatizace Issues/Projects, Codex, staging a produkce "
                "jsou mimo tuto přejímku. Vývoj připravit nejpozději "
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
            m["title"] = "Schvalování a GitHub publikace harmonogramu"
            m["acceptance"] = (
                "Backend schvaluje a verzovaně ukládá Pipeline; "
                "schválená verze se ověřeně publikuje do GitHub dokumentu. "
                "Zápisy polí Issues/Projects v2 a automatický merge jsou mimo MVP.")
        if i == 0:
            m["acceptance"] = (
                "Uzavření rozsahu MVP, skutečný audit bezpečnosti, GitHubu "
                "a produkčního Exonu, rozlišení hotových a neověřených funkcí.")
    return normalize_milestones([by_id[f"M{i}"] for i in range(7)])

def prepare_replan(db, project, chat, user, message: Message,
                   *, today: date | None = None, scope: str = 'limited_mvp') -> dict:
    today = today or date.today()
    if " ".join((project.name or "").casefold().split()) not in (
            "karel", "developer karel"):
        raise ReplanError(
            "Přeplánování jiných projektů zatím není ověřené. "
            "Nemohu automaticky použít časovou osu Karla.")
    repo, _ = repository_for_project(db, project, user)
    if not _superadmin(user) or repo != "soufekladislav/Karel":
        raise ReplanError("Nemáš ověřený přístup k harmonogramu tohoto projektu.")
    if scope != 'limited_mvp':
        raise ReplanError(
            'Bez výslovné volby omezeného MVP nelze tento krátký '
            'harmonogram předložit ke schválení.')
    target = _chat_target(db, chat.id, message, today=today)
    feasibility = assess_replan(db, project.id, target, today)
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
        "scope": "limited_mvp",
        "risk_acknowledged": True,
        "feasibility": feasibility,
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
        "**Rozsah: omezené testovací MVP, nikoli kompletně autonomní Karel.**",
        "Není doložená kapacita, proto jde o ambiciózní cíl vyžadující "
        "postupné technické přejímky.",
        "",
        "**Hlavní rizika:**",
    ]
    for warning in payload.get("feasibility", {}).get("warnings", []):
        text.append("- " + str(warning))
    text.extend([
        "",
        "| Milník | Původní termín | Nový termín |",
        "|---|---|---|",
    ])
    for m in payload["milestones"]:
        old = older.get(m["id"], {})
        text.append("| " + m["id"] + " – " + m["title"] +
                    " | " + str(old.get("due_date") or "bez termínu") +
                    " | **" + m["due_date"] + "** |")
    text += [
        "",
        "**Rozhodnutí ke schválení:** přijímáš omezený rozsah MVP a "
        "uvedená rizika. Plnou autonomizaci Codexu, Github Projects v2 a "
        "nasazování tím neschvaluješ jako hotové.",
        "**Zatím jsem nezměnil uloženou Pipeline ani GitHub Issues.**",
        "Schval tento konkrétní návrh. Po potvrzení ho zapíšu do "
        "Projektové paměti jako novou verzi a ověřím skutečné datumy v Pipeline.",
        "GitHub zápisy do Issues/Projects nejsou hotové a nebudu je předstírat.",
        "Termíny jsou cíl s předpokladem jednoho vývojového proudu, "
        "nikoli záruka kapacity či výsledku.",
    ]
    return "\n".join(text)
