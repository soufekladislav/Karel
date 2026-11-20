"""Evidence-backed milestone timeline for Karel's project Pipeline.

Project stages are governing gates; milestones are dated deliverables. The
checked-in schedule is a DRAFT until separately approved and stored. Never
represent draft dates as contractual deadlines or verified GitHub issue dates.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from sqlalchemy import select
from ..models import ProjectMemory

DRAFT_PATH = Path(__file__).resolve().parents[2] / "docs" / "PROJECT_SCHEDULE.md"
KAREL_PROJECT_NAMES = frozenset(("karel", "developer karel"))
MEMORY_KIND = "project_schedule"

# This exact release baseline was reviewed against docs/PROJECT_SCHEDULE.md.
# It is strictly a *draft fallback* when deploys omit docs/. This is NOT
# remotely refreshed GitHub data and never silently becomes an approved plan.
BUNDLED_KAREL_SCHEDULE = """## Konkrétní milníky a termíny

| ID | Od | Do / akceptace | Hmatatelný výsledek | Závisí na | GitHub |
| --- | --- | --- | --- | --- | --- |
| **M0 – Audit a bezpečný základ** | 23. 11. | **25. 11. 2026** | Ověřená verze Exonu, GitHub, bezpečnost a blokace | Bez dalšího | [#4](https://github.com/soufekladislav/Karel/issues/4), [#5](https://github.com/soufekladislav/Karel/issues/5) |
| **M1 – Časová osa přímo v Karlovi** | 26. 11. | **4. 12. 2026** | Ověřená a schvalovaná časová osa se závislostmi a historií | M0 | [#1](https://github.com/soufekladislav/Karel/issues/1), [#17](https://github.com/soufekladislav/Karel/issues/17) |
| **M2 – Spolehlivé převzetí GitHubu** | 7. 12. | **11. 12. 2026** | Čtení kódu, Issues, PR, větví a testů včetně omezení zdrojů | M0, M1 | [#20](https://github.com/soufekladislav/Karel/issues/20), [#6](https://github.com/soufekladislav/Karel/issues/6) |
| **M3 – GitHub manažer** | 14. 12. | **18. 12. 2026** | Schválené a ověřené úpravy Issues, bez neautorizovaného merge | M2 | [#9](https://github.com/soufekladislav/Karel/issues/9) |
| **M4 – AI Engine a Codex – pilot** | 4. 1. 2027 | **15. 1. 2027** | Schválené Issue, Engine job, skutečné kódování a CI | M3 | [#10](https://github.com/soufekladislav/Karel/issues/10) |
| **M5 – Testovací nasazení a přejímka** | 18. 1. | **22. 1. 2027** | Oddělené testování, protokol a rozhodnutí uživatele | M4 | [#10](https://github.com/soufekladislav/Karel/issues/10), [#4](https://github.com/soufekladislav/Karel/issues/4) |
| **M6 – Produkční pilot Karla** | 25. 1. | **29. 1. 2027** | Schválení, záloha, řízené nasazení, health a rollback | M5 | [#4](https://github.com/soufekladislav/Karel/issues/4) |
"""

DOC_HEADING = "## Konkrétní milníky a termíny"
MILESTONE_ID = re.compile(r"\b(M[0-9]+)\b")
DATE = re.compile(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d\d)?")
GH_ISSUE = re.compile(r"\[#(\d+)\]\(https://github\.com/soufekladislav/Karel/issues/\d+\)")


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("**", "").replace("*", "")).strip()


def _date(text: str, fallback_year: int | None = None) -> date:
    match = DATE.search(str(text or ""))
    if not match:
        raise ValueError("Neplatné datum harmonogramu.")
    year = int(match.group(3)) if match.group(3) else fallback_year
    if year is None:
        raise ValueError("Termín nemá určený rok.")
    return date(year, int(match.group(2)), int(match.group(1)))


def parse_checked_in_schedule(text: str) -> list[dict]:
    """Read only the Milestones table in docs/PROJECT_SCHEDULE.md."""
    if DOC_HEADING not in text:
        return []
    segment = text.split(DOC_HEADING, 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in segment.splitlines():
        if not line.startswith("| "):
            continue
        cells = [v.strip() for v in line.strip().strip("|").split("|")]
        if len(cells) != 6 or not cells[0].startswith("**"):
            continue
        match = MILESTONE_ID.search(cells[0])
        if not match:
            continue
        try:
            due = _date(cells[2])
            start = _date(cells[1], fallback_year=due.year)
            if start > due:
                # Some dates straddle a new year.
                start = date(due.year - 1, start.month, start.day)
            if start > due:
                continue
        except ValueError:
            continue
        rows.append({
            "id": match.group(1),
            "title": _clean(cells[0]).split(" – ", 1)[-1],
            "start_date": start.isoformat(),
            "due_date": due.isoformat(),
            "acceptance": _clean(cells[3]),
            "dependencies": _clean(cells[4]),
            "issue_numbers": sorted(set(int(v) for v in GH_ISSUE.findall(cells[5]))),
            "status": "planned",
        })
    return rows


def normalize_milestones(data: list) -> list[dict]:
    if not isinstance(data, list) or len(data) > 60:
        return []
    result, seen = [], set()
    for raw in data:
        if not isinstance(raw, dict):
            return []
        key = str(raw.get("id") or "").strip()
        title = str(raw.get("title") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,20}", key) or key in seen or not title:
            return []
        try:
            start = date.fromisoformat(raw["start_date"])
            due = date.fromisoformat(raw["due_date"])
            if start > due:
                return []
        except (ValueError, TypeError, KeyError):
            return []
        seen.add(key)
        status = raw.get("status", "planned")
        if status not in ("planned", "active", "blocked", "testing", "completed"):
            return []
        issues = raw.get("issue_numbers") or []
        if not isinstance(issues, list) or len(issues) > 20 or any(
                type(x) is not int or x <= 0 for x in issues):
            return []
        result.append({
            "id": key, "title": title[:160],
            "start_date": start.isoformat(), "due_date": due.isoformat(),
            "acceptance": str(raw.get("acceptance") or "")[:800],
            "dependencies": str(raw.get("dependencies") or "")[:300],
            "issue_numbers": issues, "status": status,
        })
    return sorted(result, key=lambda x: (x["start_date"], x["due_date"]))


def timeline_view(milestones: list[dict], *, approved: bool,
                  today: date | None = None, source: str = "") -> dict:
    today = today or date.today()
    if not milestones:
        return {"items": [], "approved": False, "source": "none",
                "upcoming": None, "end_date": None, "overdue": 0,
                "complete": 0, "start_date": None}
    dates = [(date.fromisoformat(x["start_date"]),
              date.fromisoformat(x["due_date"])) for x in milestones]
    first = min(x[0] for x in dates)
    last = max(x[1] for x in dates)
    span = max(1, (last - first).days + 1)
    items = []
    for item, (start, due) in zip(milestones, dates):
        offset = round(100 * (start - first).days / span, 2)
        width = max(1.5, round(100 * ((due - start).days + 1) / span, 2))
        state = item["status"]
        if approved and state != "completed":
            if due < today:
                state = "late"
            elif 0 <= (due - today).days <= 3 and state not in ("blocked", "testing"):
                state = "soon"
        items.append({
            **item, "date_label": due.strftime("%d.%m.%Y"),
            "start_label": start.strftime("%d.%m.%Y"),
            "offset_pct": offset, "width_pct": min(width, 100 - offset),
            "view_status": state, "days_left": (due - today).days
        })
    next_item = next((x for x in items if x["status"] != "completed"), None)
    return {
        "items": items, "approved": approved, "source": source,
        "upcoming": next_item, "overdue": sum(x["view_status"] == "late" for x in items),
        "complete": sum(x["status"] == "completed" for x in items),
        "start_date": first.strftime("%d.%m.%Y"),
        "end_date": last.strftime("%d.%m.%Y"),
    }


def load_project_timeline(db, project, *, is_admin=False, linked_repo=None) -> dict:
    stored = db.scalar(select(ProjectMemory).where(
        ProjectMemory.project_id == project.id,
        ProjectMemory.kind == MEMORY_KIND, ProjectMemory.verified == True
    ).order_by(ProjectMemory.id.desc()))
    if stored:
        try:
            doc = json.loads(stored.content)
            rows = normalize_milestones(doc.get("milestones"))
            if rows:
                return timeline_view(rows, approved=True, source="approved")
        except (ValueError, TypeError, AttributeError):
            pass
    project_name = " ".join((project.name or "").casefold().split())
    if (is_admin and project_name in KAREL_PROJECT_NAMES and
            linked_repo in (None, "", "soufekladislav/Karel")):
        rows = []
        if DRAFT_PATH.is_file():
            try:
                rows = normalize_milestones(parse_checked_in_schedule(
                    DRAFT_PATH.read_text(encoding="utf-8")))
            except OSError:
                rows = []
        if rows:
            return timeline_view(rows, approved=False, source="checked_in_draft")
        # Exon deployments may contain app/ but not docs/. Do not silently
        # discard the project schedule just because ancillary docs were omitted.
        rows = normalize_milestones(parse_checked_in_schedule(BUNDLED_KAREL_SCHEDULE))
        if rows:
            return timeline_view(rows, approved=False, source="bundled_draft")
    return timeline_view([], approved=False)
