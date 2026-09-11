import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.membership import RoleEnum
from app.schemas.user import UserRead


class MembershipCreate(BaseModel):
    email: EmailStr
    role: RoleEnum = RoleEnum.MEMBER


class MembershipRoleUpdate(BaseModel):
    role: RoleEnum


class MembershipRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: RoleEnum
    created_at: datetime
    updated_at: datetime
    user: UserRead | None = None

    model_config = ConfigDict(from_attributes=True)
