"""The desktop companion: URL building, the pairing handshake, command execution
over a (fake) socket, revocation, and token persistence.

No real network is used. `PairingClient.start/poll` are stubbed and the socket is
a `FakeConnection`, so the whole file runs offline and instantly.

    python -m pytest tests/test_device_companion.py
"""
import json
import threading
import time
import unittest
from unittest import mock

from core import device_companion as dc
from core import desktop_actions as da


class FakeConnection:
    """Stands in for a websockets sync client.

    Scripted: `frames` are returned by `recv`, then `recv` raises `TimeoutError`
    forever (the timeout the real client raises when nothing arrives). Stops
    early when the loop asks it to (a simple frame count cap) so a buggy loop
    cannot hang the suite."""

    def __init__(self, frames=None, cap=50):
        self._frames = list(frames or [])
        self.sent = []
        self._cap = cap
        self.closed = False

    def recv(self, timeout=None):
        if self._frames:
            return self._frames.pop(0)
        if self._cap <= 0:
            raise AssertionError("companion loop did not stop")
        self._cap -= 1
        raise TimeoutError()

    def send(self, data):
        self.sent.append(json.loads(data))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True
        return False


class TestWsUrl(unittest.TestCase):
    def test_http_becomes_ws(self):
        url = dc._ws_url("http://localhost:8000", "tok")
        self.assertEqual(url, "ws://localhost:8000/devices/companion?token=tok")

    def test_https_becomes_wss(self):
        url = dc._ws_url("https://api.example.com/", "abc")
        self.assertEqual(url, "wss://api.example.com/devices/companion?token=abc")

    def test_token_is_url_encoded(self):
        url = dc._ws_url("https://api.example.com", "a b/c")
        self.assertIn("token=a+b%2Fc", url)


class ScriptedPairing(dc.PairingClient):
    """A PairingClient whose start/poll come from a fixed script."""

    def __init__(self, statuses):
        super().__init__("http://api.test")
        self._statuses = list(statuses)
        self.polled = 0

    def start(self, name, plat, fingerprint):
        return {
            "pairing_id": "p1",
            "poll_token": "pt",
            "code": "ABC123",
            "verification_hint": "http://web.test/devices",
        }

    def poll(self, pairing_id, poll_token):
        self.polled += 1
        # Keep returning "pending" once the scripted statuses run out, so the
        # timeout test has something to time out against.
        return self._statuses.pop(0) if self._statuses else {"status": "pending"}


class TestPairing(unittest.TestCase):
    def _run(self, statuses, timeout=5.0):
        seen = []
        client = ScriptedPairing(statuses)
        with mock.patch.object(dc, "_PAIR_POLL_INTERVAL", 0.001):
            result = client.pair(
                name="PC",
                on_code=lambda code, url: seen.append((code, url)),
                stop_event=threading.Event(),
                timeout=timeout,
            )
        return result, seen, client

    def test_approved_returns_token(self):
        result, seen, client = self._run(
            [{"status": "pending"}, {"status": "approved",
                                     "device_id": "d1", "device_token": "t1"}]
        )
        self.assertEqual(result, ("d1", "t1"))
        self.assertEqual(seen, [("ABC123", "http://web.test/devices")])
        self.assertEqual(client.polled, 2)

    def test_denied_raises(self):
        with self.assertRaises(dc.CompanionError):
            self._run([{"status": "denied"}])

    def test_expired_raises(self):
        with self.assertRaises(dc.CompanionError):
            self._run([{"status": "expired"}])

    def test_timeout_raises(self):
        with self.assertRaises(dc.CompanionError):
            self._run([{"status": "pending"}], timeout=0.01)

    def test_approved_without_token_raises(self):
        with self.assertRaises(dc.CompanionError):
            self._run([{"status": "approved", "device_id": "d1"}])

    def test_stop_event_aborts(self):
        stop = threading.Event()
        stop.set()
        client = ScriptedPairing([{"status": "pending"}])
        with self.assertRaises(dc.CompanionError):
            client.pair(
                name="PC",
                on_code=lambda *_: None,
                stop_event=stop,
                timeout=5.0,
            )


class TestHandleCommand(unittest.TestCase):
    def test_unknown_action_reports_error(self):
        c = dc.DeviceCompanion("http://api.test", "tok")
        result = c.handle_command(
            {"type": "command", "action_id": "a1", "action": "rm.rf", "parameters": {}}
        )
        self.assertEqual(result["type"], "result")
        self.assertEqual(result["action_id"], "a1")
        self.assertEqual(result["status"], "error")

    def test_successful_action(self):
        original = da.ACTIONS["system.info"]["handler"]
        da.ACTIONS["system.info"]["handler"] = lambda p: "all good"
        try:
            c = dc.DeviceCompanion("http://api.test", "tok")
            result = c.handle_command(
                {"action_id": "a2", "action": "system.info", "parameters": {}}
            )
        finally:
            da.ACTIONS["system.info"]["handler"] = original
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result"], "all good")

    def test_confirmation_callback_is_passed_through(self):
        original = da.ACTIONS["power.shutdown"]["handler"]
        da.ACTIONS["power.shutdown"]["handler"] = lambda p: "bye"
        asked = []
        try:
            c = dc.DeviceCompanion(
                "http://api.test", "tok",
                confirm=lambda a, p: asked.append(a) or True,
            )
            result = c.handle_command(
                {"action_id": "a3", "action": "power.shutdown", "parameters": {}}
            )
        finally:
            da.ACTIONS["power.shutdown"]["handler"] = original
        self.assertEqual(result["status"], "success")
        self.assertEqual(asked, ["power.shutdown"])


class TestServeLoop(unittest.TestCase):
    def _companion(self, confirm=None):
        return dc.DeviceCompanion(
            "http://api.test", "tok",
            on_status=lambda _m: None,
            confirm=confirm,
            heartbeat_seconds=0.0,
        )

    def test_command_executed_and_result_sent(self):
        original = da.ACTIONS["system.info"]["handler"]
        da.ACTIONS["system.info"]["handler"] = lambda p: "metrics"
        try:
            companion = self._companion()
            frame = json.dumps(
                {"type": "command", "action_id": "c1",
                 "action": "system.info", "parameters": {}}
            )
            conn = FakeConnection(frames=[frame])
            companion._serve(conn, threading.Event())
        finally:
            da.ACTIONS["system.info"]["handler"] = original
        results = [m for m in conn.sent if m.get("type") == "result"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["action_id"], "c1")
        self.assertEqual(results[0]["status"], "success")

    def test_heartbeat_sent_when_idle(self):
        companion = self._companion()
        conn = FakeConnection(frames=[])
        companion._serve(conn, threading.Event())
        self.assertTrue(any(m.get("type") == "heartbeat" for m in conn.sent))

    def test_revoked_stops_loop(self):
        companion = self._companion()
        conn = FakeConnection(frames=[json.dumps({"type": "revoked"})])
        companion._serve(conn, threading.Event())
        self.assertTrue(companion.revoked)

    def test_garbage_frame_is_ignored(self):
        companion = self._companion()
        conn = FakeConnection(frames=["not json", json.dumps({"type": "hello"})])
        companion._serve(conn, threading.Event())
        self.assertEqual([m for m in conn.sent if m.get("type") == "result"], [])


class TestRunReconnect(unittest.TestCase):
    def test_stops_when_stop_event_set(self):
        stop = threading.Event()
        stop.set()
        companion = dc.DeviceCompanion(
            "http://api.test", "tok", on_status=lambda _m: None
        )
        with mock.patch.object(companion, "_connect") as connect:
            companion.run(stop)
        connect.assert_not_called()

    def test_reconnects_after_drop_then_stops(self):
        stop = threading.Event()
        companion = dc.DeviceCompanion(
            "http://api.test", "tok", on_status=lambda _m: None
        )
        calls = {"n": 0}

        def connect():
            calls["n"] += 1
            if calls["n"] >= 2:
                stop.set()
            # A revoke frame ends the serve loop so the next iteration reconnects.
            return FakeConnection(frames=[json.dumps({"type": "not-a-revoke"})])

        with mock.patch.object(companion, "_connect", side_effect=connect):
            with mock.patch.object(dc, "_BACKOFF_MIN", 0.001):
                companion.run(stop)
        self.assertGreaterEqual(calls["n"], 2)


class TestCompanionThreadPersistence(unittest.TestCase):
    def test_pairing_persists_token_and_runs(self):
        store = {}
        fake_cfg = mock.MagicMock()
        fake_cfg.get_companion_config.return_value = {
            "name": "My PC",
            "api_base_url": "http://api.test",
        }
        fake_cfg.save_companion_config.side_effect = (
            lambda **kw: store.update(kw)
        )

        ran = {}

        def fake_run(self, stop_event):
            ran["token"] = self.device_token
            ran["device_id"] = self.device_id

        with mock.patch("memory.config_manager.get_companion_config",
                        fake_cfg.get_companion_config), \
             mock.patch("memory.config_manager.save_companion_config",
                        fake_cfg.save_companion_config), \
             mock.patch.object(dc.PairingClient, "pair",
                               return_value=("dev-1", "tok-1")), \
             mock.patch.object(dc.DeviceCompanion, "run", fake_run):
            thread = dc.CompanionThread("http://api.test")
            thread._run()

        self.assertEqual(store.get("device_token"), "tok-1")
        self.assertEqual(store.get("device_id"), "dev-1")
        self.assertEqual(ran, {"token": "tok-1", "device_id": "dev-1"})

    def test_existing_token_skips_pairing(self):
        fake_cfg = mock.MagicMock()
        fake_cfg.get_companion_config.return_value = {
            "api_base_url": "http://api.test",
            "device_token": "saved",
            "device_id": "d9",
        }
        ran = {}
        with mock.patch("memory.config_manager.get_companion_config",
                        fake_cfg.get_companion_config), \
             mock.patch.object(dc.PairingClient, "pair") as pair, \
             mock.patch.object(dc.DeviceCompanion, "run",
                               lambda self, se: ran.update(token=self.device_token)):
            dc.CompanionThread("http://api.test")._run()
        pair.assert_not_called()
        self.assertEqual(ran["token"], "saved")

    def test_revoked_clears_token(self):
        fake_cfg = mock.MagicMock()
        fake_cfg.get_companion_config.return_value = {
            "api_base_url": "http://api.test",
            "device_token": "saved",
            "device_id": "d9",
        }

        def run_and_revoke(self, stop_event):
            self.revoked = True

        with mock.patch("memory.config_manager.get_companion_config",
                        fake_cfg.get_companion_config), \
             mock.patch("memory.config_manager.clear_companion_token") as clear, \
             mock.patch.object(dc.DeviceCompanion, "run", run_and_revoke):
            dc.CompanionThread("http://api.test")._run()
        clear.assert_called_once()

    def test_start_and_stop_thread(self):
        fake_cfg = mock.MagicMock()
        fake_cfg.get_companion_config.return_value = {
            "api_base_url": "http://api.test",
            "device_token": "saved",
            "device_id": "d9",
        }
        release = threading.Event()
        with mock.patch("memory.config_manager.get_companion_config",
                        fake_cfg.get_companion_config), \
             mock.patch.object(dc.DeviceCompanion, "run",
                               lambda self, se: release.wait(2.0)):
            thread = dc.CompanionThread("http://api.test")
            thread.start()
            thread.start()  # idempotent
            time.sleep(0.05)
            self.assertFalse(thread.stopped)
            thread.stop(timeout=1.0)
        self.assertTrue(thread.stopped)


if __name__ == "__main__":
    unittest.main()
