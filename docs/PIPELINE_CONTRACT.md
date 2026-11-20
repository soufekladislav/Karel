# Kontrakt projektového harmonogramu – Karel

**Rozhodnutí 20.–21. 11. 2026:** jediný závazný zdroj datumů je schválená databázová verze ProjectMemory(kind=project_schedule) v Karlově Pipeline. Nikoli textové pole project_plan v Projektové mapě nebo odpověď chatbota.

## Postup z dialogu do provedení

1. Uživatel řekne obchodní cíl a požadovaný termín; Karel čte existující Pipeline, odliší původní datum od nového.
2. Karel napřed vysvětlí známá rizika, neověřenou pracnost a kapacitu. Zkrácený termín není důkaz, že lze dodat vše. Pro projekt Karel nabízí A = omezené testovací MVP, B = celý rozsah s novým odhadem po technické inventuře. Volba B nevygeneruje vymyšlené termíny.
3. Po výslovné volbě A připraví M0–M6 s termíny a přejímkou; pouhý chat není schválení.
4. Uživatel vidí rozdíl, rozsah i rizika; jedním schválením backend ověří původní požadavek, ochranu před konkurující novou verzí a strukturu, zapíše historickou verzi do DB a ověří znovunačtením.
5. AŽ PO DB COMMIT backend automaticky zkusí poslat schválený plán do souboru docs/KAREL_APPROVED_PIPELINE.json v repozitáři soufekladislav/Karel (GitHub Contents API). Zkontroluje Git blob SHA z konkrétního commitu. Opakování stejné verze nevytvoří další commit.
6. Stav GitHub projekce je oddělený: synced, blocked, failed, conflict. Vzdálená chyba nikdy nemaže schválenou Pipeline. Stav a bezpečné opakování jsou přímo na stránce Pipeline.

## Jednorázové oprávnění v Exon .env

GITHUB_ALLOWED_OWNERS=soufekladislav
GITHUB_SCHEDULE_WRITE_ENABLED=true
GITHUB_SCHEDULE_WRITE_TOKEN=(tajný samostatný fine-grained token, jen soufekladislav/Karel, Contents read/write)

**Token neposílat do chatu, GitHub Issues, UI ani logů.** Nezaměňovat s GITHUB_READ_TOKEN. Při aktualizaci zachovat .env, DB a storage; restartovat Passenger.

Tento krok publikuje **GitHub dokument harmonogramu**. Nemění termínová pole GitHub Issues či Projects v2, PR ani commity se zdrojovým kódem. Na to bude navazovat jiný samostatně autorizovaný konektor.

## Omezení a provozní přejímka

- Pilotní variantu A tvoří zadání a chat, schválení/uložení Pipeline, ověřené GitHub čtení a publikování schváleného kalendáře do GitHub dokumentu.
- Automatické programování Codexu, GitHub Projects v2 zápis, staging a produkční nasazení nejsou tímto krokem dokončené.
- M0–M6 je zatím šablona Karla, ne obecný kapacitní plánovač. Riziková klasifikace není změřený odhad zbývajících hodin.
- Přejímka na Exonu: žádost o termín kompletního Karla do 20.12.2026 musí vést k vysvětlení rizik bez schvalovacího návrhu. Výběr omezeného MVP vytvoří návrh; jedno schválení zapíše datumy do Pipeline; podle oprávnění proběhne remote write + readback nebo je vidět konkrétní blokace.

### Testovací věta

„Máme v Pipeline termín 29. 1., chtěl bych celý projekt zkrátit do 20. 12. 2026. Navrhni realistický plán.“

Karel vysvětlí varianty a nepředstírá provedení. Po „Volím variantu A (omezené MVP)“ použije cíl 20.12.2026, vytvoří návrh, po schválení uloží DB verzi a ověří stav GitHub projekce.
