from pydantic import BaseModel, EmailStr, Field
class LoginRequest(BaseModel): email: EmailStr; password: str
class RefreshRequest(BaseModel): refresh_token: str
class TokenResponse(BaseModel): access_token: str; refresh_token: str; token_type: str="bearer"
class UserOut(BaseModel): id:str; email:EmailStr; full_name:str; is_platform_admin:bool
class MembershipOut(BaseModel): organization_id:str; organization_name:str; role:str
class MeResponse(BaseModel): user:UserOut; memberships:list[MembershipOut]
