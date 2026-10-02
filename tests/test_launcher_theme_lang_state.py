"""
chameleon_gui.py -- tema/dil degisiminin korunmus ekranlarla etkilesimi.

Bulgu (bkz. docs/code_review_bulgulari.md):
_build_shell() setCentralWidget() ile ESKI central widget'i (ve tum
cocuklarini) siler. _active_tool_widget (calisan ismiyle korunan arac
ekrani) ya da _return_page (Bilgi Merkezi "Geri donus" sayfasi) o agacta
duruyorsa, tema/dil degisimi onlari da siler ve referanslar silinmis Qt
nesnelerine dönerdi -- sonraki _resume_active_tool / _return_from_help
çağrısı PySide6 RuntimeError ("Internal C++ object already deleted")
ile cökerdi. Duzeltme: _build_shell yikimdan once _drop_preserved_pages
referanslari temizler.
"""

import pytest

import chameleon_gui


@pytest.fixture
def window(qapp, isolated_history):
    win = chameleon_gui.ChameleonWindow()
    win._enter_operator_mode()
    qapp.processEvents()
    yield win
    win.close()
    win.deleteLater()
    qapp.processEvents()


def test_theme_change_clears_preserved_tool_widget_refs(window, qapp, monkeypatch):
    """Çalışan korunan bir araç ekranı varken tema değiştirilince, eski
    kod silinmiş Qt nesnesini _active_tool_widget'te tutup sonraki
    _resume_active_tool çağrısında RuntimeError ile çökerdi. Artık
    referanslar _build_shell öncesinde temizlenmeli."""
    # Sahte, "çalışan" bir araç ekranı simüle et: normal akışta SSH ekranı
    # _open_ssh_engine ile açılıyor; burada widget oluşturmadan sadece
    # state'i kurmak yeterli (fix'in kendisi state temizliği).
    fake_page = chameleon_gui.QWidget()
    window.stack_layout.addWidget(fake_page)
    window._active_tool_widget = fake_page
    window._active_tool_kind = "ssh"
    window._active_tool_method = "direct"

    window._apply_theme("light")
    qapp.processEvents()

    assert window._active_tool_widget is None, \
        "Tema değişimi silinen sayfanın referansını bırakmamalı"
    assert window._active_tool_kind is None
    assert window._active_tool_method is None

    # Ve sonraki resume çağrısı çökmemeli (eskiden RuntimeError):
    assert window._resume_active_tool("ssh", method="direct") is False


def test_lang_change_clears_return_page_ref(window, qapp):
    """_return_page (Bilgi Merkezi Geri dönüş sayfası) dururken dil
    değiştirilince eski kod silinmiş nesneyi tutuyor, _return_from_help
    çağrısı çökerdi. Artık referans temizlenmeli."""
    fake_page = chameleon_gui.QWidget()
    window.stack_layout.addWidget(fake_page)
    window._return_page = fake_page
    window._return_nav = "ram"

    window._apply_lang("en")
    qapp.processEvents()

    assert window._return_page is None, \
        "Dil değişimi silinen geri dönüş sayfasının referansını bırakmamalı"
    assert window._return_nav is None

    # Ve sonraki _return_from_help çağrısı çökmemeli:
    window._return_from_help()  # sadece çökmemesi yeterli


def test_build_shell_without_preserved_pages_is_noop_for_refs(window, qapp):
    """Korunan sayfa yokken tema/dil değişimi ekstra bir şey yapmamalı --
    mevcut davranış bozulmamalı."""
    window._apply_lang("tr")
    qapp.processEvents()
    assert window._active_tool_widget is None
    assert window._return_page is None
    # Sayfa normal akışla açılabilmeli:
    window._show_home()
    qapp.processEvents()
