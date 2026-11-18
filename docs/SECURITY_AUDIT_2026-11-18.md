# Karel – bezpečnost a produkční audit (18. 11. 2026)

Status: **statická kontrola repozitáře a návrh oprav**; produkce nebyla ověřena.
Produkční doména uvedená vlastníkem: https://ai-coder.freshcrackers.cz/.
Nenasazovat tento PR do produkce bez zálohy, staging testů a zvláštního schválení.

## Potvrzené skutečnosti
- Veřejný repozitář zahrnuje historicky verzované soubory `storage/karel2.db` a `storage/uploads/...`. Jejich obsah nebyl během této revize čten ani zveřejněn. Jde o **bezpečnostní incident k prověření**, nikoli potvrzený únik osobních dat.
- Dosavadní `.gitignore` neignoroval runtime `storage/` ani DB soubory; doplněno v této větvi. **Ignorování neodstraňuje už sledované soubory ani historii Git.**
- Endpoint ručního importu manifestu používal přímo `httpx.Client(...follow_redirects=True)` bez kontroly privátních cílů. Nově používá společné ověřování adres, HTTPS a explicitní `MANIFEST_ALLOWED_HOSTS`; při chybějící konfiguraci je externí načítání manifestu vypnuto.
- Čtecí řešení URL z chatu již provádělo DNS/IP kontrolu a ověřování přesměrování. Nová kontrola manifest hostů platí také pro manifesty načítané z chatu.
- Veřejný `/healthz` předtím vracel text interních výjimek a stav založení administrátora. Nyní vrací pouze stručný dostupný/nedostupný stav.
- ZIP export používal název nahraného souboru přímo jako položku archivu; položka se nyní normalizuje na basename.
- DOCX reader nyní omezuje rozbalenou velikost `word/document.xml`.

## Nevyřešeno / vyžaduje vlastníka serveru
1. **P0 – historie Git:** zálohovat produkční data, bezpečně klasifikovat verzi veřejně sledovaných souborů bez posílání obsahu do Issue. Pokud šlo o skutečná data nebo tajemství, rozhodnout o rotaci a o čištění Git historie. Nemazat produkční `storage/` ani automaticky nepřepisovat Git historii.
2. **P0 – produkce:** porovnat HEAD kódu, DB driver a schéma, `/healthz` a přístupný (autorizovaný) `/manifest.json` na skutečné doméně, Passenger log a zálohy. Auditní skript v draft PR #3 je určen pouze pro následné read-only použití na serveru.
3. **P0 – konfigurace:** do produkčního `.env` doplnit důvěryhodné přesné manifest hosty a ověřit `APP_SECRET` (silný náhodný klíč), `SESSION_HTTPS_ONLY`, DB oprávnění, web-root, práva filesystemu a dostupnost příloh mimo URL.
4. **P1 – další obrana:** pro obecné URL ze zpráv doplnit ochranu před DNS rebindingem a streaming cap na response body; auditovat CSRF pro změnové POST routy. DNS kontrola sama o sobě nezaručuje ochranu před závodem mezi validací a připojením.
5. **P1 – zálohy a migrace:** přejít z automatického `Base.metadata.create_all` na řízené migrace a ověřitelné zálohy.
6. **P1 – přístupová práva:** prověřit přístupy k projektům, ZIP přílohám, uloženým manifestům a superadmin nástrojům v testovací produkční kopii.

## Akceptační testy
- CI: kompilace a bezpečnostní regresní testy pro manifest host allowlist, localhost odmítnutí, typ JSON, redakci veřejného health checku, bezpečné ZIP názvy a DOCX limit.
- Staging: existující projekty/soubory/chats zůstaly čitelné; opravdové povolené manifesty se načítají a nepovolené adresy jsou odmítnuty; `/manifest.json` je dostupný jen superadminovi.
- Produkce: až po ověření zálohy, stagingu, konfigurace a skutečných dat potvrdit nasazení. Automatické tvrzení o otestované produkci je zakázáno.

Navazuje na #4 a #5. Bez serverového přístupu zůstávají otevřené.
