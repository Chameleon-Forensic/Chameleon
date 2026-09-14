"""
Launcher'in (chameleon_gui.py) TUM sayfalarini, 6 dilin (tr/en/es/de/pt/fr)
TAMAMINDA, headless (QT_QPA_PLATFORM=offscreen) olarak gezip hicbir
exception/KeyError firlatmadigini dogrular.

Bu, oturum boyunca defalarca elle yazilip atilan "tum sayfalari tum
dillerde gez" test scriptinin KALICI hali -- artik her degisiklikten
sonra `pytest tests/test_gui_smoke.py` ile TEK KOMUTLA tekrar calistirilabilir.
"""

import pytest

import chameleon_gui


LANGUAGES = ["tr", "en", "es", "de", "pt", "fr"]


@pytest.fixture
def window(qapp, isolated_history):
    win = chameleon_gui.ChameleonWindow()
    win._enter_operator_mode()
    qapp.processEvents()
    yield win
    win.close()
    win.deleteLater()
    qapp.processEvents()


@pytest.mark.parametrize("lang", LANGUAGES)
def test_all_screens_render_without_crashing(window, qapp, lang):
    window._apply_lang(lang)
    qapp.processEvents()

    window._show_home()
    qapp.processEvents()

    for handler in (
        window._show_direct_detail, window._show_vpn_detail,
        window._show_tor_detail, window._show_ram_detail,
    ):
        handler()
        qapp.processEvents()
        window._show_home()
        qapp.processEvents()

    window._show_case_info(lambda case: None)
    qapp.processEvents()

    window._show_help()
    qapp.processEvents()
    for topic in chameleon_gui.HELP_TOPICS:
        window._show_help(topic["key"])
        qapp.processEvents()

    window._show_case_history()
    qapp.processEvents()

    window._show_incomplete_operations()
    qapp.processEvents()

    window._show_settings()
    qapp.processEvents()


@pytest.mark.parametrize("lang", LANGUAGES)
def test_method_info_has_all_fields_for_language(lang):
    """METHOD_INFO[method][lang] eksikse _show_method_detail KeyError
    ile cokerdi -- bu test onu GUI acmadan, daha hizli yakalar."""
    required_fields = {"title", "icon", "short", "what", "when", "requires", "steps", "warning"}
    for method in ("direct", "vpn", "tor", "ram"):
        info = chameleon_gui.METHOD_INFO[method][lang]
        assert required_fields <= set(info.keys()), f"{method}/{lang}: eksik alan"


def test_settings_language_picker_lists_all_six_languages(window, qapp):
    window._show_settings()
    qapp.processEvents()
    from chameleon_gui import widgets
    radios = {r.text() for r in window.findChildren(widgets.RadioButton)}
    for code, name in chameleon_gui.LANGUAGES:
        assert any(name in r for r in radios), f"{name} dil secicide yok"


def test_home_has_no_recent_case_card_when_history_empty(window, qapp):
    window._show_home()
    qapp.processEvents()
    assert window._recent_case_card() is None


def test_home_shows_recent_case_card_with_newest_entry(window, qapp, isolated_history):
    import json
    entries = [
        {"case_id": "VAKA-001", "examiner": "", "custodian": "", "organization": "",
         "engine": "ssh_engine", "method": "disk", "status": "success",
         "start_time_utc": "2026-01-01T10:00:00Z", "report_path": "r1.json", "html_path": "r1.html"},
        {"case_id": "VAKA-002", "examiner": "", "custodian": "", "organization": "",
         "engine": "ram_engine", "method": "process", "status": "failed",
         "start_time_utc": "2026-01-02T10:00:00Z", "report_path": "r2.json", "html_path": "r2.html"},
    ]
    with open(isolated_history.HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f)

    window._show_home()
    qapp.processEvents()
    card = window._recent_case_card()
    assert card is not None
    from PySide6.QtWidgets import QLabel
    labels = " | ".join(lbl.text() for lbl in card.findChildren(QLabel))
    assert "VAKA-002" in labels, "en yeni kayit (read_history() en yeniden en eskiye doner) gosterilmeli"
    assert "VAKA-001" not in labels


def test_apply_lang_updates_sidebar_labels(window, qapp):
    window._apply_lang("es")
    qapp.processEvents()
    window._show_home()
    qapp.processEvents()
    labels = {btn.text().strip() for btn in window.findChildren(chameleon_gui.SidebarButton)}
    assert "Inicio" in labels
    assert "Configuración" in labels
