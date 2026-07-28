from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.db import get_db
from app.core.encryption import encryption
from app.api.dependencies import principal, require_roles, Principal
from app.models.models import *
from app.schemas.domain import *
from app.services.audit import record_audit
from app.services.confidence import recalculate_investigation_posteriors, expected_information_gain

router=APIRouter(prefix="/v1",tags=["SRIS Core"])
WRITE=("owner","admin","manager","analyst","contributor")
MANAGE=("owner","admin","manager")

def create(db,p,model,body,request=None,extra=None):
    data=body.model_dump(exclude_none=True); data.update(extra or {})
    obj=model(organization_id=p.organization.id,**data);db.add(obj);db.flush()
    record_audit(db,p.organization.id,p.user.id if p.user else None,"create",model.__tablename__,obj.id,after=data,request_id=getattr(request.state,"request_id",None) if request else None)
    db.commit();db.refresh(obj);return obj

def list_tenant(db,p,model,limit=200):
    q=db.query(model).filter(model.organization_id==p.organization.id)
    order=getattr(model,"created_at",getattr(model,"id"))
    return q.order_by(order.desc()).limit(min(limit,1000)).all()

def get_tenant(db,p,model,obj_id):
    o=db.query(model).filter_by(id=obj_id,organization_id=p.organization.id).first()
    if not o: raise HTTPException(404,f"{model.__name__} not found")
    return o

def count(db,p,m): return db.query(func.count(m.id)).filter(m.organization_id==p.organization.id).scalar()

@router.get("/dashboard")
def dashboard(p:Principal=Depends(principal),db:Session=Depends(get_db)):
    unresolved=count(db,p,Investigation)-db.query(func.count(Investigation.id)).filter_by(organization_id=p.organization.id,status="closed").scalar()
    return {"missions":count(db,p,Mission),"observations":count(db,p,Observation),"investigations_open":max(unresolved,0),
            "hypotheses":count(db,p,Hypothesis),"decisions":count(db,p,Decision),"outcomes":count(db,p,Outcome),
            "learnings":count(db,p,Learning),"learnings_reused":count(db,p,LearningReuse),"assumptions_refuted":db.query(func.count(Assumption.id)).filter_by(organization_id=p.organization.id,status="refuted").scalar(),
            "constraints_violated":db.query(func.count(Constraint.id)).filter_by(organization_id=p.organization.id,status="violated").scalar()}

# Core lists and creates
for _name,_model,_schema,_roles in [
    ("missions",Mission,MissionCreate,WRITE),("events",Event,EventCreate,WRITE),("observations",Observation,ObservationCreate,WRITE),
    ("investigations",Investigation,InvestigationCreate,WRITE),("assumptions",Assumption,AssumptionCreate,WRITE),
    ("constraints",Constraint,ConstraintCreate,WRITE),("alternatives",Alternative,AlternativeCreate,WRITE),
    ("decisions",Decision,DecisionCreate,MANAGE),("actions",Action,ActionCreate,WRITE),("implementations",Implementation,ImplementationCreate,WRITE),
    ("outcomes",Outcome,OutcomeCreate,WRITE),("learnings",Learning,LearningCreate,("owner","admin","manager","analyst")),
    ("evidence-proposals",EvidenceProposal,EvidenceProposalCreate,("owner","admin","manager","analyst"))]:
    def make_get(model):
        def endpoint(p:Principal=Depends(principal),db:Session=Depends(get_db)): return list_tenant(db,p,model)
        return endpoint
    def make_post(model,roles):
        def endpoint(body,request:Request,p:Principal=Depends(require_roles(*roles)),db:Session=Depends(get_db)):
            extra={}
            if model is Event: extra={"occurred_at":getattr(body,"occurred_at",None) or datetime.now(timezone.utc),"created_by":p.user.id}
            if model is Observation: extra={"observed_at":getattr(body,"observed_at",None) or datetime.now(timezone.utc),"created_by":p.user.id}
            if model is Decision: extra={"decided_by":p.user.id,"decided_at":datetime.now(timezone.utc)}
            return create(db,p,model,body,request,extra)
        endpoint.__annotations__["body"]=_schema
        return endpoint
    router.add_api_route(f"/{_name}",make_get(_model),methods=["GET"],name=f"list_{_name}")
    router.add_api_route(f"/{_name}",make_post(_model,_roles),methods=["POST"],name=f"create_{_name}")

@router.get("/entities")
def entities(p:Principal=Depends(principal),db:Session=Depends(get_db)): return list_tenant(db,p,OrgEntity)
@router.post("/entities")
def entity_create(body:EntityCreate,request:Request,p:Principal=Depends(require_roles(*WRITE)),db:Session=Depends(get_db)):
    data=body.model_dump(exclude={"sensitive_payload"});data["sensitive_payload"]=encryption.encrypt(p.organization.id,body.sensitive_payload)
    obj=OrgEntity(organization_id=p.organization.id,**data);db.add(obj);db.flush();record_audit(db,p.organization.id,p.user.id,"create","org_entities",obj.id,after={**data,"sensitive_payload":"[encrypted]"});db.commit();return obj

@router.get("/hypotheses")
def hypotheses(p:Principal=Depends(principal),db:Session=Depends(get_db)): return list_tenant(db,p,Hypothesis)
@router.post("/hypotheses")
def hypothesis_create(body:HypothesisCreate,request:Request,p:Principal=Depends(require_roles(*WRITE)),db:Session=Depends(get_db)):
    get_tenant(db,p,Investigation,body.investigation_id)
    obj=create(db,p,Hypothesis,body,request)
    _,distribution=recalculate_investigation_posteriors(db,p.organization.id,body.investigation_id)
    record_audit(db,p.organization.id,p.user.id,"posterior_recalculation","investigations",body.investigation_id,after={"distribution":distribution,"algorithm_version":"posterior-2-normalized"})
    db.commit();db.refresh(obj)
    return obj

@router.get("/provenance")
def provenance_list(p:Principal=Depends(principal),db:Session=Depends(get_db)):
    return list_tenant(db,p,Provenance,500)

@router.post("/provenance")
def provenance_create(body:ProvenanceCreate,request:Request,p:Principal=Depends(require_roles(*WRITE)),db:Session=Depends(get_db)):
    return create(db,p,Provenance,body,request)

@router.get("/evidence")
def evidence_list(p:Principal=Depends(principal),db:Session=Depends(get_db)): return list_tenant(db,p,Evidence)
@router.post("/evidence")
def evidence_create(body:EvidenceCreate,request:Request,p:Principal=Depends(require_roles(*WRITE)),db:Session=Depends(get_db)):
    get_tenant(db,p,Investigation,body.investigation_id)
    if body.hypothesis_id:
        h=get_tenant(db,p,Hypothesis,body.hypothesis_id)
        if h.investigation_id != body.investigation_id:
            raise HTTPException(409,"A hipótese e a evidência têm de pertencer à mesma investigação.")

    data=body.model_dump(exclude_none=True)
    nested=data.pop("provenance",None)
    provenance_id=data.pop("provenance_id",None)
    if nested:
        provenance=Provenance(organization_id=p.organization.id,**nested)
        db.add(provenance);db.flush();provenance_id=provenance.id
        record_audit(db,p.organization.id,p.user.id,"create","provenance_records",provenance.id,after=nested,request_id=getattr(request.state,"request_id",None))
    else:
        get_tenant(db,p,Provenance,provenance_id)

    obj=Evidence(organization_id=p.organization.id,provenance_id=provenance_id,**data)
    db.add(obj);db.flush()
    relation=Relation(organization_id=p.organization.id,source_type="provenance",source_id=provenance_id,target_type="evidence",target_id=obj.id,relation_type="produced",explanation="A proveniência identifica quem ou o que produziu o contributo e sob que condições.")
    db.add(relation)
    record_audit(db,p.organization.id,p.user.id,"create","evidence",obj.id,after={**data,"provenance_id":provenance_id},request_id=getattr(request.state,"request_id",None))
    _,distribution=recalculate_investigation_posteriors(db,p.organization.id,body.investigation_id)
    record_audit(db,p.organization.id,p.user.id,"posterior_recalculation","investigations",body.investigation_id,after={"distribution":distribution,"algorithm_version":"posterior-2-normalized"})
    db.commit();db.refresh(obj)
    return obj

@router.post("/evidence/{evidence_id}/refutes/assumptions/{assumption_id}")
def refute_assumption(evidence_id:str,assumption_id:str,p:Principal=Depends(require_roles(*WRITE)),db:Session=Depends(get_db)):
    e=get_tenant(db,p,Evidence,evidence_id);a=get_tenant(db,p,Assumption,assumption_id)
    a.status="refuted";a.valid_to=datetime.now(timezone.utc)
    r=Relation(organization_id=p.organization.id,source_type="evidence",source_id=e.id,target_type="assumption",target_id=a.id,relation_type="refutes",confidence=e.weight,explanation="Evidence refutes assumption")
    db.add(r);record_audit(db,p.organization.id,p.user.id,"refute","assumptions",a.id,after={"status":"refuted","evidence_id":e.id});db.commit();return {"assumption":a,"relation":r}

@router.post("/constraints/{constraint_id}/status")
def constraint_status(constraint_id:str,body:StateChange,p:Principal=Depends(require_roles(*WRITE)),db:Session=Depends(get_db)):
    c=get_tenant(db,p,Constraint,constraint_id);before={"status":c.status};c.status=body.status
    if body.status in ("violated","expired"):c.valid_to=datetime.now(timezone.utc)
    record_audit(db,p.organization.id,p.user.id,"state_change","constraints",c.id,before=before,after={"status":c.status,"reason":body.reason});db.commit();return c

@router.post("/relations")
def relation_create(body:RelationCreate,request:Request,p:Principal=Depends(require_roles(*WRITE)),db:Session=Depends(get_db)): return create(db,p,Relation,body,request)
@router.get("/relations")
def relations(p:Principal=Depends(principal),db:Session=Depends(get_db)): return list_tenant(db,p,Relation,1000)

@router.post("/learnings/{learning_id}/reuse")
def reuse(learning_id:str,body:LearningReuseCreate,p:Principal=Depends(require_roles(*WRITE)),db:Session=Depends(get_db)):
    l=get_tenant(db,p,Learning,learning_id)
    x=LearningReuse(organization_id=p.organization.id,learning_id=l.id,mission_id=body.mission_id,decision_id=body.decision_id,explanation=body.explanation,reused_by=p.user.id)
    db.add(x);l.reuse_count+=1;l.last_reused_at=datetime.now(timezone.utc)
    record_audit(db,p.organization.id,p.user.id,"reuse","learnings",l.id,after={"reuse_count":l.reuse_count,"mission_id":body.mission_id,"decision_id":body.decision_id});db.commit();return x
@router.get("/learning-reuses")
def learning_reuses(p:Principal=Depends(principal),db:Session=Depends(get_db)):return list_tenant(db,p,LearningReuse)

@router.get("/opportunities", include_in_schema=False)
@router.post("/opportunities", include_in_schema=False)
@router.patch("/opportunities/{oid}", include_in_schema=False)
def opportunities_retired(oid:str|None=None):
    raise HTTPException(
        status_code=410,
        detail="O fluxo Opportunity foi retirado da Pilot Release. Valor económico só pode ser apresentado depois de baseline, intervenção, resultado e avaliação de atribuição.",
    )

@router.get("/investigations/{investigation_id}/posteriors")
def investigation_posteriors(investigation_id:str,p:Principal=Depends(principal),db:Session=Depends(get_db)):
    get_tenant(db,p,Investigation,investigation_id)
    hypotheses,distribution=recalculate_investigation_posteriors(db,p.organization.id,investigation_id)
    db.commit()
    return {
        "investigation_id": investigation_id,
        "algorithm_version": "posterior-2-normalized",
        "sum": round(sum(distribution.values()),12),
        "hypotheses": [
            {"id":h.id,"statement":h.statement,"prior":h.prior,"posterior":distribution.get(h.id,0.0)}
            for h in hypotheses
        ],
    }

@router.get("/investigations/{investigation_id}/information-value")
def investigation_information_value(investigation_id:str,p:Principal=Depends(principal),db:Session=Depends(get_db)):
    get_tenant(db,p,Investigation,investigation_id)
    hypotheses,distribution=recalculate_investigation_posteriors(db,p.organization.id,investigation_id)
    valid_ids={h.id for h in hypotheses}
    proposals=db.query(EvidenceProposal).filter_by(organization_id=p.organization.id,investigation_id=investigation_id).all()
    risk_penalty={"low":1.0,"medium":1.25,"high":1.75}
    feasibility_factor={"unknown":0.8,"low":0.55,"medium":0.8,"high":1.0}
    rows=[]
    for proposal in proposals:
        effects={key:float(value) for key,value in (proposal.expected_effects or {}).items() if key in valid_ids}
        gain=expected_information_gain(distribution,effects,proposal.weight)
        cost=max(float(proposal.estimated_cost or 0),0.0)
        days=max(float(proposal.estimated_days or 0),0.0)
        denominator=1.0+cost/1000.0+days/30.0
        priority=(gain*feasibility_factor.get(proposal.feasibility,0.8))/(denominator*risk_penalty.get(proposal.risk_level,1.25))
        rows.append({
            "id":proposal.id,"title":proposal.title,"description":proposal.description,
            "expected_information_gain_kl":gain,"priority":round(priority,12),
            "estimated_cost":proposal.estimated_cost,"estimated_days":proposal.estimated_days,
            "risk_level":proposal.risk_level,"feasibility":proposal.feasibility,
            "limitations":proposal.limitations,"expected_effects":effects,
        })
    rows.sort(key=lambda row:row["priority"],reverse=True)
    db.commit()
    return {"investigation_id":investigation_id,"algorithm_version":"voi-kl-1","posterior":distribution,"proposals":rows}

def evaluate_attribution(db,p,outcome):
    action=get_tenant(db,p,Action,outcome.action_id);decision=get_tenant(db,p,Decision,action.decision_id)
    ass=db.query(Assumption).filter_by(organization_id=p.organization.id,decision_id=decision.id).all()
    con=db.query(Constraint).filter_by(organization_id=p.organization.id,decision_id=decision.id).all()
    impl=db.query(Implementation).filter_by(organization_id=p.organization.id,decision_id=decision.id).order_by(Implementation.created_at.desc()).first()
    reasons=[];pen=0.0
    ref=[x.id for x in ass if x.status=="refuted"];vio=[x.id for x in con if x.status=="violated"]
    if ref: pen+=.45;reasons.append(f"{len(ref)} pressuposto(s) refutado(s) condicionaram a decisão.")
    if vio: pen+=.22;reasons.append(f"{len(vio)} restrição(ões) violada(s) alteraram a execução.")
    base=outcome.baseline or {}
    baseline_status="present" if base and any(v not in (None,"",[]) for v in base.values()) else "missing"
    if baseline_status=="missing":pen+=.32;reasons.append("Não existe baseline comparável declarado.")
    deviation=bool(impl and impl.deviations)
    if deviation:pen+=.12;reasons.append("A implementação contém desvios ao plano.")
    ext=(outcome.measured or {}).get("external_variables",[]) if isinstance(outcome.measured,dict) else []
    if ext:pen+=.20;reasons.append("Existem variáveis externas não controladas.")
    status="not_supported" if pen>=.55 else "partially_supported" if pen>=.25 else "supported"
    rationale="Não se afirma que a intervenção não produziu o resultado; avalia-se apenas se a cadeia registada sustenta a atribuição."
    old=db.query(AttributionAssessment).filter_by(organization_id=p.organization.id,outcome_id=outcome.id).order_by(AttributionAssessment.evaluated_at.desc()).first()
    if old and old.algorithm_version=="attribution-1":
        old.status=status;old.penalty=min(pen,1);old.baseline_status=baseline_status;old.implementation_deviation=deviation;old.external_variables=ext;old.refuted_assumptions=ref;old.violated_constraints=vio;old.reasons=reasons;old.rationale=rationale;old.evaluated_by=p.user.id;old.evaluated_at=datetime.now(timezone.utc);obj=old
    else:
        obj=AttributionAssessment(organization_id=p.organization.id,outcome_id=outcome.id,status=status,penalty=min(pen,1),baseline_status=baseline_status,implementation_deviation=deviation,external_variables=ext,refuted_assumptions=ref,violated_constraints=vio,reasons=reasons,rationale=rationale,evaluated_by=p.user.id)
        db.add(obj)
    db.commit();db.refresh(obj);return obj

@router.post("/outcomes/{outcome_id}/attribution")
def attribution(outcome_id:str,body:AttributionRequest,p:Principal=Depends(require_roles("owner","admin","manager","analyst")),db:Session=Depends(get_db)):
    return evaluate_attribution(db,p,get_tenant(db,p,Outcome,outcome_id))
@router.get("/attribution-assessments")
def attributions(p:Principal=Depends(principal),db:Session=Depends(get_db)):return list_tenant(db,p,AttributionAssessment)

@router.get("/reasoning-audit")
def reasoning_audit(mission_id:str|None=None,p:Principal=Depends(principal),db:Session=Depends(get_db)):
    def q(model):
        query=db.query(model).filter(model.organization_id==p.organization.id)
        if mission_id and hasattr(model,"mission_id"): query=query.filter(model.mission_id==mission_id)
        return query.all()
    gaps=[];hyps=q(Hypothesis);decs=q(Decision);outs=q(Outcome);learn=q(Learning);ass=q(Assumption);cons=q(Constraint);alts=q(Alternative)
    evid=q(Evidence)
    provenance_rows=db.query(Provenance).filter(Provenance.organization_id==p.organization.id).all()
    provenance_by_id={row.id:row for row in provenance_rows}
    for e in evid:
        provenance=provenance_by_id.get(e.provenance_id)
        if provenance is None:
            gaps.append({"severity":"high","ref":e.id,"rule":"EVD_NO_PROVENANCE","message":"Evidência sem registo de proveniência não é auditável."})
        elif provenance.origin_type != "human" and (not provenance.model_or_system or not provenance.version):
            gaps.append({"severity":"high","ref":e.id,"rule":"EVD_MACHINE_ORIGIN_NO_VERSION","message":"Contributo de origem artificial ou sistémica sem modelo/sistema e versão declarados não é auditável."})
    for h in hyps:
        he=[e for e in evid if e.hypothesis_id==h.id]
        if not he:gaps.append({"severity":"high","ref":h.id,"rule":"HYP_NO_EVIDENCE","message":"Hipótese sem evidência associada."})
        elif not any(e.direction in ("contradicts","refutes") for e in he):gaps.append({"severity":"medium","ref":h.id,"rule":"HYP_NO_COUNTER","message":"Hipótese sem evidência contrária registada."})
    for d in decs:
        if not [x for x in alts if x.decision_id==d.id]:gaps.append({"severity":"high","ref":d.id,"rule":"DEC_NO_ALT","message":"Decisão sem alternativas de primeira classe."})
        if not [x for x in ass if x.decision_id==d.id] and not [x for x in cons if x.decision_id==d.id]:gaps.append({"severity":"medium","ref":d.id,"rule":"DEC_NO_CONTEXT","message":"Decisão sem pressupostos nem restrições declarados."})
    for o in outs:
        if not o.baseline:gaps.append({"severity":"high","ref":o.id,"rule":"OUT_NO_BASELINE","message":"Resultado sem baseline comparável."})
    for l in learn:
        if l.reuse_count==0:gaps.append({"severity":"low","ref":l.id,"rule":"LRN_NOT_REUSED","message":"Aprendizagem ainda não reutilizada."})
    order={"high":0,"medium":1,"low":2};return sorted(gaps,key=lambda x:order[x["severity"]])

@router.get("/graph")
def graph(mission_id:str|None=None,p:Principal=Depends(principal),db:Session=Depends(get_db)):
    spec=[(Mission,"mission","name"),(OrgEntity,"entity","name"),(Observation,"observation","title"),(Provenance,"provenance","origin_actor"),(Evidence,"evidence","title"),(Investigation,"investigation","title"),(Hypothesis,"hypothesis","statement"),(Assumption,"assumption","statement"),(Constraint,"constraint","statement"),(Alternative,"alternative","title"),(Decision,"decision","title"),(Implementation,"implementation","title"),(Outcome,"outcome","observed"),(Learning,"learning","statement")]
    nodes=[]
    for model,kind,label in spec:
        query=db.query(model).filter(model.organization_id==p.organization.id)
        if mission_id and hasattr(model,"mission_id"):query=query.filter(model.mission_id==mission_id)
        for x in query.limit(700):nodes.append({"id":x.id,"type":kind,"label":str(getattr(x,label))[:180],"status":getattr(x,"status",None),"mission_id":getattr(x,"mission_id",None)})
    nodeids={n["id"] for n in nodes}
    edges=[{"id":r.id,"source":r.source_id,"target":r.target_id,"type":r.relation_type,"confidence":r.confidence} for r in db.query(Relation).filter(Relation.organization_id==p.organization.id).limit(1500) if r.source_id in nodeids and r.target_id in nodeids]
    return {"nodes":nodes,"edges":edges}

@router.get("/workspace/{mission_id}")
def workspace(mission_id:str,p:Principal=Depends(principal),db:Session=Depends(get_db)):
    mission=get_tenant(db,p,Mission,mission_id)
    graph_data=graph(mission_id,p,db)
    inv=db.query(Investigation).filter_by(organization_id=p.organization.id,mission_id=mission_id).all()
    inv_ids=[x.id for x in inv]
    hypotheses=db.query(Hypothesis).filter(Hypothesis.organization_id==p.organization.id,Hypothesis.investigation_id.in_(inv_ids or ["-"])).all()
    posterior_sets=[];information_value=[]
    for investigation in inv:
        _,distribution=recalculate_investigation_posteriors(db,p.organization.id,investigation.id)
        posterior_sets.append({"investigation_id":investigation.id,"distribution":distribution,"sum":round(sum(distribution.values()),12)})
        information_value.append(investigation_information_value(investigation.id,p,db))
    db.commit()
    return {"mission":mission,"graph":graph_data,"investigations":inv,"hypotheses":hypotheses,"posteriors":posterior_sets,"information_value":information_value,"audit":reasoning_audit(mission_id,p,db)}

@router.get("/audit")
def audit(p:Principal=Depends(require_roles("owner","admin","auditor")),db:Session=Depends(get_db)): return list_tenant(db,p,AuditLog,300)
