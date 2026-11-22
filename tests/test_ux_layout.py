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
        for name in ('base.html', '_sidebar.html', '_project_mobile_nav.html', 'project.html', 'dashboard.html',
                     'library.html', 'github.html', '_project_journey.html', 'settings.html', 'account.html', 'admin.html'):
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

    def test_mobile_navigation_is_shared_with_github(self):
        nav = (ROOT / 'app' / 'templates' / '_project_mobile_nav.html').read_text(encoding='utf-8')
        page = (ROOT / 'app' / 'templates' / 'project.html').read_text(encoding='utf-8')
        github = (ROOT / 'app' / 'templates' / 'github.html').read_text(encoding='utf-8')
        self.assertIn("include '_project_mobile_nav.html'", page)
        self.assertIn("include '_project_mobile_nav.html'", github)
        self.assertIn('project-mobile-nav', nav)
        self.assertIn("view=='github'", nav)

    def test_github_import_is_user_facing_but_server_token_remains_restricted(self):
        repo_import = (ROOT / 'app' / 'templates' / 'github_import.html').read_text(encoding='utf-8')
        github = (ROOT / 'app' / 'templates' / 'github.html').read_text(encoding='utf-8')
        main = (ROOT / 'app' / 'main.py').read_text(encoding='utf-8')
        admin = (ROOT / 'app' / 'templates' / 'admin.html').read_text(encoding='utf-8')
        self.assertIn('action="/github/import"', repo_import)
        self.assertIn('name="map_{{ item.full_name }}"', repo_import)
        self.assertIn('href="/github/import"', github)
        self.assertIn("@app.get('/github/import'", main)
        self.assertIn("@app.post('/github/import')", main)
        self.assertIn("if not is_superadmin(u):", main)
        self.assertNotIn('href="/admin/github-import"', admin)

    def test_project_first_run_is_a_conversation_not_forced_form(self):
        page = (ROOT / 'app' / 'templates' / 'project.html').read_text(encoding='utf-8')
        main = (ROOT / 'app' / 'main.py').read_text(encoding='utf-8')
        self.assertIn('karel-starter-options', page)
        self.assertIn('Připravit zadání s Karlem', page)
        self.assertIn('<details class="fresh-detail"><summary>Upravit zadání ručně', page)
        self.assertIn("guide=project-start", page)
        self.assertIn("guide={'wordpress':'wp-start','github':'github-start','general':'project-start'}", main)

    def test_empty_project_and_library_have_guided_actions(self):
        project = (ROOT / 'app' / 'templates' / 'project.html').read_text(encoding='utf-8')
        library = (ROOT / 'app' / 'templates' / 'library.html').read_text(encoding='utf-8')
        settings = (ROOT / 'app' / 'templates' / 'settings.html').read_text(encoding='utf-8')
        self.assertIn("{% if not project_has_activity and project_mode == 'general' %}", project)
        self.assertIn('class="karel-project-empty-start"', project)
        self.assertIn('Projektové workflow · 7 etap', project)
        self.assertIn('karel-library-empty', library)
        self.assertIn('Přidat první položku', library)
        self.assertNotIn('<details class="fresh-detail" open><summary>Fresh Key', settings)

    def test_wordpress_and_github_have_distinct_workflows_in_ui(self):
        dashboard=(ROOT/'app'/'templates'/'dashboard.html').read_text(encoding='utf-8')
        project=(ROOT/'app'/'templates'/'project.html').read_text(encoding='utf-8')
        nav=(ROOT/'app'/'templates'/'_sidebar.html').read_text(encoding='utf-8')
        mobile=(ROOT/'app'/'templates'/'_project_mobile_nav.html').read_text(encoding='utf-8')
        journey=(ROOT/'app'/'templates'/'_project_journey.html').read_text(encoding='utf-8')
        main=(ROOT/'app'/'main.py').read_text(encoding='utf-8')
        self.assertIn('Mám WordPress web', dashboard)
        self.assertIn('Vyvíjím aplikaci nebo web', dashboard)
        self.assertIn('name="project_mode_choice"', dashboard)
        self.assertIn('name="website_url"', dashboard)
        self.assertIn("view == 'website'", project)
        self.assertIn("www.freshcrackers.cz/produkt/fresh-core/", project)
        self.assertIn('Fresh Core', project)
        self.assertIn("include '_project_journey.html'", project)
        self.assertIn('Připravujeme', journey)
        self.assertIn('Můj WordPress', nav)
        self.assertIn("view=='website'", mobile)
        self.assertIn("@app.post('/projects/{project_id}/mode')", main)
        self.assertIn("@app.post('/projects/{project_id}/website-url')", main)

    def test_context_chat_retains_screen_and_authoritative_approval(self):
        page = (ROOT / 'app' / 'templates' / 'project.html').read_text(encoding='utf-8')
        base = (ROOT / 'app' / 'templates' / 'base.html').read_text(encoding='utf-8')
        drawer = (ROOT / 'app' / 'templates' / '_assistant_drawer.html').read_text(encoding='utf-8')
        script = (ROOT / 'app' / 'static' / 'karel-assistant.js').read_text(encoding='utf-8')
        main = (ROOT / 'app' / 'main.py').read_text(encoding='utf-8')
        self.assertIn("include '_assistant_drawer.html'", base)
        self.assertIn('id="karel-assistant-launcher"', drawer)
        self.assertIn('id="karel-assistant-project"', drawer)
        self.assertIn('id="karel-assistant-messages"', drawer)
        self.assertIn("body.set(\"screen_context\"", script)
        self.assertIn('"/assistant/approve"', script)
        self.assertIn("return_view:str=Form('chat')", main)
        self.assertIn("return_view not in safe_views", main)
        self.assertIn("await send_message(", main)
        self.assertIn("response=approve_chat_actions(", main)
        self.assertIn('Čeká na schválení', script)
        self.assertNotIn('karel-quick-panel', page)


if __name__ == '__main__':
    unittest.main()
