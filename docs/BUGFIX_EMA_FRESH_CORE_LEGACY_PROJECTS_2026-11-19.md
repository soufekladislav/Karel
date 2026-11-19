# P0 – Ema GitHub, Fresh Core a staré projekty (19. 11. 2026)

## Ověřená hlášení od uživatele

Uživatel v produkci `https://ai-coder.freshcrackers.cz` otevřel projekt **Ema** (ID 15), opakovaně synchronizoval `soufekladislav/Ema`, UI zobrazilo datum úspěšného načtení, ale stav **Snímek není ověřen** a žádná Issues/PR. Na WordPressu `adrenalinerace.eu` má Fresh Core aktivní REST konektor; Karel se přesto nepřipojil. Starší projekt **Web Fresh Develop** nejde editovat.

Protokol v přiloženém `manifest(7).json` uvádí build **2.0.0-alpha.31-readonly**, 14 aktivních projektů, událost `github_readonly_sync` Ema 19. 11. 2026 ve 20:05:53 UTC a `fresh_core_readonly_manual_sync: requires_configuration`. U projektu Boban (ID 19) se zapisuje `source_load_error` pro obecné načítání `github.com` kvůli `SOURCE_ALLOWED_HOSTS`. Žádná z těchto událostí sama o sobě neprokazuje funkční propojení WordPressu.

## 1. Prokázaná příčina Ema

GitHub repo `soufekladislav/Ema` má při kontrole **67 samostatných Issues a 19 PR**. Bounded snapshot aktuálního GitHubReaderu má na základě načtených skutečných API dat asi **125 528 UTF-8 bajtů** (bez dalšího GraphQL board payloadu). Sloupec `github_repo_links.snapshot_json` je v SQLAlchemy typu `Text`, pro existující MySQL/MariaDB odpovídá maximálně přibližně **65 535 bajtům**. V závislosti na SQL režimu může zápis selhat nebo se text tiše zkrátit. Karel měl `last_synced_at`, ale následný JSON nelze přečíst, což odpovídá hlášení `Snímek není ověřen`.

**Oprava bez migrace DB:** `github_snapshot_codec.py`, `encode_snapshot` a `decode_snapshot`, ztrátově neutrální zlib/base64 obálka pro velké snímky, SHA-256 kontrola integrity, maximálně 55 000 bajtů ve sloupci, 2 MB limit rozbalených dat; starší malé JSON záznamy zůstávají kompatibilní. Nepřepsat starý záznam, pokud nový nelze plně bezpečně uložit. UI odlišuje neplatnou cache od nikdy nenačteného repozitáře. Chat, přehled i GitHub karta používají stejný decoder.

**Akceptace po nasazení nové verze:** v projektu Ema → GitHub stisknout **Načíst aktuální stav**. Není třeba odpojovat repozitář ani zakládat nový projekt. Očekávané Issues a PR: aktuálně cca 67/19; čísla se mohou změnit, skutečné počty jsou z okamžiku synchronizace. Ověřit originální odkazy, datum a opakovaný reload. Ověřit na další repo, které má >64 kB dat.

## 2. Fresh Core: plugin už běží, chybí server Karla

Ověřeno z aktuálního zdrojového kódu `soufekladislav/WP-Fresh-Core`:
- `Fresh_Core_Auth::authorize()` kontroluje povolení REST konektoru a hlavičku `X-Fresh-Core-Key` (stará možnost `?fresh_core_key=...` není bezpečná kvůli logům);
- `GET /wp-json/fresh-core/v1/ping` vrací stav a verzi;
- `GET /wp-json/fresh-core/v1/snapshot` vrací `success/data` s `manifest.site`, `manifest.runtime`, `active_plugins`, `post_types`, `taxonomies`, `menus` a `elementor_overview`.
- Screenshot WordPressu ukazuje zapnutý „REST konektor“, takže **už instalovaný Fresh Core není nutné instalovat znovu**. Je třeba ověřit verzi konkrétní instalace a funkčnost REST header API.

**Povinné serverové hodnoty na Exonu (mimo GitHub a chat):**
```dotenv
# Jednou vygenerovaný a bezpečně mimo Exon zálohovaný Fernet klíč
FRESH_CORE_VAULT_KEY=<nový náhodný Fernet key>
# Explicitně povolené HTTPS domény (rozšiřovat podle jednotlivých zákazníků)
FRESH_CORE_ALLOWED_HOSTS=adrenalinerace.eu,www.adrenalinerace.eu
```
Vygenerovat na serveru v aplikací používaném Python venv: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. **Nezapisovat do Issue, chatu ani screenshotu**. První hodnota musí být trvalá a zálohovaná spolu s produkční DB. Aktualizovat závislosti v Passenger venv (`pip install -r requirements.txt`) a restartovat Passenger proces. Pro čtení použít **REST klíč**, nikoli Write Key, Accounting Key nebo URL manifestu. Karel odesílá čtecí klíč výhradně v HTTP hlavičce, ne v URL, REST čtecí snímek ukládá whitelistovaně a klíč šifrovaně.

**Bezpečnost incidentu ze screenshotu:** na snímku byly čitelné aktivní tajné klíče i URL s tokenem v query/cestě. Doporučeno je **bez odkladu obnovit REST, Write a Accounting klíče a obnovit i tajnou URL manifestu**, poté synchronně přenastavit všechny existující aplikace, které je využívají. Rotaci provádět v administraci WordPressu, ne sdílením nových hodnot v komunikaci. Nekopírovat žádný starý klíč do Karel projektu. Při znovuzapojení využít „Fresh Core už mám → Připojit“. Před testem zápisu ověřit pouze READ; současný Karel žádné WP writes nespouští.

**Co ještě není ověřeno:** produkční `.env`, cesta Python venv a restart Passenger, skutečný HTTP handshake s `adrenalinerace.eu`; bez přístupu na server nelze tvrdit připojení za dokončené.

## 3. Web Fresh Develop a staré projekty

Dvě funkce dříve rozhodovaly jinak: `is_superadmin(user)` pokládalo za superadmina roli *nebo nakonfigurovaný e-mail*, ale `project_role(user,project)` uznávalo **jen explicitní roli**. Projekty založené jiným účtem tak mohly zůstat nedostupné pro správce aplikace.

**Oprava:** stejné rozpoznání superadmina pro kontrolu práv, projektový switcher i přehled. Ostatním uživatelům se práva nerozšiřují. Samostatná „Správa projektu“ nyní dovolí také měnit **typ již existujícího projektu** WordPress / GitHub / obecný, bez mazání původního obsahu a GitHub vazby. U projektu `Web Fresh Develop` zvolit WordPress, pokud jde o WordPress web; pak se objeví karta **Můj WordPress**. Staré datum/projektová mapa se neztrácejí.

Pokud nelze editovat i po nasazení, ověřit konkrétní ID/vlastníka/role a databázové záznamy **pouze čtecí diagnostikou**. **Nesmazat ani automaticky nemigrovat** starý projekt bez zálohy.

## 4. GitHub URL v chatu – již připojené repo

Karel při vložení `https://github.com/soufekladislav/Boban` spouštěl obecný resolver, který oprávněně odmítal externí web při chybějícím `SOURCE_ALLOWED_HOSTS`. Ve vývojové větvi po opravě pozná GitHub URL patřící **k aktuálnímu projektu** a použije důvěryhodný *uložený* read-only snapshot. Nevydává jej za živý stav, neobchází globální URL bezpečnost a pro GitHub Issue link použije omezený uložený text konkrétního Issue. Pro jiný/nepřipojený repozitář vyžaduje jeho nejprve připojit a ověřit.

## 5. Bezpečné převzetí na Exonu

1. Zálohuj produkční MariaDB, soubory, stabilní klíče. Neprovádět reset DB ani mazání.
2. Nasaď **celý** nový commit z `develop/karel-platform`, ne jednotlivé šablony; kvůli rozporu mezi UI a manifestem ověř konkrétní `app.version` z `/manifest.json`.
3. Aktualizuj Passenger Python závislosti, zabezpečeně nastav Fernet vault + allowed hosts, restartuj Passenger.
4. V Ema klikni na obnovení GitHub snapshotu; ověř Issues/PR a odkaz na GitHub. Otestuj znovunačtení.
5. Na již instalovaném Adrenaline Race WordPressu rotuj staré klíče a připoj jen nový READ Key do bezpečného formuláře v Karlovi; ověř `ping`, `snapshot`, čas a obsah, pak odpojení/obnovení.
6. U `Web Fresh Develop` ověř editaci názvu, následně případně přepni typ projektu, kontroluj zachování chatů, úkolů, zdrojů.
7. V Boban chatu vlož GitHub link projektu a zkontroluj, že používá uložený snapshot (bez `source_load_error` pro GitHub stránku).
8. Ověř aktuální verzi a zkušební přístupy běžného uživatele, cizího uživatele a superadmina.

**Zásadní omezení:** kód a mock/DB regresní testy nejsou důkazem, že nový release běží na Exonu; samotná produkční data uživatele jsme nijak neměnili.
