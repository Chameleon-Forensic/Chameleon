"""
RAM motoruna eklenen WinPmem (acik kaynak, Full RAM alternatifi) testleri --
bkz. docs/roadmap.md. Elevate+redirect (ShellExecuteW/cmd.exe) gercek Windows
davranisina bagli oldugu icin (mock ile dogrulanamaz), sadece SAF/testlenebilir
parcalar (parametre kurma, log ayristirma) burada test edilir; gercek surucu
yuklemesi gercek makinede dogrulandi (bkz. roadmap).
"""

import ram_gui as rg


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


def test_full_mode_defaults_to_winpmem_engine(qapp):
    """Vendor araci su an calismadigi icin (Error 577) varsayilan secili
    motor WinPmem olmali -- kullanici degistirmedigi surece."""
    widget = rg.RamEngineWidget(lang="en")
    qapp.processEvents()
    try:
        assert widget.radio_engine_winpmem.isChecked()
        assert not widget.radio_engine_vendor.isChecked()
    finally:
        widget.deleteLater()
        qapp.processEvents()


def test_start_uses_winpmem_path_and_acquire_args(qapp, tmp_path, monkeypatch):
    """_start(), WinPmem seciliyken dogru exe/komut ile RamWorker('full_winpmem', ...)
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
        assert yakalanan["mode"] == "full_winpmem"
        assert yakalanan["args"] == [str(fake_exe), "acquire", str(tmp_path / "out.raw")]
    finally:
        widget.deleteLater()
        qapp.processEvents()
