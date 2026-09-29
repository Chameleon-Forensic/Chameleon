"""
AcquisitionWorker (gui_v2.py) icin dogrudan testler -- bkz. docs/roadmap.md:
gercek bir hata yakalandi (AttributeError: '_display_timezone'), su ana
kadar hicbir test bu sinifi hic orneklemiyordu (SSH tam disk/dosya-klasor/
mantiksal imaj alma islemleri, rapor uretilirken SESSIZCE cokuyordu --
genis bir except Exception blogu hatayi yutup sadece gunluge yaziyordu).
"""

import gui_v2


def test_format_duration_tr():
    assert gui_v2.format_duration_tr(45) == "45 sn"
    assert gui_v2.format_duration_tr(130) == "2 dk 10 sn"
    assert gui_v2.format_duration_tr(3900) == "1 sa 5 dk"


def test_ilerleme_metni_shows_percent_and_eta(monkeypatch):
    zaman = [0.0]
    monkeypatch.setattr(gui_v2.time, "monotonic", lambda: zaman[0])
    worker = gui_v2.AcquisitionWorker("linux_disk", None, {
        "case_id": "", "examiner": "", "custodian": "", "organization": "",
        "conn_method": "direct", "host": "h",
    })

    worker._ilerleme_metni(0.0)  # ilk cagri -- baslangici kaydeder
    zaman[0] = 2.0
    metin = worker._ilerleme_metni(0.5, "(500/1000 blok)")  # 2 sn'de yarisi

    assert "%50" in metin
    assert "(500/1000 blok)" in metin
    assert "2 sn" in metin  # 2 sn'de %50 -> kalan %50 icin de ~2 sn


def test_ilerleme_metni_resume_uses_only_this_run_throughput(monkeypatch):
    """Yarim kalan bir islemden %90'da devam edilirse, bu calistirmadaki
    GERCEK hiz olculmeden ('neredeyse bitti' yanlis tahmini yerine) sure
    gosterilmemeli."""
    zaman = [0.0]
    monkeypatch.setattr(gui_v2.time, "monotonic", lambda: zaman[0])
    worker = gui_v2.AcquisitionWorker("linux_disk", None, {
        "case_id": "", "examiner": "", "custodian": "", "organization": "",
        "conn_method": "direct", "host": "h",
    })

    worker._ilerleme_metni(0.90)  # resume: %90'dan basliyor
    zaman[0] = 2.0
    metin = worker._ilerleme_metni(0.90)  # bu calistirmada HENUZ ilerleme yok
    assert "tahmini kalan" not in metin


def _ctx(**ekstra):
    taban = {
        "case_id": "V-1", "examiner": "inceleyen", "custodian": "emanetci",
        "organization": "org", "conn_method": "direct", "host": "1.2.3.4",
        "display_timezone": "Europe/Istanbul",
    }
    taban.update(ekstra)
    return taban


def test_new_report_does_not_crash_without_display_timezone_in_ctx():
    """display_timezone hic verilmese bile (eski/eksik ctx) cokmemeli --
    .get() ile okundugu icin None'a duser, hata firlatmaz."""
    worker = gui_v2.AcquisitionWorker("linux_disk", None, {
        "case_id": "", "examiner": "", "custodian": "", "organization": "",
        "conn_method": "direct", "host": "h",
    })
    report = worker._new_report("ssh_engine", "disk")
    assert report is not None


def test_new_report_builds_real_report_with_display_timezone(qapp):
    worker = gui_v2.AcquisitionWorker("linux_disk", None, _ctx())
    report = worker._new_report("ssh_engine", "disk", target_os="linux")
    assert report is not None
    d = report.to_dict()
    assert d["case"]["case_id"] == "V-1"
    assert d["tool"]["method"] == "disk"


def test_stop_button_appears_only_while_acquisition_runs(qapp, tmp_path):
    """Durdur butonu baslangicta gizli, alma baslayinca gorunur, worker
    bitince tekrar gizlenir (kullanici istegi). ssh=None oldugu icin
    gercek worker hizlica (baglanti yok) hata verip biter -- burada sadece
    buton gorunurlugu ilgilendiriyor, alma sonucunu degil."""
    widget = gui_v2.ForensicWidget(lang="tr")
    qapp.processEvents()
    try:
        assert widget.btn_stop.isHidden()
        widget._begin_acquisition("file", {
            "case_id": "", "examiner": "", "custodian": "", "organization": "",
            "conn_method": "direct", "host": "h", "remote_path": "/tmp/x",
            "out_dir": str(tmp_path), "password": None, "target_os": "linux",
            "logical": False,
        }, "test")
        qapp.processEvents()
        assert not widget.btn_stop.isHidden()
        widget.acq_worker.wait(3000)
        qapp.processEvents()
        assert widget.btn_stop.isHidden()
    finally:
        widget.deleteLater()
        qapp.processEvents()


def test_stop_acquisition_asks_confirmation_then_requests_stop(qapp, monkeypatch):
    widget = gui_v2.ForensicWidget(lang="tr")
    qapp.processEvents()
    try:
        widget.acq_worker = gui_v2.AcquisitionWorker("file", None, {
            "case_id": "", "examiner": "", "custodian": "", "organization": "",
            "conn_method": "direct", "host": "h",
        })

        monkeypatch.setattr(widget, "_show_yesno_dialog", lambda *_a: False)
        widget._stop_acquisition()
        assert not widget.acq_worker._durdur_bayragi.is_set(), "onay verilmezse durdurulmamali"

        monkeypatch.setattr(widget, "_show_yesno_dialog", lambda *_a: True)
        widget._stop_acquisition()
        assert widget.acq_worker._durdur_bayragi.is_set()
    finally:
        widget.deleteLater()
        qapp.processEvents()


def test_case_notes_field_threads_through_to_report(qapp):
    """Vaka Bilgileri'ndeki serbest metin notu, ctx uzerinden worker'a ve
    oradan rapora (case_notes) gitmeli (kullanici istegi)."""
    widget = gui_v2.ForensicWidget(lang="tr")
    qapp.processEvents()
    try:
        widget.entry_case_notes.setPlainText("Sahada gozlemlenen bir durum.")
        ctx = widget._new_report_ctx()
        assert ctx["case_notes"] == "Sahada gozlemlenen bir durum."

        worker = gui_v2.AcquisitionWorker("linux_disk", None, ctx)
        report = worker._new_report("ssh_engine", "disk")
        assert report.to_dict()["case"]["case_notes"] == "Sahada gozlemlenen bir durum."
    finally:
        widget.deleteLater()
        qapp.processEvents()


def test_new_report_ctx_includes_display_timezone(qapp):
    """ForensicWidget._new_report_ctx() -- worker'in okudugu anahtarin
    gercekten oradan geldigini dogrular (regresyon: bu satir eksikti)."""
    widget = gui_v2.ForensicWidget(lang="tr")
    qapp.processEvents()
    try:
        widget._display_timezone = "Europe/Istanbul"
        ctx = widget._new_report_ctx()
        assert ctx["display_timezone"] == "Europe/Istanbul"
    finally:
        widget.deleteLater()
        qapp.processEvents()
