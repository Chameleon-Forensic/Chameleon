"""
icons.py
shared/assets/icons/*.svg (Lucide, MIT lisans) icin tek bir icon(name)
fonksiyonu. SVG'ler stroke="currentColor" kullaniyor -- tarayicidaki
gibi CSS baglamindan otomatik renk almiyor, bu yuzden Qt'ye vermeden
once currentColor'u istenen hex renkle metin duzeyinde degistiriyoruz.
"""

import os

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from . import theme_qt

_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icons")
_cache = {}


def icon(name, color=None, size=20):
    """
    name: shared/assets/icons/<name>.svg (uzantisiz, orn. 'home').
    color: hex renk; verilmezse o ANKI TEXT_MAIN kullanilir (fonksiyon
    govdesinde okunuyor, tema degisince guncel degeri yansitir -- varsayilan
    parametre olarak theme_qt.TEXT_MAIN yazilsaydi bu deger sadece MODUL
    YUKLENIRKEN BIR KEZ donardi, set_mode() ile tema degisse bile hep
    ILK (koyu) degeri kullanirdi).
    Sonuc QIcon olarak onbelleklenir -- ayni (isim, renk, boyut) icin
    tekrar SVG parse etmez.
    """
    color = color or theme_qt.TEXT_MAIN
    key = (name, color, size)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    path = os.path.join(_ASSETS_DIR, f"{name}.svg")
    if not os.path.isfile(path):
        return QIcon()

    with open(path, "r", encoding="utf-8") as f:
        svg_text = f.read().replace("currentColor", color)

    renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    result = QIcon(pixmap)
    _cache[key] = result
    return result
