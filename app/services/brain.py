from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from ..config import settings

BRAIN_FILE = settings.storage_dir / 'brain.json'

DEFAULT_BRAIN = {
    'version': 1,
    'communication': {
        'tone': 'stručný, praktický, přátelský a profesionální',
        'max_detail': 'short',
        'rules': [
            'Nepoužívej dlouhé texty, pokud nejsou nutné.',
            'Začni závěrem nebo nejdůležitějším krokem.',
            'Delší analýzu odděl od krátké odpovědi a označ ji jako Detailní analýza.',
            'Když něco nevíš, řekni přesně jaký zdroj chybí.',
        ],
    },
    'tools': {
        'urls': 'auto_resolve',
        'files': 'auto_context',
        'images': 'vision_when_supported',
        'manifest': 'prefer_live',
        'cross_project': 'offer_reuse',
    },
    'project_guidance': {
        'proactive': True,
        'ask_before_large_work': True,
        'offer_save': True,
        'one_confirmation_executes': True,
        'required_map_fields': ['business_goal', 'functional_goal', 'project_plan'],
    },
    'project_types': {
        'app_development': {
            'label': 'Vývoj aplikace',
            'workflow': ['Zadání', 'Analýza', 'Architektura a UX', 'Plánování', 'Vývoj', 'Závěrečné ověření', 'Nasazení a uzavření'],
        },
        'wordpress_fresh_core': {
            'label': 'Správa WordPress přes Fresh Core',
            'workflow': ['Zadání', 'Analýza', 'Architektura a UX', 'Plánování', 'Vývoj', 'Závěrečné ověření', 'Nasazení a uzavření'],
        },
        'wordpress_elementor': {
            'label': 'Vývoj WordPress + Elementor PRO',
            'workflow': ['Zadání', 'Analýza', 'Architektura a UX', 'Plánování', 'Vývoj', 'Závěrečné ověření', 'Nasazení a uzavření'],
        },
        'cyber_security': {
            'label': 'Kybernetická bezpečnost',
            'workflow': ['Zadání', 'Analýza', 'Architektura a UX', 'Plánování', 'Vývoj', 'Závěrečné ověření', 'Nasazení a uzavření'],
        },
    },
}


def _merge(default: dict, value: dict) -> dict:
    result = deepcopy(default)
    for key, val in (value or {}).items():
        if isinstance(val, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], val)
        else:
            result[key] = val
    return result


def load_brain() -> dict:
    if not BRAIN_FILE.exists():
        save_brain(DEFAULT_BRAIN)
        return deepcopy(DEFAULT_BRAIN)
    try:
        data = json.loads(BRAIN_FILE.read_text(encoding='utf-8'))
        return _merge(DEFAULT_BRAIN, data)
    except Exception:
        return deepcopy(DEFAULT_BRAIN)


def save_brain(data: dict) -> None:
    BRAIN_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = BRAIN_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(BRAIN_FILE)


def brain_instructions(project_spec: dict | None = None) -> str:
    cfg = load_brain()
    comm = cfg.get('communication', {})
    guidance = cfg.get('project_guidance', {})
    tools = cfg.get('tools', {})
    spec = project_spec or {}
    project_type = str(spec.get('project_type') or '').strip().lower()
    selected = None
    for key, item in cfg.get('project_types', {}).items():
        label = str(item.get('label') or '').strip().lower()
        if project_type in (key.lower(), label) or (project_type and project_type in label):
            selected = item
            break
    if selected is None:
        selected = cfg.get('project_types', {}).get('app_development', {})

    missing = [f for f in guidance.get('required_map_fields', []) if not str(spec.get(f) or '').strip()]
    lines = [
        'MOZEK KARLA — PROVOZNÍ PRAVIDLA:',
        f"- Tón: {comm.get('tone','stručný a praktický')}.",
        '- Odpověz krátce; nepřepisuj uživateli celý kontext, pokud o něj nežádá.',
        '- Pokud je potřeba delší analýza, dej nejdřív 2–5 stručných bodů a potom sekci „Detailní analýza“.',
        '- URL, které jsou už načtené backendem jako primární zdroj, analyzuj rovnou; neříkej uživateli, aby jejich obsah znovu vkládal.',
        '- U přiložených souborů vycházej z jejich skutečně dostupného obsahu. Pokud je k dispozici jen metadata, netvrď, že jsi soubor analyzoval.',
        '- U obrázků požaduj vision analýzu pouze pokud je obrazový obsah skutečně předán providerovi; jinak transparentně řekni, že je dostupné jen metadata.',
        '- Když najdeš použitelné řešení v jiném projektu, nabídni jeho znovupoužití a uveď zdroj; nepřenášej ho automaticky.',
        '- Karel má šetřit práci: jedno potvrzení konkrétního návrhu stačí. Po potvrzení už se na stejnou věc znovu neptej, ale proveď maximum bezpečné práce, ověř výsledek a odpověz stručně.',
    ]
    for rule in comm.get('rules', [])[:12]:
        lines.append(f'- {rule}')
    if selected:
        lines.append(f"- Doporučené workflow typu projektu „{selected.get('label','Projekt')}“: " + ' → '.join(selected.get('workflow', [])))
    if guidance.get('proactive'):
        lines.append('- Aktivně upozorni, když pro smysluplnou práci chybí důležitá část Projektové mapy, rozhodnutí nebo zdroj.')
    if guidance.get('ask_before_large_work') and missing:
        lines.append('- Před rozsáhlou revizí můžeš položit maximálně 2 konkrétní doplňující otázky, pokud bez nich hrozí špatný směr.')
        lines.append('- Chybějící pole Projektové mapy: ' + ', '.join(missing))
    if guidance.get('offer_save'):
        lines.append('- Když vznikne stabilní zadání, nabídni jeho uložení jako oddělené návrhy. Celý dlouhý text nikdy nevkládej do jediné položky.')
        lines.append('- Pokud máš dost informací pro doplnění Projektové mapy, připrav skrytý návrh v KAREL_STATE jako proposals/type=project_map. Uživatel ho musí potvrdit v UI.')
        lines.append('- Pokud jde o obecnou trvalou informaci nebo rozhodnutí, můžeš připravit proposals/type=memory. Bez potvrzení ji nepovažuj za schválenou.')
        lines.append('- Pokud vznikne opakovaně použitelná znalost, komponenta, postup nebo dokumentace, nabídni uložení do Knihovny účtu přes save_library_item.')
    return '\n'.join(lines)
