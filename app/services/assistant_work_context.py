"""Current screen and authoritative project data for Karel's assistant.

Never fetch the application's own URL through SOURCE_ALLOWED_HOSTS.
The browser sends only a screen name and optional selected record; the server
verifies that every source belongs to the currently authorized project.
"""
from __future__ import annotations

import json
import re
from sqlalchemy import select, func

from ..models import (
    Project, User, Task, ProjectMemory, GitHubRepoLink, LibraryItem,
    ProjectFile, ProjectEvent,
)
from .project_timeline import load_project_timeline
from .github_schedule_publisher import latest_sync_status

SCREENS = {
    "chat": "Chat", "development": "Pipeline projektu", "tasks": "Úkoly",
    "docs": "Zadání a dokumentace", "github": "GitHub",
    "website": "Můj WordPress", "testing": "Testování",
    "releases": "Release", "outputs": "Výstupy", "history": "Historie",
    "files": "Soubory", "components": "Komponenty",
    "manage": "Správa projektu", "settings": "Nastavení projektu",
    "library": "Knihovna", "portfolio": "Přehled projektů",
    "account": "Můj účet", "admin": "Administrace",
}
_SPEC_KINDS = ("purpose", "business_goal", "functional_goal",
               "project_scope", "project_deadline", "project_plan")


def clean_screen(value: str) -> str:
    return value if value in SCREENS else "chat"


def _short(value, maximum=180):
    return " ".join(str(value or "").split())[:maximum]


def screen_evidence(db, project: Project, user: User,
                    screen: str = "chat", focus: str = "") -> dict:
    screen = clean_screen(screen)
    lines = [
        "VIDITELNÁ OBRAZOVKA: " + SCREENS[screen],
        "AKTIVNÍ PROJEKT: " + project.name + " (ID " + str(project.id) + ")",
        "Jde o interní data databáze projektu, nikoliv nové online ověření.",
    ]
    details: list[str] = []
    if screen in ("development", "chat", "testing", "releases", "history"):
        link = db.scalar(select(GitHubRepoLink).where(
            GitHubRepoLink.project_id == project.id))
        plan = load_project_timeline(
            db, project, is_admin=True,
            linked_repo=link.repository_full_name if link else None,
        )
        if plan.get("items"):
            status = "schválená" if plan.get("approved") else "pouze návrh"
            lines.append("PIPELINE: " + status)
            details.append("Pipeline: " + status + ", " +
                           str(len(plan["items"])) + " milníků")
            for item in plan["items"][:15]:
                lines.append(
                    " - " + item["id"] + ": " +
                    _short(item["title"], 90) + ", termín " +
                    str(item["due_date"]) + ", stav " + str(item.get("status")))
            sync = latest_sync_status(db, project.id)
            lines.append("GITHUB PUBLIKACE PIPELINE: " +
                         str(sync.get("state") or "neznámá"))
        else:
            lines.append("PIPELINE: nemá schválená datumovaná data.")
    if screen in ("docs", "chat"):
        rows = db.scalars(select(ProjectMemory).where(
            ProjectMemory.project_id == project.id,
            ProjectMemory.kind.in_(_SPEC_KINDS),
            ProjectMemory.verified == True,
        ).order_by(ProjectMemory.id.desc()).limit(28)).all()
        seen = set()
        for row in rows:
            if row.kind in seen:
                continue
            seen.add(row.kind)
            lines.append("ZADÁNÍ " + row.kind + ": " + _short(row.content, 480))
        details.append("Zadání: " + str(len(seen)) + " oblastí")
    if screen in ("tasks", "development", "testing", "chat"):
        rows = db.scalars(select(Task).where(
            Task.project_id == project.id
        ).order_by(Task.updated_at.desc(), Task.id.desc()).limit(22)).all()
        counts = {}
        for row in rows:
            counts[row.status] = counts.get(row.status, 0) + 1
        details.append("Úkoly v přehledu: " + str(len(rows)))
        lines.append("AKTUÁLNÍ ÚKOLY (max. 22 podle poslední změny):")
        for row in rows:
            lines.append(
                " - TASK-" + str(row.id) + " [" + row.status +
                "] " + _short(row.title, 160))
    if screen == "github":
        link = db.scalar(select(GitHubRepoLink).where(
            GitHubRepoLink.project_id == project.id))
        if link:
            lines.append("PŘIPOJENÝ REPOZITÁŘ: " +
                         _short(link.repository_full_name, 160))
            lines.append("POSLEDNÍ SYNCHRONIZACE: " +
                         str(link.last_synced_at or "neověřená"))
            details.append("GitHub: poslední uložený snímek")
        else:
            lines.append("GITHUB: žádný repozitář není u projektu navázán.")
    if screen == "website":
        url = db.scalar(select(ProjectMemory).where(
            ProjectMemory.project_id == project.id,
            ProjectMemory.kind == "wordpress_site_url",
        ).order_by(ProjectMemory.id.desc()))
        if url:
            lines.append("WORDPRESS URL UVEDENÁ UŽIVATELEM (neověřená): " +
                         _short(url.content, 260))
        snap = db.scalar(select(ProjectMemory).where(
            ProjectMemory.project_id == project.id,
            ProjectMemory.kind == "fresh_core_snapshot", ProjectMemory.verified == True,
        ).order_by(ProjectMemory.id.desc()))
        lines.append("FRESH CORE SNAPSHOT: " +
                     (str(snap.created_at) if snap else "není načten"))
    if screen in ("files", "releases", "outputs"):
        files = db.scalars(select(ProjectFile).where(
            ProjectFile.project_id == project.id,
        ).order_by(ProjectFile.id.desc()).limit(16)).all()
        for item in files:
            lines.append("SOUBOR " + str(item.id) + " [" + item.kind +
                         ", " + item.status + "]: " + _short(item.name))
    if screen == "library":
        count = db.scalar(select(func.count(LibraryItem.id)).where(
            LibraryItem.owner_id == user.id)) or 0
        details.append("Knihovna účtu: " + str(count) + " položek")
        lines.append("KNIHOVNA UŽIVATELE: počet položek " + str(count))
    if screen in ("history", "admin"):
        events = db.scalars(select(ProjectEvent).where(
            ProjectEvent.project_id == project.id,
        ).order_by(ProjectEvent.id.desc()).limit(10)).all()
        for item in events:
            lines.append("UDÁLOST: " + str(item.id) + " [" +
                         _short(item.event_type, 90) + "] " + str(item.created_at))
    if focus and re.fullmatch(r"task:\d{1,10}", focus) and screen == "tasks":
        task_id = int(focus.split(":")[1])
        task = db.get(Task, task_id)
        if task and task.project_id == project.id:
            lines.extend([
                "UŽIVATEL PRÁVĚ PRACUJE S ÚKOLEM TASK-" + str(task.id),
                "Název: " + _short(task.title, 250),
                "Stav: " + task.status,
                "Popis: " + _short(task.description, 900),
            ])
            details.append("Vybraný úkol: TASK-" + str(task.id))
    elif focus and re.fullmatch(r"milestone:M[0-9]{1,2}", focus) and screen == "development":
        lines.append("UŽIVATEL UVEDL ZAMĚŘENÍ NA MILNÍK " +
                     focus.split(":")[1] + ". Ověř jej ve výše uvedené Pipeline.")
    lines.append(
        "KONTEXT JE VÝCHOZÍ HINT. Neodvozuj z něj automaticky souhlas "
        "s úpravou; změnu prováděj pouze dostupnou schvalovací akcí. "
        "Nikdy netvrď, že byla změna uložena, pokud backend nevrátil důkaz."
    )
    return {
        "screen": screen, "label": SCREENS[screen],
        "summary": " · ".join(details[:3]) or "Projekt: " + project.name,
        "context": "\n".join(lines)[:11500],
    }
