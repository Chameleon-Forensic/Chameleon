"""
fonts.py
Inter + JetBrains Mono'yu (shared/assets/fonts/, SIL OFL lisansli, ikisi
de degisken/variable font) uygulama acilisinda kaydeder. Boylece
kullanicinin sisteminde bu fontlar kurulu olmasa bile dogru gorunur --
Windows'ta varsayilan olarak hicbiri kurulu degil.
"""

import os

from PySide6.QtGui import QFontDatabase

_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts")

_registered = False


def register_fonts():
    """
    Inter.ttf ve JetBrainsMono.ttf'yi QFontDatabase'e ekler. Birden fazla
    cagirilirsa (launcher + gui_v2 + ram_gui ayni surecte birden fazla
    ekran acabiliyor) sadece ILK cagrida gercekten yukler -- Qt zaten
    ayni fontu iki kez eklemeyi sorun etmez ama gereksiz IO'yu onluyoruz.
    """
    global _registered
    if _registered:
        return
    for filename in ("Inter.ttf", "JetBrainsMono.ttf"):
        path = os.path.join(_ASSETS_DIR, filename)
        if os.path.isfile(path):
            QFontDatabase.addApplicationFont(path)
    _registered = True
