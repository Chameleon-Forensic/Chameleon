"""
widgets.py
Tasarim sistemine uygun, tekrar kullanilabilir PySide6 bilesenleri.
Ekranlar (launcher/chameleon_qt.py, gui_v2.py, ram_gui.py -- gecis
tamamlaninca) duz QPushButton/QLineEdit yerine bunlari kullanir; renk/
tipografi/bosluk degerleri SADECE theme_qt.py'de tanimli, burada tekrar
yazilmiyor.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
    QLabel, QLineEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from . import theme_qt as t


def _tint(hex_color, alpha=38):
    """hex_color'un dusuk-opakli 'pill' arka plani icin rgba() string'i --
    Qt QSS'de alpha 0-255 araliginda (CSS'teki 0-1 degil)."""
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


# ---------------------------------------------------------------------------
# Butonlar -- normal / hover / pressed / disabled, 4 net durum
# ---------------------------------------------------------------------------
class PrimaryButton(QPushButton):
    """Ana aksiyon butonu (marka rengi dolu). Her ekranda en fazla bir tane
    'birincil' aksiyon one cikmali -- ikincil aksiyonlar SecondaryButton."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(36)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {t.ACCENT};
                color: white;
                border: none;
                border-radius: {t.RADIUS}px;
                padding: 6px 18px;
                font-family: "{t.FONT_UI}";
                font-size: {t.SIZE_BODY}px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {t.ACCENT_HOVER}; }}
            QPushButton:pressed {{ background-color: #1D4ED8; }}
            QPushButton:disabled {{ background-color: {t.BG_LAYER2}; color: {t.TEXT_SECONDARY}; }}
        """)


class SecondaryButton(QPushButton):
    """Ikincil aksiyon: kenarlikli, dolgusuz -- gorsel olarak geride durur."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(36)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {t.TEXT_MAIN};
                border: 1px solid {t.BORDER};
                border-radius: {t.RADIUS}px;
                padding: 6px 18px;
                font-family: "{t.FONT_UI}";
                font-size: {t.SIZE_BODY}px;
            }}
            QPushButton:hover {{ background-color: {t.BG_LAYER2}; }}
            QPushButton:pressed {{ background-color: {t.BG_SURFACE}; }}
            QPushButton:disabled {{ color: {t.TEXT_SECONDARY}; border-color: {t.BG_LAYER2}; }}
        """)


# ---------------------------------------------------------------------------
# Girdi alanlari -- focus'ta kenarlik marka rengine doner + hafif glow
# ---------------------------------------------------------------------------
class Input(QLineEdit):
    """Genel metin girisi. Teknik degerler (IP/port/host/hash/yol) icin
    MonoInput kullanin -- tek basina bu ayrim 'ciddi teknik arac' hissi
    veriyor, ihmal etmeyin (tasarim sisteminin acik talimati)."""

    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        if placeholder:
            self.setPlaceholderText(placeholder)
        self.setMinimumHeight(32)
        self._apply_style(focused=False)
        self._glow = QGraphicsDropShadowEffect(self)
        self._glow.setColor(QColor(t.ACCENT))
        self._glow.setBlurRadius(0)
        self._glow.setOffset(0, 0)
        self.setGraphicsEffect(self._glow)

    def _font_family(self):
        return t.FONT_UI

    def _apply_style(self, focused):
        border_color = t.ACCENT if focused else t.BORDER
        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: {t.BG_LAYER2};
                color: {t.TEXT_MAIN};
                border: 1px solid {border_color};
                border-radius: {t.RADIUS}px;
                padding: 4px 10px;
                font-family: "{self._font_family()}";
                font-size: {t.SIZE_BODY}px;
            }}
            QLineEdit:disabled {{ color: {t.TEXT_SECONDARY}; }}
        """)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._apply_style(focused=True)
        self._glow.setBlurRadius(14)  # hafif glow, abartisiz

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._apply_style(focused=False)
        self._glow.setBlurRadius(0)


class MonoInput(Input):
    """IP, port, host, SHA-256, dosya/disk yolu gibi teknik degerler icin --
    JetBrains Mono, genel Inter arayuzden gorsel olarak ayrisiyor."""

    def _font_family(self):
        return t.FONT_MONO


class MonoLabel(QLabel):
    """Salt-okunur teknik deger gosterimi (orn. hesaplanan hash) icin."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(f"""
            QLabel {{
                color: {t.TEXT_MAIN};
                font-family: "{t.FONT_MONO}";
                font-size: {t.SIZE_BODY}px;
                background: transparent;
            }}
        """)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)


# ---------------------------------------------------------------------------
# Radio buton -- ozel cizilmis (tasarim sisteminin acik talimati)
# ---------------------------------------------------------------------------
class RadioButton(QAbstractButton):
    """
    Ozel çizilmiş radio dugmesi: secili -> marka rengi dolu ic daire +
    ince kenarlik, degilse sadece ince kenarlikli bos daire. Kullanimi
    QRadioButton ile ayni (checkable, autoExclusive icin bir QButtonGroup'a
    eklenir), sadece cizimi bizim.
    """

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(24)

    def sizeHint(self):
        fm = self.fontMetrics()
        width = 22 + fm.horizontalAdvance(self.text()) + 8
        return type(self.minimumSize())(width, 24)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cy = self.height() // 2
        outer_d, inner_d = 16, 8
        outer_rect = (2, cy - outer_d // 2, outer_d, outer_d)

        if self.isChecked():
            painter.setPen(QPen(QColor(t.ACCENT), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(*outer_rect)
            painter.setBrush(QColor(t.ACCENT))
            painter.setPen(Qt.PenStyle.NoPen)
            inner_x = outer_rect[0] + (outer_d - inner_d) // 2
            inner_y = cy - inner_d // 2
            painter.drawEllipse(inner_x, inner_y, inner_d, inner_d)
        else:
            painter.setPen(QPen(QColor(t.BORDER), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(*outer_rect)

        painter.setPen(QColor(t.TEXT_MAIN))
        font = painter.font()
        font.setFamily(t.FONT_UI)
        font.setPixelSize(t.SIZE_BODY)
        painter.setFont(font)
        painter.drawText(
            outer_d + 8, 0, self.width() - outer_d - 8, self.height(),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text(),
        )
        painter.end()


# ---------------------------------------------------------------------------
# Durum rozeti -- her zaman renkli nokta + kisa metin
# ---------------------------------------------------------------------------
class StatusBadge(QWidget):
    """
    '● Bağlı' / '● Bağlı değil' / '● Hata' / '● Bağlanıyor...' gibi durum
    gostergeleri icin gercek bir pill/rozet: renkli (soluk) arka plan +
    renkli nokta + renkli metin -- duz nokta+metinden ayirt edilebilir
    olmasi icin. set_status(color_hex, text) ile guncellenir.
    """

    PRESET_CONNECTED = (t.SUCCESS, "Bağlı")
    PRESET_DISCONNECTED = (t.TEXT_SECONDARY, "Bağlı değil")
    PRESET_ERROR = (t.ERROR, "Hata")
    PRESET_CONNECTING = (t.WARNING, "Bağlanıyor...")

    def __init__(self, parent=None):
        super().__init__(parent)
        # QWidget stylesheet'teki background/border-radius'u boyamasi icin
        # (QFrame'in aksine varsayilan olarak boyamiyor).
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(22)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(6)

        self._dot = QLabel("●")
        self._label = QLabel()
        layout.addWidget(self._dot)
        layout.addWidget(self._label)
        self.set_status(*self.PRESET_DISCONNECTED)

    def set_status(self, color, text):
        self.setStyleSheet(f"""
            StatusBadge {{
                background-color: {_tint(color)};
                border-radius: 11px;
            }}
        """)
        self._dot.setStyleSheet(f"color: {color}; font-family: '{t.FONT_UI}'; font-size: {t.SIZE_HELPER}px; background: transparent;")
        self._label.setStyleSheet(
            f"color: {color}; font-family: '{t.FONT_UI}'; font-size: {t.SIZE_HELPER}px; "
            f"font-weight: 600; background: transparent;"
        )
        self._label.setText(text)


# ---------------------------------------------------------------------------
# Adim rozeti -- numarali listelerde varsayilan liste numarasi yerine
# ---------------------------------------------------------------------------
class StepBadge(QLabel):
    """Mavi daire icinde beyaz rakam -- 'Gerekenler'/'Adım adım kullanım'
    gibi numarali listelerde wizard/rehber hissini guclendirmek icin."""

    def __init__(self, number, parent=None):
        super().__init__(str(number), parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(20, 20)
        self.setStyleSheet(f"""
            background-color: {t.ACCENT};
            color: white;
            border-radius: 10px;
            font-family: "{t.FONT_UI}";
            font-size: 11px;
            font-weight: 600;
        """)


# ---------------------------------------------------------------------------
# Ilerleme cubugu -- belirli (%) + belirsiz (indeterminate) mod
# ---------------------------------------------------------------------------
class ProgressBar(QProgressBar):
    """
    Islem surerken SESSIZ BEKLEME olmasin diye: yuzde biliniyorsa
    set_determinate(pct), bilinmiyorsa set_indeterminate() ile Qt'nin
    kendi "busy" animasyonuna gecilir (min=0, max=0).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextVisible(False)
        self.setMinimumHeight(6)
        self.setMaximumHeight(6)
        self.setStyleSheet(f"""
            QProgressBar {{
                background-color: {t.BG_LAYER2};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: {t.ACCENT};
                border-radius: 3px;
            }}
        """)
        self.set_determinate(0)

    def set_determinate(self, percent):
        if self.minimum() != 0 or self.maximum() != 100:
            self.setRange(0, 100)
        self.setValue(max(0, min(100, int(percent))))

    def set_indeterminate(self):
        self.setRange(0, 0)


# ---------------------------------------------------------------------------
# Kart -- basligi olan, kenarlikli/koseli panel (golgesiz)
# ---------------------------------------------------------------------------
class Card(QFrame):
    """
    Baslikli panel -- gui_v2.py/ram_gui.py'deki '_card()' yardimcisinin
    PySide6 karsiligi. Icerik, .body layout'una eklenir.
    """

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            Card {{
                background-color: {t.BG_SURFACE};
                border: 1px solid {t.BORDER};
                border-radius: {t.RADIUS}px;
            }}
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(t.CARD_PADDING, t.CARD_PADDING, t.CARD_PADDING, t.CARD_PADDING)
        outer.setSpacing(t.FORM_GAP)

        if title:
            label = QLabel(title.upper())
            label.setStyleSheet(f"""
                color: {t.ACCENT};
                font-family: "{t.FONT_UI}";
                font-size: {t.SIZE_SECTION_LABEL}px;
                font-weight: 600;
                letter-spacing: 1px;
                background: transparent;
            """)
            outer.addWidget(label)

        self.body = QVBoxLayout()
        self.body.setSpacing(t.FORM_GAP)
        outer.addLayout(self.body)
