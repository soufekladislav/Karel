from pathlib import Path
from datetime import datetime
import mimetypes
import os
import json
import shutil
import platform
import hashlib
import html
import re
import httpx
from urllib.parse import quote
from fastapi import FastAPI, Request, Form, UploadFile, File, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import select, or_, func

from .config import settings
from .database import Base, engine, get_db, SessionLocal
from .models import User, Project, ProjectMember, ProjectInvitation, Chat, Message, Task, ProjectFile, ProjectMemory, ProjectEvent, LibraryItem, ProjectStage
from .auth import hash_password, verify_password, current_user
from .services.context_builder import build_context
from .services.orchestrator import orchestrate
from .services.write_planner import plan_write_request, is_complex_project_brief
from .services.engine import chat as engine_chat, health as engine_health, EngineError
from .services.continuation import likely_truncated, continuation_request
from .services.source_resolver import resolve_message_sources
from .services.app_manifest import build_app_manifest
from .services.brain import load_brain, save_brain
from .services.state_parser import apply_state
from .services.actions import execute_pending_action, dismiss_pending_action, parse_pending, pending_group, execute_pending_group, dismiss_pending_for_chat, choose_pending_field
from .services.files import save_upload, absolute_path, create_bundle, save_library_upload, absolute_library_path
from .services.attachment_reader import attachments_context
from .services import fresh_key
from .services.workflow import get_stages, alerts as workflow_alerts, context as workflow_context, STATUSES as STAGE_STATUSES
from .bootstrap import initialize_app, bootstrap_state

app = FastAPI(title='Karel 2.0')
app.add_middleware(SessionMiddleware, secret_key=settings.secret, https_only=settings.https_only, same_site='lax')
BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / 'templates'))
app.mount('/static', StaticFiles(directory=str(BASE / 'static')), name='static')

def render_message_text(value):
    text=str(value or '')
    escaped=html.escape(text)
    blocks=[]
    def code_repl(m):
        idx=len(blocks); blocks.append(m.group(1)); return f'@@CODE{idx}@@'
    escaped=re.sub(r'```(?:[a-zA-Z0-9_+-]+)?\n?(.*?)```', code_repl, escaped, flags=re.S)
    lines=escaped.splitlines()
    out=[]; in_list=False
    for line in lines:
        if line.startswith('### '):
            if in_list: out.append('</ul>'); in_list=False
            out.append(f'<h4>{line[4:]}</h4>')
        elif line.startswith('## '):
            if in_list: out.append('</ul>'); in_list=False
            out.append(f'<h3>{line[3:]}</h3>')
        elif line.startswith('# '):
            if in_list: out.append('</ul>'); in_list=False
            out.append(f'<h3>{line[2:]}</h3>')
        elif line.startswith('- '):
            if not in_list: out.append('<ul>'); in_list=True
            out.append(f'<li>{line[2:]}</li>')
        elif not line.strip():
            if in_list: out.append('</ul>'); in_list=False
        else:
            if in_list: out.append('</ul>'); in_list=False
            line=re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
            line=re.sub(r'`([^`]+)`', r'<code>\1</code>', line)
            out.append(f'<p>{line}</p>')
    if in_list: out.append('</ul>')
    rendered=''.join(out)
    for i,code in enumerate(blocks):
        rendered=rendered.replace(f'@@CODE{i}@@', f'<pre><code>{code}</code></pre>')
    return rendered

templates.env.filters['message_md'] = render_message_text

STATUS_LABELS = {'todo':'Nezahájeno','working':'Ve vývoji','waiting_user':'Čeká na uživatele','testing':'V testování','done':'Dokončeno','failed':'Chyba','archived':'Archivováno'}
APP_VERSION = '2.0.0-alpha.29'


PROJECT_SPEC_KINDS = {
    'purpose': 'Účel projektu',
    'project_type': 'Typ projektu',
    'business_goal': 'Obchodní cíl',
    'functional_goal': 'Hlavní funkce / zadání',
    'project_scope': 'Rozsah projektu',
    'project_deadline': 'Cílový termín',
    'project_plan': 'Plán projektu',
}

def project_spec(db, project_id):
    rows=db.scalars(select(ProjectMemory).where(ProjectMemory.project_id==project_id, ProjectMemory.kind.in_(list(PROJECT_SPEC_KINDS.keys()))).order_by(ProjectMemory.id.desc())).all()
    data={}
    for row in rows:
        if row.kind not in data:
            data[row.kind]=row.content or ''
    return data

def save_project_spec_value(db, project_id, kind, value):
    if kind not in PROJECT_SPEC_KINDS:
        return
    row=db.scalar(select(ProjectMemory).where(ProjectMemory.project_id==project_id, ProjectMemory.kind==kind).order_by(ProjectMemory.id.desc()))
    value=(value or '').strip()
    if row:
        row.title=PROJECT_SPEC_KINDS[kind]; row.content=value; row.verified=True
    elif value:
        db.add(ProjectMemory(project_id=project_id,kind=kind,title=PROJECT_SPEC_KINDS[kind],content=value,verified=True))

def is_superadmin(user):
    return bool(user and (user.role == 'superadmin' or str(user.email or '').strip().lower() == settings.superadmin_email))

def is_confirmation_message(text: str) -> bool:
    value=(text or '').strip().lower()
    if not value:
        return False
    if any(x in value for x in ['nepotvrzuji','nepotvrzuju','neprováděj','neprovadej','nezapisuj','neukládej','neukladej','zamítám','zamitam']):
        return False
    compact=re.sub(r'[^a-zá-ž0-9 ]+',' ',value)
    compact=re.sub(r'\s+',' ',compact).strip()
    patterns=(
        r'^(ano|jo|souhlasím|souhlasim|potvrzuji|potvrzuju|potvrzeno)( .*)?$',
        r'^(zapiš|zapis|ulož|uloz|proveď|proved|udělej to|udelej to|můžeš uložit|muzes ulozit|můžeš zapsat|muzes zapsat)( .*)?$',
        r'^(ano|jo|souhlasím|souhlasim|potvrzuji|potvrzuju).*(zapiš|zapis|ulož|uloz|proveď|proved|udělej|udelej)',
    )
    return any(re.search(p,compact) for p in patterns)


def action_result_text(batch: dict) -> str:
    results=batch.get('results') or []
    errors=batch.get('errors') or []
    if results and not errors:
        if len(results)==1:
            r=results[0]; typ=r.get('type')
            labels={
                'update_project':'Projekt byl upraven.',
                'update_project_map':'Projektová mapa byla aktualizována.',
                'create_task':'Úkol byl vytvořen.',
                'update_task':'Úkol byl upraven.',
                'archive_task':'Úkol byl archivován.',
                'delete_task':'Úkol byl smazán.',
                'save_decision':'Rozhodnutí bylo uloženo.',
                'save_note':'Poznámka byla uložena.',
                'save_library_item':'Položka byla uložena do Knihovny účtu.',
                'update_library_item':'Položka Knihovny účtu byla upravena.',
            }
            return '✓ '+labels.get(typ,'Změna byla provedena a ověřena.')
        return f'✓ Hotovo. Provedl jsem a ověřil {len(results)} navržených změn.'
    if results and errors:
        return f'Částečně hotovo: provedl jsem {len(results)} změn, {len(errors)} se nepodařilo dokončit. Zbytek jsem ponechal beze změny.'
    if errors:
        return 'Změnu se nepodařilo provést: '+str(errors[0].get('error') or 'neznámá chyba')
    return 'Nebylo co provést.'


# Passenger/WSGI does not reliably run ASGI lifespan events. Initialize once at import
# and repeat on native ASGI startup (idempotent). This makes a brand-new empty DB usable.
initialize_app()

@app.on_event('startup')
def startup():
    initialize_app()

@app.get('/healthz')
def healthz():
    state = bootstrap_state()
    status = 200 if state.get('ok') else 503
    return JSONResponse({
        'app': settings.app_name,
        'version': APP_VERSION,
        'ok': bool(state.get('ok')),
        'database': bool(state.get('database')),
        'schema': bool(state.get('schema')),
        'admin_seeded': bool(state.get('admin')),
        'error': state.get('error'),
    }, status_code=status)

def ctx(request, user=None, **extra):
    # One project switcher is available in the same sidebar on every authenticated page.
    sidebar_projects = []
    if user is not None:
        with SessionLocal() as sidebar_db:
            sidebar_projects = sidebar_db.scalars(
                select(Project).where(or_(
                    Project.owner_id == user.id,
                    Project.id.in_(select(ProjectMember.project_id).where(ProjectMember.user_id == user.id))
                )).order_by(Project.name)
            ).all()
    return {'request': request, 'user': user, 'app_name': settings.app_name,
            'status_labels': STATUS_LABELS, 'sidebar_projects': sidebar_projects, **extra}

def require_user(request: Request, db: Session):
    u = current_user(request, db)
    if not u:
        raise HTTPException(401)
    return u

ROLE_LABELS = {"owner":"Vlastník", "manager":"Správce", "editor":"Editor", "viewer":"Čtenář"}
RELATIONSHIP_LABELS = {"member":"Člen týmu", "client":"Klient", "agency":"Agentura"}

def normalize_access_role(value):
    role = str(value or "").strip().lower()
    role = {"member":"editor", "client":"editor", "agency":"editor", "reader":"viewer", "visitor":"viewer"}.get(role, role)
    return role if role in ROLE_LABELS else "viewer"

def normalize_relationship(value):
    rel = str(value or "member").strip().lower()
    return rel if rel in RELATIONSHIP_LABELS else "member"

def project_role(db, user, project):
    if project.owner_id == user.id:
        return "owner"
    if user.role == "superadmin":
        return "manager"
    row = db.scalar(select(ProjectMember).where(ProjectMember.project_id==project.id, ProjectMember.user_id==user.id))
    return normalize_access_role(row.role) if row else ""

def can_access(db, user, project):
    return bool(project_role(db, user, project))

def can_edit_project(db, user, project):
    return project_role(db, user, project) in {"owner", "manager", "editor"}

def can_manage_project(db, user, project):
    return project_role(db, user, project) in {"owner", "manager"}

def get_project_or_404(db, user, project_id, *, write=False, manage=False):
    p = db.get(Project, project_id)
    if not p or not can_access(db,user,p):
        raise HTTPException(404)
    if manage and not can_manage_project(db,user,p):
        raise HTTPException(403, "Sdílení a Fresh Key může spravovat pouze Vlastník nebo Správce projektu.")
    if write and not can_edit_project(db,user,p):
        raise HTTPException(403, "Čtenář může projekt pouze prohlížet; nemůže upravovat ani schvalovat.")
    return p

def project_people(db, project):
    people=[]
    owner=db.get(User, project.owner_id)
    if owner:
        people.append({"kind":"owner","user_id":owner.id,"email":owner.email,"name":owner.name or owner.email,"role":"owner","role_label":"Vlastník","relationship":"member","relationship_label":"Člen týmu","status":"active"})
    members=db.scalars(select(ProjectMember).where(ProjectMember.project_id==project.id).order_by(ProjectMember.id)).all()
    for row in members:
        u=db.get(User,row.user_id)
        if not u or (owner and u.id==owner.id): continue
        role=normalize_access_role(row.role); rel=normalize_relationship(getattr(row,"relationship","member"))
        people.append({"kind":"member","user_id":u.id,"email":u.email,"name":u.name or u.email,"role":role,"role_label":ROLE_LABELS[role],"relationship":rel,"relationship_label":RELATIONSHIP_LABELS[rel],"status":"active"})
    invites=db.scalars(select(ProjectInvitation).where(ProjectInvitation.project_id==project.id, ProjectInvitation.status=="pending").order_by(ProjectInvitation.id)).all()
    known={str(x["email"]).lower() for x in people}
    for row in invites:
        if row.email.lower() in known: continue
        role=normalize_access_role(row.role); rel=normalize_relationship(row.relationship)
        people.append({"kind":"invitation","user_id":None,"email":row.email,"name":row.email,"role":role,"role_label":ROLE_LABELS[role],"relationship":rel,"relationship_label":RELATIONSHIP_LABELS[rel],"status":"pending"})
    return people

def accept_local_invitations(db, user):
    email=str(user.email or "").strip().lower()
    if not email: return 0
    invitations=db.scalars(select(ProjectInvitation).where(func.lower(ProjectInvitation.email)==email, ProjectInvitation.status=="pending")).all()
    count=0
    for inv in invitations:
        row=db.scalar(select(ProjectMember).where(ProjectMember.project_id==inv.project_id, ProjectMember.user_id==user.id))
        if not row:
            db.add(ProjectMember(project_id=inv.project_id,user_id=user.id,role=normalize_access_role(inv.role),relationship=normalize_relationship(inv.relationship)))
        else:
            row.role=normalize_access_role(inv.role); row.relationship=normalize_relationship(inv.relationship)
        inv.status="accepted"; inv.updated_at=datetime.utcnow(); count+=1
    if count: db.commit()
    return count

def project_link_state(user, project, role):
    if not fresh_key.configured():
        return {"linked":False,"applications":[],"members":[],"manage_url":settings.engine_url.rstrip("/")+"/account/fresh-key" if settings.engine_url else "https://aiengine.freshcrackers.cz/account/fresh-key"}, "Fresh Key není nakonfigurován.", []
    try:
        summary=fresh_key.project_summary(user, project, role=role or "viewer")
        requests=[x for x in fresh_key.pending_link_requests(user) if str(x.get("target_external_project_id") or "") == str(project.id)]
        return summary, "", requests
    except Exception as exc:
        return {"linked":False,"applications":[],"members":[],"manage_url":fresh_key.manage_url()}, str(exc), []

def redirect_project(project_id, notice="", error=""):
    q=[]
    if notice: q.append("notice="+quote(notice))
    if error: q.append("error="+quote(error))
    return RedirectResponse(f"/projects/{project_id}" + (("?"+"&".join(q)) if q else ""), 303)

@app.exception_handler(401)
def auth_required(request, exc):
    return RedirectResponse('/login', status_code=303)

@app.get('/login', response_class=HTMLResponse)
def login_page(request: Request, db: Session=Depends(get_db)):
    if current_user(request, db): return RedirectResponse('/',303)
    return templates.TemplateResponse('login.html', ctx(request))

@app.post('/login')
def login(request: Request, email: str=Form(...), password: str=Form(...), db: Session=Depends(get_db)):
    u = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not u or not verify_password(password, u.password_hash):
        return templates.TemplateResponse('login.html', ctx(request, error='E-mail nebo heslo nesedí.'), status_code=400)
    request.session['user_id'] = u.id
    accept_local_invitations(db, u)
    if fresh_key.configured():
        try: fresh_key.bootstrap_account(u)
        except Exception: pass
    return RedirectResponse('/',303)

@app.get('/logout')
def logout(request: Request):
    request.session.clear(); return RedirectResponse('/login',303)

@app.get('/', response_class=HTMLResponse)
def dashboard(request: Request, db: Session=Depends(get_db)):
    u = require_user(request, db)
    q = select(Project).where(or_(Project.owner_id==u.id, Project.id.in_(select(ProjectMember.project_id).where(ProjectMember.user_id==u.id)))).order_by(Project.updated_at.desc(), Project.id.desc())
    all_projects = db.scalars(q).all()
    projects = [p for p in all_projects if (p.status or 'active') != 'archived']
    archived_projects = [p for p in all_projects if (p.status or 'active') == 'archived']
    dashboard_projects=[]
    deadline_alerts=[]
    for p in projects:
        spec=project_spec(db,p.id)
        for warning in workflow_alerts(get_stages(db,p.id)):
            deadline_alerts.append({'project':p,'message':warning['text'],'days':warning['days']})
        counts={status: db.scalar(select(func.count(Task.id)).where(Task.project_id==p.id, Task.status==status)) or 0 for status in STATUS_LABELS}
        dashboard_projects.append({'project':p,'spec':spec,'counts':counts,'open':counts['todo']+counts['working']+counts['waiting_user']+counts['testing']+counts['failed']})
    deadline_alerts.sort(key=lambda x:x['days'])
    dashboard_totals={'open':sum(x['open'] for x in dashboard_projects),'testing':sum(x['counts'].get('testing',0) for x in dashboard_projects)}
    fresh_requests=[]; fresh_error=''
    if fresh_key.configured():
        try:
            fresh_key.bootstrap_account(u)
            fresh_requests=fresh_key.pending_link_requests(u)
        except Exception as exc:
            fresh_error=str(exc)
    return templates.TemplateResponse('dashboard.html', ctx(request,u,projects=projects,archived_projects=archived_projects,dashboard_projects=dashboard_projects,dashboard_totals=dashboard_totals,deadline_alerts=deadline_alerts[:15],fresh_key_requests=fresh_requests,fresh_key_error=fresh_error))

@app.post('/projects')
def create_project(request: Request, name: str=Form(...), description: str=Form(''), db: Session=Depends(get_db)):
    u=require_user(request,db)
    p=Project(owner_id=u.id,name=name.strip(),description=description.strip() or None,updated_at=datetime.utcnow())
    db.add(p); db.flush()
    c=Chat(project_id=p.id,title='Hlavní chat')
    db.add(c); db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='project_created',detail='Projekt vytvořen.'))
    db.commit(); return RedirectResponse(f'/projects/{p.id}',303)

@app.get('/projects/{project_id}', response_class=HTMLResponse)
def project_view(request: Request, project_id: int, chat_id: int|None=None, view: str='chat', db: Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id)
    allowed_views={'chat','tasks','development','outputs','history','files','settings','docs','components','releases','testing'}
    if view not in allowed_views: view='chat'
    selectable_projects=db.scalars(select(Project).where(or_(Project.owner_id==u.id, Project.id.in_(select(ProjectMember.project_id).where(ProjectMember.user_id==u.id)))).order_by(Project.name)).all()
    chats=db.scalars(select(Chat).where(Chat.project_id==p.id, Chat.is_archived==False).order_by(Chat.updated_at.desc(), Chat.id.desc())).all()
    archived_chats=db.scalars(select(Chat).where(Chat.project_id==p.id, Chat.is_archived==True).order_by(Chat.updated_at.desc(), Chat.id.desc())).all()
    if not chats:
        c=Chat(project_id=p.id,title='Hlavní chat'); db.add(c); db.commit(); db.refresh(c); chats=[c]
    active = next((c for c in chats if c.id==chat_id), chats[0])
    messages=db.scalars(select(Message).where(Message.chat_id==active.id).order_by(Message.id.desc()).limit(250)).all()[::-1]
    tasks=db.scalars(select(Task).where(Task.project_id==p.id).order_by(Task.status!='working',Task.priority.desc(),Task.id.desc()).limit(250)).all()
    files=db.scalars(select(ProjectFile).where(ProjectFile.project_id==p.id).order_by(ProjectFile.id.desc()).limit(250)).all()
    outputs=[f for f in files if f.kind=='output']
    current_files=[f for f in files if f.status=='current']
    file_map={}
    for f in files: file_map.setdefault(f.message_id,[]).append(f)
    memories=db.scalars(select(ProjectMemory).where(ProjectMemory.project_id==p.id).order_by(ProjectMemory.id.desc()).limit(100)).all()
    # Only the newest approval group for the active chat is actionable.
    proposals=pending_group(db,p.id,chat_id=active.id)
    pending_action_data={m.id:parse_pending(m) for m in proposals}
    latest_pending=proposals
    latest_pending_ids=[m.id for m in latest_pending]
    manifests=[m for m in memories if m.kind=='manifest']
    manifest_info=None
    if manifests:
        manifest_row=manifests[0]
        raw=(manifest_row.content or '').encode('utf-8')
        manifest_info={'url':manifest_row.title,'content':manifest_row.content or '','sha256':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw),'saved_at':manifest_row.created_at}
    events=db.scalars(select(ProjectEvent).where(ProjectEvent.project_id==p.id).order_by(ProjectEvent.id.desc()).limit(150)).all()
    library_count=db.scalar(select(func.count(LibraryItem.id)).where(LibraryItem.owner_id==u.id)) or 0
    role=project_role(db,u,p)
    fresh_link,fresh_error,fresh_requests=project_link_state(u,p,role)
    task_counts={status:sum(1 for t in tasks if t.status==status) for status in STATUS_LABELS}
    task_groups=[
        ('todo','Nezahájeno',[t for t in tasks if t.status=='todo']),
        ('working','Ve vývoji',[t for t in tasks if t.status=='working']),
        ('testing','V testování',[t for t in tasks if t.status=='testing']),
        ('waiting_user','Čeká na tebe',[t for t in tasks if t.status=='waiting_user']),
        ('failed','Chyby',[t for t in tasks if t.status=='failed']),
        ('done','Dokončeno',[t for t in tasks if t.status=='done']),
        ('archived','Archiv',[t for t in tasks if t.status=='archived']),
    ]
    spec=project_spec(db,p.id)
    stages=get_stages(db,p.id)
    stage_alerts=workflow_alerts(stages)
    document_memories=[m for m in memories if m.kind in ('specification','documentation','decision','architecture','standard','fact','note')]
    capabilities=[
        {'name':'Projektový chat','status':'active','label':'Aktivní'},
        {'name':'Více chatů a archiv','status':'active','label':'Aktivní'},
        {'name':'Task management','status':'active','label':'Aktivní'},
        {'name':'Historie tasků','status':'planned','label':'V přípravě'},
        {'name':'Manifest projektu','status':'active','label':'Aktivní'},
        {'name':'Fresh Core kontext','status':'planned','label':'V přípravě'},
        {'name':'Archiv výstupů','status':'testing','label':'V testování'},
        {'name':'Current / Testing release','status':'planned','label':'V přípravě'},
        {'name':'Workspace a build ZIP','status':'planned','label':'V přípravě'},
        {'name':'Knihovna účtu','status':'active','label':'Aktivní'},
        {'name':'Cross-project reuse','status':'planned','label':'V přípravě'},
    ]
    return templates.TemplateResponse('project.html', ctx(request,u,project=p,selectable_projects=selectable_projects,chats=chats,archived_chats=archived_chats,active_chat=active,messages=messages,can_continue=bool(messages and messages[-1].role=='assistant' and not proposals and not (messages[-1].content or '').startswith('[[ENGINE_UNAVAILABLE]]')),reply_may_be_truncated=bool(messages and messages[-1].role=='assistant' and likely_truncated(messages[-1].content)),tasks=tasks,task_counts=task_counts,files=files,current_files=current_files,outputs=outputs,file_map=file_map,memories=memories,manifests=manifests,events=events,library_count=library_count,capabilities=capabilities,view=view,
        project_role=role,project_role_label=ROLE_LABELS.get(role,role),can_edit=can_edit_project(db,u,p),can_manage=can_manage_project(db,u,p),
        project_people=project_people(db,p),project_spec=spec,stages=stages,stage_alerts=stage_alerts,stage_statuses=STAGE_STATUSES,document_memories=document_memories,task_groups=task_groups,fresh_link=fresh_link,fresh_key_error=fresh_error,fresh_key_requests=fresh_requests,manifest_info=manifest_info,proposals=proposals,pending_action_data=pending_action_data,latest_pending_ids=latest_pending_ids,
        notice=request.query_params.get('notice',''),notice_url=request.query_params.get('notice_url',''),notice_label=request.query_params.get('notice_label','Otevřít'),error=request.query_params.get('error','')))

@app.post('/projects/{project_id}/edit')
def edit_project(request:Request, project_id:int, name:str=Form(...), description:str=Form(''), db:Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,write=True)
    p.name=name.strip() or p.name
    p.description=description.strip() or None
    p.updated_at=datetime.utcnow()
    db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='project_updated',detail='Základní informace projektu byly upraveny.'))
    db.commit()
    return RedirectResponse(f'/projects/{p.id}?view=settings&notice='+quote('Projekt jsem uložil.'),303)

@app.post('/projects/{project_id}/spec')
def edit_project_spec(request:Request, project_id:int, purpose:str=Form(''), project_type:str=Form(''), business_goal:str=Form(''), functional_goal:str=Form(''), project_scope:str=Form(''), project_deadline:str=Form(''), project_plan:str=Form(''), db:Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,write=True)
    values=locals().copy()
    for kind in PROJECT_SPEC_KINDS:
        save_project_spec_value(db,p.id,kind,values.get(kind,''))
    p.updated_at=datetime.utcnow()
    db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='project_spec_updated',detail='Projektová mapa byla aktualizována.'))
    db.commit()
    return RedirectResponse(f'/projects/{p.id}?view=development&notice='+quote('Projektovou mapu jsem uložil.'),303)

@app.post('/projects/{project_id}/workflow/{stage_no}')
def update_project_stage(request:Request,project_id:int,stage_no:int,
    objective:str=Form(''),acceptance:str=Form(''),start_date:str=Form(''),
    due_date:str=Form(''),note:str=Form(''),status:str=Form('planned'),db:Session=Depends(get_db)):
    u=require_user(request,db); project=get_project_or_404(db,u,project_id,write=True)
    if stage_no not in range(1,8): raise HTTPException(404)
    stages=get_stages(db,project_id); st=stages[stage_no-1]
    if status not in STAGE_STATUSES: raise HTTPException(400,'Neplatný stav etapy')
    def parse_date(value):
        if not value: return None
        try: return datetime.strptime(value,'%Y-%m-%d')
        except ValueError: raise HTTPException(400,'Neplatné datum')
    start=parse_date(start_date); due=parse_date(due_date)
    if start and due and start>due: raise HTTPException(400,'Začátek nesmí být po termínu')
    # No skipping gates: preceding stages must be accepted before activating/completing later ones.
    if status in ('active','completed') and any(prev.status!='completed' for prev in stages[:stage_no-1]):
        raise HTTPException(409,'Nejdřív schval předchozí etapy. Plánovat termíny můžeš předem.')
    if status=='completed' and not (acceptance.strip() and objective.strip()):
        raise HTTPException(400,'Pro schválení vyplň výstup a kritéria převzetí')
    if status=='completed' and not st.completed_at: st.completed_at=datetime.utcnow()
    elif status!='completed': st.completed_at=None
    change={'before':{'status':st.status,'due':st.due_date.isoformat() if st.due_date else None},
            'after':{'status':status,'due':due.isoformat() if due else None},'stage':stage_no}
    st.objective=objective.strip()[:10000];st.acceptance=acceptance.strip()[:10000]
    st.note=note.strip()[:10000];st.start_date=start;st.due_date=due;st.status=status;st.updated_at=datetime.utcnow()
    project.updated_at=datetime.utcnow()
    db.add(ProjectEvent(project_id=project_id,user_id=u.id,event_type='workflow_stage_updated',detail=json.dumps(change,ensure_ascii=False)))
    db.commit()
    return RedirectResponse(f'/projects/{project_id}?view=development#workflow',303)

@app.post('/projects/{project_id}/chats/{chat_id}/rename')
def rename_chat(request:Request, project_id:int, chat_id:int, title:str=Form(...), db:Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,write=True)
    c=db.get(Chat,chat_id)
    if not c or c.project_id!=p.id: raise HTTPException(404)
    c.title=title.strip() or c.title; c.updated_at=datetime.utcnow()
    db.commit()
    return RedirectResponse(f'/projects/{p.id}?view=chat&chat_id={c.id}',303)

@app.post('/projects/{project_id}/chats')
def create_chat(request: Request, project_id:int, title:str=Form(...), db:Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,write=True)
    c=Chat(project_id=p.id,title=title.strip() or 'Nový chat',updated_at=datetime.utcnow()); db.add(c); db.commit(); db.refresh(c)
    return RedirectResponse(f'/projects/{p.id}?chat_id={c.id}',303)


@app.post('/projects/{project_id}/chats/{chat_id}/archive')
def archive_chat(request:Request, project_id:int, chat_id:int, archived:int=Form(1), db:Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,write=True)
    c=db.get(Chat,chat_id)
    if not c or c.project_id!=p.id: raise HTTPException(404)
    c.is_archived=bool(archived); c.updated_at=datetime.utcnow()
    db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='chat_archived' if c.is_archived else 'chat_restored',detail=c.title))
    db.commit()
    return RedirectResponse(f'/projects/{p.id}?view=chat',303)

@app.post('/projects/{project_id}/chats/{chat_id}/delete')
def delete_chat(request:Request, project_id:int, chat_id:int, db:Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,write=True)
    c=db.get(Chat,chat_id)
    if not c or c.project_id!=p.id: raise HTTPException(404)
    if not c.is_archived:
        return redirect_project(p.id,error='Chat lze smazat až po archivaci.')
    # Zachováme projektová data, ale odpojíme je od mazaného chatu.
    for task in db.scalars(select(Task).where(Task.chat_id==c.id)).all(): task.chat_id=None
    for pf in db.scalars(select(ProjectFile).where(ProjectFile.chat_id==c.id)).all(): pf.chat_id=None
    for msg in db.scalars(select(Message).where(Message.chat_id==c.id)).all(): db.delete(msg)
    title=c.title
    db.delete(c)
    db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='chat_deleted',detail=title))
    db.commit()
    return redirect_project(p.id,notice='Archivovaný chat byl smazán.')

@app.post('/projects/{project_id}/archive')
def archive_project(request:Request, project_id:int, archived:int=Form(1), db:Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,manage=True)
    p.status='archived' if bool(archived) else 'active'; p.updated_at=datetime.utcnow()
    db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='project_archived' if p.status=='archived' else 'project_restored',detail=p.name))
    db.commit()
    return RedirectResponse('/?notice='+quote('Projekt byl archivován.' if p.status=='archived' else 'Projekt byl obnoven.'),303)

@app.post('/projects/{project_id}/delete')
def delete_project(request:Request, project_id:int, db:Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,manage=True)
    if (p.status or 'active')!='archived':
        return redirect_project(p.id,error='Projekt lze smazat až po archivaci.')
    # Smazání je úmyslně dvoukrokové: nejdřív archivace, potom trvalé odstranění.
    chats=db.scalars(select(Chat).where(Chat.project_id==p.id)).all(); chat_ids=[c.id for c in chats]
    if chat_ids:
        for msg in db.scalars(select(Message).where(Message.chat_id.in_(chat_ids))).all(): db.delete(msg)
    files=db.scalars(select(ProjectFile).where(ProjectFile.project_id==p.id)).all()
    for pf in files: pf.parent_file_id=None
    db.flush()
    for pf in files:
        try: absolute_path(pf.stored_name).unlink(missing_ok=True)
        except Exception: pass
        db.delete(pf)
    for model in (Task, ProjectMemory, ProjectEvent, ProjectMember, ProjectInvitation):
        for row in db.scalars(select(model).where(model.project_id==p.id)).all(): db.delete(row)
    for c in chats: db.delete(c)
    db.delete(p); db.commit()
    try: shutil.rmtree(settings.uploads_dir / str(project_id), ignore_errors=True)
    except Exception: pass
    return RedirectResponse('/?notice='+quote('Projekt byl trvale smazán.'),303)

@app.post('/projects/{project_id}/chat/{chat_id}/send')
async def send_message(request:Request, project_id:int, chat_id:int, message:str=Form(''), attachments:list[UploadFile]=File(default=[]), db:Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,write=True)
    c=db.get(Chat,chat_id)
    if not c or c.project_id!=p.id: raise HTTPException(404)
    if not message.strip() and not attachments: return RedirectResponse(f'/projects/{p.id}?chat_id={c.id}',303)
    user_msg=Message(chat_id=c.id,user_id=u.id,role='user',content=message.strip() or '[Příloha bez textu]')
    db.add(user_msg); db.flush()
    attachment_meta=[]
    for upload in attachments:
        if not upload.filename: continue
        try: stored,size=save_upload(upload,p.id)
        except ValueError as e: raise HTTPException(413,str(e))
        pf=ProjectFile(project_id=p.id,chat_id=c.id,message_id=user_msg.id,name=upload.filename[:255],stored_name=stored,mime_type=upload.content_type,size_bytes=size,kind='input')
        db.add(pf); db.flush()
        attachment_meta.append({'id':pf.id,'name':pf.name,'mime_type':pf.mime_type,'size_bytes':pf.size_bytes})
    db.flush()
    # One explicit confirmation is enough. Confirmation never goes back to AI when a concrete
    # pending action exists for this chat.
    if not attachment_meta and is_confirmation_message(user_msg.content):
        rows=pending_group(db,p.id,chat_id=c.id)
        if rows:
            batch=execute_pending_group(db,p,rows,u.id)
            db.add(Message(chat_id=c.id,user_id=None,role='assistant',content=action_result_text(batch)))
            db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='karel_action_batch_confirmed',detail=json.dumps(batch,ensure_ascii=False)[:1800]))
            c.updated_at=datetime.utcnow(); p.updated_at=datetime.utcnow(); db.commit()
            return RedirectResponse(f'/projects/{p.id}?chat_id={c.id}&notice='+quote(action_result_text(batch))+'#bottom',303)

    # A new non-confirmation message means the user continued the discussion instead of
    # approving the current proposal. Close that proposal and keep the decision in history.
    superseded = dismiss_pending_for_chat(db,p.id,c.id,reason='discussion_continued')
    if superseded:
        db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='karel_action_not_approved',detail='Neschváleno – diskuze pokračovala.'))
        db.flush()

    # Deterministic high-frequency write planner. It creates a real pending action directly
    # from the user's request/history, so we do not depend on the LLM emitting KAREL_STATE.
    planned = plan_write_request(db,p,c,u,user_msg) if (not attachment_meta and len(user_msg.content) < 220 and not is_complex_project_brief(user_msg.content)) else []
    if planned:
        titles='; '.join(r.title for r in planned)
        reply=('Potřebuji jen vybrat, kam tuto informaci uložit.' if any(parse_pending(r).get('type')=='choose_project_map_field' for r in planned) else 'Připravil jsem změnu k uložení. Pokud souhlasí, schval ji jedním kliknutím.')
        db.add(Message(chat_id=c.id,user_id=None,role='assistant',content=reply))
        db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='orchestrator_write_planned',detail=titles[:1800]))
        c.updated_at=datetime.utcnow(); p.updated_at=datetime.utcnow(); db.commit()
        return RedirectResponse(f'/projects/{p.id}?chat_id={c.id}#bottom',303)

    orchestration=orchestrate(db,p,c,u,user_msg.content,current_message_id=user_msg.id)
    if orchestration.mode == 'direct' and orchestration.direct_response is not None and not attachment_meta:
        db.add(Message(chat_id=c.id,user_id=None,role='assistant',content=orchestration.direct_response))
        db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='orchestrator_direct',detail=json.dumps({'tools':orchestration.tools_used},ensure_ascii=False)))
        c.updated_at=datetime.utcnow(); p.updated_at=datetime.utcnow(); db.commit()
        return RedirectResponse(f'/projects/{p.id}?chat_id={c.id}#bottom',303)
    source_blocks=resolve_message_sources(db,p,u,user_msg.content,APP_VERSION)
    tool_blocks=list(orchestration.context_blocks or [])
    if source_blocks:
        tool_blocks.extend(source_blocks)
    attachment_sources=[]
    if attachment_meta:
        input_files=db.scalars(select(ProjectFile).where(ProjectFile.message_id==user_msg.id)).all()
        extracted, reports=attachments_context(input_files)
        attachment_sources.append('PŘÍLOHY UŽIVATELE – skutečné výsledky extrakce. Pokud soubor není přečten, nesmíš tvrdit, že jsi ho analyzoval.\n'+extracted)
        db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='attachments_extracted',detail=json.dumps([{'name':r['name'],'ok':r['ok'],'error':r['error']} for r in reports],ensure_ascii=False)[:1800]))
    # Requests about previously uploaded material are allowed to retrieve the
    # recent file from this same project; don't pretend filename metadata is content.
    if not attachment_meta and any(term in user_msg.content.lower() for term in ('poslední příloh','posledni priloh','poslední zip','posledni zip','nahraný soubor','nahrany soubor')):
        recent_files=db.scalars(select(ProjectFile).where(ProjectFile.project_id==p.id,ProjectFile.kind=='input').order_by(ProjectFile.id.desc()).limit(2)).all()
        if recent_files:
            extracted,reports=attachments_context(recent_files)
            attachment_sources.append('STARŠÍ PŘÍLOHY Z TOHOTO PROJEKTU, přečtené na výslovnou žádost uživatele:\n'+extracted)
    system=build_context(db,p,c,u,query=user_msg.content,extra_sources=attachment_sources+tool_blocks) + "\n\n" + workflow_context(get_stages(db,p.id))
    try:
        raw=await engine_chat(system, user_msg.content, attachment_meta)
        visible=apply_state(db,p.id,c.id,raw,source_message_id=user_msg.id,allow_actions=not is_complex_project_brief(user_msg.content))
        db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='orchestrator_ai',detail=json.dumps({'tools':orchestration.tools_used},ensure_ascii=False)[:1800]))
    except EngineError as e:
        visible='[[ENGINE_UNAVAILABLE]] Karel se teď nemůže spojit s AI službou. Zprávu jsem uložil; můžeš ji zkusit odeslat znovu.'
        db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='engine_error',detail=str(e)[:500]))
    ai_msg=Message(chat_id=c.id,user_id=None,role='assistant',content=visible or 'Hotovo.')
    db.add(ai_msg); c.updated_at=datetime.utcnow(); p.updated_at=datetime.utcnow(); db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='chat_message',detail=f'Zpráva v chatu {c.title}'))
    db.commit()
    return RedirectResponse(f'/projects/{p.id}?chat_id={c.id}#bottom',303)

@app.post('/projects/{project_id}/chat/{chat_id}/continue')
async def continue_assistant_message(request:Request,project_id:int,chat_id:int,db:Session=Depends(get_db)):
    """Resume a possibly truncated answer without re-running write planners.

    This endpoint never invokes state parsing or action creation. The user
    explicitly requests continuation and stays in the same conversation.
    """
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,write=True)
    c=db.get(Chat,chat_id)
    if not c or c.project_id!=p.id: raise HTTPException(404)
    last=db.scalar(select(Message).where(Message.chat_id==c.id).order_by(Message.id.desc()))
    if not last or last.role!='assistant' or (last.content or '').startswith('[[ENGINE_UNAVAILABLE]]'):
        return RedirectResponse(f'/projects/{p.id}?chat_id={c.id}&error='+quote('Nejprve potřebujeme platnou odpověď Karla.')+'#bottom',303)
    # No write approval, task mutation or state processing on continuation.
    prompt=continuation_request(last.content)
    context=build_context(db,p,c,u,query='Pokračování rozepsané odpovědi bez nových akcí')
    context+='\n\nPOKRAČOVÁNÍ: Nedělej žádné návrhy databázových akcí. Neopakuj text. Navazuj od poslední věty, dokonči stávající část v rozsahu nejvýše 300 slov.'
    try:
        response=await engine_chat(context,prompt)
        # Treat any accidental action markup as plain model control output,
        # never execute it as a side effect of continuation.
        response=re.sub(r'<KAREL_STATE>.*?(?:</KAREL_STATE>|$)','',response or '',flags=re.I|re.S).strip()
        if not response: raise EngineError('AI neposkytla pokračování textu.')
        db.add(Message(chat_id=c.id,user_id=None,role='assistant',content=response))
        db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='chat_continued',detail='Pokračování rozpracované odpovědi.'))
        c.updated_at=datetime.utcnow();p.updated_at=datetime.utcnow();db.commit()
    except EngineError:
        db.rollback()
        return RedirectResponse(f'/projects/{p.id}?chat_id={c.id}&error='+quote('Pokračování se nepodařilo načíst. Původní odpověď zůstává uložená.')+'#bottom',303)
    return RedirectResponse(f'/projects/{p.id}?chat_id={c.id}#bottom',303)

@app.post('/projects/{project_id}/chat/{chat_id}/retry')
async def retry_message(request:Request, project_id:int, chat_id:int, db:Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,write=True)
    c=db.get(Chat,chat_id)
    if not c or c.project_id!=p.id: raise HTTPException(404)
    user_msg=db.scalar(select(Message).where(Message.chat_id==c.id, Message.role=='user').order_by(Message.id.desc()))
    if not user_msg:
        return RedirectResponse(f'/projects/{p.id}?chat_id={c.id}&error='+quote('Není co znovu odeslat.'),303)
    files=db.scalars(select(ProjectFile).where(ProjectFile.message_id==user_msg.id)).all()
    attachment_meta=[{'id':pf.id,'name':pf.name,'mime_type':pf.mime_type,'size_bytes':pf.size_bytes} for pf in files]
    orchestration=orchestrate(db,p,c,u,user_msg.content,current_message_id=user_msg.id)
    if orchestration.mode == 'direct' and orchestration.direct_response is not None and not attachment_meta:
        db.add(Message(chat_id=c.id,user_id=None,role='assistant',content=orchestration.direct_response))
        db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='orchestrator_direct_retry',detail=json.dumps({'tools':orchestration.tools_used},ensure_ascii=False)))
        c.updated_at=datetime.utcnow(); p.updated_at=datetime.utcnow(); db.commit()
        return RedirectResponse(f'/projects/{p.id}?chat_id={c.id}#bottom',303)
    source_blocks=resolve_message_sources(db,p,u,user_msg.content,APP_VERSION)
    tool_blocks=list(orchestration.context_blocks or [])
    if source_blocks:
        tool_blocks.extend(source_blocks)
    attachment_sources=[]
    if attachment_meta:
        input_files=db.scalars(select(ProjectFile).where(ProjectFile.message_id==user_msg.id)).all()
        extracted,reports=attachments_context(input_files)
        attachment_sources.append('PŘÍLOHY UŽIVATELE – skutečně extrahovaný obsah. Chyby čtení oznam explicitně.\n'+extracted)
    # Requests about previously uploaded material are allowed to retrieve the
    # recent file from this same project; don't pretend filename metadata is content.
    if not attachment_meta and any(term in user_msg.content.lower() for term in ('poslední příloh','posledni priloh','poslední zip','posledni zip','nahraný soubor','nahrany soubor')):
        recent_files=db.scalars(select(ProjectFile).where(ProjectFile.project_id==p.id,ProjectFile.kind=='input').order_by(ProjectFile.id.desc()).limit(2)).all()
        if recent_files:
            extracted,reports=attachments_context(recent_files)
            attachment_sources.append('STARŠÍ PŘÍLOHY Z TOHOTO PROJEKTU, přečtené na výslovnou žádost uživatele:\n'+extracted)
    system=build_context(db,p,c,u,query=user_msg.content,extra_sources=attachment_sources+tool_blocks) + "\n\n" + workflow_context(get_stages(db,p.id))
    try:
        raw=await engine_chat(system, user_msg.content, attachment_meta)
        visible=apply_state(db,p.id,c.id,raw,source_message_id=user_msg.id,allow_actions=not is_complex_project_brief(user_msg.content))
        db.add(Message(chat_id=c.id,user_id=None,role='assistant',content=visible or 'Hotovo.'))
        db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='chat_retry_ok',detail=f'Opakované zpracování zprávy v chatu {c.title}'))
        c.updated_at=datetime.utcnow(); p.updated_at=datetime.utcnow(); db.commit()
        return RedirectResponse(f'/projects/{p.id}?chat_id={c.id}#bottom',303)
    except EngineError as e:
        db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='engine_error',detail=str(e)[:500])); db.commit()
        return RedirectResponse(f'/projects/{p.id}?chat_id={c.id}&error='+quote('Karel se stále nemůže spojit s AI službou. Zkus to prosím znovu později.')+'#bottom',303)


@app.post('/projects/{project_id}/chat/{chat_id}/actions/approve')
def approve_chat_actions(request:Request, project_id:int, chat_id:int, db:Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,write=True)
    c=db.get(Chat,chat_id)
    if not c or c.project_id!=p.id: raise HTTPException(404)
    rows=pending_group(db,p.id,chat_id=c.id)
    if not rows:
        return RedirectResponse(f'/projects/{p.id}?view=chat&chat_id={c.id}&error='+quote('Není žádný aktuální návrh ke schválení.'),303)
    batch=execute_pending_group(db,p,rows,u.id)
    db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='karel_action_approved',detail=json.dumps(batch,ensure_ascii=False)[:1800]))
    notice='Schváleno a provedeno.' if batch.get('ok') else ('Schváleno, část změn se nepodařila provést.' if batch.get('partial') else 'Schválení se nepodařilo provést.')
    result=(batch.get('results') or [{}])[0] if batch.get('results') else {}
    target_url=result.get('target_url','') if batch.get('ok') else ''
    label='Otevřít výsledek'
    typ=result.get('type')
    if typ=='update_project_map': label='Otevřít zadání projektu'
    elif typ=='update_workflow_stage': label='Otevřít workflow projektu'
    elif typ in ('create_task','update_task','archive_task','delete_task'): label='Otevřít Úkoly'
    elif typ in ('save_library_item','update_library_item'): label='Otevřít Knihovnu'
    elif typ=='update_project': label='Otevřít projekt'
    db.add(Message(chat_id=c.id,user_id=None,role='assistant',content=action_result_text(batch)))
    db.commit()
    url=f'/projects/{p.id}?view=chat&chat_id={c.id}&notice='+quote(notice)
    if target_url:
        url += '&notice_url='+quote(target_url,safe='')+'&notice_label='+quote(label)
    return RedirectResponse(url+'#bottom',303)

@app.post('/projects/{project_id}/chat/{chat_id}/actions/{action_id}/choose-field')
def choose_action_field(request:Request, project_id:int, chat_id:int, action_id:int, field:str=Form(...), db:Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,write=True)
    c=db.get(Chat,chat_id)
    if not c or c.project_id!=p.id: raise HTTPException(404)
    row=db.get(ProjectMemory,action_id)
    if not row or row.project_id!=p.id or row.kind!='pending_action': raise HTTPException(404)
    try:
        data=choose_pending_field(row,field)
    except ValueError as exc:
        return RedirectResponse(f'/projects/{p.id}?view=chat&chat_id={c.id}&error='+quote(str(exc)),303)
    db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='karel_action_target_selected',detail=row.title))
    db.commit()
    return RedirectResponse(f'/projects/{p.id}?view=chat&chat_id={c.id}#bottom',303)

@app.post('/projects/{project_id}/actions/confirm-latest')
def confirm_latest_actions(request:Request, project_id:int, db:Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,write=True)
    rows=pending_group(db,p.id)
    if not rows:
        return redirect_project(p.id,error='Není žádný čekající návrh k potvrzení.')
    batch=execute_pending_group(db,p,rows,u.id)
    db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='karel_action_batch_confirmed',detail=json.dumps(batch,ensure_ascii=False)[:1800]))
    db.commit()
    return RedirectResponse(f'/projects/{p.id}?view=chat&notice='+quote(action_result_text(batch)),303)

@app.post('/projects/{project_id}/actions/{action_id}/confirm')
def confirm_action(request:Request, project_id:int, action_id:int, db:Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,write=True)
    row=db.get(ProjectMemory,action_id)
    if not row or row.project_id!=p.id or row.kind!='pending_action': raise HTTPException(404)
    try:
        result=execute_pending_action(db,p,row,u.id)
        db.commit()
    except ValueError as exc:
        db.rollback(); return redirect_project(p.id,error=str(exc))
    # Mandatory control read is performed inside execute_pending_action; result is the verified state.
    return RedirectResponse(f'/projects/{p.id}?view=chat&notice='+quote('Změna byla provedena a ověřena.'),303)

@app.post('/projects/{project_id}/actions/{action_id}/dismiss')
def dismiss_action(request:Request, project_id:int, action_id:int, db:Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,write=True)
    row=db.get(ProjectMemory,action_id)
    if not row or row.project_id!=p.id or row.kind!='pending_action': raise HTTPException(404)
    dismiss_pending_action(row)
    db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='karel_action_dismissed',detail=row.title))
    db.commit()
    return RedirectResponse(f'/projects/{p.id}?view=chat&notice='+quote('Návrh jsem zamítl.'),303)

@app.post('/projects/{project_id}/tasks')
def add_task(request:Request, project_id:int, chat_id:int=Form(...), title:str=Form(...), description:str=Form(''), db:Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,write=True)
    db.add(Task(project_id=p.id,chat_id=chat_id,title=title.strip(),description=description.strip() or None,status='todo')); db.commit()
    return RedirectResponse(f'/projects/{p.id}?chat_id={chat_id}',303)

@app.post('/tasks/{task_id}/edit')
def task_edit(request:Request, task_id:int, title:str=Form(...), description:str=Form(''), db:Session=Depends(get_db)):
    u=require_user(request,db); t=db.get(Task,task_id)
    if not t: raise HTTPException(404)
    p=get_project_or_404(db,u,t.project_id,write=True)
    t.title=title.strip() or t.title; t.description=description.strip() or None; t.updated_at=datetime.utcnow()
    db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='task_updated',detail=f'TASK-{t.id}: {t.title}'))
    db.commit(); return RedirectResponse(f'/projects/{p.id}?view=tasks',303)

@app.post('/tasks/{task_id}/status')
def task_status(request:Request, task_id:int, status:str=Form(...), db:Session=Depends(get_db)):
    u=require_user(request,db); t=db.get(Task,task_id)
    if not t: raise HTTPException(404)
    p=get_project_or_404(db,u,t.project_id,write=True)
    if status not in STATUS_LABELS: raise HTTPException(400)
    t.status=status; t.updated_at=datetime.utcnow();
    if status=='done': t.completed_at=datetime.utcnow()
    db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='task_status_changed',detail=f'TASK-{t.id}: {STATUS_LABELS.get(status,status)}'))
    db.commit(); return RedirectResponse(f'/projects/{p.id}?view=tasks',303)


@app.post('/tasks/{task_id}/delete')
def task_delete(request:Request, task_id:int, db:Session=Depends(get_db)):
    u=require_user(request,db); t=db.get(Task,task_id)
    if not t: raise HTTPException(404)
    p=get_project_or_404(db,u,t.project_id,write=True)
    if t.status!='archived':
        return redirect_project(p.id,error='Úkol lze trvale smazat až po archivaci.')
    title=t.title
    for pf in db.scalars(select(ProjectFile).where(ProjectFile.task_id==t.id)).all(): pf.task_id=None
    db.flush()
    db.delete(t)
    db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='task_deleted',detail=f'TASK-{task_id}: {title}'))
    db.commit()
    return RedirectResponse(f'/projects/{p.id}?view=tasks&notice='+quote('Archivovaný úkol byl smazán.'),303)

@app.get('/files/{file_id}')
def download_file(request:Request,file_id:int,db:Session=Depends(get_db)):
    u=require_user(request,db); f=db.get(ProjectFile,file_id)
    if not f: raise HTTPException(404)
    get_project_or_404(db,u,f.project_id)
    path=absolute_path(f.stored_name)
    if not path.exists(): raise HTTPException(404)
    return FileResponse(path, filename=f.name, media_type=f.mime_type or 'application/octet-stream')

@app.post('/projects/{project_id}/bundle')
def bundle_files(request:Request,project_id:int,chat_id:int=Form(...),db:Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,write=True)
    src=db.scalars(select(ProjectFile).where(ProjectFile.project_id==p.id, ProjectFile.status=='current').order_by(ProjectFile.id)).all()
    if not src: return RedirectResponse(f'/projects/{p.id}?chat_id={chat_id}',303)
    target,size=create_bundle(p.id,src,f'{p.name.lower().replace(" ","-")}-files.zip')
    stored=f'{p.id}/{target.name}'
    pf=ProjectFile(project_id=p.id,chat_id=chat_id,name=f'{p.name}-files.zip',stored_name=stored,mime_type='application/zip',size_bytes=size,kind='output')
    db.add(pf); db.flush()
    msg=Message(chat_id=chat_id,role='assistant',content='Připravil jsem ZIP z aktuálních souborů projektu. Najdeš ho tady v chatu i v knihovně souborů.')
    db.add(msg); db.flush(); pf.message_id=msg.id
    db.commit(); return RedirectResponse(f'/projects/{p.id}?chat_id={chat_id}#bottom',303)

@app.post('/projects/{project_id}/linking/publish')
def linking_publish(request:Request, project_id:int, db:Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,manage=True)
    try:
        link_id=fresh_key.publish_project(u,p,role=project_role(db,u,p))
        for person in project_people(db,p):
            if person['role']=='owner' or person['status']!='active': continue
            try: fresh_key.add_member(u,link_id,person['email'],person['role'],notify=False)
            except Exception: pass
        return redirect_project(p.id,notice='Projekt byl odeslán do Fresh Key.')
    except Exception as exc:
        return redirect_project(p.id,error=f'Odeslání do Fresh Key se nepodařilo: {exc}')

@app.post('/projects/{project_id}/linking/request/accept')
def linking_request_accept(request:Request, project_id:int, request_id:str=Form(...), db:Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,manage=True)
    try:
        accepted=fresh_key.accept_link_request(u,request_id,p,role=project_role(db,u,p))
        link_id=str(accepted.get('fresh_key_id') or '')
        if link_id:
            for person in project_people(db,p):
                if person['role']=='owner' or person['status']!='active': continue
                try: fresh_key.add_member(u,link_id,person['email'],person['role'],notify=False)
                except Exception: pass
        return redirect_project(p.id,notice='Propojení bylo potvrzeno.')
    except Exception as exc:
        return redirect_project(p.id,error=f'Propojení se nepodařilo potvrdit: {exc}')

@app.post('/fresh-key/link-request/{request_id}/decline')
def linking_request_decline(request:Request, request_id:str, project_id:int=Form(0), db:Session=Depends(get_db)):
    u=require_user(request,db)
    if project_id:
        p=get_project_or_404(db,u,project_id,manage=True)
    try:
        fresh_key.decline_link_request(u,request_id)
        return redirect_project(project_id,notice='Návrh propojení byl odmítnut.') if project_id else RedirectResponse('/?notice='+quote('Návrh propojení byl odmítnut.'),303)
    except Exception as exc:
        return redirect_project(project_id,error=str(exc)) if project_id else RedirectResponse('/?error='+quote(str(exc)),303)

@app.post('/fresh-key/link-request/{request_id}/create')
def linking_request_create(request:Request, request_id:str, name:str=Form(''), description:str=Form(''), db:Session=Depends(get_db)):
    u=require_user(request,db)
    try:
        pending=fresh_key.pending_link_requests(u)
        req=next((x for x in pending if str(x.get('id') or '')==request_id),None)
        if not req or req.get('target_external_project_id'):
            raise RuntimeError('Návrh na vytvoření projektu už není aktivní.')
        project_name=(name or req.get('target_project_name') or req.get('link_name') or 'Projekt').strip()
        p=Project(owner_id=u.id,name=project_name,description=description.strip() or None,updated_at=datetime.utcnow())
        db.add(p); db.flush(); db.add(Chat(project_id=p.id,title='Hlavní chat')); db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='project_created',detail='Projekt vytvořen z návrhu Fresh Key.')); db.commit(); db.refresh(p)
        fresh_key.register_project(u,p,role='owner'); fresh_key.accept_link_request(u,request_id,p,role='owner')
        return redirect_project(p.id,notice='Nový projekt byl vytvořen v Karlovi a propojen po potvrzení.')
    except Exception as exc:
        db.rollback(); return RedirectResponse('/?error='+quote(str(exc)),303)

@app.post('/projects/{project_id}/members')
def project_member_add(request:Request, project_id:int, email:str=Form(...), role:str=Form('editor'), relationship:str=Form('member'), db:Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,manage=True)
    email=email.strip().lower(); role=normalize_access_role(role); relationship=normalize_relationship(relationship)
    if role=='owner': role='manager'
    if not email: return redirect_project(p.id,error='Doplň e-mail.')
    if email==str((db.get(User,p.owner_id).email if db.get(User,p.owner_id) else '') or '').lower():
        return redirect_project(p.id,error='Vlastník už k projektu přístup má.')
    try:
        target=db.scalar(select(User).where(func.lower(User.email)==email))
        if target:
            row=db.scalar(select(ProjectMember).where(ProjectMember.project_id==p.id,ProjectMember.user_id==target.id))
            if not row: db.add(ProjectMember(project_id=p.id,user_id=target.id,role=role,relationship=relationship))
            else: row.role=role; row.relationship=relationship
            inv=db.scalar(select(ProjectInvitation).where(ProjectInvitation.project_id==p.id,func.lower(ProjectInvitation.email)==email))
            if inv: inv.status='accepted'; inv.updated_at=datetime.utcnow()
            message='Uživatel byl přidán do projektu.'
        else:
            inv=db.scalar(select(ProjectInvitation).where(ProjectInvitation.project_id==p.id,func.lower(ProjectInvitation.email)==email))
            if not inv:
                inv=ProjectInvitation(project_id=p.id,email=email,role=role,relationship=relationship,status='pending',invited_by=u.id); db.add(inv)
            else:
                inv.role=role; inv.relationship=relationship; inv.status='pending'; inv.invited_by=u.id; inv.updated_at=datetime.utcnow()
            message='Pozvánka k projektu byla uložena.'
        db.commit()
        action=settings.app_url.rstrip('/')+'/login'
        try: fresh_key.notify_project_share(u,email,p.name,role,action)
        except Exception: message += ' E-mail z Fresh Key se nepodařilo odeslat.'
        try:
            summary=fresh_key.project_summary(u,p,role=project_role(db,u,p))
            if summary.get('linked'): fresh_key.add_member(u,summary['fresh_key_id'],email,role,notify=False)
        except Exception: pass
        return redirect_project(p.id,notice=message)
    except Exception as exc:
        db.rollback(); return redirect_project(p.id,error=f'Sdílení se nepodařilo: {exc}')

@app.post('/projects/{project_id}/members/update')
def project_member_update(request:Request, project_id:int, email:str=Form(...), role:str=Form('editor'), relationship:str=Form('member'), db:Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,manage=True)
    email=email.strip().lower(); role=normalize_access_role(role); relationship=normalize_relationship(relationship)
    if role=='owner': role='manager'
    try:
        target=db.scalar(select(User).where(func.lower(User.email)==email))
        if target:
            row=db.scalar(select(ProjectMember).where(ProjectMember.project_id==p.id,ProjectMember.user_id==target.id))
            if row: row.role=role; row.relationship=relationship
        inv=db.scalar(select(ProjectInvitation).where(ProjectInvitation.project_id==p.id,func.lower(ProjectInvitation.email)==email,ProjectInvitation.status=='pending'))
        if inv: inv.role=role; inv.relationship=relationship; inv.updated_at=datetime.utcnow()
        db.commit()
        try:
            summary=fresh_key.project_summary(u,p,role=project_role(db,u,p)); member=next((m for m in summary.get('members',[]) if str(m.get('email') or '').lower()==email),None)
            if summary.get('linked') and member: fresh_key.update_member(u,summary['fresh_key_id'],str(member.get('identity_id') or ''),role)
        except Exception: pass
        return redirect_project(p.id,notice='Role a vztah byly upraveny v Karlovi.')
    except Exception as exc:
        db.rollback(); return redirect_project(p.id,error=str(exc))

@app.post('/projects/{project_id}/members/remove')
def project_member_remove(request:Request, project_id:int, email:str=Form(...), db:Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,manage=True); email=email.strip().lower()
    try:
        target=db.scalar(select(User).where(func.lower(User.email)==email))
        if target:
            row=db.scalar(select(ProjectMember).where(ProjectMember.project_id==p.id,ProjectMember.user_id==target.id))
            if row: db.delete(row)
        invites=db.scalars(select(ProjectInvitation).where(ProjectInvitation.project_id==p.id,func.lower(ProjectInvitation.email)==email,ProjectInvitation.status=='pending')).all()
        for inv in invites: db.delete(inv)
        db.commit()
        try:
            summary=fresh_key.project_summary(u,p,role=project_role(db,u,p)); member=next((m for m in summary.get('members',[]) if str(m.get('email') or '').lower()==email),None)
            if summary.get('linked') and member: fresh_key.remove_member(u,summary['fresh_key_id'],str(member.get('identity_id') or ''))
        except Exception: pass
        return redirect_project(p.id,notice='Uživatel nebo pozvánka byli z projektu odebráni.')
    except Exception as exc:
        db.rollback(); return redirect_project(p.id,error=str(exc))

@app.get('/account', response_class=HTMLResponse)
def account(request:Request,db:Session=Depends(get_db)):
    u=require_user(request,db)
    users=db.scalars(select(User).order_by(User.id)).all() if is_superadmin(u) else []
    return templates.TemplateResponse('account.html',ctx(request,u,users=users))

@app.get('/settings', response_class=HTMLResponse)
def account_settings(request: Request, db: Session=Depends(get_db)):
    u=require_user(request,db)
    # Account-wide collaborators are a read-only overview of existing project permissions.
    owned=db.scalars(select(Project).where(Project.owner_id==u.id).order_by(Project.name)).all()
    owned_ids=[p.id for p in owned]
    rows=[]
    if owned_ids:
        members=db.scalars(select(ProjectMember).where(ProjectMember.project_id.in_(owned_ids))).all()
        invitations=db.scalars(select(ProjectInvitation).where(ProjectInvitation.project_id.in_(owned_ids),ProjectInvitation.status=='pending')).all()
        project_by_id={p.id:p for p in owned}
        for m in members:
            person=db.get(User,m.user_id)
            if person:
                rows.append({'email':person.email,'name':person.name or person.email,'project':project_by_id[m.project_id], 'role':m.role,'state':'Aktivní'})
        for inv in invitations:
            rows.append({'email':inv.email,'name':inv.email,'project':project_by_id[inv.project_id], 'role':inv.role,'state':'Pozvánka'})
    return templates.TemplateResponse('settings.html',ctx(request,u,collaborators=rows,owned_projects=owned))

@app.post('/account/profile')
def update_profile(request:Request,name:str=Form(''),password:str=Form(''),db:Session=Depends(get_db)):
    u=require_user(request,db); u.name=name.strip() or None
    if password.strip(): u.password_hash=hash_password(password.strip())
    u.updated_at=datetime.utcnow(); db.commit(); return RedirectResponse('/account',303)

@app.post('/admin/users')
def create_user(request:Request,email:str=Form(...),name:str=Form(''),password:str=Form(...),role:str=Form('user'),db:Session=Depends(get_db)):
    u=require_user(request,db)
    if not is_superadmin(u): raise HTTPException(403)
    email=email.strip().lower()
    if db.scalar(select(User).where(User.email==email)): return RedirectResponse('/account?error=exists',303)
    db.add(User(email=email,name=name.strip() or None,password_hash=hash_password(password),role='superadmin' if role=='superadmin' else 'user')); db.commit(); return RedirectResponse('/account',303)

def _system_stats():
    disk = shutil.disk_usage(settings.storage_dir)
    mem_total = mem_available = None
    try:
        values = {}
        with open('/proc/meminfo','r',encoding='utf-8') as fh:
            for line in fh:
                key, value = line.split(':',1)
                values[key] = int(value.strip().split()[0]) * 1024
        mem_total = values.get('MemTotal')
        mem_available = values.get('MemAvailable')
    except Exception:
        pass
    try:
        load = os.getloadavg()
    except Exception:
        load = (None, None, None)
    return {
        'hostname': platform.node(),
        'python': platform.python_version(),
        'load1': load[0], 'load5': load[1], 'load15': load[2],
        'disk_total': disk.total, 'disk_used': disk.used, 'disk_free': disk.free,
        'memory_total': mem_total, 'memory_available': mem_available,
    }

@app.get('/admin', response_class=HTMLResponse)
def admin_console(request:Request, db:Session=Depends(get_db)):
    u=require_user(request,db)
    if not is_superadmin(u): raise HTTPException(403)
    users=db.scalars(select(User).order_by(User.created_at.desc(),User.id.desc())).all()
    stats={
        'users': db.scalar(select(func.count(User.id))) or 0,
        'projects': db.scalar(select(func.count(Project.id))) or 0,
        'chats': db.scalar(select(func.count(Chat.id))) or 0,
        'messages': db.scalar(select(func.count(Message.id))) or 0,
        'files': db.scalar(select(func.count(ProjectFile.id))) or 0,
        'library': db.scalar(select(func.count(LibraryItem.id))) or 0,
    }
    return templates.TemplateResponse('admin.html',ctx(request,u,users=users,stats=stats,system=_system_stats(),version=APP_VERSION,db_driver=engine.url.drivername,manifest_url='/manifest.json',brain=load_brain()))

@app.post('/admin/brain')
async def admin_brain_save(request:Request, db:Session=Depends(get_db)):
    u=require_user(request,db)
    if not is_superadmin(u): raise HTTPException(403)
    form=await request.form()
    cfg=load_brain()
    cfg.setdefault('communication', {})['tone']=str(form.get('tone','')).strip() or cfg['communication'].get('tone','stručný a praktický')
    rules=[x.strip() for x in str(form.get('rules','')).splitlines() if x.strip()]
    cfg['communication']['rules']=rules[:20]
    cfg.setdefault('project_guidance', {})['proactive']=bool(form.get('proactive'))
    cfg['project_guidance']['ask_before_large_work']=bool(form.get('ask_before_large_work'))
    cfg['project_guidance']['offer_save']=bool(form.get('offer_save'))
    cfg.setdefault('tools', {})['urls']=str(form.get('urls','auto_resolve'))
    cfg['tools']['files']=str(form.get('files','auto_context'))
    cfg['tools']['images']=str(form.get('images','vision_when_supported'))
    for key,item in cfg.get('project_types',{}).items():
        label=str(form.get(f'label_{key}', item.get('label',''))).strip() or item.get('label',key)
        workflow=[x.strip() for x in str(form.get(f'workflow_{key}','')).splitlines() if x.strip()]
        item['label']=label
        item['workflow']=workflow[:20]
    save_brain(cfg)
    return RedirectResponse('/admin?notice='+quote('Mozek Karla jsem uložil.'),303)

@app.post('/admin/users/{user_id}/role')
def admin_user_role(request:Request,user_id:int,role:str=Form(...),db:Session=Depends(get_db)):
    u=require_user(request,db)
    if not is_superadmin(u): raise HTTPException(403)
    target=db.get(User,user_id)
    if not target: raise HTTPException(404)
    # Hlavní supersprávce se nesmí omylem degradovat.
    if str(target.email or '').strip().lower()==settings.superadmin_email:
        target.role='superadmin'
    else:
        target.role='superadmin' if role=='superadmin' else 'user'
    target.updated_at=datetime.utcnow(); db.commit()
    return RedirectResponse('/admin',303)

@app.get('/manifest.json')
def app_manifest(request:Request,db:Session=Depends(get_db)):
    u=require_user(request,db)
    if not is_superadmin(u): raise HTTPException(403)
    return JSONResponse(build_app_manifest(db, APP_VERSION))

@app.get('/library', response_class=HTMLResponse)
def library_page(request:Request,db:Session=Depends(get_db)):
    u=require_user(request,db)
    items=db.scalars(select(LibraryItem).where(LibraryItem.owner_id==u.id).order_by(LibraryItem.id.desc())).all()
    return templates.TemplateResponse('library.html',ctx(request,u,items=items,error=request.query_params.get('error','')))

@app.post('/library')
async def library_add(request:Request,title:str=Form(...),category:str=Form('other'),description:str=Form(''),upload:UploadFile|None=File(default=None),db:Session=Depends(get_db)):
    u=require_user(request,db)
    stored=None
    if upload and upload.filename:
        try: stored,_=save_library_upload(upload,u.id)
        except ValueError as exc: return RedirectResponse('/library?error='+quote(str(exc)),303)
    item=LibraryItem(owner_id=u.id,title=title.strip(),category=(category.strip() or 'other')[:80],description=description.strip() or None,stored_name=stored,is_public=False)
    db.add(item); db.commit()
    return RedirectResponse('/library',303)

@app.post('/library/{item_id}/edit')
def library_edit(request:Request,item_id:int,title:str=Form(...),category:str=Form('other'),description:str=Form(''),db:Session=Depends(get_db)):
    u=require_user(request,db)
    item=db.get(LibraryItem,item_id)
    if not item or (item.owner_id is not None and item.owner_id!=u.id): raise HTTPException(404)
    item.title=title.strip() or item.title
    item.category=category.strip()[:80] or item.category
    item.description=description.strip() or None
    db.commit()
    return RedirectResponse('/library',303)

@app.get('/library/files/{item_id}')
def library_download(request:Request,item_id:int,db:Session=Depends(get_db)):
    u=require_user(request,db); item=db.get(LibraryItem,item_id)
    if not item or item.owner_id!=u.id or not item.stored_name: raise HTTPException(404)
    path=absolute_library_path(item.stored_name)
    if not path.exists(): raise HTTPException(404)
    return FileResponse(path,filename=Path(path).name,media_type='application/octet-stream')

@app.post('/library/{item_id}/delete')
def library_delete(request:Request,item_id:int,db:Session=Depends(get_db)):
    u=require_user(request,db); item=db.get(LibraryItem,item_id)
    if not item or item.owner_id!=u.id: raise HTTPException(404)
    if item.stored_name:
        try: absolute_library_path(item.stored_name).unlink(missing_ok=True)
        except Exception: pass
    db.delete(item); db.commit(); return RedirectResponse('/library',303)

@app.post('/projects/{project_id}/manifest')
def project_manifest_save(request:Request,project_id:int,url:str=Form(...),db:Session=Depends(get_db)):
    u=require_user(request,db); p=get_project_or_404(db,u,project_id,write=True)
    url=url.strip()
    if not (url.startswith('https://') or url.startswith('http://')):
        return redirect_project(p.id,error='Manifest musí mít adresu začínající http:// nebo https://.')
    try:
        with httpx.Client(timeout=15,follow_redirects=True) as client:
            r=client.get(url,headers={'User-Agent':'Karel/2.0 Manifest Reader'})
            r.raise_for_status()
            if len(r.content)>1024*1024: raise ValueError('Manifest je větší než 1 MB.')
            data=r.json()
        body=json.dumps(data,ensure_ascii=False,indent=2)
        row=db.scalar(select(ProjectMemory).where(ProjectMemory.project_id==p.id,ProjectMemory.kind=='manifest').order_by(ProjectMemory.id.desc()))
        if row:
            row.title=url; row.content=body; row.verified=True
        else:
            db.add(ProjectMemory(project_id=p.id,kind='manifest',title=url,content=body,verified=True))
        db.add(ProjectEvent(project_id=p.id,user_id=u.id,event_type='manifest_updated',detail=url))
        db.commit(); return redirect_project(p.id,notice='Manifest jsem načetl a uložil do kontextu projektu.')
    except Exception as exc:
        db.rollback(); return redirect_project(p.id,error=f'Manifest se nepodařilo načíst: {exc}')

@app.get('/engine/status')
async def engine_status(request:Request,db:Session=Depends(get_db)):
    require_user(request,db); ok,detail=await engine_health(); return JSONResponse({'ok':ok,'detail':detail})
