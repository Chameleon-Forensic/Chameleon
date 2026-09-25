"""
Alinan dosya/klasor agaci goruntuleme testleri (hoca istegi, bkz.
docs/roadmap.md) -- sadece Dosya/Klasor ve Mantiksal Imaj icin anlamli,
Tam Disk (ham blok imaji) icin buton hic gorunmuyor.
"""

import json

import pytest

import gui_v2


def test_build_path_tree_nests_correctly():
    agac = gui_v2.build_path_tree(["/a/b/c.txt", "/a/d.txt", "/e.txt"])
    assert agac == {
        "a": {"b": {"c.txt": "/a/b/c.txt"}, "d.txt": "/a/d.txt"},
        "e.txt": "/e.txt",
    }


def test_build_path_tree_handles_windows_separators():
    agac = gui_v2.build_path_tree(["C:\\Users\\a\\file.txt"])
    assert agac == {"C:": {"Users": {"a": {"file.txt": "C:\\Users\\a\\file.txt"}}}}


def test_build_path_tree_empty_list():
    assert gui_v2.build_path_tree([]) == {}


@pytest.fixture(autouse=True)
def _no_modal(monkeypatch):
    """Dialog.exec() gercekten acilip bekletmesin -- widget agaci kurulduktan
    hemen sonra donsun (headless testte modal blokaj olmasin diye)."""
    monkeypatch.setattr(gui_v2.QDialog, "exec", lambda self: None)


def test_show_tree_dialog_populates_tree_widget(qapp, tmp_path, monkeypatch):
    manifest = {
        "remote_root": "/data",
        "acquired": [
            {"remote_path": "/data/sub/a.txt", "local_path": str(tmp_path / "a.txt")},
            {"remote_path": "/data/b.txt", "local_path": str(tmp_path / "b.txt")},
        ],
    }
    manifest_yolu = tmp_path / "manifest_files.json"
    manifest_yolu.write_text(json.dumps(manifest), encoding="utf-8")

    yakalanan = {}
    orijinal = gui_v2.QTreeWidget

    class YakalayanTree(orijinal):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            yakalanan["tree"] = self

    monkeypatch.setattr(gui_v2, "QTreeWidget", YakalayanTree)

    widget = gui_v2.ForensicWidget(lang="tr")
    qapp.processEvents()
    try:
        widget._show_tree_dialog(str(manifest_yolu))
        tree = yakalanan["tree"]
        kok = tree.topLevelItem(0)
        assert kok.text(0) == "/data"
        # klasor ("sub") once, dosya ("b.txt") sonra -- alma modlarindaki
        # ayni "klasorler once" sunum kurali.
        assert kok.child(0).text(0) == "sub"
        assert kok.child(1).text(0) == "b.txt"
        assert kok.child(0).child(0).text(0) == "a.txt"
        assert kok.child(0).child(0).data(0, gui_v2.Qt.ItemDataRole.UserRole) == str(tmp_path / "a.txt")
        # dosyanin kendisi yerel diskte gercekten yok (bu test onu olusturmadi)
        # ama yine de yol dogru eslenmis olmali.
    finally:
        widget.deleteLater()
        qapp.processEvents()


def test_show_tree_dialog_bad_manifest_shows_error_not_crash(qapp, tmp_path, monkeypatch):
    bozuk_yol = tmp_path / "manifest_files.json"
    bozuk_yol.write_text("{ gecersiz json", encoding="utf-8")

    yakalanan = []
    widget = gui_v2.ForensicWidget(lang="tr")
    qapp.processEvents()
    monkeypatch.setattr(widget, "_show_error", yakalanan.append)
    try:
        widget._show_tree_dialog(str(bozuk_yol))  # cokmemeli
        assert len(yakalanan) == 1
    finally:
        widget.deleteLater()
        qapp.processEvents()


def test_report_summary_shows_tree_button_only_for_file_and_logical(qapp, tmp_path):
    from forensic_report import ForensicReport
    from strings import t
    from ui_kit import widgets

    (tmp_path / "manifest_files.json").write_text("{}", encoding="utf-8")

    for method, beklenen in [("file", True), ("logical", True), ("disk", False)]:
        # Her yontem icin AYRI widget -- ayni widget'ta ust uste acilan
        # dialoglar (exec() no-op oldugu icin hicbiri kapanmiyor) findChildren'da
        # birikip bir onceki yontemin dugmesini de gorunur gosterirdi.
        widget = gui_v2.ForensicWidget(lang="tr")
        qapp.processEvents()
        try:
            report = ForensicReport(case_id="", examiner="", custodian="", organization="")
            report.start(engine="ssh_engine", method=method, target_os="linux")
            report.finish(status="success", output_path=str(tmp_path))
            widget._show_report_summary(report, str(tmp_path / "report.json"))
            butonlar = [b.text() for b in widget.findChildren(widgets.SecondaryButton)]
            gorunur = t("btn_view_tree", "tr") in butonlar
            assert gorunur == beklenen, f"method={method}"
        finally:
            widget.deleteLater()
            qapp.processEvents()


def test_report_summary_no_tree_button_when_manifest_missing(qapp, tmp_path):
    """manifest_files.json diskte yoksa (ör. rapor tasindi/silindi), buton
    yine gizli kalmali -- var olmayan bir dosyaya baglanmamali."""
    from forensic_report import ForensicReport
    from strings import t
    from ui_kit import widgets

    bos_klasor = tmp_path / "bos"
    bos_klasor.mkdir()

    widget = gui_v2.ForensicWidget(lang="tr")
    qapp.processEvents()
    try:
        report = ForensicReport(case_id="", examiner="", custodian="", organization="")
        report.start(engine="ssh_engine", method="file", target_os="linux")
        report.finish(status="success", output_path=str(bos_klasor))
        widget._show_report_summary(report, str(bos_klasor / "report.json"))
        butonlar = [b.text() for b in widget.findChildren(widgets.SecondaryButton)]
        assert t("btn_view_tree", "tr") not in butonlar
    finally:
        widget.deleteLater()
        qapp.processEvents()
