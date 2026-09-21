"""
Yerel mod ("Bu bilgisayar", SSH yok) testleri -- local_connector.py.

Gercek fiziksel diske (\\\\.\\PhysicalDriveN) okumak yonetici yetkisi ister;
testler bunun yerine cihaz yolunu sıradan bir dosyaya yonlendirir (okuma
mantigi -- ofset, kirpma, eksik okuma -- ayni kod). PowerShell tarafi
(Get-Disk/Get-Partition) ise GERCEK PowerShell ile calisir. Windows disinda atlanir.
"""

import hashlib
import os
import sys

import pytest

import image_acquirer as ia
import local_connector as lc
import windows_acquirer as wa

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows/PowerShell gerektirir")


@pytest.fixture(autouse=True)
def _isolated(isolated_coc_log, tmp_path, monkeypatch):
    monkeypatch.setattr(ia, "MANIFEST_DIR", str(tmp_path / "manifests"))
    return isolated_coc_log


@pytest.fixture
def fake_disk(tmp_path, monkeypatch):
    """5.5 MB'lik sahte 'disk' -- 1 MB'lik bloklarla 6 blok, sonuncusu yarim."""
    veri = os.urandom(5 * 1024 * 1024 + 512 * 1024)
    yol = tmp_path / "disk.bin"
    yol.write_bytes(veri)
    monkeypatch.setattr(lc, "disk_device_path", lambda n: str(yol))
    ssh = lc.LocalConnector()
    ssh.disk_sizes[7] = len(veri)
    return ssh, veri


def test_run_command_executes_real_powershell():
    ssh = lc.LocalConnector()
    out, _err, code = ssh.run_command("'merhaba ' + (1+2)")
    assert code == 0 and out.strip() == "merhaba 3"


def test_read_local_block_returns_exact_slice_and_clips_last_block(fake_disk):
    ssh, veri = fake_disk
    assert lc.read_local_block(ssh, 7, 0, 1) == veri[:1024 * 1024]
    assert lc.read_local_block(ssh, 7, 2, 1) == veri[2 * 1024 * 1024:3 * 1024 * 1024]
    son = lc.read_local_block(ssh, 7, 5, 1)
    assert son == veri[5 * 1024 * 1024:], "son blok diskin sonuna gore kirpilmali"
    assert lc.read_local_block(ssh, 7, 6, 1) is None, "diskin disindaki blok istenirse None"


def test_read_local_block_missing_device_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(lc, "disk_device_path", lambda n: str(tmp_path / "yok.bin"))
    ssh = lc.LocalConnector()
    ssh.disk_sizes[1] = 1024
    assert lc.read_local_block(ssh, 1, 0, 1) is None


def test_full_disk_image_locally_matches_source_byte_for_byte(fake_disk, tmp_path):
    """Mevcut acquire_disk_image_windows + concatenate_blocks, LocalConnector
    ile DEGISMEDEN calisir ve kaynakla birebir ayni imaji uretir."""
    ssh, veri = fake_disk
    cikti = tmp_path / "out"
    sonuc = wa.acquire_disk_image_windows(
        ssh, 7, output_dir=str(cikti), block_size_mb=1, apply_write_blocker=False,
        total_blocks=6,
    )
    assert sonuc is not None and not sonuc["failed_blocks"]
    assert len(sonuc["acquired_blocks"]) == 6

    imaj = ia.concatenate_blocks(
        sonuc["block_paths"], sonuc["total_blocks"],
        output_dir=str(cikti), output_path=str(cikti / "imaj.dd"), cleanup=True,
    )
    assert hashlib.sha256(open(imaj, "rb").read()).hexdigest() == hashlib.sha256(veri).hexdigest()


def test_list_disks_and_system_disk_with_real_powershell():
    ssh = lc.LocalConnector()
    sistem = lc.system_disk_number(ssh)
    assert isinstance(sistem, int)
    liste = ssh.list_disks()
    assert f"Disk {sistem}:" in liste and "SİSTEM DİSKİ" in liste


def test_output_on_source_disk_is_refused(monkeypatch):
    diskler = {"C": 0, "D": 1}
    monkeypatch.setattr(lc, "_disk_number_for_letter", lambda ssh, harf: diskler.get(harf.upper()))
    ssh = lc.LocalConnector()
    assert lc.check_output_not_on_source(ssh, 0, "C:\\imajlar") == "output_on_source"
    assert lc.check_output_not_on_source(ssh, 0, "D:\\imajlar") is None
    # ag yolu yerel disk degil -- serbest
    assert lc.check_output_not_on_source(ssh, 0, "\\\\sunucu\\paylasim") is None
    # harfli ama diski belirlenemeyen yol guvenli tarafta reddedilir
    assert lc.check_output_not_on_source(ssh, 0, "Z:\\x") == "output_disk_unknown"


def test_logical_root_and_output_must_be_separate(monkeypatch):
    monkeypatch.setattr(lc, "_disk_number_for_letter", lambda ssh, harf: {"C": 0, "D": 1}.get(harf.upper()))
    ssh = lc.LocalConnector()
    # cikti taranan kokun ICINDE -- kendi kendini tarar
    assert lc.check_root_output_separate(ssh, "C:\\", "C:\\imajlar") == "output_on_source"
    assert lc.check_root_output_separate(ssh, "C:\\Users", "C:\\Users\\x\\cikti") == "output_on_source"
    # ayni fiziksel disk, farkli klasor (kok bir alt klasor)
    assert lc.check_root_output_separate(ssh, "C:\\Users", "C:\\baska") == "output_on_source"
    assert lc.check_root_output_separate(ssh, "C:\\", "D:\\imajlar") is None
