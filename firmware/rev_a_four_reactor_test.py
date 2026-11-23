"""Standalone Thonny sequence: R1 -> R4, both LEDs/fans, 2s on / 1s gap.

Pico H on SDL4-0001 PCB Rev A. LEDs retain the established 1kHz / 20% GPIO
bench-test duty (not calibrated optical output). Fans are commanded to 100%.
Run once per TEST; Ctrl+C commands everything off. No extra Pico files required.
"""
from machine import Pin, PWM, disable_irq, enable_irq
from time import sleep_ms, ticks_ms, ticks_diff

LED_GPIO = (0, 1, 4, 5, 8, 9, 12, 13)
FAN_GPIO = (2, 3, 6, 7, 10, 11, 14, 15)
LED_DUTY = 13107  # 20% GPIO duty, as used in previous bench tests.
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
    """LEDs off, fans commanded 0%; fan power remains live."""
    while _outputs:
        output, off_duty = _outputs.pop()
        try:
            output.duty_u16(off_duty)
        finally:
            output.deinit()
    _detach_tach()
    for gpio in LED_GPIO:
        Pin(gpio, Pin.OUT, value=0)
    for gpio in FAN_GPIO:
        Pin(gpio, Pin.OUT, value=1)  # Inverting 2N7002: gate high = fan PWM low.


all_off()


def run_test():
    """One 11-second pass. Only one reactor is commanded on at a time."""
    all_off()
    try:
        for reactor in range(1, 5):
            start = 2 * (reactor - 1)
            print('REACTOR %d: both fans 100%% + both LEDs at bench duty, 2 seconds.' % reactor)
            _start_tach(reactor)
            # Fans and LEDs are enabled in the same stage; no extra spin-up wait.
            for gpio in FAN_GPIO[start:start + 2]:
                output = PWM(Pin(gpio), freq=25000, duty_u16=65535)
                _outputs.append((output, 65535))
                output.duty_u16(0)  # Full speed after the board's inversion.
            for gpio in LED_GPIO[start:start + 2]:
                output = PWM(Pin(gpio), freq=1000, duty_u16=0)
                _outputs.append((output, 0))
                output.duty_u16(LED_DUTY)
            rpm = _measure_rpm(2000)
            all_off()
            _report_rpm(reactor, rpm)
            if reactor < 4:
                print('All outputs off/0% command; 1-second gap.')
                sleep_ms(1000)
        print('Complete: reactors 1 -> 4. LEDs OFF; fans commanded to 0%.')
        print('RPM feedback reported above; confirm fan and LED identities visually.')
    finally:
        all_off()


def main():
    try:
        print('\nSDL4 Rev A -- FOUR-REACTOR SEQUENCE')
        print('Verify 5V fan rail. Stock selector 2-3; external-5V bypass NO jumper. Heatsinks fitted.')
        print('Observe LED reflections, not the bare emitters. Ctrl+C stops the test.')
        print('One pass: 2 seconds per reactor, 1 second between reactors (11s total).')
        if input('Type TEST to start, or Enter to cancel: ').strip().upper() == 'TEST':
            run_test()
        else:
            print('Cancelled.')
    except KeyboardInterrupt:
        print('\nStopped.')
    finally:
        all_off()
    print('Repeat with run_test(); all_off() commands off. Disconnect 12V, external 5V, then USB before wiring changes.')


if __name__ == '__main__':
    main()
