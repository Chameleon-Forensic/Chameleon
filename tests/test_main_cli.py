"""
main.py (SSH motoru CLI'i) genisletmesi -- artik sadece Linux Tam Disk degil,
Windows hedef + Dosya/Klasor + Mantiksal Imaj da destekliyor (kullanici
istegi). Alma mantiginin KENDISI zaten test_image_acquirer_mock_ssh.py /
test_logical_imaging.py'de test edildigi icin, burada SADECE main.py'nin
YENI orkestrasyonu (dogru motor fonksiyonunun dogru argumanlarla cagirilmasi,
menu/OS secimi) test ediliyor -- acquire fonksiyonlari sahte (mock).
"""

import builtins

import pytest

import image_acquirer as ia
import main


@pytest.fixture(autouse=True)
def _isolated(isolated_coc_log, tmp_path, monkeypatch):
    monkeypatch.setattr(ia, "MANIFEST_DIR", str(tmp_path / "manifests"))
    monkeypatch.setattr(ia, "IMAGE_DIR", str(tmp_path / "images"))
    return isolated_coc_log


class _SahteSSH:
    host = "1.2.3.4"
    password = "gizli"

    def list_disks(self):
        return "sdb 10G disk"

    def connect(self):
        return True


def _girdi_sirasi(monkeypatch, *degerler):
    sira = iter(degerler)
    monkeypatch.setattr(builtins, "input", lambda *_a, **_kw: next(sira))


def test_select_target_os_validates_input(monkeypatch):
    _girdi_sirasi(monkeypatch, "x", "1")
    assert main.select_target_os() == "linux"
    _girdi_sirasi(monkeypatch, "2")
    assert main.select_target_os() == "windows"


def test_select_windows_disk_number_validates_int(monkeypatch):
    _girdi_sirasi(monkeypatch, "abc", "3")
    assert main.select_windows_disk_number() == 3


def test_get_ssh_connection_rejects_non_numeric_port_and_retries(monkeypatch):
    """Satir ~36: SSH Port sorusuna sayisal olmayan bir deger girilirse
    (orn. 'abc' ya da bosluklu bir deger) program cokmemeli,
    select_windows_disk_number() ile AYNI desende tekrar sormali."""
    _girdi_sirasi(
        monkeypatch,
        "1.2.3.4",  # host
        "abc",  # gecersiz port (1. deneme)
        "2222",  # gecerli port (2. deneme)
        "root",  # username
        "2",  # auth: SSH Key
        "/home/user/.ssh/id_rsa",  # key_path
    )
    baglanti = main.get_ssh_connection()
    assert baglanti.port == 2222


def test_get_ssh_connection_blank_port_uses_default(monkeypatch):
    _girdi_sirasi(
        monkeypatch,
        "1.2.3.4", "", "root", "2", "/home/user/.ssh/id_rsa",
    )
    baglanti = main.get_ssh_connection()
    assert baglanti.port == 22


def test_parse_lsblk_names_ignores_tree_chars_and_other_columns():
    """Satir ~96: select_disk gercek NAME kolonuna karsi tam eslesme
    yapmali -- SIZE/MODEL/SERIAL kolonlarindaki bir substring ya da
    lsblk'nin agac-cizim karakterleri ('├─', '└─') sahte bir eslesme
    URETMEMELI."""
    disks_output = (
        "NAME   SIZE TYPE FSTYPE MOUNTPOINT MODEL          SERIAL\n"
        "sda     500G disk\n"
        "├─sda1  500M part  vfat   /boot/efi\n"
        "└─sda2  499G part  ext4   /\n"
        "sdb     1T   disk                   Samsung_500GB  ABC123\n"
    )
    isimler = main._parse_lsblk_names(disks_output)
    assert isimler == ["sda", "sda1", "sda2", "sdb"]
    # "500" SIZE kolonunda gecen bir alt string; NAME olarak gecerli DEGIL.
    assert "500" not in isimler
    # "sd" gercek bir NAME'in on eki; tam eslesme olmadan kabul edilmemeli.
    assert "sd" not in isimler


def test_select_disk_rejects_substring_match(monkeypatch, capsys):
    """select_disk, 'sda' ve 'sdb' listelenmisken kisa/kismi bir string
    (orn. 'sd') veya baska bir kolondan gelen bir deger (orn. '500')
    OLMAYAN bir cihazi 'dogrulandi' diye KABUL ETMEMELI."""
    disks_output = "NAME SIZE TYPE\nsda  500G disk\nsdb  1T   disk\n"
    _girdi_sirasi(monkeypatch, "sd", "500", "sdb")
    sonuc = main.select_disk(disks_output)
    assert sonuc == "/dev/sdb"
    cikti = capsys.readouterr().out
    assert "'sd' listede bulunamadi" in cikti
    assert "'500' listede bulunamadi" in cikti


def test_handle_disk_acquisition_linux_calls_linux_engine(monkeypatch, tmp_path):
    yakalanan = {}

    def sahte_acquire(ssh, disk_path, password, **kw):
        yakalanan["disk_path"] = disk_path
        yakalanan["apply_write_blocker"] = kw["apply_write_blocker"]
        return {"total_blocks": 1, "acquired_blocks": [0], "failed_blocks": [], "block_paths": {0: "x"}, "output_dir": str(tmp_path)}

    monkeypatch.setattr(main.image_acquirer, "acquire_disk_image", sahte_acquire)
    monkeypatch.setattr(main.image_acquirer, "concatenate_blocks", lambda *a, **kw: None)
    # imaj_yolu None donunce _finish_disk_acquisition erken cikar, input sorulmaz.
    _girdi_sirasi(monkeypatch, "1", "sdb")  # live/offline, disk

    main.handle_disk_acquisition(_SahteSSH(), "linux")

    assert yakalanan["disk_path"] == "/dev/sdb"
    assert yakalanan["apply_write_blocker"] is False  # "1" = Live


def test_handle_disk_acquisition_windows_calls_windows_engine(monkeypatch, tmp_path):
    yakalanan = {}

    def sahte_acquire(ssh, disk_number, output_dir, **kw):
        yakalanan["disk_number"] = disk_number
        yakalanan["apply_write_blocker"] = kw["apply_write_blocker"]
        return {"total_blocks": 1, "acquired_blocks": [0], "failed_blocks": [], "block_paths": {0: "x"}, "output_dir": str(tmp_path)}

    monkeypatch.setattr(main.windows_acquirer, "acquire_disk_image_windows", sahte_acquire)
    monkeypatch.setattr(main.image_acquirer, "concatenate_blocks", lambda *a, **kw: None)
    _girdi_sirasi(monkeypatch, "2", "0")  # Offline, disk 0

    main.handle_disk_acquisition(_SahteSSH(), "windows")

    assert yakalanan["disk_number"] == 0
    assert yakalanan["apply_write_blocker"] is True  # "2" = Offline


@pytest.mark.parametrize("target_os, logical, beklenen_modul_attr", [
    ("linux", False, "acquire_remote_tree"),
    ("linux", True, "acquire_logical_image"),
    ("windows", False, "acquire_remote_tree_windows"),
    ("windows", True, "acquire_logical_image_windows"),
])
def test_handle_tree_acquisition_dispatches_correct_engine(monkeypatch, tmp_path, capsys, target_os, logical, beklenen_modul_attr):
    yakalanan = {}
    modul = main.file_acquirer if target_os == "linux" else main.windows_acquirer

    def sahte_alici(ssh, remote_path, out_dir, **kw):
        yakalanan["remote_path"] = remote_path
        yakalanan["out_dir"] = out_dir
        return {
            "total_files": 2, "acquired": [{"remote_path": "a", "local_path": "a"}],
            "failed": ["b"], "failed_reasons": {"b": "izin yok"}, "excluded": ["c"],
        }

    monkeypatch.setattr(modul, beklenen_modul_attr, sahte_alici)
    _girdi_sirasi(monkeypatch, "/data/hedef", "")  # yol, cikti (bos -> varsayilan)

    main.handle_tree_acquisition(_SahteSSH(), target_os, logical=logical)

    assert yakalanan["remote_path"] == "/data/hedef"
    cikti = capsys.readouterr().out
    assert "1/2 dosya alindi" in cikti
    assert "izin yok" in cikti
    assert "bilerek alinmadi" in cikti


def test_handle_tree_acquisition_blank_path_is_rejected(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(main.file_acquirer, "acquire_remote_tree", lambda *a, **kw: called.append(1))
    _girdi_sirasi(monkeypatch, "   ")
    main.handle_tree_acquisition(_SahteSSH(), "linux", logical=False)
    assert not called
    assert "bos olamaz" in capsys.readouterr().out
