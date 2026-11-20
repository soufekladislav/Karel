# GitHub Karel – úklid a kontrola větví (20. 11. 2026)

Zdroj: skutečné GitHub API porovnání větví vůči main HEAD
9f63748f3753ae67e208a9a95cd906039031bf5b. Jedná se o
**návrh provozního úklidu**, nikoli potvrzení, že byly větve smazány.

| Větev | Ahead vůči main | Behind | Bezpečné rozhodnutí |
| --- | ---: | ---: | --- |
| develop/karel-platform | 0 | 11 | Obsah již zahrnutý v main; lze odstranit vzdálený odkaz po schválení |
| feature/fresh-core-read-audit | 0 | 12 | Obsah zahrnutý v main; lze odstranit odkaz po schválení |
| audit/p0-security-prod-20261118 | 0 | 195 | Obsah zahrnutý v main; lze odstranit odkaz po schválení |
| docs/karel-project-manager-orchestration-2026-11 | 6 | 215 | Diverged, neodstraňovat bez porovnání dokumentů |
| feature/github-readonly-import-sync-p1 | 19 | 214 | Diverged, neslučovat automaticky; pozdější main může již obsahovat funkčně shodný kód |
| ux/karel-six-screens-20261118 | 7 | 214 | Diverged, neodstraňovat bez kontroly odlišných commitů |

Počty jsou konkrétní k 20. 11. 2026 před dalšími commity a mohou zestárnout.
Staré PR #13, #11 a #3 jsou CLOSED bez merge; jejich zdrojové větve jsou
odlišné. PR #14 a #21 jsou sloučené; PR #2 je také merged.
**Zero active PR** a 15 otevřených Issues byly ověřeny na GitHubu.

## Pořádek v zdroji pravdy

- README + AGENTS.md používají aktivní větev main.
- docs/PRODUCT_SPECIFICATION.md: cílová specifikace, nikoli důkaz funkčního release.
- Docs/README netvrdit, že schválený projektový plán vzniká v chatu automaticky
  bez potvrzeného zápisu.
- GitHub Issue #20: čtení dokumentů, kódu a větví, postupný audit.
- GitHub Issue #9: schválené zápisy Issues, změny a případně merge.
- GitHub Issue #10: exekuce přes AI Engine → coding agent, CI a test.
- GitHub Issue #4: akceptace skutečného provozu na Exonu.

## Co musí Karel příště udělat sám

1. Porovnat všechny větve s aktuálním main; odlišit merged (ahead=0) od diverged.
2. U diverged porovnat relevantní zdrojové soubory se současným main, určit
   funkcionality skutečně chybějící, duplicitní a nahrazené.
3. Připravit návrhy na úklid s přesným odkazem a diffs a získat konkrétní schválení.
4. Provedenou operaci ověřit opětovným čtením GitHubu a zapsat audit.
5. Nikdy nepovažovat zavřený PR za automaticky začleněný nebo otestovaný.

### Omezení této revize

Použitý GitHub konektor pro tuto konzultaci neumí odstranit branch ref.
**Nebyly mazány větve ani Issues, nic nebylo automaticky sloučeno.**
Žádné obsahové rozdíly z diverged větví se tímto dokumentem neuzavírají.
