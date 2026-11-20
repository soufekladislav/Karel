# Fresh Core – read-only audit v Karlovi (alpha.34 návrh)

Tato dávka navazuje na #19 a draft PR #14. Výchozím zdrojem je skutečný
\`GET /wp-json/fresh-core/v1/snapshot\` z Fresh Core 0.7.8 (přiložený ZIP).
Nečte automaticky tajné veřejné static-export URL ani zákaznická data.

## Co je nové
- Rozšířen whitelist ukládaných údajů o identifikátor/verzi aktivních pluginů,
  bezpečné otisky struktur menu, typy Elementor šablon, aktivní Fresh moduly
  a pokrytí/omezení načtených seznamů.
- Po každém úspěšném READ handshake je porovnán nový snímek s předchozím.
  Změněný starý stav se uchová jako verzovaná historie v projektové paměti,
  nejvýše 10 předchozích stavů. Přehled změn je dostupný v kartě webu a chatu.
- Změny jsou **struktura a inventura**, nikoli diagnostika PHP/JS runtime;
  chybějící evidence znamená \`nelze ověřit\`, nikoli automaticky chybu.
- V případě chybného REST spojení zůstává poslední ověřený snímek.
- Žádný zápis do WordPressu, žádný účetní/WRITE klíč ani migrace DB.

## Zprovoznění na Exonu (provozní zásah se provádí zvlášť)
1. Záloha Karlovy DB, souborů a \`.env\`. Nenasazovat částečný mix PR.
2. Staging: nainstalovat závislosti \`pip install -r requirements.txt\`, spustit
   \`python -m unittest discover -s tests -p 'test_fresh_core*.py'\`.
3. Do skutečné neveřejné \`.env\` Karla nastavit stabilní a zálohovaný
   \`FRESH_CORE_VAULT_KEY\` a přesně povolené domény v
   \`FRESH_CORE_ALLOWED_HOSTS\` (např. \`adrenalinerace.eu,www.adrenalinerace.eu\`).
   Klíč generovat na serveru \`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"\`.
   Nikdy v GitHubu nebo chatu. **Pokud již existuje klíč a zašifrovaná spojení,
   původní vault klíč zachovat, nevytvářet nový.**
4. Restart Passenger. V projektu Web – Adrenaline Race vyplnit
   \`https://adrenalinerace.eu\` a nový READ Access Key z již instalovaného
   Fresh Core. Nepoužívat WRITE/ACCOUNTING ani manifest URL.
5. Ověřit skutečná data (pluginy/WordPress/Elementor) a zopakovat refresh
   po řízené změně na staging webu. Provozní verzi ověřit v manifestu Karla.
6. Negativní test: špatný klíč / 403 / redirect / nekompletní JSON; starý
   snímek zůstává. Před produkcí schválit rollback a celkovou akceptaci.

## Důležitá hranice
Dnešní REST /snapshot není plný statický export manifest/batch-status
a neobsahuje runtime PHP error log, JS console, detailní obsah stránek ani
otisky každého PHP souboru. Plný export se bude doplňovat bezpečnou
READ-only API cestou ve společném Fresh Core, bez narušení Bobana, Lindy,
Viki a Edy. Nikdy nepředstírat úplnou kontrolu všech funkcionalit.
