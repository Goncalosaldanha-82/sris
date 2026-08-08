from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.mission_intelligence.api import organization_router, public_router

from . import workflow_models  # noqa: F401
from .audit import record_audit
from .auth import current_user, require_org_role
from .config import environment_flag
from .database import get_db
from .models import KnowledgeObject, Membership, Organization, Role, User
from .schemas import (
    KnowledgeObjectCreate,
    KnowledgeObjectRead,
    LoginRequest,
    MembershipRead,
    OrganizationCreate,
    OrganizationRead,
    TokenResponse,
    UserCreate,
    UserRead,
)
from .security import create_access_token, hash_password, verify_password
from .workflow_api import router as workflow_router

app = FastAPI(
    title="SRIS Mission Intelligence API",
    version="1.4.0",
    description=(
        "Canonical mission intelligence, authentication, organizations, RBAC and "
        "the unified knowledge workflow."
    ),
)

app.include_router(workflow_router)
app.include_router(public_router)
app.include_router(organization_router)


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("select 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ok", "database": "ok"}


@app.post("/api/auth/register", response_model=UserRead, status_code=201)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    if not environment_flag("ATLAS_SELF_REGISTRATION_ENABLED", default=True):
        raise HTTPException(status_code=403, detail="Self-registration is disabled")
    if db.query(User).filter(User.email == payload.email.lower()).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    record_audit(
        db,
        action="user.registered",
        resource_type="user",
        resource_id=user.id,
        user_id=user.id,
    )
    db.commit()
    db.refresh(user)
    return user


@app.post("/api/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == payload.email.lower()).one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(access_token=create_access_token(user_id=user.id))


@app.get("/api/auth/me", response_model=UserRead)
def me(user: User = Depends(current_user)) -> User:
    return user


@app.post("/api/organizations", response_model=OrganizationRead, status_code=201)
def create_organization(
    payload: OrganizationCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Organization:
    if not environment_flag("ATLAS_ORGANIZATION_CREATION_ENABLED", default=True):
        raise HTTPException(status_code=403, detail="Organization creation is disabled")
    if db.query(Organization).filter(Organization.slug == payload.slug).first():
        raise HTTPException(status_code=409, detail="Organization slug already exists")

    organization = Organization(name=payload.name, slug=payload.slug)
    db.add(organization)
    db.flush()

    membership = Membership(
        user_id=user.id,
        organization_id=organization.id,
        role=Role.OWNER.value,
    )
    db.add(membership)
    record_audit(
        db,
        action="organization.created",
        resource_type="organization",
        resource_id=organization.id,
        organization_id=organization.id,
        user_id=user.id,
    )
    db.commit()
    db.refresh(organization)
    return organization


@app.get("/api/organizations", response_model=list[OrganizationRead])
def list_organizations(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[Organization]:
    return (
        db.query(Organization)
        .join(Membership, Membership.organization_id == Organization.id)
        .filter(Membership.user_id == user.id)
        .all()
    )


@app.get(
    "/api/organizations/{organization_id}/memberships",
    response_model=list[MembershipRead],
)
def list_memberships(
    organization_id: str,
    _: Membership = Depends(
        require_org_role(Role.OWNER.value, Role.ADMIN.value, Role.REVIEWER.value)
    ),
    db: Session = Depends(get_db),
) -> list[Membership]:
    return db.query(Membership).filter(Membership.organization_id == organization_id).all()


@app.post(
    "/api/organizations/{organization_id}/knowledge",
    response_model=KnowledgeObjectRead,
    status_code=201,
)
def create_knowledge_object(
    organization_id: str,
    payload: KnowledgeObjectCreate,
    membership: Membership = Depends(
        require_org_role(
            Role.OWNER.value,
            Role.ADMIN.value,
            Role.REVIEWER.value,
            Role.CONTRIBUTOR.value,
        )
    ),
    db: Session = Depends(get_db),
) -> KnowledgeObject:
    obj = KnowledgeObject(
        organization_id=organization_id,
        object_type=payload.object_type,
        title=payload.title,
        summary=payload.summary,
        state=payload.state,
        source_path=payload.source_path,
        created_by_user_id=membership.user_id,
    )
    db.add(obj)
    record_audit(
        db,
        action="knowledge.created",
        resource_type="knowledge_object",
        resource_id=obj.id,
        organization_id=organization_id,
        user_id=membership.user_id,
        payload={"object_type": payload.object_type},
    )
    db.commit()
    db.refresh(obj)
    return obj


@app.get(
    "/api/organizations/{organization_id}/knowledge",
    response_model=list[KnowledgeObjectRead],
)
def list_knowledge_objects(
    organization_id: str,
    _: Membership = Depends(
        require_org_role(
            Role.OWNER.value,
            Role.ADMIN.value,
            Role.REVIEWER.value,
            Role.CONTRIBUTOR.value,
            Role.OBSERVER.value,
        )
    ),
    db: Session = Depends(get_db),
) -> list[KnowledgeObject]:
    return (
        db.query(KnowledgeObject)
        .filter(KnowledgeObject.organization_id == organization_id)
        .order_by(KnowledgeObject.created_at.desc())
        .all()
    )
