"""Explicit safe continuation for unfinished model responses.

A continuation is a new assistant message, not a data-write operation. Its
request is built from the latest response, preserving the user's original
intent without duplicating all the project specification in the prompt.
"""
import re

TRAILING_PUNCTUATION = re.compile(r'[.!?…:;»"\)\]]\s*$')


def likely_truncated(text: str) -> bool:
    text = (text or '').strip()
    if not text or text.startswith('[[ENGINE_UNAVAILABLE]]'):
        return False
    if re.search(r'<KAREL_STATE>', text, re.I) and not re.search(r'</KAREL_STATE>', text, re.I):
        return True
    # A long answer ending mid-sentence (without conventional punctuation)
    # is a useful hint but not proof of a server-side output limit.
    if len(text) > 400 and not TRAILING_PUNCTUATION.search(text):
        return True
    if text.count('```') % 2:
        return True
    return False


def continuation_request(previous: str) -> str:
    excerpt = (previous or '')[-2600:]
    return (
        'Navazuj na POSLEDNÍ rozepsanou odpověď, nikoli na celý původní dokument. '
        'Pokračuj přesně od místa, kde skončila, neopakuj už uvedené části. '
        'Dokonči jen aktuální téma a zakonči souvislou větou. '
        'Pokud bylo zadání rozsáhlé, místo dalšího dlouhého výpisu nabídni strukturovaný návrh '
        'a polož jednu nejdůležitější otázku. '
        'Není to souhlas se zápisem: neprováděj, nevytvářej ani nenavrhuj KAREL_STATE akce. '
        'POSLEDNÍ ČÁST PŘEDCHOZÍ ODPOVĚDI:\n' + excerpt
    )
