"""
widgets.py
Tasarim sistemine uygun, tekrar kullanilabilir PySide6 bilesenleri.
Ekranlar (launcher/chameleon_qt.py, gui_v2.py, ram_gui.py -- gecis
tamamlaninca) duz QPushButton/QLineEdit yerine bunlari kullanir; renk/
tipografi/bosluk degerleri SADECE theme_qt.py'de tanimli, burada tekrar
yazilmiyor.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
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
            /* Dolgu zaten ACCENT oldugu icin odak kenarligi da ayni mavi
            tondan olursa (orn. ACCENT_TEXT) neredeyse hic secilmiyor
            (olcum: 1.41:1) -- beyaz kenarlik burada ACCENT'e karsi 5.17:1. */
            QPushButton:focus {{ border: 2px solid white; padding: 5px 17px; }}
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
            QPushButton:focus {{ border: 2px solid {t.ACCENT_TEXT}; padding: 5px 17px; }}
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
        self._glow.setColor(QColor(t.ACCENT_TEXT))
        self._glow.setBlurRadius(0)
        self._glow.setOffset(0, 0)
        self.setGraphicsEffect(self._glow)

    def _font_family(self):
        return t.FONT_UI

    def _apply_style(self, focused):
        # Odaklaninca kenarlik hem daha acik bir maviye (ACCENT_TEXT --
        # duz ACCENT'in BG_LAYER2'ye karsi kontrasti 2.84:1'di, WCAG'in
        # istedigi 3:1'in altinda kaliyordu) HEM de 1px'ten 2px'e cikiyor --
        # odagin nerede oldugu artik dusuk gorusle de fark edilebiliyor.
        border_color = t.ACCENT_TEXT if focused else t.BORDER
        border_width = 2 if focused else 1
        h_pad = 10 if focused else 11
        v_pad = 3 if focused else 4
        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: {t.BG_LAYER2};
                color: {t.TEXT_MAIN};
                border: {border_width}px solid {border_color};
                border-radius: {t.RADIUS}px;
                padding: {v_pad}px {h_pad}px;
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
        # Onceden sadece fareyle secilebiliyordu -- islem sonunda gosterilen
        # SHA-256 hash gibi degerleri klavye-only bir kullanici kopyalayamiyordu
        # (erisilebilirlik denetiminde bulundu). Klavye odagi alabilmesi icin
        # de FocusPolicy gerekiyor, TextInteractionFlags tek basina yetmiyor.
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


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
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def sizeHint(self):
        fm = self.fontMetrics()
        width = 22 + fm.horizontalAdvance(self.text()) + 8
        return type(self.minimumSize())(width, 24)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.update()

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

        # Klavye odagi -- oncesinde HIC cizilmiyordu: Tab ile gezinirken
        # hangi secenekte oldugunuz sadece secili (isChecked) olani
        # degistirdikten SONRA belli oluyordu, odagin KENDISI hicbir
        # zaman gorunmuyordu (erisilebilirlik denetiminde bulundu, WCAG
        # 2.4.7 "Focus Visible"). Butun kontrolun etrafina ince, yuvarlak
        # koseli bir cerceve cizerek duzeltildi.
        if self.hasFocus():
            painter.setPen(QPen(QColor(t.ACCENT_TEXT), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            focus_rect = self.rect().adjusted(1, 1, -1, -1)
            painter.drawRoundedRect(focus_rect, 4, 4)
        painter.end()


class Checkbox(QAbstractButton):
    """
    RadioButton ile AYNI cizim/odak deseni (yuvarlak yerine kose radiuslu
    kare + isaretliyken beyaz check isareti). Tasarim sisteminde onceden
    checkbox ihtiyaci olmadigi icin yoktu -- ilk kullanim yerinde (gzip
    sikistirma secenegi) varsayilan QCheckBox yerine bu eklendi, aksi
    halde tek bir kontrol geri kalan her seyle (renk, odak halkasi,
    kose radiusu) tutarsiz kalirdi.
    """

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(24)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def sizeHint(self):
        fm = self.fontMetrics()
        width = 22 + fm.horizontalAdvance(self.text()) + 8
        return type(self.minimumSize())(width, 24)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cy = self.height() // 2
        box_d = 16
        box_rect = (2, cy - box_d // 2, box_d, box_d)

        if self.isChecked():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t.ACCENT))
            painter.drawRoundedRect(*box_rect, 4, 4)
            check = QPainterPath()
            x, y = box_rect[0], box_rect[1]
            check.moveTo(x + 3.5, y + 8.2)
            check.lineTo(x + 6.7, y + 11.5)
            check.lineTo(x + 12.5, y + 4.5)
            check_pen = QPen(QColor("#FFFFFF"), 1.8)
            check_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            check_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(check_pen)
            painter.drawPath(check)
        else:
            painter.setPen(QPen(QColor(t.BORDER), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(*box_rect, 4, 4)

        painter.setPen(QColor(t.TEXT_MAIN))
        font = painter.font()
        font.setFamily(t.FONT_UI)
        font.setPixelSize(t.SIZE_BODY)
        painter.setFont(font)
        painter.drawText(
            box_d + 8, 0, self.width() - box_d - 8, self.height(),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text(),
        )

        if self.hasFocus():
            painter.setPen(QPen(QColor(t.ACCENT_TEXT), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            focus_rect = self.rect().adjusted(1, 1, -1, -1)
            painter.drawRoundedRect(focus_rect, 4, 4)
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
                color: {t.ACCENT_TEXT};
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
