from datetime import datetime

from pydantic import BaseModel, Field


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None

    model_config = {"from_attributes": True}


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=256)
    display_name: str | None = Field(default=None, max_length=128)
    role: str = "user"
    is_active: bool = True


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=128)
    role: str | None = None
    is_active: bool | None = None


class PasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=256)
