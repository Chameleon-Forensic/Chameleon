"""
Tam Disk (ham blok) imajlarinda pytsk3 ile agac gorunumu -- docs/roadmap.md
"Sirada" listesindeki "Mount/pytsk3 ile Tam Disk imajlarinda da agac
gorunumu" maddesi. Gercek bir disk/USB gerektirmeden calismasi icin
conftest.py'deki build_minimal_fat12_image() ile kucuk, gecerli bir FAT12
imaji bayt bayt kuruluyor (bkz. o fonksiyonun docstring'i).
"""

import pytest
import pytsk3

import disk_tree


class _SahteAd:
    """entry.info.name.name -- pytsk3'un girdi adini ham bayt olarak
    tuttugu gibi (sanitize/dogrulama YOK, bkz. path traversal testi)."""

    def __init__(self, isim):
        self.name = isim.encode("utf-8")


class _SahteMeta:
    def __init__(self, tip, addr=0, size=0):
        self.type = tip
        self.addr = addr
        self.size = size


class _SahteInfo:
    def __init__(self, isim, meta):
        self.name = _SahteAd(isim)
        self.meta = meta


class _SahteEntry:
    def __init__(self, isim, meta, alt_dizin=None):
        self.info = _SahteInfo(isim, meta)
        self._alt_dizin = alt_dizin

    def as_directory(self):
        if self._alt_dizin is None:
            raise OSError("dizin acilamadi (sahte/bozuk girdi)")
        return self._alt_dizin


class _SahteDizin(list):
    """Bir dizinin entry listesi -- pytsk3 dizin nesnesi gibi ITERABLE
    olmasi yeterli, _walk baska hicbir seyini kullanmiyor."""


def test_walk_deep_nesting_does_not_raise_recursion_error():
    """HATA 1 regresyon testi: eskiden _walk REKURSIF oldugu icin, MAX_ENTRIES
    sayacina (300.000) hic ulasmadan COK ONCE, derinligi Python'un varsayilan
    rekursion limitini (~1000) asan bir dizin zinciri RecursionError
    firlatirdi -- bu bir RuntimeError'dur ve open_disk_tree'nin per-bolum
    try/except'i (OSError/IOError/DiskTreeError) tarafindan YAKALANMAZDI.
    Yigin tabanli (iteratif) _walk bu sinira hic carpmamali."""
    derinlik = 2000  # varsayilan rekursion limitinden (~1000) fazla
    en_alt = _SahteDizin([
        _SahteEntry("yaprak.txt", _SahteMeta(pytsk3.TSK_FS_META_TYPE_REG, addr=1, size=4)),
    ])
    for i in range(derinlik):
        ust = _SahteDizin([_SahteEntry(f"d{i}", _SahteMeta(pytsk3.TSK_FS_META_TYPE_DIR), alt_dizin=en_alt)])
        en_alt = ust

    kok_node = {}
    disk_tree._walk(None, en_alt, kok_node, [0])  # RecursionError FIRLATMAMALI

    # En derine kadar dogru kurulmus mu, kontrol icin asagi in.
    dugum = kok_node
    for i in range(derinlik - 1, -1, -1):
        assert set(dugum.keys()) == {f"d{i}"}
        dugum = dugum[f"d{i}"]
    assert dugum == {"yaprak.txt": (1, 4)}


def test_walk_counts_failed_directory_opens_toward_max_entries(monkeypatch):
    """HATA 3 regresyon testi: as_directory() basarisiz olan (acilamayan
    ama DIR tipinde gorunen) girdiler eskiden sayaca DAHIL EDILMIYORDU --
    binlerce boyle girdi iceren bozuk bir imaj MAX_ENTRIES'i hic
    tetiklemeden sinirsiz buyuyebilirdi. sayac'in bu girdileri de
    saydigini, kucuk bir MAX_ENTRIES ile dogruluyoruz."""
    monkeypatch.setattr(disk_tree, "MAX_ENTRIES", 3)
    bozuk_meta = _SahteMeta(pytsk3.TSK_FS_META_TYPE_DIR)
    dizin = _SahteDizin([_SahteEntry(f"bozuk{i}", bozuk_meta, alt_dizin=None) for i in range(5)])

    with pytest.raises(disk_tree.DiskTreeError):
        disk_tree._walk(None, dizin, {}, [0])


def test_extract_file_raises_disk_tree_error_when_meta_none(monkeypatch, tmp_path):
    """HATA 4 regresyon testi: extract_file, _walk'un aksine meta'nin None
    olup olmadigini KONTROL ETMEDEN meta.size'a erisiyordu -- silinmis/
    tutarsiz bir girdi icin bu yakalanmamis bir AttributeError firlatirdi
    (gui_v2.py'nin double-click handler'i sadece OSError yakaliyor)."""

    class _SahteDosyaInfo:
        meta = None

    class _SahteDosya:
        info = _SahteDosyaInfo()

    class _SahteFS:
        def open_meta(self, inode):
            return _SahteDosya()

    monkeypatch.setattr(disk_tree.pytsk3, "Img_Info", lambda yol: object())
    monkeypatch.setattr(disk_tree.pytsk3, "FS_Info", lambda img, offset=0: _SahteFS())

    with pytest.raises(disk_tree.DiskTreeError):
        disk_tree.extract_file("herhangi_bir_imaj.img", 0, 42, str(tmp_path / "cikti.bin"))


def test_open_disk_tree_isolates_partition_enumeration_errors(monkeypatch, tmp_path):
    """HATA 5 regresyon testi: bolum listesini kuran (eskiden) liste
    comprehension'i hicbir try/except icinde degildi -- bir partition
    entry'sinin `desc` alani None/beklenmedik olursa (bozuk bolum tablosu),
    per-bolum try/except'e (FS_Info asamasi) HIC ULASMADAN TUM
    open_disk_tree cagrisi cokerdi. Artik bu SADECE o bolumu "hatali"
    olarak isaretlemeli, digerlerinin enumerasyonunu ETKILEMEMELI."""
    dosya = tmp_path / "sahte.img"
    dosya.write_bytes(b"\x00" * 1024)

    class _SahteBolum:
        def __init__(self, desc, start, flags):
            self.desc = desc
            self.start = start
            self.flags = flags

    class _SahteVSInfo:
        block_size = 512

    class _SahteVS:
        info = _SahteVSInfo()

        def __iter__(self):
            return iter([
                # desc None -> .decode() AttributeError firlatir (bozuk bolum tablosu senaryosu)
                _SahteBolum(None, 0, pytsk3.TSK_VS_PART_FLAG_ALLOC),
                _SahteBolum(b"Partition 2", 100, pytsk3.TSK_VS_PART_FLAG_ALLOC),
            ])

    def _sahte_fs_info(img, offset=0):
        # Bu testin odagi partition ENUMERASYONU, FS ayristirmasi degil --
        # ikisi de "taninmayan dosya sistemi" hatasi alsin.
        raise OSError("taninmayan dosya sistemi")

    monkeypatch.setattr(disk_tree.pytsk3, "Volume_Info", lambda img: _SahteVS())
    monkeypatch.setattr(disk_tree.pytsk3, "FS_Info", _sahte_fs_info)

    bolumler = disk_tree.open_disk_tree(str(dosya))
    assert len(bolumler) == 2  # enumerasyon COKMEDI, iki bolum de raporlandi
    assert all(b["error"] for b in bolumler)


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
