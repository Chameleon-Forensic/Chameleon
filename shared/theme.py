"""
Chameleon genelinde kullanilan ortak renk paleti. Launcher ve motorlerin
kendi arayuzleri (ornegin ssh_engine/local_collector/gui_v2.py) ayni
degerleri buradan okur, her dosyada ayri ayri tanimlamaz.

Acik ve koyu iki tema var, set_mode() ile aralarinda gecis yapilir --
degistirince bu modulun ust seviye degiskenleri (BG_MAIN, ACCENT, vb.)
guncellenir, onlari kullanan kod bir sonraki ciziminde yeni renkleri
gorur.
"""

LIGHT = {
    "BG_MAIN": "#F5F5F3",
    "BG_PANEL": "#FFFFFF",
    "TEXT_MAIN": "#2B2B2B",
    "TEXT_SECONDARY": "#6B6B6B",
    "ACCENT": "#3B5D6B",
    "ACCENT_HOVER": "#2C4650",
    "ERROR": "#A64545",
    "BORDER": "#DADAD8",
    "OK": "#3F7D57",
    "WARN": "#B98A2E",
}

DARK = {
    "BG_MAIN": "#1E1F22",
    "BG_PANEL": "#2B2D30",
    "TEXT_MAIN": "#E8E8E8",
    "TEXT_SECONDARY": "#A0A0A0",
    "ACCENT": "#5B8CA3",
    "ACCENT_HOVER": "#4A7488",
    "ERROR": "#D97066",
    "BORDER": "#3F4145",
    "OK": "#5FAE7C",
    "WARN": "#D9A94B",
}

_current_mode = "dark"


def set_mode(mode):
    """mode: 'light' ya da 'dark'. Modul degiskenlerini (BG_MAIN vb.) gunceller."""
    global _current_mode
    _current_mode = mode if mode in ("light", "dark") else "light"
    globals().update(DARK if _current_mode == "dark" else LIGHT)


def get_mode():
    return _current_mode


set_mode("dark")
