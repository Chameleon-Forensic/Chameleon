"""
"Yarim Kalanlar" sayfasi -- bkz. docs/roadmap.md madde 0.5 bilinen sinir:
mantiksal imaj (mode="logical") manifestleri daha once klasor modu ile AYNI
("SSH Dosya/Klasor") etiketiyle gorunuyordu, ayirt edilemiyordu.
"""

import json

import chameleon_gui
import image_acquirer


def _manifest_yaz(manifest_dir, ad, **alanlar):
    veri = {
        "remote_root": "/data", "host": "h", "acquired_files": ["a"],
        "total_files": 5, "started_at_utc": "2026-01-01T00:00:00Z", **alanlar,
    }
    with open(f"{manifest_dir}/{ad}", "w", encoding="utf-8") as f:
        json.dump(veri, f)


def test_incomplete_page_labels_logical_and_file_tree_manifests_separately(
    qapp, isolated_history, tmp_path, monkeypatch,
):
    monkeypatch.setattr(image_acquirer, "MANIFEST_DIR", str(tmp_path))
    _manifest_yaz(tmp_path, "manifest_tree_1.json", mode="file")
    _manifest_yaz(tmp_path, "manifest_tree_2.json", mode="logical")

    win = chameleon_gui.ChameleonWindow()
    win._enter_operator_mode()
    qapp.processEvents()
    try:
        win._show_incomplete_operations()
        qapp.processEvents()
        from strings import t
        from PySide6.QtWidgets import QLabel
        metinler = [w.text() for w in win.findChildren(QLabel)]
        assert t("type_ssh_file_folder", win.lang) in metinler
        assert t("type_ssh_logical", win.lang) in metinler
    finally:
        win.close()
        win.deleteLater()
        qapp.processEvents()
