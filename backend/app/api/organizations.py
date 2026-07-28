import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from app.core.db import get_db
from app.core.security import hash_password
from app.models.models import Organization, User, Membership
from app.api.dependencies import principal, require_roles, Principal
from app.services.audit import record_audit
router=APIRouter(prefix="/organizations",tags=["organizations"])
class OrgCreate(BaseModel): name:str
class Invite(BaseModel): email:EmailStr; full_name:str=""; role:str="viewer"; temporary_password:str|None=None
@router.post("")
def create_org(body:OrgCreate, p:Principal=Depends(principal), db:Session=Depends(get_db)):
    # Platform admins may create additional orgs through an existing org context.
    if not p.user or not p.user.is_platform_admin: raise HTTPException(403,"Platform administrator required")
    slug=re.sub(r"[^a-z0-9]+","-",body.name.lower()).strip("-")
    if db.query(Organization).filter_by(slug=slug).first(): slug += "-" + str(db.query(Organization).count()+1)
    org=Organization(name=body.name,slug=slug);db.add(org);db.flush();db.add(Membership(organization_id=org.id,user_id=p.user.id,role="owner"));db.commit();return {"id":org.id,"name":org.name,"slug":org.slug}
@router.get("/current")
def current(p:Principal=Depends(principal)): return {"id":p.organization.id,"name":p.organization.name,"slug":p.organization.slug,"role":p.role}
@router.get("/members")
def members(p:Principal=Depends(require_roles("admin","manager","auditor")),db:Session=Depends(get_db)):
    rows=db.query(Membership,User).join(User,Membership.user_id==User.id).filter(Membership.organization_id==p.organization.id).all()
    return [{"id":m.id,"user_id":u.id,"email":u.email,"full_name":u.full_name,"role":m.role,"active":m.active} for m,u in rows]
@router.post("/members")
def invite(body:Invite,p:Principal=Depends(require_roles("admin")),db:Session=Depends(get_db)):
    user=db.query(User).filter(User.email==body.email.lower()).first()
    if not user:
        if not body.temporary_password: raise HTTPException(400,"temporary_password required for new user")
        user=User(email=body.email.lower(),full_name=body.full_name,password_hash=hash_password(body.temporary_password));db.add(user);db.flush()
    if db.query(Membership).filter_by(organization_id=p.organization.id,user_id=user.id).first(): raise HTTPException(409,"Membership already exists")
    m=Membership(organization_id=p.organization.id,user_id=user.id,role=body.role);db.add(m)
    record_audit(db,p.organization.id,p.user.id,"membership.create","membership",m.id,after={"email":user.email,"role":body.role})
    db.commit();return {"id":m.id,"user_id":user.id,"role":m.role}
