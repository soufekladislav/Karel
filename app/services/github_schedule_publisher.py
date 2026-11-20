"""Publication of the APPROVED local Pipeline to one authorized GitHub file.

Pipeline/ProjectMemory is authoritative. A contents-API write is a verified
projection, never an alternative master. No Issue/Projects writes here.

Requires explicit user-approved schedule, separate narrowly-scoped GitHub
token and administrator configuration. Avoid exposing secrets or overwriting
an unrelated repository file. All remote work is bounded and mock-testable.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime
from urllib.parse import quote

import httpx
from sqlalchemy import select

from ..config import settings
from ..models import GitHubRepoLink, ProjectMemory, ProjectEvent
from .github_chat_audit import _superadmin, repository_for_project
from .project_timeline import normalize_milestones

REPO = "soufekladislav/Karel"
PATH = "docs/KAREL_APPROVED_PIPELINE.json"
API = "https://api.github.com"
SCHEMA = "freshcrackers.karel.approved_pipeline.v1"
MAX_SIZE = 48 * 1024
_SUSPICIOUS = re.compile(
    r"(?i)(?:gh[pousr]_[a-z0-9_]{12,}|github_pat_[a-z0-9_]{12,}|"
    r"sk-[a-z0-9_-]{16,}|(?:API_KEY|PRIVATE_KEY|ACCESS_TOKEN|"
    r"FRESH_CORE_WRITE_KEY)\s*[:=])"
)


class ScheduleSyncError(RuntimeError):
    pass


def latest_approved_row(db, project_id: int):
    return db.scalar(select(ProjectMemory).where(
        ProjectMemory.project_id == project_id,
        ProjectMemory.kind == "project_schedule",
        ProjectMemory.verified == True,
    ).order_by(ProjectMemory.id.desc()))


def latest_sync_status(db, project_id: int) -> dict:
    row = db.scalar(select(ProjectMemory).where(
        ProjectMemory.project_id == project_id,
        ProjectMemory.kind == "project_schedule_github_sync",
    ).order_by(ProjectMemory.id.desc()))
    if not row:
        return {"state": "not_attempted", "version": None}
    try:
        return json.loads(row.content)
    except (TypeError, ValueError):
        return {"state": "unknown", "version": None}


def record_schedule_sync(db, project_id: int, user_id: int | None,
                         status: dict) -> dict:
    state = str(status.get("state") or "unknown")
    safe = {
        "state": state, "version": status.get("version"),
        "commit_sha": str(status.get("commit_sha") or "")[:40],
        "url": str(status.get("url") or "")[:350],
        "reason": str(status.get("reason") or "")[:280],
        "time": datetime.utcnow().isoformat() + "Z",
    }
    db.add(ProjectMemory(
        project_id=project_id, kind="project_schedule_github_sync",
        title="GitHub synchronizace harmonogramu",
        content=json.dumps(safe, ensure_ascii=False), verified=True,
    ))
    db.add(ProjectEvent(
        project_id=project_id, user_id=user_id,
        event_type="project_schedule_github_sync_" + (
            state if state in ("synced", "blocked", "failed", "conflict")
            else "unknown"),
        detail=json.dumps(safe, ensure_ascii=False)[:1000],
    ))
    db.flush()
    return safe


def _verified_document(row, *, project_id: int) -> tuple[dict, bytes, str]:
    if row is None or row.project_id != project_id:
        raise ScheduleSyncError("Chybí schválená verze harmonogramu.")
    try:
        doc = json.loads(row.content)
        milestones = normalize_milestones(doc.get("milestones"))
        version = int(doc["version"])
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise ScheduleSyncError("Schválený plán nemá platnou strukturu.") from exc
    if not milestones or len(milestones) != len(doc.get("milestones") or []) or version < 1:
        raise ScheduleSyncError("Schválený plán obsahuje neplatné milníky.")
    body = {
        "schema": SCHEMA, "project_id": project_id, "repository": REPO,
        "version": version,
        "approved_at": str(doc.get("approved_at") or ""),
        "approved_by_user_id": doc.get("approved_by_user_id"),
        "milestones": milestones,
    }
    raw = (json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2)
           + "\n").encode("utf-8")
    if len(raw) > MAX_SIZE or _SUSPICIOUS.search(raw.decode("utf-8")):
        raise ScheduleSyncError(
            "Harmonogram obsahuje nevhodná nebo citlivá data pro GitHub export.")
    blobsha = hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\x00" + raw
    ).hexdigest()
    return body, raw, blobsha


def _api(client: httpx.Client, method: str, path: str, token: str, *,
         params=None, payload=None, allow_missing=False) -> dict | None:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Fresh-Karel-ApprovedSchedule/1.0",
    }
    try:
        response = client.request(
            method, API + path, headers=headers,
            params=params, json=payload, timeout=18,
            follow_redirects=False,
        )
    except httpx.RequestError as exc:
        raise ScheduleSyncError("GitHub API není dostupné; změna čeká na opakování.") from exc
    if allow_missing and response.status_code == 404:
        return None
    if response.status_code in (409, 412, 422):
        raise ScheduleSyncError(
            "GitHub odmítl zápis kvůli konfliktu verze (409/412/422). "
            "Bez ručního ověření nepřepíšu cizí změnu.")
    if response.status_code == 401:
        raise ScheduleSyncError("GitHub odmítl zapisovací token (401).")
    if response.status_code == 403:
        raise ScheduleSyncError(
            "GitHub odmítl zápis nebo chybí Contents:write oprávnění (403).")
    if response.status_code >= 400:
        raise ScheduleSyncError(
            "GitHub API vrátilo HTTP " + str(response.status_code) + ".")
    try:
        body = response.json()
    except ValueError as exc:
        raise ScheduleSyncError("GitHub nevrátil ověřitelný JSON.") from exc
    if not isinstance(body, dict):
        raise ScheduleSyncError("GitHub vrátil neočekávanou odpověď.")
    return body


def publish_approved_schedule(db, project, user, *,
                              client: httpx.Client | None = None) -> dict:
    repo, _ = repository_for_project(db, project, user)
    if not _superadmin(user) or repo != REPO:
        raise ScheduleSyncError("K zápisu do tohoto GitHub repozitáře nejsi oprávněn.")
    if (" ".join((project.name or "").casefold().split()) not in
            ("karel", "developer karel")):
        raise ScheduleSyncError("Synchronizace není připravená pro tento projekt.")
    owners = {x.strip().casefold() for x in
              settings.github_allowed_owners.split(",") if x.strip()}
    if REPO.split("/")[0].casefold() not in owners:
        raise ScheduleSyncError("Vlastník repozitáře není v povoleném seznamu.")
    if not settings.github_schedule_write_enabled:
        raise ScheduleSyncError(
            "Zápis schváleného harmonogramu do GitHubu není zapnutý.")
    token = settings.github_schedule_write_token
    if not token:
        raise ScheduleSyncError(
            "Chybí jednorázově nastavený GITHUB_SCHEDULE_WRITE_TOKEN "
            "s oprávněním Contents:write.")
    row = latest_approved_row(db, project.id)
    desired, raw, blob_sha = _verified_document(row, project_id=project.id)
    endpoint = "/repos/" + REPO + "/contents/" + PATH
    own = client is None
    cli = client or httpx.Client(timeout=18, follow_redirects=False)
    try:
        repo_info = _api(cli, "GET", "/repos/" + REPO, token)
        if str(repo_info.get("full_name") or "").casefold() != REPO.casefold():
            raise ScheduleSyncError("Nepotvrzená identita cílového GitHub repozitáře.")
        branch = str(repo_info.get("default_branch") or "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", branch):
            raise ScheduleSyncError("GitHub výchozí větev nelze ověřit.")
        remote = _api(cli, "GET", endpoint, token,
                      params={"ref": branch}, allow_missing=True)
        remote_sha = None
        if remote:
            if (remote.get("type") != "file" or
                    not re.fullmatch(r"[0-9a-f]{40}", str(remote.get("sha") or ""))):
                raise ScheduleSyncError("Cílový GitHub soubor má neplatný typ.")
            remote_sha = remote["sha"]
            if (remote.get("encoding") != "base64" or
                    not isinstance(remote.get("content"), str)):
                raise ScheduleSyncError("Vzdálený obsah nelze ověřit.")
            try:
                decoded = base64.b64decode(
                    "".join(remote["content"].split()), validate=True)
                current = json.loads(decoded)
            except (ValueError, TypeError) as exc:
                raise ScheduleSyncError(
                    "Cílový soubor neodpovídá očekávanému JSON harmonogramu.") from exc
            if (current.get("schema") != SCHEMA or
                    current.get("repository") != REPO or
                    current.get("project_id") != project.id):
                raise ScheduleSyncError(
                    "GitHub soubor patří jinému obsahu nebo projektu; nepřepisuji.")
            try:
                remote_version = int(current.get("version"))
            except (ValueError, TypeError) as exc:
                raise ScheduleSyncError(
                    "Vzdálený harmonogram nemá platnou verzi.") from exc
            if remote_sha == blob_sha:
                return {"state": "synced", "version": desired["version"],
                        "commit_sha": "", "url": "https://github.com/" +
                        REPO + "/blob/" + quote(branch, safe="") + "/" + PATH}
            if remote_version > desired["version"]:
                raise ScheduleSyncError(
                    "GitHub má novější verzi harmonogramu; "
                    "nelze ji přepsat starším návrhem.")
            if remote_version == desired["version"]:
                raise ScheduleSyncError(
                    "GitHub má jiný obsah stejné verze harmonogramu; "
                    "vyžaduje kontrolu konfliktu.")
        request_body = {
            "message": "docs(schedule): sync approved Karel Pipeline v" +
                       str(desired["version"]),
            "branch": branch,
            "content": base64.b64encode(raw).decode("ascii"),
        }
        if remote_sha:
            request_body["sha"] = remote_sha
        written = _api(cli, "PUT", endpoint, token, payload=request_body)
        commit_sha = str((written.get("commit") or {}).get("sha") or "")
        if not re.fullmatch(r"[a-fA-F0-9]{40}", commit_sha):
            raise ScheduleSyncError(
                "GitHub nepotvrdil SHA commitu. Zápis nelze označit za úspěšný.")
        verified = _api(
            cli, "GET", endpoint, token, params={"ref": commit_sha})
        if (verified.get("sha") != blob_sha or
                verified.get("type") != "file"):
            raise ScheduleSyncError(
                "Po zápisu se GitHub obsah nepodařilo ověřit. "
                "Neoznačuji harmonogram za synchronizovaný.")
        return {
            "state": "synced", "version": desired["version"],
            "commit_sha": commit_sha,
            "url": "https://github.com/" + REPO + "/blob/" +
                   commit_sha + "/" + PATH,
        }
    finally:
        if own:
            cli.close()


def sync_after_approved_action(db, project, user, action_results: list[dict]) -> dict | None:
    """Called only *after DB commit* for an approved schedule action.

    Remote failure never rolls back an already approved local Pipeline. Each
    attempt leaves an audit record, and subsequent attempts are idempotent.
    """
    if not any(x.get("type") == "approve_project_schedule"
               for x in (action_results or [])):
        return None
    try:
        status = publish_approved_schedule(db, project, user)
    except ScheduleSyncError as exc:
        message = str(exc)
        if any(x in message for x in (
            "token", "Contents:write", "povoleném seznamu", "není zapnutý",
        )):
            state = "blocked"
        elif any(x in message for x in (
            "konflikt", "jiný obsah", "jinému obsahu",
            "novější verzi", "přepsat",
        )):
            state = "conflict"
        else:
            state = "failed"
        version_row = latest_approved_row(db, project.id)
        version = None
        if version_row:
            try:
                version = int(json.loads(version_row.content)["version"])
            except (ValueError, TypeError, KeyError):
                pass
        status = {
            "state": state, "version": version, "reason": message,
            "commit_sha": "", "url": "",
        }
    recorded = record_schedule_sync(db, project.id, user.id, status)
    db.commit()
    return recorded
