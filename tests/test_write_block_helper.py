"""write_block_helper.py icin regresyon testleri -- code review'da bulunan
2 gercek hataya karsi (bkz. docs/roadmap.md):

1. getro_out.strip() == "1" katı esitlik kontrolu, get_pty=True (NOPASSWD
   sudo) yolunda sudo/host-resolution uyari satirlarini (orn. "sudo:
   unable to resolve host ...") tolere etmiyordu -- gercekten salt-okunur
   bir diski YANLIS sekilde "degil" gosteriyordu.
2. is_write_blocked(), uzak komutun exit status'unu tamamen atliyordu --
   komut gercekten basarisiz olduysa (blockdev yok/izin yok/disk yolu
   gecersiz) bunu "salt-okunur DEGIL" ile AYNI False sonucuna dusuruyordu,
   oysa fonksiyonun kendi sozlesmesi bu durumda None (kontrol edilemedi)
   vaat ediyor.

Gercek bir SSH sunucusu kurmadan, run_command()'i taklit eden basit bir
FakeSSH nesnesiyle test edilir (image_acquirer.py testlerindeki AYNI
mock SSH yontemi)."""

import pytest

import write_block_helper as wbh


class FakeSSH:
    """write_block_helper._run_blockdev()'in bekledigi run_command(cmd,
    get_pty=False, sudo_password=None) -> (stdout, stderr, exit) arayuzunu
    taklit eder. cmd -> (stdout, stderr, exit) sozlugunden cevap bulur."""

    def __init__(self, responses):
        # responses: {"--setro": (out, err, exit), "--getro": (out, err, exit)}
        self.responses = responses
        self.calls = []

    def run_command(self, cmd, get_pty=False, sudo_password=None):
        self.calls.append(cmd)
        for flag, cevap in self.responses.items():
            if flag in cmd:
                return cevap
        return ("", "", 0)


@pytest.fixture(autouse=True)
def _isolated_logs(isolated_coc_log):
    """Bu dosyadaki testler apply_write_block() araciligiyla coc.log_event()
    cagirir -- gercek log dosyasina hic yazilmasin diye otomatik uygulanir."""
    return isolated_coc_log


# ---------------------------------------------------------------------------
# Hata 1: eslitlik kontrolu sudo/host-resolution uyari satirlarini tolere etmeli
# ---------------------------------------------------------------------------

def test_is_write_blocked_tolerates_sudo_host_resolution_warning():
    """NOPASSWD sudo + /etc/hosts'ta kendi hostname'i eksik hedeflerde
    (adli imaj hedeflerinde YAYGIN), gercek '1' satirindan ONCE bir sudo
    uyarisi basilir -- getro_out TAMAMEN '1' DEGILDIR ama disk GERCEKTEN
    salt-okunurdur."""
    ssh = FakeSSH({
        "--getro": ("sudo: unable to resolve host sunucu: Name or service not known\n1", "", 0),
    })
    assert wbh.is_write_blocked(ssh, "/dev/sdb", password=None) is True


def test_is_write_blocked_tolerates_warning_for_not_readonly_disk():
    """Ayni uyari satiri, disk GERCEKTEN salt-okunur DEGILKEN de dogru
    sekilde False donmeli (sadece '1' durumu degil, '0' durumu da
    korunmali)."""
    ssh = FakeSSH({
        "--getro": ("sudo: unable to resolve host sunucu: Name or service not known\n0", "", 0),
    })
    assert wbh.is_write_blocked(ssh, "/dev/sdb", password=None) is False


def test_apply_write_block_tolerates_sudo_host_resolution_warning(isolated_coc_log):
    """apply_write_block()'un kendi getro dogrulamasi da AYNI toleransi
    gostermeli -- aksi halde basarili bir --setro, basarisiz bir
    dogrulama gibi gorunup EXAM_ERROR'a dusurur."""
    ssh = FakeSSH({
        "--setro": ("", "", 0),
        "--getro": ("sudo: unable to resolve host sunucu: Name or service not known\n1", "", 0),
    })
    assert wbh.apply_write_block(ssh, "/dev/sdb", password=None) is True

    events = isolated_coc_log.read_events()
    assert any(e["event"] == isolated_coc_log.EVENT_WRITE_BLOCK_APPLIED for e in events)
    assert not any(e["event"] == isolated_coc_log.EVENT_EXAM_ERROR for e in events)


# ---------------------------------------------------------------------------
# Hata 2: exit status atlaniyordu -- basarisiz komut False'a degil None'a dusmeli
# ---------------------------------------------------------------------------

def test_is_write_blocked_returns_none_when_remote_command_fails():
    """blockdev PATH'te degil/izin yok/disk yolu artik gecersiz gibi bir
    durumda uzak komut SSH seviyesinde CALISIR ama kendisi basarisiz olur
    (exit != 0), stdout bos ('', None DEGIL) doner. Eskiden bu "".strip()
    == "1" -> False'a dusup 'kontrol edildi, salt-okunur degil' diye
    YANLIS loglaniyordu -- artik None (kontrol edilemedi) donmeli."""
    ssh = FakeSSH({
        "--getro": ("", "blockdev: cannot open /dev/sdc: No such file or directory", 1),
    })
    assert wbh.is_write_blocked(ssh, "/dev/sdc", password=None) is None


def test_is_write_blocked_returns_true_when_exit_zero_and_output_is_one():
    """Mevcut basarili yol (exit=0, temiz '1' ciktisi) BOZULMAMALI."""
    ssh = FakeSSH({"--getro": ("1", "", 0)})
    assert wbh.is_write_blocked(ssh, "/dev/sdb", password=None) is True


def test_is_write_blocked_returns_false_when_exit_zero_and_output_is_zero():
    """Mevcut basarili yol (exit=0, temiz '0' ciktisi) BOZULMAMALI."""
    ssh = FakeSSH({"--getro": ("0", "", 0)})
    assert wbh.is_write_blocked(ssh, "/dev/sdb", password=None) is False


def test_is_write_blocked_returns_none_when_ssh_call_itself_fails():
    """SSH seviyesinde hata (stdout=None) -- mevcut davranis korunmali."""
    ssh = FakeSSH({"--getro": (None, None, None)})
    assert wbh.is_write_blocked(ssh, "/dev/sdb", password=None) is None
