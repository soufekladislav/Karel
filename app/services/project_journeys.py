"""Truthful beginner journeys for a WordPress site or GitHub development project.

Presentation and data validation only. No WordPress or GitHub network calls,
no automatic approvals, writes, installations or deployments.
"""
from __future__ import annotations

from urllib.parse import urlsplit

WORDPRESS_TYPE = "WordPress / WooCommerce"
DEVELOPMENT_TYPE = "Vývoj aplikace / GitHub"
GENERAL_TYPE = "Jiný digitální projekt"

FRESH_CORE_PRODUCT_URL = "https://www.freshcrackers.cz/produkt/fresh-core/"
FRESH_CORE_SOURCE_URL = "https://github.com/soufekladislav/WP-Fresh-Core"


def selected_project_type(choice: str | None) -> str:
    """Only approved onboarding types may be written by the quick-create form."""
    choices = {
        "wordpress": WORDPRESS_TYPE,
        "github": DEVELOPMENT_TYPE,
        "general": GENERAL_TYPE,
    }
    return choices.get(str(choice or "").strip().lower(), GENERAL_TYPE)


def project_mode(project_type: str | None, *, github_linked: bool = False) -> str:
    value = str(project_type or "").strip().lower()
    if any(term in value for term in ("wordpress", "woocommerce", "wp web", "wp strán")):
        return "wordpress"
    if github_linked or any(term in value for term in (
            "github", "vývoj", "aplikace", "software", "saas", "program")):
        return "github"
    return "general"


def validate_site_url(value: str | None) -> str:
    """Save a user-declared URL, never fetch it or treat it as verified."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    if len(raw) > 300 or any(ord(ch) < 32 for ch in raw):
        raise ValueError("Adresa webu je příliš dlouhá nebo obsahuje nepovolené znaky.")
    candidate = raw if "://" in raw else "https://" + raw
    try:
        url = urlsplit(candidate)
        if url.scheme not in {"http", "https"} or not url.hostname:
            raise ValueError()
        if url.username or url.password or url.query or url.fragment:
            raise ValueError()
        if url.port not in (None, 80, 443):
            raise ValueError()
        if not all(c.isalnum() or c in "-." for c in url.hostname):
            raise ValueError()
        if "." not in url.hostname or url.hostname.startswith(".") or ".." in url.hostname:
            raise ValueError()
    except ValueError as exc:
        raise ValueError("Zadej veřejnou adresu webu, například mujweb.cz (bez přihlašovacích údajů).") from exc
    host = url.hostname.lower()
    if url.port and url.port != (443 if url.scheme == "https" else 80):
        host += ":" + str(url.port)
    return url.scheme + "://" + host + (url.path.rstrip("/") or "")


def journey_for_project(*, project_id: int, mode: str, github: dict,
                        has_business_goal: bool, has_site_url: bool,
                        can_import: bool = False) -> dict:
    """One understandable route. States are claims based on evidence, not clicks."""
    chat = f"/projects/{project_id}?view=chat"
    docs = f"/projects/{project_id}?view=docs"
    if mode == "wordpress":
        steps = [
            {"title": "Popsat svůj web", "body": "Uložili jsme webový projekt."
             + (" Adresu webu máme, ale ještě jsme ho neověřili." if has_site_url else
                " Doplň adresu webu, abychom věděli, co chceš spravovat."),
             "status": "done" if has_site_url else "next",
             "action": "Probrat web s Karlem", "href": chat + "&guide=wp-start"},
            {"title": "Získat a nainstalovat Fresh Core",
             "body": "Plugin umožní vybraným aplikacím Fresh bezpečně číst data webu. "
                     "Stažení je na stránce produktu, instalace probíhá ve WordPressu.",
             "status": "next", "action": "Otevřít Fresh Core",
             "href": FRESH_CORE_PRODUCT_URL},
            {"title": "Ověřit spojení a připravit plán",
             "body": "Propojení Karla s Fresh Core a automatické načtení stavu webu teprve dokončujeme. "
                     "Bez ověření neukazujeme data webu ani připojeno.",
             "status": "planned", "action": "Probrat cíl webu", "href": docs},
            {"title": "Schválit úpravu a ověřit výsledek",
             "body": "Návrhy úkolů lze připravovat. Odesílání změn na web a kontrola publikování "
                     "budou k dispozici až po ověřeném zápisovém konektoru.",
             "status": "planned", "action": "Připravit požadavek", "href": chat},
        ]
        return {
            "mode": mode, "name": "Můj WordPress web", "source_label": "Fresh Core",
            "headline": "Zvládneme správu webu srozumitelně, krok po kroku.",
            "detail": "Nejdřív si řekneme, co chceš změnit. Pak bezpečně propojíme WordPress a připravíme úkoly ke schválení.",
            "steps": steps, "action_label": "Pokračovat se správou webu",
            "action_url": f"/projects/{project_id}?view=website",
        }
    if mode == "github":
        state = github.get("kind", "unlinked")
        linked = state in ("pending", "error", "synced")
        synced = state == "synced"
        steps = [
            {"title": "Popsat nebo importovat projekt",
             "body": "Projekt je založen. Existující data se nepřepisují.",
             "status": "done", "action": "Otevřít zadání", "href": docs},
            {"title": "Připojit GitHub",
             "body": ("Repozitář je propojen." if linked else
                      "Repozitář zatím není propojen. Přístup k vlastnímu GitHub účtu budeme zpřístupňovat postupně."),
             "status": "done" if linked else "next",
             "action": "Otevřít GitHub",
             "href": f"/projects/{project_id}/github"},
            {"title": "Načíst skutečný stav",
             "body": ("Máme uložený časově označený snímek GitHubu; nejedná se o živou synchronizaci."
                      if synced else "Po úspěšném čtecím načtení uvidíš Issues, PR, CI a odkazy na původní zdroj."),
             "status": "done" if synced else "next" if linked else "planned",
             "action": "Zkontrolovat zdroje", "href": f"/projects/{project_id}/github"},
            {"title": "Navrhnout, schválit a otestovat práci",
             "body": "Karel dnes umí pomoci se zadáním a interními úkoly. "
                     "Zápisy do GitHubu, Codex worker a staging/produkční nasazení teprve připravujeme.",
             "status": "planned", "action": "Probrat první úkol", "href": chat},
        ]
        return {
            "mode": mode, "name": "Vývoj s GitHubem", "source_label": "GitHub",
            "headline": "Já pohlídám projekt. Ty rozhoduješ o změnách.",
            "detail": "Připojíme zdrojový kód, zjistíme stav a postupně převedeme zadání na malé schvalované úkoly.",
            "steps": steps, "action_label": "Otevřít GitHub projektu",
            "action_url": f"/projects/{project_id}/github",
        }
    return {
        "mode": "general", "name": "Můj digitální projekt",
        "source_label": "Podklady projektu",
        "headline": "Začni krátkým rozhovorem. Naplánujeme, co má smysl.",
        "detail": "Karel pomůže pojmenovat cíl, udržet rozhodnutí a zorganizovat další práci.",
        "steps": [
            {"title": "Popsat cíl", "body": "Jaký problém má projekt řešit?",
             "status": "done" if has_business_goal else "next",
             "action": "Probrat cíl", "href": chat},
            {"title": "Vybrat podklady a plán",
             "body": "Přidej dokumenty a souvislosti, potom společně vybereme další kroky.",
             "status": "next" if has_business_goal else "planned",
             "action": "Zadání a dokumentace", "href": docs},
            {"title": "Schvalovat a sledovat práci",
             "body": "Úkoly a návrhy změn zůstávají pod tvou kontrolou.",
             "status": "planned", "action": "Otevřít úkoly",
             "href": f"/projects/{project_id}?view=tasks"},
        ],
        "action_label": "Pokračovat v chatu", "action_url": chat,
    }
