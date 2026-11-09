# Karel 2.0.0-alpha.28 — Dlouhé odpovědi a projektový dialog

## Opravy
- Nová akce **Pokračovat v odpovědi** na konci chatu: pokračuje v témže chatu bez opětovného plánování nebo schvalování zápisů.
- Přidána orientační indikace možného uříznutí textu; jde o heuristiku, nikoli spolehlivé hlášení z AI Engine.
- Volba **Rozpracovat zadání** v rychlých dotazech, která vede analytický dialog bez předčasného kopírování zadání do jednoho pole.
- Upravená instrukce pro krátké analytické odpovědi, rozlišení známých informací od mezer a cílenou otázku.
- Verze manifestu a adminu sjednocena na `2.0.0-alpha.28`.

## Rozsah a omezení
- Nezměněna struktura databáze; zachována stávající data a oprávnění.
- Limit generování v samotném externím Fresh AI Engine nelze spolehlivě určit z manifestu. Pokud jeho odpověď končí na výstupním token limitu, vyžaduje nastavení na straně Engine. Přidané pokračování umožní text dokončit, není ale samo o sobě opravou tohoto limitu.
- Skutečná funkčnost modelu se musí ověřit na testovacím serveru, lokální kontrola ověřila syntaxi, šablony a přítomnost endpointu.

## Test scénář
1. Otevři dosavadní projekt Developer Karel a chat Zadání Karla.
2. Po poslední odpovědi klikni **Pokračovat v odpovědi**. Ověř navazující odpověď bez duplicit a bez návrhů zápisu.
3. Klikni **Rozpracovat zadání** a odešli. Karel má shrnout známé, chybějící údaje a položit jednu otázku.
4. Ověř, že se žádný nový zápis do projektové mapy automaticky neprovedl.
5. Otevři `/manifest.json`, kontroluj `app.version` == `2.0.0-alpha.28`.
