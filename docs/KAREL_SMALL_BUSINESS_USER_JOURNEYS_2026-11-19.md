# KAREL – produktové workflow pro malé podnikatele (závazné zadání)
**Schválená obchodní vize uživatele, 19. 11. 2026.** Založit návaznost na EPIC #1, UX #12, GitHub #6–#8 a Codex #10.

## Proč produkt existuje
Karel je **konzultant a vývojový projektový manažer**, který malému podnikateli pomáhá řídit WordPress web nebo vlastní aplikaci. Uživatel nesmí potřebovat předchozí zkušenost s programováním, GitHubem ani správou serveru. První dojem musí dát jasnou odpověď:
1. **Co Karel pro mě udělá a jak mi ušetří čas?**
2. **Co mám udělat jako první?**
3. **Co už Karel skutečně zjistil a co ještě neumí bez propojení?**
4. **Co čeká na můj souhlas?**
5. **Kde je výsledek, test a historie?**

Přehledové karty nejsou kopie GitHubu nebo WordPress administrace. Zobrazují podstatu, provozní stav, termín, blokace, důležité odkazy a jedno doporučené další tlačítko. Detail otevřou na původním zdroji.

## A. První cesta – „Mám WordPress“

**Cílový dialog:** „Ahoj, jsem Karel. Pomohu ti se správou webu, úpravami a plánováním. Abych bezpečně viděl, co se na webu děje, nainstaluj Fresh Core. Provedu tě tím krok za krokem.“

1. Založit **webový projekt**: název a adresa webu (URL uživatele je zatím pouze uložená informace; není potvrzeno, že mu web patří).
2. **Nainstalovat Fresh Core**: jasný odkaz na ověřený zdroj pluginu a tři krátké kroky instalace v WP. Jde o samostatnou instalaci na webu uživatele, ne o instalaci na server Karla.
   - Ověřená stránka produktu: https://www.freshcrackers.cz/produkt/fresh-core/ (produkt s digitálním stažením po objednávce, aktuálně uvedeno 0 Kč).
   - Ověřený zdroj kódu: https://github.com/soufekladislav/WP-Fresh-Core; GitHub Releases zatím nemá publikovaný instalační release ZIP.
   - **Karel nesmí tvrdit „plugin je nainstalovaný“ jen proto, že uživatel klikl na odkaz.**
3. **Ověřit bezpečné spojení** mezi daným WordPressem a Karlem: autorizace přes Fresh Key / Fresh Core, rozlišené read a write oprávnění, čas posledního úspěšného spojení, odvolatelnost. Dnes v Karlovi **NENÍ hotové**.
4. Z načtených a skutečně ověřených dat navrhnout **obchodní cíl webu**, strukturu, audit a plán. Uložit po schválení uživatele, ne tichým přepsáním.
5. Každá žádost o změnu: **chat → konkrétní úkol → návrh změny → uživatelský souhlas → omezený zápis Fresh Core → read-after-write ověření → historie/vrácení změny**. Zápis se v Karla smí aktivovat až po ověření implementace v dalších issues.
6. Pro méně technické uživatele: krok po kroku, bez tokenů a názvů API v hlavním UI. Technické detaily v rozbalovací části.

### Akceptační scénář WP
Majitel WordPress webu do 2 kliknutí ví, jak Fresh Core získat a nainstalovat. Chápe, že kliknutí/instalace ještě neznamená propojení. Pokud konektor neodpovídá, UI neukazuje smyšlený audit ani „připraveno k zápisu“. Žádnou změnu nelze provést bez schválení.

## B. Druhá cesta – „Vyvíjím aplikaci nebo web“

**Cílový dialog:** „Založíme projekt a propojíme GitHub. Projdu, co už máš připravené, a pomohu ti řídit další kroky. Nemusíš mi znovu opisovat zadání.“

1. Založit **vývojový projekt** nebo **importovat repozitáře** ze svého GitHub účtu; mapovat na existující projekty bez duplicit.
2. Bezpečná **autorizace uživatele ke GitHubu** přes GitHub App/OAuth (ve vývoji). Do doby jejího dokončení je shared-token import dostupný pouze superadminovi. Nikdy neukazovat sdílený PAT zákazníkovi.
3. **Načíst a synchronizovat** relevantní dokumentaci, Issues, PR, CI a Projects v2 včetně stavu úplnosti a poslední aktualizace. GitHub zůstává zdrojem pravdy. Dnes existuje pouze ruční read-only snapshot, nikoliv plná průběžná synchronizace.
4. Karel projde repo a schválené standardy knihovny, připraví podklad zadání, obchodní cíl, harmonogram a malé realizační úkoly. Ověřit s uživatelem, nezapisovat automaticky špatně rozpoznané zadání.
5. **Schválený úkol → GitHub Issue → Codex/worker → malý PR → CI → uživatelská akceptace → testovací prostředí → výslovný souhlas s produkcí**. Codex worker a automatické nasazení dnes nejsou hotové.
6. Karel ukazuje **jen současný stav a relevantní odkazy** („PR #123 hotový, otevřít GitHub“, „Testování připraveno, otevřít testovací prostředí“). Nezrcadlit celé GitHub UI a nevydávat CI za skutečný produkční test.
7. **Ostré nasazení nikdy bez lidského souhlasu**, ověřené zálohy, rollbacku a průkazného výsledku testu.

### Akceptační scénář GitHub
Uživatel po vytvoření projektu vidí jednoznačnou nabídku připojení GitHubu a aktuální status. Žádná Jira/GitHub náhražka s prázdnými kolonami. Při úspěšném read-only snapshotu lze přejít na originální Issue/PR jedním kliknutím. Před chybějící autorizací se nejde tvářit jako propojený účet.

## Společná informační architektura

| Místo | Smysl pro laika | Zásada |
|---|---|---|
| **Moje projekty** | „Co řešíme a co potřebuje můj souhlas?“ | Dvě jasné cesty pro nový projekt; aktivní práce se řadí před technické detaily |
| **Chat s Karlem** | „Řeknu jednou větou, co potřebuji.“ | Kontext projektu, vedený dialog, návrhy; ne automatické neodsouhlasené změny |
| **Přehled projektu** | „Co víme, co se děje a co přijde?“ | Cíl, propojení, nejbližší krok, rozhodnutí, výsledek; 3–5 etap podle typu |
| **Zadání a dokumentace** | „Co už jsme odsouhlasili?“ | Stručné schválené shrnutí, historie rozhodnutí, ruční detail volitelně |
| **GitHub / Zdroj** | „Odkud Karel zná projekt?“ | Status, čas synchronizace, odkazy na originál, Import pouze při oprávnění |
| **Úkoly / Pipeline** | „Co se dělá, kdo čeká a co je hotovo?“ | Task, termín, schválení, stav testu, čitelný odkaz |
| **Knihovna** | „Co umí Karel opakovaně použít?“ | Schválené verze standardů a komponent (verzování teprve dokončit) |
| **Nastavení / Účet** | „Čemu mám dát přístup a kde ho odeberu?“ | Uživatel a propojené služby; interní diagnostika do superadmina |
| **Superadmin** | „Jak běží služba a jak podpořím zákazníky?“ | Administrace, uživatelé, server, náklady; ne běžný import projektů |

## Kontrakt stavu funkcionality

**Dostupné po testu:** skutečně fungující funkce s potvrzeným serverovým výsledkem.

**Připojení vyžaduje akci:** například „Nainstalovat Fresh Core“, „Připojit GitHub“. Nesmí se automaticky označit za úspěch při kliknutí.

**Připravujeme:** WordPress write konektor v Karlovi, GitHub OAuth pro ostatní uživatele, automatické Issues/Projects synchy, Codex, staging/production worker.

**Chyba:** zobrazit příčinu srozumitelně, naposledy ověřená data nesmazat, umožnit nový pokus.

**Žádná falešná demoverze:** nikdy nesimulovat výpis WordPress pluginů, stav webu, GitHub Issues, CI, dokončený task, odpověď AI ani úspěšné nasazení.

## UX implementační iterace (malé schvalované kroky)

1. P0 – dvoucestné založení projektu s uložením typu do stávajícího `project_spec.project_type` (bez migrace). WordPress URL pouze uživatelský údaj, před přímým čtením nutné ověření.
2. P0 – hlavní karty: řízená cesta WordPress/GitHub, stav zdrojů a jedno CTA, průvodce instalací Fresh Core s pravdivým odkazem; prázdný projekt před KPI nabídne vstupní cestu.
3. P1 – per-user GitHub autorizace + úplná skutečná synchronizace + mapa repo. Navázat #6–#8.
4. P1 – Fresh Core handshake, read-only audit + oprávnění a účet; oddělená implementace od UX.
5. P2 – návrhy Task/Issue + schválení + bezpečné zápisy / Codex / staged deploy; navázat #10 a samostatné WP Issue.
6. P2 – knihovna schválených verzovaných standardů, termíny, reporting napříč projekty.

## Definition of Done
- 15min test na skutečném účtu začínajícího uživatele WordPress i GitHub: pochopí, co Karel nabízí, kde získá zdroj, zda je připojen, proč čeká na souhlas a kam jít dál.
- Klikací desktop a mobilní test, bez mrtvých CTA a překryvů, Poppins a současný Fresh styl.
- Nezměnit historické projekty/DB schéma ani bezpečnostní oprávnění; každá cesta rozlišuje dostupnou funkci od plánu.
- Automatický test navigace, renderu šablon, role/scope, vytvoření projektu a uložení typu; následně staging a uživatelská akceptace.
