"""chain_of_custody.py icin testler -- ozellikle _sanitize_log_field()
(guvenlik denetiminde bulunan, HEDEF cihazdan gelen dosya adlariyla delil
zincirinin manipule edilebildigi gercek bir acik icin eklenmisti, bkz.
docs/roadmap.md '4 uzman ajanla kapsamli inceleme'). Bu suit hem 'delil
kaybi' hem 'sahte kayit enjeksiyonu' senaryolarinin engellendigini
dogrular."""

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
