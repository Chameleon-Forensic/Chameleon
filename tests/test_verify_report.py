"""verify_report.py icin testler -- ozellikle YENI eklenen segmentli
(.001/.002/...) imaj destegi (bkz. image_acquirer.write_segments())."""

import gzip
import hashlib
import json

import verify_report as vr


def _write_report(path, output_path, image_hash):
    report = {
        "case": {"case_id": "VAKA-TEST"},
        "result": {"output_path": output_path},
        "integrity": {"image_hash": image_hash},
    }
    path.write_text(json.dumps(report), encoding="utf-8")


def test_find_segments_detects_sibling_segments(tmp_path):
    (tmp_path / "image.001").write_bytes(b"a")
    (tmp_path / "image.002").write_bytes(b"b")
    (tmp_path / "image.003").write_bytes(b"c")

    segments = vr._find_segments(str(tmp_path / "image.001"))
    assert segments == [
        str(tmp_path / "image.001"), str(tmp_path / "image.002"), str(tmp_path / "image.003"),
    ]


def test_find_segments_returns_none_for_single_file(tmp_path):
    single = tmp_path / "image.dd"
    single.write_bytes(b"x")
    assert vr._find_segments(str(single)) is None


def test_find_segments_returns_none_for_lone_numbered_file(tmp_path):
    """Sadece TEK bir '.001' varsa (kardes segment yoksa) segmentli
    sayilmamali -- baska bir amacla '.001' uzantili tek bir dosya olabilir."""
    (tmp_path / "image.001").write_bytes(b"a")
    assert vr._find_segments(str(tmp_path / "image.001")) is None


def test_check_image_hash_succeeds_for_matching_segments(tmp_path):
    (tmp_path / "image.001").write_bytes(b"parca-bir-")
    (tmp_path / "image.002").write_bytes(b"parca-iki")
    combined_hash = hashlib.sha256(b"parca-bir-parca-iki").hexdigest()

    report_path = tmp_path / "report.json"
    _write_report(report_path, str(tmp_path / "image.001"), combined_hash)

    assert vr.check_image_hash(str(report_path)) is True


def test_check_image_hash_fails_for_tampered_segment(tmp_path):
    (tmp_path / "image.001").write_bytes(b"parca-bir-")
    (tmp_path / "image.002").write_bytes(b"DEGISTIRILDI")
    combined_hash = hashlib.sha256(b"parca-bir-parca-iki").hexdigest()  # ORIJINAL hash

    report_path = tmp_path / "report.json"
    _write_report(report_path, str(tmp_path / "image.001"), combined_hash)

    assert vr.check_image_hash(str(report_path)) is False


def test_check_image_hash_segmented_invalid_expected_hash_does_not_raise(tmp_path):
    """Bozuk/kurcalanmis bir report.json'daki image_hash 64 hex karakter
    degilse, compare_digests() -> InvalidDigestError (HashError alt sinifi)
    yakalanmali, traceback ile cokmemeli."""
    (tmp_path / "image.001").write_bytes(b"a")
    (tmp_path / "image.002").write_bytes(b"b")

    report_path = tmp_path / "report.json"
    _write_report(report_path, str(tmp_path / "image.001"), "gecersiz-hash")

    assert vr.check_image_hash(str(report_path)) is False


def test_check_image_hash_gzip_invalid_expected_hash_does_not_raise(tmp_path):
    img_path = tmp_path / "image.dd.gz"
    with gzip.open(img_path, "wb") as f:
        f.write(b"veri")

    report_path = tmp_path / "report.json"
    _write_report(report_path, str(img_path), "gecersiz-hash")

    assert vr.check_image_hash(str(report_path)) is False


def test_check_image_hash_truncated_gzip_does_not_raise(tmp_path):
    """Yarida kesilmis bir transfer sonucu kirpilmis bir .gz dosyasi,
    gzip modulunde EOFError firlatir -- bu araci ozellikle bu senaryoyu
    ('bozuk delil') traceback vermeden [HATA] ile bildirmeli."""
    img_path = tmp_path / "image.dd.gz"
    icerik = b"x" * 10000
    with gzip.open(img_path, "wb") as f:
        f.write(icerik)

    data = img_path.read_bytes()
    img_path.write_bytes(data[: len(data) - 50])  # akisi kirp, gecersiz gzip

    combined_hash = hashlib.sha256(icerik).hexdigest()
    report_path = tmp_path / "report.json"
    _write_report(report_path, str(img_path), combined_hash)

    assert vr.check_image_hash(str(report_path)) is False


def test_check_report_integrity_blank_sidecar_does_not_raise(tmp_path):
    """report.json.sha256 sidecar'i VAR ama bos/sadece bosluk ise (kopyalama
    sirasinda kirpilmis ya da disk dolu yazim), split()[0] IndexError
    firlatmamali -- anlamli bir [HATA] mesajiyla False donmeli."""
    report_path = tmp_path / "report.json"
    report_path.write_text("{}", encoding="utf-8")
    sidecar_path = tmp_path / "report.json.sha256"
    sidecar_path.write_text("   \n", encoding="utf-8")

    assert vr.check_report_integrity(str(report_path)) is False


def test_check_image_hash_segmented_reports_progress(tmp_path, monkeypatch):
    """Segmentli imaj yolu da (tek-dosya yolu gibi) _print_progress'i
    hash_files_multi()'ye iletmeli -- uzun suren bir dogrulamada kullanici
    ilerleme gormeli."""
    (tmp_path / "image.001").write_bytes(b"parca-bir-")
    (tmp_path / "image.002").write_bytes(b"parca-iki")
    combined_hash = hashlib.sha256(b"parca-bir-parca-iki").hexdigest()

    report_path = tmp_path / "report.json"
    _write_report(report_path, str(tmp_path / "image.001"), combined_hash)

    orijinal = vr.hash_files_multi
    yakalanan = {}

    def sarmalayici(paths, **kwargs):
        yakalanan["progress"] = kwargs.get("progress")
        return orijinal(paths, **kwargs)

    monkeypatch.setattr(vr, "hash_files_multi", sarmalayici)

    assert vr.check_image_hash(str(report_path)) is True
    assert yakalanan["progress"] is vr._print_progress
