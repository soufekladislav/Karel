# Karel – závazné produktové zadání (návrh 2026-11-18)

**Stav:** cílová produktová specifikace, průběžně ověřovaná v projektu. Původní dokumentační PR #2 byl sloučen 18. 11. 2026. Sloučení do kódu **není** schválením znění v aktuální projektové databázi ani důkazem hotových funkcí.
**Úloha:** projektový manažer a orchestrátor vývoje pro Fresh Crackers. Karel **není programátor** ani náhrada GitHubu, Codexu nebo Fresh AI Engine.

## Obchodní cíl
Snížit čas majitele věnovaný operativnímu řízení vývoje, počet opakovaných analýz a spotřebu tokenů, omezit chybné nebo nedokončené implementace. Výstupem musí být funkční a testované projekty, nikoli líbivá administrace nebo množství vygenerovaných dokumentů.

## Zásady (závazné)
1. GitHub je hlavní zdroj pravdy pro repozitáře, kód, Issues, Pull Requesty, GitHub Projects, historii změn a CI výsledky. GitHub Projects (plánování/stavy) a GitHub Actions (CI/pipeline) jsou odlišné zdroje.
2. Karel používá vlastní databázi pro uživatelský dialog, návrhy před schválením, běhy fronty, diagnostiku, účetní náklady, cache a pracovní snapshoty. Nesmí v ní vzniknout druhá nesynchronizovaná pravda o Issues.
3. Při připojení stávajícího projektu se nejprve provede bezpečný **read-only import**, audit stavu a návrh mapování. Případné zápisy, přesuny a uzavírání stávajících Issues vyžadují schválení.
4. Každá změna uživatelem řízených dat a každé nasazení je návrh → schválení → provedení → ověření skutečného výsledku. Žádný automatický merge do main ani produkční release bez výslovného souhlasu.
5. Z jednoho schváleného zadání vznikají malé, samostatně testovatelné úkoly s cílem, vstupy, závislostmi, očekávaným výsledkem a rozpočtem. Karel předává Codexu/workeru jen nutný kontext.
6. „Dokončeno“ znamená prokazatelně otestováno a přijato; vytvořený commit nebo Pull Request není akceptace.
7. Karel musí přiznat chybějící přístup, nečitelné soubory, konfliktní stavy, skutečné limity a neúspěšné běhy. Nikdy nehlásí neprovedenou práci jako hotovou.

## Uživatel a UX
- Hlavní uživatel je vlastník projektu s obchodní vizí, bez nutnosti znalosti programování. Karel komunikuje česky a srozumitelně.
- Jedno hlavní chatové rozhraní pro rozbor, návrhy a schválení; vedle něj přehled projektu, fronty, blokací, testů a nákladů. Nepřidávat pro každé pravidlo nové tlačítko.
- Responzivní mobil/desktop, jednotné prvky z knihovny, styl Poppins podle již přijatých UX pravidel.
- U každého tvrzení o stavu zobrazit zdroj, čas poslední synchronizace a odkaz do GitHubu; rozlišovat „návrh“, „čeká na test“, „ověřeno“, „nevíme“.

## Hlavní schopnosti (požadavky)
**R1. Převzetí existujícího projektu:** navázání repozitáře, zjištění default branche a přístupových práv; čtení README, dokumentace, manifestu, struktury kódu, otevřených i uzavřených Issues, PR, projektových položek/fieldů, commitů a dostupných CI běhů. Žádné vytváření duplicit při opakovaném importu. Je-li GitHub Projects API nedostupné, přiznat omezení a nezaměňovat za Issues.

**R2. Projektová mapa a dokumentace:** z existujících autoritativních zdrojů a rozhovoru vytvořit strukturovaný stručný popis obchodního cíle, uživatelů, rozsahu, architektury, integrací, omezení, rozhodnutí, testování a plánovaného vývoje. Udržovat změnovou historii a odkazy na zdroje; nikdy nekopírovat celé původní zadání do jediného pole.

**R3. Projektový dialog:** rozlišovat potvrzené skutečnosti, pracovní hypotézy a otevřené otázky. Nejdřív analyzovat, potom navrhnout změny; u komplexního zadání neprovádět předčasný zápis. Předložit přiměřeně stručný návrh k jednomu schválení.

**R4. Knihovna:** použít verzované standardy, schválené komponenty, UX, API kontrakty, bezpečnostní a vývojové postupy napříč projekty. Načítat jen relevantní položky. Povýšení nové komponenty do sdílené knihovny podmínit testem a schválením.

**R5. Sedm etap:** zachovat současné názvy z app/services/workflow.py: Zadání → Analýza → Architektura a UX → Plánování → Vývoj → Závěrečné ověření → Nasazení a uzavření. Etapy jsou **řídicí proces**, ne seznam tlačítek. Úkoly, závislosti, termíny, odpovědnosti a akceptační kritéria se promítají do GitHub Issues a GitHub Projects; průběžné testy běží během vývoje.

**R6. Backlog a harmonogram:** navrhovat priority a realistické termíny, přebírat existující Issues a jejich stavy, navrhovat přesuny v GitHub Projects. Blokovaný úkol nespouštět; po změně předchůdce přepočítat plán. Odhad není slib.

**R7. Fronta a dávkování:** řídit vykonávací joby po malých dávkách. Pro každou dávku uložit identitu issue, branch, commit SHA, vstupní snapshot, související soubory, testy, cenu/spotřebu, počty pokusů, timeout, chybu, stav, návaznosti a bezpečný bod pokračování. Při překročení limitů pauza, nikoli nekonečný retry.

**R8. Exekutor:** Codex nebo Fresh AI Engine dostanou smluvně definovaný pracovní balíček; Karel realizaci sleduje, ale netvrdí, že sám píše kód. Vytvořený PR se propojí s Issue a během fronty; uchovává se diff, výsledky testů a odkazy.

**R9. Testování:** automatické testy jsou podmínkou předání uživateli, ale **reálné uživatelské testování** je zdrojem akceptace. Karel zaznamená testovací scénář, prostředí, očekávání, skutečný výsledek, chybu a výsledek; z neúspěchu vytvoří opravný úkol a vrátí ho do fronty. Stav Issue/Project se změní až po schválení a úspěšném zápisu do GitHubu.

**R10. Přehled:** jedna obrazovka musí říci: co běží, co čeká, proč je úkol blokován, co je připravené k testu, poslední úspěšná synchronizace, kolik bylo pokusů, orientační ETA pouze s podklady, skutečné/odhadované náklady a další doporučený krok.

## Kritéria úspěchu pilotu
- Existující repozitář s Issues lze převzít opakovaně bez duplicit a bez nechtěných zápisů.
- Karel z něj připraví přezkoumatelný stručný plán a navrhne rozdílové změny.
- Uživatel schválí jeden konkrétní Issue; vytvoří se nejvýše jeden navázaný job s omezeným kontextem.
- Po přerušení job bezpečně naváže bez opětovného čtení celého repozitáře.
- Výsledek má PR, testovací výstup a srozumitelnou historii; neúspěšný test vrací úkol do opravy.
- GitHub a UI po synchronizaci zobrazují stejný dohledatelný stav, případné konflikty se označí.
- U běhu je dohledatelná spotřeba, počet pokusů a důvod případného zastavení.

## Co není součástí prvního MVP
Plně autonomní vývoj bez kontroly, automatický merge/release, obecná náhrada GitHub Projects, vlastní kompletní IDE, nový velký design systém ani pokus nahradit Codex. Zvyšování složitosti jen tehdy, když prokazatelně snižuje náklady nebo čas.

## Stav podle repo při revizi
Doloženo v kódu/dokumentech: projektový chat, schvalované zápisy, projektová mapa, lokální úkoly, knihovna, sedm etap, čtení vybraných příloh a základní výběr kontextu (alpha.27–29). **Částečně doloženo po 20. 11. 2026:** GitHub read-only konektor s omezeným snapshotem, čtením vybraných dokumentů a nově i po dávkách načítaného kódu, porovnávání větví a testů; chatový návrh oddělených polí zadání s čekající akcí pro schválení. **Nedoloženo jako hotové:** úplný automatický audit každého souboru, obousměrná synchronizace Projects/Issues/PR, GitHub write/merge, Codex executor, staging/produkční deploy, skutečné akceptační testy a řízená fronta. Produkční provoz nové verze vyžaduje samostatné ověření.
