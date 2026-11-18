# Karel – realizační plán po malých dávkách

Toto je plán požadavků, ne potvrzení hotových funkcí. Nedělat vše v jednom Codex zadání; každá fáze končí testem.

## P0 – Sjednotit zdroj pravdy a audit [nejvyšší priorita]
- [ ] Porovnat nasazenou aplikaci, manifest, skutečný DB schema a HEAD GitHubu; zaznamenat rozpory, rizika migrace, existující uživatelská data a verzování.
- [ ] Bezpečnostní kontrola: veřejný repozitář obsahuje storage/karel2.db a storage/uploads; ověřit, zda jde jen o neškodná testovací data. Pokud ne, řešit bezpečné odstranění z historie a případnou rotaci uniklých tajemství. Nesmazat bez zálohy a bez schválení.
- [ ] Sladit neshodu mezi sedmi etapami v app/services/workflow.py a šesti položkami pro app_development v storage/brain.json.
- [ ] Sjednotit README, verzi a status dokumentace; zachovat historii alpha release.
- [ ] Definovat datové kontrakty mezi GitHubem, projektem Karel a knihovnou, bez duplikace původních Issues.
- **Akceptace:** audit zobrazí doložené důkazy, seznam rozdílů a nulové změny uživatelských dat.

## P1 – Čtecí GitHub konektor a převzetí projektu [MVP 1]
- [ ] Autorizace a bezpečné propojení repozitáře (ideálně Fresh Key / úzká oprávnění).
- [ ] Čtení repo, branches, kódu a manifestů, commitů, Issues, PR a check/Actions běhů s odkazy.
- [ ] Samostatně prokázat dostupnost GitHub Projects v2 a načíst položky, stavy, pole, priority a termíny tam, kde přístup existuje.
- [ ] Read-only initial import, mapování lokálních úkolů a externích ID, kontrola duplicity.
- [ ] Stav připojení, poslední úspěšná synchronizace, vysvětlení chyb API.
- **Akceptace:** minimálně dva skutečné repozitáře, jeden s Issues/PR a jeden bez; opakovaný import nic nezdvojí, nenastane žádný externí zápis.

## P2 – Projektový dialog, dokumentace a knihovna [MVP 2]
- [ ] Nad importovanými podklady vytvořit mapu obchodních cílů, rozsahu, architektury, rizik a časový plán; každé tvrzení dohledatelné.
- [ ] Zachovat existující sedm etap, schvalování a projektové úkoly; výstup navázat na reálné GitHub Issues.
- [ ] Rozdílové návrhy a jedno schválení pro každou související skupinu; lokální draft ≠ GitHub změna.
- [ ] Verze knihovny a retrieval jen relevantních standardů; prompt budget a dokumentované invalidace cache.
- **Akceptace:** uživatel schválí plán; Karel nevymýšlí neexistující Issues, nevyžaduje znovu již dostupné podklady a nezapíše nic bez souhlasu.

## P3 – GitHub zápisy, plánování a fronta [MVP 3]
- [ ] Schválené create/update/close Issues a změny Project item statusu s idempotencí a kontrolou výsledku.
- [ ] Stavový model jobů, závislosti, priority, pause/resume, bezpečné retry, lease a fronta.
- [ ] Limit nákladů, pokusů, času a tokenů; evidence skutečných nákladů a důvodů stop.
- [ ] Jednotlivý úkol se připraví jako malý kontextový balíček s SHA a knihovní verzí.
- **Akceptace:** schválená změna se objeví na GitHubu, konflikt se nepřepíše; dvě frontové úlohy respektují závislosti; přerušení/resume neprovede duplicitní akci.

## P4 – Codex/Fresh AI Engine exekuce, PR, CI a akceptace [MVP 4]
- [ ] Bezpečný executor adapter: jeden malý úkol → branch/PR → výsledky testů.
- [ ] Načíst CI/check statuses; nedokončené nebo selhané testy nahlásit jako problém.
- [ ] Uživatelský testovací protokol (prostředí, kroky, očekávání, skutečnost, rozhodnutí).
- [ ] Selhání → opravné issue/job; schválení → synchronizace stavů a aktualizace dokumentace.
- **Akceptace:** úspěšný a záměrně neúspěšný end-to-end test; žádné automatické uzavření před akceptací, všechny přechody auditovatelné.

## P5 – Stabilita, náklady a provoz [až po MVP]
- [ ] Reconciliation job, rate-limit handling, přehled stárnutí snapshotů, provozní alerting a zastavení při chybách.
- [ ] Měření času a ceny každé fáze, cache hit-rate, procento úspěšných testů, čas zásahu uživatele.
- [ ] Mobilní UX, přístupnost, regresní testy, staging a produkční rollout se zálohou/rollbackem.
- **Akceptace:** 30 dní provozních dat bez ztracených či duplicitních úloh; průkazná úspora opakovaného načítání kontextu.

## Povinná definice hotového dílčího Issue
- Účel a obchodní přínos; přesný rozsah a mimo rozsah.
- Odkazy na zdroje/aktuální kód a ověřenou výchozí verzi.
- Akceptační kritéria včetně negativního testu.
- Závislosti, priorita, odhad časové i tokenové náročnosti.
- Implementační PR + testovací výsledek + status uživatelského převzetí.
- Pokud je výsledek jen lokálně ověřen, označit „čeká na produkční test“; ne „hotovo“.

## Pravidla spuštění
Začít P0 a první read-only částí P1. Dokud neznáme stav produkce a GitHub přístupů, **nepouštět autonomní zápisy ani dávkovou exekuci**. Každý krok zkontrolovat s uživatelem, teprve pak posunout stav.
