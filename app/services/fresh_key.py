from __future__ import annotations

from urllib.parse import urlencode
import httpx
from ..config import settings


class FreshKeyError(RuntimeError):
    pass


def configured() -> bool:
    return bool(settings.engine_url and settings.engine_api_key)


def _headers(user_id: int | str | None = None) -> dict[str, str]:
    h = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.engine_api_key}",
        "X-Fresh-App": "karel",
    }
    if user_id is not None:
        h["X-Fresh-User"] = str(user_id)
    return h


def _request(method: str, path: str, *, user_id=None, payload=None, params=None) -> dict:
    if not configured():
        raise FreshKeyError("Fresh Key není nakonfigurován. Doplň FRESH_AI_ENGINE_URL a FRESH_AI_ENGINE_API_KEY.")
    try:
        with httpx.Client(timeout=25) as client:
            r = client.request(method, settings.engine_url.rstrip("/") + path, headers=_headers(user_id), json=payload, params=params)
    except Exception as exc:
        raise FreshKeyError(f"Fresh Key není dostupný: {exc}") from exc
    try:
        data = r.json()
    except Exception:
        data = {"ok": False, "error": r.text[:500]}
    if r.status_code >= 400 or not data.get("ok", False):
        raise FreshKeyError(str(data.get("error") or f"Fresh Key HTTP {r.status_code}"))
    return data


def bootstrap_account(user) -> dict:
    """Prepare a free Fresh Key identity / AI Engine shell from Karel.

    No credits are allocated or required. The user can later open the central
    management UI with the same Fresh Account e-mail.
    """
    return _request("POST", "/v1/fresh-key/account/bootstrap", user_id=user.id, payload={
        "app_code": "karel",
        "external_user_id": str(user.id),
        "email": str(user.email or "").strip().lower(),
        "display_name": str(user.name or user.email or "").strip(),
        "email_verified": True,
    })


def manage_url(link_id: str = "") -> str:
    base = settings.engine_url.rstrip("/") + "/account/fresh-key"
    return base + ("?" + urlencode({"link": str(link_id)}) if link_id else "")


def register_project(user, project, role: str = "viewer") -> dict:
    return _request("POST", "/v1/fresh-key/local-projects/sync", user_id=user.id, payload={
        "app_code": "karel",
        "external_user_id": str(user.id),
        "external_project_id": str(project.id),
        "name": str(project.name or ""),
        "website_url": "",
        "organization_name": "",
        "role": role,
    }).get("local_project") or {}


def publish_project(user, project, role: str = "viewer") -> str:
    bootstrap_account(user)
    register_project(user, project, role=role)
    data = _request("POST", "/v1/fresh-key/links/sync", user_id=user.id, payload={
        "app_code": "karel",
        "external_user_id": str(user.id),
        "external_project_id": str(project.id),
        "name": str(project.name or ""),
        "website_url": "",
        "organization_name": "",
    })
    link = data.get("link") or data.get("project") or {}
    link_id = str(link.get("id") or "")
    if not link_id:
        raise FreshKeyError("Fresh Key nevrátil ID propojení.")
    return link_id


def project_summary(user, project, role: str = "viewer") -> dict:
    bootstrap_account(user)
    locals_ = _request("GET", "/v1/fresh-key/local-projects", user_id=user.id).get("local_projects") or []
    synced = next((x for x in locals_ if str(x.get("app_code") or "") == "karel" and str(x.get("external_project_id") or "") == str(project.id)), None) or {}
    link_id = str(synced.get("fresh_key_id") or "")
    if not link_id:
        return {"linked": False, "fresh_key_id": "", "applications": [], "members": [], "manage_url": manage_url()}
    links = _request("GET", "/v1/fresh-key/links", user_id=user.id).get("links") or []
    link = next((x for x in links if str(x.get("id") or "") == link_id), None) or {"id": link_id, "bindings": []}
    members = _request("GET", f"/v1/fresh-key/links/{link_id}/members", user_id=user.id).get("members") or []
    return {
        "linked": True,
        "fresh_key_id": link_id,
        "name": link.get("name") or project.name,
        "applications": [x for x in (link.get("bindings") or []) if str(x.get("app_code") or "") != "ai-engine"],
        "members": members,
        "manage_url": manage_url(link_id),
    }


def pending_link_requests(user) -> list[dict]:
    bootstrap_account(user)
    return _request("GET", "/v1/fresh-key/link-requests", user_id=user.id, params={"status": "pending"}).get("requests") or []


def accept_link_request(user, request_id: str, project, role: str = "viewer") -> dict:
    data = _request("POST", f"/v1/fresh-key/link-requests/{request_id}/accept", user_id=user.id, payload={
        "app_code": "karel",
        "external_user_id": str(user.id),
        "external_project_id": str(project.id),
        "name": str(project.name or ""),
        "website_url": "",
        "organization_name": "",
        "role": role,
    })
    return data.get("request") or {}


def decline_link_request(user, request_id: str) -> dict:
    return _request("POST", f"/v1/fresh-key/link-requests/{request_id}/decline", user_id=user.id, payload={
        "app_code": "karel", "external_user_id": str(user.id),
    }).get("request") or {}


def notify_project_share(user, email: str, project_name: str, role: str, action_url: str) -> dict:
    return _request("POST", "/v1/fresh-key/project-share/notify", user_id=user.id, payload={
        "app_code": "karel",
        "external_user_id": str(user.id),
        "email": str(email or "").strip().lower(),
        "project_name": str(project_name or "Projekt"),
        "role": str(role or "editor"),
        "action_url": str(action_url or ""),
    })


def add_member(user, link_id: str, email: str, role: str, notify: bool = False) -> dict:
    return _request("POST", f"/v1/fresh-key/links/{link_id}/members", user_id=user.id, payload={
        "app_code": "karel", "external_user_id": str(user.id), "email": email, "role": role,
        "can_manage_connections": role == "manager", "notify": bool(notify),
    }).get("member") or {}


def update_member(user, link_id: str, identity_id: str, role: str) -> dict:
    return _request("POST", f"/v1/fresh-key/links/{link_id}/members", user_id=user.id, payload={
        "app_code": "karel", "external_user_id": str(user.id), "action": "update", "identity_id": identity_id,
        "role": role, "can_manage_connections": role == "manager",
    }).get("member") or {}


def remove_member(user, link_id: str, identity_id: str) -> None:
    _request("POST", f"/v1/fresh-key/links/{link_id}/members", user_id=user.id, payload={
        "app_code": "karel", "external_user_id": str(user.id), "action": "remove", "identity_id": identity_id,
    })
