"""
file_acquirer.py icin regresyon testleri -- high-effort code review'da
bulunan 4 gercek hataya karsi (bkz. docs/roadmap.md, docs/kararlar.md):

1. Girilemeyen (execute izni olmayan) bir alt dizin, `find -xdev -type f`
   tarafindan hic gorulemedigi icin altindaki dosyalar hicbir kayit
   birakmadan sessizce eksik kaliyordu -- ne alinan listesine, ne
   failed_reasons'a, ne de bir log kaydina giriyordu.
2. Resume, resume_state'teki "acquired_files"a koru korune guveniyordu --
   yerel cikti dosyasinin hala var olup olmadigi hic kontrol edilmiyordu
   (bkz. tests/test_logical_imaging.py'deki ayri regresyon testi).
3. Bir dosya MAX_RETRY_PER_BLOCK tukenip KALICI olarak basarisiz olunca,
   o ana kadar diske yazilmis YARIM/DOGRULANMAMIS veri local_path'te
   KALICI olarak kaliyordu -- hicbir cagiran onu silmiyordu.
4. _acquire_raw_file_block(), dogrudan ssh.client.exec_command() kullanip
   SADECE stdout okuyordu, stderr HIC bosaltilmiyordu -- klasik bir
   paramiko kanal kilitlenme riski.

Yontem: diger dosyalardaki (test_image_acquirer_mock_ssh.py,
test_ssh_connector.py) ile AYNI -- run_command/exec_command taklit eden
kucuk bir sahte SSH nesnesi, gercek bir sunucu kurmadan.
"""

import hashlib
import os
import re

import pytest

import file_acquirer as fa
import image_acquirer as ia


# ---------------------------------------------------------------------------
# Ortak yardimcilar
# ---------------------------------------------------------------------------

def _parse_dd(cmd):
    bs_match = re.search(r"bs=(\d+)M", cmd)
    skip_match = re.search(r"skip=(\d+)", cmd)
    return int(skip_match.group(1)), int(bs_match.group(1))


def _is_inaccessible_dirs_cmd(cmd):
    return "-type d" in cmd and "! -readable" in cmd and "! -executable" in cmd


class _NullIO:
    def write(self, *_a, **_k):
        pass

    def flush(self):
        pass

    def read(self):
        return b""


@pytest.fixture(autouse=True)
def _isolated_logs(isolated_coc_log):
    """Bu dosyadaki testler coc.log_event() tetikleyebilir -- gercek log
    dosyasina hic yazilmasin diye otomatik uygulanir."""
    return isolated_coc_log


# ---------------------------------------------------------------------------
# Hata #1: girilemeyen dizinler artik iz birakiyor
# ---------------------------------------------------------------------------

class _DirListingSSH:
    """list_remote_files/list_logical_files'in kullandigi `find` komutlarini
    taklit eder. Gercekci senaryo: /data altinda /data/gizli GIRILEMEYEN
    (execute izni yok) bir dizin -- gercek `find` onun ICINE inemeyecegi
    icin /data/gizli/inner.txt hic listede cikmaz, sadece /data/gizli'nin
    KENDISI "-type d ! -readable -o ! -executable" taramasinda gorunur."""

    ACIK_ICERIK = b"merhaba"

    def __init__(self):
        self.client = self
        self._active = True

    def is_active(self):
        return self._active

    def reconnect(self):
        self._active = True
        return True

    def run_command(self, cmd, sudo_password=None, get_pty=False):
        if cmd.startswith("test -f"):
            return ("DIR\n", "", 0)  # remote_path_kind: /data bir klasor
        if _is_inaccessible_dirs_cmd(cmd):
            return ("/data/gizli\n", "", 0)
        if "-type f ! -readable" in cmd:
            return ("", "", 0)
        if cmd.startswith("find ") and "-type f" in cmd:
            # gercek find'in gorebildigi -- /data/gizli/inner.txt YOK
            return ("/data/acik.txt\n", "", 0)
        if cmd.startswith("stat -c%s"):
            return (str(len(self.ACIK_ICERIK)), "", 0)
        if "sha256sum" in cmd:
            return (f"{hashlib.sha256(self.ACIK_ICERIK).hexdigest()}  -\n", "", 0)
        return ("", "", 0)

    def exec_command(self, cmd, get_pty=False):
        return _NullIO(), _RawOut(self.ACIK_ICERIK), _NullIO()


def test_list_remote_files_logs_inaccessible_directory_instead_of_silent_gap(isolated_coc_log):
    """Duzeltmeden once: /data/gizli hicbir yerde gorunmuyordu -- ne
    donen listede ne bir log kaydinda. Simdi en azindan delil zincirine
    EXAM_ERROR olarak iz birakmali."""
    ssh = _DirListingSSH()
    dosyalar = fa.list_remote_files(ssh, "/data")

    assert dosyalar == ["/data/acik.txt"]

    events = isolated_coc_log.read_events(isolated_coc_log.get_log_file_path())
    eslesen = [
        e for e in events
        if e["event"] == isolated_coc_log.EVENT_EXAM_ERROR and "/data/gizli" in e["description"]
    ]
    assert eslesen, (
        "girilemeyen dizin en azindan delil zincirine loglanmali -- "
        "onceden HICBIR iz birakmiyordu"
    )
    assert "girilemedi" in eslesen[0]["description"]


def test_list_logical_files_reports_inaccessible_directory_in_failed_reasons():
    """Mantiksal imaj modunda ayni sorun manifest'e de (failed_reasons)
    islenmeli -- sadece loglanmakla kalmamali, acquire_remote_tree'nin
    ozet manifest_files.json'una da yazilabilsin diye."""
    ssh = _DirListingSSH()
    dosyalar, onceden_basarisiz, dislanan = fa.list_logical_files(ssh, "/data")

    assert dosyalar == ["/data/acik.txt"]
    assert onceden_basarisiz.get("/data/gizli") == "dizine girilemedi (izin yok)"
    assert dislanan == {}


def test_logical_acquisition_end_to_end_surfaces_inaccessible_dir_in_manifest(tmp_path):
    """acquire_logical_image uctan uca: /data/gizli hem failed_reasons'da
    hem toplam dosya sayisinda gorunmeli, sessizce kaybolmamali."""
    ssh = _DirListingSSH()
    manifest = fa.acquire_logical_image(ssh, "/data", str(tmp_path / "out"))

    assert manifest["failed_reasons"].get("/data/gizli") == "dizine girilemedi (izin yok)"
    assert "/data/gizli" in manifest["failed"]
    # acik.txt basariyla alinmis olmali (mock'un dd/sha256sum ciktisi
    # vermedigi icin burada sadece varligini/failed listesinde OLMADIGINI
    # dogruluyoruz).
    assert "/data/acik.txt" not in manifest["failed"]


# ---------------------------------------------------------------------------
# Hata #3: kalici basarisizlikta yarim dosya diskte birakilmiyor
# ---------------------------------------------------------------------------

class _BlockAcquireSSH:
    """acquire_remote_file'in tam blok+dogrulama akisini taklit eder.
    `bad_blocks` icindeki blok numaralari icin sha256sum HER ZAMAN yanlis
    bir hash dondurur -- gercek veriyle asla eslesmez, bu yuzden
    MAX_RETRY_PER_BLOCK tukenip KALICI basarisizliga yol acar (orn. dosya
    ortasinda izin iptal edilmesi senaryosu)."""

    def __init__(self, data, bad_blocks=()):
        self.data = data
        self.bad_blocks = set(bad_blocks)
        self.client = self
        self._active = True

    def is_active(self):
        return self._active

    def reconnect(self):
        self._active = True
        return True

    def _block(self, block_no, block_size_mb):
        b = block_size_mb * 1024 * 1024
        return self.data[block_no * b:(block_no + 1) * b]

    def run_command(self, cmd, sudo_password=None, get_pty=False):
        if cmd.startswith("stat -c%s"):
            return (str(len(self.data)), "", 0)
        if "sha256sum" in cmd:
            block_no, block_size_mb = _parse_dd(cmd)
            if block_no in self.bad_blocks:
                return ("0" * 64 + "  -\n", "", 0)  # asla eslesmeyecek sahte hash
            digest = hashlib.sha256(self._block(block_no, block_size_mb)).hexdigest()
            return (f"{digest}  -\n", "", 0)
        return ("", "", 0)

    def exec_command(self, cmd, get_pty=False):
        block_no, block_size_mb = _parse_dd(cmd)
        return _NullIO(), _RawOut(self._block(block_no, block_size_mb)), _NullIO()


class _RawOut:
    def __init__(self, data):
        self._data = data
        self.channel = self

    def read(self):
        return self._data

    def recv_exit_status(self):
        return 0


def test_permanently_failed_block_removes_half_written_local_file(tmp_path):
    """Hata #3: 3 bloklu bir dosyanin 0/1. bloklari basarili yazilir,
    2. blok (orn. izin iptali) KALICI olarak basarisiz olur -- diskte
    yarim/dogrulanmamis bir dosya KALMAMALI."""
    block = 1024 * 1024
    veri = bytes([1]) * block + bytes([2]) * block + bytes([3]) * block
    ssh = _BlockAcquireSSH(veri, bad_blocks={2})

    local_path = str(tmp_path / "cikti" / "dosya.bin")
    basarili, hash_deger = fa.acquire_remote_file(
        ssh, "/uzak/dosya.bin", local_path, block_size_mb=1,
    )

    assert basarili is False
    assert hash_deger is None
    assert not os.path.exists(local_path), (
        "kalici basarisizlikta diskte yarim/dogrulanmamis bir dosya "
        "KALMAMALI -- manifest'te hic kaydi olmayan boyle bir dosya "
        "gercek delil sanilabilir"
    )


def test_successful_acquisition_still_leaves_verified_file_on_disk(tmp_path):
    """Duzeltmenin normal (basarili) yolu bozmadigini dogrular."""
    block = 1024 * 1024
    veri = bytes([9]) * block * 2
    ssh = _BlockAcquireSSH(veri)

    local_path = str(tmp_path / "cikti" / "dosya.bin")
    basarili, hash_deger = fa.acquire_remote_file(
        ssh, "/uzak/dosya.bin", local_path, block_size_mb=1,
    )

    assert basarili is True
    assert hash_deger == hashlib.sha256(veri).hexdigest()
    assert os.path.exists(local_path)
    assert open(local_path, "rb").read() == veri


def test_connection_drop_mid_file_also_removes_half_written_file(tmp_path, monkeypatch):
    """Hata #3'un ikinci kalici-basarisizlik yolu: ensure_connection()
    basarisiz olursa (baglanti bir daha gelmezse) da ayni temizlik
    uygulanmali."""
    monkeypatch.setattr(ia.time, "sleep", lambda _s: None)  # gercek bekleme yok

    block = 1024 * 1024
    veri = bytes([5]) * block * 3
    ssh = _BlockAcquireSSH(veri)

    gercek_sha256sum = ssh.run_command
    cagri = {"n": 0}

    def flaky_run_command(cmd, sudo_password=None, get_pty=False):
        if "sha256sum" in cmd:
            cagri["n"] += 1
            if cagri["n"] > 1:  # 1. blok basarili, 2. blogun basinda baglanti kopuyor
                ssh._active = False
        return gercek_sha256sum(cmd, sudo_password=sudo_password, get_pty=get_pty)

    ssh.run_command = flaky_run_command
    ssh.reconnect = lambda: False  # yeniden baglanma da basarisiz

    local_path = str(tmp_path / "cikti" / "dosya.bin")
    basarili, hash_deger = fa.acquire_remote_file(
        ssh, "/uzak/dosya.bin", local_path, block_size_mb=1,
    )

    assert basarili is False
    assert hash_deger is None
    assert not os.path.exists(local_path)


# ---------------------------------------------------------------------------
# Hata #4: _acquire_raw_file_block artik stderr'i bosaltiyor (kilitlenme onlenir)
# ---------------------------------------------------------------------------

class _DeadlockProneChannel:
    """Gercek paramiko Channel'in _acquire_raw_file_block() icin ilgili
    davranisini taklit eder: recv_exit_status(), stdout VE stderr
    TAMAMEN okunmadan cagirilirsa -- gercek paramiko'da uzak `dd`/`sudo`
    stderr'e kanalin flow-control penceresini asacak kadar yazarsa
    SONSUZA KADAR blokeye yol acacagi icin -- burada deterministik bir
    AssertionError'a cevirir (bkz. tests/test_ssh_connector.py'deki AYNI
    desen, run_command() icin)."""

    def __init__(self):
        self.stdout_read_done = False
        self.stderr_read_done = False

    def recv_exit_status(self):
        if not (self.stdout_read_done and self.stderr_read_done):
            raise AssertionError(
                "recv_exit_status() stdout/stderr TAMAMEN okunmadan once "
                "cagirildi -- gercek paramiko'da stderr'e yazan bir dd/sudo "
                "SONSUZA KADAR bloke olurdu (kanal kilitlenmesi)."
            )
        return 0


class _DeadlockProneStream:
    def __init__(self, data, channel, mark_done):
        self._data = data
        self.channel = channel
        self._mark_done = mark_done

    def read(self):
        self._mark_done()
        return self._data


class _DeadlockProneSSH:
    """_acquire_raw_file_block'un dogrudan kullandigi ssh.client.exec_command()
    arayuzunu taklit eder -- run_command()'dan BAGIMSIZ bir kod yolu
    oldugu icin ssh_connector.py'deki duzeltmeden HIC etkilenmez, ayrica
    test edilmesi gerekiyordu."""

    def __init__(self, stdout_data, stderr_data):
        self.client = self
        self.channel = _DeadlockProneChannel()
        self.stdout_data = stdout_data
        self.stderr_data = stderr_data

    def exec_command(self, cmd, get_pty=False):
        def mark_stdout():
            self.channel.stdout_read_done = True

        def mark_stderr():
            self.channel.stderr_read_done = True

        stdout = _DeadlockProneStream(self.stdout_data, self.channel, mark_stdout)
        stderr = _DeadlockProneStream(self.stderr_data, self.channel, mark_stderr)
        return _NullIO(), stdout, stderr


def test_acquire_raw_file_block_drains_stderr_before_exit_status():
    """Duzeltmeden once: stderr hic okunmuyordu -- gercek paramiko'da bu
    kanal kilitlenmesine yol acardi; bu sahte kanalda ise
    recv_exit_status() AssertionError firlatirdi, fonksiyonun kendi genel
    except'i bunu yutup SESSIZCE None donerdi (basarili bir blok bile
    basarisiz gibi gorunurdu). Duzeltmeden sonra stderr once bosaltilir,
    gercek veri sorunsuzca donmeli."""
    beklenen_veri = b"X" * (1024 * 1024)
    ssh = _DeadlockProneSSH(beklenen_veri, b"dd: bazi bilgi mesaji\n")

    sonuc = fa._acquire_raw_file_block(ssh, "/uzak/dosya.bin", 0, 1, password=None)

    assert sonuc == beklenen_veri, (
        "stderr bosaltilmadan recv_exit_status() cagirilirsa "
        "AssertionError yutulup None donerdi -- regresyon burada yakalanir"
    )
    assert ssh.channel.stdout_read_done is True
    assert ssh.channel.stderr_read_done is True


def test_acquire_raw_file_block_with_sudo_also_drains_stderr():
    """sudo yolunda (password verilmisse) da AYNI korumanin gecerli
    oldugunu dogrular."""
    beklenen_veri = b"Y" * (1024 * 1024)
    ssh = _DeadlockProneSSH(beklenen_veri, b"")

    sonuc = fa._acquire_raw_file_block(ssh, "/uzak/dosya.bin", 0, 1, password="gizli-parola")

    assert sonuc == beklenen_veri
    assert ssh.channel.stderr_read_done is True
