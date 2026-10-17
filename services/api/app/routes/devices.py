"""Device pairing + web→desktop command relay.

Two audiences share this router:

* **The desktop companion** (unauthenticated at first) starts a pairing, polls
  for approval, then opens a WebSocket with its device token.
* **The signed-in web app** approves the code, lists devices, sends allowlisted
  commands, reads action history, and revokes devices.

Nothing here can run a shell or an unvalidated command: every action is checked
against `app.services.device_actions` before it is queued, and sensitive actions
still require an on-device confirmation from the human at that machine.
"""
from __future__ import annotations

import logging
import time
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database.base import utcnow
from app.database.session import get_sessionmaker
from app.deps import get_current_user, get_db
from app.models.device import ActionHistory, DevicePermission, PairedDevice
from app.models.user import User
from app.schemas.device import (
    ActionOut,
    DeviceActionOut,
    DeviceOut,
    PairingApproveRequest,
    PairingStartRequest,
    PairingStartResponse,
    PairingStatusResponse,
    SendCommandRequest,
    SendCommandResponse,
    UpdateDeviceRequest,
)
from app.services import device_actions, devices

log = logging.getLogger("mark_liv.devices")
router = APIRouter(tags=["devices"])

_TERMINAL_RESULT_STATUSES = {"approved", "denied", "success", "error"}
_ONLINE_STALE_SECONDS = 45


# ── helpers ───────────────────────────────────────────────────────────────────


def _device_out(device: PairedDevice) -> DeviceOut:
    online = devices.hub.is_online(device.id)
    if not online and device.last_seen_at is not None:
        last = device.last_seen_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        online = (utcnow() - last).total_seconds() < _ONLINE_STALE_SECONDS
    return DeviceOut(
        id=device.id,
        name=device.name,
        platform=device.platform,
        fingerprint=device.fingerprint,
        revoked=device.revoked,
        online=online,
        paired_at=device.paired_at,
        last_seen_at=device.last_seen_at,
        permissions=[
            {"permission": p.permission, "granted": p.granted}
            for p in device.permissions
        ],
    )


async def _owned_device(
    db: AsyncSession, user: User, device_id: str
) -> PairedDevice:
    stmt = (
        select(PairedDevice)
        .where(PairedDevice.id == device_id, PairedDevice.user_id == user.id)
        .options(selectinload(PairedDevice.permissions))
    )
    device = (await db.execute(stmt)).scalar_one_or_none()
    if device is None:
        # 404 not 403, so another account's device ids are indistinguishable.
        raise HTTPException(status_code=404, detail="Device not found.")
    return device


async def _touch_device(device_id: str) -> None:
    """Update last-seen without holding a session open across the socket."""
    try:
        async with get_sessionmaker()() as db:
            device = await db.get(PairedDevice, device_id)
            if device is not None:
                device.last_seen_at = utcnow()
                await db.commit()
    except Exception:  # noqa: BLE001 - telemetry must never break the socket
        log.debug("failed to update last_seen for %s", device_id, exc_info=True)


async def _record_result(device_id: str, message: dict) -> None:
    action_id = message.get("action_id")
    result_status = message.get("status")
    result_text = str(message.get("result", ""))[:2000]
    if not action_id or result_status not in _TERMINAL_RESULT_STATUSES:
        return
    try:
        async with get_sessionmaker()() as db:
            stmt = select(ActionHistory).where(
                ActionHistory.id == str(action_id),
                ActionHistory.device_id == device_id,
            )
            entry = (await db.execute(stmt)).scalar_one_or_none()
            if entry is None:
                return
            entry.status = result_status
            entry.result = result_text
            await db.commit()
    except Exception:  # noqa: BLE001
        log.exception("failed to record action result for %s", device_id)


# ── companion: unauthenticated pairing ────────────────────────────────────────


@router.post("/pairing/start", response_model=PairingStartResponse)
async def pairing_start(body: PairingStartRequest) -> PairingStartResponse:
    session = devices.pairings.start(body.name, body.platform, body.fingerprint)
    return PairingStartResponse(
        pairing_id=session.id,
        code=session.code,
        poll_token=session.poll_token,
        expires_in=int(session.expires_at - time.monotonic()),
        verification_hint=get_settings().web_app_url,
    )


@router.get("/pairing/{pairing_id}", response_model=PairingStatusResponse)
async def pairing_status(pairing_id: str, poll_token: str = "") -> PairingStatusResponse:
    session = devices.pairings.get(pairing_id, poll_token)
    if session is None:
        # Don't distinguish "unknown" from "wrong poll token".
        raise HTTPException(status_code=404, detail="Pairing not found.")
    return PairingStatusResponse(**session.public_status())


@router.websocket("/companion")
async def companion_socket(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token", "")
    if not token:
        await websocket.close(code=4401)
        return

    token_hash = devices.hash_device_token(token)
    async with get_sessionmaker()() as db:
        stmt = select(PairedDevice).where(
            PairedDevice.token_hash == token_hash,
            PairedDevice.revoked.is_(False),
        )
        device = (await db.execute(stmt)).scalar_one_or_none()
        if device is None:
            await websocket.close(code=4401)  # unknown or revoked credential
            return
        device_id = device.id
        device.last_seen_at = utcnow()
        await db.commit()

    await websocket.accept()
    await devices.hub.register(device_id, websocket)
    log.info("companion connected: %s", device_id)

    try:
        await websocket.send_json({"type": "paired", "device_id": device_id})
        while True:
            message = await websocket.receive_json()
            kind = message.get("type")
            if kind == "heartbeat":
                await _touch_device(device_id)
            elif kind == "result":
                await _record_result(device_id, message)
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 - a bad frame must not kill the worker
        log.exception("companion socket error for %s", device_id)
    finally:
        await devices.hub.unregister(device_id, websocket)
        await _touch_device(device_id)
        log.info("companion disconnected: %s", device_id)


# ── web: authenticated management ─────────────────────────────────────────────


@router.post("/pairing/approve", response_model=DeviceOut)
async def pairing_approve(
    body: PairingApproveRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeviceOut:
    session = devices.pairings.find_by_code(body.code)
    if session is None:
        raise HTTPException(
            status_code=404, detail="That code is invalid or has expired."
        )

    raw_token = devices.generate_device_token()
    device = PairedDevice(
        user_id=user.id,
        name=(body.name or session.name or "MARK LIV Desktop")[:120],
        platform=session.platform,
        fingerprint=session.fingerprint,
        token_hash=devices.hash_device_token(raw_token),
        paired_at=utcnow(),
        last_seen_at=None,
    )

    wanted = body.permissions
    if wanted is None:
        wanted = device_actions.default_permissions()
    # Only grant scopes that actually exist; ignore anything else silently.
    wanted_set = {p for p in wanted if p in device_actions.ALL_PERMISSIONS}
    for perm in device_actions.ALL_PERMISSIONS:
        device.permissions.append(
            DevicePermission(permission=perm, granted=perm in wanted_set)
        )

    db.add(device)
    await db.commit()
    await db.refresh(device, attribute_names=["permissions"])

    devices.pairings.approve(session, device.id, raw_token)
    log.info("device paired: %s for user %s", device.id, user.id)
    return _device_out(device)


@router.get("/catalog", response_model=list[DeviceActionOut])
async def action_catalog(user: User = Depends(get_current_user)) -> list[dict]:
    """The full allowlist, so the web UI can build a command form. These are the
    only actions the server will ever route to a device."""
    return [a.public() for a in device_actions.ACTIONS.values()]


@router.get("/actions", response_model=list[ActionOut])
async def list_actions(
    device_id: str | None = None,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ActionOut]:
    limit = max(1, min(limit, 200))
    stmt = (
        select(ActionHistory)
        .where(ActionHistory.user_id == user.id)
        .order_by(ActionHistory.created_at.desc())
        .limit(limit)
    )
    if device_id:
        stmt = stmt.where(ActionHistory.device_id == device_id)
    rows = list((await db.execute(stmt)).scalars().all())
    return [_action_out(r, device_actions.ACTIONS.get(r.action)) for r in rows]


@router.get("/actions/{action_id}", response_model=ActionOut)
async def get_action(
    action_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ActionOut:
    stmt = select(ActionHistory).where(
        ActionHistory.id == action_id, ActionHistory.user_id == user.id
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Action not found.")
    return _action_out(row, device_actions.ACTIONS.get(row.action))


@router.get("", response_model=list[DeviceOut])
async def list_devices(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[DeviceOut]:
    stmt = (
        select(PairedDevice)
        .where(PairedDevice.user_id == user.id)
        .options(selectinload(PairedDevice.permissions))
        .order_by(PairedDevice.paired_at.desc())
    )
    rows = list((await db.execute(stmt)).scalars().all())
    return [_device_out(d) for d in rows]


@router.patch("/{device_id}", response_model=DeviceOut)
async def update_device(
    device_id: str,
    body: UpdateDeviceRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeviceOut:
    device = await _owned_device(db, user, device_id)
    if body.name is not None:
        device.name = body.name.strip()[:120] or device.name
    if body.permissions is not None:
        wanted = {p for p in body.permissions if p in device_actions.ALL_PERMISSIONS}
        existing = {p.permission: p for p in device.permissions}
        for perm in device_actions.ALL_PERMISSIONS:
            if perm in existing:
                existing[perm].granted = perm in wanted
            else:
                device.permissions.append(
                    DevicePermission(permission=perm, granted=perm in wanted)
                )
    await db.commit()
    await db.refresh(device, attribute_names=["permissions"])
    return _device_out(device)


@router.delete("/{device_id}", status_code=204)
async def revoke_device(
    device_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    device = await _owned_device(db, user, device_id)
    device.revoked = True
    device.token_hash = ""  # the credential is dead the moment it is revoked
    await db.commit()
    # Close the live socket so the companion stops commanding the machine.
    try:
        await devices.hub.send(device.id, {"type": "revoked"})
    finally:
        await devices.hub.disconnect(device.id)
    return None


@router.post("/{device_id}/command", response_model=SendCommandResponse)
async def send_command(
    device_id: str,
    body: SendCommandRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SendCommandResponse:
    device = await _owned_device(db, user, device_id)
    if device.revoked:
        raise HTTPException(status_code=403, detail="This device has been revoked.")

    # 1. The action must be on the allowlist and its parameters valid.
    try:
        normalized = device_actions.validate(body.action, body.parameters)
    except device_actions.ActionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    action = device_actions.get_action(body.action)

    # 2. The device must have been granted the matching permission scope.
    granted = {p.permission for p in device.permissions if p.granted}
    if action.permission not in granted:
        raise HTTPException(
            status_code=403,
            detail=f"Permission '{action.permission}' is not granted to this device.",
        )

    # 3. The device must actually be connected.
    if not devices.hub.is_online(device.id):
        raise HTTPException(status_code=409, detail="That device is offline.")

    entry = ActionHistory(
        user_id=user.id,
        device_id=device.id,
        action=body.action,
        parameters=normalized,
        status="pending",
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    delivered = await devices.hub.send(
        device.id,
        {
            "type": "command",
            "action_id": entry.id,
            "action": body.action,
            "parameters": normalized,
            "requires_confirmation": action.requires_confirmation,
        },
    )
    if not delivered:
        entry.status = "error"
        entry.result = "Device went offline before the command could be delivered."
        await db.commit()
        raise HTTPException(status_code=409, detail="That device is offline.")

    return SendCommandResponse(
        action_id=entry.id,
        status="pending",
        requires_confirmation=action.requires_confirmation,
    )


def _action_out(row: ActionHistory, action: device_actions.DeviceAction | None) -> ActionOut:
    return ActionOut(
        id=row.id,
        device_id=row.device_id,
        action=row.action,
        parameters=row.parameters or {},
        status=row.status,
        result=row.result or "",
        created_at=row.created_at,
        requires_confirmation=bool(action and action.requires_confirmation),
    )
