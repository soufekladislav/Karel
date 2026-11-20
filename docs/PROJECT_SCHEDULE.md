# Karel – projektový plán a harmonogram (návrh k odsouhlasení)

> **Baseline v0.1 · 20. 11. 2026 · stav: NAVRŽENO, nikoli schváleno ani zapsáno do produkční databáze Karla.**
> Autoritativní zdroje: schválené zadání v Karlovi (uživatelem potvrzena funkce uložení; konkrétní obsah této DB zde nevidíme), aktuální `main` GitHubu, Issues #1, #4, #5, #9, #10, #20 a sedm etap v `app/services/workflow.py`.

## Rozhodnutí o struktuře

**Sedm etap** je vrstva *řízení projektu* a přejímacích bran: Zadání → Analýza → Architektura a UX → Plánování → Vývoj → Závěrečné ověření → Nasazení a uzavření.
**Milníky M0–M6** jsou vrstva *funkčních výsledků a termínů*, často více milníků uvnitř jedné etapy Vývoj. **Issues** jsou jednotlivé práce, které vedou k milníku. Není potřeba sedm nových pipeline pro každé Issue.

Jednotlivé milníky musejí být průběžně testovány; etapa 6 je celková integrační a uživatelská akceptace. Technicky hotové ≠ uživatelsky schválené ≠ nasazené.

## Předpoklady výchozího harmonogramu

- Začátek navazujících prací: **pondělí 23. 11. 2026** (dnes 20. 11. 2026).
- **Jeden hlavní vývojový proud**, kratší dílčí úkoly, realizace po schválení; aktuální dostupná kapacita vývojáře ani rychlost Codex executoru nejsou nezávisle ověřené. Data jsou **cílové termíny**, nikoli závazný příslib.
- Pro každou přejímku předpoklad: uživatelská reakce do **jednoho pracovního dne**; pokud není možná, harmonogram se musí přepočítat.
- **21.–23. 12. 2026** rezerva na regresní testy a opravy před svátky. **24. 12. 2026–3. 1. 2027** neplánujeme běžný vývoj ani produkční releasy (plánovací přestávka, může se změnit po schválení).
- Zásahy do produkční Exon/MariaDB až po záloze a samostatném souhlasu. Kód v `main` a zelené CI nejsou samy o sobě dokladem nasazení.
- Pokud se objeví blokace bezpečnosti, chybějící GitHub práva nebo nefunkční API, navazující termíny jsou předběžné.

## 7 etap projektu – nadřazená časová osa

| Etapa | Předpokládané období | Výstup / podmínka převzetí | Stav k 20. 11. |
| --- | --- | --- | --- |
| 1. Zadání | do **23. 11. 2026** | Ověřit a obsahově schválit již uložené zadání; neplést technicky fungující ukládání se schválením etapy | Ukládání potvrzeno uživatelem, stav etapy v DB **neověřen** |
| 2. Analýza | **23.–25. 11. 2026** | Reálný audit GitHubu, Exonu a bezpečnosti; zdroje, rizika a blokace | Navrženo |
| 3. Architektura a UX | **26.–27. 11. 2026** | Datový kontrakt plán / milník / Issue / datum a jednoduché UX schválení; bez duplicity druhé pravdy | Navrženo |
| 4. Plánování | **30. 11. 2026** | Schválená verze harmonogramu, konkrétní termíny, kapacita, závislosti a přejímky | **Tento dokument je návrh** |
| 5. Vývoj | **1. 12. 2026–15. 1. 2027**, s plánovací přestávkou | Dílčí výsledky M1–M4, každý s testem a doloženým stavem | Navrženo |
| 6. Závěrečné ověření | **18.–22. 1. 2027** | Integrační a uživatelské testy celého vývojového cyklu, zápis skutečných výsledků | Navrženo |
| 7. Nasazení a uzavření | **25.–29. 1. 2027** | Schválený, zálohovaný produkční pilot s kontrolou funkčnosti a rollbackem | Navrženo |

## Konkrétní milníky a termíny

| ID | Od | Do / akceptace | Hmatatelný výsledek | Závisí na | GitHub |
| --- | --- | --- | --- | --- | --- |
| **M0 – Audit a bezpečný základ** | 23. 11. | **25. 11. 2026** | Ověřená skutečná verze Exonu, bezpečnost veřejné historie/storage, zdrojový SHA, seznam blokací | Bez dalšího | [#4](https://github.com/soufekladislav/Karel/issues/4), [#5](https://github.com/soufekladislav/Karel/issues/5) |
| **M1 – Časová osa přímo v Karlovi** | 26. 11. | **4. 12. 2026** | Karel sestaví z uloženého zadání *reálné termínované milníky*, propojí je se 7 etapami, ukáže závislosti, nabídne změny a po schválení prokazatelně uloží verzi plánu; uživatelský test | M0 a schválená architektura | [#1](https://github.com/soufekladislav/Karel/issues/1), [#17](https://github.com/soufekladislav/Karel/issues/17) |
| **M2 – Spolehlivé převzetí GitHubu** | 7. 12. | **11. 12. 2026** | Úplnost/partial state Issues, PR, větví, relevantního kódu a CI; mapování zadání na existující Issues; ověření i na repozitáři bez Issues | M0, M1 | [#20](https://github.com/soufekladislav/Karel/issues/20), [#6](https://github.com/soufekladislav/Karel/issues/6), [#7](https://github.com/soufekladislav/Karel/issues/7), [#8](https://github.com/soufekladislav/Karel/issues/8) |
| **M3 – GitHub manažer** | 14. 12. | **18. 12. 2026** | Schválené vytvoření/úprava/uzavření pilotního Issue; kontrola konfliktů a skutečného zápisu; žádný merge bez CI a souhlasu | M2 a oprávnění GitHubu | [#9](https://github.com/soufekladislav/Karel/issues/9), [#17](https://github.com/soufekladislav/Karel/issues/17) |
| **Rezerva / prosincová přejímka** | 21. 12. | **23. 12. 2026** | Opravy z uživatelských testů M1–M3, zamrazení stabilního základu; žádný předčasný release | M3 | [#4](https://github.com/soufekladislav/Karel/issues/4) |
| **M4 – AI Engine → Codex – jeden reálný úkol** | 4. 1. 2027 | **15. 1. 2027** | Schválené Issue → Engine job ID → izolované programování → commit/PR → CI → ověřený výsledek a náklady. Po selhání STOP, ne falešné hotovo | M3; skutečná dostupnost executoru v AI Engine | [#10](https://github.com/soufekladislav/Karel/issues/10) |
| **M5 – Tester, testovací nasazení** | 18. 1. | **22. 1. 2027** | Oddělené staging, kontrolované nasazení, testovací protokol a rozhodnutí uživatele; záměrně chybný scénář musí zablokovat release | M4 | [#10](https://github.com/soufekladislav/Karel/issues/10), [#4](https://github.com/soufekladislav/Karel/issues/4) |
| **M6 – Produkční pilot Karla** | 25. 1. | **29. 1. 2027** | Samostatné schválení, záloha, řízený Exon deploy, health, verze a rollback ověřené; bez přímého zásahu do cizích projektů | Úspěšně přijaté M5 | [#4](https://github.com/soufekladislav/Karel/issues/4) |

**Kontrolní obchodní body:** 4. 12. první verze časového plánování; 18. 12. první použitelná schvalovaná správa Issues; 15. 1. jeden kódový úkol end-to-end; 29. 1. schválený pilot produkčního nasazení. Pokud kapacita nebo dostupnost API nedovolí termíny, Karel musí transparentně předložit nový výpočet.

## Jak musí Karel dotáhnout uživatele k hotovému plánu (M1)

1. **Načti podklady:** schválenou Projektovou mapu, datumy v sedmi `ProjectStage`, existující Issues/Projects, poslední ověřený GitHub SHA a již potvrzené milníky. Nejprve si ověř, že nehrozí duplicitní plán.
2. **Navrhni reálné termíny sám:** podle dnešního data v lokálním kalendáři projektu, pracovní kapacity, odhadů, pořadí a závislostí. Pokud chybí kapacita, označ výchozí předpoklad *jeden vývojový proud / pracovní dny* a nabídni ho ke schválení; nepotřebuješ po uživateli vyplnit deset polí.
3. **Zeptej se nejvýše na jednu zásadní otázku:** pokud dosud neznáš ani cílový termín, ani přijatelnou kapacitu, ptej se prioritně na pevný termín uvedení. Současně nabídni provizorní plán vypočítaný dopředu bez čekání na formulář.
4. **Ukaž přehled:** milník, datum zahájení a konce (ISO `YYYY-MM-DD` + český formát pro člověka), trvání v pracovních dnech, závislosti, rezerva, stav, odpovědnost (Karel/Engine/uživatel) a očekávaný test. Uživateli se nejdřív ukáže jednoduchá časová osa, detail na vyžádání.
5. **Schvalování:** jediný srozumitelný krok „Schválit plán“. Karel uloží **verzi plánu** s předchozí verzí, konkrétními `start_date` / `due_date`, závislostmi a identitami zdrojů; pak ověří čtením z databáze. Externí GitHub write až po samostatně autorizovaném kroku.
6. **Aktualizace:** po zdržení přepočti navazující termíny a kritickou cestu; ukaž rozdíl proti původnímu baseline. Nikdy potichu nepřepisuj schválené datum ani automaticky neoznačuj úlohu jako hotovou. Pokud test selže, navazující release je blokovaný.
7. **Kontrola:** krátké upozornění při blížícím se/propadlém termínu a jeden doporučený další krok. Bez skutečně běžícího workeru neslibuj upozornění mimo aplikaci.

## Datové hranice – netvořit dva konkurenční harmonogramy

- `ProjectStage` (existuje): 7 hlavních fází, start/end/status/acceptance.
- `project_plan` v `ProjectMemory` (existuje): lidský schválený souhrn, **nikoli** strojově spolehlivý kalendář.
- Nový plán milníků (M1): verze + cílové datumy + závislosti + vazby na GitHub Issues a projektové etapy. Ukládání/migrace musí projít návrhem a testem; nesimulovat datumy pouze textem.
- GitHub je autoritou pro zdrojový kód, Issues a PR. Dokud nejsou GitHub write oprávnění ověřená, datumy jsou lokální plán v Karlovi, nikoli tvrzení o aktualizovaném GitHubu.
- První produkční pilot může mít plán lokálně; po spuštění schvalovaných GitHub zápisů navázat na GitHub Milestones / Projects v2 (date fields) bez duplikací a s kontrolou konfliktu.

## M1 – minimální skutečná implementace a testy

- Z existujícího zadání a uživatelské historie vytvořit více konkrétních milníků. Každý má `id`, název, `project_stage_no`, `start_date`, `due_date`, `estimated_workdays`, `dependencies`, `acceptance`, `status`, `source_issue_ids`, `baseline_version`.
- Výpočty se provádějí deterministicky na backendu; AI Engine pouze navrhne obsah, pořadí a odhady. Systém kontroluje, že `start_date <= due_date`, žádná kruhová závislost, konec následujícího milníku respektuje předchozí.
- Podpora českých pracovních dnů, víkendů, kalendářních výjimek a schválených přestávek; rozlišit termínový *odhad* od závazného termínu.
- Přejímací testy: rozpoznání již schváleného zadání bez nové duplicity; generování skutečných dat; změna termínu nadřazeného milníku a správný návrh posunu závislých; odmítnutí neplatného data; chyba API; opakované potvrzení; záloha/historie; test uživatele na Exonu.
- **Definition of Done:** majitel řekne „Karle, naplánuj mi tento projekt“; vidí časovou osu a konkrétní datumy, řekne „Posuň testování o tři pracovní dny“, dostane správně přepočtený návrh, schválí jednou a po obnově stránky i novém chatu vidí stejnou schválenou časovou osu.

## Otevřená schvalovací otázka

**Potvrzuješ tento orientační harmonogram s cílem pilotního produkčního provozu 29. 1. 2027, nebo máš pevný dřívější termín?** Toto datum je jediný zásadní plánovací předpoklad, který nyní potřebuje obchodní potvrzení. Harmonogram se jinak může použít jako pracovní návrh.

---

**Realizační režim:** úkol → analýza → schválený rozsah → implementace → automatický test → uživatelský test → nasazení. Před přejímkou nic neoznačovat za provozně hotové.