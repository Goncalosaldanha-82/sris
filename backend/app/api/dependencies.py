from dataclasses import dataclass
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.db import get_db
from app.core.security import decode_token, hash_api_key
from app.models.models import User, Membership, Organization, APIKey

bearer=HTTPBearer(auto_error=False)
@dataclass
class Principal:
    user: User|None
    organization: Organization
    role: str
    api_key: APIKey|None=None

async def current_user(credentials: HTTPAuthorizationCredentials=Depends(bearer), db:Session=Depends(get_db)):
    if not credentials: raise HTTPException(401,"Authentication required")
    payload=decode_token(credentials.credentials,"access")
    user=db.get(User,payload["sub"])
    if not user or not user.active or user.token_version != payload.get("ver"):
        raise HTTPException(401,"Inactive or revoked user")
    return user

async def principal(
    x_organization_id: str|None=Header(None, alias="X-Organization-ID"),
    x_api_key: str|None=Header(None, alias="X-API-Key"),
    credentials: HTTPAuthorizationCredentials=Depends(bearer),
    db:Session=Depends(get_db)
):
    if not x_organization_id: raise HTTPException(400,"X-Organization-ID header required")
    org=db.get(Organization,x_organization_id)
    if not org or not org.active: raise HTTPException(404,"Organization not found")
    # RLS context is set before any tenant-scoped query, including API keys.
    if db.bind and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT set_config('app.current_organization_id', :org_id, true)"), {"org_id": x_organization_id})
    if x_api_key:
        key=db.query(APIKey).filter(APIKey.organization_id==x_organization_id, APIKey.key_hash==hash_api_key(x_api_key), APIKey.active.is_(True)).first()
        if not key: raise HTTPException(401,"Invalid API key")
        return Principal(None,org,"api",key)
    if not credentials: raise HTTPException(401,"Authentication required")
    payload=decode_token(credentials.credentials,"access")
    user=db.get(User,payload["sub"])
    if not user or not user.active or user.token_version != payload.get("ver"): raise HTTPException(401,"Invalid principal")
    membership=db.query(Membership).filter_by(organization_id=x_organization_id,user_id=user.id,active=True).first()
    if not membership and not user.is_platform_admin: raise HTTPException(403,"No access to this organization")
    return Principal(user,org,membership.role if membership else "owner",None)

def require_roles(*roles):
    async def dep(p:Principal=Depends(principal)):
        if p.role not in roles and p.role!="owner": raise HTTPException(403,"Insufficient permissions")
        return p
    return dep
