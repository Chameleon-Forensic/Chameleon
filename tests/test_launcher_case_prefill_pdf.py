"""
chameleon_gui.py -- iki kucuk correctness fix'in regresyon testleri:

1. RAM yarim-kalan karti "Yeniden Baslat" prefill'i case_notes'u tasiyor
   (diger 4 vaka alani zaten tasiyordu).
2. _export_report_pdf ciplak `import forensic_report` yapiyordu -- modul
   yuklenemezse (bozuk kurulum) tiklama sesizce crashti; artik
   _show_case_history ile AYNI ImportError dongusune alindi.
"""

import types

import builtins
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


def test_ram_engine_prefill_carries_case_notes(window, qapp, monkeypatch):
    """RAM ekranini acan _open_ram_engine, prefill dict'indeki case_notes'u
    widget'a initial_case_notes olarak gecirmeli -- _show_incomplete_operations
    RAM karti artik bu dict'e case_notes'u da koyuyor."""
    yakalanan = {}

    class _SahteRamWidget(chameleon_gui.QWidget):
        def __init__(self, **kw):
            super().__init__()
            yakalanan.update(kw)

    sahte_modul = types.ModuleType("ram_gui")
    sahte_modul.RamEngineWidget = _SahteRamWidget
    monkeypatch.setitem(chameleon_gui.sys.modules, "ram_gui", sahte_modul)

    window._open_ram_engine({
        "case_id": "V-9", "examiner": "adli", "custodian": "sahip",
        "organization": "org", "case_notes": "not: disk kamerada",
    })
    qapp.processEvents()

    assert yakalanan.get("initial_case_notes") == "not: disk kamerada", \
        "case_notes prefill akisi bozulmamali"
    assert yakalanan.get("initial_case_id") == "V-9"


def test_export_report_pdf_survives_forensic_report_import_error(window, qapp, monkeypatch):
    """forensic_report modulu yuklenemezse PDF export uygulamayi cokertmemeli
    -- durum satirina hata yazilmali (eskiden ciplak import ile crashti)."""
    real_import = builtins.__import__

    def _engelleyen_import(name, *a, **kw):
        if name == "forensic_report":
            raise ImportError("forensic_report yuklenemedi (test)")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", _engelleyen_import)
    monkeypatch.setattr(
        chameleon_gui.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **kw: ("cikti.pdf", "")),
    )
    window._history_status = chameleon_gui.QLabel("")

    # COKMEMELI:
    window._export_report_pdf("var_olmayan/report.json")
    qapp.processEvents()

    assert window._history_status.text() != "", \
        "Import hatasi kullaniciya durum satirinda bildirilmeli"
