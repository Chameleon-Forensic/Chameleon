"""chain_of_custody.py icin testler -- ozellikle _sanitize_log_field()
(guvenlik denetiminde bulunan, HEDEF cihazdan gelen dosya adlariyla delil
zincirinin manipule edilebildigi gercek bir acik icin eklenmisti, bkz.
docs/roadmap.md '4 uzman ajanla kapsamli inceleme'). Bu suit hem 'delil
kaybi' hem 'sahte kayit enjeksiyonu' senaryolarinin engellendigini
dogrular."""

import os

import chain_of_custody as coc


def test_log_event_round_trips_through_read_events(isolated_coc_log):
    coc.log_event(coc.EVENT_EXAM_START, "Test baslatildi")
    coc.log_event(coc.EVENT_BLOCK_ACQUIRED, "Blok 0 alindi", "abc123")

    events = coc.read_events()
    assert len(events) == 2
    assert events[0]["event"] == coc.EVENT_EXAM_START
    assert events[0]["hash"] is None
    assert events[1]["event"] == coc.EVENT_BLOCK_ACQUIRED
    assert events[1]["hash"] == "abc123"


def test_read_events_filters_by_time_range(isolated_coc_log):
    coc.log_event(coc.EVENT_EXAM_START, "ilk")
    events_all = coc.read_events()
    ts = events_all[0]["timestamp_utc"]

    # start_time_utc'nin TAM O ANI dahil etmesi gerekiyor (ts < start ise atla)
    assert coc.read_events(start_time_utc=ts, end_time_utc=ts)
    # gelecekte bir start_time_utc verilirse hicbir olay donmemeli
    future = "9999-01-01T00:00:00Z"
    assert coc.read_events(start_time_utc=future) == []


def test_pipe_in_description_does_not_break_log_parsing(isolated_coc_log):
    """Eskiden: HEDEFteki 'kotu|dosya.txt' adi, log parse'inda parca
    sayisini bozup KAYDIN SESSIZCE DUSMESINE (delil kaybi) sebep oluyordu."""
    coc.log_event(coc.EVENT_EXAM_START, "onceki kayit")
    kotu_niyetli_ad = "kotu|dosya.txt"
    coc.log_event(coc.EVENT_BLOCK_ACQUIRED, kotu_niyetli_ad, "hash1")

    events = coc.read_events()
    assert len(events) == 2, "pipe iceren aciklama yuzunden bir kayit DUSMEMELI"
    assert "dosya.txt" in events[1]["description"]
    assert "|" not in events[1]["description"], "gercek '|' log ayracıyla karismamali"


def test_newline_in_description_cannot_inject_fake_log_line(isolated_coc_log):
    """Eskiden: aciklamaya satir sonu + sahte '[ts] | EVENT | .. | hash'
    deseni eklenerek SAHTE bir olay log dosyasina ENJEKTE edilebiliyordu."""
    sahte_satir = "normal_ad\n[2026-01-01T00:00:00Z] | EXAM_END | sahte-olay | sahte-hash"
    coc.log_event(coc.EVENT_BLOCK_ACQUIRED, sahte_satir, "gercek-hash")

    events = coc.read_events()
    # TEK bir kayit olmali -- enjekte edilmeye calisilan "EXAM_END" AYRI
    # bir olay olarak GORUNMEMELI, hepsi tek satirin parcasi olarak kalmali
    assert len(events) == 1
    assert "\n" not in events[0]["description"]
    assert events[0]["event"] == coc.EVENT_BLOCK_ACQUIRED


def test_read_events_returns_empty_list_for_missing_file(tmp_path):
    assert coc.read_events(log_file_path=str(tmp_path / "yok.log")) == []


def test_sanitize_log_field_handles_none():
    assert coc._sanitize_log_field(None) is None


# ---------------------------------------------------------------------------
# Hata 1: dosya adi sadece saniye hassasiyetli zaman damgasindan uretiliyordu,
# PID/UUID gibi bir benzersizlik bileseni yoktu -- iki surec AYNI saniyede
# baslarsa AYNI dosyaya yazip delillerini karistirabilirdi.
# ---------------------------------------------------------------------------

def test_log_file_name_includes_pid_for_cross_process_uniqueness(isolated_coc_log, monkeypatch):
    """Ayni saniyede baslayan iki AYRI surecin (orn. SSH motoru + RAM
    motoru) ayni case_<timestamp>.log dosyasina yazip olaylarini
    KARISTIRMAMASI icin dosya adina os.getpid() eklenmis olmali."""
    sabit_pid = 424242
    monkeypatch.setattr(coc.os, "getpid", lambda: sabit_pid)
    monkeypatch.setattr(coc, "_current_log_file", None, raising=False)

    log_path = coc.get_log_file_path()
    assert str(sabit_pid) in os.path.basename(log_path), (
        "log dosyasi adinda surec kimligi (PID) bulunmali -- aksi halde "
        "ayni saniyede baslayan iki surec CARPISABILIR"
    )
    # mevcut "case_<tarih-saat>" on-eki BOZULMAMALI
    assert os.path.basename(log_path).startswith("case_")
    assert log_path.endswith(".log")


class _FakeNow:
    def strftime(self, _fmt):
        return "20260101-120000"


class _FakeDatetime:
    @staticmethod
    def now(_tz):
        return _FakeNow()


def test_two_processes_starting_in_same_second_get_different_log_files(isolated_coc_log, monkeypatch):
    """Zaman damgasi AYNI kalsa bile (ayni saniyede baslama senaryosu),
    farkli PID'ler farkli dosya yolu URETMELI."""
    monkeypatch.setattr(coc, "datetime", _FakeDatetime)

    monkeypatch.setattr(coc.os, "getpid", lambda: 1111)
    monkeypatch.setattr(coc, "_current_log_file", None, raising=False)
    yol1 = coc.get_log_file_path()

    monkeypatch.setattr(coc.os, "getpid", lambda: 2222)
    monkeypatch.setattr(coc, "_current_log_file", None, raising=False)
    yol2 = coc.get_log_file_path()

    assert yol1 != yol2, "ayni saniyede baslayan farkli surecler AYNI log dosyasini PAYLASMAMALI"


# ---------------------------------------------------------------------------
# Hata 2: get_log_file_path()/read_events(), log_event()'in aksine
# _get_log_file()'i try/except'siz cagirip bir OSError'i cagirana sizdiriyordu.
# ---------------------------------------------------------------------------

def test_get_log_file_path_returns_none_instead_of_raising_on_os_error(tmp_path, monkeypatch):
    """os.makedirs basarisiz olursa (disk dolu/salt-okunur/USB cikarilmis),
    get_log_file_path() artik OSError FIRLATMAMALI -- None donmeli."""
    monkeypatch.setattr(coc, "LOG_DIR", str(tmp_path / "yok"))
    monkeypatch.setattr(coc, "_current_log_file", None, raising=False)

    def patlayan_makedirs(*_args, **_kwargs):
        raise OSError("disk dolu (simulasyon)")

    monkeypatch.setattr(coc.os, "makedirs", patlayan_makedirs)

    assert coc.get_log_file_path() is None, (
        "dosya sistemi hatasi cagirana sizdirilmemeli, None donulmeli"
    )


def test_read_events_does_not_raise_when_log_path_cannot_be_determined(tmp_path, monkeypatch):
    """read_events() (path verilmeden cagrildiginda) get_log_file_path()'in
    None donmesini de gorulmemis bir hata olmadan ele almali."""
    monkeypatch.setattr(coc, "LOG_DIR", str(tmp_path / "yok"))
    monkeypatch.setattr(coc, "_current_log_file", None, raising=False)

    def patlayan_makedirs(*_args, **_kwargs):
        raise OSError("disk dolu (simulasyon)")

    monkeypatch.setattr(coc.os, "makedirs", patlayan_makedirs)

    assert coc.read_events() == []


# ---------------------------------------------------------------------------
# Hata 3: read_events(), log dosyasi YOKSA "hic olay yok" ile "log'a
# ulasilamadi" arasindaki farki hic bildirmiyordu (sessizce bos liste).
# ---------------------------------------------------------------------------

def test_read_events_with_status_distinguishes_missing_file_from_no_events(tmp_path, isolated_coc_log):
    # Henuz hic log_event() cagrilmadi -- dosya yok, ama BU "hic olay yok"
    # anlamina gelmeli (log'a ulasilamadi anlamina GELMEMELI).
    hic_olay_yok = coc.read_events_with_status(log_file_path=str(tmp_path / "hic-yazilmadi.log"))
    assert hic_olay_yok == {"events": [], "log_file_found": False}, (
        "dosya hic olusturulmadiysa bu durum acikca 'log_file_found': False "
        "ile isaretlenmeli -- forensic_report.py bunu 'hic olay yok' ile "
        "karistirmamali"
    )

    # Gercekten olay olan (dosya var) durumda log_file_found True olmali.
    coc.log_event(coc.EVENT_EXAM_START, "test")
    sonuc = coc.read_events_with_status()
    assert sonuc["log_file_found"] is True
    assert len(sonuc["events"]) == 1


def test_read_events_backward_compatible_signature_unchanged(isolated_coc_log):
    """read_events() imzasi/davranisi (bos liste donmesi) DEGISMEMELI --
    sadece read_events_with_status() ek bilgi tasir."""
    coc.log_event(coc.EVENT_EXAM_START, "test")
    assert coc.read_events() == coc.read_events_with_status()["events"]


def test_forensic_report_surfaces_log_missing_status(tmp_path, monkeypatch):
    """forensic_report.to_dict()'in chain_of_custody.log_dosyasi_bulundu
    alani, log dosyasina ulasilamadiginda False olmali -- incelemeci bos
    bir events listesinin nedenini raporun KENDISINDEN ayirt edebilsin."""
    import forensic_report as fr

    monkeypatch.setattr(coc, "LOG_DIR", str(tmp_path / "yok"))
    monkeypatch.setattr(coc, "_current_log_file", None, raising=False)

    def patlayan_makedirs(*_args, **_kwargs):
        raise OSError("USB cikarildi (simulasyon)")

    monkeypatch.setattr(coc.os, "makedirs", patlayan_makedirs)

    report = fr.ForensicReport(case_id="V")
    report.start(engine="ssh_engine", method="disk")
    d = report.to_dict()

    assert d["chain_of_custody"]["log_dosyasi_bulundu"] is False
    assert d["chain_of_custody"]["events"] == []
