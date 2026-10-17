from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PairingStartRequest(BaseModel):
    name: str = Field(default="MARK LIV Desktop", max_length=120)
    platform: str = Field(default="", max_length=40)
    fingerprint: str = Field(default="", max_length=128)


class PairingStartResponse(BaseModel):
    pairing_id: str
    code: str
    poll_token: str
    expires_in: int
    # Where the user types the code (the web app).
    verification_hint: str


class PairingStatusResponse(BaseModel):
    status: str  # pending | approved | denied | expired
    device_id: str | None = None
    device_token: str | None = None


class PairingApproveRequest(BaseModel):
    code: str = Field(min_length=4, max_length=12)
    name: str | None = Field(default=None, max_length=120)
    permissions: list[str] | None = None


class DevicePermissionOut(BaseModel):
    permission: str
    granted: bool

    model_config = {"from_attributes": True}


class DeviceOut(BaseModel):
    id: str
    name: str
    platform: str
    fingerprint: str
    revoked: bool
    online: bool
    paired_at: datetime | None
    last_seen_at: datetime | None
    permissions: list[DevicePermissionOut] = []

    model_config = {"from_attributes": True}


class DeviceActionOut(BaseModel):
    name: str
    description: str
    permission: str
    parameters: dict[str, dict[str, Any]]
    requires_confirmation: bool
    default_granted: bool


class UpdateDeviceRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    permissions: list[str] | None = None


class SendCommandRequest(BaseModel):
    action: str = Field(min_length=1, max_length=100)
    parameters: dict[str, Any] = Field(default_factory=dict)


class ActionOut(BaseModel):
    id: str
    device_id: str | None
    action: str
    parameters: dict[str, Any]
    status: str  # pending | approved | denied | success | error
    result: str
    created_at: datetime
    requires_confirmation: bool = False

    model_config = {"from_attributes": True}


class SendCommandResponse(BaseModel):
    action_id: str
    status: str
    requires_confirmation: bool
