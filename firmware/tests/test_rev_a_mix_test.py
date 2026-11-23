"""Host checks of mixing PWM and startup/no-feedback handling."""
import contextlib
import io
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch
from test_rev_a_reactor1_test import Hardware

class MixDiagnostics(unittest.TestCase):
    def load(self):
        hw = Hardware()
        with patch.dict(sys.modules, {'machine': hw.machine, 'time': hw.time}):
            p = runpy.run_path(str(Path(__file__).resolve().parents[1].joinpath('rev_a_mix_test.py')))
        return hw, p

    def test_pwm_inversion_and_slower_ramp(self):
        for percent in (20, 23, 30, 35, 40):
            hw, p = self.load()
            with contextlib.redirect_stdout(io.StringIO()):
                p['mix'](1, percent, 2, ramp_seconds=5)
            duties = [d for g, f, d in hw.duties if g == 2 and d != 65535]
            self.assertEqual(duties[-1], round(65535 * (100-percent)/100))
            self.assertEqual(duties, sorted(duties, reverse=True))
            self.assertEqual(hw.now, 7000)
            self.assertTrue(all(hw.pins[g] == 0 for g in p['LED_GPIO']))
            self.assertFalse(hw.pwm)

    def test_delayed_start_is_not_aborted_after_one_zero(self):
        hw, p = self.load()
        windows = [0, 0, 900, 1200]
        def measure(duration):
            return windows.pop(0), 0
        p['mix'].__globals__['_measure_rpm'] = measure
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            p['mix'](1, 30, 4)
        self.assertFalse(windows)
        self.assertIn('1200 RPM', output.getvalue())
        self.assertNotIn('Stopping after', output.getvalue())

    def test_persistent_zero_stops_after_three_windows(self):
        hw, p = self.load()
        calls = []
        def measure(duration):
            calls.append(duration)
            return 0, 0
        p['mix'].__globals__['_measure_rpm'] = measure
        with contextlib.redirect_stdout(io.StringIO()):
            p['mix'](1, 40, 10)
        self.assertEqual(calls, [1000]*3)
        self.assertFalse(hw.pwm)
        self.assertFalse(any(hw.handlers.values()))

    def test_interrupt_cleanup(self):
        hw, p = self.load()
        hw.fail_sleep = True
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(KeyboardInterrupt):
            p['mix'](1, 30, 10)
        self.assertFalse(hw.pwm)
        self.assertFalse(any(hw.handlers.values()))
        self.assertTrue(all(hw.pins[g] == 1 for g in p['FAN_GPIO']))
