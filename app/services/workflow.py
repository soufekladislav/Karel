"""Project workflow: stable seven stages, project-local deadlines, contextual warnings."""
from datetime import datetime, date, timedelta
from sqlalchemy import select
from ..models import ProjectStage

STAGES = [
 ('Zadání','Schválený účel, rozsah a podmínky převzetí'),
 ('Analýza','Současný stav, zdroje, omezení a rizika'),
 ('Architektura a UX','Datový a funkční model, navigace a vizuální standardy'),
 ('Plánování','Milníky, odhady, termíny, priority a závislosti'),
 ('Vývoj','Implementace schváleného rozsahu a průběžné testy'),
 ('Závěrečné ověření','Regresní, integrační, bezpečnostní a akceptační testy'),
 ('Nasazení a uzavření','Pilot/produkce, převzetí, dokumentace a další plán'),
]
STATUSES = {'planned':'Plánováno','active':'Probíhá','blocked':'Blokováno','completed':'Schváleno'}

def get_stages(db, project_id):
    rows=db.scalars(select(ProjectStage).where(ProjectStage.project_id==project_id).order_by(ProjectStage.stage_no)).all()
    if not rows:
        rows=[ProjectStage(project_id=project_id,stage_no=i+1,title=title,objective=goal,
            acceptance='',status='planned') for i,(title,goal) in enumerate(STAGES)]
        db.add_all(rows); db.commit()
    return rows

def alerts(stages, today=None):
    today=today or date.today()
    result=[]
    for st in stages:
        if st.status=='completed' or not st.due_date: continue
        days=(st.due_date.date()-today).days
        if days<0: result.append({'stage':st,'days':days,'level':'late','text':f'Etapa {st.stage_no} – {st.title}: {abs(days)} dní po termínu'})
        elif days<=3: result.append({'stage':st,'days':days,'level':'soon','text':f'Etapa {st.stage_no} – {st.title}: zbývá {days} dní'})
    return sorted(result,key=lambda x:x['days'])

def context(stages):
    parts=['SEDM KROKŮ PROJEKTU (autoritativní projektový harmonogram):']
    for st in stages:
        end=st.due_date.strftime('%Y-%m-%d') if st.due_date else 'neurčeno'
        parts.append(f'{st.stage_no}. {st.title} | {STATUSES.get(st.status,st.status)} | termín {end} | výstup: {st.objective or "nezadáno"} | převzetí: {st.acceptance or "neurčeno"}')
    warnings=alerts(stages)
    if warnings: parts.append('ČASOVÁ UPOZORNĚNÍ: '+'; '.join(x['text'] for x in warnings[:5]))
    parts.append('Drž aktuální etapu. Nové nápady zařazuj do dalšího plánu; změny schválených etap nejprve posuď. Testování probíhá průběžně, krok 6 je souhrnné ověření. Neříkej, že etapa byla schválena, pokud to nepotvrzuje její stav. Nemáš-li nástroj pro změnu etap, naveď uživatele do projektového přehledu; neslibuj uložení.')
    return '\n'.join(parts)
