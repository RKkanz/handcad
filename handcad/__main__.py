import argparse
import os
import signal
import sys

# The overlay runs through XWayland: GNOME's Wayland session ignores "always on top"
# for native Wayland clients, but honours it (and click-through) for X11 windows.
os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from .config import Config  # noqa: E402
from .controller import Controller  # noqa: E402
from .overlay import Overlay  # noqa: E402
from .tracker import Tracker  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Hand-tracking mouse + CAD navigation.")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--debug", action="store_true", help="show finger curl / thumb values for tuning")
    ap.add_argument("--click", choices=["pinch", "thumb"], default="pinch",
                    help="pinch: thumb tip to index tip (default); thumb: point and pull the thumb out")
    ap.add_argument("--air-tap", action="store_true", help="also click by tapping the index finger in the air")
    ap.add_argument("--dry-run", action="store_true", help="track and draw, but don't touch the mouse")
    ap.add_argument("--invert-zoom", action="store_true")
    ap.add_argument("--calibrate", action="store_true", help="measure your pinches and save click thresholds")
    args = ap.parse_args()

    cfg = Config().load_user()
    cfg.camera, cfg.debug, cfg.click = args.camera, args.debug, args.click
    cfg.air_tap = args.air_tap or cfg.air_tap
    cfg.zoom_invert = args.invert_zoom or cfg.zoom_invert

    if args.calibrate:
        from .calibrate import run

        run(cfg)
        return

    mouse = None
    if not args.dry_run:
        from .mouse import VirtualMouse

        try:
            mouse = VirtualMouse()
        except PermissionError:
            sys.exit("No access to /dev/uinput. Run scripts/setup.sh once (or use --dry-run).")

    app = QApplication(sys.argv)
    overlay = Overlay()
    overlay.show_on_screen(app.primaryScreen())

    controller = Controller(cfg, mouse)
    tracker = Tracker(cfg, controller)
    tracker.frame.connect(overlay.on_frame)
    tracker.start()

    signal.signal(signal.SIGINT, lambda *_: app.quit())
    tick = QTimer()
    tick.start(200)  # lets Python see Ctrl+C while Qt's loop runs
    tick.timeout.connect(lambda: None)

    code = app.exec()
    tracker.stop()
    if mouse:
        mouse.close()
    sys.exit(code)


if __name__ == "__main__":
    main()
