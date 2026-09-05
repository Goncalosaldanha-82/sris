from __future__ import annotations

import json
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FRONT=ROOT/'frontend'/'pilot-v1'
OUT=ROOT/'qa-current-static'
OUT.mkdir(exist_ok=True)
findings=[]; checks=[]

def finding(severity,area,title,detail='',file=''):
    findings.append({'severity':severity,'area':area,'title':title,'detail':detail,'file':file})

def check(name,ok,detail='',severity='major',file=''):
    checks.append({'name':name,'ok':bool(ok),'detail':detail,'severity':severity,'file':file})
    if not ok: finding(severity,'static-check',name,detail,file)

class Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.ids=[];self.refs=[];self.controls=[];self.labels=set();self.inline_scripts=0;self.inline_styles=0
    def handle_starttag(self,tag,attrs_list):
        a={k:v or '' for k,v in attrs_list}
        if a.get('id'):self.ids.append(a['id'])
        if tag in {'script','img','link','a'}:
            k='src' if tag in {'script','img'} else 'href'
            if a.get(k):self.refs.append((tag,a[k]))
        if tag in {'input','select','textarea'}:self.controls.append({'tag':tag,**a})
        if tag=='label' and a.get('for'):self.labels.add(a['for'])
        if tag=='script' and not a.get('src'):self.inline_scripts+=1
        if tag=='style':self.inline_styles+=1

def local(ref):
    r=ref.split('#',1)[0].split('?',1)[0]
    if not r or r.startswith(('http://','https://','mailto:','tel:','data:','javascript:')):return None
    if r=='/':return FRONT/'home.html'
    return FRONT/r.lstrip('/')

for hp in sorted(FRONT.glob('*.html')):
    rel=hp.relative_to(ROOT).as_posix();txt=hp.read_text(encoding='utf-8');p=Parser();p.feed(txt)
    dup={k:v for k,v in Counter(p.ids).items() if v>1};check(f'{rel}: unique IDs',not dup,json.dumps(dup),'critical',rel)
    missing=[]
    for tag,ref in p.refs:
        target=local(ref)
        if target is not None and not target.exists():missing.append({'tag':tag,'ref':ref,'target':target.relative_to(ROOT).as_posix()})
    check(f'{rel}: local assets exist',not missing,json.dumps(missing),'critical',rel)
    unl=[]
    for c in p.controls:
        cid=c.get('id','');typ=c.get('type','')
        if not cid or typ=='hidden':continue
        if cid not in p.labels and not c.get('aria-label') and not c.get('aria-labelledby') and not c.get('title'):unl.append(cid)
    check(f'{rel}: controls have accessible labels',not unl,json.dumps(unl),'major',rel)
    versions=sorted(set(re.findall(r'[?&]v=([^\"\'&\s>]+)',txt)))
    stale=[v for v in versions if v!='__PILOT_BUILD__']
    if hp.name in {'home.html','index.html','demonstracao.html','account.html'}:check(f'{rel}: versioned assets use build placeholder',not stale,json.dumps(stale),'major',rel)

# Canonical product contract in source.
cap=(ROOT/'backend/app/pilot_capabilities.py').read_text(encoding='utf-8')
check('Capabilities define five user moments',all(x in cap for x in ['"context"','"evidence"','"decision"','"measurement"','"memory"']),'missing user moment','critical','backend/app/pilot_capabilities.py')
check('Capabilities define eight canonical records',all(x in cap for x in ['"observation"','"evidence"','"hypothesis"','"alternative"','"decision"','"action"','"outcome"','"learning"']),'missing canonical record','critical','backend/app/pilot_capabilities.py')
api=(ROOT/'backend/app/atlas_platform/api.py').read_text(encoding='utf-8')
check('Managed runtime disables public API docs by default','default=not _managed_runtime()' in api and 'openapi_url="/openapi.json" if _api_docs_enabled else None' in api,'managed docs gate not found','major','backend/app/atlas_platform/api.py')
identity=(ROOT/'backend/app/atlas_platform/identity.py').read_text(encoding='utf-8')
authjs=(FRONT/'auth.js').read_text(encoding='utf-8')
check('Entry password-reset request/confirm uses canonical auth route family','/api/auth/password-reset/request' in authjs and '/api/auth/password-reset/confirm' in authjs,'mixed route family detected','critical','frontend/pilot-v1/auth.js')
check('Password reset raw token is not returned by identity request', 'reset_token' not in re.sub(r'def confirm_password_reset[\s\S]*','',identity), 'reset_token string appears in request-side identity implementation', 'major','backend/app/atlas_platform/identity.py')

main=(ROOT/'backend/app/main.py').read_text(encoding='utf-8')
if "'unsafe-inline'" in main:finding('minor','csp','CSP still permits unsafe-inline','Inline script/style allowances reduce XSS containment.','backend/app/main.py')

# Runtime code smells.
for path in list((ROOT/'backend/app').rglob('*.py'))+list(FRONT.glob('*.js')):
    rel=path.relative_to(ROOT).as_posix();txt=path.read_text(encoding='utf-8',errors='ignore')
    if re.search(r'\beval\s*\(|new Function\s*\(',txt):finding('critical','dynamic-code','Dynamic code execution primitive detected','eval/new Function',rel)
    if path.suffix=='.js' and 'console.log(' in txt:finding('minor','frontend-debug','console.log remains in frontend source','Remove or gate production debug logging.',rel)

# Reproducibility and accidental secrets indicators.
check('Runtime dependency lock exists',(ROOT/'requirements.lock').exists(),'requirements.lock missing','critical','requirements.lock')
check('Test dependency lock exists',(ROOT/'requirements-test.lock').exists(),'requirements-test.lock missing','major','requirements-test.lock')
config=(ROOT/'backend/app/atlas_platform/config.py').read_text(encoding='utf-8')
check('Managed runtime rejects default JWT secret','DEFAULT_JWT_SECRET' in config and 'len(value.jwt_secret.encode("utf-8")) < 32' in config,'security validation not found','critical','backend/app/atlas_platform/config.py')
check('Managed runtime rejects SQLite','managed deployments cannot use SQLite' in config,'SQLite rejection not found','critical','backend/app/atlas_platform/config.py')

findings.sort(key=lambda f:{'critical':0,'major':1,'minor':2,'info':3}.get(f['severity'],9))
summary={'checks':len(checks),'passed':sum(c['ok'] for c in checks),'failed':sum(not c['ok'] for c in checks),'critical':sum(f['severity']=='critical' for f in findings),'major':sum(f['severity']=='major' for f in findings),'minor':sum(f['severity']=='minor' for f in findings)}
report={'summary':summary,'checks':checks,'findings':findings}
(OUT/'current-static-quality.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
md=['# SRIS current static quality audit','',f"Checks: {summary['passed']}/{summary['checks']} passed",f"Findings: {summary['critical']} critical · {summary['major']} major · {summary['minor']} minor",'','## Findings']
for i,f in enumerate(findings,1):md.append(f"{i}. **{f['severity'].upper()} · {f['area']} · {f['title']}** — {f['detail']} ({f['file']})")
md+=['','## Failed checks']+[f"{i}. **{c['severity'].upper()} · {c['name']}** — {c['detail']}" for i,c in enumerate([x for x in checks if not x['ok']],1)]
textout='\n'.join(md)+'\n';(OUT/'current-static-quality.md').write_text(textout,encoding='utf-8');print('===== SRIS_CURRENT_STATIC_START =====');print(json.dumps(summary));print(textout);print('===== SRIS_CURRENT_STATIC_END =====')
