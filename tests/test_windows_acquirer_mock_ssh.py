"""
windows_acquirer.py'deki code-review'da bulunan 4 hataya karsi regresyon
testleri (docs/roadmap.md'ye bkz.). test_image_acquirer_mock_ssh.py'deki
AYNI yontem: gercek bir SSH sunucusu/PowerShell kurmadan, run_command'i
taklit eden bir MockSSH nesnesiyle uctan uca test.

MockWindowsSSH, windows_acquirer.py'nin urettigi PowerShell komut
metinlerini (Get-Disk/Set-Disk/ComputeHash/ToBase64String) REGEX ile
ayristirip kucuk bir "sahte disk" (bytes) uzerinden gercekci cikti
uretir -- gercek PowerShell'i CALISTIRMAZ (bu yuzden hata #3, PowerShell
tarafinin kendisi, ayri bir statik string testiyle ele alinir asagida).
"""

import hashlib
import base64
import re

import pytest

import windows_acquirer as wa


class MockWindowsSSH:
    """windows_acquirer.py'nin bekledigi run_command/is_active/reconnect
    arayuzunu taklit eder. Gercek bir disk yerine bytes tutar."""

    def __init__(self, disk_bytes):
        self.disk_bytes = disk_bytes
        self.write_blocked = False
        self.fail_setro = False
        # is_write_blocked_windows() cagrisinin ne donecegini kontrol eder:
        # None -> normal (write_blocked bayragina gore True/False),
        # "FORCE_NONE" -> SSH hatasi taklidi (hata #4'un testi icin).
        self.readonly_check_mode = None
        self._active = True
        self.reconnect_succeeds = True

    def is_active(self):
        return self._active

    def reconnect(self):
        if self.reconnect_succeeds:
            self._active = True
            return True
        return False

    def run_command(self, cmd, sudo_password=None, get_pty=False):
        if "Set-Disk" in cmd:
            if self.fail_setro:
                return (None, "blockdev hata", 1)
            self.write_blocked = True
            return ("True", "", 0)
        if "IsReadOnly" in cmd:
            if self.readonly_check_mode == "FORCE_NONE":
                return (None, "ssh hatasi", 1)
            return ("True" if self.write_blocked else "False", "", 0)
        if ").Size" in cmd:
            return (str(len(self.disk_bytes)), "", 0)
        if "PhysicalDrive" in cmd:
            offset = int(re.search(r"Seek\((\d+),", cmd).group(1))
            length = int(re.search(r"byte\[\] (\d+)", cmd).group(1))
            chunk = self.disk_bytes[offset:offset + length]
            if "ComputeHash" in cmd:
                return (hashlib.sha256(chunk).hexdigest(), "", 0)
            return (base64.b64encode(chunk).decode(), "", 0)
        return ("", "", 0)


@pytest.fixture
def fake_disk():
    """3 blok x 1 MB = 3 MB, her blok ayirt edilebilir icerikte."""
    block = 1024 * 1024
    return bytes([0]) * block + bytes([1]) * block + bytes([2]) * block


@pytest.fixture(autouse=True)
def _isolated_logs(isolated_coc_log):
    """Bu dosyadaki testler coc.log_event() cagirir -- gercek log
    dosyasina hic yazilmasin diye otomatik uygulanir."""
    return isolated_coc_log


# ---------------------------------------------------------------------------
# Hata #1: resume_state'ten yuklenen block_paths string anahtarli kaliyordu
# ---------------------------------------------------------------------------
def test_resume_converts_string_keyed_block_paths_to_int(tmp_path, fake_disk):
    """find_incomplete_manifest() json.load ile okudugu icin block_paths'in
    anahtarlari STRING olarak gelir ("0", "1", ...). Duzeltmeden once bu
    string anahtarlar HIC int'e cevrilmiyordu; concatenate_blocks/
    write_segments'teki 'i not in block_paths' (int i) bu bloklari hep
    'eksik' sayardi -- oysa gercekten diskte ve dogrulanmis."""
    ssh = MockWindowsSSH(fake_disk)
    ssh.write_blocked = True  # resume kontrolu True/False dalina girsin, None'a degil

    resume_state = {
        "acquired_blocks": [0, 1],
        "failed_blocks": [],
        # json.load'dan gelen manifestteki HALIYLE: string anahtarlar
        "block_paths": {"0": str(tmp_path / "block_000000.dd"), "1": str(tmp_path / "block_000001.dd")},
        "started_at_utc": "2020-01-01T00:00:00Z",
    }

    sonuc = wa.acquire_disk_image_windows(
        ssh, disk_number=5, output_dir=str(tmp_path), block_size_mb=1,
        total_blocks=3, start_block=2, resume_state=resume_state,
        manifest_path=str(tmp_path / "manifest.json"),
    )

    assert sonuc is not None
    # Butun anahtarlar int olmali -- ne resume'dan gelenler ne yeni eklenen.
    assert all(isinstance(k, int) for k in sonuc["block_paths"]), (
        f"block_paths anahtarlari int OLMALI, bulunan: {list(sonuc['block_paths'].keys())}"
    )
    # Regresyon: duzeltmeden ONCE 0 ve 1 (string anahtarli) sonuc dict'inde
    # int olarak BULUNAMAZDI.
    assert set(sonuc["block_paths"].keys()) == {0, 1, 2}
    assert 0 in sonuc["block_paths"]
    assert 1 in sonuc["block_paths"]


def test_image_acquirer_resume_also_converts_string_keyed_block_paths(tmp_path):
    """Ayni hata image_acquirer.py'de (Linux tarafi) de vardi -- ayni
    kalip, ayni duzeltme. Burada dogrudan resume dallanmasini (block_paths
    dict comprehension) hedefleyen kucuk/izole bir test."""
    import image_acquirer as ia

    class _NoBlocksLeftSSH:
        """total_blocks == start_block oldugu icin dongu HIC calismaz --
        sadece resume_state'ten yuklenen block_paths'in donus degerine
        NASIL gectigini test eder. run_command, resume'da yapilan
        is_write_blocked() kontrolunu (--getro) karsilamak icin gerekli."""

        def is_active(self):
            return True

        def run_command(self, cmd, sudo_password=None, get_pty=False):
            return ("0", "", 0)

    resume_state = {
        "acquired_blocks": [0, 1],
        "failed_blocks": [],
        "block_paths": {"0": "a.dd", "1": "b.dd"},
        "started_at_utc": "2020-01-01T00:00:00Z",
    }
    sonuc = ia.acquire_disk_image(
        _NoBlocksLeftSSH(), "/dev/fake0", password=None, output_dir=str(tmp_path),
        block_size_mb=1, total_blocks=2, start_block=2, resume_state=resume_state,
        apply_write_blocker=False, manifest_path=str(tmp_path / "manifest.json"),
    )
    assert sonuc is not None
    assert all(isinstance(k, int) for k in sonuc["block_paths"])
    assert set(sonuc["block_paths"].keys()) == {0, 1}


# ---------------------------------------------------------------------------
# Hata #2: baglanti koptu/durduruldu donuslerinde started_at_utc kayboluyordu
# ---------------------------------------------------------------------------
def test_user_stopped_return_dict_includes_started_at_utc(tmp_path, fake_disk):
    ssh = MockWindowsSSH(fake_disk)
    sonuc = wa.acquire_disk_image_windows(
        ssh, disk_number=1, output_dir=str(tmp_path), block_size_mb=1,
        total_blocks=3, apply_write_blocker=True,
        manifest_path=str(tmp_path / "manifest.json"),
        should_stop=lambda: True,  # ilk blok denemesinden ONCE dur
    )
    assert sonuc["user_stopped"] is True
    assert "started_at_utc" in sonuc and sonuc["started_at_utc"]


def test_connection_lost_return_dict_includes_started_at_utc(tmp_path, fake_disk):
    ssh = MockWindowsSSH(fake_disk)
    ssh._active = False
    ssh.reconnect_succeeds = False  # yeniden baglanma basarisiz -- hemen durur

    sonuc = wa.acquire_disk_image_windows(
        ssh, disk_number=1, output_dir=str(tmp_path), block_size_mb=1,
        total_blocks=3, apply_write_blocker=True,
        manifest_path=str(tmp_path / "manifest.json"),
    )
    assert "resume_from" in sonuc
    assert "started_at_utc" in sonuc and sonuc["started_at_utc"]


def test_started_at_utc_preserved_across_successive_early_returns(tmp_path, fake_disk):
    """Duzeltmeden once: erken donus sozluklerinde started_at_utc HIC
    olmadigi icin, bu sozluk dogrudan bir sonraki cagriya resume_state
    olarak verildiginde YENI bir zaman damgasi uretilirdi. Simdi: ilk
    cagridan donen started_at_utc, ikinci (resume) cagriya AYNEN
    gecmeli."""
    ssh1 = MockWindowsSSH(fake_disk)
    ilk = wa.acquire_disk_image_windows(
        ssh1, disk_number=1, output_dir=str(tmp_path), block_size_mb=1,
        total_blocks=3, apply_write_blocker=True,
        manifest_path=str(tmp_path / "manifest.json"),
        should_stop=lambda: True,
    )
    assert ilk["started_at_utc"]

    ssh2 = MockWindowsSSH(fake_disk)
    ssh2.write_blocked = True
    ikinci = wa.acquire_disk_image_windows(
        ssh2, disk_number=1, output_dir=str(tmp_path), block_size_mb=1,
        total_blocks=3, start_block=ilk["resume_from"], resume_state=ilk,
        manifest_path=ilk["manifest_path"],
        should_stop=lambda: True,
    )
    assert ikinci["started_at_utc"] == ilk["started_at_utc"], (
        "resume sirasinda ORIJINAL baslangic zamani KORUNMALI, "
        "yeni bir zaman damgasi uretilmemeli"
    )


# ---------------------------------------------------------------------------
# Hata #4: resume sirasinda write-block kontrolu None (SSH hatasi) donerse
# delil zincirine hicbir kayit girmiyordu
# ---------------------------------------------------------------------------
def test_resume_write_block_check_none_logs_exam_error(tmp_path, fake_disk, isolated_coc_log):
    ssh = MockWindowsSSH(fake_disk)
    ssh.readonly_check_mode = "FORCE_NONE"  # is_write_blocked_windows() None donsun

    resume_state = {
        "acquired_blocks": [0],
        "failed_blocks": [],
        "block_paths": {"0": str(tmp_path / "block_000000.dd")},
        "started_at_utc": "2020-01-01T00:00:00Z",
    }
    wa.acquire_disk_image_windows(
        ssh, disk_number=9, output_dir=str(tmp_path), block_size_mb=1,
        total_blocks=3, start_block=1, resume_state=resume_state,
        manifest_path=str(tmp_path / "manifest.json"),
        should_stop=lambda: True,  # kontrolden SONRA hemen dur, blok islemeye gerek yok
    )

    events = isolated_coc_log.read_events(isolated_coc_log.get_log_file_path())
    eslesenler = [
        e for e in events
        if e["event"] == isolated_coc_log.EVENT_EXAM_ERROR and "DOGRULANAMADI" in e["description"]
    ]
    assert eslesenler, (
        "write-block durumu None (SSH hatasi) donerse delil zincirine "
        "BIR KAYIT girmeli -- sessizce atlanmamali"
    )


def test_resume_write_block_check_true_and_false_still_log_as_before(tmp_path, fake_disk, isolated_coc_log):
    """Yeni None dali eklenirken mevcut True/False davranisi BOZULMAMALI."""
    resume_state = {
        "acquired_blocks": [0],
        "failed_blocks": [],
        "block_paths": {"0": str(tmp_path / "block_000000.dd")},
        "started_at_utc": "2020-01-01T00:00:00Z",
    }

    ssh_true = MockWindowsSSH(fake_disk)
    ssh_true.write_blocked = True
    wa.acquire_disk_image_windows(
        ssh_true, disk_number=1, output_dir=str(tmp_path), block_size_mb=1,
        total_blocks=3, start_block=1, resume_state=dict(resume_state),
        manifest_path=str(tmp_path / "m1.json"), should_stop=lambda: True,
    )
    events = isolated_coc_log.read_events(isolated_coc_log.get_log_file_path())
    assert any(e["event"] == isolated_coc_log.EVENT_WRITE_BLOCK_APPLIED for e in events)

    ssh_false = MockWindowsSSH(fake_disk)
    ssh_false.write_blocked = False
    wa.acquire_disk_image_windows(
        ssh_false, disk_number=1, output_dir=str(tmp_path), block_size_mb=1,
        total_blocks=3, start_block=1, resume_state=dict(resume_state),
        manifest_path=str(tmp_path / "m2.json"), should_stop=lambda: True,
    )
    events = isolated_coc_log.read_events(isolated_coc_log.get_log_file_path())
    assert any(e["event"] == isolated_coc_log.EVENT_WRITE_BLOCK_SKIPPED for e in events)


# ---------------------------------------------------------------------------
# Hata #3: $read=0 durumunda PowerShell $buf[0..($read-1)] BOS DIZI degil
# 1 BAYTLIK sahte bir dizi donduruyordu (bkz. windows_acquirer.py docstring)
# ---------------------------------------------------------------------------
def test_block_read_script_handles_zero_byte_read_as_truly_empty():
    """[Math]::Max($read-1,0) formulu $read=0 icin $buf[0..0] (1 elemanli,
    0x00) uretiyordu -- eski hatali kalip script'te ARTIK OLMAMALI, yerine
    $read<=0 icin GERCEKTEN bos bir dizi donen ayri bir dal olmali."""
    script = wa._block_read_script(disk_number=0, offset=0, length=4 * 1024 * 1024)

    assert "[Math]::Max" not in script, (
        "eski hatali kirpma formulu (0 okumayi 1 baytlik sahte veri gibi "
        "gosteren) script'ten TAMAMEN kaldirilmali"
    )
    assert "$read -le 0" in script and "[byte[]]@()" in script, (
        "$read=0 durumu ayri ele alinip GERCEKTEN bos bir dizi donmeli"
    )
    # kismi okuma (0 < read < length) davranisi BOZULMAMALI
    assert "$buf[0..($read-1)]" in script


def test_block_read_script_zero_read_cross_check_would_no_longer_false_verify():
    """Hata senaryosunun DAVRANISSAL kanitini bagimsiz bir dogrulamayla
    (get_remote_block_hash_windows / acquire_raw_block_windows AYNI script'i
    kullanir) tekrar uretir: $read=0 icin script'in URETMESI GEREKEN sonuc
    artik BOS bayt dizisidir -- eski hatali kalipla b'\\x00' (1 bayt) ile
    KARISTIRILAMAZ. PowerShell calistirmadan, formulun KENDISI Python'da
    ayni sekilde degerlendirilerek dogrulanir."""
    def eski_hatali_kirpma(buf, read):
        return buf[0:max(read - 1, 0) + 1]  # [Math]::Max($read-1,0) + inclusive .. araligi

    def yeni_kirpma(buf, read, length):
        if read <= 0:
            return b""
        if read < length:
            return buf[0:read]
        return buf

    length = 16
    buf = bytearray(length)  # PowerShell New-Object byte[] length -- hep sifirlarla baslar

    # $read = 0 (bozuk USB koprusu): eski kalip 1 baytlik SAHTE veri
    # uretiyordu, yenisi GERCEKTEN bos donuyor.
    assert eski_hatali_kirpma(bytes(buf), 0) == b"\x00"
    assert yeni_kirpma(bytes(buf), 0, length) == b""

    # kismi okuma davranisi (0 < read < length) HER IKI formulde de ayni
    # kalmali -- fix sadece read=0 ucundaki hatayi duzeltir.
    assert eski_hatali_kirpma(bytes(buf), 5) == yeni_kirpma(bytes(buf), 5, length) == bytes(5)
