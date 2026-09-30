"""hash_verifier.py icin birim testleri -- ozellikle hash_file_multi()
(TEK gecişte SHA-256+MD5+SHA-1), cunku bu, buyuk bir imajda cift I/O'yu
onleyen performans duzeltmesinin dogrulugunu garanti eden tek yer."""

import hashlib

import pytest

import hash_verifier as hv


@pytest.fixture
def sample_file(tmp_path):
    path = tmp_path / "ornek.bin"
    data = b"Chameleon test verisi -- Turkce karakterler: \xc4\xb0\xc5\x9f\xc4\x9f" * 1000
    path.write_bytes(data)
    return path, data


def test_hash_file_multi_matches_hashlib_reference(sample_file):
    path, data = sample_file
    result = hv.hash_file_multi(path, algorithms=("sha256", "md5", "sha1"))
    assert result["sha256"] == hashlib.sha256(data).hexdigest()
    assert result["md5"] == hashlib.md5(data).hexdigest()
    assert result["sha1"] == hashlib.sha1(data).hexdigest()


def test_hash_file_multi_single_algorithm(sample_file):
    path, data = sample_file
    result = hv.hash_file_multi(path, algorithms=("sha256",))
    assert set(result.keys()) == {"sha256"}
    assert result["sha256"] == hashlib.sha256(data).hexdigest()


def test_hash_file_multi_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        hv.hash_file_multi(tmp_path / "yok.bin")


def test_hash_file_multi_reports_progress(sample_file):
    path, data = sample_file
    calls = []
    hv.hash_file_multi(path, algorithms=("sha256",), progress=lambda done, total: calls.append((done, total)))
    assert calls, "progress callback hic cagrilmadi"
    assert calls[-1][0] == calls[-1][1] == len(data)


def test_compare_digests_case_insensitive():
    digest_upper = "AB" * 32
    digest_lower = "ab" * 32
    assert hv.compare_digests(digest_upper, digest_lower)
    assert not hv.compare_digests("a" * 64, "b" * 64)


def test_parse_sha256sum_output():
    # gercek `sha256sum` ciktisi: "<hash>  -" ya da "<hash>  dosyaadi"
    digest = "a" * 64
    assert hv.parse_sha256sum_output(f"{digest}  -\n") == digest
    assert hv.parse_sha256sum_output(f"{digest}  /tmp/x.bin\n") == digest


def test_normalize_digest_rejects_wrong_length():
    with pytest.raises(hv.InvalidDigestError):
        hv.normalize_digest("kisadeger")


def test_hash_files_multi_matches_single_file_hash(tmp_path, sample_file):
    """Segmentli bir imajin (birden fazla kucuk dosya) SIRAYLA okunarak
    hesaplanan hash'i, AYNI icerigin TEK bir dosyada oldugu durumdaki
    hash ile BIREBIR AYNI olmali -- write_segments()'in delil butunlugunu
    bozmadigini garanti eden temel varsayim budur."""
    _whole_path, data = sample_file

    seg1 = tmp_path / "parca.001"
    seg2 = tmp_path / "parca.002"
    orta = len(data) // 2
    seg1.write_bytes(data[:orta])
    seg2.write_bytes(data[orta:])

    result = hv.hash_files_multi([seg1, seg2], algorithms=("sha256", "md5"))
    assert result["sha256"] == hashlib.sha256(data).hexdigest()
    assert result["md5"] == hashlib.md5(data).hexdigest()


def test_hash_files_multi_missing_segment_raises(tmp_path):
    (tmp_path / "parca.001").write_bytes(b"veri")
    with pytest.raises(FileNotFoundError):
        hv.hash_files_multi([tmp_path / "parca.001", tmp_path / "parca.002"])


def test_verify_image_against_manifest_all_matched(sample_file):
    path, data = sample_file
    chunk_size = 1024
    expected = {}
    for i in range(0, len(data), chunk_size):
        block = data[i : i + chunk_size]
        expected[i // chunk_size] = hashlib.sha256(block).hexdigest()

    report = hv.verify_image_against_manifest(path, expected, chunk_size=chunk_size)
    assert report.ok
    assert not report.mismatched
    assert not report.missing
    assert not report.unexpected
    assert not report.malformed
    assert report.master.digest == hashlib.sha256(data).hexdigest()


def test_verify_image_against_manifest_malformed_entries_dont_raise(sample_file):
    """Yarim kalan/bozuk bir manifest'te gecersiz indeks (int'e cevrilemeyen)
    ya da gecersiz ozet (yanlis uzunlukta hex) iceren girdiler, fonksiyonun
    kendi sozlestigi gibi (docstring: 'hata FIRLATMAZ') hic exception
    firlatmadan report.malformed'a kaydedilmeli, dogrulama calismaya devam
    etmeli."""
    path, data = sample_file
    chunk_size = 1024
    expected = {
        "gecersiz-indeks": hashlib.sha256(b"x").hexdigest(),
        0: "kisa-ve-gecersiz-ozet",
    }

    report = hv.verify_image_against_manifest(path, expected, chunk_size=chunk_size)

    assert not report.ok
    assert len(report.malformed) == 2
    # Gecersiz girdiler normalized_expected'e hic girmedigi icin gercek 0.
    # blok, hicbir beklenen ozetle eslesmeyip "unexpected" olarak raporlanir.
    assert any(item["index"] == 0 for item in report.unexpected)


def test_verify_image_against_manifest_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        hv.verify_image_against_manifest(tmp_path / "yok.bin", {})
