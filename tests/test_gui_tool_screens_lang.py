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
def test_logical_image_option_is_translated_in_every_language(qapp, lang):
    """"Mantıksal İmaj" radyo düğmesi ve kartı her dilde kendi çevirisini
    göstermeli -- TR metnine takılı kalmış bir çağrıyı yakalar."""
    from strings import t
    widget = gui_v2.ForensicWidget(lang=lang)
    qapp.processEvents()
    try:
        assert widget.radio_acq_logical.text() == t("tool_acq_logical", lang)
        assert t("tool_logical_note", lang) in _all_texts(widget)
        if lang != "tr":
            assert t("tool_acq_logical", lang) != t("tool_acq_logical", "tr")
    finally:
        widget.deleteLater()
        qapp.processEvents()


@pytest.mark.parametrize("lang", LANGUAGES)
def test_segment_and_compress_hints_are_shown_in_every_language(qapp, lang):
    """Segment boyutu / gzip açıklamaları her dilde kendi çevirisiyle görünmeli."""
    from strings import t
    widget = gui_v2.ForensicWidget(lang=lang)
    qapp.processEvents()
    try:
        textler = _all_texts(widget)
        assert t("tool_segment_hint", lang) in textler
        assert t("tool_compress_hint", lang) in textler
        if lang != "tr":
            assert t("tool_compress_hint", lang) != t("tool_compress_hint", "tr")
    finally:
        widget.deleteLater()
        qapp.processEvents()


def test_acquisition_type_switches_visible_card(qapp):
    """Üç seçenek (Tam Disk / Dosya-Klasör / Mantıksal) sırayla SADECE kendi
    kartını göstermeli; Windows'a geçince mantıksal kök yol varsayılanı da
    C:\\ olmalı, elle değiştirilmişse dokunulmamalı."""
    widget = gui_v2.ForensicWidget(lang="en")
    qapp.processEvents()
    try:
        # isVisible() pencere gösterilmediği için hep False; açıkça gizlenip
        # gizlenmediğine (isHidden) bakılır.
        widget.radio_acq_logical.setChecked(True)
        assert not widget.logical_card.isHidden()
        assert widget.disk_card.isHidden() and widget.file_card.isHidden()
        widget.radio_acq_file.setChecked(True)
        assert widget.logical_card.isHidden() and not widget.file_card.isHidden()
        widget.radio_acq_disk.setChecked(True)
        assert widget.logical_card.isHidden() and not widget.disk_card.isHidden()

        assert widget.entry_logical_root.text() == "/"
        widget.radio_os_windows.setChecked(True)
        assert widget.entry_logical_root.text() == "C:\\"
        widget.entry_logical_root.setText("D:\\")
        widget.radio_os_linux.setChecked(True)
        assert widget.entry_logical_root.text() == "D:\\"
    finally:
        widget.deleteLater()
        qapp.processEvents()


@pytest.mark.parametrize("lang", LANGUAGES)
def test_local_mode_screen_builds_in_every_language(qapp, lang):
    """Yerel mod (SSH yok): SSH kartları gizli, OS Windows'a sabit, bağlantı
    hazır (LocalConnector), başlık seçili dilde."""
    from strings import t
    widget = gui_v2.ForensicWidget(initial_connection_method="local", lang=lang)
    qapp.processEvents()
    try:
        # yönetici uyarı şeridi: sadece yönetici DEĞİLKEN var, seçili dilde
        if gui_v2.is_admin():
            assert widget.admin_banner is None
        else:
            assert t("tool_local_admin_banner", lang) in _all_texts(widget)
        assert isinstance(widget.ssh, gui_v2.LocalConnector)
        assert widget.radio_os_windows.isChecked()
        assert widget.conn_method_value == "local"
        assert widget.entry_logical_root.text() == "C:\\"
        assert all(card.isHidden() for card in widget._ssh_only_cards)
        assert t("tool_local_title", lang) in _all_texts(widget)
        assert t("tool_local_info", lang) in _all_texts(widget)
        # Blok boyutu: yerel modda ag hizina gore aciklama YOK, sadece duz
        # MB degeri -- ag yok ki hizina gore secim yapilsin (kullanici bildirdi).
        combo_metinleri = [widget.combo_block_size.itemText(i) for i in range(widget.combo_block_size.count())]
        assert combo_metinleri == ["4 MB", "16 MB", "32 MB", "64 MB"]
        assert widget.combo_block_size.currentText() == "64 MB"
    finally:
        widget.deleteLater()
        qapp.processEvents()


def test_local_mode_refuses_output_on_source_or_without_admin(qapp, monkeypatch):
    """Kaynak diske yazma ve yetkisiz ham disk okuma İMAJ BAŞLAMADAN reddedilir."""
    from strings import t
    widget = gui_v2.ForensicWidget(initial_connection_method="local", lang="en")
    qapp.processEvents()
    hatalar = []
    monkeypatch.setattr(widget, "_show_error", hatalar.append)
    try:
        # yönetici değil -> disk modu reddedilir
        monkeypatch.setattr(gui_v2, "is_admin", lambda: False)
        assert widget._local_precheck(disk_number=1, out_path="D:\\x") is False
        assert hatalar[-1] == t("tool_local_err_admin", "en")

        # yönetici ama çıktı kaynakla aynı diskte -> reddedilir
        monkeypatch.setattr(gui_v2, "is_admin", lambda: True)
        monkeypatch.setattr(gui_v2, "check_output_not_on_source", lambda ssh, disk, out: "output_on_source")
        assert widget._local_precheck(disk_number=1, out_path="C:\\x") is False
        assert hatalar[-1] == t("tool_local_err_output_on_source", "en")

        # her şey yolunda, kaynak sistem diski DEĞİL -> geçer
        monkeypatch.setattr(gui_v2, "check_output_not_on_source", lambda ssh, disk, out: None)
        monkeypatch.setattr(gui_v2, "system_disk_number", lambda ssh: 0)
        assert widget._local_precheck(disk_number=1, out_path="D:\\x") is True

        # sistem diski + Offline -> reddedilir (salt-okunur yapılamaz)
        widget.radio_offline.setChecked(True)
        assert widget._local_precheck(disk_number=0, out_path="D:\\x") is False
        assert hatalar[-1] == t("tool_local_err_system_offline", "en")

        # sistem diski + Live -> kullanıcıya sorulur; hayır derse iptal, evet derse geçer
        widget.radio_live.setChecked(True)
        monkeypatch.setattr(widget, "_show_yesno_dialog", lambda title, msg: False)
        assert widget._local_precheck(disk_number=0, out_path="D:\\x") is False
        monkeypatch.setattr(widget, "_show_yesno_dialog", lambda title, msg: True)
        assert widget._local_precheck(disk_number=0, out_path="D:\\x") is True
    finally:
        widget.deleteLater()
        qapp.processEvents()


def test_local_mode_refuses_when_root_disk_unknown(qapp, monkeypatch, isolated_coc_log):
    """HATA 1 regresyonu (GUI ucu): mantiksal/dosya modunda kok yolun diski
    belirlenemediginde eski `check_root_output_separate` None donuyordu ve
    `_local_precheck` None'ı 'sorun yok' sayip imaja baslatmana izin
    veriyordu. Artik fonksiyon fail-CLOSED `output_disk_unknown` dondugu icin
    GUI de imaj BASLAMADAN reddetmeli."""
    from strings import t
    import local_connector as lc
    widget = gui_v2.ForensicWidget(initial_connection_method="local", lang="en")
    qapp.processEvents()
    hatalar = []
    monkeypatch.setattr(widget, "_show_error", hatalar.append)
    try:
        # kok yolun diski belirlenemiyor (PowerShell/partition hatasi simulasyonu)
        monkeypatch.setattr(lc, "_disk_number_for_letter", lambda ssh, harf: None)
        assert widget._local_precheck(root_path="C:\\", out_path="D:\\x") is False
        assert hatalar[-1] == t("tool_local_err_output_unknown", "en")
        # diski belirlenebilen normal durum degismemeli
        monkeypatch.setattr(lc, "_disk_number_for_letter", lambda ssh, harf: {"C": 0, "D": 1}.get(harf.upper()))
        assert widget._local_precheck(root_path="C:\\", out_path="D:\\x") is True
        assert widget._local_precheck(root_path="C:\\", out_path="C:\\x") is False
        assert hatalar[-1] == t("tool_local_err_output_on_source", "en")
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
