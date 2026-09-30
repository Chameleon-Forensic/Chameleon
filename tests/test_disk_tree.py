"""
Tam Disk (ham blok) imajlarinda pytsk3 ile agac gorunumu -- docs/roadmap.md
"Sirada" listesindeki "Mount/pytsk3 ile Tam Disk imajlarinda da agac
gorunumu" maddesi. Gercek bir disk/USB gerektirmeden calismasi icin
conftest.py'deki build_minimal_fat12_image() ile kucuk, gecerli bir FAT12
imaji bayt bayt kuruluyor (bkz. o fonksiyonun docstring'i).
"""

import pytest

import disk_tree


def test_open_disk_tree_walks_root_and_subdirectory(fat12_image_path):
    bolumler = disk_tree.open_disk_tree(fat12_image_path)
    # Bolum tablosu (MBR/GPT) olmayan bir imaj -- TUM imaj tek "bolum" sayilir.
    assert len(bolumler) == 1
    bolum = bolumler[0]
    assert bolum["error"] is None
    assert bolum["offset"] == 0
    agac = bolum["tree"]
    assert set(agac.keys()) == {"HELLO.TXT", "SUBDIR"}
    assert isinstance(agac["SUBDIR"], dict)
    assert set(agac["SUBDIR"].keys()) == {"A.TXT"}
    # Yaprak degeri (inode, boyut) -- build_path_tree'nin aksine (str yol) tuple.
    inode, boyut = agac["HELLO.TXT"]
    assert boyut == 5
    assert isinstance(inode, int)


def test_extract_file_reads_correct_bytes(tmp_path, fat12_image_path):
    bolum = disk_tree.open_disk_tree(fat12_image_path)[0]
    agac = bolum["tree"]

    inode, _ = agac["HELLO.TXT"]
    hedef = tmp_path / "hello_out.txt"
    disk_tree.extract_file(fat12_image_path, bolum["offset"], inode, str(hedef))
    assert hedef.read_bytes() == b"hello"

    inode2, _ = agac["SUBDIR"]["A.TXT"]
    hedef2 = tmp_path / "a_out.txt"
    disk_tree.extract_file(fat12_image_path, bolum["offset"], inode2, str(hedef2))
    assert hedef2.read_bytes() == b"abc"


def test_open_disk_tree_missing_file_raises():
    with pytest.raises(disk_tree.DiskTreeError):
        disk_tree.open_disk_tree("bu_dosya_hic_yok.img")


def test_open_disk_tree_unrecognized_filesystem_reports_error_not_raise(tmp_path):
    # Ne bolum tablosu ne dosya sistemi -- taninmayan/bos icerik. Tum imaj
    # okunamiyor olsa bile fonksiyon RAISE ETMEMELI, "error" alaniyla
    # bildirmeli (bir bolumdeki bozukluk butun sonucu cokertmemeli).
    bozuk = tmp_path / "garbage.img"
    bozuk.write_bytes(b"\x00" * (1024 * 1024))
    bolumler = disk_tree.open_disk_tree(str(bozuk))
    assert len(bolumler) == 1
    assert bolumler[0]["tree"] is None
    assert bolumler[0]["error"]
