from datetime import datetime

from pydantic import BaseModel, Field


class CreateLicenceRequest(BaseModel):
    tier: str = Field(min_length=2, max_length=80)
    products: list[str] = Field(default_factory=list)
    sports: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    max_devices: int = Field(default=1, ge=1, le=50)


class ActivateLicenceRequest(BaseModel):
    code: str
    device_id: str = Field(min_length=3, max_length=160)
    device_name: str | None = Field(default=None, max_length=160)


class ValidateLicenceRequest(BaseModel):
    device_id: str = Field(min_length=3, max_length=160)


class DeactivateDeviceRequest(BaseModel):
    device_id: str = Field(min_length=3, max_length=160)
