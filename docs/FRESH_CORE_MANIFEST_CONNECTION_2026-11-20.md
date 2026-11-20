# Fresh Core v Karlovi – připojení přes manifest a Write Key (20. 11. 2026)

Tato implementace reaguje na provozní připomínku u projektu „Web – Adrenaline Race“.
**Verze zdrojového kódu: 2.0.0-alpha.35-fresh-core-manifest-link.**
Vývoj probíhá přímo v `main`. Nasazení na Exon není tímto dokumentem potvrzeno.

## Jak připojit již existující Fresh Core
1. V Karlovi otevřít WordPress projekt → **Můj WordPress** → **Čtení z WordPressu**.
2. Vložit skutečnou kompletní **Connector Manifest URL** ze sekce statického konektoru Fresh Core (stejný typ zdroje jako v Bobanovi) a stisknout **Připojit a ověřit manifest**.
3. Karel HTTPS manifest skutečně stáhne, ověří identitu WP webu, strukturu exportu a kontrolní součty vybraných souborů; pak uloží ověřený souhrn i URL webu. Předem není nutné samostatně ukládat adresu.
4. Karel **neukazuje token manifestu v UI ani chatu**. URL je v projektovém úložišti šifrovaná.
5. Pro budoucí zapisování lze ve druhém odděleném formuláři vložit **Write Key** z Fresh Core. Karel jej ověří pouze pomocí `GET /wp-json/fresh-core/v1/write/ping`, zašifruje a označí stav oprávnění. **Neprovede žádný POST, nenasadí změnu ani nepublikuje obsah**.
6. Opakované načtení manifestu porovná ověřené inventurní údaje s předchozím snímkem. Nezmění WordPress ani připojení ostatních aplikací Boban, Linda, Viki, Eda.

Alternativní původní cesta s `X-Fresh-Core-Key` pro READ REST zůstává zachována v rozbalovací části.

## Trezor klíčů
- Je-li na serveru nastaveno `FRESH_CORE_VAULT_KEY`, má přednost. **Nikdy jej při upgradu nepřepisovat**.
- Pokud klíč není nastaven, při prvním pokusu o propojení si Karel na single-tenant hostingu připraví stabilní Fernet key file v
  `~/.freshcrackers-karel-private/fresh-core-vault.key` (adresář `0700`, soubor `0600`).
- Tento soubor je **mimo aplikaci a veřejný DocumentRoot**, má být v záloze spolu s DB. Při jiném layoutu hostingu ověřit, že je skutečně mimo veřejné URL. Pokud není možné bezpečné vytvoření, připojení selže a admin musí použít serverovou .env.
- Globální `FRESH_CORE_ALLOWED_HOSTS` je **volitelný přísnější seznam**. V základní verzi je síťový cíl vázán na host z ručně předané úplné URL manifestu a následně na ověřenou identitu WordPressu. HTTPS, kontrola veřejné DNS a zákaz přesměrování jsou povinné; u multi-tenant produkce je navíc doporučeno egress omezení a ochrana proti DNS rebinding.
- Manifest token a Write Key **nevkládat do chatu, screenshotů, GitHub Issues ani logů**. Starší hodnoty, které byly zobrazené na screenshotu, je vhodné obnovit ve WordPressu a v navázaných aplikacích.

## Co skutečně čteme
- `manifest.json`: číslo verze, datum posledního exportu, soupis a kontrolní součty, stav batch a identita webu.
- `structure.json`: WP verze, aktivní pluginy, téma, struktura post types, taxonomie, menu.
- `elementor.json` a `fresh-modules.json`: stručné inventurní údaje, pokud jsou dostupné do limitu 2 MB.
- `diagnostics.json`: pouze agregované strukturální diagnostiky taxonomií (např. prázdné kategorie), nikoliv komplexní PHP/JS chyby.
- Jen pro tyto načtené soubory kontrolujeme velikost a SHA-256; **nepředstíráme čtení všech tisíců položek nebo ověření veškerého obsahu**. Ostatní vybrané SHA ze seznamu mohou být porovnávány jako známka změny bez načtení samotného obsahu.
- Statické exporty mohou být starší, zvlášť pokud je na WordPressu vypnuta automatická úplná aktualizace. Karel označí manifest starší než 48 hodin jako **zastaralý**, nikoli „aktuálně vše v pořádku“.
- Chybný checksum, přesměrování, nedokončená dávka, cizí host či neplatná struktura způsobí bezpečné odmítnutí; poslední ověřený stav se nemaže.

## Přejímací ověření po nasazení na Exon
1. Záloha DB, souborů, .env a trvalého vault klíče (pokud již existuje); žádná automatická DB migrace.
2. Nasadit kompletní HEAD z GitHub `main`, nainstalovat requirements do správného Passenger virtualenv a restartovat Passenger.
3. Ověřit `GET /healthz`, přihlášení, projektovou kartu a verzi v `/manifest.json` v administrátorské relaci.
4. Připojit Adrenaline Race pouze přes jeho **novou/aktuální soukromou manifest URL**, bez vkládání klíčů do chatu. Ověřit výpis skutečného WordPress názvu, verze a pluginů.
5. Volitelně ověřit Write Key – jen GET/ping, žádný zápis. Poté provést řízenou změnu na staging WordPressu, obnovit manifest a zkontrolovat diff.
6. Pokud se stále „neukládá web“, ověřit ze serverového logu odpověď **POST /projects/7/website-url**: HTTP 403 značí např. nesoulad `APP_URL` a skutečného Origin, HTTP 400 chybu autorizace/validace, 303 následné přesměrování; konkrétní příčinu bez logu netvrdit.

**Status kódu:** návrh připravený pro CI; neprokázáno funkční produkční propojení konkrétního WordPressu.