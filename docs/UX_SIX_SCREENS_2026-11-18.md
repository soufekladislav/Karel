# Karel – přehledný pracovní prostor, první UX průchod

Stav: návrh v samostatném draft PR. Není nasazená ani uživatelsky otestovaná produkční změna.

## Hlavní navigace
1. Chat s Karlem
2. Zadání a obchodní cíle
3. GitHub (zatím stavový placeholder; čtecí import až z PR #3)
4. Pipeline projektu (přehled, úkoly, testování, výstupy, historie, další)
5. Knihovny (dosavadní account library)
6. Nastavení a účet (konfigurace, účet, projektové zdroje, admin podle oprávnění)

Přepínač projektu je dostupný z celého účtu. Starší adresy projektových pohledů a jejich backend operace zůstávají zachované; nejde o migraci DB ani odstranění funkcí.

## Kontextový chat
- Na ostatních projektových pohledech přidán pravý panel posledních zpráv a formulář pro odeslání zprávy.
- `return_view` je na backendu omezen na seznam známých obrazovek, aby uživatel po odpovědi zůstal na místě.
- Rozhraní předává jako pomocnou informaci původní obrazovku. Nepředstírá, že byly automaticky načteny GitHub data.
- Schválení a práce s přílohami zůstávají v plném chatu; zmenšený panel na ně odkazuje.

## Zachované funkce
Historie chatů, projektové zadání, lokální úkoly, sedm etap, knihovna, Fresh Key, účet, admin, soubory, výstupy a původní URL routy.

## Akceptace před nasazením
- Na desktopu: výběr projektu, všech 6 položek, čitelnost, hlavní chat, odeslání z dokumentace a pipeline, návrh ke schválení.
- Na mobilu: navigace, pipeline podmenu, zobrazení a obsluha kontextového chatu, přístup k účtu a knihovně.
- Regrese: vytvoření a úprava projektu, upload, archivace chatu, přístupová práva reader/editor, workflow, uživatelská správa.
- E2E: Chrome/Edge na desktopu a alespoň jedna skutečná mobilní obrazovka; test v přihlášené staging instanci, žádná manipulace s produkční DB.
- Teprve po schválení UX řešit další složitější funkce GitHubu a workerů.

Tento PR řeší první průchod UX, ne konečný design systém ani hotový GitHub konektor.
