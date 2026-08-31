from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.atlas_platform.audit import record_audit
from app.atlas_platform.auth import require_org_role
from app.atlas_platform.database import Base, get_db
from app.atlas_platform.models import Membership, Role
from app.mission_intelligence.models import CanonicalMission

router = APIRouter(prefix="/api/organizations/{organization_id}/pilots", tags=["Pilot & Mission Intelligence"])
READ_ROLES=(Role.OWNER.value,Role.ADMIN.value,Role.REVIEWER.value,Role.CONTRIBUTOR.value,Role.OBSERVER.value)
WRITE_ROLES=(Role.OWNER.value,Role.ADMIN.value,Role.REVIEWER.value,Role.CONTRIBUTOR.value)
USER_MOMENTS=["context","evidence","decision","measurement","memory"]
CANONICAL_RECORDS=["observation","evidence","hypothesis","alternative","decision","action","outcome","learning"]
TRANSVERSAL_CONDITIONS=["assumptions","constraints","gaps","uncertainty","provenance","confidence"]

def utcnow()->datetime:return datetime.now(timezone.utc)
def _json(value:Any)->str:return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))
def _loads(value:str|None,fallback:Any)->Any:
    try:return json.loads(value) if value else deepcopy(fallback)
    except (TypeError,ValueError):return deepcopy(fallback)

class Pilot(Base):
    __tablename__="sris_pilots"
    __table_args__=(UniqueConstraint("organization_id","code",name="uq_sris_pilot_org_code"),)
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    organization_id:Mapped[str]=mapped_column(ForeignKey("organizations.id",ondelete="CASCADE"),index=True)
    code:Mapped[str]=mapped_column(String(80),index=True)
    title:Mapped[str]=mapped_column(String(300))
    sector_profile:Mapped[str]=mapped_column(String(80),default="cross_sector",index=True)
    template_key:Mapped[str]=mapped_column(String(100),default="universal_decision_pilot")
    program_source:Mapped[str]=mapped_column(String(200),default="direct")
    partner_name:Mapped[str]=mapped_column(String(300),default="")
    context_name:Mapped[str]=mapped_column(String(300),default="")
    context_type:Mapped[str]=mapped_column(String(80),default="unit")
    location:Mapped[str]=mapped_column(String(500),default="")
    problem_statement:Mapped[str]=mapped_column(Text)
    decision_question:Mapped[str]=mapped_column(Text)
    objective:Mapped[str]=mapped_column(Text)
    scope:Mapped[str]=mapped_column(Text,default="")
    exclusions:Mapped[str]=mapped_column(Text,default="")
    sponsor:Mapped[str]=mapped_column(String(240),default="")
    pilot_owner:Mapped[str]=mapped_column(String(240),default="")
    data_owner:Mapped[str]=mapped_column(String(240),default="")
    operator:Mapped[str]=mapped_column(String(240),default="")
    reviewer:Mapped[str]=mapped_column(String(240),default="")
    start_date:Mapped[date|None]=mapped_column(Date,nullable=True)
    end_date:Mapped[date|None]=mapped_column(Date,nullable=True)
    lifecycle_state:Mapped[str]=mapped_column(String(40),default="draft",index=True)
    charter_json:Mapped[str]=mapped_column(Text,default="{}")
    data_readiness_json:Mapped[str]=mapped_column(Text,default="{}")
    implementation_json:Mapped[str]=mapped_column(Text,default="{}")
    scale_json:Mapped[str]=mapped_column(Text,default="{}")
    revision:Mapped[int]=mapped_column(Integer,default=1)
    created_by_user_id:Mapped[str|None]=mapped_column(ForeignKey("users.id",ondelete="SET NULL"),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)

class PilotMissionLink(Base):
    __tablename__="sris_pilot_missions"
    __table_args__=(UniqueConstraint("pilot_id","mission_id",name="uq_sris_pilot_mission_link"),)
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    pilot_id:Mapped[str]=mapped_column(ForeignKey("sris_pilots.id",ondelete="CASCADE"),index=True)
    mission_id:Mapped[str]=mapped_column(ForeignKey("mi_missions.id",ondelete="CASCADE"),index=True)
    link_role:Mapped[str]=mapped_column(String(40),default="primary")
    created_by_user_id:Mapped[str|None]=mapped_column(ForeignKey("users.id",ondelete="SET NULL"),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class PilotMetric(Base):
    __tablename__="sris_pilot_metrics"
    __table_args__=(UniqueConstraint("pilot_id","metric_key",name="uq_sris_pilot_metric_key"),)
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    pilot_id:Mapped[str]=mapped_column(ForeignKey("sris_pilots.id",ondelete="CASCADE"),index=True)
    metric_key:Mapped[str]=mapped_column(String(100))
    label:Mapped[str]=mapped_column(String(300))
    category:Mapped[str]=mapped_column(String(80),default="operational")
    unit:Mapped[str]=mapped_column(String(80),default="")
    direction:Mapped[str]=mapped_column(String(20),default="decrease")
    baseline_value:Mapped[Decimal|None]=mapped_column(Numeric(20,6),nullable=True)
    target_value:Mapped[Decimal|None]=mapped_column(Numeric(20,6),nullable=True)
    current_value:Mapped[Decimal|None]=mapped_column(Numeric(20,6),nullable=True)
    normalized_by:Mapped[str]=mapped_column(String(200),default="")
    source:Mapped[str]=mapped_column(Text,default="")
    method:Mapped[str]=mapped_column(Text,default="")
    limitations:Mapped[str]=mapped_column(Text,default="")
    confidence:Mapped[str]=mapped_column(String(20),default="not_evaluable")
    status:Mapped[str]=mapped_column(String(30),default="not_measured")
    baseline_period:Mapped[str]=mapped_column(String(120),default="")
    result_period:Mapped[str]=mapped_column(String(120),default="")
    created_by_user_id:Mapped[str|None]=mapped_column(ForeignKey("users.id",ondelete="SET NULL"),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)

class PilotDataSource(Base):
    __tablename__="sris_pilot_data_sources"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    pilot_id:Mapped[str]=mapped_column(ForeignKey("sris_pilots.id",ondelete="CASCADE"),index=True)
    name:Mapped[str]=mapped_column(String(300))
    source_type:Mapped[str]=mapped_column(String(80),default="file")
    system_name:Mapped[str]=mapped_column(String(240),default="")
    data_format:Mapped[str]=mapped_column(String(80),default="")
    owner:Mapped[str]=mapped_column(String(240),default="")
    frequency:Mapped[str]=mapped_column(String(120),default="")
    access_method:Mapped[str]=mapped_column(String(160),default="manual_upload")
    readiness_state:Mapped[str]=mapped_column(String(30),default="identified")
    quality_state:Mapped[str]=mapped_column(String(30),default="unknown")
    required:Mapped[bool]=mapped_column(default=True)
    limitations:Mapped[str]=mapped_column(Text,default="")
    created_by_user_id:Mapped[str|None]=mapped_column(ForeignKey("users.id",ondelete="SET NULL"),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)

class PilotWorkItem(Base):
    __tablename__="sris_pilot_work_items"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    pilot_id:Mapped[str]=mapped_column(ForeignKey("sris_pilots.id",ondelete="CASCADE"),index=True)
    title:Mapped[str]=mapped_column(String(400))
    item_type:Mapped[str]=mapped_column(String(40),default="action")
    status:Mapped[str]=mapped_column(String(30),default="planned")
    owner:Mapped[str]=mapped_column(String(240),default="")
    due_date:Mapped[date|None]=mapped_column(Date,nullable=True)
    description:Mapped[str]=mapped_column(Text,default="")
    evidence_reference:Mapped[str]=mapped_column(Text,default="")
    sort_order:Mapped[int]=mapped_column(Integer,default=0)
    created_by_user_id:Mapped[str|None]=mapped_column(ForeignKey("users.id",ondelete="SET NULL"),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)

class StrictModel(BaseModel):model_config=ConfigDict(extra="forbid",str_strip_whitespace=True)
class PilotCreate(StrictModel):
    title:str=Field(min_length=3,max_length=300);problem_statement:str=Field(min_length=10,max_length=30000);decision_question:str=Field(min_length=10,max_length=10000);objective:str=Field(min_length=10,max_length=10000)
    sector_profile:str=Field(default="cross_sector",min_length=2,max_length=80);template_key:str=Field(default="universal_decision_pilot",min_length=2,max_length=100);program_source:str=Field(default="direct",max_length=200)
    partner_name:str=Field(default="",max_length=300);context_name:str=Field(default="",max_length=300);context_type:str=Field(default="unit",max_length=80);location:str=Field(default="",max_length=500)
    scope:str=Field(default="",max_length=30000);exclusions:str=Field(default="",max_length=30000);sponsor:str=Field(default="",max_length=240);pilot_owner:str=Field(default="",max_length=240);data_owner:str=Field(default="",max_length=240);operator:str=Field(default="",max_length=240);reviewer:str=Field(default="",max_length=240)
    start_date:date|None=None;end_date:date|None=None;charter:dict[str,Any]=Field(default_factory=dict);data_readiness:dict[str,Any]=Field(default_factory=dict);implementation:dict[str,Any]=Field(default_factory=dict);scale:dict[str,Any]=Field(default_factory=dict);apply_template_defaults:bool=True
    @model_validator(mode="after")
    def dates_are_ordered(self)->"PilotCreate":
        if self.start_date and self.end_date and self.end_date<self.start_date:raise ValueError("Pilot end_date cannot be before start_date")
        return self
class PilotUpdate(StrictModel):
    expected_revision:int=Field(ge=1);title:str|None=Field(default=None,min_length=3,max_length=300);problem_statement:str|None=Field(default=None,min_length=10,max_length=30000);decision_question:str|None=Field(default=None,min_length=10,max_length=10000);objective:str|None=Field(default=None,min_length=10,max_length=10000)
    sector_profile:str|None=Field(default=None,min_length=2,max_length=80);template_key:str|None=Field(default=None,min_length=2,max_length=100);program_source:str|None=Field(default=None,max_length=200);partner_name:str|None=Field(default=None,max_length=300);context_name:str|None=Field(default=None,max_length=300);context_type:str|None=Field(default=None,max_length=80);location:str|None=Field(default=None,max_length=500)
    scope:str|None=Field(default=None,max_length=30000);exclusions:str|None=Field(default=None,max_length=30000);sponsor:str|None=Field(default=None,max_length=240);pilot_owner:str|None=Field(default=None,max_length=240);data_owner:str|None=Field(default=None,max_length=240);operator:str|None=Field(default=None,max_length=240);reviewer:str|None=Field(default=None,max_length=240);start_date:date|None=None;end_date:date|None=None
    lifecycle_state:Literal["draft","discovery","design","baseline","active","evaluating","scale_review","completed","suspended","cancelled"]|None=None
    charter:dict[str,Any]|None=None;data_readiness:dict[str,Any]|None=None;implementation:dict[str,Any]|None=None;scale:dict[str,Any]|None=None;change_note:str=Field(min_length=3,max_length=1000)
class MissionLinkCreate(StrictModel):mission_id:str=Field(min_length=36,max_length=36);link_role:Literal["primary","supporting","measurement","scale"]="primary"
class MetricCreate(StrictModel):
    metric_key:str|None=Field(default=None,min_length=2,max_length=100);label:str=Field(min_length=2,max_length=300);category:Literal["economic","operational","resource","experience","governance","learning"]="operational";unit:str=Field(default="",max_length=80);direction:Literal["increase","decrease","maintain","range"]="decrease"
    baseline_value:Decimal|None=None;target_value:Decimal|None=None;current_value:Decimal|None=None;normalized_by:str=Field(default="",max_length=200);source:str=Field(default="",max_length=10000);method:str=Field(default="",max_length=10000);limitations:str=Field(default="",max_length=10000);confidence:Literal["high","moderate","low","not_evaluable"]="not_evaluable";status:Literal["not_measured","baseline_ready","tracking","attention","achieved"]="not_measured";baseline_period:str=Field(default="",max_length=120);result_period:str=Field(default="",max_length=120)
class MetricUpdate(StrictModel):
    label:str|None=Field(default=None,min_length=2,max_length=300);category:Literal["economic","operational","resource","experience","governance","learning"]|None=None;unit:str|None=Field(default=None,max_length=80);direction:Literal["increase","decrease","maintain","range"]|None=None;baseline_value:Decimal|None=None;target_value:Decimal|None=None;current_value:Decimal|None=None;normalized_by:str|None=Field(default=None,max_length=200);source:str|None=Field(default=None,max_length=10000);method:str|None=Field(default=None,max_length=10000);limitations:str|None=Field(default=None,max_length=10000);confidence:Literal["high","moderate","low","not_evaluable"]|None=None;status:Literal["not_measured","baseline_ready","tracking","attention","achieved"]|None=None;baseline_period:str|None=Field(default=None,max_length=120);result_period:str|None=Field(default=None,max_length=120)
class DataSourceCreate(StrictModel):
    name:str=Field(min_length=2,max_length=300);source_type:Literal["file","document","manual","api","database","sensor","system","external"]="file";system_name:str=Field(default="",max_length=240);data_format:str=Field(default="",max_length=80);owner:str=Field(default="",max_length=240);frequency:str=Field(default="",max_length=120);access_method:str=Field(default="manual_upload",max_length=160);readiness_state:Literal["identified","requested","received","mapped","validated","unavailable"]="identified";quality_state:Literal["unknown","weak","usable","strong"]="unknown";required:bool=True;limitations:str=Field(default="",max_length=10000)
class DataSourceUpdate(StrictModel):
    name:str|None=Field(default=None,min_length=2,max_length=300);source_type:Literal["file","document","manual","api","database","sensor","system","external"]|None=None;system_name:str|None=Field(default=None,max_length=240);data_format:str|None=Field(default=None,max_length=80);owner:str|None=Field(default=None,max_length=240);frequency:str|None=Field(default=None,max_length=120);access_method:str|None=Field(default=None,max_length=160);readiness_state:Literal["identified","requested","received","mapped","validated","unavailable"]|None=None;quality_state:Literal["unknown","weak","usable","strong"]|None=None;required:bool|None=None;limitations:str|None=Field(default=None,max_length=10000)
class WorkItemCreate(StrictModel):
    title:str=Field(min_length=2,max_length=400);item_type:Literal["milestone","action","risk","decision","gate"]="action";status:Literal["planned","in_progress","blocked","completed","cancelled"]="planned";owner:str=Field(default="",max_length=240);due_date:date|None=None;description:str=Field(default="",max_length=10000);evidence_reference:str=Field(default="",max_length=10000);sort_order:int=Field(default=0,ge=0,le=10000)
class WorkItemUpdate(StrictModel):
    title:str|None=Field(default=None,min_length=2,max_length=400);item_type:Literal["milestone","action","risk","decision","gate"]|None=None;status:Literal["planned","in_progress","blocked","completed","cancelled"]|None=None;owner:str|None=Field(default=None,max_length=240);due_date:date|None=None;description:str|None=Field(default=None,max_length=10000);evidence_reference:str|None=Field(default=None,max_length=10000);sort_order:int|None=Field(default=None,ge=0,le=10000)

SECTOR_PROFILES={
"cross_sector":{"key":"cross_sector","label":"Transversal","description":"Decisões, intervenções e aprendizagem em qualquer organização.","context_labels":["organização","unidade","departamento","território","projeto"],"typical_sources":["documentos","dados operacionais","custos","ocorrências"]},
"hospitality":{"key":"hospitality","label":"Hospitality","description":"Operações de alojamento, recursos, experiência e capacidade operacional.","context_labels":["hotel","unidade","departamento","espaço","operação"],"typical_sources":["PMS","consumos","ocupação","manutenção","custos","reclamações"]},
"public_sector":{"key":"public_sector","label":"Setor público","description":"Serviços, políticas, equipamentos e territórios sob responsabilidade pública.","context_labels":["município","serviço","equipamento","território","programa"],"typical_sources":["processos","indicadores","orçamento","utilização","participação"]},
"industrial_operations":{"key":"industrial_operations","label":"Operações industriais","description":"Processos, manutenção, recursos, qualidade e segurança operacional.","context_labels":["instalação","linha","processo","equipa","ativo"],"typical_sources":["produção","sensores","manutenção","qualidade","custos"]},
"territorial_lab":{"key":"territorial_lab","label":"Laboratório territorial","description":"Experimentação multientidade com condições, resultados e memória territorial.","context_labels":["território","comunidade","ecossistema","parceria","infraestrutura"],"typical_sources":["cartografia","monitorização","participação","ambiente","economia"]}}
TEMPLATES={
"universal_decision_pilot":{"key":"universal_decision_pilot","label":"Decisão e intervenção mensurável","sector_profile":"cross_sector","description":"Estruturar um problema real, testar uma intervenção e preservar a aprendizagem.","scope_hint":"Uma unidade, uma decisão material, uma intervenção observável e um horizonte definido.","metrics":[{"metric_key":"primary_outcome","label":"Resultado principal","category":"operational","unit":"","direction":"increase"},{"metric_key":"implementation_cost","label":"Custo da intervenção","category":"economic","unit":"EUR","direction":"decrease"},{"metric_key":"decision_confidence","label":"Confiança da decisão","category":"governance","unit":"%","direction":"increase"}],"data_sources":[{"name":"Dados do problema e atividade","source_type":"file","required":True},{"name":"Custos e recursos","source_type":"document","required":True},{"name":"Ocorrências e contexto operacional","source_type":"manual","required":True}]},
"hospitality_resource_efficiency":{"key":"hospitality_resource_efficiency","label":"Hospitality · Eficiência de recursos","sector_profile":"hospitality","description":"Água, energia, resíduos, atividade real, custos e experiência do hóspede.","scope_hint":"Uma unidade de alojamento, um recurso prioritário e uma intervenção reversível.","metrics":[{"metric_key":"water_per_occupied_room_night","label":"Água por quarto-noite ocupado","category":"resource","unit":"L/quarto-noite","direction":"decrease","normalized_by":"quarto-noite ocupado"},{"metric_key":"energy_per_occupied_room_night","label":"Energia por quarto-noite ocupado","category":"resource","unit":"kWh/quarto-noite","direction":"decrease","normalized_by":"quarto-noite ocupado"},{"metric_key":"operating_cost_per_occupied_room_night","label":"Custo por quarto-noite ocupado","category":"economic","unit":"EUR/quarto-noite","direction":"decrease","normalized_by":"quarto-noite ocupado"},{"metric_key":"guest_experience_safeguard","label":"Experiência do hóspede","category":"experience","unit":"índice","direction":"maintain"}],"data_sources":[{"name":"Consumos de água e energia","source_type":"file","data_format":"CSV/XLSX/PDF","required":True},{"name":"Ocupação, quartos vendidos e hóspedes-noite","source_type":"system","system_name":"PMS ou mapa operacional","required":True},{"name":"Custos, manutenção e ocorrências","source_type":"document","required":True},{"name":"Reclamações e sinais de experiência","source_type":"manual","required":False}]},
"hospitality_operational_intelligence":{"key":"hospitality_operational_intelligence","label":"Hospitality · Inteligência operacional","sector_profile":"hospitality","description":"Converter sinais operacionais, manutenção ou sensing em decisões e ações acompanháveis.","scope_hint":"Um processo, espaço ou ativo; uma anomalia material; uma intervenção mensurável.","metrics":[{"metric_key":"response_time","label":"Tempo de resposta operacional","category":"operational","unit":"min","direction":"decrease"},{"metric_key":"recurring_incidents","label":"Ocorrências recorrentes","category":"operational","unit":"n.º","direction":"decrease"},{"metric_key":"availability","label":"Disponibilidade operacional","category":"operational","unit":"%","direction":"increase"},{"metric_key":"comfort_or_service_guardrail","label":"Conforto ou qualidade de serviço","category":"experience","unit":"índice","direction":"maintain"}],"data_sources":[{"name":"Ordens de trabalho e incidentes","source_type":"system","required":True},{"name":"Sinais de sensores, BMS ou registos de operação","source_type":"sensor","required":False},{"name":"Tempos, escalas e capacidade da equipa","source_type":"file","required":True},{"name":"Custos e impacto no serviço","source_type":"document","required":True}]},
"public_service_improvement":{"key":"public_service_improvement","label":"Serviço público · Melhoria mensurável","sector_profile":"public_sector","description":"Testar uma alteração num serviço, equipamento ou território com transparência e aprendizagem.","scope_hint":"Um serviço ou equipamento, um grupo de utilizadores e uma mudança delimitada.","metrics":[{"metric_key":"service_time","label":"Tempo de resposta do serviço","category":"operational","unit":"dias","direction":"decrease"},{"metric_key":"user_access","label":"Acesso ou utilização","category":"experience","unit":"n.º","direction":"increase"},{"metric_key":"public_cost","label":"Custo por resultado","category":"economic","unit":"EUR","direction":"decrease"}],"data_sources":[{"name":"Procura e utilização do serviço","source_type":"database","required":True},{"name":"Tempos, capacidade e recursos","source_type":"file","required":True},{"name":"Feedback de utilizadores","source_type":"manual","required":False}]},
"investment_validation":{"key":"investment_validation","label":"Investimento · Validação antes de escala","sector_profile":"cross_sector","description":"Comparar alternativas, testar pressupostos e medir valor antes de comprometer escala.","scope_hint":"Um investimento material, alternativas reais, critérios explícitos e uma prova reversível.","metrics":[{"metric_key":"total_cost","label":"Custo total","category":"economic","unit":"EUR","direction":"decrease"},{"metric_key":"realized_benefit","label":"Benefício realizado","category":"economic","unit":"EUR","direction":"increase"},{"metric_key":"implementation_time","label":"Tempo de implementação","category":"operational","unit":"dias","direction":"decrease"},{"metric_key":"evidence_robustness","label":"Robustez da evidência","category":"governance","unit":"%","direction":"increase"}],"data_sources":[{"name":"Propostas, estimativas e alternativas","source_type":"document","required":True},{"name":"Custos internos e capacidade","source_type":"file","required":True},{"name":"Baseline operacional","source_type":"database","required":True}]}}
DEFAULT_WORK_ITEMS=[{"title":"Contrato do piloto validado","item_type":"gate","sort_order":10},{"title":"Fontes de dados recebidas e avaliadas","item_type":"gate","sort_order":20},{"title":"Baseline aprovada","item_type":"milestone","sort_order":30},{"title":"Intervenção autorizada e executada","item_type":"milestone","sort_order":40},{"title":"Resultado revisto e aprendizagem publicada","item_type":"gate","sort_order":50},{"title":"Decisão de escala registada","item_type":"decision","sort_order":60}]

def _slug(value:str)->str:return re.sub(r"[^a-z0-9]+","_",value.lower()).strip("_")[:80] or "metric"
def _next_code(db:Session,organization_id:str)->str:
    used=set()
    for (code,) in db.query(Pilot.code).filter(Pilot.organization_id==organization_id).all():
        match=re.match(r"^PLT-(\d+)$",code or "",re.I)
        if match:used.add(int(match.group(1)))
    number=1
    while number in used:number+=1
    return f"PLT-{number:03d}"
def _pilot_or_404(db:Session,organization_id:str,pilot_id:str)->Pilot:
    row=db.query(Pilot).filter(Pilot.id==pilot_id,Pilot.organization_id==organization_id).one_or_none()
    if row is None:raise HTTPException(status_code=404,detail="Piloto não encontrado")
    return row
def _metric_change(row:PilotMetric)->float|None:
    if row.baseline_value is None or row.current_value is None:return None
    baseline=Decimal(row.baseline_value)
    if baseline==0:return None
    return round(float((Decimal(row.current_value)-baseline)/abs(baseline)*100),2)
def _target_state(row:PilotMetric)->str:
    if row.current_value is None:return row.status or "not_measured"
    if row.target_value is None:return "tracking"
    current,target=Decimal(row.current_value),Decimal(row.target_value)
    if row.direction=="decrease":return "achieved" if current<=target else "attention"
    if row.direction=="increase":return "achieved" if current>=target else "attention"
    if row.direction=="maintain" and row.baseline_value is not None:
        baseline=Decimal(row.baseline_value);return "achieved" if abs(current-baseline)<=abs(baseline)*Decimal("0.05") else "attention"
    return "tracking"
def _metric_view(row:PilotMetric)->dict[str,Any]:return {"id":row.id,"metric_key":row.metric_key,"label":row.label,"category":row.category,"unit":row.unit,"direction":row.direction,"baseline_value":float(row.baseline_value) if row.baseline_value is not None else None,"target_value":float(row.target_value) if row.target_value is not None else None,"current_value":float(row.current_value) if row.current_value is not None else None,"change_pct":_metric_change(row),"normalized_by":row.normalized_by,"source":row.source,"method":row.method,"limitations":row.limitations,"confidence":row.confidence,"status":_target_state(row),"baseline_period":row.baseline_period,"result_period":row.result_period,"created_at":row.created_at,"updated_at":row.updated_at}
def _data_source_view(row:PilotDataSource)->dict[str,Any]:return {"id":row.id,"name":row.name,"source_type":row.source_type,"system_name":row.system_name,"data_format":row.data_format,"owner":row.owner,"frequency":row.frequency,"access_method":row.access_method,"readiness_state":row.readiness_state,"quality_state":row.quality_state,"required":row.required,"limitations":row.limitations,"created_at":row.created_at,"updated_at":row.updated_at}
def _work_item_view(row:PilotWorkItem)->dict[str,Any]:return {"id":row.id,"title":row.title,"item_type":row.item_type,"status":row.status,"owner":row.owner,"due_date":row.due_date,"description":row.description,"evidence_reference":row.evidence_reference,"sort_order":row.sort_order,"created_at":row.created_at,"updated_at":row.updated_at}
def _readiness(row:Pilot,metrics:list[PilotMetric],sources:list[PilotDataSource],work_items:list[PilotWorkItem],mission_count:int)->dict[str,Any]:
    charter=[bool(row.problem_statement.strip()),bool(row.decision_question.strip()),bool(row.objective.strip()),bool(row.scope.strip()),bool(row.pilot_owner.strip() or row.sponsor.strip())]
    required=[s for s in sources if s.required];available=[s for s in required if s.readiness_state in {"received","mapped","validated"}];baseline=[m for m in metrics if m.baseline_value is not None];results=[m for m in metrics if m.current_value is not None];completed=[i for i in work_items if i.status=="completed"];blocked=[i for i in work_items if i.status=="blocked"];scale=_loads(row.scale_json,{})
    dimensions={"charter":round(sum(charter)/len(charter)*100),"data":round(len(available)/max(1,len(required))*100),"baseline":round(len(baseline)/max(1,len(metrics))*100),"missions":100 if mission_count else 0,"delivery":round(len(completed)/max(1,len(work_items))*100),"outcomes":round(len(results)/max(1,len(metrics))*100),"scale":100 if str(scale.get("recommendation") or "").strip() else 0};weights={"charter":.15,"data":.15,"baseline":.15,"missions":.10,"delivery":.15,"outcomes":.20,"scale":.10};score=round(sum(dimensions[k]*weights[k] for k in dimensions));attention=[]
    if dimensions["charter"]<100:attention.append("Completar e validar o contrato do piloto.")
    if required and dimensions["data"]<100:attention.append("Receber, mapear ou validar as fontes de dados obrigatórias.")
    if metrics and dimensions["baseline"]<100:attention.append("Completar a baseline das métricas prioritárias.")
    if not mission_count:attention.append("Ligar pelo menos uma missão governada ao piloto.")
    if blocked:attention.append(f"Resolver {len(blocked)} bloqueio(s) de implementação.")
    if metrics and dimensions["outcomes"]<100 and row.lifecycle_state in {"active","evaluating","scale_review"}:attention.append("Registar e rever resultados observados.")
    if row.lifecycle_state in {"evaluating","scale_review"} and dimensions["scale"]<100:attention.append("Registar a recomendação de escala, adaptação, repetição ou paragem.")
    return {"score":score,"dimensions":dimensions,"attention":attention,"blocked_count":len(blocked),"ready_for_execution":dimensions["charter"]==100 and dimensions["data"]>=50 and dimensions["baseline"]>=50 and mission_count>0,"ready_for_scale_decision":dimensions["outcomes"]==100 and dimensions["scale"]==100}
def _pilot_view(db:Session,row:Pilot,include_detail:bool=True)->dict[str,Any]:
    links=db.query(PilotMissionLink,CanonicalMission).join(CanonicalMission,CanonicalMission.id==PilotMissionLink.mission_id).filter(PilotMissionLink.pilot_id==row.id).order_by(PilotMissionLink.created_at).all();metrics=db.query(PilotMetric).filter(PilotMetric.pilot_id==row.id).order_by(PilotMetric.category,PilotMetric.created_at).all();sources=db.query(PilotDataSource).filter(PilotDataSource.pilot_id==row.id).order_by(PilotDataSource.required.desc(),PilotDataSource.created_at).all();items=db.query(PilotWorkItem).filter(PilotWorkItem.pilot_id==row.id).order_by(PilotWorkItem.sort_order,PilotWorkItem.created_at).all();readiness=_readiness(row,metrics,sources,items,len(links))
    view={"id":row.id,"code":row.code,"title":row.title,"sector_profile":row.sector_profile,"template_key":row.template_key,"program_source":row.program_source,"partner_name":row.partner_name,"context_name":row.context_name,"context_type":row.context_type,"location":row.location,"problem_statement":row.problem_statement,"decision_question":row.decision_question,"objective":row.objective,"scope":row.scope,"exclusions":row.exclusions,"sponsor":row.sponsor,"pilot_owner":row.pilot_owner,"data_owner":row.data_owner,"operator":row.operator,"reviewer":row.reviewer,"start_date":row.start_date,"end_date":row.end_date,"lifecycle_state":row.lifecycle_state,"revision":row.revision,"readiness":readiness,"created_at":row.created_at,"updated_at":row.updated_at}
    if include_detail:view.update(charter=_loads(row.charter_json,{}),data_readiness=_loads(row.data_readiness_json,{}),implementation=_loads(row.implementation_json,{}),scale=_loads(row.scale_json,{}),missions=[{"link_id":link.id,"link_role":link.link_role,"mission_id":mission.id,"code":mission.code,"title":mission.title,"lifecycle_state":mission.lifecycle_state,"revision":mission.revision} for link,mission in links],metrics=[_metric_view(m) for m in metrics],data_sources=[_data_source_view(s) for s in sources],work_items=[_work_item_view(i) for i in items],methodological_contract={"user_moments":USER_MOMENTS,"canonical_records":CANONICAL_RECORDS,"transversal_conditions":TRANSVERSAL_CONDITIONS,"human_authority":["formal_decision","authorization_to_execute","outcome_validation","learning_publication","pilot_scale_decision"]})
    return view
def _seed_template(db:Session,row:Pilot,template:dict[str,Any],user_id:str)->None:
    for m in template.get("metrics",[]):db.add(PilotMetric(pilot_id=row.id,metric_key=m["metric_key"],label=m["label"],category=m.get("category","operational"),unit=m.get("unit",""),direction=m.get("direction","decrease"),normalized_by=m.get("normalized_by",""),created_by_user_id=user_id))
    for s in template.get("data_sources",[]):db.add(PilotDataSource(pilot_id=row.id,name=s["name"],source_type=s.get("source_type","file"),system_name=s.get("system_name",""),data_format=s.get("data_format",""),required=bool(s.get("required",True)),created_by_user_id=user_id))
    for item in DEFAULT_WORK_ITEMS:db.add(PilotWorkItem(pilot_id=row.id,created_by_user_id=user_id,**item))

@router.get("/profiles")
def list_profiles(organization_id:str,_:Membership=Depends(require_org_role(*READ_ROLES)))->dict[str,Any]:return {"profiles":list(SECTOR_PROFILES.values()),"architecture":"universal_core_configurable_profiles","user_moments":USER_MOMENTS,"canonical_records":CANONICAL_RECORDS,"transversal_conditions":TRANSVERSAL_CONDITIONS}
@router.get("/templates")
def list_templates(organization_id:str,_:Membership=Depends(require_org_role(*READ_ROLES)))->dict[str,Any]:return {"templates":list(TEMPLATES.values()),"profiles":list(SECTOR_PROFILES.values())}
@router.get("/summary")
def pilot_summary(organization_id:str,_:Membership=Depends(require_org_role(*READ_ROLES)),db:Session=Depends(get_db))->dict[str,Any]:
    views=[_pilot_view(db,r,False) for r in db.query(Pilot).filter(Pilot.organization_id==organization_id).order_by(Pilot.updated_at.desc()).all()];active={"discovery","design","baseline","active","evaluating","scale_review"};return {"total":len(views),"active":sum(v["lifecycle_state"] in active for v in views),"require_attention":sum(bool(v["readiness"]["attention"]) for v in views),"ready_for_execution":sum(v["readiness"]["ready_for_execution"] for v in views),"ready_for_scale_decision":sum(v["readiness"]["ready_for_scale_decision"] for v in views),"pilots":views[:8]}
@router.get("")
def list_pilots(organization_id:str,_:Membership=Depends(require_org_role(*READ_ROLES)),db:Session=Depends(get_db))->list[dict[str,Any]]:return [_pilot_view(db,r,False) for r in db.query(Pilot).filter(Pilot.organization_id==organization_id).order_by(Pilot.updated_at.desc()).all()]
@router.post("",status_code=status.HTTP_201_CREATED)
def create_pilot(organization_id:str,payload:PilotCreate,membership:Membership=Depends(require_org_role(*WRITE_ROLES)),db:Session=Depends(get_db))->dict[str,Any]:
    template=deepcopy(TEMPLATES.get(payload.template_key) or TEMPLATES["universal_decision_pilot"]);profile=template.get("sector_profile") if payload.apply_template_defaults and payload.sector_profile=="cross_sector" else payload.sector_profile;charter=deepcopy(payload.charter);charter.setdefault("success_definition","");charter.setdefault("suspension_conditions","");charter.setdefault("deliverables",["Data Readiness Report","Baseline aprovada","Decision Dossier","Pilot Outcome Report","Scale Recommendation"]);charter.setdefault("template_scope_hint",template.get("scope_hint",""));data=deepcopy(payload.data_readiness);data.setdefault("integration_level","manual_and_structured_import");data.setdefault("privacy_conditions","");implementation=deepcopy(payload.implementation);implementation.setdefault("intervention","");implementation.setdefault("resources","");implementation.setdefault("risks","");implementation.setdefault("reversibility","");scale=deepcopy(payload.scale);scale.setdefault("recommendation","");scale.setdefault("conditions","");scale.setdefault("rollout_cost",None)
    row=Pilot(organization_id=organization_id,code=_next_code(db,organization_id),title=payload.title,sector_profile=profile,template_key=template["key"],program_source=payload.program_source,partner_name=payload.partner_name,context_name=payload.context_name,context_type=payload.context_type,location=payload.location,problem_statement=payload.problem_statement,decision_question=payload.decision_question,objective=payload.objective,scope=payload.scope or template.get("scope_hint",""),exclusions=payload.exclusions,sponsor=payload.sponsor,pilot_owner=payload.pilot_owner,data_owner=payload.data_owner,operator=payload.operator,reviewer=payload.reviewer,start_date=payload.start_date,end_date=payload.end_date,charter_json=_json(charter),data_readiness_json=_json(data),implementation_json=_json(implementation),scale_json=_json(scale),created_by_user_id=membership.user_id);db.add(row);db.flush()
    if payload.apply_template_defaults:_seed_template(db,row,template,membership.user_id)
    record_audit(db,action="pilot.created",resource_type="pilot",resource_id=row.id,organization_id=organization_id,user_id=membership.user_id,payload={"code":row.code,"template_key":row.template_key,"sector_profile":row.sector_profile,"program_source":row.program_source});db.commit();db.refresh(row);return _pilot_view(db,row)
@router.get("/{pilot_id}")
def get_pilot(organization_id:str,pilot_id:str,_:Membership=Depends(require_org_role(*READ_ROLES)),db:Session=Depends(get_db))->dict[str,Any]:return _pilot_view(db,_pilot_or_404(db,organization_id,pilot_id))
@router.patch("/{pilot_id}")
def update_pilot(organization_id:str,pilot_id:str,payload:PilotUpdate,membership:Membership=Depends(require_org_role(*WRITE_ROLES)),db:Session=Depends(get_db))->dict[str,Any]:
    row=_pilot_or_404(db,organization_id,pilot_id)
    if row.revision!=payload.expected_revision:raise HTTPException(status_code=409,detail={"code":"pilot_revision_conflict","message":"O piloto foi alterado. Atualize o conteúdo antes de repetir a edição.","current_revision":row.revision})
    scalars=("title","problem_statement","decision_question","objective","sector_profile","template_key","program_source","partner_name","context_name","context_type","location","scope","exclusions","sponsor","pilot_owner","data_owner","operator","reviewer","start_date","end_date","lifecycle_state");changed={}
    for name in scalars:
        if name in payload.model_fields_set:setattr(row,name,getattr(payload,name));changed[name]=getattr(payload,name)
    for name,column in {"charter":"charter_json","data_readiness":"data_readiness_json","implementation":"implementation_json","scale":"scale_json"}.items():
        if name in payload.model_fields_set and getattr(payload,name) is not None:setattr(row,column,_json(getattr(payload,name)));changed[name]=True
    if row.start_date and row.end_date and row.end_date<row.start_date:raise HTTPException(status_code=422,detail="A data final não pode anteceder a data inicial.")
    row.revision+=1;record_audit(db,action="pilot.revised",resource_type="pilot",resource_id=row.id,organization_id=organization_id,user_id=membership.user_id,payload={"revision":row.revision,"change_note":payload.change_note,"changed":changed});db.commit();db.refresh(row);return _pilot_view(db,row)
@router.post("/{pilot_id}/missions",status_code=status.HTTP_201_CREATED)
def link_mission(organization_id:str,pilot_id:str,payload:MissionLinkCreate,membership:Membership=Depends(require_org_role(*WRITE_ROLES)),db:Session=Depends(get_db))->dict[str,Any]:
    pilot=_pilot_or_404(db,organization_id,pilot_id);mission=db.query(CanonicalMission).filter(CanonicalMission.id==payload.mission_id,CanonicalMission.organization_id==organization_id).one_or_none()
    if mission is None:raise HTTPException(status_code=404,detail="Missão não encontrada")
    link=db.query(PilotMissionLink).filter(PilotMissionLink.pilot_id==pilot.id,PilotMissionLink.mission_id==mission.id).one_or_none()
    if link:link.link_role=payload.link_role
    else:db.add(PilotMissionLink(pilot_id=pilot.id,mission_id=mission.id,link_role=payload.link_role,created_by_user_id=membership.user_id))
    record_audit(db,action="pilot.mission_linked",resource_type="pilot",resource_id=pilot.id,organization_id=organization_id,user_id=membership.user_id,payload={"mission_id":mission.id,"mission_code":mission.code,"link_role":payload.link_role});db.commit();return _pilot_view(db,pilot)
@router.delete("/{pilot_id}/missions/{mission_id}",status_code=status.HTTP_204_NO_CONTENT)
def unlink_mission(organization_id:str,pilot_id:str,mission_id:str,membership:Membership=Depends(require_org_role(*WRITE_ROLES)),db:Session=Depends(get_db))->Response:
    pilot=_pilot_or_404(db,organization_id,pilot_id);link=db.query(PilotMissionLink).join(CanonicalMission,CanonicalMission.id==PilotMissionLink.mission_id).filter(PilotMissionLink.pilot_id==pilot.id,PilotMissionLink.mission_id==mission_id,CanonicalMission.organization_id==organization_id).one_or_none()
    if link is None:raise HTTPException(status_code=404,detail="Ligação não encontrada")
    db.delete(link);record_audit(db,action="pilot.mission_unlinked",resource_type="pilot",resource_id=pilot.id,organization_id=organization_id,user_id=membership.user_id,payload={"mission_id":mission_id});db.commit();return Response(status_code=204)
@router.post("/{pilot_id}/metrics",status_code=status.HTTP_201_CREATED)
def create_metric(organization_id:str,pilot_id:str,payload:MetricCreate,membership:Membership=Depends(require_org_role(*WRITE_ROLES)),db:Session=Depends(get_db))->dict[str,Any]:
    pilot=_pilot_or_404(db,organization_id,pilot_id);key=_slug(payload.metric_key or payload.label)
    if db.query(PilotMetric.id).filter(PilotMetric.pilot_id==pilot.id,PilotMetric.metric_key==key).first():raise HTTPException(status_code=409,detail="Já existe uma métrica com esta chave.")
    row=PilotMetric(pilot_id=pilot.id,metric_key=key,created_by_user_id=membership.user_id,**payload.model_dump(exclude={"metric_key"}));db.add(row);record_audit(db,action="pilot.metric_created",resource_type="pilot_metric",resource_id=row.id,organization_id=organization_id,user_id=membership.user_id,payload={"pilot_id":pilot.id,"metric_key":key});db.commit();db.refresh(row);return _metric_view(row)
@router.patch("/{pilot_id}/metrics/{metric_id}")
def update_metric(organization_id:str,pilot_id:str,metric_id:str,payload:MetricUpdate,membership:Membership=Depends(require_org_role(*WRITE_ROLES)),db:Session=Depends(get_db))->dict[str,Any]:
    pilot=_pilot_or_404(db,organization_id,pilot_id);row=db.query(PilotMetric).filter(PilotMetric.id==metric_id,PilotMetric.pilot_id==pilot.id).one_or_none()
    if row is None:raise HTTPException(status_code=404,detail="Métrica não encontrada")
    for name in payload.model_fields_set:setattr(row,name,getattr(payload,name))
    record_audit(db,action="pilot.metric_updated",resource_type="pilot_metric",resource_id=row.id,organization_id=organization_id,user_id=membership.user_id,payload={"pilot_id":pilot.id,"fields":sorted(payload.model_fields_set)});db.commit();db.refresh(row);return _metric_view(row)
@router.delete("/{pilot_id}/metrics/{metric_id}",status_code=status.HTTP_204_NO_CONTENT)
def delete_metric(organization_id:str,pilot_id:str,metric_id:str,membership:Membership=Depends(require_org_role(*WRITE_ROLES)),db:Session=Depends(get_db))->Response:
    pilot=_pilot_or_404(db,organization_id,pilot_id);row=db.query(PilotMetric).filter(PilotMetric.id==metric_id,PilotMetric.pilot_id==pilot.id).one_or_none()
    if row is None:raise HTTPException(status_code=404,detail="Métrica não encontrada")
    db.delete(row);record_audit(db,action="pilot.metric_deleted",resource_type="pilot_metric",resource_id=row.id,organization_id=organization_id,user_id=membership.user_id,payload={"pilot_id":pilot.id});db.commit();return Response(status_code=204)
@router.post("/{pilot_id}/data-sources",status_code=status.HTTP_201_CREATED)
def create_data_source(organization_id:str,pilot_id:str,payload:DataSourceCreate,membership:Membership=Depends(require_org_role(*WRITE_ROLES)),db:Session=Depends(get_db))->dict[str,Any]:
    pilot=_pilot_or_404(db,organization_id,pilot_id);row=PilotDataSource(pilot_id=pilot.id,created_by_user_id=membership.user_id,**payload.model_dump());db.add(row);record_audit(db,action="pilot.data_source_created",resource_type="pilot_data_source",resource_id=row.id,organization_id=organization_id,user_id=membership.user_id,payload={"pilot_id":pilot.id,"name":row.name});db.commit();db.refresh(row);return _data_source_view(row)
@router.patch("/{pilot_id}/data-sources/{source_id}")
def update_data_source(organization_id:str,pilot_id:str,source_id:str,payload:DataSourceUpdate,membership:Membership=Depends(require_org_role(*WRITE_ROLES)),db:Session=Depends(get_db))->dict[str,Any]:
    pilot=_pilot_or_404(db,organization_id,pilot_id);row=db.query(PilotDataSource).filter(PilotDataSource.id==source_id,PilotDataSource.pilot_id==pilot.id).one_or_none()
    if row is None:raise HTTPException(status_code=404,detail="Fonte de dados não encontrada")
    for name in payload.model_fields_set:setattr(row,name,getattr(payload,name))
    record_audit(db,action="pilot.data_source_updated",resource_type="pilot_data_source",resource_id=row.id,organization_id=organization_id,user_id=membership.user_id,payload={"pilot_id":pilot.id,"fields":sorted(payload.model_fields_set)});db.commit();db.refresh(row);return _data_source_view(row)
@router.delete("/{pilot_id}/data-sources/{source_id}",status_code=status.HTTP_204_NO_CONTENT)
def delete_data_source(organization_id:str,pilot_id:str,source_id:str,membership:Membership=Depends(require_org_role(*WRITE_ROLES)),db:Session=Depends(get_db))->Response:
    pilot=_pilot_or_404(db,organization_id,pilot_id);row=db.query(PilotDataSource).filter(PilotDataSource.id==source_id,PilotDataSource.pilot_id==pilot.id).one_or_none()
    if row is None:raise HTTPException(status_code=404,detail="Fonte de dados não encontrada")
    db.delete(row);record_audit(db,action="pilot.data_source_deleted",resource_type="pilot_data_source",resource_id=row.id,organization_id=organization_id,user_id=membership.user_id,payload={"pilot_id":pilot.id});db.commit();return Response(status_code=204)
@router.post("/{pilot_id}/work-items",status_code=status.HTTP_201_CREATED)
def create_work_item(organization_id:str,pilot_id:str,payload:WorkItemCreate,membership:Membership=Depends(require_org_role(*WRITE_ROLES)),db:Session=Depends(get_db))->dict[str,Any]:
    pilot=_pilot_or_404(db,organization_id,pilot_id);row=PilotWorkItem(pilot_id=pilot.id,created_by_user_id=membership.user_id,**payload.model_dump());db.add(row);record_audit(db,action="pilot.work_item_created",resource_type="pilot_work_item",resource_id=row.id,organization_id=organization_id,user_id=membership.user_id,payload={"pilot_id":pilot.id,"item_type":row.item_type});db.commit();db.refresh(row);return _work_item_view(row)
@router.patch("/{pilot_id}/work-items/{item_id}")
def update_work_item(organization_id:str,pilot_id:str,item_id:str,payload:WorkItemUpdate,membership:Membership=Depends(require_org_role(*WRITE_ROLES)),db:Session=Depends(get_db))->dict[str,Any]:
    pilot=_pilot_or_404(db,organization_id,pilot_id);row=db.query(PilotWorkItem).filter(PilotWorkItem.id==item_id,PilotWorkItem.pilot_id==pilot.id).one_or_none()
    if row is None:raise HTTPException(status_code=404,detail="Item de execução não encontrado")
    for name in payload.model_fields_set:setattr(row,name,getattr(payload,name))
    record_audit(db,action="pilot.work_item_updated",resource_type="pilot_work_item",resource_id=row.id,organization_id=organization_id,user_id=membership.user_id,payload={"pilot_id":pilot.id,"fields":sorted(payload.model_fields_set)});db.commit();db.refresh(row);return _work_item_view(row)
@router.delete("/{pilot_id}/work-items/{item_id}",status_code=status.HTTP_204_NO_CONTENT)
def delete_work_item(organization_id:str,pilot_id:str,item_id:str,membership:Membership=Depends(require_org_role(*WRITE_ROLES)),db:Session=Depends(get_db))->Response:
    pilot=_pilot_or_404(db,organization_id,pilot_id);row=db.query(PilotWorkItem).filter(PilotWorkItem.id==item_id,PilotWorkItem.pilot_id==pilot.id).one_or_none()
    if row is None:raise HTTPException(status_code=404,detail="Item de execução não encontrado")
    db.delete(row);record_audit(db,action="pilot.work_item_deleted",resource_type="pilot_work_item",resource_id=row.id,organization_id=organization_id,user_id=membership.user_id,payload={"pilot_id":pilot.id});db.commit();return Response(status_code=204)
@router.get("/{pilot_id}/report")
def pilot_report(organization_id:str,pilot_id:str,_:Membership=Depends(require_org_role(*READ_ROLES)),db:Session=Depends(get_db))->dict[str,Any]:
    pilot=_pilot_view(db,_pilot_or_404(db,organization_id,pilot_id));scorecard=[{"metric":m["label"],"category":m["category"],"baseline":m["baseline_value"],"target":m["target_value"],"result":m["current_value"],"unit":m["unit"],"change_pct":m["change_pct"],"status":m["status"],"source":m["source"],"method":m["method"],"limitations":m["limitations"],"confidence":m["confidence"]} for m in pilot["metrics"]]
    return {"schema":"sris.pilot-report.v1","generated_at":utcnow(),"pilot_brief":{k:pilot[k] for k in ("code","title","sector_profile","template_key","program_source","partner_name","context_name","context_type","location","problem_statement","decision_question","objective","scope","exclusions","start_date","end_date","lifecycle_state")},"governance":{"sponsor":pilot["sponsor"],"pilot_owner":pilot["pilot_owner"],"data_owner":pilot["data_owner"],"operator":pilot["operator"],"reviewer":pilot["reviewer"],"charter":pilot["charter"]},"data_readiness":{"assessment":pilot["data_readiness"],"sources":pilot["data_sources"]},"mission_dossier":{"missions":pilot["missions"],"canonical_records":CANONICAL_RECORDS,"user_moments":USER_MOMENTS},"implementation":{"plan":pilot["implementation"],"work_items":pilot["work_items"]},"outcome_scorecard":scorecard,"value_and_scale":{"scale":pilot["scale"],"readiness":pilot["readiness"],"rule":"Nenhum benefício é apresentado como realizado sem baseline, período, fonte, método e limitação de atribuição."},"methodological_integrity":pilot["methodological_contract"]}
