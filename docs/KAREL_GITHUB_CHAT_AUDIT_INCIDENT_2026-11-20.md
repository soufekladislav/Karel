# Karel – konkrétní incident falešné schopnosti GitHub chatu (20. 11. 2026)

## Uživatelský reproduktor
V projektu „Developer Karel“ byly zadány tyto pokyny:
- „Ahoj, co už umíš?“ → odpověď jmenovala návrhové/budoucí vlastnosti jako již hotové
- „Potřebuji projít GitHub a zkontrolovat celý projekt včetně repozitáře a očistit o všechny balasty.“ → Karel požadoval URL a oprávnění, přestože již existovala projektová karta GitHub
- „Karle, projdi aplikaci svou app Karel na GitHubu a vysvětli mi, k čemu slouží, co umí a co je potřeba dodělat.“ → Karel znovu požadoval URL a odhadoval chybějící funkce ze zadání

## Příčina ověřená v kódu
- orchestrator.py uměl číst lokální project/tasks/library/history, ale **neměl žádné volání GitHubReader pro přímý chatový audit**
- context_builder.py pouze vkládal **existující** GithubRepoLink.snapshot_json. Pokud link nebyl k dispozici, nezjišťoval repo a nevytvářel živé zdroje
- Dřívější alfa .35.3 přidala obsah několika Markdown souborů do synchronizačního snímku, ale chatu nedala možnost tuto synchronizaci skutečně vyvolat
- prompt s ambiciózním popisem schopností bez strojového potvrzení dovolil odpověď, která pletla zamýšlené a implementované funkce

## Oprava v main – alpha.35.4
- Přidán projektově omezený read-only GitHub audit do orchestrator.py. Dotaz „projdi GitHub“ vyvolá skutečný GitHubReader.snapshot, ne samotnou LLM odpověď. Při chybě API nevymýšlí výsledek ani nezamění starou cache za live data.
- U propojených projektů se **nežádá znovu URL**. Jediná administrátorská výjimka je self-project s přesně daným názvem „Developer Karel“/„Karel“ a repozitářem soufekladislav/Karel. U ostatních zákaznických projektů žádné odhadování repo.
- READ snapshot se může uložit do stejného projektu bez GitHub zápisu; po načtení znovu nejdřív po 5 minutách. Pokud bylo repo již přiřazeno jiné vlastní kartě, duplicitu automaticky nevytváříme.
- Odpověď z GitHub auditu obsahuje repo URL, SHA, čas, vybrané dokumenty, skutečné Issues/PR/CI a označení omezení. Neoznačuje těchto pár dokumentů za celý audit kódu; kandidáty souborů k úklidu pouze navrhuje ke kontrole.
- Na obecné „Co už umíš?“ vrací Karel ověřený aktuální seznam a přiznává, že GitHub write, Codex programming, staging a release zatím neumí.

## Převzetí
1. Nasadit kompletní vydání na Exon. Zachovat DB, storage/.env a restartovat Passenger; na serveru ověřit alpha.35.4
2. V projektu Developer Karel bez vložení URL zadat přesně třetí uživatelův pokyn výše. Očekávaný výsledek: zdroj soufekladislav/Karel, skutečný SHA, datum, konkrétní README, názvy a odkazy na Issues; bez žádosti o URL. Pokud je limit GitHub API, Karel musí výslovně ukázat chybu a nepsat vymyšlený audit
3. Zopakovat stejný dotaz po méně než 5 minutách a ověřit označení uloženého snímku (nikoli nový placený network crawl)
4. Z projektu jiného zákazníka bez GitHub linku musí připojení bezpečně vyžadovat skutečnou vazbu; nesmí automaticky číst Karel repo
5. „Co už umíš?“ musí obsahovat i dosud neimplementované vlastnosti, nesmí slibovat write ani produkční deploy

## Omezení
Tento fix není globální full code analyzer, GitHub write API ani Cleanup agent. V rámci zabezpečení zůstává potřeba projít zbytek Issue #20 (paginace/cílené file reads) a Issue #9 (schvalované GitHub writes). Konec fáze je až **uživatelský test na Exonu**, nikoli samotné CI.
