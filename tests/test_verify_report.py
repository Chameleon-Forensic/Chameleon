"""verify_report.py icin testler -- ozellikle YENI eklenen segmentli
(.001/.002/...) imaj destegi (bkz. image_acquirer.write_segments())."""

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
