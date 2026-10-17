"""Tests for device pairing and the web→desktop command relay (Phase 6).

The command path is exercised end to end: the companion WebSocket handler is
run as a real coroutine against a fake socket, commands are pushed through the
HTTP API, and results flow back — all in the same event loop as the test, so no
network, no real desktop, and no second process are involved.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import WebSocketDisconnect

from app.routes import devices as devices_route
from app.services import device_actions, devices

from tests.conftest import register

_DISCONNECT = object()


@pytest.fixture(autouse=True)
def _reset_in_process_stores():
    """The pairing store and hub are process-global; isolate every test."""
    devices.hub._sockets.clear()
    devices.pairings = devices.PairingStore()
    yield
    devices.hub._sockets.clear()
    devices.pairings = devices.PairingStore()


# ── Unit: the allowlist ───────────────────────────────────────────────────────

def test_validate_rejects_unknown_action():
    with pytest.raises(device_actions.ActionValidationError):
        device_actions.validate("run_shell", {"cmd": "rm -rf /"})


def test_validate_rejects_unexpected_and_bad_params():
    with pytest.raises(device_actions.ActionValidationError):
        device_actions.validate("open_app", {"app": "calc", "extra": 1})
    with pytest.raises(device_actions.ActionValidationError):
        device_actions.validate("open_app", {"app": "bad;rm -rf"})
    with pytest.raises(device_actions.ActionValidationError):
        device_actions.validate("browser.navigate", {"url": "javascript:alert(1)"})
    with pytest.raises(device_actions.ActionValidationError):
        device_actions.validate("volume.set", {"level": 200})


def test_validate_normalises_good_params():
    assert device_actions.validate("open_app", {"app": "  Chrome "}) == {"app": "Chrome"}
    assert device_actions.validate("volume.set", {"level": 42}) == {"level": 42}
    assert device_actions.validate("notification.send", {"title": "Hi"}) == {
        "title": "Hi",
        "body": "",
    }


def test_sensitive_actions_require_confirmation_and_are_not_default():
    assert device_actions.ACTIONS["power.shutdown"].requires_confirmation is True
    assert device_actions.PERMISSION_POWER not in device_actions.default_permissions()
    assert device_actions.PERMISSION_APP_LAUNCH in device_actions.default_permissions()


# ── HTTP: pairing handshake ───────────────────────────────────────────────────

async def _auth(client) -> dict:
    tokens = await register(client)
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _pair(client, headers) -> tuple[dict, str]:
    """Run the full handshake and return (device, device_token)."""
    start = await client.post(
        "/devices/pairing/start",
        json={"name": "Test PC", "platform": "Windows", "fingerprint": "abc"},
    )
    assert start.status_code == 200, start.text
    pairing = start.json()

    pending = await client.get(
        f"/devices/pairing/{pairing['pairing_id']}",
        params={"poll_token": pairing["poll_token"]},
    )
    assert pending.json()["status"] == "pending"

    approved = await client.post(
        "/devices/pairing/approve", json={"code": pairing["code"]}, headers=headers
    )
    assert approved.status_code == 200, approved.text
    device = approved.json()

    status = await client.get(
        f"/devices/pairing/{pairing['pairing_id']}",
        params={"poll_token": pairing["poll_token"]},
    )
    body = status.json()
    assert body["status"] == "approved"
    assert body["device_token"]
    return device, body["device_token"]


async def test_pairing_requires_auth_to_approve(client):
    resp = await client.post("/devices/pairing/approve", json={"code": "ABCDEF"})
    assert resp.status_code == 401


async def test_full_pairing_flow(client):
    headers = await _auth(client)
    device, token = await _pair(client, headers)
    assert device["name"] == "Test PC"
    assert device["online"] is False
    granted = {p["permission"] for p in device["permissions"] if p["granted"]}
    assert device_actions.PERMISSION_APP_LAUNCH in granted
    assert device_actions.PERMISSION_POWER not in granted
    assert token and len(token) > 20

    listing = await client.get("/devices", headers=headers)
    assert listing.status_code == 200
    assert [d["id"] for d in listing.json()] == [device["id"]]


async def test_approve_with_wrong_code_is_404(client):
    headers = await _auth(client)
    resp = await client.post(
        "/devices/pairing/approve", json={"code": "ZZZZZZ"}, headers=headers
    )
    assert resp.status_code == 404


async def test_pairing_status_wrong_poll_token_is_404(client):
    start = await client.post("/devices/pairing/start", json={})
    pairing = start.json()
    resp = await client.get(
        f"/devices/pairing/{pairing['pairing_id']}", params={"poll_token": "wrong"}
    )
    assert resp.status_code == 404


async def test_catalog_lists_allowlist(client):
    headers = await _auth(client)
    resp = await client.get("/devices/catalog", headers=headers)
    names = {a["name"] for a in resp.json()}
    assert {"open_app", "browser.navigate", "system.info"} <= names
    assert "run_shell" not in names


# ── HTTP: command validation / gating ─────────────────────────────────────────

async def test_command_rejected_for_unknown_action(client):
    headers = await _auth(client)
    device, _ = await _pair(client, headers)
    resp = await client.post(
        f"/devices/{device['id']}/command",
        json={"action": "run_shell", "parameters": {"cmd": "whoami"}},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_command_rejected_when_device_offline(client):
    headers = await _auth(client)
    device, _ = await _pair(client, headers)
    resp = await client.post(
        f"/devices/{device['id']}/command",
        json={"action": "open_app", "parameters": {"app": "Chrome"}},
        headers=headers,
    )
    assert resp.status_code == 409


async def test_command_rejected_without_permission(client):
    headers = await _auth(client)
    device, _ = await _pair(client, headers)
    # Power actions are not granted by default.
    resp = await client.post(
        f"/devices/{device['id']}/command",
        json={"action": "power.shutdown", "parameters": {}},
        headers=headers,
    )
    assert resp.status_code == 403


async def test_command_cannot_touch_another_users_device(client):
    headers_a = await _auth(client)
    device, _ = await _pair(client, headers_a)

    reg_b = await client.post(
        "/auth/register",
        json={"email": "other@example.com", "password": "supersecret1"},
    )
    headers_b = {"Authorization": f"Bearer {reg_b.json()['access_token']}"}
    resp = await client.post(
        f"/devices/{device['id']}/command",
        json={"action": "open_app", "parameters": {"app": "Chrome"}},
        headers=headers_b,
    )
    assert resp.status_code == 404


async def test_revoke_marks_device_and_blocks_commands(client):
    headers = await _auth(client)
    device, _ = await _pair(client, headers)
    resp = await client.delete(f"/devices/{device['id']}", headers=headers)
    assert resp.status_code == 204

    listing = (await client.get("/devices", headers=headers)).json()
    assert listing[0]["revoked"] is True
    # A revoked device can no longer be commanded.
    cmd = await client.post(
        f"/devices/{device['id']}/command",
        json={"action": "open_app", "parameters": {"app": "Chrome"}},
        headers=headers,
    )
    assert cmd.status_code == 403


# ── WebSocket: full round trip through the handler ────────────────────────────

class FakeWebSocket:
    """Enough of a Starlette WebSocket for the companion handler."""

    def __init__(self, query: dict[str, str]) -> None:
        self.query_params = query
        self.sent_json: list[dict] = []
        self.accepted = False
        self.closed_code: int | None = None
        self._queue: asyncio.Queue = asyncio.Queue()

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int = 1000) -> None:
        self.closed_code = code

    async def send_json(self, data: dict) -> None:
        self.sent_json.append(data)

    async def receive_json(self) -> dict:
        item = await self._queue.get()
        if item is _DISCONNECT:
            raise WebSocketDisconnect(code=1000)
        return item

    def feed(self, message: dict) -> None:
        self._queue.put_nowait(message)

    def disconnect(self) -> None:
        self._queue.put_nowait(_DISCONNECT)


async def _wait_until(predicate, timeout: float = 2.0) -> None:
    waited = 0.0
    while not predicate() and waited < timeout:
        await asyncio.sleep(0.01)
        waited += 0.01
    assert predicate(), "condition not met before timeout"


async def test_companion_socket_full_command_round_trip(client):
    headers = await _auth(client)
    device, token = await _pair(client, headers)

    # Enable power so we can also verify the confirmation flag is surfaced.
    await client.patch(
        f"/devices/{device['id']}",
        json={"permissions": list(device_actions.ALL_PERMISSIONS)},
        headers=headers,
    )

    ws = FakeWebSocket({"token": token})
    task = asyncio.create_task(devices_route.companion_socket(ws))
    await _wait_until(lambda: devices.hub.is_online(device["id"]))
    assert ws.accepted
    assert ws.sent_json[0]["type"] == "paired"

    # Send a normal command and let the fake desktop answer it.
    sent = await client.post(
        f"/devices/{device['id']}/command",
        json={"action": "open_app", "parameters": {"app": "Chrome"}},
        headers=headers,
    )
    assert sent.status_code == 200, sent.text
    action_id = sent.json()["action_id"]
    assert sent.json()["requires_confirmation"] is False

    await _wait_until(
        lambda: any(
            m.get("type") == "command" and m.get("action_id") == action_id
            for m in ws.sent_json
        )
    )
    command = next(m for m in ws.sent_json if m.get("action_id") == action_id)
    assert command["action"] == "open_app"
    assert command["parameters"] == {"app": "Chrome"}

    ws.feed(
        {
            "type": "result",
            "action_id": action_id,
            "status": "success",
            "result": "Chrome opened",
        }
    )
    # Poll the action endpoint until the recorded result appears.
    for _ in range(100):
        got = await client.get(f"/devices/actions/{action_id}", headers=headers)
        if got.json()["status"] == "success":
            break
        await asyncio.sleep(0.02)
    else:
        raise AssertionError("result was never recorded")

    assert got.json()["result"] == "Chrome opened"

    # A sensitive action is flagged for on-device confirmation.
    shutdown = await client.post(
        f"/devices/{device['id']}/command",
        json={"action": "power.shutdown", "parameters": {}},
        headers=headers,
    )
    assert shutdown.status_code == 200
    assert shutdown.json()["requires_confirmation"] is True

    ws.disconnect()
    await asyncio.wait_for(task, timeout=2)
    assert not devices.hub.is_online(device["id"])


async def test_companion_socket_rejects_bad_token(client):
    ws = FakeWebSocket({"token": "not-a-real-token"})
    await devices_route.companion_socket(ws)
    assert ws.accepted is False
    assert ws.closed_code == 4401
