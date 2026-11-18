# Karel – srovnávací matrice aplikace (obchodní pohled × skutečná funkčnost)

Datum: 18. 11. 2026. Stav: **připraveno ke staging/produkčnímu porovnání,
nikoli otestovaný produkční výsledek**. Zdroj změn: `develop/karel-platform`.

## Jak hodnotit
Každý řádek uzavřít jedním z:
- `NEOVĚŘENO` – nemáme důkaz;
- `V KÓDU / CI` – automatické testy, ale ne běžící aplikace;
- `STAGING OK` – prošlo přihlášeným testem proti staging DB;
- `PRODUKCE OK` – prošlo bezpečnou produkční kontrolou.

Nenahradit živý test tvrzením „v aplikaci to vidím“. Karel musí umět věc
**provést, potvrdit, zaznamenat a znovu načíst**.

## Srovnávací tabulka

| Pohled | Zamýšlený výsledek pro uživatele | Co je ve vývojové větvi | Co reálně otestovat |
|---|---|---|---|
| 1. Chat | Karel rozumí projektu, naváže na kontext, navrhne změnu a vyžádá schválení | Projektový chat, historie, schvalování, panel na dalších obrazovkách | 3 navazující dotazy; reálný zápis do projektu; příloha ZIP; korektní chybový stav AI; mobil |
| 2. Zadání a obchodní cíle | Jeden srozumitelný plán bez duplicit, obchodní cíl + rozsah + schválené rozhodnutí | Formuláře a projektová paměť, oddělená obrazovka | Uložení zadání v chatu vs UI; změna jedné části; historie, kontrola přístupů |
| 3. GitHub | Vidět repozitář, Issues, PR, Projects v2, CI a synchronizaci bez přepisu dat | Read-only snapshot, stav chyb, čas synchronizace; admin portfolio import s náhledem | Skutečný token a API; přesné počty; opakovaný import bez duplicit; pagination; neslučovat Projects v2 s CI |
| 4. Pipeline | Sedm řídicích kroků a skutečné úkoly/CI/akceptace na jednom místě | Seskupené pohledy Úkoly, Testování, Výstupy, Historie a etapové workflow | Přechod stavu, schválení, vazba na GitHub Issue/PR, odpovědnost; žádná falešná hotovost |
| 5. Knihovny | Schválené UX/technické komponenty se sdílejí napříč projekty | Dosavadní knihovna účtu, verze a schvalování reuse zatím neúplné | Uložit/načíst komponentu, přístupová práva, znovupoužití mezi dvěma projekty, verze |
| 6. Nastavení a účet | Přehled všech integrací, stavu provozu, připojených účtů a oprávnění | Nastavení účtu, Fresh Key, admin self-check, GitHub konfigurace v env | Stav Fresh Key/Fresh Core/AI Engine/GitHub, poslední úspěch/chyba, roles, superadmin, mobil |

## Prioritní end-to-end scénář (povinná akceptace)
1. Přihlásit se jako schválený uživatel a vybrat správný projekt.
2. Načíst reálné GitHub repo, Issues, PR a Projects v2; zobrazit přesný čas
   synchronizace a stav úplnosti. Pokud právo chybí, UI musí ukázat „nedostupné“.
3. V chatu zadat obchodní cíl, dostat přiměřený návrh na úkol bez programátorské řeči.
4. Po schválení vznikne jedno konkrétní Issue ve správném repozitáři – až po
   implementaci schvalovaných GitHub zápisů. Do té doby úkol **neoznačovat za hotový**.
5. Codex dostane pouze schválený scope. První verze workflow zatím provádí
   jen read-only analýzu; následná verze musí umět malý PR a ověřené CI.
6. Karel načte skutečné výsledky PR/CI, zaznamená blokace a vyžádá lidskou akceptaci.
7. Na mobilu ověřit stejný tok – bez přeskakování schvalovacích kroků.

## Co zatím chybí a nesmí být vydáváno za hotové
- Reálná produkční Exon bezpečnostní akceptace a ověřené zálohy.
- Propojení všech deseti viditelných repo do skutečné databáze Karla.
- Plná synchronizace uživatelských a organizačních GitHub Projects v2,
  stránkování a delta-synchronizace.
- Řízené GitHub zápisy a skutečný vývojářský Codex worker s náklady a frontou.
- Verze knihovny, runtime kontrola Fresh Core a prokázané mobilní UX.

## Podklady k praktickému porovnání
Po staging nasazení uložit šest screenshotů desktopu a šest mobilu,
popis konkrétního nefunkčního chování a testovací výsledek každého bodu.
Screenshot bez ověření akce nestačí. Každý nalezený problém založit jako
jedno Issue s očekáváním, realitou, krokem reprodukce a prioritou P0–P3.

**Pravidlo:** uživatelská jednoduchost a prověřená funkčnost mají přednost
před efektním UI a rozšiřováním aplikace o další moduly.

## P0 UX – první implementační etapa, 18. 11. 2026

Realizováno v integrační větvi `develop/karel-platform` (draft PR #14):
- Portfolio (Nástěnka): obchodní cíl jako stručný **odvozený náhled**
  (originální data a znění specifikace se nemění); počet otevřených, čekajících
  a chybných úkolů; jeden další krok odvozený z dostupných údajů; filtrování.
- Přehled projektu: podrobné zadání je v Dokumentaci, karta ukazuje jen účel,
  stav úkolů, rozsah, stav GitHubu a další krok. Workflow zůstává dostupné.
- GitHub: přísně oddělené stavy vyžaduje nastavení, nepřipojeno, čeká,
  chyba synchronizace, synchronizováno. Počet Issues a PR se nevykresluje
  jako platný snímek, dokud není ověřené načtení.
- Mobil: jedna sdílená navigace projektových pohledů včetně GitHubu.
- Poppins a čitelnější typografie; změny pouze v šablonách/CSS a prezentačních
  funkcích, **bez DB migrací, přepsání zadání a přímých GitHub zápisů**.
- Regresní testy: helpers pro reálné next steps, různé GitHub stavy,
  render dashboardu s připojeným i prázdným portfoliem, render nepřipojeného
  a synchronizovaného GitHubu, kontrola mobilních tabů.

**Stav akceptace:** automatický test a běžící nasazení jsou dvě různé věci.
Ještě musí proběhnout vizuální a funkční test na skutečné verzi Exonu
(PC/mobil, načtení dat, scroll, klikání, obnovení stránky, role a chybové stavy).
Do té doby neoznačovat `PRODUKCE OK`.
