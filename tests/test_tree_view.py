"""
Alinan dosya/klasor agaci goruntuleme testleri (hoca istegi, bkz.
docs/roadmap.md). Dosya/Klasor ve Mantiksal Imaj'da agac manifest'ten
kurulur; Tam Disk'te (ham blok imaji) pytsk3 ile DOGRUDAN imajin
kendisinden kurulur (bkz. disk_tree.py, test_disk_tree.py).
"""

import json
import os
import tempfile

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


def test_report_summary_shows_tree_button_for_disk_with_real_image(qapp, fat12_image_path):
    """Tam Disk'te buton artik pytsk3 (disk_tree.py) ile GERCEK bir ham
    imaj dosyasi varsa gorunuyor -- test_report_summary_shows_tree_button_
    only_for_file_and_logical'daki "disk" senaryosu output_path olarak bir
    KLASOR verdigi icin (dogru sekilde) hep False donuyordu, bu test
    output_path GERCEK bir imaj DOSYASI oldugunda True donmesini dogrular."""
    from forensic_report import ForensicReport
    from strings import t
    from ui_kit import widgets

    widget = gui_v2.ForensicWidget(lang="tr")
    qapp.processEvents()
    try:
        report = ForensicReport(case_id="", examiner="", custodian="", organization="")
        report.start(engine="ssh_engine", method="disk", target_os="linux")
        report.finish(status="success", output_path=fat12_image_path)
        rapor_yolu = os.path.join(os.path.dirname(fat12_image_path), "report.json")
        widget._show_report_summary(report, rapor_yolu)
        butonlar = [b.text() for b in widget.findChildren(widgets.SecondaryButton)]
        assert t("btn_view_tree", "tr") in butonlar
    finally:
        widget.deleteLater()
        qapp.processEvents()


def test_report_summary_hides_tree_button_for_segmented_or_compressed_disk(qapp, tmp_path):
    """disk_tree.py sadece TEK PARCALI, sikistirilmamis ham imajlari
    destekliyor (bkz. docs/roadmap.md) -- segmentli (.001) veya gzip'li
    (.gz) bir imaj dosyasi GERCEKTEN var olsa bile buton gorunmemeli,
    aksi halde pytsk3 sadece ilk parcayi/sikistirilmis bayt akisini
    ham disk gibi okumaya calisir, YANLIS/eksik bir agac gosterebilirdi."""
    from forensic_report import ForensicReport
    from strings import t
    from ui_kit import widgets

    for isim in ("full_image.001", "full_image.dd.gz"):
        imaj_yolu = tmp_path / isim
        imaj_yolu.write_bytes(b"\x00" * 1024)
        widget = gui_v2.ForensicWidget(lang="tr")
        qapp.processEvents()
        try:
            report = ForensicReport(case_id="", examiner="", custodian="", organization="")
            report.start(engine="ssh_engine", method="disk", target_os="linux")
            report.finish(status="success", output_path=str(imaj_yolu))
            widget._show_report_summary(report, str(tmp_path / "report.json"))
            butonlar = [b.text() for b in widget.findChildren(widgets.SecondaryButton)]
            assert t("btn_view_tree", "tr") not in butonlar, f"dosya={isim}"
        finally:
            widget.deleteLater()
            qapp.processEvents()


def test_show_disk_tree_dialog_populates_tree_widget(qapp, fat12_image_path, monkeypatch):
    from strings import t

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
        widget._show_disk_tree_dialog(fat12_image_path)
        tree = yakalanan["tree"]
        kok = tree.topLevelItem(0)
        # Bolum tablosu yok -- "Tum Imaj" etiketiyle TEK bir kok dugum.
        assert kok.text(0) == t("tool_tree_whole_image", "tr")
        alt_isimler = {kok.child(i).text(0) for i in range(kok.childCount())}
        assert alt_isimler == {"HELLO.TXT", "SUBDIR"}
    finally:
        widget.deleteLater()
        qapp.processEvents()


@pytest.mark.parametrize("kotu_isim", [
    "../../evil.txt",
    "..\\..\\evil.txt",
    "../../../etc/passwd",
    "..",
    "/etc/passwd",
])
def test_guvenli_onizleme_dosya_adi_strips_traversal_and_separators(kotu_isim):
    """HATA 2 birim testi (path traversal, CWE-22): disk_tree.py'den gelen
    (sanitize edilmemis) isim ne olursa olsun, onizleme dosya adinda '/'\
    '\\' veya '..' KESINLIKLE bulunmamali -- ad inode'a dayanmali."""
    guvenli = gui_v2._guvenli_onizleme_dosya_adi(42, kotu_isim)
    assert "/" not in guvenli
    assert "\\" not in guvenli
    assert ".." not in guvenli
    assert guvenli.startswith("inode42")


def test_show_disk_tree_dialog_double_click_sanitizes_traversal_filename(qapp, tmp_path, monkeypatch):
    """HATA 2 regresyon testi (path traversal, CWE-22): disk_tree.py ham
    imajdan sanitize edilmemis bir dosya adi dondurse bile ('../../evil.txt'
    gibi -- pytsk3 dizin girdisi adlarini OS dosya adi dogrulamasindan
    GECIRMEDEN ham bayttan okuyor), cift tiklamada cikarilan dosyanin
    GERCEK (realpath) yolu HER ZAMAN gecici klasorun ICINDE kalmali,
    hicbir sekilde disina yazilmamali."""
    kotu_isim = "../../../../evil.txt"
    sahte_bolumler = [{
        "description": None,
        "offset": 0,
        "tree": {kotu_isim: (7, 3)},
        "error": None,
    }]
    monkeypatch.setattr(gui_v2.disk_tree, "open_disk_tree", lambda yol: sahte_bolumler)

    yakalanan = {}

    def _sahte_extract_file(image_path, offset, inode, dest_path):
        yakalanan["dest_path"] = dest_path
        with open(dest_path, "wb") as f:
            f.write(b"zararsiz")

    monkeypatch.setattr(gui_v2.disk_tree, "extract_file", _sahte_extract_file)
    monkeypatch.setattr(gui_v2.os, "startfile", lambda yol: None, raising=False)

    orijinal = gui_v2.QTreeWidget

    class YakalayanTree(orijinal):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            yakalanan["tree"] = self

    monkeypatch.setattr(gui_v2, "QTreeWidget", YakalayanTree)

    sahte_imaj = tmp_path / "sahte.img"
    sahte_imaj.write_bytes(b"\x00")

    widget = gui_v2.ForensicWidget(lang="tr")
    qapp.processEvents()
    try:
        widget._show_disk_tree_dialog(str(sahte_imaj))
        tree = yakalanan["tree"]
        kok = tree.topLevelItem(0)
        dosya_oge = kok.child(0)
        assert dosya_oge.text(0) == kotu_isim  # goruntulemede orijinal isim (bilerek) korunuyor

        tree.itemDoubleClicked.emit(dosya_oge, 0)

        assert "dest_path" in yakalanan
        gecici_kok = os.path.realpath(tempfile.gettempdir())
        gercek_hedef = os.path.realpath(yakalanan["dest_path"])
        assert gercek_hedef == gecici_kok or gercek_hedef.startswith(gecici_kok + os.sep)
    finally:
        widget.deleteLater()
        qapp.processEvents()


def test_show_disk_tree_dialog_bad_image_shows_error_not_crash(qapp, tmp_path, monkeypatch):
    yakalanan = []
    widget = gui_v2.ForensicWidget(lang="tr")
    qapp.processEvents()
    monkeypatch.setattr(widget, "_show_error", yakalanan.append)
    olmayan_yol = tmp_path / "does_not_exist.img"
    try:
        widget._show_disk_tree_dialog(str(olmayan_yol))  # cokmemeli
        assert len(yakalanan) == 1
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
