"""
Custom color picker widget.
Hue wheel + saturation/brightness square + sliders + hex/RGB inputs.
"""

import math
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QSpinBox, QDialog,
    QPushButton, QSizePolicy, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QRectF, QSize
from PyQt6.QtGui import (
    QPainter, QColor, QLinearGradient, QConicalGradient,
    QRadialGradient, QPen, QBrush, QImage, QPainterPath,
    QMouseEvent,
)


# ── Hue + Saturation/Brightness square ───────────────────────────────────────

class ColorSquare(QWidget):
    """
    Saturation (x) vs Brightness (y) picker square for a fixed hue.
    """
    changed = pyqtSignal(float, float)   # sat, val  (0.0–1.0)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hue  = 0.0   # 0–360
        self._sat  = 1.0
        self._val  = 1.0
        self._drag = False
        self.setMinimumSize(200, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_hue(self, hue: float):
        self._hue = hue
        self.update()

    def set_sv(self, sat: float, val: float):
        self._sat = max(0.0, min(1.0, sat))
        self._val = max(0.0, min(1.0, val))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(4, 4, -4, -4)

        # Draw S/V square using a QImage for performance
        img = QImage(rect.width(), rect.height(), QImage.Format.Format_RGB32)
        for xi in range(rect.width()):
            for yi in range(rect.height()):
                s = xi / max(1, rect.width()  - 1)
                v = 1.0 - yi / max(1, rect.height() - 1)
                c = QColor.fromHsvF(self._hue / 360.0, s, v)
                img.setPixel(xi, yi, c.rgb())
        painter.drawImage(rect, img)

        # Border
        painter.setPen(QPen(QColor("#555"), 1))
        painter.drawRect(rect)

        # Crosshair cursor
        cx = int(rect.left() + self._sat * rect.width())
        cy = int(rect.top()  + (1.0 - self._val) * rect.height())
        pen_outer = QPen(QColor("white"), 2)
        pen_inner = QPen(QColor("black"), 1)
        for pen, r in [(pen_outer, 6), (pen_inner, 5)]:
            painter.setPen(pen)
            painter.drawEllipse(QPointF(cx, cy), r, r)

    def _pos_to_sv(self, x: int, y: int):
        rect = self.rect().adjusted(4, 4, -4, -4)
        s = max(0.0, min(1.0, (x - rect.left()) / max(1, rect.width())))
        v = max(0.0, min(1.0, 1.0 - (y - rect.top())  / max(1, rect.height())))
        return s, v

    def mousePressEvent(self, e: QMouseEvent):
        self._drag = True
        s, v = self._pos_to_sv(e.position().x(), e.position().y())
        self._sat, self._val = s, v
        self.update()
        self.changed.emit(s, v)

    def mouseMoveEvent(self, e: QMouseEvent):
        if self._drag:
            s, v = self._pos_to_sv(e.position().x(), e.position().y())
            self._sat, self._val = s, v
            self.update()
            self.changed.emit(s, v)

    def mouseReleaseEvent(self, e: QMouseEvent):
        self._drag = False


class HueRing(QWidget):
    """
    Circular hue ring picker.
    """
    changed = pyqtSignal(float)   # hue 0–360

    RING_WIDTH = 18

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hue  = 0.0
        self._drag = False
        self.setMinimumSize(240, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_hue(self, hue: float):
        self._hue = hue % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        r_outer = min(w, h) / 2 - 4
        r_inner = r_outer - self.RING_WIDTH

        # Draw hue ring as conic gradient segments
        steps = 360
        for i in range(steps):
            angle = i
            color = QColor.fromHsvF(angle / 360.0, 1.0, 1.0)
            painter.setPen(QPen(color, 0))
            painter.setBrush(QBrush(color))
            path = QPainterPath()
            # Draw a thin wedge
            start_a = angle
            span_a  = 1.2  # slightly overlapping for no gaps
            path.moveTo(cx, cy)
            path.arcTo(
                QRectF(cx - r_outer, cy - r_outer, r_outer * 2, r_outer * 2),
                -start_a, -span_a
            )
            path.arcTo(
                QRectF(cx - r_inner, cy - r_inner, r_inner * 2, r_inner * 2),
                -(start_a + span_a), span_a
            )
            path.closeSubpath()
            painter.drawPath(path)

        # Black border rings
        painter.setPen(QPen(QColor("#333"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), r_outer, r_outer)
        painter.drawEllipse(QPointF(cx, cy), r_inner, r_inner)

        # Hue indicator
        angle_rad = math.radians(-self._hue)
        mid_r = (r_outer + r_inner) / 2
        ix = cx + mid_r * math.cos(angle_rad)
        iy = cy + mid_r * math.sin(angle_rad)
        painter.setPen(QPen(QColor("white"), 2))
        painter.setBrush(QBrush(QColor.fromHsvF(self._hue / 360.0, 1.0, 1.0)))
        painter.drawEllipse(QPointF(ix, iy), self.RING_WIDTH / 2 - 2,
                            self.RING_WIDTH / 2 - 2)
        painter.setPen(QPen(QColor("black"), 1))
        painter.drawEllipse(QPointF(ix, iy), self.RING_WIDTH / 2 - 2,
                            self.RING_WIDTH / 2 - 2)

    def _pos_to_hue(self, x: float, y: float) -> float:
        cx, cy = self.width() / 2, self.height() / 2
        angle = math.degrees(math.atan2(y - cy, x - cx))
        return (-angle) % 360

    def _in_ring(self, x: float, y: float) -> bool:
        cx, cy = self.width() / 2, self.height() / 2
        r_outer = min(self.width(), self.height()) / 2 - 4
        r_inner = r_outer - self.RING_WIDTH
        dist = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
        return r_inner <= dist <= r_outer + 4

    def mousePressEvent(self, e: QMouseEvent):
        if self._in_ring(e.position().x(), e.position().y()):
            self._drag = True
            h = self._pos_to_hue(e.position().x(), e.position().y())
            self._hue = h
            self.update()
            self.changed.emit(h)

    def mouseMoveEvent(self, e: QMouseEvent):
        if self._drag:
            h = self._pos_to_hue(e.position().x(), e.position().y())
            self._hue = h
            self.update()
            self.changed.emit(h)

    def mouseReleaseEvent(self, e: QMouseEvent):
        self._drag = False


class AlphaSlider(QWidget):
    """Horizontal alpha/opacity slider with checkerboard background."""
    changed = pyqtSignal(int)   # 0–255

    def __init__(self, parent=None):
        super().__init__(parent)
        self._alpha = 255
        self._hue   = 0.0
        self._drag  = False
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_color(self, hue: float, alpha: int):
        self._hue   = hue
        self._alpha = alpha
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(4, 4, -4, -4)

        # Checkerboard
        checker_size = 6
        for xi in range(0, rect.width(), checker_size):
            for yi in range(0, rect.height(), checker_size):
                c = QColor("#ccc") if (xi // checker_size + yi // checker_size) % 2 == 0 \
                    else QColor("#888")
                painter.fillRect(
                    rect.left() + xi, rect.top() + yi,
                    min(checker_size, rect.width() - xi),
                    min(checker_size, rect.height() - yi), c
                )

        # Alpha gradient
        grad = QLinearGradient(rect.left(), 0, rect.right(), 0)
        base = QColor.fromHsvF(self._hue / 360.0, 1.0, 1.0)
        transparent = QColor(base)
        transparent.setAlpha(0)
        grad.setColorAt(0, transparent)
        grad.setColorAt(1, base)
        painter.fillRect(rect, grad)

        # Border
        painter.setPen(QPen(QColor("#555"), 1))
        painter.drawRect(rect)

        # Handle
        hx = int(rect.left() + (self._alpha / 255.0) * rect.width())
        painter.setPen(QPen(QColor("white"), 2))
        painter.drawLine(hx, rect.top(), hx, rect.bottom())

    def _pos_to_alpha(self, x: float) -> int:
        rect = self.rect().adjusted(4, 4, -4, -4)
        a = (x - rect.left()) / max(1, rect.width())
        return max(0, min(255, int(a * 255)))

    def mousePressEvent(self, e):
        self._drag  = True
        self._alpha = self._pos_to_alpha(e.position().x())
        self.update(); self.changed.emit(self._alpha)

    def mouseMoveEvent(self, e):
        if self._drag:
            self._alpha = self._pos_to_alpha(e.position().x())
            self.update(); self.changed.emit(self._alpha)

    def mouseReleaseEvent(self, e):
        self._drag = False


class ColorPreviewBar(QWidget):
    """Before / after color comparison bar."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._before = QColor("#888888")
        self._after  = QColor("#888888")
        self.setFixedHeight(32)

    def set_before(self, c: QColor): self._before = c; self.update()
    def set_after(self, c: QColor):  self._after  = c; self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        w, h = self.width(), self.height()
        # Left half = before, right half = after
        painter.fillRect(0,     0, w // 2, h, self._before)
        painter.fillRect(w // 2, 0, w - w // 2, h, self._after)
        # Labels
        painter.setPen(QColor("white"))
        painter.setFont(self.font())
        painter.drawText(4, h - 6, "Before")
        painter.drawText(w // 2 + 4, h - 6, "After")
        # Divider
        painter.setPen(QPen(QColor("#333"), 2))
        painter.drawLine(w // 2, 0, w // 2, h)


# ── Full color picker widget ──────────────────────────────────────────────────

class ColorPickerWidget(QWidget):
    """
    Full graphical color picker:
    Hue ring + SV square + alpha slider + hex/RGB/HSV inputs + preview bar.
    """
    color_changed = pyqtSignal(QColor)

    def __init__(self, initial: QColor = None, parent=None):
        super().__init__(parent)
        self._color  = initial or QColor("#5c9bd6")
        self._before = QColor(self._color)
        self._updating = False
        self._build_ui()
        self._set_color_silent(self._color)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(8, 8, 8, 8)

        # ── Top: ring + square side by side ──────────────────────────────────
        picker_row = QHBoxLayout()
        picker_row.setSpacing(8)

        self._ring   = HueRing()
        self._square = ColorSquare()
        self._ring.changed.connect(self._on_hue_changed)
        self._square.changed.connect(self._on_sv_changed)

        picker_row.addWidget(self._ring,   stretch=2)
        picker_row.addWidget(self._square, stretch=3)
        root.addLayout(picker_row)

        # ── Alpha slider ──────────────────────────────────────────────────────
        alpha_row = QHBoxLayout()
        alpha_lbl = QLabel("Alpha:")
        alpha_lbl.setFixedWidth(40)
        self._alpha_slider = AlphaSlider()
        self._alpha_slider.changed.connect(self._on_alpha_changed)
        self._alpha_spin = QSpinBox()
        self._alpha_spin.setRange(0, 255)
        self._alpha_spin.setValue(255)
        self._alpha_spin.setFixedWidth(52)
        self._alpha_spin.valueChanged.connect(self._on_alpha_spin_changed)
        alpha_row.addWidget(alpha_lbl)
        alpha_row.addWidget(self._alpha_slider, stretch=1)
        alpha_row.addWidget(self._alpha_spin)
        root.addLayout(alpha_row)

        # ── Preview bar ───────────────────────────────────────────────────────
        self._preview = ColorPreviewBar()
        root.addWidget(self._preview)

        # ── Hex + RGB + HSV inputs ────────────────────────────────────────────
        inputs_row = QHBoxLayout()
        inputs_row.setSpacing(12)

        # Hex
        hex_col = QVBoxLayout()
        hex_col.addWidget(QLabel("Hex"))
        self._hex_edit = QLineEdit()
        self._hex_edit.setMaxLength(9)
        self._hex_edit.setFixedWidth(82)
        self._hex_edit.setFont(self.font())
        self._hex_edit.textEdited.connect(self._on_hex_edited)
        hex_col.addWidget(self._hex_edit)
        inputs_row.addLayout(hex_col)

        # RGB
        for label, attr in [("R", "_r_spin"), ("G", "_g_spin"), ("B", "_b_spin")]:
            col = QVBoxLayout()
            col.addWidget(QLabel(label))
            spin = QSpinBox()
            spin.setRange(0, 255)
            spin.setFixedWidth(54)
            spin.valueChanged.connect(self._on_rgb_changed)
            setattr(self, attr, spin)
            col.addWidget(spin)
            inputs_row.addLayout(col)

        # HSV
        for label, attr, maxv in [
            ("H°", "_h_spin", 359),
            ("S%", "_s_spin", 100),
            ("V%", "_v_spin", 100),
        ]:
            col = QVBoxLayout()
            col.addWidget(QLabel(label))
            spin = QSpinBox()
            spin.setRange(0, maxv)
            spin.setFixedWidth(54)
            spin.valueChanged.connect(self._on_hsv_changed)
            setattr(self, attr, spin)
            col.addWidget(spin)
            inputs_row.addLayout(col)

        inputs_row.addStretch()
        root.addLayout(inputs_row)

    # ── Signal handlers ───────────────────────────────────────────────────────

    def _on_hue_changed(self, hue: float):
        if self._updating: return
        h, s, v, a = self._color.hsvHueF(), self._color.hsvSaturationF(), \
                     self._color.valueF(), self._color.alphaF()
        c = QColor.fromHsvF(hue / 360.0, s, v)
        c.setAlphaF(a)
        self._set_color_silent(c)
        self.color_changed.emit(self._color)

    def _on_sv_changed(self, sat: float, val: float):
        if self._updating: return
        h = self._color.hsvHueF()
        a = self._color.alphaF()
        c = QColor.fromHsvF(max(0.0, h), sat, val)
        c.setAlphaF(a)
        self._set_color_silent(c)
        self.color_changed.emit(self._color)

    def _on_alpha_changed(self, alpha: int):
        if self._updating: return
        c = QColor(self._color)
        c.setAlpha(alpha)
        self._set_color_silent(c)
        self.color_changed.emit(self._color)

    def _on_alpha_spin_changed(self, alpha: int):
        if self._updating: return
        c = QColor(self._color)
        c.setAlpha(alpha)
        self._set_color_silent(c)
        self.color_changed.emit(self._color)

    def _on_hex_edited(self, text: str):
        if self._updating: return
        text = text.strip()
        if not text.startswith("#"):
            text = "#" + text
        c = QColor(text)
        if c.isValid():
            self._set_color_silent(c)
            self.color_changed.emit(self._color)

    def _on_rgb_changed(self):
        if self._updating: return
        c = QColor(self._r_spin.value(), self._g_spin.value(),
                   self._b_spin.value(), self._color.alpha())
        self._set_color_silent(c)
        self.color_changed.emit(self._color)

    def _on_hsv_changed(self):
        if self._updating: return
        c = QColor.fromHsv(
            self._h_spin.value(),
            int(self._s_spin.value() * 2.55),
            int(self._v_spin.value() * 2.55),
            self._color.alpha(),
        )
        self._set_color_silent(c)
        self.color_changed.emit(self._color)

    # ── Internal sync ─────────────────────────────────────────────────────────

    def _set_color_silent(self, c: QColor):
        """Update all widgets from a new color without triggering signals."""
        self._updating = True
        self._color = QColor(c)
        h = max(0, c.hsvHue())
        s = c.hsvSaturation()
        v = c.value()

        self._ring.set_hue(h)
        self._square.set_hue(h)
        self._square.set_sv(s / 255.0, v / 255.0)
        self._alpha_slider.set_color(h, c.alpha())

        self._hex_edit.setText(c.name(QColor.NameFormat.HexArgb)
                               if c.alpha() < 255 else c.name().upper())
        self._r_spin.setValue(c.red())
        self._g_spin.setValue(c.green())
        self._b_spin.setValue(c.blue())
        self._h_spin.setValue(h)
        self._s_spin.setValue(int(s / 2.55))
        self._v_spin.setValue(int(v / 2.55))
        self._alpha_spin.setValue(c.alpha())
        self._preview.set_before(self._before)
        self._preview.set_after(c)
        self._updating = False

    def set_color(self, c: QColor):
        self._before = QColor(c)
        self._set_color_silent(c)

    def color(self) -> QColor:
        return QColor(self._color)

    def hex_color(self) -> str:
        if self._color.alpha() < 255:
            return self._color.name(QColor.NameFormat.HexArgb)
        return self._color.name().lower()


# ── Dialog wrapper ────────────────────────────────────────────────────────────

class ColorPickerDialog(QDialog):
    """
    Standalone dialog wrapping ColorPickerWidget.
    Drop-in replacement for QColorDialog.
    """

    def __init__(self, initial: QColor = None, title: str = "Pick Color",
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(520, 440)
        self._accepted_color: QColor = initial or QColor("#5c9bd6")
        self._build_ui(initial)

    def _build_ui(self, initial: QColor):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self._picker = ColorPickerWidget(initial)
        layout.addWidget(self._picker)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setFixedHeight(30)
        cancel.clicked.connect(self.reject)
        ok = QPushButton("OK")
        ok.setFixedHeight(30)
        ok.setDefault(True)
        ok.clicked.connect(self._on_ok)
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

    def _on_ok(self):
        self._accepted_color = self._picker.color()
        self.accept()

    def selected_color(self) -> QColor:
        return self._accepted_color

    @staticmethod
    def get_color(initial: QColor = None, parent=None,
                  title: str = "Pick Color") -> tuple[QColor, bool]:
        """
        Static convenience method matching QColorDialog.getColor() signature.
        Returns (color, accepted).
        """
        dlg = ColorPickerDialog(initial, title, parent)
        accepted = dlg.exec() == QDialog.DialogCode.Accepted
        return dlg.selected_color(), accepted
