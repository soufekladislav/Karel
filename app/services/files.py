from pathlib import Path
from uuid import uuid4
import shutil, zipfile
from fastapi import UploadFile
from ..config import settings

SAFE_TEXT_EXT = {'.txt','.md','.json','.yaml','.yml','.xml','.csv','.py','.php','.js','.ts','.css','.html','.htm','.sql','.ini','.conf','.log'}

def save_upload(upload: UploadFile, project_id: int) -> tuple[str,int]:
    folder = settings.uploads_dir / str(project_id)
    folder.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or '').suffix[:20]
    stored = f'{uuid4().hex}{suffix}'
    path = folder / stored
    total = 0
    with path.open('wb') as f:
        while True:
            chunk = upload.file.read(1024*1024)
            if not chunk:
                break
            total += len(chunk)
            if total > settings.max_upload_mb * 1024 * 1024:
                f.close(); path.unlink(missing_ok=True)
                raise ValueError(f'Soubor je větší než limit {settings.max_upload_mb} MB.')
            f.write(chunk)
    return f'{project_id}/{stored}', total

def absolute_path(stored_name: str) -> Path:
    p = (settings.uploads_dir / stored_name).resolve()
    if settings.uploads_dir.resolve() not in p.parents:
        raise ValueError('Neplatná cesta souboru.')
    return p

def create_bundle(project_id: int, files: list, output_name: str='project-files.zip') -> tuple[Path,int]:
    folder = settings.uploads_dir / str(project_id)
    folder.mkdir(parents=True, exist_ok=True)
    clean = ''.join(c for c in output_name if c.isalnum() or c in '._-') or 'project-files.zip'
    if not clean.endswith('.zip'): clean += '.zip'
    target = folder / f'{uuid4().hex}_{clean}'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as zf:
        used = set()
        for pf in files:
            src = absolute_path(pf.stored_name)
            if not src.exists(): continue
            name = pf.name
            if name in used:
                name = f'{pf.id}_{name}'
            used.add(name)
            zf.write(src, name)
    return target, target.stat().st_size


def save_library_upload(upload: UploadFile, user_id: int) -> tuple[str,int]:
    root = settings.storage_dir / 'library'
    folder = root / str(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or '').suffix[:20]
    stored = f'{uuid4().hex}{suffix}'
    path = folder / stored
    total = 0
    with path.open('wb') as f:
        while True:
            chunk = upload.file.read(1024*1024)
            if not chunk:
                break
            total += len(chunk)
            if total > settings.max_upload_mb * 1024 * 1024:
                f.close(); path.unlink(missing_ok=True)
                raise ValueError(f'Soubor je větší než limit {settings.max_upload_mb} MB.')
            f.write(chunk)
    return f'{user_id}/{stored}', total

def absolute_library_path(stored_name: str) -> Path:
    root = (settings.storage_dir / 'library').resolve()
    p = (root / stored_name).resolve()
    if root != p and root not in p.parents:
        raise ValueError('Neplatná cesta souboru knihovny.')
    return p
