"""Linha do tempo com marcadores de início/fim arrastáveis."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
)
from PyQt6.QtWidgets import (
    QWidget,
)

ACCENT = QColor("#4f9dff")
IN_COLOR = QColor("#3ecf8e")
OUT_COLOR = QColor("#ff6b6b")


class Timeline(QWidget):
    seekRequested = pyqtSignal(int)  # ms
    inChanged = pyqtSignal(int)
    outChanged = pyqtSignal(int)

    PAD = 12
    HANDLE_HIT = 8

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(54)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.duration = 0
        self.position = 0
        self.in_ms = 0
        self.out_ms = 0
        self._drag: str | None = None  # "in" | "out" | "seek"

    def set_duration(self, ms: int):
        self.duration, self.position, self.in_ms, self.out_ms = ms, 0, 0, ms
        self.update()

    def set_position(self, ms: int):
        self.position = ms
        self.update()

    def set_range(self, in_ms: int, out_ms: int):
        self.in_ms, self.out_ms = in_ms, out_ms
        self.update()

    # conversões
    def _track(self) -> QRectF:
        return QRectF(self.PAD, 14, self.width() - 2 * self.PAD, self.height() - 28)

    def _x(self, ms: int) -> float:
        t = self._track()
        return t.left() + (ms / self.duration * t.width() if self.duration else 0)

    def _ms(self, x: float) -> int:
        t = self._track()
        if not self.duration or t.width() <= 0:
            return 0
        return int(round(min(max((x - t.left()) / t.width(), 0), 1) * self.duration))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        t = self._track()

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.color(QPalette.ColorRole.Base))
        p.drawRoundedRect(t, 6, 6)

        if not self.duration:
            p.setPen(pal.color(QPalette.ColorRole.PlaceholderText))
            p.drawText(t, Qt.AlignmentFlag.AlignCenter, "Nenhum vídeo carregado")
            return

        # trecho selecionado
        xi, xo = self._x(self.in_ms), self._x(self.out_ms)
        sel = QRectF(xi, t.top(), max(1.0, xo - xi), t.height())
        fill = QColor(ACCENT)
        fill.setAlpha(70)
        p.setBrush(fill)
        p.drawRect(sel)
        p.setPen(QPen(ACCENT, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(sel)

        # marcadores (colchetes)
        for x, color, left in ((xi, IN_COLOR, True), (xo, OUT_COLOR, False)):
            p.setPen(QPen(color, 3))
            d = 6 if left else -6
            path = QPainterPath(QPointF(x + d, t.top() - 4))
            path.lineTo(x, t.top() - 4)
            path.lineTo(x, t.bottom() + 4)
            path.lineTo(x + d, t.bottom() + 4)
            p.drawPath(path)

        # cursor de reprodução
        xp = self._x(self.position)
        p.setPen(QPen(pal.color(QPalette.ColorRole.Text), 2))
        p.drawLine(QPointF(xp, t.top() - 8), QPointF(xp, t.bottom() + 8))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.color(QPalette.ColorRole.Text))
        tri = QPainterPath(QPointF(xp - 6, 2))
        tri.lineTo(xp + 6, 2)
        tri.lineTo(xp, 10)
        tri.closeSubpath()
        p.drawPath(tri)

    def _hit(self, x: float) -> str:
        if self.duration:
            if abs(x - self._x(self.out_ms)) <= self.HANDLE_HIT:
                return "out"
            if abs(x - self._x(self.in_ms)) <= self.HANDLE_HIT:
                return "in"
        return "seek"

    def mousePressEvent(self, e):
        if not self.duration or e.button() != Qt.MouseButton.LeftButton:
            return
        self._drag = self._hit(e.position().x())
        self.mouseMoveEvent(e)

    def mouseMoveEvent(self, e):
        x = e.position().x()
        if self._drag is None:
            self.setCursor(
                Qt.CursorShape.SizeHorCursor if self._hit(x) != "seek" else Qt.CursorShape.PointingHandCursor
            )
            return
        ms = self._ms(x)
        if self._drag == "in":
            self.in_ms = min(ms, self.out_ms)
            self.inChanged.emit(self.in_ms)
            self.seekRequested.emit(self.in_ms)
        elif self._drag == "out":
            self.out_ms = max(ms, self.in_ms)
            self.outChanged.emit(self.out_ms)
            self.seekRequested.emit(self.out_ms)
        else:
            self.seekRequested.emit(ms)
        self.update()

    def mouseReleaseEvent(self, _):
        self._drag = None
