# Karel – projektový manažer a orchestrátor vývoje

**Aktuální vývojová verze v GitHub `main`: `2.0.0-alpha.36.4-conversational-schedule-replan`.**
Základní repozitář: [soufekladislav/Karel](https://github.com/soufekladislav/Karel).

**Oprava starých formulářů (20. 11. 2026):** WordPress Fresh Core `manifest.json` vložený i do staršího formuláře „Manifest projektu / aplikace“ je bezpečně rozpoznán a předán `/fresh-core/manifest-connect`. Zapisuje se pouze šifrovaná URL a ověřené READ údaje. Po úspěchu nebo chybě se uživatel vrací na `?view=website#fresh-core-pripojeni`, nikoli do chatu. Obecné manifesty jiných aplikací nadále používají původní cestu. Podrobnosti v [Issue #19](https://github.com/soufekladislav/Karel/issues/19).

**Hotfix HTTP 500 (20. 11. 2026):** aktualizován `passenger_wsgi.py` pro Python 3.12+; neinstalované `cryptography` v Exon venv již neshodí celého Karla při importu. Pro správnou činnost konektoru však musí být `requirements.txt` nainstalován **v Passenger venv**. Viz [návod k obnově 500](docs/EXON_SERVER_500_RECOVERY_2026-11-20.md).

**První GitHub funkční celek (20. 11. 2026):** Karlův čtecí snapshot nyní obsahuje i ověřené výňatky vybraných projektových dokumentů. Starší projekty musí provést aktualizaci GitHub snímku, jinak jejich cache ještě neobsahuje texty. Chybějící dokumenty se nesmějí prezentovat jako ověřené. Tato dávka **nepřidává žádné GitHub write, merge ani close operace**.

**Projektový harmonogram:** [sedm etap + datumované funkční milníky 23. 11. 2026–29. 1. 2027](docs/PROJECT_SCHEDULE.md). Dokument je aktuálně **návrh baseline v0.1**, nikoli schválený plán v databázi Karla. Karel jej po GitHub synchronizaci prioritně načítá jako podklad; do plánovacích karet/ProjectStage se data smějí uložit až po schválení. Samotný engine pro deterministické plánování pracovních dnů a přesuny závislostí ještě není implementovaný.

## Vývojový režim (rozhodnutí 20. 11. 2026)
- **`main` je jediná aktuální pracovní vývojová větev.** Karel je stále v raném vývoji a nemá nasazené projekty třetích stran. Vývojové větve a oddělené staging prostředí zavádět až při potřebě stabilizovaného vydání; u každé změny evidovat commit a testy.
- Dřívější [PR #14](https://github.com/soufekladislav/Karel/pull/14) a [PR #21](https://github.com/soufekladislav/Karel/pull/21) jsou **sloučeny do `main`**. Žádné ruční skládání jejich souborů není potřeba.
- **Sloučení v GitHubu není automatické nasazení na Exon.** Skutečná verze na serveru se musí ověřit zvlášť (manifest/health/logy).

**Hotfix skutečného GitHub dotazu v chatu (20. 11. 2026):** Na konkrétní výzvu `projdi / zkontroluj GitHub` Karel nyní používá `github_chat_audit.py` přímo z orchestrátoru. Pokud projekt má vazbu na repozitář, sám vykoná časově označené READ čtení (s omezením opakování), vytvoří věcný přehled včetně odkazů na dokumentaci a Issues a uloží stav do projektu. Administrátorský projekt přesně pojmenovaný `Developer Karel` může bezpečně rozpoznat vlastní `soufekladislav/Karel` i bez ručního kopírování URL; u jiných projektů se identita nehádá. Odpověď na `co už umíš?` nyní výslovně odlišuje aktuální implementaci od budoucích funkcí. Čtení kódu je stále omezené a není plnohodnotným auditem zdrojových souborů.

**První průchod projektovým zadáním a kódem (20. 11. 2026):** Na explicitní požadavek `sestav zadání / projektovou mapu / milníky` Karel nově načte relevantní uživatelské vstupy z historie celého projektu, stávající schválené části mapy a dostupnou dokumentaci z GitHubu. Fresh AI Engine vrací validovaný JSON pro pět stávajících polí. Karel vytvoří pouze **návrh ke schválení**; po potvrzení backend uloží oddělená pole a předchozí verze zachová v historii. GitHub je rozšířen o skutečné porovnání větví a postupné bezpečné čtení zdrojových souborů s uloženým cursor/HEAD, nikoli jednorázový výpis 3 Markdown souborů. To **není** dokončený autonomní audit/cleanup ani nasazení do Exonu. Viz [revize větví a úklidu](docs/GITHUB_HOUSEKEEPING_2026-11-20.md).

**Pipeline – skutečná časová osa (20. 11. 2026):** stránka `?view=development` zobrazuje datumované milníky, jejich akceptaci, závislosti a odkazy na Issues. U administrátorského vlastního projektu Karel použije zatím **neschválený** návrh z lokální kopie `docs/PROJECT_SCHEDULE.md` nainstalované s aktuální verzí. Jiné projekty nezdědí data Karla. Čte i strukturované schválené verze z `ProjectMemory(kind=project_schedule)`, pokud již existují. Neodsouhlasený návrh není označen jako zpožděný. **Tato dávka zatím NEUMÍ** sestavit/odsouhlasit/uložit strukturované milníky z chatu ani zapisovat datumy do GitHub Issues/Projects. Na to naváže další samostatně testovaná dávka (#1, #9). Žádná produkční data, GitHub Issues ani stávající etapy neaktualizuje.

**P0 oprava Pipeline 500 (20. 11. 2026):** původní `_project_timeline.html` používala `project_timeline.items` jako seznam. Jinja2 na slovníku nejprve nalezne metodu `dict.items`, takže stránka vyvolala `TypeError: 'builtin_function_or_method' object is not iterable`. Opraveno na explicitní `project_timeline['items']`. Regresní test nyní **skutečně renderuje šablonu přes Jinja2** s návrhem M0–M6, prázdným plánem a schváleným plánem (předchozí test pouze hledal text šablony). Změna nemění DB ani termíny. Produkční Exon ověřit po restartu.

**Oprava prázdné Pipeline a plánování z GitHubu (20. 11. 2026, alpha.36.3):** Předchozí implementace hledala výchozí návrh harmonogramu pouze na lokální cestě `docs/PROJECT_SCHEDULE.md`. Při nasazení bez složky `docs/` vykreslila prázdný harmonogram, ačkoli README v GitHubu obsahoval M0–M6. Nyní má projekt Karel **výslovně nezávazný záložní návrh M0–M6 zabalený v kódu**, ale vždy upřednostní schválený strukturovaný harmonogram a případně skutečný `docs/` soubor. Návrh není vydáván za aktuální živá GitHub data. Chatový požadavek na přípravu časové osy nejprve načte GitHub přes READ API, ověří HEAD i blob SHA dokumentu a teprve pak vytvoří existující schvalovací akci typu `approve_project_schedule`. **Až po schválení** uloží verzovaná pole a stav do `ProjectMemory(project_schedule)`, ověří znovunačtením a zobrazí v Pipeline. Zpětné zápisy do GitHub Issues/Projects v2, posuny navazujících datumů a obecná tvorba kalendáře jiných projektů nadále čekají (#1, #9). Při chybě GitHubu Karel nezveřejní falešné ověření. Desktopová Pipeline má pouze jeden svislý scroll místo dvou vnořených. Regresní testy zahrnují i chybějící `docs/`, GitHub čtení a schválený databázový zápis.

**Oprava přeplánování časové osy z chatu (alpha.36.4, 20. 11. 2026):** Předchozí verze uměla načíst první harmonogram z GitHubu, ale příkaz `chci testovací verzi do 20.12` nebo `Fajn, zapracuj to prosím do harmonogramu` padal do obecného LLM/write planneru. Nyní má projekt Karel samostatnou cestu `project_schedule_replan`: z aktuální i nedávné uživatelské konverzace získá cílové datum, deterministicky připraví sedm navazujících milestone termínů, předloží porovnání starý/nový a založí schvalovací akci. **Bez schválení nezapisuje.** Po schválení přidá novou historickou verzi `ProjectMemory(project_schedule)`; ověření z DB a audit zachová. Pokud mezitím vznikla novější schválená verze, starý návrh odmítne (optimistické řízení konfliktu). Na stránce Pipeline je čekající schválení viditelné včetně datumů a tlačítka pro potvrzení. GitHub Issues/Projects nejsou v tomto kroku aktualizovány; to vyžaduje samostatný dokončený write konektor. Pilotní přepočet je zatím omezen na **Karlův vlastní 7milníkový plán** a **cílové předání funkční testovací verze**, obecné přeplánování všech projektů a kalendáře svátků dosud není hotové. 20. 12. 2026 je neděle: code freeze je plánován na pátek 18. 12., poté více než měsíc stabilizace a přejímka před produkcí. CI testuje přesnou konverzaci, návrh→schválení→persist→Pipeline i odmítnutí zastaralého schválení.

## Současné schopnosti a omezení
- GitHub: při ruční synchronizaci načte inventuru souborů, Issues, PR, CI a nejvýše 3 Markdown dokumenty se SHA. Z chatu umí na explicitní žádost spustit **živé porovnání větví včetně check runs**, nebo zahájit **postupné čtení zdrojových souborů** z indexu na pevném HEAD. Průběh souborového čtení ukládá v DB, po opakování příkazu `pokračuj v auditu kódu` naváže; podklady pak věcně interpretuje Fresh AI Engine. Jedna dávka čte nejvýše 5 segmentů; nejde o kompletní jednorázový code audit, bez testů a produkčního nasazení. GitHub Projects v2/delta sync a zápisy jsou nadále otevřené (#20, #9).
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
