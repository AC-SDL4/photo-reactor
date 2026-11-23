"""Standalone Pico H / SDL4 Rev A mixing-fan test. No LEDs or cooling fans.
Run in Thonny, then call mix(reactor, percent, seconds).
Percent is open-loop PWM command, not a calibrated RPM or torque setting.
"""
from machine import Pin, PWM, disable_irq, enable_irq
from time import sleep_ms, ticks_ms, ticks_diff

LED_GPIO = (0, 1, 4, 5, 8, 9, 12, 13)
FAN_GPIO = (2, 3, 6, 7, 10, 11, 14, 15)
_outputs = []

TACH_GPIO = (16, 17, 18, 19, 20, 21, 22, 26)
TACH_PULSES_PER_REV = 2
_tach_counts = [0, 0]
_tach_pins = []


def _tach_stir(pin):
    _tach_counts[0] += 1


def _tach_cool(pin):
    _tach_counts[1] += 1


def _detach_tach():
    for pin in _tach_pins:
        pin.irq(handler=None)
    _tach_pins[:] = []


def _start_tach(reactor):
    _detach_tach()
    _tach_counts[0] = 0
    _tach_counts[1] = 0
    start = (reactor - 1) * 2
    for gpio, handler in zip(TACH_GPIO[start:start + 2], (_tach_stir, _tach_cool)):
        pin = Pin(gpio, Pin.IN)  # Controller has external 3.3V pull-ups.
        _tach_pins.append(pin)
        pin.irq(trigger=Pin.IRQ_RISING, handler=handler)


def _snapshot():
    state = disable_irq()
    try:
        return ticks_ms(), _tach_counts[0], _tach_counts[1]
    finally:
        enable_irq(state)


def _measure_rpm(duration_ms):
    start, a0, b0 = _snapshot()
    sleep_ms(duration_ms)
    end, a1, b1 = _snapshot()
    elapsed = ticks_diff(end, start)
    if elapsed <= 0:
        raise RuntimeError('Invalid tach measurement interval')
    scale = 60000 / (TACH_PULSES_PER_REV * elapsed)
    return ((a1 - a0) * scale, (b1 - b0) * scale)


def _report_rpm(reactor, rpm):
    print('R%d measured: STIR %.0f RPM / COOL %.0f RPM (stage average, includes startup).' %
          (reactor, rpm[0], rpm[1]))
    for label, speed in zip(('STIR', 'COOL'), rpm):
        if speed == 0:
            print('CHECK R%d %s: no tach pulses; may be stalled or tach wiring is missing.' %
                  (reactor, label))
    print('Tach feedback indicates fan rotation; it does not prove stir-bar coupling.')




def all_off():
    """Stop commands; supply stays live and fans may coast."""
    while _outputs:
        output = _outputs.pop()
        try:
            output.duty_u16(65535)
        finally:
            output.deinit()
    _detach_tach()
    for gpio in LED_GPIO:
        Pin(gpio, Pin.OUT, value=0)
    for gpio in FAN_GPIO:
        Pin(gpio, Pin.OUT, value=1)


all_off()



def mix(reactor=1, percent=20, seconds=10, ramp_seconds=1):
    """Ramp one stir fan, then report RPM each second.

The hold time is 1..60 whole seconds, in addition to the 1..10 second ramp.
Stop after three consecutive no-pulse windows, allowing a short startup grace.
No full-speed startup kick: observe whether the loaded fan actually starts.
"""
    if type(reactor) is not int or reactor not in (1, 2, 3, 4):
        raise ValueError('reactor must be 1..4')
    if not isinstance(percent, (int, float)) or not 0 <= percent <= 100:
        raise ValueError('percent must be 0..100')
    if type(seconds) is not int or not 1 <= seconds <= 60:
        raise ValueError('seconds must be a whole number, 1..60')
    if type(ramp_seconds) is not int or not 1 <= ramp_seconds <= 10:
        raise ValueError('ramp_seconds must be a whole number, 1..10')
    all_off()
    if percent == 0:
        return
    try:
        _start_tach(reactor)
        gpio = FAN_GPIO[2 * (reactor - 1)]
        output = PWM(Pin(gpio), freq=25000, duty_u16=65535)
        _outputs.append(output)
        print('R%d STIR only: ramp to %s%%; LEDs and cooling fans OFF.' % (reactor, percent))
        steps = 20 * ramp_seconds
        for step in range(1, steps + 1):
            requested = percent * step / steps
            output.duty_u16(round(65535 * (100 - requested) / 100))
            sleep_ms(50)
        no_pulse_windows = 0
        for second in range(seconds):
            rpm = _measure_rpm(1000)[0]
            print('R%d STIR %s%%: %.0f RPM (%d/%ds)' %
                  (reactor, percent, rpm, second + 1, seconds))
            no_pulse_windows = no_pulse_windows + 1 if rpm == 0 else 0
            if no_pulse_windows:
                print('No tach pulses (%d/3): startup, stall or missing feedback.' % no_pulse_windows)
            if no_pulse_windows >= 3:
                print('Stopping after 3 consecutive seconds without tach pulses.')
                break
        print('Check the bar visually: fan RPM does not prove liquid stirring.')
    finally:
        all_off()


def main():
    all_off()
    print('MIXING FAN TEST: all outputs off. Stock selector 2-3; external-5V bypass NO jumper.')
    print('Example: mix(1, 20, 10) = reactor 1, 20% PWM, ten-second hold.')
    print('Slower ramp: mix(1, 30, 10, ramp_seconds=5). No full-speed startup kick.')
    print('Stops after 3 consecutive no-pulse seconds; Ctrl+C immediately if visibly stalled.')
    print('Ctrl+C stops a running mix(); all_off() commands off. Supply stays live.')


if __name__ == '__main__':
    main()
