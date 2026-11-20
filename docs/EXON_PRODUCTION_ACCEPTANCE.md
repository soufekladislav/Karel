# Exon – bezpečnostní a produkční akceptace Karla

Datum přípravy: 18. 11. 2026. Stav: **NEPROVEDENO NA SERVERU**.
Repo: `soufekladislav/Karel`, aktuální vývoj probíhá přímo v `main`; PR #14 a #21 jsou sloučené. Tento dokument je stále provozní checklist, nikoliv potvrzené nasazení.

## Důležitá hranice odpovědnosti
Tento dokument je provozní postup, nikoliv tvrzení o hotovém nasazení.
Přístup do cPanel/SSH nebyl připojen; produkční URL nebylo možné z dostupného
prostředí ověřit. **Nenasazovat aktuální `main` bez zálohy a funkčního ověření v kontrolovaném prostředí.**
Obsah `storage/` ve veřejném GitHub repozitáři byly podle vlastníka testy.
Tím není povoleno mazání serverového `storage/`.

## 1. Read-only audit současné produkce
Zkopírovat pouze bezpečnostně zkontrolovaný skript `scripts/production_audit.py`
na server do správné aplikační struktury. Ve správci souborů ani v chatu
nezveřejňovat `.env`, tokeny, zálohy, DB výpisy ani soubory klientů.

Z cPanel Terminalu v kořenu nasazené aplikace a správném Python virtualenv:

```bash
python scripts/production_audit.py > karel-audit.json
```

Skript **neimportuje `app.main`**, nespouští `create_all`, neprovádí ALTER
a nenačítá obsah zákaznických záznamů. Vrací verzi zdrojáku, booleany konfigurace
a pouze počty řádků a existenci očekávaných tabulek. Výstup sdílet jen po kontrole,
že v něm není nic citlivého. Pokud se spouští proti starému deploymentu, místní
verze zdrojáku může být odlišná.

Pro zjištění práv a přímé veřejné dostupnosti mimo script ještě ověřit:
- Kde skutečně leží Apache DocumentRoot a PassengerAppRoot; zda `.env`, `storage/`,
  `tmp/`, SQLite/MariaDB dump ani archiv příloh nejsou stažitelné HTTP URL.
- SSH/cPanel oprávnění k `.env`, DB, logům, uploadům a zálohám; `.env` pouze pro
  oprávněného uživatele aplikace, storage mimo veřejný DocumentRoot.
- Dostupné zálohy databáze, `storage/` a kódu; **vyzkoušet obnovu do stagingu**.
- Verzi Pythonu/Passengeru a reálné venv oproti requirements; záznamy chyb v logu.

## 2. Záloha + staging (povinné)
1. Vytvořit zvlášť zálohu databáze a serverového `storage/`. Uchovat mimo veřejný
   web root; DB backup nesmí být v GitHubu. Ověřit dobu a velikost zálohy.
2. V cPanelu vytvořit testovací Python app s **oddělenou DB, storage a `.env`**.
   Nenasazovat staging do stejné cesty jako produkci.
3. Nasadit obsah ověřeného commitu z `main` pouze na staging (pokud se pro bezpečné ověření používá). Nenahrazovat produkční
   `.env` ani `storage/`. Ověřit Passenger virtualenv a `pip install -r requirements.txt`.
4. Ve staging `.env` nastavit:
   - `KAREL_ENV=production`, vlastní HTTPS `APP_URL`, náhodný `APP_SECRET` délky
     alespoň 32 znaků, `SESSION_HTTPS_ONLY=true`.
   - Správnou `DATABASE_URL`; `GITHUB_ALLOWED_OWNERS=soufekladislav`, read-only
     `GITHUB_READ_TOKEN` jen pokud je skutečně třeba. Nepředávat klíč chatu.
   - Jen důvěryhodné `MANIFEST_ALLOWED_HOSTS` a `SOURCE_ALLOWED_HOSTS`.
     Prázdný seznam znamená bezpečné odmítnutí daných externích načtení.
5. Schéma databáze: **nedělat automatické migrace při restartu**. Spustit jen náhled:

```bash
python scripts/schema_migration.py
```

   Pokud vypíše změny, nejdříve ověřit obnovu DB ze zálohy ve stagingu.
   Teprve poté je možné explicitně spustit:

```bash
python scripts/schema_migration.py --apply --backup-file /SECURE_BACKUP_OUTSIDE_WEB_ROOT/karel-backup.sql
```

   Skript kontroluje existenci, velikost a stáří zálohy (do 24 hodin).
   **Neumí potvrdit, že záloha je obnovitelná**, proto je test obnovy zvlášť.
   Na MariaDB DDL nemusí podporovat rollback; bez restorable backup NEPOUŽÍT.
6. Staging znovu spustit a testovat přihlášení, chat, dokumentaci, uploady, knihovny,
   návrhy akcí a schválení, předávání obsahu AI Engine, GitHub čtení a import bez duplicit.

## 3. Bezpečnostní smoke test před release
| Test | Požadovaný výsledek |
|---|---|
| `GET /healthz` | 200, pouze `ok/status`, nebo 503 při skutečné chybě |
| `GET /login` | Přihlašovací stránka, bez interní výjimky |
| `GET /manifest.json` bez relace | Nevrátí interní manifest |
| `GET /.env`, `/storage/karel2.db`, `/tmp/` | 403/404, nikdy 200 |
| POST formuláře s cizím `Origin` | 403 bez změny DB |
| POST správným formulářem na stejné doméně | Funguje; ochrana nesmí rozbít UI |
| Uživatelská role `viewer` | Nemůže schvalovat, zapisovat, stahovat cizí soubory |
| Cizí `chat_id` při task/ZIP | 404, žádné zápisy mimo projekt |
| Manifest mimo allowlist nebo na interní IP | Odmítnut, žádné načítání |
| Import stejného GitHub repo opakovaně | Jedna vazba, bez nových duplicit |
| Upload ZIP/PDF/DOCX s chybným obsahem | Bez spuštění souboru, bezpečné odmítnutí |
| Přerušení DB či GitHub API | Srozumitelná chyba, data se nepřepisují |
| Ověřená obnova databáze | Stejná počáteční data a přístup v testovacím prostředí |

`.htaccess` obsahuje dodatečnou Apache ochranu. **Není důkazem uzavření přímých
URL, dokud nejsou testovány z internetu proti skutečnému DocumentRoot.**

## 4. Produkční nasazení (až po akceptaci)
- Označit otestovaný commit/release; nasazovat schválený artefakt, ne libovolný HEAD.
- Zálohovat živou DB a storage ještě jednou před nasazením, mít rollback kód i DB.
- Migraci schématu spustit výslovně po záloze. Udržet nezměněné produkční secrets.
- Restart Passengeru a zkontrolovat `/healthz`, přihlášení, úkoly, soubory, AI Engine,
  GitHub a logy. Po změně `APP_SECRET` dojde k očekávanému odhlášení uživatelů.
- Pokud některý test selže, zastavit rollout a obnovit odpovídající kombinaci kódu
  a DB; nevracet jen kód, pokud nová migrace změnila schéma.

## 5. Závislosti před porovnáním UX
- Zaznamenat přesnou produkční verzi a přesnou staging verzi.
- Udělat screenshoty desktop/mobile: Chat, Zadání a obchodní cíle, GitHub, Pipeline,
  Knihovny, Nastavení/Účet.
- Použít `docs/UX_COMPARISON_ACCEPTANCE_2026-11-18.md` pro porovnání s požadavky.
- Žádný CI test nebo screenshot sám o sobě nepotvrzuje bezpečné produkční nasazení.

**Závěr:** do potvrzení všech testů v Exon prostředí zůstává bezpečnost produkce
otevřená; výsledky v GitHub Actions jsou pouze důkazem otestovaného kódu.
