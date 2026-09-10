"""
PyQt6 GUI for Clara — a futuristic voice companion with a live waveform.
Runs Bot in a background thread, updates widgets via queue polling.

Usage: python run_gui.py
"""
import html
import math
import queue
import random
import threading

from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import (
    QColor, QFont, QFontDatabase, QPainter, QPainterPath, QPen,
    QLinearGradient, QRadialGradient, QTextCursor,
)
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QTextEdit, QVBoxLayout, QWidget, QGraphicsOpacityEffect,
)

from main import Bot

# ── Palette ──────────────────────────────────────────────────────────
# A crisp, light glass surface — a futuristic waveform doesn't require
# a dark theme, just clear contrast and one glowing accent that pops
# off a bright, disciplined field.
BG = "#F4F6F8"          # cool white
SURFACE = "#FFFFFF"     # panel glass
INK = "#161A20"         # primary text
INK_SOFT = "#767E89"    # secondary text
HAIRLINE = "#E1E5EA"    # borders / rules
ACCENT = "#0FB8AC"      # listening — cyan-teal
ACCENT_SOFT = "#E3F8F5"
WARM = "#7C5CFC"        # speaking — violet
WARM_SOFT = "#EFEAFF"
USER_BUBBLE = "#EEF1F4"
MIC_OFF = "#C7CCD3"

SERIF_FAMILY = "Georgia"        # identity / wordmark voice
SANS_FAMILY = "Segoe UI"        # functional / body voice


def _pick_family(candidates, fallback):
    available = set(QFontDatabase.families())
    for name in candidates:
        if name in available:
            return name
    return fallback


# ── Waveform ─────────────────────────────────────────────────────────
# A live audio-reactive waveform in place of the orb. Idle: a flat,
# faint line with a slow scanning glint. Listening: cyan bars driven by
# smoothed noise. Speaking: violet bars, faster and taller. Built from
# a fixed set of bars with independent phase/amplitude so it reads as
# a signal, not a decorative animation.
class WaveWidget(QWidget):
    BAR_COUNT = 40

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 120)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._tick = 0
        self._state = "IDLE"
        self._levels = [0.05] * self.BAR_COUNT
        self._targets = [0.05] * self.BAR_COUNT
        self._phases = [random.uniform(0, math.tau) for _ in range(self.BAR_COUNT)]

    def set_state(self, state: str):
        self._state = state

    def _advance(self):
        self._tick += 1
        n = self.BAR_COUNT
        if self._state == "LISTENING":
            amp, speed, jitter = 0.55, 0.10, 0.10
        elif self._state == "SPEAKING":
            amp, speed, jitter = 0.85, 0.16, 0.16
        else:
            amp, speed, jitter = 0.06, 0.02, 0.0

        for i in range(n):
            center_falloff = 1.0 - abs(i - n / 2) / (n / 2) * 0.35
            base = (math.sin(self._tick * speed + self._phases[i]) + 1) / 2
            noise = random.uniform(-jitter, jitter)
            self._targets[i] = max(0.04, min(1.0, (0.15 + base * amp + noise) * center_falloff))
            # smooth toward target so bars don't snap
            self._levels[i] += (self._targets[i] - self._levels[i]) * 0.35

    def paintEvent(self, event):
        self._advance()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cy = h / 2
        n = self.BAR_COUNT
        gap = 4
        bar_w = max(2.0, (w - gap * (n - 1)) / n)
        total_w = n * bar_w + (n - 1) * gap
        x0 = (w - total_w) / 2

        if self._state == "LISTENING":
            top, bottom = QColor("#7FEAE0"), QColor(ACCENT)
            glow_c = ACCENT
        elif self._state == "SPEAKING":
            top, bottom = QColor("#CBB6FF"), QColor(WARM)
            glow_c = WARM
        else:
            top, bottom = QColor("#3A3F47"), QColor("#2A2E35")
            glow_c = None

        # faint ambient glow band behind the waveform
        if glow_c:
            band = QLinearGradient(0, cy - h * 0.4, 0, cy + h * 0.4)
            band.setColorAt(0, QColor(glow_c + "00"))
            band.setColorAt(0.5, QColor(glow_c + "14"))
            band.setColorAt(1, QColor(glow_c + "00"))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(band)
            p.drawRect(QRectF(0, 0, w, h))

        p.setPen(Qt.PenStyle.NoPen)
        for i, level in enumerate(self._levels):
            bar_h = max(3.0, level * h * 0.42)
            x = x0 + i * (bar_w + gap)
            grad = QLinearGradient(0, cy - bar_h, 0, cy + bar_h)
            grad.setColorAt(0, top)
            grad.setColorAt(1, bottom)
            p.setBrush(grad)
            radius = bar_w / 2
            p.drawRoundedRect(QRectF(x, cy - bar_h, bar_w, bar_h * 2), radius, radius)

        p.end()


# ── Mic control ──────────────────────────────────────────────────────
class MicButton(QWidget):
    SIZE = 60

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # fully transparent background + no autofill, so Qt/Fusion doesn't
        # paint a default panel/shadow behind this custom-painted circle
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent; border: none;")
        self._active = False
        self._pulse_tick = 0

    def set_active(self, active: bool):
        self._active = active
        self.update()

    def set_label(self, text: str):
        pass

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self.SIZE
        center = QPointF(s / 2, s / 2)
        r = s / 2 - 4

        if self._active:
            self._pulse_tick += 1
            pulse = (math.sin(self._pulse_tick * 0.09) + 1) / 2
            glow_r = r + 3 + pulse * 4
            glow = QRadialGradient(center, glow_r)
            glow.setColorAt(0, QColor(ACCENT + "2A"))
            glow.setColorAt(1, QColor(ACCENT + "00"))
            p.setBrush(glow)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(center, glow_r, glow_r)

        color = QColor(ACCENT) if self._active else QColor(MIC_OFF)
        p.setBrush(color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(center, r, r)

        p.setPen(QPen(QColor("white"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        icon_y = -7
        p.drawRoundedRect(QRectF(center.x() - 3.5, center.y() + icon_y, 7, 12), 3.5, 3.5)
        p.drawArc(QRectF(center.x() - 6, center.y() + icon_y - 5, 12, 9), 0, 180 * 16)
        p.drawLine(QPointF(center.x(), center.y() + icon_y + 12),
                   QPointF(center.x(), center.y() + icon_y + 16))
        p.drawLine(QPointF(center.x() - 4, center.y() + icon_y + 16),
                   QPointF(center.x() + 4, center.y() + icon_y + 16))

        p.end()

    def sizeHint(self):
        return self.minimumSizeHint()


# ── Transcript ───────────────────────────────────────────────────────
class Transcript(QTextEdit):
    def __init__(self, sans_family, parent=None):
        super().__init__(parent)
        self._messages = []
        self._sans = sans_family
        self.setReadOnly(True)
        self.setFrameShape(QTextEdit.Shape.NoFrame)
        self.setStyleSheet(f"""
            QTextEdit {{
                background-color: transparent;
                border: none;
                padding: 4px 2px;
            }}
        """)

    def append_message(self, sender: str, text: str, color: str):
        self._messages.append((sender or "Clara", text, color))
        self._render()

    def append_bot_delta(self, text: str):
        if self._messages and self._messages[-1][0] == "Clara":
            sender, previous, color = self._messages[-1]
            self._messages[-1] = (sender, previous + text, color)
        else:
            self._messages.append(("Clara", text, INK))
        self._render()

    def _render(self):
        blocks = [self._message_html(s, t, c) for s, t, c in self._messages]
        self.setHtml(f'<div style="font-family:{self._sans};">' + "".join(blocks) + "</div>")
        self.moveCursor(QTextCursor.MoveOperation.End)

    @staticmethod
    def _message_html(sender: str, text: str, color: str):
        safe_text = html.escape(text).replace("\n", "<br>")
        if sender == "You":
            return f'''<table width="100%" cellspacing="0" cellpadding="0"><tr><td align="right">
                <table cellspacing="0" cellpadding="0"><tr><td bgcolor="{USER_BUBBLE}"
                style="padding: 10px 14px; border-radius: 14px;">
                <font color="{color}" size="3">{safe_text}</font></td></tr></table>
                </td></tr></table><div style="height:14px;"></div>'''
        return f'''<table width="100%" cellspacing="0" cellpadding="0"><tr><td>
            <font color="{INK_SOFT}" size="2"><b>Clara</b></font><br>
            <font color="{color}" size="3">{safe_text}</font>
            </td></tr></table><div style="height:18px;"></div>'''

    def clear(self):
        super().clear()
        self._messages.clear()
        self.setPlaceholderText("Say something — I'm listening.")


# ── Status ───────────────────────────────────────────────────────────
class StatusText(QLabel):
    def __init__(self, sans_family, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sans = sans_family
        self._state = "INIT"
        self._update_style()

    def set_state(self, state: str, detail: str = ""):
        self._state = state
        labels = {
            "LISTENING": "Listening",
            "SPEAKING": "Speaking",
            "INIT": "Getting ready",
        }
        self.setText(labels.get(state, state.title() if state else ""))
        self._update_style()

    def _update_style(self):
        color = {"LISTENING": ACCENT, "SPEAKING": WARM}.get(self._state, INK_SOFT)
        self.setStyleSheet(f"""
            color: {color};
            font-family: '{self._sans}';
            font-size: 10.5pt;
            font-weight: 500;
            padding: 2px;
        """)


# ── Main window ──────────────────────────────────────────────────────
class App(QMainWindow):
    POLL_MS = 50

    def __init__(self):
        super().__init__()

        self._serif = _pick_family(
            ["Fraunces", "Lora", "Georgia", "Iowan Old Style"], "Georgia"
        )
        self._sans = _pick_family(
            ["Inter", "Segoe UI", "Helvetica Neue", "Arial"], "Segoe UI"
        )

        self.setWindowTitle("Clara")
        self.setMinimumSize(420, 660)
        self.resize(440, 740)
        self.setStyleSheet(f"background-color: {BG};")

        self._queue: queue.Queue = queue.Queue()
        self._build_ui()
        self._setup_bot()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(32, 30, 32, 26)
        layout.setSpacing(6)

        # identity — centered wordmark carries the personality
        title = QLabel("Clara")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"""
            color: {INK};
            font-family: '{self._serif}';
            font-size: 25pt;
            font-weight: 500;
        """)
        layout.addWidget(title)

        subtitle = QLabel("A quiet place to think out loud.")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(f"""
            color: {INK_SOFT};
            font-family: '{self._sans}';
            font-size: 10.5pt;
            margin-bottom: 6px;
        """)
        layout.addWidget(subtitle)

        layout.addSpacing(10)

        # waveform — the emotional center of the window
        self.orb = WaveWidget()
        self.orb.setStyleSheet("background: transparent;")
        self.orb.setFixedHeight(148)
        layout.addWidget(self.orb)

        self.status = StatusText(self._sans)
        layout.addWidget(self.status)

        layout.addSpacing(14)

        # a single hairline separates "presence" from "conversation"
        rule = QWidget()
        rule.setFixedHeight(1)
        rule.setStyleSheet(f"background-color: {HAIRLINE};")
        layout.addWidget(rule)

        layout.addSpacing(10)

        self.transcript = Transcript(self._sans)
        self.transcript.setPlaceholderText("Say something — I'm listening.")
        layout.addWidget(self.transcript, stretch=1)

        # bottom row: clear (quiet, left) — mic (focal, center) — spacer (right)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 14, 0, 0)
        bottom.setSpacing(12)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setFixedHeight(32)
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {INK_SOFT};
                border: none;
                font-family: '{self._sans}';
                font-size: 9.5pt;
                font-weight: 500;
                text-align: left;
                padding: 0;
            }}
            QPushButton:hover {{
                color: {INK};
            }}
        """)
        self.clear_btn.clicked.connect(self.transcript.clear)
        bottom.addWidget(self.clear_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        bottom.addStretch()

        self.mic = MicButton()
        self.mic.mousePressEvent = lambda _: None
        bottom.addWidget(self.mic, alignment=Qt.AlignmentFlag.AlignVCenter)

        bottom.addStretch()

        # balances the "Clear" label so the mic stays visually centered
        spacer = QLabel("")
        spacer.setFixedWidth(self.clear_btn.sizeHint().width())
        bottom.addWidget(spacer)

        layout.addLayout(bottom)

    # ---------------------------------------------------------------- bot
    def _setup_bot(self):
        self.bot = Bot()
        self.bot.on_reply_delta = lambda t: self._queue.put(("bot_delta", t))
        self.bot.on_reply_done = lambda: self._queue.put(("bot_done",))
        self.bot.on_partial = lambda t: self._queue.put(("partial", t))
        self.bot.on_user_line = lambda t: self._queue.put(("user_line", t))

        threading.Thread(target=self.bot.run, daemon=True).start()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(self.POLL_MS)

    # -------------------------------------------------------------- poll
    def _poll(self):
        while not self._queue.empty():
            kind, *args = self._queue.get_nowait()

            if kind == "partial":
                self.status.set_state("LISTENING")

            elif kind == "user_line":
                self.transcript.append_message("You", args[0], INK)
                self.status.set_state("SPEAKING")
                self.mic.set_active(False)

            elif kind == "bot_delta":
                self.transcript.append_bot_delta(args[0])

            elif kind == "bot_done":
                self.status.set_state("LISTENING")
                self.mic.set_active(True)

        self.orb.set_state(self.bot.state)
        self.orb.update()


def main():
    import sys
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = App()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()