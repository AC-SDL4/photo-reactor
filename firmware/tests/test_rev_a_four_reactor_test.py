"""Check reactor order, simultaneous stage states, timing and interrupt cleanup."""
import contextlib
import io
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch
from test_rev_a_reactor1_test import Hardware


class FourReactors(unittest.TestCase):
    def load(self):
        hw = Hardware()
        with patch.dict(sys.modules, {'machine': hw.machine, 'time': hw.time}):
            program = runpy.run_path(str(Path(__file__).resolve().parents[1].joinpath('rev_a_four_reactor_test.py')))
        return hw, program

    def assert_off(self, hw, program):
        self.assertFalse(hw.pwm)
        self.assertFalse(any(hw.handlers.values()))
        for gpio in program['LED_GPIO']:
            self.assertEqual(hw.pins[gpio], 0)
        for gpio in program['FAN_GPIO']:
            self.assertEqual(hw.pins[gpio], 1)

    def test_sequence_and_gaps(self):
        hw, program = self.load()
        stages = []
        def sleep(duration):
            stages.append((duration, {g: (p.freq, p.duty) for g, p in hw.pwm.items()}))
            hw.sleep_ms(duration)
        program['run_test'].__globals__['sleep_ms'] = sleep
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            program['run_test']()
        for reactor in range(1, 5):
            self.assertIn('R%d measured: STIR 6000 RPM / COOL 6000 RPM' % reactor, output.getvalue())
        self.assertEqual([s[0] for s in stages], [2000, 1000, 2000, 1000, 2000, 1000, 2000])
        for reactor, (_, state) in enumerate(stages[::2]):
            index = reactor * 2
            expected = {g: (1000, 13107) for g in program['LED_GPIO'][index:index + 2]}
            expected.update({g: (25000, 0) for g in program['FAN_GPIO'][index:index + 2]})
            self.assertEqual(state, expected)
        for _, state in stages[1::2]:
            self.assertEqual(state, {})
        self.assert_off(hw, program)

    def test_interrupt_turns_all_channels_off(self):
        hw, program = self.load()
        hw.fail_sleep = True
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(KeyboardInterrupt):
            program['run_test']()
        self.assert_off(hw, program)


class AllFanFeedback(FourReactors):
    def load(self):
        hw = Hardware()
        with patch.dict(sys.modules, {'machine': hw.machine, 'time': hw.time}):
            program = runpy.run_path(str(Path(__file__).resolve().parents[1].joinpath('rev_a_all_fans.py')))
        program['run_test'] = program['test_fans']
        return hw, program

    def test_sequence_and_gaps(self):
        hw, program = self.load()
        stages = []
        def sleep(duration):
            stages.append((duration, set(hw.pwm)))
            self.assertTrue(all(hw.pins[g] == 0 for g in program['LED_GPIO']))
            hw.sleep_ms(duration)
        program['run_test'].__globals__['sleep_ms'] = sleep
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            program['run_test']()
        self.assertEqual([d for d, _ in stages], [2000, 1000, 2000, 1000, 2000, 1000, 2000])
        for reactor, (_, pins) in enumerate(stages[::2]):
            self.assertEqual(pins, set(program['FAN_GPIO'][2*reactor:2*reactor+2]))
            self.assertIn('R%d measured: STIR 6000 RPM / COOL 6000 RPM' % (reactor+1), output.getvalue())
        self.assert_off(hw, program)

    def test_missing_feedback_is_flagged(self):
        hw, program = self.load()
        program['run_fans'].__globals__['sleep_ms'] = lambda duration: setattr(hw, 'now', hw.now + duration)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(program['run_fans'](4), (0, 0))
        self.assertIn('CHECK R4 STIR: no tach pulses', output.getvalue())
        self.assertIn('CHECK R4 COOL: no tach pulses', output.getvalue())
        self.assert_off(hw, program)
