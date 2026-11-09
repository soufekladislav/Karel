# Karel 2.0.0-alpha.27 — Project Intake / Dialogue Gate

## Opravy
- U komplexních zadání (dlouhý text, více částí) je vypnutý předčasný klíčově-slovní zápis do projektové mapy.
- První reakce AI na komplexní zadání je analytická, bez zápisových akcí, i když model navrhne skrytý stav.
- Projektový kontext nově vyžaduje rozbor cílů, uživatelů, rolí, UX, zařízení, funkcí, integrací a chybějících informací.
- Výchozí typové workflow sjednoceno na sedm etap Fresh Development Standard.
- Přidaná schvalovaná akce update_workflow_stage pro řízenou aktualizaci etap, dat a termínů.
- Dlouhé zadání se na projektové nástěnce zobrazuje jako stručný úryvek.

## Co není hotové
- Neexistuje robustní řízený průvodce s validací úplnosti zadání a trvalou strukturou všech jeho částí.
- Model může v dalších zprávách navrhnout nevhodné rozdělení: uživatel musí změny před schválením kontrolovat.
- Zatím není realizováno plné napojení úkolů na etapy a automatické plánování termínů.
- Není nový samostatný dokumentový typ pro UX/persony. Prozatím jde o inteligentnější konverzační návrh nad existující mapou.

## Nasazení
1. Zálohuj aplikační adresář a databázi.
2. Zachovej `.env`, `storage/`, stávající databázi a `.venv/`.
3. Nahraď aplikační soubory ze ZIPu. Neodstraňuj uživatelské soubory ani data.
4. Restartuj Passenger. Otestuj nové dlouhé zadání i úzký zápis, schválení akce workflow a sedm etap.

Statické a smoke testy proběhly. Produkční provoz na Exon.io nebyl testován.
