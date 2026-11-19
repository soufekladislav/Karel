# Karel – připojení živých dat Fresh Core 0.7.8 a GitHub (19. 11. 2026)

**Stav:** implementováno v integrační větvi `develop/karel-platform`, draft PR #14; testy používají mockované HTTP serverové odpovědi. Nejedná se o potvrzení, že je připojen konkrétní skutečný WordPress ani že byl kód nasazen na Exon.

## 1. Ověřený kontrakt ze souboru Fresh Core 0.7.8 (přiložený ZIP)
V dodaném balíčku `fresh-core(3).zip`:
- `fresh-core/fresh-core.php` a `readme.txt`: verze 0.7.8.
- `includes/class-fresh-core-auth.php`: čtení používá hlavičku `X-Fresh-Core-Key`; čtecí konektor musí být povolen. Write má **jiný** klíč `X-Fresh-Core-Write-Key`, nová integrace v Karlovi jej nepoužívá.
- `includes/class-fresh-core-rest.php`: `GET /wp-json/fresh-core/v1/ping` a `GET /wp-json/fresh-core/v1/snapshot`; struktura `{"success":true,"data":{...}}`.
- `includes/class-fresh-core-data.php`: snapshot obsahuje `manifest.site`, `manifest.runtime`, `manifest.active_plugins`, `post_types`, `taxonomies`, `menus` a `elementor_overview`; může obsahovat i interní struktury webu. **Karel ukládá pouze whitelistovaný čtecí souhrn**, ne celý snapshot ani uživatelské účty, objednávky nebo DB tabulky.
- `RELEASE-0.7.8.md` popisuje SEO URL resolve/write, který není v této P1 čtecí integraci povolen.

## 2. Příprava Exon – bez změny produkční DB schématu

Nejdříve aktualizuj instalační závislosti novou `requirements.txt` v aktivním Python Passenger venv, potom ověř zdrojový kód v staging prostředí. **Žádná migrace tabulek není v této etapě požadována**; používají se existující `project_memory` a `project_events`.

Do neveřejné serverové `.env` (nikdy do GitHubu ani chatu) nakonfiguruj:
```dotenv
FRESH_CORE_VAULT_KEY=<vygenerovaný Fernet klíč, 44 znaků>
FRESH_CORE_ALLOWED_HOSTS=freshcrackers.cz,www.freshcrackers.cz,adrenalinerace.eu,www.adrenalinerace.eu
```
Vygeneruj klíč **na serveru**:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Seznam hostitelů nastav podle **skutečných webů, které chceš v projektu připojovat**. Nenastavuj `*`, celé veřejné TLD ani interní domény. Vlastní web zákazníka musí být v seznamu výslovně povolen, což je omezení této první bezpečné verze. `FRESH_CORE_VAULT_KEY` uchovej v zabezpečené externí záloze spolu s produkční databází; po ztrátě klíče nepůjde uložené Fresh Core credential dešifrovat.

**Nikdy nevkládej READ key do URL, query stringu, logu, chatu ani GitHub Issue.** V projektu ho vlastník zadá do specializovaného heslového formuláře, který jej před uložením šifruje Fernetem. Dešifrování je pouze na serveru při konkrétním dotazu. Tímto se ale neprokazuje, že samotná databáze nebo aplikace není kompromitovaná.

## 3. Test skutečného WordPress webu
1. Na WordPressu nainstaluj/aktivuj verzi Fresh Core 0.7.8.
2. Ve správě Fresh Core zapni REST čtecí konektor a vyhledej jeho `Access Key`; při testování nech zapisovací bridge vypnutý.
3. V Karlovi otevři WordPress projekt → „Můj WordPress“, ulož kanonickou HTTPS adresu a v části „Čtení z WordPressu“ vyplň **pouze READ Key**.
4. Klikni na „Ověřit spojení a načíst web“. Server udělá GET ping a snapshot s hlavičkou `X-Fresh-Core-Key`, bez následování redirectů a bez jiných HTTP metod.
5. Ověř skutečný název webu, WordPress verzi, počet pluginů a dokumentů, poslední čas načtení a související informace v chatu. Testovací spojení nesmí být zobrazeno jako dokončené bez úspěšné odpovědi ze správné domény.
6. Spusť „Načíst aktuální data“ a porovnej čas. Po odpojení zmizí klíč i snímek z Karla. Pro úplné zneplatnění klíče jej regeneruj také ve WordPress Fresh Core.

**Stav v Karlovi:** `unlinked`, `synced`, `key_unavailable`, `pending`. Pokud spojení selže, předchozí úspěšný snímek zůstane, v UI se zobrazí srozumitelná chyba. Nejde o automatický periodický monitoring; refresh je nyní vyvolaný uživatelem.

**Zabezpečení:** schválený HTTPS host, kontrola veřejné IP při každém dotazu, redirect zakázán, limit 2 MB po dekompresi, READ klíč pouze v HTTP hlavičce, oddělení rolí (spravuje vlastník/správce, obnoví editor). Tato kombinace není náhradou síťové egress politiky – pro silnější ochranu proti DNS rebinding se doporučuje navázat provozní síťové omezení cílových adres.

## 4. GitHub – veřejná a privátní cesta
- **Běžný vlastník projektu:** může do GitHub karty zadat `vlastnik/repozitar` a načíst *veřejný* repozitář. GitHubReader běží **bez společného tokenu** a odmítá `private=true`. GitHub API běžně limituje anonymní požadavky; ruční obnovu stejného repozitáře aplikace omezuje na 5 minut.
- **Superadmin:** pro vlastní soukromá repozitáře může na Exonu nastavit `GITHUB_ALLOWED_OWNERS` a `GITHUB_READ_TOKEN`; tento serverový token se nikdy nepoužije pro běžného zákazníka.
- Karel ukládá časově označený snapshot (omezené Issues, PR, Projects v2 a CI) a poskytuje originální odkazy. Nejde o plné stahování celého GitHubu ani o automatický obousměrný sync.
- „Odpojit GitHub“ smaže jen lokální vazbu a snapshot v Karlovi. Originální repo, Issues/PR zůstávají beze změny.
- **Soukromé repozitáře běžných zákazníků:** stále vyžadují GitHub App/OAuth per-user. Nepoužívat cizí PAT ani vkládání tokenů do chatu.

## 5. Správa dat
Stávající Karel již podporoval: úpravy projektových údajů, archivaci/smazání projektu, přejmenování/archivaci/smazání chatů, změny/archivaci/smazání tasků, úpravy/smazání knihovny.

Tato etapa doplňuje:
- odstranění při mazání projektu **také `project_stages` a `github_repo_links`**, takže FK vazby nezůstanou viset;
- trvalé smazání projektu **jen po archivaci** a po přesném opsání názvu; fyzické uploady mažeme až po DB commit;
- archivaci, obnovení a smazání projektových souborů s vlastnickou kontrolou a se zachováním ostatních záznamů;
- potvrzení nevratného odstranění položky knihovny;
- bezpečné odpojení GitHub a Fresh Core, bez zásahu do externího webu/repozitáře.

**Zbývá:** archivační stav položek knihovny a podrobnější versioning dokumentace, prodloužená testovací obnova projektu a revizní audit po celkovém smazání; tyto věci vyžadují samostatné datové rozhodnutí/migraci, ne skrytý hack do existujících sloupců.

## 6. Převzetí
Před produkcí: CI, záloha DB + souborů + vault key, staging se skutečným Fresh Core webem, dva testovací profily rolí, kontrola bezpečných hostů, opakovaný sync i selhání spojení, archive/restore/delete v testovacím projektu a návrat na původní verzi. Při nesplnění **nevykazovat jako otestovanou produkční funkcionalitu**.

**Rollback:** vrátit aplikační release; ponechat databázi/snapshoty/klíče. Nevynucovat reset DB. Nové `cryptography` je přidaná závislost aplikace; pokud není ve venv, nenasazovat. Tato etapa nemění externí WP plugin, WordPress write bridge ani externí GitHub obsah.
