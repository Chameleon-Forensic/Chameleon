"""
RAM motoruna eklenen WinPmem (acik kaynak, Full RAM alternatifi) testleri --
bkz. docs/roadmap.md. Elevate+redirect (ShellExecuteW/cmd.exe) gercek Windows
davranisina bagli oldugu icin (mock ile dogrulanamaz), sadece SAF/testlenebilir
parcalar (parametre kurma, log ayristirma) burada test edilir; gercek surucu
yuklemesi gercek makinede dogrulandi (bkz. roadmap).
"""

from PySide6.QtWidgets import QLabel, QPushButton

import ram_gui as rg


def _all_texts(widget):
    return [w.text() for w in widget.findChildren(QLabel)] + [w.text() for w in widget.findChildren(QPushButton)]


def test_full_mode_ui_never_shows_the_word_winpmem(qapp):
    """Full RAM ekranindaki HICBIR gorunen metin 'winpmem' kelimesini
    icermemeli -- arac ismi kullaniciya gosterilmiyor, sadece rapor/log gibi
    dahili delil kayitlarinda (adli dogruluk icin) geciyor."""
    widget = rg.RamEngineWidget(lang="tr")
    qapp.processEvents()
    try:
        widget.radio_full.setChecked(True)
        qapp.processEvents()
        metinler = " ".join(_all_texts(widget)).lower()
        assert "winpmem" not in metinler
    finally:
        widget.deleteLater()
        qapp.processEvents()


def test_full_mode_elevates_with_hidden_window(qapp, tmp_path, monkeypatch):
    """cmd penceresi GORUNMEMELI (nShowCmd=0) -- ilerleme zaten uygulamanin
    kendi gunluk paneline aktariliyor, ayri bir konsol penceresi gereksiz."""
    fake_exe = tmp_path / "winpmem.exe"
    fake_exe.write_bytes(b"")
    monkeypatch.setattr(rg, "WINPMEM_PATH", str(fake_exe))

    yakalanan = {}

    def sahte_shell_execute(hwnd, verb, dosya, params, dizin, show_cmd):
        yakalanan["show_cmd"] = show_cmd
        return 33  # >32 -- basarili sayilir, tail dongusune girmesin diye log'u da olusturuyoruz

    class _SahteShell32:
        ShellExecuteW = staticmethod(sahte_shell_execute)

    class _SahteWindll:
        shell32 = _SahteShell32()

    monkeypatch.setattr(rg.ctypes, "windll", _SahteWindll())
    monkeypatch.setattr(rg.time, "sleep", lambda *_a: None)
    # coc/incomplete_ops/ForensicReport gercek dosyalara yazmasin diye
    # devre disi birakiliyor -- bu test SADECE ShellExecuteW'e verilen
    # nShowCmd degerini dogruluyor.
    monkeypatch.setattr(rg, "coc", None)
    monkeypatch.setattr(rg, "incomplete_ops", None)
    monkeypatch.setattr(rg, "ForensicReport", None)

    worker = rg.RamWorker("full", [str(fake_exe), "acquire", str(tmp_path / "out.raw")],
                           str(tmp_path / "out.raw"), "", "", "")
    # Tail donguesunun sonsuza kadar donmemesi icin log dosyasini hemen
    # "bitti" olarak isaretliyoruz.
    log_path = str(tmp_path / "out.raw.log")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("CHAMELEON_DONE\n")
    worker.log.connect(lambda *_a: None)
    worker.status.connect(lambda *_a: None)
    worker._run_full_mode_winpmem()

    assert yakalanan["show_cmd"] == 0


def test_format_duration_tr():
    assert rg.format_duration_tr(45) == "45 sn"
    assert rg.format_duration_tr(130) == "2 dk 10 sn"
    assert rg.format_duration_tr(120) == "2 dk"
    assert rg.format_duration_tr(3900) == "1 sa 5 dk"


def test_emit_hash_progress_shows_percent_and_eta(monkeypatch):
    """Kullanici istegi: tahmini kalan sure de gosterilsin -- SABIT bir
    tahmin degil, olculen GERCEK hiza gore (boylece RAM boyutuna ve
    donanima otomatik uyar)."""
    zaman = [0.0]
    monkeypatch.setattr(rg.time, "monotonic", lambda: zaman[0])

    worker = rg.RamWorker("full", ["exe", "acquire", "out"], "out", "", "", "")
    durumlar = []
    worker.status.connect(lambda metin, _renk=None: durumlar.append(metin))

    worker._emit_hash_progress(0, 1000)  # ilk cagri -- baslangic zamanini kaydeder, henuz hiz yok
    zaman[0] = 2.0
    worker._emit_hash_progress(500, 1000)  # 2 saniyede yarisi -- hiz: 250/sn, kalan 500 -> 2 sn

    assert "%50" in durumlar[-1]
    assert "2 sn" in durumlar[-1]


def test_emit_hash_progress_throttles_updates(monkeypatch):
    """Cok sik ilerleme cagrisi (kucuk buffer_size) sinyal trafigini
    bogmamali -- ayni saniye icinde ikinci cagri (henuz bitmemisken)
    yeni bir durum yaymamali."""
    zaman = [0.0]
    monkeypatch.setattr(rg.time, "monotonic", lambda: zaman[0])

    worker = rg.RamWorker("full", ["exe", "acquire", "out"], "out", "", "", "")
    durumlar = []
    worker.status.connect(lambda metin, _renk=None: durumlar.append(metin))

    worker._emit_hash_progress(100, 1000)
    ilk_sayi = len(durumlar)
    zaman[0] = 0.3  # 1 saniyeden az gecti
    worker._emit_hash_progress(200, 1000)
    assert len(durumlar) == ilk_sayi, "1 saniyeden once ikinci guncelleme yayilmamali"


def test_completed_status_is_emitted_only_after_hash_and_report_are_done(tmp_path, monkeypatch):
    """Kullanici gercek makinede bildirdi: 'Tamamlandi' yazisi cikinca bile
    ilerleme cubugu donmeye devam ediyordu -- sebebi, buyuk bir imajda
    dakikalar surebilen hash hesaplamasi BITMEDEN 'Tamamlandi' yazilmasiydi.
    Bu test, hash hesaplamasi calisirken durum metninin HENUZ 'Tamamlandi'
    OLMAMASINI, sadece hash+rapor GERCEKTEN bittikten sonra 'Tamamlandi'
    yazilmasini dogrular."""
    out_path = tmp_path / "test.img"
    out_path.write_bytes(b"x" * 10)
    log_path = tmp_path / "test.img.log"
    log_path.write_text("Completed imaging in 1s\nCHAMELEON_DONE\n", encoding="utf-8")

    sira = []

    def sahte_hash_file_multi(path, progress=None):
        sira.append("hash_hesaplandi")
        return {"sha256": "h", "md5": "m", "sha1": "s"}

    monkeypatch.setattr(rg, "hash_file_multi", sahte_hash_file_multi)
    monkeypatch.setattr(rg, "coc", None)
    monkeypatch.setattr(rg, "incomplete_ops", None)
    monkeypatch.setattr(rg, "ForensicReport", None)
    monkeypatch.setattr(rg.time, "sleep", lambda *_a: None)

    worker = rg.RamWorker("full", ["exe", "acquire", str(out_path)], str(out_path), "", "", "")
    worker.status.connect(lambda metin, _renk=None: sira.append(f"durum:{metin}"))
    worker.log.connect(lambda *_a: None)
    worker._tail_log_winpmem(str(log_path), str(out_path))

    hash_idx = sira.index("hash_hesaplandi")
    tamamlandi_idx = sira.index("durum:Tamamlandı.")
    assert hash_idx < tamamlandi_idx, "hash hesaplanmadan 'Tamamlandi' yazilmamali"
    # Hash hesaplanmadan ONCE gosterilen hicbir durum metni 'Tamamlandi' OLMAMALI.
    onceki_durumlar = [s for s in sira[:hash_idx] if s.startswith("durum:")]
    assert all(d != "durum:Tamamlandı." for d in onceki_durumlar)


def test_build_winpmem_elevate_params_quotes_exe_path_and_redirects_output(tmp_path):
    # Yol kasitli olarak bosluk iceriyor (ör. "Program Files") -- list2cmdline
    # boslugu OLMAYAN yollari tirnaklamaz, bu yuzden tirnaklamanin gercekten
    # calistigini gormek icin boslukla test etmek gerekiyor.
    klasor = tmp_path / "go winpmem dir"
    klasor.mkdir()
    exe = str(klasor / "go-winpmem.exe")
    out = str(klasor / "test.raw")
    log = out + ".log"

    params = rg.build_winpmem_elevate_params([exe, "acquire", out], log)

    assert params.startswith('/c "')
    assert f'"{exe}" acquire "{out}"' in params
    assert f'> "{log}" 2>&1' in params
    assert "CHAMELEON_DONE" in params
    # cmd.exe /c'nin disaridan bir tirnak siline bilecegi kurala karsi --
    # butun govde bir kat FAZLA tirnakla sarilmali.
    assert params.count('"') % 2 == 0


def test_winpmem_log_finished_only_after_sentinel():
    assert not rg.winpmem_log_finished("Copying 5864448 pages ...\n")
    assert rg.winpmem_log_finished("Copying ...\nCompleted imaging in 6m30s\nCHAMELEON_DONE\n")


def test_winpmem_log_succeeded_matches_real_output():
    basarili_log = (
        "Copying 5864448 pages (0x597c00000) from 0x100000000\n"
        "Completed imaging in 6m30.4163291s\n"
        "Stopped service winpmem\n"
    )
    assert rg.winpmem_log_succeeded(basarili_log)


def test_winpmem_log_succeeded_false_on_error_only():
    hata_log = "StartService failed (error 577). The driver may be unsigned.\n"
    assert not rg.winpmem_log_succeeded(hata_log)


def test_full_mode_has_no_engine_choice_in_ui(qapp):
    """Full RAM'de artik motor secimi YOK -- vendor araci (RamImagerCLI)
    SADECE Process Dump'ta kullaniliyor, kullaniciya secenek sunulmuyor."""
    widget = rg.RamEngineWidget(lang="en")
    qapp.processEvents()
    try:
        assert not hasattr(widget, "radio_engine_winpmem")
        assert not hasattr(widget, "radio_engine_vendor")
    finally:
        widget.deleteLater()
        qapp.processEvents()


def test_case_notes_field_threads_through_to_ram_worker(qapp, tmp_path, monkeypatch):
    """Vaka Bilgileri'ndeki serbest metin notu RamWorker'a ve oradan rapora
    (case_notes) gitmeli (kullanici istegi, bkz. gui_v2.py'deki AYNI)."""
    fake_exe = tmp_path / "winpmem.exe"
    fake_exe.write_bytes(b"")
    monkeypatch.setattr(rg, "WINPMEM_PATH", str(fake_exe))

    widget = rg.RamEngineWidget(lang="en")
    qapp.processEvents()
    yakalanan = {}

    class _SahteSinyal:
        def connect(self, *a, **kw):
            pass

    class _SahteWorker:
        def __init__(self, mode, args, out_path, case, examiner, custodian, **kw):
            yakalanan["case_notes"] = kw.get("case_notes")
            self.log = _SahteSinyal()
            self.status = _SahteSinyal()
            self.report_ready = _SahteSinyal()
            self.finished = _SahteSinyal()

        def start(self):
            pass

    monkeypatch.setattr(rg, "RamWorker", _SahteWorker)
    try:
        widget.entry_case_notes.setPlainText("RAM alirken sistem yavastı.")
        widget.radio_full.setChecked(True)
        widget.entry_out.setText(str(tmp_path / "out.raw"))
        widget._start()
        assert yakalanan["case_notes"] == "RAM alirken sistem yavastı."
    finally:
        widget.deleteLater()
        qapp.processEvents()


def test_start_uses_winpmem_path_and_acquire_args(qapp, tmp_path, monkeypatch):
    """_start(), Full RAM seciliyken dogru exe/komut ile RamWorker('full', ...)
    olusturmali -- gercekten calistirmadan (worker.start yerine sahte kontrol)."""
    fake_exe = tmp_path / "winpmem.exe"
    fake_exe.write_bytes(b"")
    monkeypatch.setattr(rg, "WINPMEM_PATH", str(fake_exe))

    widget = rg.RamEngineWidget(lang="en")
    qapp.processEvents()
    yakalanan = {}

    class _SahteSinyal:
        def connect(self, *a, **kw):
            pass

    class _SahteWorker:
        def __init__(self, mode, args, out_path, *a, **kw):
            yakalanan["mode"] = mode
            yakalanan["args"] = args
            self.log = _SahteSinyal()
            self.status = _SahteSinyal()
            self.report_ready = _SahteSinyal()
            self.finished = _SahteSinyal()

        def start(self):
            pass

    monkeypatch.setattr(rg, "RamWorker", _SahteWorker)
    try:
        widget.radio_full.setChecked(True)
        widget.entry_out.setText(str(tmp_path / "out.raw"))
        widget._start()
        assert yakalanan["mode"] == "full"
        assert yakalanan["args"] == [str(fake_exe), "acquire", str(tmp_path / "out.raw")]
    finally:
        widget.deleteLater()
        qapp.processEvents()
