"""Human-friendly presentation rules & rendered portfolio (no DB/network writes)."""
import unittest
from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader

from app.services.project_presentation import brief, github_connection_state, project_next_step


ROOT = Path(__file__).resolve().parents[1]


def repo_link(**kw):
    defaults = {"last_synced_at": None, "last_error": "", "snapshot_json": ""}
    defaults.update(kw)
    return SimpleNamespace(**defaults)


class PresentationLogicTests(unittest.TestCase):
    def test_legacy_multiline_brief_is_short_and_skips_heading(self):
        text = "Účel Karla:\n\nKarel je projektový manažer.\nDalší dlouhé kapitoly."
        self.assertEqual(brief(text, 70), "Karel je projektový manažer.")
        self.assertEqual(brief(None, fallback="Bez zadání"), "Bez zadání")
        self.assertLessEqual(len(brief("Dlouhý popis " * 50, 65)), 65)

    def test_github_configuration_and_link_states_are_distinct(self):
        self.assertEqual(github_connection_state(None, False)["kind"], "setup")
        self.assertEqual(github_connection_state(None, True)["kind"], "unlinked")
        self.assertEqual(github_connection_state(repo_link(), True)["kind"], "pending")
        self.assertEqual(github_connection_state(repo_link(last_error="Bad credentials"), True)["kind"], "error")
        self.assertEqual(github_connection_state(repo_link(
            last_synced_at="now", snapshot_json="{}"), True)["kind"], "pending")
        self.assertEqual(github_connection_state(repo_link(
            last_synced_at="now", snapshot_json='{"repository":"owner/repo","counts":{}}'),
            True)["kind"], "synced")
        self.assertEqual(github_connection_state(repo_link(
            last_synced_at="yesterday", last_error="Rate limit",
            snapshot_json='{"repository":"owner/repo"}'), True)["kind"], "error")

    def test_next_step_uses_real_priorities_and_no_fabricated_approval(self):
        gh = {"kind": "synced"}
        spec = {"business_goal": "A usable project management platform"}
        self.assertEqual(project_next_step(spec, {"waiting_user": 2, "failed": 3}, gh)["href"], "tasks")
        self.assertEqual(project_next_step(spec, {"failed": 1}, gh)["kind"], "attention")
        self.assertEqual(project_next_step(spec, {}, gh, [{"days": -1}])["href"], "development")
        self.assertEqual(project_next_step({}, {}, gh)["href"], "docs")
        self.assertEqual(project_next_step(spec, {}, {"kind": "error"})["href"], "github")
        self.assertEqual(project_next_step(spec, {"working": 1}, gh)["href"], "tasks")
        self.assertEqual(project_next_step(spec, {}, gh)["href"], "chat")


class PortfolioTemplateTests(unittest.TestCase):
    def test_dashboard_renders_only_short_summary_and_real_status(self):
        env = Environment(loader=FileSystemLoader(str(ROOT / "app" / "templates")),
                          autoescape=True)
        project = SimpleNamespace(id=2, name="Developer Karel",
                                  description="Detailnější projektový popis", status="active")
        item = {
            "project": project, "spec": {"project_type": "Webová aplikace"},
            "counts": {"waiting_user": 2, "failed": 0, "testing": 1},
            "open": 3, "goal_preview": "Řídit a vyhodnocovat vývoj.",
            "github_status": {"kind": "unlinked", "label": "Nepřipojeno",
                              "detail": "Žádný repozitář."},
            "next_step": {"label": "Zkontrolovat úkoly čekající na tebe (2)",
                          "href": "tasks", "kind": "attention"},
        }
        html = env.get_template("dashboard.html").render(
            app_name="Karel", user=None,
            request=SimpleNamespace(query_params={}),
            projects=[project], archived_projects=[],
            dashboard_projects=[item], dashboard_totals={
                "open": 3, "waiting_user": 2, "failed": 0, "testing": 1},
            deadline_alerts=[],
        )
        self.assertIn("Řídit a vyhodnocovat vývoj.", html)
        self.assertIn("Zkontrolovat úkoly čekající na tebe (2)", html)
        self.assertIn("GitHub: Nepřipojeno", html)
        self.assertIn("/projects/2?view=tasks", html)
        self.assertIn("karel-project-card", html)

    def test_empty_portfolio_has_real_onboarding(self):
        env = Environment(loader=FileSystemLoader(str(ROOT / "app" / "templates")),
                          autoescape=True)
        html = env.get_template("dashboard.html").render(
            app_name="Karel", user=None,
            request=SimpleNamespace(query_params={}),
            projects=[], archived_projects=[], dashboard_projects=[],
            dashboard_totals={"open": 0, "waiting_user": 0,
                              "failed": 0, "testing": 0},
            deadline_alerts=[],
        )
        self.assertIn("Zatím nemáš žádný projekt", html)
        self.assertIn("Založit první projekt", html)
        self.assertNotIn("GitHub: Synchronizováno", html)


if __name__ == "__main__":
    unittest.main()
