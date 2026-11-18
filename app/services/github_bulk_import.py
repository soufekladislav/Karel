"""Safe, idempotent bulk onboarding of GitHub repositories into local projects.

GitHub is authoritative. Import creates local project shells and repo links ONLY.
It does not download issue bodies, modify GitHub, or claim an initial sync.
"""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import quote

from sqlalchemy import select

from ..models import Chat, GitHubRepoLink, Project, ProjectEvent
from .github_connector import GitHubReader, GitHubSyncError, validate_repository

MAX_DISCOVERED = 300
MAX_APPLY = 75
_OWNER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")


def discover_repositories(reader: GitHubReader, allowed_owners: str) -> tuple[list[dict], bool]:
    """Discover token-visible repos or public repos (without token), with a hard cap."""
    owners = [o.strip() for o in allowed_owners.split(',') if o.strip()]
    if not owners or any(not _OWNER_RE.fullmatch(o) for o in owners):
        raise GitHubSyncError("Nastav důvěryhodné vlastníky v GITHUB_ALLOWED_OWNERS.")
    found = {}
    truncated = False

    def absorb(items):
        for item in items:
            full_name = str(item.get('full_name') or '')
            try:
                name = validate_repository(full_name, allowed_owners)
            except GitHubSyncError:
                continue
            found[name.lower()] = {
                'full_name': name,
                'name': name.split('/', 1)[1],
                'description': str(item.get('description') or '')[:500],
                'html_url': str(item.get('html_url') or '')[:300],
                'private': bool(item.get('private')),
                'archived': bool(item.get('archived')),
                'default_branch': str(item.get('default_branch') or 'main')[:150],
                'repository_id': item.get('id'),
            }

    if reader.token:
        # The token can see private repositories; values are filtered by owner allowlist.
        for page in range(1, 1 + MAX_DISCOVERED // 100):
            items = reader._request('GET', '/user/repos', params={
                'affiliation': 'owner,collaborator,organization_member',
                'sort': 'full_name', 'per_page': 100, 'page': page,
            })
            if not isinstance(items, list):
                raise GitHubSyncError("GitHub vrátil neočekávaný seznam repozitářů.")
            absorb(items)
            if len(items) < 100:
                break
            if page == MAX_DISCOVERED // 100:
                truncated = True
    else:
        for owner in owners:
            # Both personal and org repositories may be public; never search arbitrary hosts.
            for prefix in ('users', 'orgs'):
                if len(found) >= MAX_DISCOVERED:
                    truncated = True
                    break
                for page in range(1, 1 + MAX_DISCOVERED // 100):
                    items = reader._request('GET', '/' + prefix + '/' + quote(owner, safe='') +
                                            '/repos', params={'per_page': 100, 'page': page},
                                            optional=True)
                    if items is None:
                        break  # /orgs owner returns 404 for personal accounts, and vice versa
                    if not isinstance(items, list):
                        raise GitHubSyncError("GitHub vrátil neočekávaný seznam repozitářů.")
                    absorb(items)
                    if len(items) < 100:
                        break
                    if page == MAX_DISCOVERED // 100:
                        truncated = True
    result = sorted(found.values(), key=lambda x: x['full_name'].lower())
    if len(result) > MAX_DISCOVERED:
        truncated = True
    return result[:MAX_DISCOVERED], truncated


def prepare_import_plan(db, user_id: int, repositories: list[dict]) -> list[dict]:
    """One repo -> one local project. Exact name matches are never overwritten."""
    links = db.scalars(select(GitHubRepoLink)).all()
    projects = db.scalars(select(Project).where(Project.owner_id == user_id)).all()
    link_by_repo = {link.repository_full_name.lower(): link for link in links}
    linked_project_ids = {link.project_id for link in links}
    entries = []
    seen = set()
    for repo in repositories:
        full = str(repo['full_name'])
        key = full.lower()
        if key in seen:
            continue
        seen.add(key)
        name = str(repo['name'])
        entry = {**repo, 'action': 'create', 'local_project_id': None, 'reason': ''}
        if key in link_by_repo:
            entry.update(action='linked', local_project_id=link_by_repo[key].project_id,
                         reason='Repozitář už je propojen; nevytváří se duplicita.')
        else:
            matches = [p for p in projects if p.name.strip().lower() in
                       {name.lower(), full.lower()} and p.id not in linked_project_ids]
            if len(matches) == 1:
                entry.update(action='attach', local_project_id=matches[0].id,
                             reason='Existující projekt se stejným názvem; zachová se jeho obsah.')
            elif len(matches) > 1:
                entry.update(action='review', reason='Více místních projektů se stejným názvem; nutné ruční mapování.')
            elif any(p.name.strip().lower() in {name.lower(), full.lower()} and p.id in linked_project_ids
                     for p in projects):
                entry.update(action='review', reason='Stejnojmenný projekt je propojen s jiným repozitářem.')
        entries.append(entry)
    return entries


def apply_import_plan(db, user_id: int, plan: list[dict], selected: list[str]) -> dict:
    """Explicit, bounded, repeat-safe DB write. Never delete or replace a project."""
    approved = set(s.lower() for s in selected)
    if len(selected) > MAX_APPLY or len(approved) != len(selected):
        raise ValueError('V jedné dávce lze vybrat nejvýše 75 různých repozitářů.')
    if any(s not in {str(p['full_name']).lower() for p in plan} for s in approved):
        raise ValueError('Výběr neodpovídá ověřenému seznamu GitHubu.')
    result = {'created': 0, 'attached': 0, 'skipped': 0, 'linked': 0}
    # Re-evaluate against DB immediately before committing to prevent stale previews.
    fresh = prepare_import_plan(db, user_id, plan)
    try:
        for item in fresh:
            if item['full_name'].lower() not in approved:
                continue
            if item['action'] == 'linked':
                result['linked'] += 1
                continue
            if item['action'] == 'review':
                result['skipped'] += 1
                continue
            if item['action'] == 'attach':
                p = db.get(Project, item['local_project_id'])
                if not p or p.owner_id != user_id:
                    result['skipped'] += 1
                    continue
                result['attached'] += 1
            else:
                p = Project(owner_id=user_id, name=item['name'],
                            description=item['description'] or 'Projekt importovaný z GitHubu.',
                            status='active', updated_at=datetime.utcnow())
                db.add(p)
                db.flush()
                db.add(Chat(project_id=p.id, title='Hlavní chat'))
                result['created'] += 1
            db.add(GitHubRepoLink(project_id=p.id,
                                  repository_full_name=item['full_name'], snapshot_json='{}'))
            db.add(ProjectEvent(project_id=p.id, user_id=user_id, event_type='github_repo_linked',
                                detail='Repozitář připojen; dosud neproběhla synchronizace: ' +
                                item['full_name']))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result
