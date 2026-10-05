"""Virtual input devices via /dev/uinput.

Works on Wayland because events come from the kernel, like a real USB device.
The mouse is an *absolute* pointer (same shape as QEMU's USB tablet), so a point
in the camera maps straight to a point on screen with no pointer acceleration.
"""

from evdev import AbsInfo, UInput, ecodes as e

ABS_MAX = 32767


class VirtualMouse:
    def __init__(self):
        self.mouse = UInput(
            {
                e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE],
                e.EV_REL: [e.REL_WHEEL, e.REL_HWHEEL],
                e.EV_ABS: [
                    (e.ABS_X, AbsInfo(0, 0, ABS_MAX, 0, 0, 0)),
                    (e.ABS_Y, AbsInfo(0, 0, ABS_MAX, 0, 0, 0)),
                ],
            },
            name="handcad virtual mouse",
        )
        # Modifier keys live on a separate device so the mouse isn't classified as a keyboard.
        self.keyboard = UInput({e.EV_KEY: [e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT]}, name="handcad virtual keys")
        self.held: set[int] = set()

    def move(self, x: float, y: float):
        """x, y normalized 0..1 across the desktop."""
        x = min(max(x, 0.0), 1.0)
        y = min(max(y, 0.0), 1.0)
        self.mouse.write(e.EV_ABS, e.ABS_X, int(x * ABS_MAX))
        self.mouse.write(e.EV_ABS, e.ABS_Y, int(y * ABS_MAX))
        self.mouse.syn()

    def _dev(self, code):
        return self.keyboard if code in (e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT) else self.mouse

    def press(self, code: int):
        if code in self.held:
            return
        dev = self._dev(code)
        dev.write(e.EV_KEY, code, 1)
        dev.syn()
        self.held.add(code)

    def release(self, code: int):
        if code not in self.held:
            return
        dev = self._dev(code)
        dev.write(e.EV_KEY, code, 0)
        dev.syn()
        self.held.discard(code)

    def click(self, code: int = e.BTN_LEFT):
        self.press(code)
        self.release(code)

    def scroll(self, notches: int):
        if notches:
            self.mouse.write(e.EV_REL, e.REL_WHEEL, notches)
            self.mouse.syn()

    def release_all(self):
        # Buttons before modifiers, so a Ctrl+middle drag ends cleanly.
        for code in sorted(self.held, key=lambda c: c in (e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT)):
            self.release(code)

    def close(self):
        self.release_all()
        self.mouse.close()
        self.keyboard.close()
