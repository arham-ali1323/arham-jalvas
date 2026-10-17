"""Desktop companion: the local half of web→desktop control.

The companion is what makes "MARK LIV, open Chrome on my computer" work. It:

1. **Pairs once.** It asks the backend for a short code, shows it, and polls
   until the signed-in user approves it on the website. Approval issues a
   long-lived device token, which is stored in the local config.
2. **Stays connected.** It holds a WebSocket to the backend (its credential in
   the URL, so it is never sent as a header the socket cannot set) and sends a
   heartbeat on a timer.
3. **Executes — carefully.** Each inbound command is validated and run through
   `core.desktop_actions`. Sensitive actions (shutdown, restart, lock, sleep)
   call the confirmation callback and are refused if there is none.

The design is deliberately decoupled from the Qt app: it takes callbacks for
status and confirmation and runs in its own thread, so it can be started, shown
and stopped without touching the UI internals. `main()` at the bottom is a
standalone entry point for testing and for `PyInstaller`.
"""
from __future__ import annotations

import json
import platform
import threading
import time
from typing import Any, Callable
from urllib.parse import urlencode

from core import desktop_actions

# How often to ping the server, and how long to wait for an inbound frame before
# sending one. Reconnect backoff doubles from the min up to the max.
HEARTBEAT_SECONDS = 20.0
_RECV_TIMEOUT = 1.0
_BACKOFF_MIN = 1.0
_BACKOFF_MAX = 30.0
_PAIR_TIMEOUT = 300.0
_PAIR_POLL_INTERVAL = 2.0

StatusCallback = Callable[[str], None]
ConfirmCallback = Callable[[str, dict[str, Any]], bool]
CodeCallback = Callable[[str, str], None]


class CompanionError(Exception):
    """A pairing or connection failure worth showing the user."""


def _ws_url(api_base_url: str, token: str) -> str:
    base = api_base_url.rstrip("/")
    if base.startswith("https://"):
        base = "wss://" + base[len("https://"):]
    elif base.startswith("http://"):
        base = "ws://" + base[len("http://"):]
    return f"{base}/devices/companion?{urlencode({'token': token})}"


class PairingClient:
    """The one-time handshake. Uses `requests` (already a desktop dependency)."""

    def __init__(self, api_base_url: str) -> None:
        self.base = api_base_url.rstrip("/")

    def start(self, name: str, plat: str, fingerprint: str) -> dict:
        import requests

        resp = requests.post(
            f"{self.base}/devices/pairing/start",
            json={"name": name, "platform": plat, "fingerprint": fingerprint},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def poll(self, pairing_id: str, poll_token: str) -> dict:
        import requests

        resp = requests.get(
            f"{self.base}/devices/pairing/{pairing_id}",
            params={"poll_token": poll_token},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def pair(
        self,
        *,
        name: str,
        on_code: CodeCallback,
        stop_event: threading.Event,
        plat: str | None = None,
        fingerprint: str = "",
        timeout: float = _PAIR_TIMEOUT,
    ) -> tuple[str, str]:
        """Run the handshake. Returns `(device_id, device_token)`.

        `on_code(code, verification_url)` is called once, so the caller can show
        the code to the human. Blocks until approved, denied, expired or timed
        out. Raises `CompanionError` on anything but approval."""
        started = self.start(name, plat or platform.system(), fingerprint)
        on_code(started["code"], started.get("verification_hint", ""))
        deadline = time.monotonic() + timeout
        while not stop_event.is_set() and time.monotonic() < deadline:
            status = self.poll(started["pairing_id"], started["poll_token"])
            state = status.get("status")
            if state == "approved":
                device_id = status.get("device_id")
                token = status.get("device_token")
                if not device_id or not token:
                    raise CompanionError("Server approved the pairing without a token.")
                return device_id, token
            if state in ("denied", "expired"):
                raise CompanionError(f"Pairing {state}.")
            stop_event.wait(_PAIR_POLL_INTERVAL)
        raise CompanionError("Pairing timed out.")


class DeviceCompanion:
    """Holds the device WebSocket and executes allowlisted commands."""

    def __init__(
        self,
        api_base_url: str,
        device_token: str,
        *,
        device_id: str = "",
        on_status: StatusCallback | None = None,
        confirm: ConfirmCallback | None = None,
        heartbeat_seconds: float = HEARTBEAT_SECONDS,
    ) -> None:
        self.api_base_url = api_base_url
        self.device_token = device_token
        self.device_id = device_id
        self.on_status = on_status or (lambda _m: None)
        self.confirm = confirm
        self.heartbeat_seconds = heartbeat_seconds
        # Set True when the server revokes this device; the caller clears the
        # stored token afterwards.
        self.revoked = False

    def _connect(self):  # pragma: no cover - exercised via tests with a fake
        from websockets.sync.client import connect

        return connect(_ws_url(self.api_base_url, self.device_token), open_timeout=15)

    def handle_command(self, message: dict[str, Any]) -> dict[str, Any]:
        """Execute one command frame and return the result frame to send back."""
        action_id = message.get("action_id")
        action = message.get("action", "")
        params = message.get("parameters") or {}
        status, text = desktop_actions.execute(action, params, confirm=self.confirm)
        return {
            "type": "result",
            "action_id": action_id,
            "status": status,
            "result": text,
        }

    def _serve(self, connection, stop_event: threading.Event) -> None:
        last_ping = time.monotonic()
        while not stop_event.is_set():
            try:
                raw = connection.recv(timeout=_RECV_TIMEOUT)
            except TimeoutError:
                raw = None
            except Exception as exc:  # noqa: BLE001 - connection dropped
                self.on_status(f"Connection lost: {exc}")
                return

            if raw is not None:
                try:
                    message = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                kind = message.get("type")
                if kind == "command":
                    self.on_status(f"Executing {message.get('action')}…")
                    result = self.handle_command(message)
                    try:
                        connection.send(json.dumps(result))
                    except Exception:  # noqa: BLE001
                        return
                    self.on_status(f"{result['status']}: {result['result']}")
                elif kind == "revoked":
                    self.revoked = True
                    self.on_status("This device was unpaired from the website.")
                    return

            now = time.monotonic()
            if now - last_ping >= self.heartbeat_seconds:
                try:
                    connection.send(json.dumps({"type": "heartbeat"}))
                except Exception:  # noqa: BLE001
                    return
                last_ping = now

    def run(self, stop_event: threading.Event) -> None:
        """Connect and serve until stopped, reconnecting with backoff.

        Its own connection only: a dropped socket retries, but it never loops
        forever at full speed — the delay doubles up to `_BACKOFF_MAX`."""
        backoff = _BACKOFF_MIN
        while not stop_event.is_set():
            if backoff >= _BACKOFF_MAX:
                self.on_status(
                    "Could not reach the server. Retrying less often…"
                )
            try:
                connection = self._connect()
            except Exception as exc:  # noqa: BLE001
                self.on_status(f"Connect failed, retrying: {exc}")
                if stop_event.wait(backoff):
                    return
                backoff = min(_BACKOFF_MAX, backoff * 2)
                continue

            self.on_status("Connected — this computer is available to your account.")
            backoff = _BACKOFF_MIN
            try:
                with connection:
                    self._serve(connection, stop_event)
            except Exception as exc:  # noqa: BLE001
                self.on_status(f"Disconnected: {exc}")
            if self.revoked or stop_event.is_set():
                return
            self.on_status("Reconnecting…")
            if stop_event.wait(backoff):
                return


class CompanionThread:
    """Runs pairing (if needed) and the connection loop on a daemon thread."""

    def __init__(
        self,
        api_base_url: str,
        *,
        on_status: StatusCallback | None = None,
        on_code: CodeCallback | None = None,
        confirm: ConfirmCallback | None = None,
    ) -> None:
        self.api_base_url = api_base_url
        self.on_status = on_status or (lambda _m: None)
        self.on_code = on_code or (lambda _c, _u: None)
        self.confirm = confirm
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="mark-liv-companion", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        from memory import config_manager as cfg

        conf = cfg.get_companion_config()
        token = conf.get("device_token") or ""
        device_id = conf.get("device_id") or ""

        if not token:
            try:
                client = PairingClient(self.api_base_url)
                device_id, token = client.pair(
                    name=conf.get("name") or f"MARK LIV on {platform.node() or 'PC'}",
                    on_code=self.on_code,
                    stop_event=self._stop,
                    fingerprint=_fingerprint(),
                )
            except CompanionError as exc:
                self.on_status(f"Pairing failed: {exc}")
                return
            except Exception as exc:  # noqa: BLE001
                self.on_status(f"Pairing failed: {exc}")
                return
            cfg.save_companion_config(
                api_base_url=self.api_base_url,
                device_id=device_id,
                device_token=token,
            )

        companion = DeviceCompanion(
            self.api_base_url,
            token,
            device_id=device_id,
            on_status=self.on_status,
            confirm=self.confirm,
        )
        companion.run(self._stop)
        if companion.revoked:
            cfg.clear_companion_token()


def _fingerprint() -> str:
    """A stable, non-identifying hint so the same machine re-pairs recognisably."""
    import hashlib

    raw = f"{platform.node()}|{platform.system()}|{platform.machine()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def main(argv: list[str] | None = None) -> int:
    """Standalone entry point: `python -m core.device_companion --api URL`.

    Prints the pairing code to the console and runs until interrupted. Useful
    for manual testing and as the PyInstaller companion target."""
    import argparse

    parser = argparse.ArgumentParser(description="MARK LIV desktop companion")
    parser.add_argument("--api", required=True, help="Base URL of the MARK LIV API")
    args = parser.parse_args(argv)

    stop = threading.Event()

    def on_status(msg: str) -> None:
        print(f"[Companion] {msg}")

    def on_code(code: str, url: str) -> None:
        print("\n" + "=" * 52)
        print(f"  Pair this computer on {url or 'the MARK LIV website'}")
        print(f"  Pairing code:  {code}")
        print("=" * 52 + "\n")

    def confirm(action: str, params: dict[str, Any]) -> bool:
        answer = input(f"Allow '{action}' from the website? [y/N] ").strip().lower()
        return answer == "y"

    thread = CompanionThread(
        args.api, on_status=on_status, on_code=on_code, confirm=confirm
    )
    thread.start()
    try:
        while thread._thread and thread._thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        on_status("Stopping…")
    finally:
        thread.stop()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
