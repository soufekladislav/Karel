# Karel – uživatelská revize produktu a UX z ostrého provozu
19. 11. 2026 · podklad pro průběžnou akceptaci · draft PR #14

## Cíl produktu
Karel není katalog nastavení, formulářová aplikace ani náhrada GitHubu.
Pro uživatele má být jediným průvodcem od otázky „Co potřebuji na svém webu
nebo projektu vyřešit?“ po **ověřený výsledek**.

> Zadání → zjištění skutečného stavu → návrh práce → souhlas uživatele →
> provedení → kontrola → historie.

Tento sled je obchodní slib. Každý krok, který zatím nemá technickou
implementaci, musí být viditelně označen jako dostupný teprve po propojení
nebo plánovaný. Karel nesmí tvrdit, že sám upravil WordPress, provedl deploy,
zapsal GitHub Issue nebo spustil Codex, pokud to nebylo ověřeno.

## Hodnocení dodaných screenshotů

| Povrch | Zjištění | Výsledek první reakce |
|---|---|---|
| Prázdný Chat u Lindy | Velká prázdná plocha, žádný úkol ani vodítko | Konkrétní první volby: WordPress / vývoj / udělat pořádek; zvolení pouze předvyplní prompt |
| Zadání a dokumentace | Otevřený dlouhý formulář připomíná administraci | První volba „Připravit zadání s Karlem“; ruční formulář zůstává, ale je složený |
| GitHub projektu | Konfigurace není nastavená; chybí import a manuální mapování | Link „Importovat projekty z GitHubu“, nové uživatelské mapování + přesun mimo admin |
| Pipeline projektu | U projektu bez dat příliš mnoho velkých nul a sedm etap | Prázdný projekt nabízí rozhovor a teprve po přidání dat ukazuje KPI; workflow zůstává |
| Knihovna | 0 položek, bez vysvětlení hodnoty | Onboarding hodnoty a prvního souboru/standardu, pravdivé upozornění na chybějící verzování |
| Nastavení | Fresh Key automaticky rozbalí výpis všech projektů | Technický seznam na vyžádání, ne v první obrazovce |
| Účet | Karta profilu navíc k nastavení; dvě místa se stejnou funkcí | Pro další iteraci sjednotit účet pod nastavením |
| Moje projekty | 12 projektů, 20 otevřených úkolů, z toho 9 čeká a 1 selhal; opakované GH „Vyžaduje nastavení“ u každého | Úkoly vyžadující zásah řadit na začátek; GH konfiguraci sdělit pouze jednou |
| Superadmin | GitHub import zabírá výsostné místo v konzoli podpory | Import přemístěn do běžného GitHub pracovního toku, superadmin nechává provoz/správu uživatelů |

Čísla výše jsou **stav na poskytnutých screenshotech**, nikoliv nezávislý
audit DB. Nezaměňovat je s 18. 11. manifestem, kdy bylo v aplikaci
8 projektů / 74 úkolů.

## Co Karel umí a co ještě není produkční služba

**V současném aplikačním kódu:** projektové chaty, uložení strukturované
projektové mapy, návrhy schvalovaných akcí, úkoly, historie, přílohy, čtení
manifestů, jednoduchá knihovna, read-only GitHub snapshot po konfiguraci,
předběžné hromadné zakládání/propojování projektů. Při hodnocení „hotovo“
vždy rozlišovat kód od skutečně ověřené konverzace a zápisu v provozu.

**Ještě nehotové:** přímá editace WordPress přes Fresh Core, GitHub zápisy
do Issues/Projects, autonomní Codex coding workflow, automatické plné
repo->issue->PR->CI->Karel naskladnění všech dat, průběžná delta synchronizace,
verzovaná schválená knihovna a ověřený deployment worker.

## První UX iterace (provedena v kódu této větve)

1. GitHub portfolio import přemístěn z `/admin/github-import` do
   `/github/import`, vstup z GitHub karty projektu i z portfolia; stará URL
   zůstává kvůli kompatibilitě. **Dočasně pouze superadmin**: aplikace má
   serverový token, nemá bezpečnou per-user autorizaci GitHubu.
2. Import nadále záměrně nezaškrtává všechny repozitáře a vyžaduje potvrzení;
   dovoluje ručně mapovat rozdílná jména jako `Karel` → `Developer Karel`,
   ale jen na dosud nepropojené projekty **vlastněné přihlášeným uživatelem**.
   Nedovoluje obsadit projekt dvakrát nebo použít cizí projekt.
3. Projektová karta s chybami nebo čekajícími schváleními je prioritní.
   Když není GitHub vůbec nakonfigurován, nepropagujeme stejný varovný badge
   12× na nástěnce.
4. Nový projekt po vytvoření nabídne chat s předvyplněným návrhem na rozhovor.
   Když nejsou žádná smysluplná data, přehled neukazuje obrovské nuly, ale
   konkrétní bezpečný první krok. Původní šablona workflow se nemaže.
5. Zadání ručním formulářem zůstává; primární CTA rozpracuje cíl chatem.
   Prázdný chat navrhne situace WordPress, vývoj aplikace, nepořádek v projektu.
   Žádné předvyplnění samo nic neodesílá a nemění DB.
6. Knihovna vysvětlí hodnotu prvního standardu a rozdíl mezi uloženým souborem
   a budoucím verzovaným katalogem. Fresh Key v nastavení je standardně složený.

## Další fáze – skutečná práce namísto dalších karet

### A. Projektový asistent pro vlastníka WordPressu
- Začít otázkou na URL webu / cíl / současnou potíž.
- Karel nabídne připojení Fresh Core v režimu čtení s viditelným stavem.
- Po **reálném ověření** načte aktuální stránky, pluginy, chyby a aktualizace.
- Navrhne konkrétní drobnou změnu a vyžádá souhlas.
- Teprve po existenci bezpečného write API zapíše změnu a znovu ověří výsledek.

### B. Vývojářský projekt na GitHubu
- Připojit GitHub každému uživateli přes vlastní OAuth/GitHub App grant
  (nikoli vydat společný PAT do klientského UI).
- Vybrat repozitáře; rozhodnout mapování; založit/propojit projekt bez duplicit.
- Automaticky a bezpečně načíst Issues, PR, CI a příslušné Projects v2 včetně
  stránkování a aktualizací.
- Chat nad aktuálními daty připraví návrh; uživatel schválí; kontrolované
  GitHub zápisy a Codex tvoří **další samostatné akceptační fáze**.

### C. Jediný pracovní přehled
- Cíl (stručně), stav a nejbližší krok.
- Co čeká na uživatele a proč.
- Odkud máme ověřená data a kdy se naposledy synchronizovala.
- Otevřený chat jako vstup a schválení změn jako výslovný bezpečnostní bod.
- Technické údaje (tokeny, manifest, staré ZIPy, worker) ve druhém plánu.

## Akceptační kritéria
- Nový uživatel u prázdného projektu může do jednoho kliknutí začít smysluplný
  rozhovor; není tlačen k dlouhému formuláři.
- Import `Karel` lze namapovat na existující `Developer Karel` bez přepsání
  zadání a bez vytvoření duplicitního projektu.
- Bez `GITHUB_ALLOWED_OWNERS` se import nezačne tvářit jako připojený; bez
  prvního GitHub snapshotu se nezobrazují smyšlené počty Issues/PR.
- Při konfliktu mapování nebo výběru cizího projektu nedojde k žádnému zápisu.
- Dvě stejné URL/duplicity repozitáře zůstávají bezpečné po opakovaném importu.
- UX je čitelné na desktopu i mobilu; uživatelské testování nesmí být nahrazeno CI.
- Stávající projekty, přílohy, Tasks, chaty a schvalování jsou nedotčené.
- PR zůstává draft, produkční nasazení je výslovná následná akce.

**Pozor:** GitHub portfolio import dnes nezajišťuje automatické načtení všech
Issues a PR po vytvoření projektu. To je samostatný P1 worker/sync krok
v návaznosti na Issues #6–#8.
