# Karel – nový vývojový základ a provozní pořadí (18. 11. 2026)

## Základní rozhodnutí
Karel je **projektový manažer a orchestrátor**, GitHub je zdrojem pravdy pro Issues/PR/CI a Codex je **vykonavatel pouze schválených vývojových úloh**. V produkci musí mít uživatel jednoduché, srozumitelné rozhraní. Nedělat další izolované prototypy bez provozního dokončení.

**Větve:** `main` je stabilní release; `develop/karel-platform` je jediná dlouhodobá integrační větev. Přechodový draft PR #14 slučuje bezpečnost (#11), UX (#13) a GitHub read-only (#3). Nové malé úpravy mohou mít krátkodobý PR do develop, nikoliv další trvalou hlavní větev. Neprovádět automatický merge/deploy.

## Aktuálně viditelné repozitáře GitHub
Následující deset repozitářů vrátil propojený GitHub účet při čtení 18. 11. 2026. Jde o **inventář GitHub repozitářů, nikoli důkaz, že již existují v Karlově databázi**. Účet může mít další GitHub Projects v2 boardy mimo repozitáře.

| Repozitář | Plánovaný projekt Karla |
|---|---|
| soufekladislav/Karel | Karel |
| soufekladislav/AI-engine | AI Engine |
| soufekladislav/Boban | Boban |
| soufekladislav/Viki | Viki |
| soufekladislav/Linda | Linda |
| soufekladislav/Ema | Ema |
| soufekladislav/Eda | Eda |
| soufekladislav/WP-Fresh-Core | WP Fresh Core |
| soufekladislav/AI---chat | AI Chat |
| soufekladislav/testovaci | Testovací repo (zahrnout, ale označit jako testovací) |

Řešení první etapy: v administraci Karla `/admin/github-import` přehled dostupných repozitářů s volbou „vytvořit / propojit existující / již propojeno / ruční kontrola“. Úprava se provede až po výslovném potvrzení superadmina. Připojení nemění GitHub a netvrdí, že obsah je již synchronizovaný.

## Etapy ověřitelného zprovoznění
### P0 – bezpečný skutečný provoz
- Zjistit přesný kód a DB na Exonu; bezpečně zálohovat. Nenasazovat bez možnosti návratu.
- Staging na `ai-coder.freshcrackers.cz` nebo samostatná ověřená URL (nepřepsat produkční data).
- Konfigurace: `APP_SECRET`, `SESSION_HTTPS_ONLY`, `GITHUB_ALLOWED_OWNERS`, `GITHUB_READ_TOKEN` pokud jsou nutné privátní repozitáře a Projects v2, `MANIFEST_ALLOWED_HOSTS`. Žádná tajemství do GitHub Issues ani repozitáře.
- Ověřit admin/login, manifest, nahrávání příloh, role, starší data a provozní logy.
- Bezpečnostní CI není penetrační test serveru.

### P1 – Portfolio GitHub → Karel
- Ověřit skutečný GitHub API přístup podle oprávnění.
- Spustit náhled a potvrzený **idempotentní** import projektů, bez mazání/ztráty existujícího zadání.
- Zkontrolovat, že každý zvolený repozitář má jednu vazbu; zobrazit historii synchronizace.
- Ručně načíst read-only snapshot Issues, PR, kódu, dokumentace a CI; uložit čas, partial/permission/errors. Nedělat ze snapshotu místní duplicitní Issues.
- Až poté navázat osobní/organizační GitHub Projects v2 boardy, plné stránkování, delta sync, retry a monitoring. Současný P1 konektor je omezený (repo-linked boards max. 10, items max. 100, Issues max. 200).
- Nezaměňovat lokální projekt Karla, GitHub repozitář a GitHub Projects v2 board.

### P2 – Codex v kontrolovaném režimu
- Manuální workflow `.github/workflows/codex-approved-issue.yml` je pouze první **read-only** analýza Issues s označením `karel-approved`, spouštěná vlastníkem. Nemění kód.
- Před skutečným spuštěním nastavit GitHub Actions secret `OPENAI_API_KEY` a ověřit oprávnění/účtování. `workflow_dispatch` workflow musí být dostupné na výchozí větvi repozitáře podle GitHub Actions pravidel.
- Další fáze: Karel schválí malou úlohu, vytvoří evidovanou frontu s limity, Codex na oddělené pracovní větvi upraví kód a předá draft PR. Povinné skutečné CI výsledky, diff, náklady, log a akceptace uživatele. Žádné automatické nasazení či merge.
- Po ověření Karla lze Codex používat přes stejný standard také pro Bobana, Viki, Lindu a další projekty. Přístupové tokeny a pracovní prostředí musí být izolované po repozitářích.

### P3 – Projektové řízení celé firmy
- Karel sleduje schválené zadání a obchodní cíl, GitHub Issues, PR, blokace, CI, změny verzí a skutečný stav nasazení.
- Sedm etap řízení projektu zůstává odděleno od stavů jednotlivých úkolů a PR.
- Knihovna standardů verzovaná a používaná napříč projekty. Změny se nepřenášejí bez schválení a kontroly kompatibility.

## Definice hotovo
Issue je hotové jen pokud proběhla implementace, úspěšné automatické testy, ověření v provozním prostředí odpovídajícím produkci a akceptace uživatele. Stav `PR created` není totéž co `done`.

## Co je ověřené a co ne
- **GitHub:** vytvořena a čitelná integrační větev a PR #14; práce na repozitáři skutečně probíhají.
- **CI:** průběžně běží GitHub Actions testy, závěrečné testy z posledního commitu je nutné vyhodnotit.
- **Karel produkce:** nesmí být označen za otestovaný bez přístupu do produkčního prostředí.
- **Import:** backend/UI implementována ve vývojové větvi; žádná záznamová změna produkční DB nebyla provedena.
- **Codex:** workflow připravené v kódu; bez klíče a skutečného prvního úspěšného běhu není nástroj nasazený.
