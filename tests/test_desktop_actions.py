"""The desktop-side allowlist and executor.

These mirror the assertions in services/api/tests/test_devices.py so the two
copies of the allowlist cannot drift apart silently. If you add or rename an
action, both test files must change — that is the point.

    python -m pytest tests/test_desktop_actions.py
"""
import unittest

from core import desktop_actions as da

# The contract, written out in full and independently of either module. Both the
# server test and this one assert against their own copy of this table.
EXPECTED = {
    "open_app": ("app.launch", False),
    "browser.navigate": ("browser.navigate", False),
    "system.info": ("system.info", False),
    "media.control": ("media.control", False),
    "volume.set": ("volume.control", False),
    "volume.mute": ("volume.control", False),
    "notification.send": ("notification.send", False),
    "screen.lock": ("power.control", True),
    "power.sleep": ("power.control", True),
    "power.shutdown": ("power.control", True),
    "power.restart": ("power.control", True),
}


class TestAllowlist(unittest.TestCase):
    def test_names_match_contract(self):
        self.assertEqual(set(da.ACTIONS), set(EXPECTED))

    def test_permission_and_confirmation_match(self):
        for name, (perm, confirm) in EXPECTED.items():
            spec = da.ACTIONS[name]
            self.assertEqual(spec["permission"], perm, name)
            self.assertEqual(spec["confirm"], confirm, name)

    def test_only_power_actions_need_confirmation(self):
        sensitive = {n for n, s in da.ACTIONS.items() if s["confirm"]}
        self.assertEqual(sensitive, {
            "screen.lock", "power.sleep", "power.shutdown", "power.restart",
        })

    def test_public_listing_shape(self):
        listing = da.actions_public()
        self.assertEqual(len(listing), len(EXPECTED))
        for entry in listing:
            self.assertEqual(
                set(entry), {"name", "permission", "requires_confirmation"}
            )


class TestExecuteValidation(unittest.TestCase):
    def test_unknown_action(self):
        status, _ = da.execute("format.c", {})
        self.assertEqual(status, "error")

    def test_unexpected_parameter_is_denied(self):
        status, _ = da.execute("system.info", {"evil": "rm -rf"})
        self.assertEqual(status, "denied")

    def test_missing_parameter_is_denied(self):
        status, _ = da.execute("open_app", {})
        self.assertEqual(status, "denied")

    def test_non_dict_parameters(self):
        status, _ = da.execute("system.info", ["nope"])
        self.assertEqual(status, "error")

    def test_open_app_rejects_metacharacters(self):
        status, _ = da.execute("open_app", {"app": "calc & rm -rf /"})
        self.assertEqual(status, "denied")

    def test_navigate_rejects_non_http(self):
        for url in ("file:///etc/passwd", "javascript:alert(1)", "ftp://x"):
            status, _ = da.execute("browser.navigate", {"url": url})
            self.assertEqual(status, "denied", url)

    def test_media_rejects_unknown_command(self):
        status, _ = da.execute("media.control", {"command": "eject"})
        self.assertEqual(status, "denied")

    def test_volume_out_of_range(self):
        for level in (-1, 101, "loud"):
            status, _ = da.execute("volume.set", {"level": level})
            self.assertEqual(status, "denied", str(level))

    def test_notification_title_required(self):
        status, _ = da.execute("notification.send", {"title": "   "})
        self.assertEqual(status, "denied")


class TestExecuteDispatch(unittest.TestCase):
    def _stub(self, action):
        """Swap an action's handler for one that records and returns."""

        calls = []
        spec = da.ACTIONS[action]

        def handler(params):
            calls.append(params)
            return "did it"

        spec["handler"] = handler
        return calls

    def test_successful_dispatch(self):
        original = da.ACTIONS["open_app"]["handler"]
        calls = self._stub("open_app")
        try:
            status, message = da.execute("open_app", {"app": "notepad"})
        finally:
            da.ACTIONS["open_app"]["handler"] = original
        self.assertEqual(status, "success")
        self.assertEqual(message, "did it")
        self.assertEqual(calls, [{"app": "notepad"}])

    def test_confirmation_denies_without_callback(self):
        status, _ = da.execute("power.shutdown", {})
        self.assertEqual(status, "denied")

    def test_confirmation_denies_when_refused(self):
        status, _ = da.execute(
            "power.shutdown", {}, confirm=lambda a, p: False
        )
        self.assertEqual(status, "denied")

    def test_confirmation_runs_when_granted(self):
        original = da.ACTIONS["power.restart"]["handler"]
        calls = self._stub("power.restart")
        asked = []

        def confirm(action, params):
            asked.append(action)
            return True

        try:
            status, _ = da.execute("power.restart", {}, confirm=confirm)
        finally:
            da.ACTIONS["power.restart"]["handler"] = original
        self.assertEqual(status, "success")
        self.assertEqual(asked, ["power.restart"])
        self.assertEqual(len(calls), 1)

    def test_handler_exception_becomes_error(self):
        original = da.ACTIONS["system.info"]["handler"]

        def boom(_params):
            raise RuntimeError("kaboom")

        da.ACTIONS["system.info"]["handler"] = boom
        try:
            status, message = da.execute("system.info", {})
        finally:
            da.ACTIONS["system.info"]["handler"] = original
        self.assertEqual(status, "error")
        self.assertIn("kaboom", message)

    def test_action_denied_inside_handler(self):
        original = da.ACTIONS["browser.navigate"]["handler"]

        def deny(_params):
            raise da.ActionDenied("nope")

        da.ACTIONS["browser.navigate"]["handler"] = deny
        try:
            status, message = da.execute(
                "browser.navigate", {"url": "https://example.com"}
            )
        finally:
            da.ACTIONS["browser.navigate"]["handler"] = original
        self.assertEqual(status, "denied")
        self.assertEqual(message, "nope")

    def test_notification_body_is_optional(self):
        original = da.ACTIONS["notification.send"]["handler"]
        calls = self._stub("notification.send")
        # The stub returns before the length checks, so this only proves the
        # parameter gate lets a title-only command through to the handler.
        try:
            status, _ = da.execute("notification.send", {"title": "Hi"})
        finally:
            da.ACTIONS["notification.send"]["handler"] = original
        self.assertEqual(status, "success")
        self.assertEqual(calls, [{"title": "Hi"}])

    def test_requires_confirmation_helper(self):
        self.assertTrue(da.requires_confirmation("power.shutdown"))
        self.assertFalse(da.requires_confirmation("open_app"))
        self.assertFalse(da.requires_confirmation("no.such.action"))


class TestNoShell(unittest.TestCase):
    def test_media_key_never_uses_a_shell(self):
        import inspect

        source = inspect.getsource(da)
        self.assertNotIn("shell=True", source)
        # Argument lists only: the subprocess seam is always called with a list.
        self.assertIn("subprocess.run(args", source)


if __name__ == "__main__":
    unittest.main()
