"""AI Engine draft for existing Project Map approval flow."""
from __future__ import annotations
import json, re
from sqlalchemy import select
from ..models import Chat, Message, ProjectMemory, GitHubRepoLink
from .github_snapshot_codec import decode_snapshot

FIELDS = ("purpose", "business_goal", "functional_goal", "project_scope", "project_plan")
LABELS = dict(zip(FIELDS, ("Účel", "Obchodní cíl", "Funkční zadání", "Rozsah", "Plán a milníky")))
LIMIT = dict(zip(FIELDS, (500, 700, 1600, 1000, 1600)))

class SpecDraftError(ValueError):
    pass

def is_spec_request(message):
    q = (message or "").lower()
    target = ("zadání", "zadani", "projektovou mapu", "vývojový plán",
              "vyvojovy plan", "plán projektu", "plan projektu", "funkční celky",
              "priority projektu", "priority vývoje", "milníky", "milniky")
    verb = ("sestav", "připrav", "priprav", "vytvoř", "vytvor", "zpracuj",
            "zapiš", "zapis", "ulož", "uloz", "vytěž", "vytez")
    return any(t in q for t in target) and any(t in q for t in verb) and not any(
        t in q for t in ("jen obchodní", "pouze obchodní", "jen účel", "jen ucel"))

def existing_spec(db, project_id):
    rows = db.scalars(select(ProjectMemory).where(
        ProjectMemory.project_id == project_id, ProjectMemory.kind.in_(FIELDS),
        ProjectMemory.verified == True
    ).order_by(ProjectMemory.id.desc())).all()
    result = {}
    for row in rows:
        result.setdefault(row.kind, row.content)
    return result

def sources(db, project):
    parts = ["Aktivní projekt: " + project.name,
             "Popis projektu: " + str(project.description or "")[:600]]
    old = existing_spec(db, project.id)
    for key, value in old.items():
        parts.append("Schválené " + key + ": " + str(value)[:750])
    link = db.scalar(select(GitHubRepoLink).where(GitHubRepoLink.project_id == project.id))
    if link:
        snap = decode_snapshot(link.snapshot_json)
        if snap.get("repository"):
            parts.append("Ověřený GitHub: " + snap["repository"] +
                         ", revize " + str(snap.get("source_commit_sha") or "nezjištěna"))
            for doc in (snap.get("documentation_excerpts") or [])[:3]:
                parts.append("Externí dokument " + str(doc.get("path")) + ": " +
                             str(doc.get("excerpt") or "")[:1250])
    rows = db.scalars(select(Message).join(Chat, Message.chat_id == Chat.id).where(
        Chat.project_id == project.id, Message.role == "user"
    ).order_by(Message.id.desc()).limit(85)).all()
    budget, chosen = 9000, []
    for row in rows:
        text = (row.content or "").strip()
        if len(text) < 25:
            continue
        block = "UŽIVATEL: " + text[:1100]
        if budget - len(block) < 0:
            break
        budget -= len(block)
        chosen.append(block)
    parts.extend(reversed(chosen))
    return "\n\n".join(parts)[-13500:]

def prompt(project_name):
    return (
        "Jsi projektový analytik Karla. Vytvoř stručný NÁVRH strukturovaného "
        "zadání projektu " + project_name + " pouze z dodaných podkladů. "
        "Nepleť aktuálně fungující funkce s cílovými. "
        "Odděl obchodní smysl, funkce, rozsah a testovatelné milníky. "
        "Plán má mít 3 až 5 funkčních celků s akceptačními podmínkami. "
        "Nevymýšlej termíny ani hotové funkce. Chybějící informace označ jako "
        "neověřené. Nic neukládej ani netvrď, že bylo uloženo. "
        "Vrať VÝHRADNĚ JSON objekt s pěti string poli: purpose, business_goal, "
        "functional_goal, project_scope, project_plan. "
        "Maximálně 350 znaků pro purpose, 400 pro business_goal, 900 pro "
        "functional_goal, 600 pro project_scope, 1100 pro project_plan. "
        "Žádný markdown ani bloky KAREL_STATE."
    )

def parse(raw, existing=None):
    text = str(raw or "").strip()
    fence = chr(96) * 3
    if text.startswith(fence):
        text = re.sub(r"^" + fence + r"(?:json)?\s*|\s*" + fence + r"$", "", text, flags=re.I).strip()
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise SpecDraftError("AI Engine nevrátil strukturované zadání; nic jsem neuložil.") from exc
    if not isinstance(data, dict):
        raise SpecDraftError("Výsledek není strukturovaná Projektová mapa.")
    draft = {}
    for field in FIELDS:
        value = data.get(field)
        if isinstance(value, str) and value.strip():
            value = re.sub(r"[\x00-\x08\x0b-\x1f]", " ", value).strip()
            draft[field] = value[:LIMIT[field]]
    if len(draft) < 3 or not draft.get("purpose") or not draft.get("functional_goal"):
        raise SpecDraftError("Návrh zadání není kompletní; databázi jsem neměnil.")
    existing = existing or {}
    return {key: value for key, value in draft.items()
            if value != str(existing.get(key) or "").strip()}

def preview(changes):
    lines = ["## Návrh projektového zadání ke schválení",
             "Nic ještě není uloženo jako schválené zadání. "
             "Zkontroluj navržené změny:"]
    for key in FIELDS:
        if key in changes:
            lines.append("\n**" + LABELS[key] + "**\n" + changes[key])
    lines.append("\nPo tvém schválení Karel uloží data do existujících karet "
                 "Projektové mapy. Milníky jsou návrh, nikoliv hotové GitHub Issues.")
    return "\n".join(lines)
