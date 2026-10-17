"""Smoke tests: the desktop app's core modules import on this machine.

    python -m unittest tests.test_imports -v
"""
import unittest


class TestImports(unittest.TestCase):
    def test_audio_devices(self):
        import core.audio_devices as m
        for name in ("configure", "prefetch", "list_devices", "resolve",
                     "input_candidates", "InputCandidate"):
            self.assertTrue(hasattr(m, name), name)

    def test_gemini(self):
        import core.gemini as m
        for name in ("client", "text", "as_json", "live_model",
                     "note_live_failure", "api_key"):
            self.assertTrue(hasattr(m, name), name)

    def test_memory(self):
        import memory.memory_manager as mm
        import memory.config_manager as cm
        self.assertTrue(hasattr(mm, "load_memory"))
        self.assertTrue(hasattr(mm, "format_memory_for_prompt"))
        self.assertTrue(hasattr(cm, "get_input_device"))
        self.assertTrue(hasattr(cm, "get_voice"))

    def test_config_package(self):
        import config
        self.assertIn(config.get_os(), ("windows", "mac", "linux"))


if __name__ == "__main__":
    unittest.main()
