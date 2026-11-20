# Obnova Karla po Server Error 500 – Exon / Passenger

Vydání **2.0.0-alpha.35.2-passenger-startup-fix** řeší dvě třídy problémů
při ručním nasazení Karla přes GitHub Desktop na Exon:
- nový konektor Fresh Core dříve **importoval knihovnu `cryptography` při
  startu aplikace**; pokud nebyla nainstalována v Passenger venv, spadl celý web,
  i když se konektor ještě nepoužíval;
- původní `passenger_wsgi.py` používal `imp.load_source`, který je **odstraněný
  od Pythonu 3.12**. Nyní používá standardní import `startup.application`.

Obě chyby byly identifikovány kontrolou repozitáře. **Bez produkčního tracebacku
nelze potvrdit, která z nich způsobila konkrétní chybu 500 na Exonu.**

## Nasazení bez ztráty dat

1. Zálohovat **.env, MariaDB, storage/** a privátní Fresh Core vault.
2. Na Exon stáhnout kompletní `main`, nikoli jednotlivé soubory. NEMAŽTE
   `storage/` ani serverovou `.env`, neprovádějte `git clean` přes runtime data.
3. V cPanelu **Setup Python App** otevřít Karla, použít tam uvedený příkaz
   pro aktivaci přesně toho virtuálního Python prostředí, které Passenger používá.
4. V kořenové složce aplikace spustit v tomto prostředí:

   ```bash
   python -m pip install -r requirements.txt
   python scripts/server_preflight.py
   ```

   Očekáváme všechny základní knihovny **OK**, zejména `a2wsgi`,
   `PyMySQL` a `cryptography`. Neposílat `.env` nebo klíče do chatu.
5. V cPanelu stisknout **Restart** aplikace / Passenger. Ověřit úvodní stránku,
   přihlášení a projekt Adrenaline Race. Poté spojení manifestu Fresh Core.
6. Pokud aplikace stále vrací HTTP 500, zjišťovat **první exception/traceback**
   ze serverového stderr nebo Passenger logu; nehádat příčinu podle samotné HTTP
   stránky. Sdílet pouze redigované řádky – bez tokenů, přístupových údajů,
   domovských cest a osobních dat.

## Kritérium pro vývoj
Automatické testy musí kontrolovat i import `passenger_wsgi.py` při simulaci
chybějící `cryptography` a pod Pythonem 3.11 i 3.12. Připojovací funkce
může ohlásit chybějící knihovnu, ale **nesmí shodit login, projektové stránky
a ostatní agenty**.

**Tato změna nezapisuje do WordPressu, nemigruje databázi a sama o sobě
nedokazuje produkční funkčnost.**
