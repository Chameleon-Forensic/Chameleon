"""
image_acquirer.py'nin en kritik yolunu (blok blok alma -> hash
dogrulama -> diske yazma -> birlestirme -> master hash) GERCEK bir SSH
sunucusu kurmadan uctan uca test eder. CONTRIBUTING.md'de belgelenen
"run_command/exec_command taklit eden mock SSH nesnesi" yontemi burada
ILK KEZ kalici bir test dosyasina donusturuluyor -- daha once her oturumda
ayni sekilde ELLE yazilip atiliyordu.

MockSSHClient, kucuk bir "sahte disk" (bytes) tutar; blockdev/lsblk/dd/
sha256sum komutlarini gercek cikti bicimleriyle taklit eder.
"""

import hashlib
import re

import pytest

import image_acquirer as ia
from hash_verifier import HashMismatchError


class _MockStdout:
    def __init__(self, data, exit_status=0):
        self._data = data
        self.channel = _MockChannel(exit_status)

    def read(self):
        return self._data


class _MockChannel:
    def __init__(self, exit_status):
        self._exit_status = exit_status

    def recv_exit_status(self):
        return self._exit_status


class _MockStdin:
    def write(self, _data):
        pass

    def flush(self):
        pass


class _MockStderr:
    def read(self):
        return b""


class MockSSHClient:
    """image_acquirer.py'nin bekledigi ssh_connector.SSHConnector arayuzunu
    (run_command/client.exec_command/is_active/reconnect) taklit eder."""

    def __init__(self, disk_bytes):
        self.disk_bytes = disk_bytes
        self._active = True
        self.client = self  # ssh.client.exec_command -- kendisi "client"
        self.write_blocked = False
        self.fail_setro = False
        self.reconnect_succeeds = True
        # block_no -> bu blok icin dondurulecek YANLIS hash (bir kere)
        self.bad_hash_once = {}
        # is_write_blocked() cagrisinin ne donecegini kontrol eder: None ->
        # normal (write_blocked bayragina gore "1"/"0"), "FORCE_NONE" -> SSH
        # hatasi taklidi (bkz. windows_acquirer.py testlerindeki AYNI desen).
        self.readonly_check_mode = None

    # -- ssh_connector.SSHConnector arayuzu --
    def is_active(self):
        return self._active

    def reconnect(self):
        if self.reconnect_succeeds:
            self._active = True
            return True
        return False

    def run_command(self, cmd, sudo_password=None, get_pty=False):
        if "--getsize64" in cmd:
            return (str(len(self.disk_bytes)), "", 0)
        if "--setro" in cmd:
            if self.fail_setro:
                return (None, "blockdev: hata", 1)
            self.write_blocked = True
            return ("", "", 0)
        if "--getro" in cmd:
            if self.readonly_check_mode == "FORCE_NONE":
                return (None, "ssh baglanti hatasi", None)
            return ("1" if self.write_blocked else "0", "", 0)
        if "lsblk" in cmd:
            return ('MODEL="MockDisk" SERIAL="TEST123"', "", 0)
        if "sha256sum" in cmd:
            block_no, block_size_mb = self._parse_dd(cmd)
            if block_no in self.bad_hash_once:
                # bir kereye mahsus BOZUK hash dondur -- retry mekanizmasini test eder
                wrong = self.bad_hash_once.pop(block_no)
                return (f"{wrong}  -\n", "", 0)
            data = self._read_block(block_no, block_size_mb)
            digest = hashlib.sha256(data).hexdigest()
            return (f"{digest}  -\n", "", 0)
        return ("", "", 0)

    def exec_command(self, cmd, get_pty=False):
        block_no, block_size_mb = self._parse_dd(cmd)
        data = self._read_block(block_no, block_size_mb)
        return _MockStdin(), _MockStdout(data), _MockStderr()

    def _parse_dd(self, cmd):
        bs_match = re.search(r"bs=(\d+)M", cmd)
        skip_match = re.search(r"skip=(\d+)", cmd)
        return int(skip_match.group(1)), int(bs_match.group(1))

    def _read_block(self, block_no, block_size_mb):
        block_bytes = block_size_mb * 1024 * 1024
        start = block_no * block_bytes
        return self.disk_bytes[start:start + block_bytes]


@pytest.fixture
def fake_disk():
    """3 blok x 1 MB = 3 MB, her blok ayirt edilebilir icerikte."""
    block = 1024 * 1024
    return bytes([0]) * block + bytes([1]) * block + bytes([2]) * block


@pytest.fixture(autouse=True)
def _isolated_logs(isolated_coc_log):
    """Bu dosyadaki HER test coc.log_event() cagirir -- gercek log
    dosyasina hic yazilmasin diye otomatik uygulanir."""
    return isolated_coc_log


def test_full_acquisition_round_trips_to_identical_bytes(tmp_path, fake_disk):
    ssh = MockSSHClient(fake_disk)
    result = ia.acquire_disk_image(
        ssh, "/dev/fake0", password=None, output_dir=str(tmp_path),
        block_size_mb=1, apply_write_blocker=True,
    )
    assert result is not None
    assert result["total_blocks"] == 3
    assert result["acquired_blocks"] == [0, 1, 2]
    assert result["failed_blocks"] == []
    assert ssh.write_blocked is True

    output_path = tmp_path / "image.dd"
    ia.concatenate_blocks(
        result["block_paths"], result["total_blocks"],
        output_dir=str(tmp_path), output_path=str(output_path), cleanup=False,
    )
    assert output_path.read_bytes() == fake_disk
    assert ia.local_master_hash(str(output_path)) == hashlib.sha256(fake_disk).hexdigest()


def test_write_segments_splits_across_segment_boundary_correctly(tmp_path, fake_disk):
    """3 MB'lik sahte diski 1.2 MB'lik segmentlere boler -- blok sinirlari
    (1 MB) segment sinirlariyla (1.2 MB) ORTUSMUYOR, tam da bu yuzden
    kritik: bir blok iki segmente BOLUNMELI ve hicbir bayt kaybolmamali/
    tekrarlanmamali."""
    ssh = MockSSHClient(fake_disk)
    result = ia.acquire_disk_image(
        ssh, "/dev/fake0", password=None, output_dir=str(tmp_path),
        block_size_mb=1, apply_write_blocker=True,
    )
    segment_size = int(1.2 * 1024 * 1024)
    segments = ia.write_segments(
        result["block_paths"], result["total_blocks"], segment_size,
        output_dir=str(tmp_path), output_basename="parcali", cleanup=False,
    )
    assert segments is not None
    assert len(segments) == 3  # ceil(3MB / 1.2MB) = 3

    yeniden_birlesik = b"".join(open(s, "rb").read() for s in segments)
    assert yeniden_birlesik == fake_disk, "segmentler sirayla birlestirilince orijinal veriyle BIREBIR ayni olmali"

    from hash_verifier import hash_files_multi
    master = hash_files_multi(segments, algorithms=("sha256",))["sha256"]
    assert master == hashlib.sha256(fake_disk).hexdigest()


def test_write_segments_returns_none_for_missing_blocks(tmp_path, fake_disk):
    ssh = MockSSHClient(fake_disk)
    result = ia.acquire_disk_image(
        ssh, "/dev/fake0", password=None, output_dir=str(tmp_path),
        block_size_mb=1, apply_write_blocker=True,
    )
    eksik_block_paths = dict(result["block_paths"])
    del eksik_block_paths[1]
    segments = ia.write_segments(
        eksik_block_paths, result["total_blocks"], 1024 * 1024,
        output_dir=str(tmp_path), output_basename="eksik", cleanup=False,
    )
    assert segments is None


def test_write_block_failure_aborts_before_reading_any_block(tmp_path, fake_disk):
    ssh = MockSSHClient(fake_disk)
    ssh.fail_setro = True
    result = ia.acquire_disk_image(
        ssh, "/dev/fake0", password=None, output_dir=str(tmp_path),
        block_size_mb=1, apply_write_blocker=True,
    )
    assert result is None, "write-block basarisizsa islem hic BASLAMAMALI"
    assert list(tmp_path.glob("block_*.dd")) == [], "hicbir blok diske yazilmamis olmali"


def test_hash_mismatch_triggers_retry_then_succeeds(tmp_path, fake_disk):
    """Bozuk/degistirilmis bir blok hash'i, veri diske YAZILMADAN once
    reddedilip yeniden istenmeli -- verify_chunk() bu korumayi saglar."""
    ssh = MockSSHClient(fake_disk)
    ssh.bad_hash_once[1] = "f" * 64  # blok 1 icin ilk denemede YANLIS hash
    result = ia.acquire_disk_image(
        ssh, "/dev/fake0", password=None, output_dir=str(tmp_path),
        block_size_mb=1, apply_write_blocker=True,
    )
    assert result["acquired_blocks"] == [0, 1, 2]
    assert result["failed_blocks"] == []

    output_path = tmp_path / "image.dd"
    ia.concatenate_blocks(
        result["block_paths"], result["total_blocks"],
        output_dir=str(tmp_path), output_path=str(output_path), cleanup=False,
    )
    assert output_path.read_bytes() == fake_disk, "yeniden denenen blok SONUNDA dogru veriyle yazilmali"


def test_connection_drop_returns_resume_point_without_losing_progress(
    tmp_path, fake_disk, monkeypatch,
):
    """Baglanti kopup bir daha gelmezse, islem durur ve 'resume_from' ile
    kaldigi yerden devam edilebilecek bir durum dondurmeli -- o ana kadar
    basariyla alinan bloklar KAYBOLMAMALI. Baglanti, blok 1'in hash'i
    ALINDIKTAN SONRA (ensure_connection() sadece her BLOGUN basinda
    kontrol edildigi icin) kopar -- bu yuzden blok 1 yine de tamamlanir,
    kopma ancak blok 2'nin basinda fark edilir."""
    monkeypatch.setattr(ia.time, "sleep", lambda _s: None)  # 1+2+4sn gercek bekleme yok

    ssh = MockSSHClient(fake_disk)

    original_run_command = ssh.run_command
    call_count = {"n": 0}

    def flaky_run_command(cmd, sudo_password=None, get_pty=False):
        if "sha256sum" in cmd:
            call_count["n"] += 1
            if call_count["n"] > 1:  # blok 0 basarili, blok 1'in hash'inden SONRA baglanti kopuyor
                ssh._active = False
        return original_run_command(cmd, sudo_password=sudo_password, get_pty=get_pty)

    ssh.run_command = flaky_run_command
    ssh.reconnect_succeeds = False  # yeniden baglanma da basarisiz -- gercekci en kotu senaryo

    result = ia.acquire_disk_image(
        ssh, "/dev/fake0", password=None, output_dir=str(tmp_path),
        block_size_mb=1, apply_write_blocker=True,
    )

    assert "resume_from" in result
    assert result["acquired_blocks"] == [0, 1], "kopmadan ONCE alinan bloklar KAYBOLMAMALI"


def test_should_stop_halts_cleanly_and_marks_user_stopped(tmp_path, fake_disk):
    """Kullanici 'Durdur' butonuna bastiginda (should_stop True donunce),
    baglanti koptugundaki ile AYNI 'resume_from' seklinde durmali ama
    ayrica 'user_stopped': True tasimali -- GUI bunu 'baglanti koptu,
    tekrar baglanilsin mi?' diye SORMAMASI icin kullanir."""
    ssh = MockSSHClient(fake_disk)
    cagri_sayisi = [0]

    def should_stop():
        # ilk cagri (block_no=0'dan once): henuz durma. ikinci cagri
        # (block_no=1'den once): dur -- boylece blok 0 tamamlanmis olmali.
        cagri_sayisi[0] += 1
        return cagri_sayisi[0] > 1

    result = ia.acquire_disk_image(
        ssh, "/dev/fake0", password=None, output_dir=str(tmp_path),
        block_size_mb=1, apply_write_blocker=True, should_stop=should_stop,
    )

    assert result["user_stopped"] is True
    assert "resume_from" in result
    assert result["acquired_blocks"] == [0], "durdurulmadan ONCE alinan blok KAYBOLMAMALI"
    assert result["resume_from"] == 1

    # ayni cagriyi start_block=resume_from ile tekrarlarsak (baglanti
    # bu sefer duzgun calisirken) kalan bloklar tamamlanabilmeli
    ssh2 = MockSSHClient(fake_disk)
    result2 = ia.acquire_disk_image(
        ssh2, "/dev/fake0", password=None, output_dir=str(tmp_path),
        block_size_mb=1, apply_write_blocker=False, start_block=result["resume_from"],
        resume_state=result, manifest_path=result["manifest_path"],
    )
    assert result2["acquired_blocks"] == [0, 1, 2]


# ---------------------------------------------------------------------------
# Hata: baglanti koptu/durduruldu erken-donus sozluklerinde started_at_utc
# eksikti -- windows_acquirer.py'de bu oturumda AYNI hata duzeltildi,
# burada da (image_acquirer.py, Linux tarafi) ayni eksiklik vardi (bkz.
# docs/roadmap.md, docs/kararlar.md).
# ---------------------------------------------------------------------------

def test_user_stopped_return_dict_includes_started_at_utc(tmp_path, fake_disk):
    ssh = MockSSHClient(fake_disk)
    result = ia.acquire_disk_image(
        ssh, "/dev/fake0", password=None, output_dir=str(tmp_path),
        block_size_mb=1, apply_write_blocker=True, should_stop=lambda: True,
    )
    assert result["user_stopped"] is True
    assert "started_at_utc" in result and result["started_at_utc"]


def test_connection_lost_return_dict_includes_started_at_utc(tmp_path, fake_disk):
    ssh = MockSSHClient(fake_disk)
    ssh._active = False
    ssh.reconnect_succeeds = False  # yeniden baglanma basarisiz -- hemen durur

    result = ia.acquire_disk_image(
        ssh, "/dev/fake0", password=None, output_dir=str(tmp_path),
        block_size_mb=1, apply_write_blocker=True,
    )
    assert "resume_from" in result
    assert "started_at_utc" in result and result["started_at_utc"]


def test_started_at_utc_preserved_across_successive_early_returns(tmp_path, fake_disk):
    """Duzeltmeden once: erken donus sozluklerinde started_at_utc HIC
    olmadigi icin, bu sozluk dogrudan bir sonraki cagriya resume_state
    olarak verildiginde YENI bir zaman damgasi uretilirdi. Simdi: ilk
    cagridan donen started_at_utc, ikinci (resume) cagriya AYNEN gecmeli."""
    ssh1 = MockSSHClient(fake_disk)
    ilk = ia.acquire_disk_image(
        ssh1, "/dev/fake0", password=None, output_dir=str(tmp_path),
        block_size_mb=1, apply_write_blocker=True, should_stop=lambda: True,
    )
    assert ilk["started_at_utc"]

    ssh2 = MockSSHClient(fake_disk)
    ssh2.write_blocked = True
    ikinci = ia.acquire_disk_image(
        ssh2, "/dev/fake0", password=None, output_dir=str(tmp_path),
        block_size_mb=1, start_block=ilk["resume_from"], resume_state=ilk,
        manifest_path=ilk["manifest_path"], should_stop=lambda: True,
    )
    assert ikinci["started_at_utc"] == ilk["started_at_utc"], (
        "resume sirasinda ORIJINAL baslangic zamani KORUNMALI, "
        "yeni bir zaman damgasi uretilmemeli"
    )


# ---------------------------------------------------------------------------
# Hata: resume sirasinda is_write_blocked() None (SSH hatasi) donerse delil
# zincirine hicbir kayit girmiyordu -- windows_acquirer.py'de bu oturumda
# duzeltilen AYNI eksiklik Linux tarafinda da vardi.
# ---------------------------------------------------------------------------

def test_resume_write_block_check_none_logs_exam_error(tmp_path, fake_disk, isolated_coc_log):
    ssh = MockSSHClient(fake_disk)
    ssh.readonly_check_mode = "FORCE_NONE"  # is_write_blocked() None donsun

    resume_state = {
        "acquired_blocks": [0],
        "failed_blocks": [],
        "block_paths": {"0": str(tmp_path / "block_000000.dd")},
        "started_at_utc": "2020-01-01T00:00:00Z",
    }
    ia.acquire_disk_image(
        ssh, "/dev/fake0", password=None, output_dir=str(tmp_path),
        block_size_mb=1, total_blocks=3, start_block=1, resume_state=resume_state,
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

    ssh_true = MockSSHClient(fake_disk)
    ssh_true.write_blocked = True
    ia.acquire_disk_image(
        ssh_true, "/dev/fake0", password=None, output_dir=str(tmp_path),
        block_size_mb=1, total_blocks=3, start_block=1, resume_state=dict(resume_state),
        manifest_path=str(tmp_path / "m1.json"), should_stop=lambda: True,
    )
    events = isolated_coc_log.read_events(isolated_coc_log.get_log_file_path())
    assert any(e["event"] == isolated_coc_log.EVENT_WRITE_BLOCK_APPLIED for e in events)

    ssh_false = MockSSHClient(fake_disk)
    ssh_false.write_blocked = False
    ia.acquire_disk_image(
        ssh_false, "/dev/fake0", password=None, output_dir=str(tmp_path),
        block_size_mb=1, total_blocks=3, start_block=1, resume_state=dict(resume_state),
        manifest_path=str(tmp_path / "m2.json"), should_stop=lambda: True,
    )
    events = isolated_coc_log.read_events(isolated_coc_log.get_log_file_path())
    assert any(e["event"] == isolated_coc_log.EVENT_WRITE_BLOCK_SKIPPED for e in events)
