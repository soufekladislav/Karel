# Aktualizace Karla alpha.28

1. Zálohuj produkční soubory i databázi.
2. Zachovej `.env`, celý `storage/` a existující Python virtuální prostředí.
3. Nahraď aplikační kód soubory z ZIP, bez mazání provozních dat.
4. Restartuj Passenger / Python aplikaci.
5. Ověř `/manifest.json` a `app.version = 2.0.0-alpha.28`.
6. Proveď test dle `RELEASE-ALPHA28.md`.

Balíček neobsahuje žádné provozní databáze, nahrané přílohy ani historii release.
