"""
PyQt6 GUI for the voice bot — light theme with animated orb.
Runs Bot in a background thread, updates widgets via queue polling.

Usage: python run_gui.py
"""
import html
import math
import queue
import threading

from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import (
    QColor, QFont, QPainter, QPainterPath, QPen, QLinearGradient,
    QRadialGradient, QTextCursor,
)
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

from main import Bot

# -- light palette --
BG = "#f4f1ea"
SURFACE = "#fffdf8"
TEXT = "#24231f"
TEXT_DIM = "#817d73"
ACCENT = "#0f766e"
USER_COLOR = "#155e75"
BOT_COLOR = "#3f3b35"
MIC_ON = "#0f766e"
MIC_OFF = "#b4b0a6"
BORDER = "#e3ded3"


# ── Iridescent orb ──────────────────────────────────────────────────
class OrbWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 200)
        self._tick = 0
        self._state = "IDLE"

    def set_state(self, state: str):
        self._state = state

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._tick += 1

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        r = min(w, h) / 2 - 10

        # outer glow
        glow_r = r + 20
        glow = QRadialGradient(QPointF(cx, cy), glow_r)
        if self._state == "LISTENING":
            glow.setColorAt(0, QColor("#0f766e28"))
        elif self._state == "SPEAKING":
            glow.setColorAt(0, QColor("#d9770628"))
        else:
            glow.setColorAt(0, QColor("#a8a29e18"))
        glow.setColorAt(1, QColor("#00000000"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        # base sphere
        base = QRadialGradient(QPointF(cx - r * 0.2, cy - r * 0.2), r * 1.2)
        if self._state == "LISTENING":
            base.setColorAt(0, QColor("#d9f2ee"))
            base.setColorAt(0.5, QColor("#a7d9d2"))
            base.setColorAt(1, QColor("#65b8ad"))
        elif self._state == "SPEAKING":
            base.setColorAt(0, QColor("#fff1d8"))
            base.setColorAt(0.5, QColor("#f5d49d"))
            base.setColorAt(1, QColor("#e6a84f"))
        else:
            base.setColorAt(0, QColor("#faf8f2"))
            base.setColorAt(0.5, QColor("#e8e2d6"))
            base.setColorAt(1, QColor("#cfc7b8"))
        p.setBrush(base)
        p.drawEllipse(QPointF(cx, cy), r, r)

        # iridescent highlights — animated swirling blobs
        t = self._tick * 0.02
        blobs = [
            (0.0, 0.35, 0.28),
            (2.1, 0.30, 0.25),
            (4.2, 0.25, 0.30),
            (1.0, 0.40, 0.22),
            (3.1, 0.20, 0.35),
        ]
        for phase, speed, size_frac in blobs:
            angle = t * speed + phase
            bx = cx + math.cos(angle) * r * 0.35
            by = cy + math.sin(angle * 0.7) * r * 0.35
            br = r * size_frac

            highlight = QRadialGradient(QPointF(bx, by), br)
            if self._state == "LISTENING":
                highlight.setColorAt(0, QColor("#ffffff90"))
                highlight.setColorAt(0.6, QColor("#2f9e9380"))
                highlight.setColorAt(1, QColor("#00000000"))
            elif self._state == "SPEAKING":
                highlight.setColorAt(0, QColor("#fff8e890"))
                highlight.setColorAt(0.6, QColor("#d9770680"))
                highlight.setColorAt(1, QColor("#00000000"))
            else:
                highlight.setColorAt(0, QColor("#ffffff70"))
                highlight.setColorAt(0.6, QColor("#b8b0a040"))
                highlight.setColorAt(1, QColor("#00000000"))
            p.setBrush(highlight)
            p.drawEllipse(QPointF(bx, by), br, br)

        # specular highlight (top-left)
        spec = QRadialGradient(QPointF(cx - r * 0.3, cy - r * 0.35), r * 0.4)
        spec.setColorAt(0, QColor("#ffffff90"))
        spec.setColorAt(1, QColor("#ffffff00"))
        p.setBrush(spec)
        p.drawEllipse(QPointF(cx, cy), r, r)

        p.end()


# ── Circular mic button ─────────────────────────────────────────────
class MicButton(QWidget):
    SIZE = 64

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
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
        r = s / 2 - 3

        # glow pulse when active
        if self._active:
            self._pulse_tick += 1
            pulse = (math.sin(self._pulse_tick * 0.1) + 1) / 2
            glow_r = r + 4 + pulse * 5
            glow = QRadialGradient(center, glow_r)
            glow.setColorAt(0, QColor(MIC_ON + "30"))
            glow.setColorAt(1, QColor(MIC_ON + "00"))
            p.setBrush(glow)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(center, glow_r, glow_r)

        # circle
        color = QColor(MIC_ON) if self._active else QColor(MIC_OFF)
        p.setBrush(color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(center, r, r)

        # mic icon
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


# ── Transcript ──────────────────────────────────────────────────────
class Transcript(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._messages = []
        self.setReadOnly(True)
        self.setStyleSheet(f"""
            background-color: {SURFACE};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 16px;
            padding: 16px;
            font-family: 'SF Pro Text', 'Segoe UI', 'Helvetica Neue', sans-serif;
            font-size: 11pt;
            selection-background-color: {ACCENT};
        """)

    def append_message(self, sender: str, text: str, color: str):
        self._messages.append((sender or "Clara", text, color))
        self._render()

    def append_bot_delta(self, text: str):
        if self._messages and self._messages[-1][0] == "Clara":
            sender, previous, color = self._messages[-1]
            self._messages[-1] = (sender, previous + text, color)
        else:
            self._messages.append(("Clara", text, BOT_COLOR))
        self._render()

    def _render(self):
        blocks = []
        for sender, text, color in self._messages:
            blocks.append(self._message_html(sender, text, color))
        self.setHtml("".join(blocks))
        self.moveCursor(QTextCursor.MoveOperation.End)

    @staticmethod
    def _message_html(sender: str, text: str, color: str):
        safe_text = html.escape(text).replace("\n", "<br>")
        if sender == "You":
            return f'''<table width="100%" cellspacing="0" cellpadding="0"><tr><td align="right">
                <table cellspacing="0" cellpadding="0"><tr><td bgcolor="#e2f0ef" style="padding: 9px 12px;">
                <font color="{color}"><b>You</b><br>{safe_text}</font></td></tr></table>
                </td></tr></table><br>'''
        return f'''<table width="100%" cellspacing="0" cellpadding="0"><tr><td>
            <font color="{color}"><b>Clara</b><br>{safe_text}</font>
            </td></tr></table><br>'''

    def clear(self):
        super().clear()
        self._messages.clear()
        self.setPlaceholderText("Your conversation will appear here")


# ── Status text ─────────────────────────────────────────────────────
class StatusText(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._state = "INIT"
        self._update_style()

    def set_state(self, state: str, detail: str = ""):
        self._state = state
        labels = {
            "LISTENING": "Listening...",
            "SPEAKING": "Speaking...",
            "INIT": "Starting...",
        }
        self.setText(labels.get(state, state))
        self._update_style()

    def _update_style(self):
        self.setStyleSheet(f"""
            color: {TEXT_DIM};
            font-size: 9pt;
            font-weight: 600;
            letter-spacing: 1px;
            padding: 5px;
        """)


# ── Main window ─────────────────────────────────────────────────────
class App(QMainWindow):
    POLL_MS = 50

    def __init__(self):
        super().__init__()
        self.setWindowTitle("English Practice")
        self.setMinimumSize(440, 680)
        self.resize(460, 760)
        self.setStyleSheet(f"background-color: {BG};")

        self._queue: queue.Queue = queue.Queue()
        self._build_ui()
        self._setup_bot()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(30, 26, 30, 24)
        layout.setSpacing(10)

        # title
        header = QHBoxLayout()
        title = QLabel("English Practice")
        title.setStyleSheet(f"color: {TEXT}; font-size: 19pt; font-weight: 700;")
        header.addWidget(title)
        header.addStretch()
        live = QLabel("●  LIVE")
        live.setStyleSheet(f"color: {ACCENT}; font-size: 8pt; font-weight: 700; letter-spacing: 1px;")
        header.addWidget(live)
        layout.addLayout(header)

        subtitle = QLabel("Speak naturally, I'll follow.")
        subtitle.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10pt; margin-bottom: 8px;")
        layout.addWidget(subtitle)

        # orb (center)
        self.orb = OrbWidget()
        self.orb.setStyleSheet("background: transparent;")
        self.orb.setFixedHeight(160)
        layout.addWidget(self.orb, alignment=Qt.AlignmentFlag.AlignCenter)

        # status
        self.status = StatusText()
        layout.addWidget(self.status)

        # transcript (subtle panel)
        self.transcript = Transcript()
        self.transcript.setMinimumHeight(210)
        self.transcript.setPlaceholderText("Your conversation will appear here")
        layout.addWidget(self.transcript)

        # bottom row: clear + mic
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 8, 0, 0)
        bottom.setSpacing(12)

        self.clear_btn = QPushButton("Clear conversation")
        self.clear_btn.setFixedHeight(36)
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {TEXT_DIM};
                border: none;
                border-radius: 6px;
                padding: 0 14px;
                font-size: 9pt;
                font-weight: 600;
            }}
            QPushButton:hover {{
                color: {TEXT};
                border-color: {ACCENT};
            }}
        """)
        self.clear_btn.clicked.connect(self.transcript.clear)
        bottom.addWidget(self.clear_btn)

        bottom.addStretch()

        self.mic = MicButton()
        self.mic.mousePressEvent = lambda _: None
        bottom.addWidget(self.mic)

        bottom.addStretch()

        hint = QLabel("Speak when the ring is teal")
        hint.setStyleSheet(f"color: {TEXT_DIM}; font-size: 8pt;")
        bottom.addWidget(hint)

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
                self.transcript.append_message("You", args[0], USER_COLOR)
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
