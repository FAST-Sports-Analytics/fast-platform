from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=2, max_length=160)
    organisation_name: str = Field(min_length=2, max_length=180)
    country: str | None = Field(default=None, max_length=100)
    accept_terms: bool = False
    accept_dpa: bool = False
    confirm_admin_age: bool = False
    terms_version: str = Field(default="2026-08-20", max_length=40)
    dpa_version: str = Field(default="2026-08-20", max_length=40)
    privacy_version: str = Field(default="2026-08-20", max_length=40)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class VerifyEmailRequest(BaseModel):
    token: str


class SessionStatusRequest(BaseModel):
    device_id: str = Field(min_length=3, max_length=160)
    device_name: str | None = Field(default=None, max_length=160)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict
    licence: dict | None = None


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=20, max_length=500)
    new_password: str = Field(min_length=10, max_length=128)


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=20, max_length=500)
    new_password: str = Field(min_length=10, max_length=128)
