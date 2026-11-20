"""A real, read-only GitHub audit directly from Karel's chat.

Never assume a remote GitHub mutation or a full code audit. Bound fresh reads,
cache by project, and use deterministic source-backed output for audit requests.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from sqlalchemy import select

from ..config import settings
from ..models import GitHubRepoLink, Project, User
from .github_connector import GitHubReader, GitHubSyncError
from .github_snapshot_codec import decode_snapshot, GitHubSnapshotCodecError
from .github_snapshot_store import upsert_snapshot

SELF_REPO = "soufekladislav/Karel"
SELF_PROJECT_NAMES = {"developer karel", "karel", "karel developer"}
SUBJECTS = ("github", "repozitář", "repozitar", "repo ", "issue",
            "pull request", "větv", "vetv", "commit", "zdrojov",
            "kódu", "kodu", "kód ", "kod ", "svou app karel")
ACTIONS = ("projdi", "projít", "projit", "procház", "prochaz",
           "prověř", "prover", "zkontroluj", "zkontrolov", "audit", "reviz",
           "zrevid", "očisti", "ocisti", "úklid", "uklid", "vysvětli", "vysvetli",
           "co je", "co umí", "co umi", "dodělat", "dodelat")


def is_capabilities_question(query: str) -> bool:
    q = str(query or "").casefold().strip()
    return ("co už umíš" in q or "co uz umis" in q or
            "co všechno umíš" in q or "co vsechno umis" in q)


def capabilities_reply() -> str:
    return (
        "## Co umím skutečně dnes\n\n"
        "Pracuji s lokálními projektovými úkoly, chaty, dokumentací a "
        "schvalováním interních změn. Umím spustit **omezené čtení GitHubu** "
        "u projektu s ověřenou vazbou: získat vybrané dokumenty, Issues, PR a "
        "CI, uvést zdroje a označit neúplná data. Přes Fresh AI Engine "
        "mohu připravovat textové analýzy. Fresh Core nabízí čtecí "
        "inventuru WordPressu po ověření přístupu.\n\n"
        "**Co zatím neumím samostatně dokončit:** kompletně projít "
        "každý zdrojový soubor, bezpečně měnit/uzavírat GitHub Issues, "
        "slučovat větve, zadat skutečné programování Codexu, nasadit "
        "testovací či produkční verzi nebo prokázat jejich provoz. "
        "U těchto kroků zatím nabízím jen návrh, ne předstírané provedení.\n\n"
        "Mohu začít omezeným živým přehledem GitHubu tohoto projektu "
        "a ukázat, co jsem opravdu přečetl."
    )


def is_audit_request(query: str) -> bool:
    q = str(query or "").casefold()
    return any(t in q for t in SUBJECTS) and any(t in q for t in ACTIONS)


def _superadmin(user: User) -> bool:
    email = str(getattr(user, "email", "") or "").strip().casefold()
    return bool(getattr(user, "role", "") == "superadmin" or (
        settings.superadmin_email and
        email == settings.superadmin_email.strip().casefold()
    ))


def repository_for_project(db, project: Project, user: User) -> tuple[str | None, str]:
    link = db.scalar(select(GitHubRepoLink).where(GitHubRepoLink.project_id == project.id))
    if link and link.repository_full_name:
        return link.repository_full_name, "linked"
    name = " ".join(str(project.name or "").strip().casefold().split())
    if _superadmin(user) and name in SELF_PROJECT_NAMES:
        return SELF_REPO, "self_project"
    return None, "unlinked"


def _candidates(snapshot: dict) -> list[str]:
    out = []
    for file_path in (snapshot.get("source_tree") or []):
        low = str(file_path).lower()
        if low.endswith((".db", ".sqlite", ".sqlite3", ".log", ".lock", ".pyc")) or (
                low.startswith(("tmp/", "storage/", "__pycache__/", ".pytest_cache/"))):
            out.append(str(file_path))
    return out[:8]


def report(snapshot: dict, freshness: str) -> str:
    repo = snapshot.get("repository") or "(nezjištěno)"
    base = "https://github.com/" + repo
    counts = snapshot.get("counts") or {}
    partial = snapshot.get("partial") or {}
    sha = str(snapshot.get("source_commit_sha") or "")
    lines = [
        "## Ověřený GitHub přehled: " + repo,
        "Zdroj: " + base + " | Načteno: " + str(snapshot.get("fetched_at") or "?") +
        " | " + freshness,
        "Výchozí větev: " + str(snapshot.get("default_branch") or "?") +
        " | HEAD: " + (sha[:12] if sha else "neověřen"),
    ]
    desc = str(snapshot.get("description") or "").strip()
    if desc:
        lines.append("\n**Popis repozitáře:** " + desc[:400])
    docs = snapshot.get("documentation_excerpts") or []
    if docs:
        lines.append("\n**Doložené informace z projektové dokumentace:**")
        for doc in docs[:3]:
            text = str(doc.get("excerpt") or "").strip()
            if not text:
                continue
            lines.append("\n" + str(doc.get("path")) + " — " + str(doc.get("url")) +
                         " (blob SHA " + str(doc.get("sha") or "")[:12] + ")")
            lines.append(text[:1350] +
                         ("\n[Text je zkrácený.]" if len(text) > 1350 or
                          doc.get("excerpt_truncated") else ""))
    else:
        lines.append("\n**Obsah dokumentace není ověřen.** Nemohu jej vydávat za přečtený.")

    lines.extend((
        "\n**Zjištěný stav GitHubu:**",
        "- Issues: " + str(counts.get("issues_loaded", "?")) + " načtených / " +
        str(counts.get("open_issues", "?")) + " otevřených",
        "- PR: " + str(counts.get("prs_loaded", "?")) + " načtených / " +
        str(counts.get("open_prs", "?")) + " otevřených",
        "- Projects v2: " + str(snapshot.get("projects_v2_status") or "?") +
        " | CI běhy: " + str(counts.get("workflow_runs", "?")),
    ))
    opened = [x for x in (snapshot.get("issues") or []) if x.get("state") == "open"]
    if opened:
        lines.append("\n**Otevřené úkoly, které mohu věcně zrevidovat:**")
        for issue in opened[:9]:
            lines.append("- #" + str(issue.get("number")) + " " +
                         str(issue.get("title") or "bez názvu")[:130] +
                         " — " + str(issue.get("url") or base))
        if len(opened) > 9:
            lines.append("... dalších " + str(len(opened)-9) + " v načteném výběru.")
    else:
        lines.append("\nV načtené sadě nejsou otevřené Issues; to neprokazuje dokončený vývoj.")

    candidates = _candidates(snapshot)
    if candidates:
        lines.append("\n**Soubory k prověření při úklidu (zatím nic nemažu):**")
        lines.extend("- " + p[:220] for p in candidates)
    else:
        lines.append("\nV omezeném seznamu souborů se nenašly zjevné provozní artefakty.")
    limited = [key for key, value in partial.items() if value]
    if limited:
        lines.append("POZOR: Neúplná data: " + ", ".join(limited) + ".")
    lines.append(
        "\n**Rozsah této kontroly:** načetl jsem omezený seznam Issues, PR, CI, "
        "souborů a nejvýše 3 vybrané dokumenty (dokumentace: " +
        str(snapshot.get("documentation_status") or "nezjištěno") + "). "
        "Neprovedl jsem analýzu všech zdrojových souborů, běh aplikace, "
        "kontrolu všech větví ani odstranění balastu. "
        "Návrh úklidu lze posoudit po podrobné kontrole konkrétních souborů."
    )
    return "\n".join(lines)


def audit_for_chat(db, project: Project, user: User, *,
                   reader_factory=GitHubReader) -> tuple[str, str]:
    repo, binding = repository_for_project(db, project, user)
    if not repo:
        return (
            "Tento projekt nemá potvrzenou vazbu na GitHub repozitář. "
            "Zatím nemohu bezpečně určit, který mu patří. Otevři "
            "/projects/" + str(project.id) + "/github a připoj ho jednou; "
            "pak už se na jeho adresu nebudu ptát.", "unlinked"
        )
    link = db.scalar(select(GitHubRepoLink).where(GitHubRepoLink.project_id == project.id))
    cached = decode_snapshot(link.snapshot_json) if link else {}
    if (link and link.repository_full_name.casefold() == repo.casefold()
            and link.last_synced_at and cached.get("documentation_status")
            and datetime.utcnow() - link.last_synced_at < timedelta(minutes=5)):
        return report(cached, "ověřený uložený snímek do 5 minut"), "cached"

    owner = repo.split("/", 1)[0]
    authorized_owners = {p.strip().casefold()
                         for p in settings.github_allowed_owners.split(",") if p.strip()}
    token = (settings.github_read_token if _superadmin(user) and
             owner.casefold() in authorized_owners else "")
    try:
        with reader_factory(token=token) as reader:
            snapshot = reader.snapshot(repo, owner)
        if snapshot.get("private") and not token:
            raise GitHubSyncError("Soukromý repozitář není pro uživatele autorizovaný.")
        occupied = db.scalar(select(GitHubRepoLink).join(
            Project, Project.id == GitHubRepoLink.project_id
        ).where(Project.owner_id == project.owner_id,
                GitHubRepoLink.project_id != project.id,
                GitHubRepoLink.repository_full_name == repo))
        if link or not occupied:
            try:
                upsert_snapshot(db, project.id, user.id, snapshot)
            except GitHubSnapshotCodecError:
                db.rollback()
                return report(snapshot, "živé čtení, cache nebyla uložena"), "ephemeral"
        return report(snapshot, "ověřeno živým GitHub API"), "live"
    except GitHubSyncError as exc:
        if cached.get("repository") == repo:
            return ("Živý GitHub audit selhal: " + str(exc) +
                    "\nNásleduje pouze starší snímek, ne aktuální stav:\n\n" +
                    report(cached, "STARŠÍ CACHE")), "stale"
        return ("Repozitář " + repo + " jsem zjistil, ale jeho živé čtení selhalo: "
                + str(exc) + ". O změny v GitHubu jsem se nepokoušel."), "failed"
