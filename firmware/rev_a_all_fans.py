"""Pico H / SDL4-0001 Rev A: fans only, reactors 1 -> 4.

Standalone MicroPython: run this file in Thonny, then type TEST.
Both fans at 100% for 2 seconds per reactor, 1 second between reactors.
All eight LED controls remain off. Ctrl+C commands fans off.
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


def run_fans(reactor, seconds=2):
    """Both fans on one reactor at full command, bounded to 60 seconds."""
    if type(reactor) is not int or reactor not in (1, 2, 3, 4):
        raise ValueError('Use reactor 1, 2, 3 or 4')
    if not isinstance(seconds, (int, float)) or not 0 < seconds <= 60:
        raise ValueError('seconds must be greater than 0 and at most 60')
    all_off()
    try:
        print('REACTOR %d: STIR + COOL at 100%%, LEDs OFF, %s seconds.' % (reactor, seconds))
        _start_tach(reactor)
        start = (reactor - 1) * 2
        for gpio in FAN_GPIO[start:start + 2]:
            output = PWM(Pin(gpio), freq=25000, duty_u16=65535)
            _outputs.append(output)
            output.duty_u16(0)  # Controller transistor inverts PWM.
        rpm = _measure_rpm(max(1, int(seconds * 1000)))
    finally:
        all_off()

    _report_rpm(reactor, rpm)
    return rpm


def test_fans():
    """One 11-second fans-only pass through all four reactors."""
    all_off()
    try:
        for reactor in range(1, 5):
            run_fans(reactor)
            if reactor < 4:
                print('Fans commanded off; 1-second gap.')
                sleep_ms(1000)
        print('Complete. All fans commanded off; all LEDs OFF.')
        print('RPM feedback reported above for all eight fans.')
    finally:
        all_off()


def test_3():
    """R1 -> R2 -> R3, both fans at 100% for 5s; R4 and LEDs stay off."""
    all_off()
    try:
        for reactor in (1, 2, 3):
            run_fans(reactor, 5)
            if reactor != 3:
                print('Fans commanded off; 1-second gap.')
                sleep_ms(1000)
        print('Complete. All fans commanded off; all LEDs OFF.')
    finally:
        all_off()


def main():
    try:
        print('\nSDL4 Rev A -- ALL FOUR REACTORS, FANS ONLY')
        print('Verify the fan rail is 5V. Keep blades clear. LEDs remain OFF.')
        print('Stock board: JP_FANV 2-3. External-5V bypass: selector absent, NO jumper.')
        if input('Type TEST to start, or Enter to cancel: ').strip().upper() == 'TEST':
            test_fans()
        else:
            print('Cancelled.')
    except KeyboardInterrupt:
        print('\nStopped.')
    finally:
        all_off()
    print('Repeat: test_fans(). One reactor: run_fans(1, 10). Stop: Ctrl+C.')
    print('Three reactors only: test_3() (R1 -> R2 -> R3, five seconds each).')
    print('Disconnect 12V, external 5V and USB before rewiring. Off commands leave supplies live.')


if __name__ == '__main__':
    main()
