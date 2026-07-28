import json
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import new_api_key
from app.core.encryption import encryption
from app.api.dependencies import principal, require_roles, Principal
from app.models.models import APIKey, Integration, WebhookEndpoint, Event
from app.schemas.domain import APIKeyCreate, IntegrationCreate, WebhookCreate, EventCreate
from app.services.audit import record_audit
router=APIRouter(prefix="/v1/integrations",tags=["integrations"])
@router.get("")
def list_integrations(p:Principal=Depends(require_roles("admin","manager")),db:Session=Depends(get_db)):
    return db.query(Integration).filter_by(organization_id=p.organization.id).all()
@router.post("")
def create_integration(body:IntegrationCreate,p:Principal=Depends(require_roles("admin")),db:Session=Depends(get_db)):
    obj=Integration(organization_id=p.organization.id,kind=body.kind,name=body.name,config_encrypted=encryption.encrypt(p.organization.id,json.dumps(body.config)))
    db.add(obj);record_audit(db,p.organization.id,p.user.id,"create","integration",obj.id,after={"kind":body.kind,"name":body.name});db.commit();return {"id":obj.id,"kind":obj.kind,"name":obj.name,"status":obj.status}
@router.post("/api-keys")
def create_key(body:APIKeyCreate,p:Principal=Depends(require_roles("admin")),db:Session=Depends(get_db)):
    raw,prefix,digest=new_api_key();obj=APIKey(organization_id=p.organization.id,name=body.name,prefix=prefix,key_hash=digest,scopes=body.scopes,created_by=p.user.id)
    db.add(obj);db.commit();return {"id":obj.id,"name":obj.name,"prefix":prefix,"api_key":raw,"warning":"This value is shown once."}
@router.get("/api-keys")
def list_keys(p:Principal=Depends(require_roles("admin")),db:Session=Depends(get_db)):
    return [{"id":x.id,"name":x.name,"prefix":x.prefix,"scopes":x.scopes,"active":x.active,"last_used_at":x.last_used_at} for x in db.query(APIKey).filter_by(organization_id=p.organization.id).all()]
@router.post("/webhooks")
def create_webhook(body:WebhookCreate,p:Principal=Depends(require_roles("admin")),db:Session=Depends(get_db)):
    import secrets
    secret=secrets.token_urlsafe(32);obj=WebhookEndpoint(organization_id=p.organization.id,url=body.url,events=body.events,secret_encrypted=encryption.encrypt(p.organization.id,secret));db.add(obj);db.commit();return {"id":obj.id,"secret":secret,"warning":"This value is shown once."}
@router.post("/ingest/events")
def ingest(body:EventCreate,request:Request,p:Principal=Depends(principal),db:Session=Depends(get_db)):
    if p.api_key and p.api_key.scopes and "events:write" not in p.api_key.scopes: raise HTTPException(403,"API key lacks events:write")
    obj=Event(organization_id=p.organization.id,mission_id=body.mission_id,event_type=body.event_type,title=body.title,source=body.source,payload=body.payload,quality=body.quality,confidence=body.confidence,limitations=body.limitations)
    db.add(obj);record_audit(db,p.organization.id,p.user.id if p.user else None,"ingest","events",obj.id,after={"source":body.source,"event_type":body.event_type});db.commit();return {"id":obj.id,"accepted":True}
