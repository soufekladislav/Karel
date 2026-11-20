"""Redacted, read-only security posture report for the superadmin UI.

This is not a penetration test, a backup test, or proof of production safety.
Never include actual secrets, environment variables, customer data or file paths.
"""
from datetime import datetime, timezone


def collect_security_checks(settings, bootstrap_state: dict) -> dict:
    secret = str(settings.secret or '')
    secret_ok = len(secret) >= 32 and secret not in ('change-me', 'CHANGE_ME_TO_A_LONG_RANDOM_SECRET')
    checks = [
        {
            'id': 'production-mode',
            'label': 'Režim produkčního prostředí',
            'state': 'ok' if settings.environment == 'production' else 'warning',
            'detail': 'Produkční bezpečnostní podmínky jsou vynuceny.' if settings.environment == 'production' else 'Na serveru nastav KAREL_ENV=production.',
        },
        {
            'id': 'source-hosts',
            'label': 'Povolené webové zdroje chatu',
            'state': 'ok' if settings.source_allowed_hosts else 'unverified',
            'detail': 'Povolené domény jsou nakonfigurovány.' if settings.source_allowed_hosts else 'Externí webové zdroje zůstanou vypnuté, dokud nenastavíš SOURCE_ALLOWED_HOSTS.',
        },
        {
            'id': 'session-secret',
            'label': 'Ochrana přihlašovacích relací',
            'state': 'ok' if secret_ok else 'warning',
            'detail': 'Silný tajný klíč je nakonfigurován.' if secret_ok else 'APP_SECRET je příliš krátký nebo používá výchozí hodnotu.',
        },
        {
            'id': 'https-session',
            'label': 'Přístupové cookies přes HTTPS',
            'state': 'ok' if settings.https_only else 'warning',
            'detail': 'Přihlašovací cookies jsou omezené na HTTPS.' if settings.https_only else 'SESSION_HTTPS_ONLY není zapnuto.',
        },
        {
            'id': 'fresh-core-read',
            'label': 'Fresh Core – čtecí konektor',
            'state': 'ok' if (getattr(settings,'fresh_core_vault_key','')
                              and getattr(settings,'fresh_core_allowed_hosts','')) else 'unverified',
            'detail': 'Šifrovací vault a seznam povolených WordPress hostitelů jsou nakonfigurovány; toto není živý test webu.'
                      if (getattr(settings,'fresh_core_vault_key','')
                          and getattr(settings,'fresh_core_allowed_hosts',''))
                      else 'Pro bezpečné připojení WordPressu nastav FRESH_CORE_VAULT_KEY a FRESH_CORE_ALLOWED_HOSTS.',
        },
        {
            'id': 'manifest-hosts',
            'label': 'Důvěryhodné zdroje manifestů',
            'state': 'ok' if settings.manifest_allowed_hosts else 'warning',
            'detail': 'Seznam povolených hostitelů je vyplněn.' if settings.manifest_allowed_hosts else 'Žádné externí manifesty nejsou povoleny.',
        },
        {
            'id': 'db-initialization',
            'label': 'Základní stav databáze',
            'state': 'ok' if bootstrap_state.get('database') and bootstrap_state.get('schema') else 'warning',
            'detail': 'Spojení a základní struktura databáze byly inicializovány.' if bootstrap_state.get('database') and bootstrap_state.get('schema') else 'Inicializace databáze nebo její struktury hlásí problém.',
        },
        {
            'id': 'external-audit',
            'label': 'Zálohy, veřejná Git historie a přístup z internetu',
            'state': 'unverified',
            'detail': 'Vyžaduje samostatnou kontrolu serveru a repozitáře; automatická kontrola nastavení to nepotvrzuje.',
        },
    ]
    return {'checked_at': datetime.now(timezone.utc).isoformat(), 'checks': checks,
            'scope': 'Pouze read-only kontrola části konfigurace aplikace; není to potvrzení bezpečnosti produkce.'}
