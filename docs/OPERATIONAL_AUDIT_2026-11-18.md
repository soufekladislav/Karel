# Karel – revize stavu a GitHub P1 (18. 11. 2026)

## Doložený stav
- GitHub repozitář soufekladislav/Karel je veřejný; default branch main.
- Dokumentační PR #2 byl na pokyn uživatele sloučen do main.
- Kód na main před P1 má 2.0.0-alpha.29, FastAPI/Passenger, Fresh AI Engine, lokální task a projektové modely. Schéma se inicializuje přes Base.metadata.create_all.
- app/services/workflow.py definuje sedm etap, ale storage/brain.json má u app_development šest položek.
- README dlouho nesl alpha.24, deploy.md alpha.28, release-core-29 popisuje lokální testy.

## Co není ověřeno
- Přes pracovní prostředí nešlo načíst karel.freshcrackers.cz/healthz ani /manifest.json; nejde potvrdit běžící verzi, připojení DB ani funkčnost Engine na Exon.io.
- Nelze ověřit práva k GitHub Projects v2 z produkčního serveru; testy budou pouze CI/mock a později staging.
- GitHub repozitář má v historii soubory storage/karel2.db a storage/uploads při veřejné viditelnosti. Zda jsou citlivé, je potřeba ověřit na serveru / s vlastníkem; nemazat bez zálohy.

## Scope P1 – navržený ve feature PR
- Ruční superadminem schválený read-only import jednoho GitHub repo k jednomu existujícímu projektu Karel.
- Povolené vlastníky omezí GITHUB_ALLOWED_OWNERS; volitelný GITHUB_READ_TOKEN zůstává pouze na serveru v .env a není součástí logů nebo DB.
- Načítá repo, Issues, PR, commity, strom, dostupné CI běhy a případně repository-linked Projects v2.
- V DB jediný snapshot cache na project_id. Opakovaná synchronizace přepisuje cache, **nezakládá žádné lokální Tasks** a nikdy nezapisuje do GitHubu.
- Přehled zobrazuje stav připojení, čas posledního úspěšného načtení a nedostupné zdroje.
- Karel dostává jen malý časově označený výtah, ne celý repozitář.

## Přesný postup skutečného produkčního auditu
1. Záloha produkčních souborů, .env a databáze do chráněného úložiště.
2. Ve stávajícím Python venv na serveru spustit samostatný read-only skript scripts/production_audit.py (teprve po jeho nahrání do serverového adresáře). Vrací jen agregované počty, verzi a informaci o schématu.
3. Prověřit /healthz a /manifest.json v bezpečné administrátorské relaci; nesdílet tajemství.
4. Porovnat skutečný HEAD nasazeného kódu, DB typ (SQLite/MariaDB) a provozní logy s GitHubem. Pro novou tabulku github_repo_links ověřit migraci na stagingu.
5. Až poté na stagingu nastavit GITHUB_ALLOWED_OWNERS a GITHUB_READ_TOKEN s nejnižšími možnými právy. Otestovat import a opakování, 403/404, read-only oprávnění a zakázané repo owner.
6. Reálné schválení funkce znamená uživatelský test a porovnání proti GitHub UI.

## Zjištěná omezení a následné kroky
- P1 používá globální serverový token. Proto je spojení oprávněno pouze superadminovi; později přenést oprávnění do Fresh Key/OAuth a navázat na konkrétního uživatele.
- Repository.projectsV2 není automaticky seznam osobních či organizačních Project boardů, kde jsou Issues jen přidané. Nutno dokončit v P1b.
- Import načítá nejvýše 200 Issues, 100 PR, 750 cest, 100 položek per GitHub Project; partial označení je povinné.
- Neexistuje průběžná delta synchronizace / webhook ani GitHub write endpointy, proto nesmí být stav prezentován jako live.
- Automatická tvorba tabulky při startu může vyžadovat CREATE privilege; staging a řízené nasazení jsou povinné.
- Public storage v Git historii je bezpečnostní P0. Ověřit před produkčním nasazením, i když se P1 databáze nijak nedotýká.

## Akceptační brána
Jde o návrh P1 na samostatné větvi. Dokud není CI, staging test a uživatelská akceptace, nesmí být označen jako produkčně funkční.
