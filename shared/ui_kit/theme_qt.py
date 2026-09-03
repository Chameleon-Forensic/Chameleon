"""
theme_qt.py
Verilen tasarim sistemindeki renk paleti, tipografi ve bosluk sabitleri +
uygulama genelinde kullanilan taban QSS. Ozel bilesenler (widgets.py)
kendi ek QSS'lerini bu renklerden turetir -- renk degeri baska hicbir
yerde tekrar yazilmaz.

Acik ve koyu iki tema var (set_mode() ile aralarinda gecis yapilir,
shared/theme.py'nin -- eski Tk suruminun -- deseniyle ayni: modul seviyesi
degiskenler globals().update() ile guncelleniyor). Renk isimleri (orn.
BG_DARKEST) koyu temaya gore konuldu ama acik temada da AYNI isim
kullaniliyor (orn. BG_DARKEST acik modda en acik/ana arka plan olur) --
her yerde tek bir isim seti kullanmak, iki ayri isim seti tutmaktan daha
az hataya acik.

ONEMLI: Widget'lar bu degerleri KURULUM ANINDA (QSS string'ine gomerek)
okuyor -- canli/otomatik guncellenmiyor. Tema degisince gorunmesi icin
cagiran taraf (chameleon_gui.py) ilgili ekrani/kabugu YENIDEN KURMALI
(eski Tk suruminun _toggle_theme() -> _build_shell() deseniyle ayni).
"""

FONT_UI = "Inter"
FONT_MONO = "JetBrains Mono"

SIZE_TITLE = 20
SIZE_SECTION_LABEL = 13
SIZE_BODY = 14
SIZE_HELPER = 12

WEIGHT_REGULAR = 400
WEIGHT_SEMIBOLD = 600

SPACING_UNIT = 8
CARD_PADDING = 20
CARD_GAP = 16
FORM_GAP = 12

RADIUS = 5  # 4-6px, asla daha buyuk degil (AI-dashboard hissi yaratiyor)

DARK = {
    "BG_DARKEST": "#0D1117",   # Arka plan (en koyu / ana)
    "BG_SURFACE": "#161B22",   # Kart/panel yuzeyi
    "BG_LAYER2": "#1F2937",    # Ikinci katman (input, hover)
    "ACCENT": "#2563EB",
    "ACCENT_HOVER": "#3B82F6",
    "SUCCESS": "#22C55E",
    "WARNING": "#F59E0B",
    "ERROR": "#EF4444",
    "TEXT_MAIN": "#E5E7EB",
    "TEXT_SECONDARY": "#9CA3AF",
    "BORDER": "#30363D",
}

LIGHT = {
    "BG_DARKEST": "#F5F7FA",   # Ana arka plan (acik temada EN ACIK)
    "BG_SURFACE": "#FFFFFF",
    "BG_LAYER2": "#EEF1F5",
    "ACCENT": "#2563EB",
    "ACCENT_HOVER": "#1D4ED8",  # acik zeminde hover koyulastirir
    "SUCCESS": "#16A34A",
    "WARNING": "#D97706",
    "ERROR": "#DC2626",
    "TEXT_MAIN": "#111827",
    "TEXT_SECONDARY": "#6B7280",
    "BORDER": "#D1D5DB",
}

_current_mode = "dark"


def set_mode(mode):
    """mode: 'light' ya da 'dark'. Modul degiskenlerini (BG_DARKEST vb.) gunceller."""
    global _current_mode
    _current_mode = mode if mode in ("light", "dark") else "dark"
    globals().update(DARK if _current_mode == "dark" else LIGHT)


def get_mode():
    return _current_mode


set_mode("dark")


def base_stylesheet():
    """
    Uygulama genelinde (QApplication.setStyleSheet) uygulanan taban QSS.
    Ozel bilesenler (PrimaryButton, Input, RadioButton vb.) kendi
    obje-adi/class secicileriyle bunun UZERINE ek kurallar getiriyor,
    burasi sadece varsayilan/genel gorunumu belirliyor. Tema degisince
    (set_mode) TEKRAR cagirilip QApplication'a yeniden uygulanmali.
    """
    return f"""
    QWidget {{
        background-color: {BG_DARKEST};
        color: {TEXT_MAIN};
        font-family: "{FONT_UI}";
        font-size: {SIZE_BODY}px;
    }}

    /* QLabel'lar her zaman kendi konteynerinin (kart, sidebar, sayfa)
    arka planinin UZERINDE oturur -- aksi halde her ikon/metin etiketi
    genel QWidget arka planiyla (yukarida) KUTU gibi gorunur, ozellikle
    bir kartin (BG_SURFACE) icindeki bir QLabel genel arka plani
    (BG_DARKEST) miras alip fark edilir bir kutu birakiyordu. */
    QLabel {{
        background: transparent;
    }}

    QScrollArea {{
        border: none;
        background-color: transparent;
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {BORDER};
        border-radius: 4px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {TEXT_SECONDARY};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QToolTip {{
        background-color: {BG_LAYER2};
        color: {TEXT_MAIN};
        border: 1px solid {BORDER};
        border-radius: {RADIUS}px;
        padding: 4px 8px;
    }}
    """
