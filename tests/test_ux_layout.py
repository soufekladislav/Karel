"""Template/navigation contract checks for the initial six-screen Karel workspace."""
import unittest
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


ROOT = Path(__file__).resolve().parents[1]


class WorkspaceUxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = Environment(loader=FileSystemLoader(str(ROOT / 'app' / 'templates')))
        env.filters['message_md'] = lambda value: value
        cls.templates = env

    def test_existing_templates_remain_parseable(self):
        for name in ('base.html', '_sidebar.html', 'project.html', 'dashboard.html',
                     'library.html', 'github.html', 'settings.html', 'account.html', 'admin.html'):
            with self.subTest(template=name):
                self.templates.get_template(name)

    def test_exact_primary_project_screen_groups_are_present(self):
        menu = (ROOT / 'app' / 'templates' / '_sidebar.html').read_text(encoding='utf-8')
        for name in ('Chat s Karlem', 'Zadání a obchodní cíle', 'GitHub',
                     'Pipeline projektu', 'Knihovny', 'Nastavení a účet'):
            self.assertIn(name, menu)
        self.assertNotIn('Vývoj a historie</summary>', menu)

    def test_github_view_has_real_route_without_legacy_placeholder(self):
        page = (ROOT / 'app' / 'templates' / 'project.html').read_text(encoding='utf-8')
        github = (ROOT / 'app' / 'templates' / 'github.html').read_text(encoding='utf-8')
        main = (ROOT / 'app' / 'main.py').read_text(encoding='utf-8')
        self.assertIn("view == 'github'", page)
        self.assertNotIn('zatím není schválený ani nasazený', page)
        self.assertIn("/projects/{{ project.id }}/github", github)
        self.assertIn("@app.get('/projects/{project_id}/github'", main)
        self.assertIn("github_status=gh_status", main)
        self.assertIn("github_status.kind", github)

    def test_three_focus_surfaces_are_present(self):
        dashboard = (ROOT / 'app' / 'templates' / 'dashboard.html').read_text(encoding='utf-8')
        project = (ROOT / 'app' / 'templates' / 'project.html').read_text(encoding='utf-8')
        github = (ROOT / 'app' / 'templates' / 'github.html').read_text(encoding='utf-8')
        self.assertIn('karel-project-cards', dashboard)
        self.assertIn('item.goal_preview', dashboard)
        self.assertIn('item.next_step.label', dashboard)
        self.assertIn('karel-project-focus', project)
        self.assertIn('project_goal_preview', project)
        self.assertNotIn("<p>{{ project_spec.get('functional_goal')", project)
        self.assertIn('karel-github-connection', github)
        self.assertIn("('synced','error')", github)
        self.assertIn('karel-snapshot-disclaimer', github)

    def test_context_chat_retains_screen_and_authoritative_approval(self):
        page = (ROOT / 'app' / 'templates' / 'project.html').read_text(encoding='utf-8')
        main = (ROOT / 'app' / 'main.py').read_text(encoding='utf-8')
        self.assertIn('name="return_view"', page)
        self.assertIn("return_view:str=Form('chat')", main)
        self.assertIn("return_view not in safe_views", main)
        self.assertIn('destination+anchor', main)
        self.assertIn('Připravený návrh čeká na schválení', page)
        self.assertIn('karel-quick-panel', page)


if __name__ == '__main__':
    unittest.main()
