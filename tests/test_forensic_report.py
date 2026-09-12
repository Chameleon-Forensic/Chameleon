"""forensic_report.py icin testler: ForensicReport.to_dict()/save()'in
report.json/report.html/sidecar .sha256 uretmesi, Vaka Gecmisi (read_history)
+ etiket (read_tags/set_tag) kalicilıği, ve YENI eklenen export_pdf()'in
gercekten bir PDF uretip Turkce karakterleri dogru gomdugu (bkz.
docs/hatalar_ve_sonuclar.md -- reportlab'in yerlesik fontlari Turkce'ye
ozgu karakterleri desteklemiyordu, Inter.ttf'e gecilerek duzeltildi)."""

import hashlib
import json
import os

import pytest

import forensic_report as fr


def _build_sample_report():
    report = fr.ForensicReport(
        case_id="VAKA-TEST", examiner="Test İnceleyen", organization="Test Kurumu",
        custodian="Test Yetkili",
    )
    report.start(
        engine="ssh_engine", method="disk", target_os="linux", target_host="10.0.0.5",
        source_identifier="/dev/sdb", acquisition_type="full_disk",
        connection_method="direct",
    )
    report.set_write_blocking(True, "Offline acquisition")
    report.finish(
        status="success", output_path="C:/tmp/image.dd", image_hash="a" * 64,
        total_bytes=1024, chunk_size_bytes=4194304, chunk_count=1,
        md5_hash="b" * 32, sha1_hash="c" * 40,
    )
    return report


def test_to_dict_preserves_case_and_integrity_fields():
    report = _build_sample_report()
    d = report.to_dict()
    assert d["case"]["case_id"] == "VAKA-TEST"
    assert d["integrity"]["image_hash"] == "a" * 64
    assert d["integrity"]["md5_hash"] == "b" * 32
    assert d["result"]["status"] == "success"


def test_finish_uses_precomputed_md5_sha1_without_rereading_file(tmp_path):
    """Performans regresyonu: md5_hash/sha1_hash verildiyse, output_path
    HIC diskte olmasa bile finish() dosyayi okumaya CALISMAMALI (ikinci
    I/O gecisini onlemek asil amac, bkz. docs/hatalar_ve_sonuclar.md)."""
    report = fr.ForensicReport()
    report.start(engine="ssh_engine", method="disk")
    report.finish(
        status="success", output_path=str(tmp_path / "hic-olmayan-dosya.dd"),
        md5_hash="d" * 32, sha1_hash="e" * 40,
    )
    assert report.md5_hash == "d" * 32
    assert report.sha1_hash == "e" * 40


def test_save_writes_json_html_and_sha256_sidecar(tmp_path, isolated_coc_log, isolated_history):
    report = _build_sample_report()
    report.save(str(tmp_path))

    json_path = tmp_path / "report.json"
    html_path = tmp_path / "report.html"
    sha_path = tmp_path / "report.json.sha256"
    assert json_path.is_file()
    assert html_path.is_file()
    assert sha_path.is_file()

    raw = json_path.read_bytes()
    expected_hash = hashlib.sha256(raw).hexdigest()
    assert expected_hash in sha_path.read_text(encoding="utf-8")

    html_content = html_path.read_text(encoding="utf-8")
    assert "VAKA-TEST" in html_content


def test_save_appends_to_case_history_and_read_history_returns_newest_first(
    tmp_path, isolated_history, isolated_coc_log,
):
    r1 = _build_sample_report()
    r1.case_id = "VAKA-001"
    r1.save(str(tmp_path / "r1"))

    r2 = _build_sample_report()
    r2.case_id = "VAKA-002"
    r2.save(str(tmp_path / "r2"))

    history = fr.read_history()
    assert len(history) == 2
    assert history[0]["case_id"] == "VAKA-002"  # en yeni once
    assert history[1]["case_id"] == "VAKA-001"


def test_save_called_twice_for_same_report_path_updates_not_duplicates(
    tmp_path, isolated_history, isolated_coc_log,
):
    """set_verification() sonrasi save() TEKRAR cagrildiginda (gercek
    GUI akisi) Vaka Gecmisi'nde AYNI kayit ikinci kez EKLENMEMELI."""
    report = _build_sample_report()
    report.save(str(tmp_path))
    report.set_verification(True)
    report.save(str(tmp_path))

    history = fr.read_history()
    assert len(history) == 1
    assert history[0]["case_id"] == "VAKA-TEST"


def test_set_tag_and_read_tags_round_trip(isolated_history):
    fr.set_tag("C:/tmp/report1.json", "takip gerekiyor")
    tags = fr.read_tags()
    assert tags["C:/tmp/report1.json"] == "takip gerekiyor"


def test_set_tag_with_empty_text_removes_existing_tag(isolated_history):
    fr.set_tag("C:/tmp/report1.json", "gecici")
    assert fr.read_tags()["C:/tmp/report1.json"] == "gecici"
    fr.set_tag("C:/tmp/report1.json", "")
    assert "C:/tmp/report1.json" not in fr.read_tags()


def test_read_tags_returns_empty_dict_when_file_missing(isolated_history):
    assert fr.read_tags() == {}


def test_export_pdf_produces_file_with_turkish_characters(tmp_path):
    """Regresyon: reportlab'in yerlesik Helvetica fontu Turkce'ye ozgu
    karakterleri (İ ş ı ğ ç) render edemiyordu (siyah kutu), Inter.ttf'e
    gecilerek duzeltildi -- bkz. docs/hatalar_ve_sonuclar.md."""
    sample = {
        "tool": {"name": "Chameleon", "version": "0.1.0", "engine": "ssh_engine", "method": "disk"},
        "case": {"case_id": "VAKA-TEST", "examiner": "İnceleyen Şükrü", "organization": "", "custodian": ""},
        "acquisition": {
            "target_os": "linux", "target_host": "10.0.0.5", "source_identifier": "/dev/sdb",
            "acquisition_type": "full_disk", "connection_method": "direct",
            "start_time_utc": "2026-01-01T10:00:00Z", "end_time_utc": "2026-01-01T10:05:00Z",
            "write_blocking_applied": True, "write_blocking_reason": "Offline",
        },
        "integrity": {
            "hash_algorithm": "SHA-256", "image_hash": "abc", "md5_hash": "def", "sha1_hash": "ghi",
            "total_bytes": 100, "chunk_size_bytes": 4, "chunk_count": 1,
        },
        "result": {"status": "success", "output_path": "C:/tmp/img.dd", "failed_items": []},
        "verification": {"verified": True, "verified_at_utc": "2026-01-01T10:06:00Z", "hash_match": True},
        "chain_of_custody": {"log_file": "C:/tmp/coc.log", "events": []},
    }
    json_path = tmp_path / "report.json"
    pdf_path = tmp_path / "report.pdf"
    json_path.write_text(json.dumps(sample), encoding="utf-8")

    fr.export_pdf(str(json_path), str(pdf_path))

    assert pdf_path.is_file()
    assert pdf_path.stat().st_size > 1000
    # gercek bir PDF dosyasi %PDF ile baslar
    assert pdf_path.read_bytes()[:4] == b"%PDF"


def test_export_pdf_raises_for_missing_report(tmp_path):
    with pytest.raises(FileNotFoundError):
        fr.export_pdf(str(tmp_path / "yok.json"), str(tmp_path / "out.pdf"))
