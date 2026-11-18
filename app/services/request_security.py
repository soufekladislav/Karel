"""Request-origin checks for browser mutation routes (CSRF baseline).

Cookies are SameSite=Lax, but same-site subdomains and older clients still
need protection. Only the canonical APP_URL origin may submit forms.

This is deliberately framework-independent and never trusts X-Forwarded-*.
"""
from urllib.parse import urlsplit


def _normalized_origin(raw: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlsplit(str(raw or '').strip())
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            return None
        if parsed.username or parsed.password:
            return None
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        return parsed.scheme, parsed.hostname.lower().rstrip('.'), port
    except ValueError:
        return None


def allow_browser_mutation(headers, app_url: str) -> bool:
    """Deny cross-origin POSTs, including same-site *other subdomains*.

    Accept verified Origin, or Referrer, or an explicit Fetch Metadata header
    'same-origin' for privacy-sensitive user agents that suppress both. Reject
    requests with no provenance signal. Machine clients need a dedicated API
    with bearer auth; session-bearing HTML mutations must originate in-browser.
    """
    expected = _normalized_origin(app_url)
    if not expected:
        return False

    fetch_site = (headers.get('sec-fetch-site') or '').strip().lower()
    if fetch_site in ('cross-site', 'same-site'):
        return False

    origin = (headers.get('origin') or '').strip()
    referer = (headers.get('referer') or '').strip()
    if origin and _normalized_origin(origin) != expected:
        return False
    if referer and _normalized_origin(referer) != expected:
        return False

    if origin or referer:
        return True
    return fetch_site == 'same-origin'


def secure_production_configuration(app_url: str, secret: str, https_only: bool) -> bool:
    """True only when a HTTPS deployment has viable session settings."""
    origin = _normalized_origin(app_url)
    if not origin or origin[0] != 'https':
        return False
    forbidden = {'change-me', 'CHANGE_ME_TO_A_LONG_RANDOM_SECRET', 'secret', 'test'}
    return (len(secret or '') >= 32 and (secret or '') not in forbidden and https_only)
