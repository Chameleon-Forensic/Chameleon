"""
gui_v2.ForensicWidget ve ram_gui.RamEngineWidget'in (SSH/RAM arac ekranlari)
6 dilin (tr/en/es/de/pt/fr) TAMAMINDA, headless olarak hicbir exception
firlatmadan kurulabildigini ve gorunen etiketlerin secili dile gore
degistigini dogrular -- bkz. docs/roadmap.md "gui_v2.py/ram_gui.py'yi 6
dile tasima". test_gui_smoke.py sadece launcher sayfalarini geziyordu, bu
iki sinifi hic ORNEKLEMIYORDU (bilincli olarak genisletildi).
"""

import pytest

from PySide6.QtWidgets import QLabel, QPushButton

import gui_v2
import ram_gui


LANGUAGES = ["tr", "en", "es", "de", "pt", "fr"]

# Her dilde en azindan bir kere gorunmesi beklenen, SSH ekranina ozgu bir
# metin -- yanlislikla "tr"ye sabit kalmis bir cagriyi yakalamak icin.
SSH_TITLE_SPOT_CHECK = {
    "tr": "SSH ile Uzak İmaj Al",
    "en": "Remote Image over SSH",
    "es": "Imagen Remota por SSH",
    "de": "Remote-Image über SSH",
    "pt": "Imagem Remota via SSH",
    "fr": "Image Distante via SSH",
}
RAM_TITLE_SPOT_CHECK = {
    "tr": "RAM İmajı Al",
    "en": "Acquire RAM Image",
    "es": "Obtener Imagen de RAM",
    "de": "RAM-Image Erfassen",
    "pt": "Obter Imagem de RAM",
    "fr": "Acquérir une Image RAM",
}


def _all_texts(widget):
    texts = [w.text() for w in widget.findChildren(QLabel)]
    texts += [w.text() for w in widget.findChildren(QPushButton)]
    return texts


@pytest.mark.parametrize("lang", LANGUAGES)
def test_forensic_widget_builds_in_every_language(qapp, lang):
    widget = gui_v2.ForensicWidget(lang=lang)
    qapp.processEvents()
    try:
        assert SSH_TITLE_SPOT_CHECK[lang] in _all_texts(widget)
    finally:
        widget.deleteLater()
        qapp.processEvents()


@pytest.mark.parametrize("lang", LANGUAGES)
def test_ram_engine_widget_builds_in_every_language(qapp, lang):
    widget = ram_gui.RamEngineWidget(lang=lang)
    qapp.processEvents()
    try:
        assert RAM_TITLE_SPOT_CHECK[lang] in _all_texts(widget)
    finally:
        widget.deleteLater()
        qapp.processEvents()


def test_forensic_widget_hides_case_info_card_when_launched_from_launcher(qapp):
    """on_back verilirse (launcher'dan acilis) Vaka Bilgileri karti
    GORUNMEZ -- bkz. chameleon_gui._show_case_info ile duplikasyon
    onlemi. Standalone'da (on_back yok) gorunur kalmali."""
    embedded = gui_v2.ForensicWidget(on_back=lambda: None, lang="en")
    qapp.processEvents()
    standalone = gui_v2.ForensicWidget(lang="en")
    qapp.processEvents()
    try:
        from PySide6.QtWidgets import QWidget
        # Card basligi "Case Information" olan widget'i bul, gorunurlugune bak.
        def _case_card(w):
            for c in w.findChildren(QWidget):
                if any(lbl.text() == "CASE INFORMATION" for lbl in c.findChildren(QLabel)):
                    return c
            return None
        embedded_card = _case_card(embedded)
        standalone_card = _case_card(standalone)
        assert embedded_card is not None and not embedded_card.isVisible()
        assert standalone_card is not None
    finally:
        embedded.deleteLater()
        standalone.deleteLater()
        qapp.processEvents()
