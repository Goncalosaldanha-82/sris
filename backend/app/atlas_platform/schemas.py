from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=10, max_length=200)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str
    is_active: bool


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PasswordRecoveryRequest(BaseModel):
    email: EmailStr
    recovery_token: str = Field(min_length=32, max_length=512)
    new_password: str = Field(min_length=12, max_length=200)


class PasswordRecoveryResponse(BaseModel):
    status: str


class InstitutionalAccessActivationRequest(BaseModel):
    email: EmailStr
    activation_token: str = Field(min_length=32, max_length=512)
    new_password: str = Field(min_length=12, max_length=200)
    full_name: str = Field(min_length=2, max_length=200)
    organization_name: str = Field(min_length=2, max_length=200)
    organization_slug: str = Field(
        pattern=r"^[a-z0-9-]+$",
        min_length=2,
        max_length=120,
    )


class InstitutionalAccessActivationResponse(BaseModel):
    status: str


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9-]+$", min_length=2, max_length=120)


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str


class MembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    organization_id: str
    role: str


class KnowledgeObjectCreate(BaseModel):
    object_type: str = Field(min_length=2, max_length=60)
    title: str = Field(min_length=3, max_length=300)
    summary: str = Field(min_length=3, max_length=20000)
    state: str = "candidate"
    source_path: str | None = None


class KnowledgeObjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    object_type: str
    title: str
    summary: str
    state: str
    source_path: str | None
