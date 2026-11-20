# Karel – projektový manažer a orchestrátor vývoje

**Aktuální vývojová verze v GitHub `main`: `2.0.0-alpha.34-fresh-core-read-audit`.**
Základní repozitář: [soufekladislav/Karel](https://github.com/soufekladislav/Karel).

## Vývojový režim (rozhodnutí 20. 11. 2026)
- **`main` je jediná aktuální pracovní vývojová větev.** Karel je stále v raném vývoji a nemá nasazené projekty třetích stran. Vývojové větve a oddělené staging prostředí zavádět až při potřebě stabilizovaného vydání; u každé změny evidovat commit a testy.
- Dřívější [PR #14](https://github.com/soufekladislav/Karel/pull/14) a [PR #21](https://github.com/soufekladislav/Karel/pull/21) jsou **sloučeny do `main`**. Žádné ruční skládání jejich souborů není potřeba.
- **Sloučení v GitHubu není automatické nasazení na Exon.** Skutečná verze na serveru se musí ověřit zvlášť (manifest/health/logy).

## Současné schopnosti a omezení
- GitHub: ruční READ snapshot / import a základní přehled Issues, PR a CI. Kompletní dokumentace/obsah souborů, Projects v2 a delta synchronizace jsou stále rozpracované (#20).
- Fresh Core: READ-only `ping` → `snapshot`, šifrovaný projektový Access Key, rozšířená inventura WordPressu a porovnání dvou úspěšně načtených stavů. **Není** implementováno úplné čtení statického batch manifestu, runtime PHP/JS diagnostika ani WordPress zápisy (#19).
- Karel je projektový manažer, nikoli automatický vývojář ani nástroj s neomezeným přístupem do WordPressu.

## Nasazení aktuálního `main` na Exon
1. Zálohovat serverovou DB, `storage/`, uživatelské soubory, `.env` a konfigurační klíče mimo webový root. **Nesmazat serverová data `storage/` při přechodu:** historické testovací soubory byly z GitHubu odstraněny a nyní jsou ignorovány.
2. Nasadit kompletní ověřený commit z `main`, nikoli jednotlivé soubory; zachovat serverovou `.env`, nainstalovat nové Python dependencies do správného Passenger virtualenv.
3. Ověřit kompatibilitu databáze, bezpečnostní konfiguraci a migraci podle [Exon provozní akceptace](docs/EXON_PRODUCTION_ACCEPTANCE.md); restartovat Passenger.
4. Ve skutečné serverové konfiguraci nastavit bezpečný stálý `FRESH_CORE_VAULT_KEY` (nepřepisovat existující), `FRESH_CORE_ALLOWED_HOSTS` jen pro povolené weby. Klíče nikdy do chatu, URL ani GitHubu.
5. Ověřit skutečnou verzi `alpha.34`, login, projekt, GitHub a čtecí spojení Fresh Core na kontrolovaném WordPressu včetně opakovaného refresh a změnové kontroly.

**GitHub CI není důkaz produkční funkčnosti.** Na Exon zatím z tohoto repozitáře automaticky nic nenasazujeme.

## Dokumentace
- [Produktová specifikace](docs/PRODUCT_SPECIFICATION.md)
- [Architektura a synchronizace](docs/ARCHITECTURE_AND_SYNCHRONIZATION.md)
- [Realizační plán](docs/IMPLEMENTATION_PLAN.md)
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
