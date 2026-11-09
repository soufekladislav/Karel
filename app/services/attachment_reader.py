"""Bounded, non-executing source extraction for chat attachments.

Archives are inspected in memory without unpacking to disk. Only a carefully
bounded selection of readable source files is passed into AI context.
"""
from __future__ import annotations
from pathlib import Path
from io import BytesIO
from xml.etree import ElementTree as ET
import csv
import json
import re
import zipfile

from .files import absolute_path, SAFE_TEXT_EXT

MAX_SOURCE_BYTES = 3 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 1200
MAX_ARCHIVE_UNCOMPRESSED = 35 * 1024 * 1024
MAX_PER_ENTRY = 128 * 1024
MAX_PER_FILE_CHARS = 16000
MAX_TOTAL_CONTEXT_CHARS = 28000
SKIP_PARTS = {'node_modules','.git','__pycache__','.venv','venv','vendor','dist','build','cache','.next','.idea','coverage','logs'}
SAFE_SUFFIXES = SAFE_TEXT_EXT | {'.toml','.env.example','.sh','.bash','.rst','.svg','.tsx','.jsx','.vue','.scss','.lock','.properties'}


_SECRETS = [
    re.compile(r'(?im)^(\s*(?:api[_-]?key|secret|password|access[_-]?token|private[_-]?key|database_url|db_password)\s*[:=]\s*)[^\n#]+'),
    re.compile(r'(?i)Bearer\s+[A-Za-z0-9._\-]{16,}'),
]

def _redact(s: str) -> str:
    s=_SECRETS[0].sub(lambda m: m.group(1)+'[REDACTED]',s)
    return _SECRETS[1].sub('Bearer [REDACTED]',s)


def _clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n] + f'\n[ZKRÁCENO: {len(s)} znaků]'


def _safe_name(name: str) -> bool:
    p = Path(name.replace('\\','/'))
    return (not p.is_absolute() and '..' not in p.parts
            and not any(part.lower() in SKIP_PARTS for part in p.parts)
            and not any(part.startswith('.') and part not in ('.env.example',) for part in p.parts))


def _read_zip_bytes(data: bytes) -> str:
    parts = []
    with zipfile.ZipFile(BytesIO(data)) as zf:
        entries = zf.infolist()
        if len(entries) > MAX_ARCHIVE_ENTRIES:
            raise ValueError(f'Archiv má {len(entries)} položek, limit je {MAX_ARCHIVE_ENTRIES}.')
        total = sum(max(0, x.file_size) for x in entries)
        if total > MAX_ARCHIVE_UNCOMPRESSED:
            raise ValueError('Archiv má příliš mnoho rozbalených dat. Analýza byla bezpečně zastavena.')
        names = [x.filename for x in entries if not x.is_dir() and _safe_name(x.filename)]
        parts.append(f'STRUKTURA ARCHIVU: {len(names)} vhodných souborů, {len(entries)} všech položek.\n' + '\n'.join(names[:220]))
        candidates=[]
        for item in entries:
            name = item.filename
            if item.is_dir() or not _safe_name(name) or item.file_size > MAX_PER_ENTRY:
                continue
            suffix = Path(name).suffix.lower()
            if suffix not in SAFE_SUFFIXES:
                continue
            depth = len(Path(name).parts)
            bonus = 5 if Path(name).name.lower() in {'readme.md','requirements.txt','pyproject.toml','package.json','composer.json','manifest.json','main.py','app.py','index.php'} else 0
            candidates.append((-(bonus - depth), item))
        candidates.sort(key=lambda t: (t[0], t[1].filename))
        remaining = MAX_TOTAL_CONTEXT_CHARS - len(parts[0])
        read_count=0
        for _, item in candidates:
            if remaining < 400 or read_count >= 30:
                break
            with zf.open(item) as f:
                raw=f.read(MAX_PER_ENTRY + 1)
            text=raw[:MAX_PER_ENTRY].decode('utf-8', errors='replace')
            if not text.strip():
                continue
            piece=f'\nSOUBOR: {item.filename}\n' + _clip(text, min(MAX_PER_FILE_CHARS, remaining-120))
            parts.append(piece)
            remaining-=len(piece)
            read_count+=1
        parts.append(f'\nPřečteno {read_count} textových souborů z archivu; další obsah může vyžadovat cílené načtení. Nespouštěl se žádný kód.')
    return '\n'.join(parts)


def _read_docx(data: bytes) -> str:
    with zipfile.ZipFile(BytesIO(data)) as zf:
        if 'word/document.xml' not in zf.namelist():
            raise ValueError('DOCX neobsahuje word/document.xml.')
        xml=zf.read('word/document.xml')
    root=ET.fromstring(xml)
    ns='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    paras=[]
    for p in root.iter(ns+'p'):
        s=''.join(t.text or '' for t in p.iter(ns+'t'))
        if s.strip(): paras.append(s)
    return _clip('\n'.join(paras),MAX_TOTAL_CONTEXT_CHARS)


def _read_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise ValueError('Pro čtení PDF chybí závislost pypdf. Nainstaluj requirements.txt.') from e
    reader=PdfReader(BytesIO(data))
    output=[]
    for i,page in enumerate(reader.pages[:25]):
        txt=(page.extract_text() or '').strip()
        if txt: output.append(f'[strana {i+1}]\n'+txt)
        if sum(map(len,output))>MAX_TOTAL_CONTEXT_CHARS: break
    if not output: raise ValueError('PDF neobsahuje extrahovatelný text (pravděpodobně sken nebo obrázky).')
    return _clip('\n\n'.join(output),MAX_TOTAL_CONTEXT_CHARS)


def extract_attachment(pf) -> dict:
    """Return structured, explicit extraction result; never silently claim a file was read."""
    name=(pf.name or 'soubor')[:255]
    try:
        path=absolute_path(pf.stored_name)
        if not path.is_file(): raise ValueError('Uložený soubor neexistuje.')
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError('Soubor je větší než limit pro jednorázovou analýzu 3 MB.')
        data=path.read_bytes()
        ext=Path(name).suffix.lower()
        if ext == '.zip': text=_read_zip_bytes(data)
        elif ext == '.pdf': text=_read_pdf(data)
        elif ext == '.docx': text=_read_docx(data)
        elif ext in SAFE_SUFFIXES: text=data.decode('utf-8',errors='replace')
        else: raise ValueError(f'Typ {ext or "bez přípony"} není podporovaný pro obsahovou analýzu.')
        return {'file_id':pf.id,'name':name,'ok':True,'content':_clip(_redact(text),MAX_TOTAL_CONTEXT_CHARS),'error':None}
    except (ValueError,OSError,zipfile.BadZipFile,ET.ParseError) as exc:
        return {'file_id':pf.id,'name':name,'ok':False,'content':'','error':str(exc)[:350]}


def attachments_context(files: list) -> tuple[str,list[dict]]:
    results=[extract_attachment(pf) for pf in files]
    blocks=[]
    remaining=MAX_TOTAL_CONTEXT_CHARS
    for r in results:
        if not r['ok']:
            blocks.append(f"PŘÍLOHA {r['name']}: NEPŘEČTENA – {r['error']}")
            continue
        intro=f"PŘÍLOHA {r['name']} (FILE-{r['file_id']}; skutečně extrahovaný obsah):\n"
        budget=max(0,remaining-len(intro))
        content=_clip(r['content'],budget) if budget else '[Obsah se nevešel do limitu kontextu]'
        blocks.append(intro+content)
        remaining-=len(intro)+len(content)
    return '\n\n'.join(blocks),results
