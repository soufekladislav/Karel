# Karel – návrh technické architektury a synchronizace

Stav: cílová architektura k posouzení, nikoli popis implementovaných integrací.

## Vrstvy
1. **Rozhovor a schválení** – UI chat, návrhy změn (už existují v základní podobě), explicitní potvrzení.
2. **GitHub adapter** – čtecí/zápisové operace nad repository, Issues, PR, GitHub Projects v2, workflow/check runs. Disponibilita a oprávnění se vyhodnocují zvlášť.
3. **Projektový model** – synchronizovaná vazba Karel project ↔ repo ↔ GitHub Project; identifikátory zůstávají trvalé i při přejmenování.
4. **Knihovna a kontext** – schválené standardy, repo tree, dokumentace, diff a vybrané soubory podle úkolu.
5. **Plánovač a fronta** – závislosti, priority, rezervace rozpočtu, retry s backoff, lease/heartbeat, resume.
6. **Executor adapter** – oddělený worker pro Codex / Fresh AI Engine, nikdy nepřímé tvrzení „Karel naprogramoval“.
7. **Validace** – CI, testovací protokol uživatele, kontrola skutečného GitHub stavu.
8. **Observabilita** – čas, cache hit-rate, input/output tokeny (pokud provider poskytuje), odhad/skutečný náklad, chybové kódy, návaznost na Issues.

## Zdroj pravdy
| Oblast | Zdroj pravdy | Lokálně u Karla |
|---|---|---|
| Zdrojový kód, commit, branch, PR, CI | GitHub | SHA/metadata/snapshot pro kontext |
| Issues, otevřené/uzavřené stavy | GitHub | Index a cache, včetně času synchronizace |
| Stav položky v GitHub Projects, vlastní pole, termíny | GitHub Projects | Projekce pro UI a plánování |
| Projektová sedmistupňová metodika a standardy Fresh | Schválená projektová dokumentace / knihovna | Karel DB a verzované soubory |
| Rozpracovaný návrh před schválením | Karel | Jediná autorita do rozhodnutí |
| Běhová fronta, náklady, pokusy, diagnostika | Karel | Jediná autorita; do GitHubu stručná vazba a výsledek |
| Akceptační rozhodnutí uživatele | Záznam testu u Karla + potvrzený zápis do GitHubu | Důkaz a auditní stopa |

Pozn.: GitHub Project může spojovat několik repozitářů, jeden repozitář může být v několika Project boardech. Nesmí se předpokládat mapování 1:1.

## Model synchronizace
- Ukládat alespoň owner/repo, repository_id, external issue number a node_id, project_id, project_item_id, PR number, head/base SHA, updated_at, ETag nebo jiný kontrolní otisk, last_success_sync a last_error.
- **Initial import:** pouze čtení → inventarizace → porovnání existujících lokálních úkolů → návrh mapování → schválení změn. Pokud repo nemá žádná Issues, nevyplňovat vymyšlená data.
- **Delta sync:** pokud existuje webhook a oprávnění, použít eventy s validací podpisu; vedle toho pravidelný reconciliation job. Pokud webhook není dostupný, bezpečný intervalový polling s checkpointem a respektováním GitHub rate limits.
- Idempotentní UPSERT podle stabilního ID, ne názvu. Třídit změny podle GitHub updated_at + checkpoint; kontrolovat mezery a při chybě provést reconciliation.
- Konflikt mezi lokálně čekající změnou a vzdálenou úpravou neskrytě zobrazit; nikdy automaticky nepřepsat vzdálená data. Zápis s optimistic concurrency / verifikací nového stavu.
- Při výpadku API zobrazit starý snapshot jako **zastaralý**, zakázat nebezpečné akce, zachovat rozpracované návrhy a retry až s limitem.
- Při změně GitHub role/token práv jasně označit read-only režim. Fresh Key může sloužit jako správce přístupů, nikoli kopie tokenu v logu.
- GitHub Projects API ověřit samostatným testem; GitHub Actions workflow a CI mohou být čitelné i bez Projects přístupu. Neschovávat tyto rozdíly.

## Úsporný kontext a dávkování
- První sken repo: tree, manifest, dependency mapa, dokumentace, kontrolní součet/commit SHA.
- Vybudovat index po souborech a knihovních komponentách; pro další dotazy pracovat **delta-first**, invalidovat jen změněné položky.
- Pro úkol vybrat: Issue + akceptační kritéria, závislosti, relevantní soubory/úseky, odpovídající knihovní standardy, poslední chybu a testovací výsledky. Preferovat citace zdrojových SHA/řádků.
- Pokud změna zasahuje architekturu, provést cílené rozšíření kontextu; nemožnost udržet limit řešit rozdělením úkolu, nikoli slepým zkrácením důležitých podkladů.
- Konfigurovatelný limit vstupních/výstupních tokenů, peněžního rozpočtu, paralelních jobů, času běhu a počtu pokusů; skutečnou cenu poskytovatele evidovat zvlášť od odhadu.
- Cache nesmí obsahovat nechráněná tajemství; logovat jen vyčištěná diagnostická data, ne syrové tokeny, hesla nebo celé privátní dokumenty.

## Stavový automat jobu
draft → approved → queued → running → awaiting_ci → awaiting_user_test → accepted.
Vedlejší terminální/přerušované stavy: blocked, paused_budget, failed, cancelled. Přechody vyžadují auditní záznam; obnovovaný job musí mít idempotency_key a lease, aby se nespustil dvakrát.

### Vstupní pracovní balíček pro exekutora
task_id, issue_url + node_id, base_sha, branch, affected_paths, minimal_context_refs, relevant_library_versions, explicit_allowed_changes, tests_to_run, definition_of_done, budget, retry_policy, output_schema.

### Výstup exekutora
run_id, provider, start/end, token/cost evidence, changed_files, head_sha, PR URL, tests with exit status, failures, diagnostics, unresolved questions. Karel výsledek ověří; žádné samozřejmé automatické uzavření issue.

## Bezpečnost a souhlasy
- Práva least-privilege, repo/organizace scoping, oddělený read/write a chráněný produkční režim.
- Ověřit uživatelský přístup ke každému repo a projektu; odmítnout cross-tenant únik dat.
- Nedůvěřovat instrukcím z issue, dokumentu či cizího PR (prompt injection). Externí text je podklad, nikoli příkaz k provedení akce.
- Schválení musí v UI uvést: co se mění, kde, proč, náklady/rozsah, návratový plán. Ověřit provedení a vrátit URL konkrétního výsledku.
- Zálohovat stávající DB; migrace jen dopředná, idempotentní a testovaná na kopii dat.

## Implementační omezení z revize 2026-11-18
V hlavní větvi nejsou v app/models.py tabulky pro externí GitHub ID ani worker joby. app/services/orchestrator.py pracuje s lokálními read tools. app/services/engine.py vyřizuje odpovědi Fresh AI Engine, ale není worker pro implementační joby. Zdrojová dokumentace alpha.29 dokládá pouze lokální smoke testy. Tento návrh tak vyžaduje skutečný vývoj, integraci a verifikaci.
