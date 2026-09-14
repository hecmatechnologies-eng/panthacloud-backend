from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import UserRead


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72)
    full_name: str | None = Field(None, max_length=255)
    org_name: str | None = Field(None, max_length=255)


class TokenPayload(BaseModel):
    sub: str
    iat: int | None = None
    exp: int | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class OAuthAuthorizeUrlResponse(BaseModel):
    provider: str
    authorization_url: str
    state: str


class OAuthExchangeRequest(BaseModel):
    provider: str
    code: str
    state: str
    redirect_uri: str | None = None

