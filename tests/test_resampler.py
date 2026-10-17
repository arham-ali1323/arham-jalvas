"""Tests for the microphone resampler in main.py (Phase 2).

These run with the standard library only:

    python -m unittest tests.test_resampler -v

Importing main.py pulls in the whole desktop app (PyQt6, numpy). That is
deliberate: the resampler must be tested through the exact class the audio
thread uses, not a copy. The app is never launched — only module import happens.
"""
import unittest

import numpy as np

import main


class TestStreamResampler(unittest.TestCase):
    def test_dc_level_preserved(self):
        rs = main._StreamResampler(48000, 16000)
        block = np.full(480, 1000, dtype=np.int16)   # 10 ms @ 48 kHz
        chunks = [rs.process(block) for _ in range(200)]
        y = np.concatenate([c for c in chunks if c.size])
        # After the FIR warm-up a constant input must stay constant (gain 1).
        tail = y[2000:].astype(np.float64)
        self.assertAlmostEqual(float(np.mean(tail)), 1000.0, delta=5.0)

    def test_output_length_ratio(self):
        rs = main._StreamResampler(48000, 16000)
        block = np.zeros(480, dtype=np.int16)
        total = sum(rs.process(block).size for _ in range(100))
        # 48,000 samples in -> ~16,000 out.
        self.assertGreater(total, 15900)
        self.assertLess(total, 16100)

    def test_no_discontinuity_across_blocks(self):
        rs = main._StreamResampler(48000, 16000)
        block = np.full(480, 100, dtype=np.int16)
        chunks = [rs.process(block) for _ in range(50)]
        y = np.concatenate([c for c in chunks if c.size]).astype(np.int64)
        # A constant input must not produce ticks at block boundaries.
        jumps = np.abs(np.diff(y[1000:]))
        self.assertLess(int(jumps.max()), 5)

    def test_tone_frequency_is_preserved(self):
        rs = main._StreamResampler(48000, 16000)
        fs_in, freq = 48000, 1000
        chunks = []
        for _ in range(200):
            x = (3000 * np.sin(2 * np.pi * freq * np.arange(480) / fs_in))
            chunks.append(rs.process(x.astype(np.int16)))
        y = np.concatenate([c for c in chunks if c.size]).astype(np.float64)[1000:]
        spec = np.abs(np.fft.rfft(y * np.hanning(y.size)))
        peak = np.fft.rfftfreq(y.size, d=1 / 16000.0)[int(np.argmax(spec))]
        self.assertAlmostEqual(peak, float(freq), delta=25.0)

    def test_same_rate_is_safe(self):
        rs = main._StreamResampler(16000, 16000)
        out = rs.process(np.arange(160, dtype=np.int16))
        # FIR group delay costs a sample or two at the very start; no crash,
        # no explosion.
        self.assertTrue(155 <= out.size <= 160)
        self.assertTrue(np.all(out > -32768))


if __name__ == "__main__":
    unittest.main()
