# Karel – projektový manažer a orchestrátor vývoje

**Aktuální vývojová verze v GitHub `main`: `2.0.0-alpha.35.3-github-document-context`.**
Základní repozitář: [soufekladislav/Karel](https://github.com/soufekladislav/Karel).

**Oprava starých formulářů (20. 11. 2026):** WordPress Fresh Core `manifest.json` vložený i do staršího formuláře „Manifest projektu / aplikace“ je bezpečně rozpoznán a předán `/fresh-core/manifest-connect`. Zapisuje se pouze šifrovaná URL a ověřené READ údaje. Po úspěchu nebo chybě se uživatel vrací na `?view=website#fresh-core-pripojeni`, nikoli do chatu. Obecné manifesty jiných aplikací nadále používají původní cestu. Podrobnosti v [Issue #19](https://github.com/soufekladislav/Karel/issues/19).

**Hotfix HTTP 500 (20. 11. 2026):** aktualizován `passenger_wsgi.py` pro Python 3.12+; neinstalované `cryptography` v Exon venv již neshodí celého Karla při importu. Pro správnou činnost konektoru však musí být `requirements.txt` nainstalován **v Passenger venv**. Viz [návod k obnově 500](docs/EXON_SERVER_500_RECOVERY_2026-11-20.md).

**První GitHub funkční celek (20. 11. 2026):** Karlův čtecí snapshot nyní obsahuje i ověřené výňatky vybraných projektových dokumentů. Starší projekty musí provést aktualizaci GitHub snímku, jinak jejich cache ještě neobsahuje texty. Chybějící dokumenty se nesmějí prezentovat jako ověřené. Tato dávka **nepřidává žádné GitHub write, merge ani close operace**.

## Vývojový režim (rozhodnutí 20. 11. 2026)
- **`main` je jediná aktuální pracovní vývojová větev.** Karel je stále v raném vývoji a nemá nasazené projekty třetích stran. Vývojové větve a oddělené staging prostředí zavádět až při potřebě stabilizovaného vydání; u každé změny evidovat commit a testy.
- Dřívější [PR #14](https://github.com/soufekladislav/Karel/pull/14) a [PR #21](https://github.com/soufekladislav/Karel/pull/21) jsou **sloučeny do `main`**. Žádné ruční skládání jejich souborů není potřeba.
- **Sloučení v GitHubu není automatické nasazení na Exon.** Skutečná verze na serveru se musí ověřit zvlášť (manifest/health/logy).

## Současné schopnosti a omezení
- GitHub: při ruční synchronizaci Karel nově čte obsah nejvýše 3 **vybraných Markdown dokumentů** (typicky README, produktovou dokumentaci, AGENTS), připne jejich blob SHA a bezpečně omezené výňatky uloží se snapshotem i do kontextu chatu. Na GitHub kartě vypíše, co skutečně četl. **Nejde o kompletní audit kódu** a GitHub Projects v2/delta sync/zápisy jsou stále otevřené (#20, #9). Přejímací otázka: „Co je Linda a co má umět?“ musí mít odpověď z README a docs/PARITY.md i při nulových Issues.
- Fresh Core: **dva způsoby READ** – přímý REST Access Key nebo soukromá Connector Manifest URL jako v Bobanovi. Manifest se ověří (identita webu, dokončení dávky, kontrolní součty vybraných souborů), zašifruje a automaticky nastaví projektovou URL. Inventura a diff změn jsou dostupné v kartě webu i chatu. Samostatný Write Key lze ověřit pouze přes `GET /write/ping`; skutečné zápisy do WP nejsou povoleny. Celý obsah exportů, runtime PHP/JS diagnostika a obecné editace pluginů dosud nejsou hotové (#19).
- Karel je projektový manažer, nikoli automatický vývojář ani nástroj s neomezeným přístupem do WordPressu.

## Nasazení aktuálního `main` na Exon
1. Zálohovat serverovou DB, `storage/`, uživatelské soubory, `.env` a konfigurační klíče mimo webový root. **Nesmazat serverová data `storage/` při přechodu:** historické testovací soubory byly z GitHubu odstraněny a nyní jsou ignorovány.
2. Nasadit kompletní ověřený commit z `main`, nikoli jednotlivé soubory; zachovat serverovou `.env`, nainstalovat nové Python dependencies do správného Passenger virtualenv.
3. Ověřit kompatibilitu databáze, bezpečnostní konfiguraci a migraci podle [Exon provozní akceptace](docs/EXON_PRODUCTION_ACCEPTANCE.md); restartovat Passenger.
4. Fresh Core vault: stávající `FRESH_CORE_VAULT_KEY` **zachovat**; pokud není nastaven, Karel vytvoří bezpečný 0600 klíč v domovském adresáři účtu při prvním propojení. `FRESH_CORE_ALLOWED_HOSTS` zůstává nepovinný přísnější whitelist. Nový klíč či URL manifestu nikdy nevkládat do chatu nebo GitHubu.
5. Ověřit skutečnou verzi `alpha.35`, login, projekt, GitHub a připojení existujícího Fresh Core přes manifest (bez nutnosti REST klíče), poté obnovu a změnovou kontrolu. Podrobný návod: [Fresh Core manifest a Write Key](docs/FRESH_CORE_MANIFEST_CONNECTION_2026-11-20.md).

**GitHub CI není důkaz produkční funkčnosti.** Na Exon zatím z tohoto repozitáře automaticky nic nenasazujeme.

## Dokumentace
- [Produktová specifikace](docs/PRODUCT_SPECIFICATION.md)
- [Architektura a synchronizace](docs/ARCHITECTURE_AND_SYNCHRONIZATION.md)
- [Realizační plán](docs/IMPLEMENTATION_PLAN.md)
- [Fresh Core manifest + Write Key alpha.35](docs/FRESH_CORE_MANIFEST_CONNECTION_2026-11-20.md)
- [Fresh Core READ audit alpha.34](docs/FRESH_CORE_READ_AUDIT_2026-11-20.md)
- [Pravidla pro Codex/AI](AGENTS.md)

---

## Historie
Níže uvedené změny starších verzí popisují jejich tehdejší stav. Není to aktuální seznam hotových funkcí.

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
