from __future__ import annotations

import ipaddress
import json
import re
import socket
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Project, ProjectMemory, ProjectEvent, User
from .app_manifest import build_app_manifest
from .brain import load_brain

MAX_SOURCE_BYTES = 1024 * 1024
MAX_SOURCE_CHARS = 24000
URL_RE = re.compile(r'https?://[^\s<>\]\[)]+', re.I)
ALLOWED_CONTENT_HINTS = ('json', 'text/', 'xml', 'javascript', 'yaml', 'x-yaml')
MANIFEST_WORDS = ('manifest', 'capabilit', 'funkčnost', 'funkcnost', 'endpoint', 'verze aplikace')


def _clip(text: str, limit: int = MAX_SOURCE_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f'\n… [zdroj zkrácen, původně {len(text)} znaků]'


def _manifest_requested(message: str) -> bool:
    low = (message or '').lower()
    return any(word in low for word in MANIFEST_WORDS)


def _validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise ValueError('Nepodporovaná URL.')
    if parsed.username or parsed.password:
        raise ValueError('URL s přihlašovacími údaji není povolena.')
    host = parsed.hostname.lower().rstrip('.')
    if host in ('localhost',) or host.endswith('.local'):
        raise ValueError('Lokální adresa není povolena.')
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError('Doménu se nepodařilo přeložit.') from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise ValueError('Privátní nebo lokální síťová adresa není povolena.')


def _same_app_manifest(url: str) -> bool:
    try:
        wanted = urlparse(url)
        app = urlparse(str(settings.app_url or ''))
        return bool(wanted.hostname and app.hostname and wanted.hostname.lower() == app.hostname.lower() and wanted.path.rstrip('/') == '/manifest.json')
    except Exception:
        return False


def _is_karel_project(project: Project, stored_manifest: ProjectMemory | None = None) -> bool:
    name = (project.name or '').lower()
    if 'karel' in name:
        return True
    if stored_manifest and _same_app_manifest(stored_manifest.title or ''):
        return True
    return False


def _save_manifest(db: Session, project: Project, user: User, url: str, content: str) -> None:
    row = db.scalar(
        select(ProjectMemory).where(ProjectMemory.project_id == project.id, ProjectMemory.kind == 'manifest')
        .order_by(ProjectMemory.id.desc())
    )
    if row:
        row.title = url
        row.content = content
        row.verified = True
    else:
        db.add(ProjectMemory(project_id=project.id, kind='manifest', title=url, content=content, verified=True))
    db.add(ProjectEvent(project_id=project.id, user_id=user.id, event_type='manifest_updated', detail=url))
    db.flush()


def _fetch_public_text(url: str, is_manifest: bool) -> tuple[str, str]:
    current = url
    response = None
    for _ in range(4):
        _validate_public_url(current)
        with httpx.Client(timeout=12, follow_redirects=False, headers={'User-Agent': 'Karel/2.0 Source Resolver'}) as client:
            response = client.get(current)
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get('location')
            if not location:
                raise ValueError('Přesměrování nemá cílovou adresu.')
            current = str(httpx.URL(current).join(location))
            continue
        response.raise_for_status()
        break
    if response is None:
        raise ValueError('Zdroj se nepodařilo načíst.')
    if len(response.content) > MAX_SOURCE_BYTES:
        raise ValueError('Zdroj je větší než 1 MB.')
    content_type = (response.headers.get('content-type') or '').lower()
    if not any(h in content_type for h in ALLOWED_CONTENT_HINTS) and not is_manifest:
        raise ValueError('URL nevrací podporovaný textový zdroj.')
    if is_manifest:
        try:
            data = response.json()
            content = json.dumps(data, ensure_ascii=False, indent=2)
        except Exception as exc:
            raise ValueError('Manifest není platný JSON.') from exc
    else:
        content = response.text
    return content, content_type


def _live_karel_manifest(db: Session, project: Project, user: User, app_version: str) -> str:
    data = build_app_manifest(db, app_version)
    content = json.dumps(data, ensure_ascii=False, indent=2)
    url = str(settings.app_url or '').rstrip('/') + '/manifest.json'
    _save_manifest(db, project, user, url, content)
    db.add(ProjectEvent(project_id=project.id, user_id=user.id, event_type='source_loaded_live', detail=url))
    return (
        'PRIMÁRNÍ ŽIVÝ ZDROJ — MANIFEST KARLA\n'
        f'Zdroj: interně generovaný manifest aplikace ({url})\n'
        'Stav zdroje: LIVE / aktuální pro tento dotaz\n'
        f'Obsah:\n{_clip(content)}'
    )


def _implicit_manifest_source(db: Session, project: Project, user: User, message: str, app_version: str) -> list[str]:
    """Resolve manifest intent even when the user does not repeat a URL."""
    if not _manifest_requested(message):
        return []
    stored = db.scalar(
        select(ProjectMemory).where(
            ProjectMemory.project_id == project.id,
            ProjectMemory.kind == 'manifest',
            ProjectMemory.verified == True,
        ).order_by(ProjectMemory.id.desc())
    )
    if _is_karel_project(project, stored):
        return [_live_karel_manifest(db, project, user, app_version)]
    if not stored:
        return []

    # If a public manifest URL is known, refresh it for a manifest-specific question.
    url = (stored.title or '').strip()
    if url.startswith(('http://', 'https://')):
        try:
            if _same_app_manifest(url):
                return [_live_karel_manifest(db, project, user, app_version)]
            content, content_type = _fetch_public_text(url, True)
            _save_manifest(db, project, user, url, content)
            db.add(ProjectEvent(project_id=project.id, user_id=user.id, event_type='source_loaded_live', detail=url))
            return [
                'PRIMÁRNÍ ŽIVÝ ZDROJ — MANIFEST PROJEKTU\n'
                f'URL: {url}\nTyp: {content_type}\nStav zdroje: LIVE / právě obnoveno\n'
                f'Obsah:\n{_clip(content)}'
            ]
        except Exception as exc:
            db.add(ProjectEvent(project_id=project.id, user_id=user.id, event_type='source_refresh_error', detail=f'{url}: {str(exc)[:350]}'))
            # Fall back to stored snapshot, but label it clearly.
    return [
        'PRIMÁRNÍ ULOŽENÝ ZDROJ — MANIFEST PROJEKTU\n'
        f'Zdroj: {stored.title}\nStav zdroje: SNAPSHOT / uložená kopie\n'
        f'Obsah:\n{_clip(stored.content or "")}'
    ]


def resolve_message_sources(db: Session, project: Project, user: User, message: str, app_version: str) -> list[str]:
    """Resolve explicit URLs and first-class implicit project sources before AI execution."""
    brain = load_brain()
    if brain.get('tools', {}).get('urls') == 'manual' and not _manifest_requested(message):
        return []
    urls = []
    for raw in URL_RE.findall(message or ''):
        url = raw.rstrip('.,;:!?')
        if url not in urls:
            urls.append(url)
        if len(urls) >= 3:
            break

    # If no URL was repeated, still resolve a known manifest from project configuration/context.
    if not urls:
        return _implicit_manifest_source(db, project, user, message, app_version)

    blocks: list[str] = []
    lower_message = (message or '').lower()
    for url in urls:
        is_manifest = 'manifest' in lower_message or urlparse(url).path.lower().endswith('manifest.json')
        try:
            if _same_app_manifest(url):
                data = build_app_manifest(db, app_version)
                content = json.dumps(data, ensure_ascii=False, indent=2)
                content_type = 'application/json'
            else:
                content, content_type = _fetch_public_text(url, is_manifest)

            if is_manifest:
                _save_manifest(db, project, user, url, content)
            blocks.append(
                ('PRIMÁRNÍ ŽIVÝ ZDROJ — MANIFEST\n' if is_manifest else 'ZDROJ NAČTENÝ PŘÍMO PRO TENTO DOTAZ\n') +
                f'URL: {url}\nTyp: {content_type}\nStav zdroje: LIVE / právě načteno\nObsah:\n{_clip(content)}'
            )
            db.add(ProjectEvent(project_id=project.id, user_id=user.id, event_type='source_loaded_live', detail=url))
        except Exception as exc:
            blocks.append(f'ZDROJ SE NEPODAŘILO NAČÍST\nURL: {url}\nDůvod: {str(exc)[:300]}')
            db.add(ProjectEvent(project_id=project.id, user_id=user.id, event_type='source_load_error', detail=f'{url}: {str(exc)[:350]}'))
    return blocks
