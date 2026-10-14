from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    id: int
    username: str
    full_name: str
    role_name: str
    permissions: list[str]
    csrf_token: str


class CurrentUserResponse(BaseModel):
    id: int
    username: str
    full_name: str
    role_name: str
    permissions: list[str]
    csrf_token: str


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3)
    full_name: str = Field(min_length=1)
    role_name: str
    password: str = Field(min_length=8)
    is_active: bool = True
    must_change_password: bool = False


class UserUpdateRequest(BaseModel):
    full_name: str | None = None
    role_name: str | None = None
    is_active: bool | None = None
    must_change_password: bool | None = None


class UserPasswordRequest(BaseModel):
    password: str = Field(min_length=8)
    must_change_password: bool = False


class UserStatusRequest(BaseModel):
    is_active: bool


class UserResponse(BaseModel):
    id: int
    username: str
    full_name: str
    role_name: str
    is_active: bool
    must_change_password: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None
