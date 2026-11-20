"""Build an approvable timeline from the REAL, pinned GitHub source.

This is the self-project Karel pilot. Source content is untrusted, bounded and
validated; a local release fallback displayed in Pipeline is never substituted
for a live GitHub read when requesting approval.
"""
from __future__ import annotations
import base64
import binascii
import hashlib
import re
from urllib.parse import quote
from ..config import settings
from .github_chat_audit import repository_for_project, _superadmin
from .github_connector import GitHubReader, GitHubSyncError
from .project_timeline import parse_checked_in_schedule, normalize_milestones

SOURCE_REPO = "soufekladislav/Karel"
SOURCE_PATH = "docs/PROJECT_SCHEDULE.md"
MAX_BYTES = 48 * 1024

class ScheduleReadError(RuntimeError):
    pass

def is_schedule_request(question: str) -> bool:
    q = re.sub(r"\s+", " ", (question or "").casefold())
    topic = any(t in q for t in ("časov", "casov", "harmonogram", "milník", "milnik",
                                 "termínov", "terminov", "timeline"))
    action = any(t in q for t in ("připrav", "priprav", "připravo", "pripravo",
                                  "sestav", "naplán", "naplan", "podívej", "podivej",
                                  "projdi", "udělej", "udelej", "vytvoř", "vytvor",
                                  "ukaž", "ukaz"))
    return topic and action

def _credentials(user) -> str:
    owners = {s.strip().casefold() for s in
              settings.github_allowed_owners.split(",") if s.strip()}
    if (_superadmin(user) and
            SOURCE_REPO.split("/")[0].casefold() in owners):
        return settings.github_read_token
    return ""

def read_live_karel_schedule(db, project, user, *, reader_factory=GitHubReader) -> dict:
    repo, _ = repository_for_project(db, project, user)
    # Never silently apply Karel's calendar to another customer's project.
    if repo != SOURCE_REPO or not _superadmin(user) or (
            " ".join((project.name or "").casefold().split()) not in
            {"karel", "developer karel"}):
        raise ScheduleReadError(
            "Pro tento projekt zatím nemám ověřený zdroj datumového harmonogramu "
            "v GitHubu. Výchozí plán Karla nelze použít v jiném projektu.")
    base = "/repos/" + quote(repo, safe="/")
    try:
        with reader_factory(token=_credentials(user)) as reader:
            info = reader._request("GET", base)
            if not isinstance(info, dict) or (
                    str(info.get("full_name") or "").casefold() != repo.casefold()):
                raise ScheduleReadError("GitHub nevrátil ověřenou identitu repozitáře.")
            branch = str(info.get("default_branch") or "main")
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", branch):
                raise ScheduleReadError("GitHub vrátil neplatnou výchozí větev.")
            latest = reader._request("GET", base + "/branches/" + quote(branch, safe=""))
            if not isinstance(latest, dict):
                raise ScheduleReadError("GitHub nevrátil ověřenou výchozí revizi.")
            sha = str((latest.get("commit") or {}).get("sha") or "")
            if not re.fullmatch(r"[a-fA-F0-9]{40}", sha):
                raise ScheduleReadError("Nepodařilo se ověřit HEAD GitHubu.")
            obj = reader._request(
                "GET", base + "/contents/" + SOURCE_PATH,
                params={"ref": sha}, optional=True)
    except GitHubSyncError as exc:
        raise ScheduleReadError("Čtení GitHubu selhalo: " + str(exc)) from exc
    if not isinstance(obj, dict) or obj.get("type") != "file":
        raise ScheduleReadError(
            "V GitHubu chybí docs/PROJECT_SCHEDULE.md. "
            "Žádný plán jsem nevytvořil ani neuložil.")
    size = obj.get("size")
    if (not isinstance(size, int) or size < 1 or size > MAX_BYTES or
            obj.get("encoding") != "base64" or
            not isinstance(obj.get("content"), str)):
        raise ScheduleReadError("GitHub harmonogram není použitelný textový soubor.")
    try:
        raw = base64.b64decode("".join(obj["content"].split()), validate=True)
        if len(raw) != size:
            raise ValueError("size mismatch")
        digest = hashlib.sha1(
            b"blob " + str(len(raw)).encode("ascii") + b"\x00" + raw
        ).hexdigest()
        if str(obj.get("sha") or "").lower() != digest:
            raise ValueError("blob sha mismatch")
        text = raw.decode("utf-8")
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ScheduleReadError(
            "Obsah nebo SHA harmonogramu z GitHubu nelze ověřit."
        ) from exc
    milestones = normalize_milestones(parse_checked_in_schedule(text))
    if len(milestones) < 2:
        raise ScheduleReadError(
            "GitHub dokument neobsahuje dostatek validních datumovaných milníků. "
            "Návrh jsem nezapsal.")
    return {
        "source": "github_verified_document",
        "repo": repo,
        "ref": branch,
        "source_commit_sha": sha.lower(),
        "source_blob_sha": digest,
        "source_path": SOURCE_PATH,
        "source_url": ("https://github.com/" + repo + "/blob/" +
                       quote(sha, safe="") + "/" + SOURCE_PATH),
        "milestones": milestones,
    }

def preview_schedule(schedule: dict) -> str:
    items = schedule["milestones"]
    lines = [
        "## Harmonogram projektu Karel – návrh ke schválení",
        "Skutečně jsem načetl GitHub repozitář " + schedule["repo"] +
        " na revizi " + schedule["source_commit_sha"][:12] + ".",
        "Zdroj: " + schedule["source_url"],
        "",
        "| Milník | Od | Do | Přejímací výsledek |",
        "|---|---|---|---|",
    ]
    for item in items:
        title = str(item["title"]).replace("|", " ").replace("\n", " ")
        acceptance = str(item["acceptance"]).replace("|", " ").replace("\n", " ")
        lines.append("| " + item["id"] + " – " + title +
                     " | " + item["start_date"] + " | " +
                     item["due_date"] + " | " + acceptance[:125] + " |")
    lines += [
        "",
        "**Toto je návrh, ne schválený plán.**",
        "Připravil jsem schvalovací akci. Po tvém potvrzení jej uložím "
        "jako novou verzi harmonogramu a prokazatelně zobrazím v Pipeline.",
        "Do GitHub Issues/Projects nic nezapisuji: automatické GitHub zápisy "
        "ještě nejsou dokončené. Před schválením můžeme termíny probrat.",
    ]
    return "\n".join(lines)
