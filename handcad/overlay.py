"""Fullscreen, transparent, click-through window that draws only the hand skeleton."""

import time

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import gestures as g
from .controller import ViewState

COLORS = {
    g.POINT: QColor(80, 200, 255),
    g.CUP: QColor(255, 170, 60),
    g.THREE: QColor(120, 230, 120),
    g.TWO: QColor(220, 120, 255),
    g.OPEN: QColor(255, 255, 255),
    g.FIST: QColor(255, 255, 255),
    g.NONE: QColor(200, 200, 200),
}
PAUSED = QColor(150, 150, 150)
CLICK_COLORS = {"left": QColor(80, 200, 255), "right": QColor(255, 150, 40)}
CLICK_TEXT = {"left": "click", "right": "right click"}
RIPPLE_S = 0.4


class Overlay(QWidget):
    def __init__(self):
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.state = ViewState()
        self.ripples: list[tuple[QPointF, str, float]] = []  # (pos, button, start time)
        # Frames arrive at camera rate (~20 fps); repaint faster while a ripple animates.
        self.anim = QTimer(self)
        self.anim.timeout.connect(self._animate)
        self.last_dirty = QRect()

    def show_on_screen(self, screen):
        self.setGeometry(screen.geometry())
        self.show()

    def on_frame(self, state: ViewState):
        self.state = state
        if state.cursor and state.clicks:
            pos = QPointF(state.cursor[0] * self.width(), state.cursor[1] * self.height())
            now = time.monotonic()
            self.ripples += [(pos, b, now) for b in state.clicks]
            self.anim.start(16)
        # Repaint only around the hand (this frame and last), not the whole screen:
        # less painting here and less compositing for GNOME.
        dirty = self._dirty_rect(state)
        self.update(dirty.united(self.last_dirty))
        self.last_dirty = dirty

    def _ripple_rects(self) -> QRect:
        r = QRect()
        for pos, _, _ in self.ripples:
            # ring grows to ~72 px; the label sits up and to the right
            r = r.united(QRect(int(pos.x()) - 80, int(pos.y()) - 95, 280, 175))
        return r

    def _dirty_rect(self, s: ViewState) -> QRect:
        w, h = self.width(), self.height()
        r = self._ripple_rects()
        if s.points:
            xs = [x * w for x, _ in s.points]
            ys = [y * h for _, y in s.points]
            # margin covers joint dots, the pause arc, and the mode label under the wrist
            r = r.united(QRect(int(min(xs)) - 90, int(min(ys)) - 50, int(max(xs) - min(xs)) + 230, int(max(ys) - min(ys)) + 110))
        if s.cursor:
            r = r.united(QRect(int(s.cursor[0] * w) - 40, int(s.cursor[1] * h) - 40, 80, 80))
        if s.paused:
            r = r.united(QRect(0, h - 50, 520, 50))
        if s.debug:
            r = r.united(QRect(0, 0, w, 45))
        return r

    def _animate(self):
        self.update(self._ripple_rects())

    def paintEvent(self, _):
        s = self.state
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        color = PAUSED if s.paused else COLORS.get(s.gesture, COLORS[g.NONE])

        if s.points:
            pts = [QPointF(x * w, y * h) for x, y in s.points]
            bone = QColor(color)
            bone.setAlpha(170 if not s.paused else 90)
            p.setPen(QPen(bone, 4, Qt.SolidLine, Qt.RoundCap))
            for a, b in g.BONES:
                p.drawLine(pts[a], pts[b])
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 200 if not s.paused else 90))
            for i, pt in enumerate(pts):
                r = 7 if i in (4, 8, 12, 16, 20) else 4.5
                p.drawEllipse(pt, r, r)

            if s.pause_progress > 0:
                p.setPen(QPen(QColor(255, 255, 255, 220), 5, Qt.SolidLine, Qt.RoundCap))
                p.setBrush(Qt.NoBrush)
                c = pts[9]
                p.drawArc(QRectF(c.x() - 40, c.y() - 40, 80, 80), 90 * 16, int(-360 * 16 * s.pause_progress))

            if s.label:
                p.setFont(QFont("Sans", 13, QFont.Bold))
                p.setPen(color)
                p.drawText(pts[0] + QPointF(-30, 34), s.label)

        if s.cursor and not s.paused:
            c = QPointF(s.cursor[0] * w, s.cursor[1] * h)
            if s.pinch is not None:
                self._pinch_ring(p, c, s)
            else:
                p.setPen(QPen(color, 3))
                p.setBrush(QColor(color.red(), color.green(), color.blue(), 120 if s.pressed else 0))
                p.drawEllipse(c, 16, 16)

        self._draw_ripples(p)

        if s.paused and not s.points:
            p.setFont(QFont("Sans", 12))
            p.setPen(PAUSED)
            p.drawText(20, h - 20, "handcad paused - hold a fist to resume")

        if s.debug:
            p.setFont(QFont("Monospace", 10))
            p.setPen(QColor(255, 255, 255, 200))
            text = f"{s.fps:4.0f} fps  " + "  ".join(f"{k}={v}" for k, v in s.debug.items())
            p.drawText(20, 30, text)
        p.end()

    def _pinch_ring(self, p: QPainter, c: QPointF, s: ViewState):
        """Ring that fills as the pinch closes; solid disc while the button is held."""
        button = "right" if s.pinch_finger == g.MIDDLE_TIP else "left"
        col = QColor(CLICK_COLORS[button])
        r = 22
        if s.pressed:
            p.setPen(QPen(QColor(255, 255, 255), 3))
            col.setAlpha(200)
            p.setBrush(col)
            p.drawEllipse(c, r, r)
            return
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 110), 3))
        p.drawEllipse(c, r, r)
        p.drawEllipse(c, 3, 3)
        if s.pinch > 0.02:
            p.setPen(QPen(col, 6, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), 90 * 16, int(-360 * 16 * s.pinch))

    def _draw_ripples(self, p: QPainter):
        now = time.monotonic()
        self.ripples = [rp for rp in self.ripples if now - rp[2] < RIPPLE_S]
        if not self.ripples:
            self.anim.stop()
            return
        p.setFont(QFont("Sans", 14, QFont.Bold))
        for pos, button, t0 in self.ripples:
            k = (now - t0) / RIPPLE_S
            col = QColor(CLICK_COLORS[button])
            col.setAlpha(int(255 * (1 - k)))
            p.setPen(QPen(col, 5 * (1 - k) + 1))
            p.setBrush(Qt.NoBrush)
            r = 22 + 50 * k
            p.drawEllipse(pos, r, r)
            p.setPen(col)
            p.drawText(pos + QPointF(30, -30 - 15 * k), CLICK_TEXT[button])
