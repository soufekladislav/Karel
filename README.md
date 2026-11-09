# Karel 2.0 – Clean Workspace (alpha.24)

Kompletní zdrojová verze aplikace určená k čistému nasazení se zachováním existujících dat.

## Změny
- Jediná společná navigace na nástěnce, v detailu projektu a na stránkách knihovny, účtu a nastavení (`app/templates/_sidebar.html`).
- Jednotné přepínání přístupných projektů; seznam projektů a založení projektu z postranního panelu.
- Čitelnější sjednocení typografie, responsivní úpravy, samostatná mobilní navigace na neprojektových stránkách.
- Projektový přehled je pracovní nástěnka: úkoly, požadavky, dokumentace, poslední aktivita, evidované výstupy a termín ze zadání.
- Neexistující workflow release, automatických testů a časové evidence je viditelně označené jako ve vývoji.
- Dokumentace je ve výchozím stavu stručná; jednotlivé oblasti mají rozbalovací detaily.
- Zachovány existující operace, routy a databázové modely, bez nové migrace.

## Co není hotové
Automatická analýza ZIP, řízené release, testovací protokoly, samostatné připomínky a timesheety nejsou v této verzi implementovány.

## Testování
Lokální FastAPI TestClient ověřil přihlášení, vytvoření projektu a HTML odpovědi projektových a účetních obrazovek. Nebyl proveden vizuální test na nasazeném serveru ani kompletní regresní test všech akcí.
