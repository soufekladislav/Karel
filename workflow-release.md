# Karel alpha.25 – 7 etap projektu

Nová tabulka `project_stages` se vytvoří při bootstrapu aplikace (`create_all`). Existující databázové tabulky ani storage se nemažou.

- Projektová nástěnka obsahuje 7 rozbalovacích etap, termíny, kritéria převzetí a stav.
- Etapy mohou být naplánovány dopředu. Aktivace a schválení vyžadují schválené předchozí etapy.
- Každá změna etapy se zapisuje do `project_events`.
- Při zobrazení stránky jsou počítána upozornění 3 dny před termínem a při prodlení.
- Kontext všech etap a termínových rizik vstupuje do chatu.
- Automatická externí oznámení, propojení úkolů na etapy a schvalování pomocí konverzačních nástrojů zatím nejsou implementována.

## Nasazení
Zálohujte DB a celý adresář. Zachovejte produkční `.env`, `storage/`, virtuální prostředí a Passenger konfiguraci. Po nahrání nové aplikace restartujte Passenger a ověřte `/healthz`, otevření projektu, ukládání etap a upozornění. Při změně způsobu nasazení kontrolujte, zda DB účet může vytvářet novou tabulku.
