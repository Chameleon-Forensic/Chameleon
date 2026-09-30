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
import struct
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


_SECTOR = 512


def _fat12_dir_entry(name, ext, attr, first_cluster, size=0):
    entry = bytearray(32)
    entry[0:8] = name.ljust(8)[:8].encode("ascii")
    entry[8:11] = ext.ljust(3)[:3].encode("ascii")
    entry[11] = attr
    struct.pack_into("<H", entry, 26, first_cluster)
    struct.pack_into("<I", entry, 28, size)
    return bytes(entry)


def _fat12_set_entry(fat, idx, value):
    off = idx * 3 // 2
    if idx % 2 == 0:
        fat[off] = value & 0xFF
        fat[off + 1] = (fat[off + 1] & 0xF0) | ((value >> 8) & 0x0F)
    else:
        fat[off] = (fat[off] & 0x0F) | ((value & 0x0F) << 4)
        fat[off + 1] = (value >> 4) & 0xFF


def build_minimal_fat12_image():
    """disk_tree.py (pytsk3 ile Tam Disk agac gorunumu) testleri icin,
    gercek bir disk/USB gerektirmeden calisan, TSK'nin DOGRUDAN taniyacagi
    kucuk ve gecerli bir FAT12 (1.44MB disket duzeni) imaji bayt bayt
    kurar. Icerik: kokte HELLO.TXT + SUBDIR/A.TXT -- klasor icinde ic ice
    dosya olan bir agaci test etmeye yeter."""
    total_sectors = 2880
    reserved = 1
    num_fats = 2
    sectors_per_fat = 9
    root_entries = 224
    root_dir_sectors = (root_entries * 32) // _SECTOR

    boot = bytearray(_SECTOR)
    boot[0:3] = b"\xEB\x3C\x90"
    boot[3:11] = b"MSDOS5.0"
    struct.pack_into("<H", boot, 11, _SECTOR)
    boot[13] = 1
    struct.pack_into("<H", boot, 14, reserved)
    boot[16] = num_fats
    struct.pack_into("<H", boot, 17, root_entries)
    struct.pack_into("<H", boot, 19, total_sectors)
    boot[21] = 0xF0
    struct.pack_into("<H", boot, 22, sectors_per_fat)
    struct.pack_into("<H", boot, 24, 18)
    struct.pack_into("<H", boot, 26, 2)
    boot[38] = 0x29
    struct.pack_into("<I", boot, 39, 0x12345678)
    boot[43:54] = b"NO NAME    "
    boot[54:62] = b"FAT12   "
    boot[510] = 0x55
    boot[511] = 0xAA

    fat = bytearray(sectors_per_fat * _SECTOR)
    _fat12_set_entry(fat, 0, 0xFF0)
    _fat12_set_entry(fat, 1, 0xFFF)
    _fat12_set_entry(fat, 2, 0xFFF)  # HELLO.TXT (1 kume)
    _fat12_set_entry(fat, 3, 0xFFF)  # SUBDIR (1 kume)
    _fat12_set_entry(fat, 4, 0xFFF)  # SUBDIR/A.TXT (1 kume)

    root_dir = bytearray(root_dir_sectors * _SECTOR)
    root_dir[0:32] = _fat12_dir_entry("HELLO", "TXT", 0x20, 2, size=5)
    root_dir[32:64] = _fat12_dir_entry("SUBDIR", "", 0x10, 3, size=0)

    cluster2 = bytearray(_SECTOR)
    cluster2[0:5] = b"hello"

    cluster3 = bytearray(_SECTOR)
    cluster3[0:32] = _fat12_dir_entry(".", "", 0x10, 3)
    cluster3[32:64] = _fat12_dir_entry("..", "", 0x10, 0)
    cluster3[64:96] = _fat12_dir_entry("A", "TXT", 0x20, 4, size=3)

    cluster4 = bytearray(_SECTOR)
    cluster4[0:3] = b"abc"

    image = bytearray(total_sectors * _SECTOR)
    image[0:_SECTOR] = boot
    off = reserved * _SECTOR
    image[off:off + len(fat)] = fat
    off += len(fat)
    image[off:off + len(fat)] = fat
    off += len(fat)
    image[off:off + len(root_dir)] = root_dir
    off += len(root_dir)
    image[off:off + _SECTOR] = cluster2
    off += _SECTOR
    image[off:off + _SECTOR] = cluster3
    off += _SECTOR
    image[off:off + _SECTOR] = cluster4

    return bytes(image)


@pytest.fixture
def fat12_image_path(tmp_path):
    """build_minimal_fat12_image()'i gecici bir dosyaya yazip yolunu doner."""
    yol = tmp_path / "fat12.img"
    yol.write_bytes(build_minimal_fat12_image())
    return str(yol)


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
