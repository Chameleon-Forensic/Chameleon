"""
conftest.py
Tum test dosyalarinin paylastigi ortak altyapi:
  - src/ altindaki her modulun kendi sys.path.insert() desenini (bkz.
    CONTRIBUTING.md) test sürecinde de calisir kilmak icin gerekli
    dizinleri sys.path'e ekler.
  - Qt tabanli testler icin headless (offscreen) bir QApplication fixture'i.
  - Gercek shared/data/ altindaki kalici dosyalara (case_history.json vb.)
    HICBIR testin dokunmamasi icin, ilgili modullerin dizin sabitlerini
    (HISTORY_DIR, LOG_DIR, IMAGE_DIR...) gecici bir klasore yonlendiren
    yardimci fixture'lar.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")

_PATHS = [
    os.path.join(SRC, "launcher"),
    os.path.join(SRC, "shared"),
    os.path.join(SRC, "shared", "i18n"),
    os.path.join(SRC, "engines", "ssh_engine", "local_collector"),
    os.path.join(SRC, "engines", "ram_engine"),
]
for p in _PATHS:
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest


@pytest.fixture(scope="session")
def qapp():
    """Tum Qt testlerinin paylastigi tek QApplication (offscreen)."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from ui_kit import theme_qt as ui, fonts
    fonts.register_fonts()
    app.setStyleSheet(ui.base_stylesheet())
    return app


@pytest.fixture
def isolated_history(tmp_path, monkeypatch):
    """forensic_report.py'nin HISTORY_DIR/HISTORY_FILE/TAGS_FILE'ini
    gecici bir klasore yonlendirir -- gercek shared/data/case_history.json
    hic etkilenmez."""
    import forensic_report
    hist_dir = tmp_path / "data"
    hist_dir.mkdir()
    monkeypatch.setattr(forensic_report, "HISTORY_DIR", str(hist_dir))
    monkeypatch.setattr(forensic_report, "HISTORY_FILE", str(hist_dir / "case_history.json"))
    monkeypatch.setattr(forensic_report, "TAGS_FILE", str(hist_dir / "case_tags.json"))
    return forensic_report


@pytest.fixture
def isolated_coc_log(tmp_path, monkeypatch):
    """chain_of_custody.py'nin LOG_DIR'ini gecici bir klasore yonlendirir
    -- gercek log dosyalarina hic yazilmaz. Modul-seviyesi _current_log_file
    onbellegini de sifirlar (her testte YENI bir log dosyasi acilsin diye)."""
    import chain_of_custody as coc
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setattr(coc, "LOG_DIR", str(log_dir))
    monkeypatch.setattr(coc, "_current_log_file", None, raising=False)
    return coc
