from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import verify_password, create_token, decode_token
from app.core.config import settings
from app.models.models import User, Membership, Organization
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse
from app.api.dependencies import current_user
router=APIRouter(prefix="/auth",tags=["auth"])

def tokens(user):
    return TokenResponse(
        access_token=create_token(user.id,"access",minutes=settings.access_token_minutes,extra={"ver":user.token_version}),
        refresh_token=create_token(user.id,"refresh",days=settings.refresh_token_days,extra={"ver":user.token_version}))
@router.post("/login",response_model=TokenResponse)
def login(body:LoginRequest,db:Session=Depends(get_db)):
    user=db.query(User).filter(User.email==body.email.lower()).first()
    if not user or not verify_password(body.password,user.password_hash): raise HTTPException(401,"Invalid credentials")
    if not user.active: raise HTTPException(403,"Account disabled")
    user.last_login_at=datetime.now(timezone.utc);db.commit();return tokens(user)
@router.post("/refresh",response_model=TokenResponse)
def refresh(body:RefreshRequest,db:Session=Depends(get_db)):
    payload=decode_token(body.refresh_token,"refresh");user=db.get(User,payload["sub"])
    if not user or not user.active or user.token_version!=payload.get("ver"): raise HTTPException(401,"Refresh token revoked")
    return tokens(user)
@router.post("/logout-all")
def logout_all(user=Depends(current_user),db:Session=Depends(get_db)):
    user.token_version+=1;db.commit();return {"message":"All sessions revoked"}
@router.get("/me")
def me(user=Depends(current_user),db:Session=Depends(get_db)):
    ms=db.query(Membership,Organization).join(Organization,Membership.organization_id==Organization.id).filter(Membership.user_id==user.id,Membership.active.is_(True)).all()
    return {"user":{"id":user.id,"email":user.email,"full_name":user.full_name,"is_platform_admin":user.is_platform_admin},
            "memberships":[{"organization_id":o.id,"organization_name":o.name,"role":m.role} for m,o in ms]}
