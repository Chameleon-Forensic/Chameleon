"""
gui_v2.py AcquisitionWorker._run_windows_disk -- "segments" NameError
regresyon testi + Windows kolunda segment akisinin gercekten calismasi.

Bulgular (bkz. docs/code_review_bulgulari.md):
1. Windows disk kolu, Linux kolu ile AYNI birleştirme/hash/log akışını
   kullanıyor ama `segments` değişkenini SADECE Linux kolu tanımlıyordu.
   Windows disk imajı başarıyla bittiğinde NameError fırlatıyordu; geniş
   except Exception bunu yutup sadece traceback logluyordu -- yani rapor
   kaydedilmiyor, "İmaj alma tamamlandı" durumu gösterilmiyordu.
2. Windows kolunda `segment_size_bytes` ctx'e koyulmasına rağmen kol
   içinde HİÇ kontrol edilmiyordu: kullanıcı segment seçse bile sessizce
   tek dosya birleştiriliyordu (Linux'ta çalışan özelliğin Windows'ta
   sessiz kaybı). Artık Linux koluyla birebir aynı segment akışı var.
"""

import gui_v2


def _ctx(**ekstra):
    taban = {
        "case_id": "V-1", "examiner": "inceleyen", "custodian": "emanetci",
        "organization": "org", "conn_method": "direct", "host": "1.2.3.4",
        "display_timezone": "Europe/Istanbul",
        "disk_number": 0, "out_path": "imaj.raw", "mode": "live",
        "block_size_mb": 4, "compress": False, "segment_size_bytes": None,
    }
    taban.update(ekstra)
    return taban


class _SahteSSH:
    def list_disks(self):
        return ""


def _worker(ctx, tmp_path, yakalanan):
    """Ortak kurulum: mock'lar bagli worker dondurur."""
    def _sahte_acquire(*a, **kw):
        return {
            "block_paths": [str(tmp_path / "blok0")], "total_blocks": 1,
            "output_dir": str(tmp_path), "block_size_mb": 4,
            "acquired_blocks": [0], "failed_blocks": [],
        }

    monkeypatchs = yakalanan  # sadece okunabilirlik
    return _sahte_acquire


def test_windows_disk_success_flow_does_not_hit_nameerror(monkeypatch, tmp_path):
    """Windows disk imajı TAM BAŞARIYLA bittiğinde worker NameError'a
    düşmemeli; rapor kaydedilip report_ready yayılmalı."""
    out_path = str(tmp_path / "imaj.raw")
    ctx = _ctx(out_path=out_path)

    with open(out_path, "wb") as f:
        f.write(b"A" * 1024)

    def _sahte_acquire(*a, **kw):
        return {
            "block_paths": [out_path], "total_blocks": 1,
            "output_dir": str(tmp_path), "block_size_mb": 4,
            "acquired_blocks": [0], "failed_blocks": [],
        }

    def _sahte_concat(block_paths, total_blocks, output_dir=None, output_path=None, cleanup=False):
        return output_path

    monkeypatch.setattr(gui_v2, "acquire_disk_image_windows", _sahte_acquire)
    monkeypatch.setattr(gui_v2, "concatenate_blocks", _sahte_concat)
    monkeypatch.setattr(gui_v2, "hash_file_multi", lambda p: {"sha256": "a" * 64, "md5": "b" * 32, "sha1": "c" * 40})
    monkeypatch.setattr(gui_v2, "find_incomplete_manifest", lambda *a, **kw: None)
    monkeypatch.setattr(gui_v2.coc, "log_event", lambda *a, **kw: None)

    worker = gui_v2.AcquisitionWorker("windows_disk", _SahteSSH(), ctx)
    raporlar = []
    worker.report_ready.connect(lambda r, p: raporlar.append((r, p)))
    loglar = []
    worker.log.connect(lambda m, *a: loglar.append(m))
    durumlar = []
    worker.status.connect(lambda m: durumlar.append(m))

    worker.run()

    hatalar = [m for m in loglar if "Beklenmeyen hata" in m]
    assert not hatalar, f"Worker beklenmeyen hataya düştü: {hatalar}"
    assert any("İmaj alma tamamlandı" in m for m in durumlar), \
        f"Başarı akışı tamamlanmalıydı (durumlar: {durumlar})"
    assert raporlar, "Rapor report_ready ile yayılmalıydı"
    assert raporlar[0][0].to_dict()["case"]["case_id"] == "V-1"


def test_windows_disk_with_segments_flow_also_works(monkeypatch, tmp_path):
    """Windows kolunda segment akışı (segment_size_bytes verildiğinde)
    ARTIK gercekten segment uretir -- onceki kodda bu secenek sessizce
    YOK SAYILIYORDU (Linux'ta calisan ozellik Windows'ta kayipti)."""
    ctx = _ctx(out_path=str(tmp_path / "imaj.000"), segment_size_bytes=650 * 1024 * 1024)

    seg1 = tmp_path / "imaj.000"
    seg1.write_bytes(b"B" * 512)

    def _sahte_acquire(*a, **kw):
        return {
            "block_paths": [str(tmp_path / "blok0")], "total_blocks": 1,
            "output_dir": str(tmp_path), "block_size_mb": 4,
            "acquired_blocks": [0], "failed_blocks": [],
        }

    segment_cagrildi = {}

    def _sahte_write_segments(block_paths, total_blocks, seg_bytes, output_dir=None, output_basename=None, cleanup=False):
        segment_cagrildi["evet"] = (block_paths, total_blocks, seg_bytes)
        return [str(seg1)]

    monkeypatch.setattr(gui_v2, "acquire_disk_image_windows", _sahte_acquire)
    monkeypatch.setattr(gui_v2, "write_segments", _sahte_write_segments)
    monkeypatch.setattr(gui_v2, "hash_files_multi", lambda paths: {"sha256": "a" * 64})
    monkeypatch.setattr(gui_v2, "find_incomplete_manifest", lambda *a, **kw: None)
    monkeypatch.setattr(gui_v2.coc, "log_event", lambda *a, **kw: None)
    # compress yolu (compress=False zaten) dokunulmaz; ask_verify yayinini
    # segments dogru zamanda engelliyor.

    worker = gui_v2.AcquisitionWorker("windows_disk", _SahteSSH(), ctx)
    loglar = []
    worker.log.connect(lambda m, *a: loglar.append(m))
    raporlar = []
    worker.report_ready.connect(lambda r, p: raporlar.append((r, p)))

    worker.run()

    assert segment_cagrildi.get("evet"), \
        "segment_size_bytes verildiğinde write_segments ÇAĞRILMALIYDI (eski kodda sessizce atlanıyordu)"
    hatalar = [m for m in loglar if "Beklenmeyen hata" in m]
    assert not hatalar, f"Segmentli akış beklenmeyen hataya düştü: {hatalar}"
    assert any("segmente bölündü" in m for m in loglar), f"Segment logu yok: {loglar[-5:]}"
    assert raporlar, "Segmentli akışta da rapor yayılmalıydı"


def test_windows_disk_segments_none_keeps_concatenate_flow(monkeypatch, tmp_path):
    """segment_size_bytes=None ise (varsayilan) birlestirme akisi aynen
    calismali -- fix mevcut davranisi bozmamali."""
    out_path = str(tmp_path / "imaj.raw")
    ctx = _ctx(out_path=out_path, segment_size_bytes=None)
    with open(out_path, "wb") as f:
        f.write(b"C" * 256)

    concat_cagrildi = {}

    def _sahte_concat(block_paths, total_blocks, output_dir=None, output_path=None, cleanup=False):
        concat_cagrildi["evet"] = output_path
        return output_path

    monkeypatch.setattr(gui_v2, "acquire_disk_image_windows", lambda *a, **kw: {
        "block_paths": [out_path], "total_blocks": 1, "output_dir": str(tmp_path),
        "block_size_mb": 4, "acquired_blocks": [0], "failed_blocks": [],
    })
    monkeypatch.setattr(gui_v2, "concatenate_blocks", _sahte_concat)
    monkeypatch.setattr(gui_v2, "hash_file_multi", lambda p: {"sha256": "d" * 64})
    monkeypatch.setattr(gui_v2, "find_incomplete_manifest", lambda *a, **kw: None)
    monkeypatch.setattr(gui_v2.coc, "log_event", lambda *a, **kw: None)

    worker = gui_v2.AcquisitionWorker("windows_disk", _SahteSSH(), ctx)
    worker.run()
    assert concat_cagrildi.get("evet") == out_path, "Varsayilan akis birlestirme olmali"
