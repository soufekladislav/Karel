import json
import asyncio
import httpx
from ..config import settings

class EngineError(RuntimeError):
    pass

async def _request_with_retry(method: str, url: str, *, headers: dict, json_body=None, timeout=30):
    retry_statuses = {429, 502, 503, 504}
    last_response = None
    last_error = None
    attempts = max(1, int(getattr(settings, 'engine_retries', 3)))
    for attempt in range(attempts):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if method == 'GET':
                    response = await client.get(url, headers=headers)
                else:
                    response = await client.post(url, headers=headers, json=json_body)
            last_response = response
            if response.status_code not in retry_statuses or attempt == attempts - 1:
                return response
        except Exception as exc:
            last_error = exc
            if attempt == attempts - 1:
                raise
        await asyncio.sleep(min(0.8 * (2 ** attempt), 3.0))
    if last_response is not None:
        return last_response
    raise last_error or RuntimeError('Fresh AI Engine není dostupný.')

def _safe_http_detail(response: httpx.Response) -> str:
    content_type = (response.headers.get('content-type') or '').lower()
    if 'text/html' in content_type or '<html' in (response.text or '')[:300].lower():
        return f'HTTP {response.status_code} – služba je dočasně nedostupná.'
    try:
        data = response.json()
        if isinstance(data, dict):
            msg = data.get('detail') or data.get('message') or data.get('error')
            if isinstance(msg, str) and msg.strip():
                return f'HTTP {response.status_code}: {msg[:300]}'
    except Exception:
        pass
    text = (response.text or '').strip().replace('\n', ' ')
    return f'HTTP {response.status_code}' + (f': {text[:300]}' if text else '')

async def health() -> tuple[bool, str]:
    if not settings.engine_url:
        return False, 'Fresh AI Engine není nakonfigurovaný.'
    url = settings.engine_url + settings.engine_health_path
    headers = {'Authorization': f'Bearer {settings.engine_api_key}'} if settings.engine_api_key else {}
    try:
        r = await _request_with_retry('GET', url, headers=headers, timeout=15)
        return r.is_success, ('Online' if r.is_success else _safe_http_detail(r))
    except Exception as e:
        return False, f'Služba není dostupná: {type(e).__name__}'

async def chat(system_prompt: str, user_text: str, attachments: list[dict] | None = None) -> str:
    if not settings.engine_url:
        raise EngineError('Fresh AI Engine není nastavený.')
    url = settings.engine_url + settings.engine_chat_path
    headers = {'Content-Type': 'application/json'}
    if settings.engine_api_key:
        headers['Authorization'] = f'Bearer {settings.engine_api_key}'

    attachment_note = ''
    if attachments:
        attachment_note = '\n\nPřiložené soubory:\n' + '\n'.join(
            f"- {a.get('name')} ({a.get('mime_type') or 'soubor'}, {a.get('size_bytes',0)} B)" for a in attachments
        )
    full_user = user_text + attachment_note

    if settings.engine_mode == 'fresh':
        payload = {
            'source': 'karel',
            'task_type': 'development_chat',
            'quality': 'balanced',
            'prompt': full_user,
            'context': {
                'system_prompt': system_prompt,
                'assistant': 'karel',
                'attachments': attachments or [],
                'client': 'karel-2'
            }
        }
    else:
        payload = {
            'model': settings.engine_model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': full_user}
            ]
        }

    try:
        r = await _request_with_retry('POST', url, headers=headers, json_body=payload, timeout=settings.engine_timeout)
    except Exception as e:
        raise EngineError(f'AI služba není dostupná ({type(e).__name__}).')
    if not r.is_success:
        raise EngineError(_safe_http_detail(r))
    try:
        data = r.json()
    except Exception:
        return r.text

    if isinstance(data, dict):
        choices = data.get('choices')
        if choices and isinstance(choices, list):
            msg = (choices[0] or {}).get('message') or {}
            if isinstance(msg, dict) and msg.get('content'):
                return str(msg['content'])
        for key in ('reply','message','content','text','output'):
            if isinstance(data.get(key), str):
                return data[key]
        if isinstance(data.get('data'), dict):
            for key in ('reply','message','content','text','output'):
                if isinstance(data['data'].get(key), str):
                    return data['data'][key]
    return json.dumps(data, ensure_ascii=False)
