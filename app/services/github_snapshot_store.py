"""Persistence for GitHub read-only snapshots. GitHub remains source of truth."""
from datetime import datetime
import json

from sqlalchemy import select
from ..models import GitHubRepoLink, ProjectEvent


def upsert_snapshot(db, project_id: int, user_id: int, snapshot: dict) -> GitHubRepoLink:
    """Update one cache row by local project ID, without creating any Tasks."""
    repo = snapshot["repository"]
    if not repo:
        raise ValueError("Missing repository")
    link = db.scalar(select(GitHubRepoLink).where(GitHubRepoLink.project_id == project_id))
    if link is None:
        link = GitHubRepoLink(project_id=project_id, repository_full_name=repo)
        db.add(link)
    link.repository_full_name = repo
    link.snapshot_json = json.dumps(snapshot, ensure_ascii=False)
    link.last_synced_at = datetime.utcnow()
    link.last_error = None
    link.updated_at = datetime.utcnow()
    db.add(ProjectEvent(project_id=project_id, user_id=user_id,
                        event_type="github_readonly_sync",
                        detail="Read-only GitHub snapshot: " + repo + " @ " + str(snapshot.get("fetched_at") or "")))
    db.commit()
    return link
