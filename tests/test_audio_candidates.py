"""Tests for microphone candidate selection (core/audio_devices.py, Phase 2).

A fake `sounddevice` is injected so the selection logic can be exercised
without touching real hardware. Run with:

    python -m unittest tests.test_audio_candidates -v
"""
import sys
import types
import unittest
from unittest import mock

import core.audio_devices as audio_devices


class _FakeStream:
    def __init__(self):
        self.active = False

    def start(self):
        self.active = True

    def stop(self):
        self.active = False

    def close(self):
        pass


def _make_fake_sd(devices, apis):
    class FakeSD(types.SimpleNamespace):
        def query_devices(self, device=None, kind=None):
            if device is None:
                if kind == "input":
                    di = apis[0].get("default_input_device", 0)
                    return devices[di]
                return devices
            return devices[int(device)]

        def query_hostapis(self):
            return apis

        def InputStream(self, samplerate, channels, dtype, blocksize,
                        device, callback):
            idx = apis[0]["default_input_device"] if device is None else int(device)
            dev = devices[idx]
            if int(samplerate) not in dev.get("rates", []):
                raise RuntimeError("Invalid sample rate")
            return _FakeStream()

    return FakeSD()


# Two mics under WASAPI that open at 48 kHz, one MME alias that opens at 16 kHz,
# and one MME pseudo-device that must be filtered out.
DEVICES = [
    {"name": "Camo Mic", "hostapi": 0, "max_input_channels": 1,
     "default_samplerate": 48000.0, "rates": [48000]},
    {"name": "Camo Mic", "hostapi": 1, "max_input_channels": 1,
     "default_samplerate": 48000.0, "rates": [16000]},
    {"name": "Realtek Mic", "hostapi": 0, "max_input_channels": 1,
     "default_samplerate": 48000.0, "rates": [48000]},
    {"name": "Primary Sound Capture Driver", "hostapi": 1,
     "max_input_channels": 1, "default_samplerate": 44100.0, "rates": [44100]},
]
APIS = [
    {"name": "Windows WASAPI", "default_input_device": 0,
     "default_output_device": -1},
    {"name": "MME", "default_input_device": 1, "default_output_device": -1},
]


class TestInputCandidates(unittest.TestCase):
    def setUp(self):
        sys.modules["sounddevice"] = _make_fake_sd(DEVICES, APIS)
        audio_devices.configure(16000, 24000)   # also clears the probe caches
        audio_devices._chosen_api = {"input": None, "output": None}
        self._plat = mock.patch("platform.system", return_value="Windows")
        self._plat.start()

    def tearDown(self):
        self._plat.stop()
        sys.modules.pop("sounddevice", None)

    def test_wasapi_default_is_first_and_pseudo_filtered(self):
        cands = audio_devices.input_candidates("")
        self.assertTrue(cands)
        self.assertEqual(cands[0].device, 0)
        self.assertIn("wasapi", cands[0].backend.lower())
        self.assertEqual(cands[0].rate, 48000)
        # The pseudo-device must never be offered.
        self.assertFalse(any("primary sound" in c.name.lower() for c in cands))
        # Every candidate must have a real working rate.
        self.assertTrue(all(c.rate for c in cands))

    def test_saved_device_takes_precedence(self):
        cands = audio_devices.input_candidates("Realtek Mic")
        self.assertEqual(cands[0].device, 2)
        self.assertEqual(cands[0].rate, 48000)

    def test_no_duplicate_device_indices(self):
        cands = audio_devices.input_candidates("")
        idxs = [c.device for c in cands]
        self.assertEqual(len(idxs), len(set(idxs)))

    def test_device_that_only_opens_at_16k_is_listed(self):
        cands = audio_devices.input_candidates("")
        mme = [c for c in cands if c.device == 1]
        self.assertEqual(len(mme), 1)
        self.assertEqual(mme[0].rate, 16000)


if __name__ == "__main__":
    unittest.main()
