"""
disk_tree.py
Tam Disk (ham blok) imajlarinda dosya sistemi agacini KURAR -- imaji
mount ETMEDEN, pytsk3 (The Sleuth Kit Python binding'i) ile salt-okunur
ayristirir. Dosya/Klasor ve Mantiksal Imaj modlarindaki agac gorunumu
(build_path_tree, gui_v2.py) alma sirasinda yazilan manifest'teki bilinen
yol listesinden kuruluyordu; Tam Disk modunda boyle bir manifest yok (ham
blok imaji tek bir dosya), bu yuzden agacin kendisi HAM IMAJDAN ayristirilan
dosya sisteminden CIKARILIYOR.

Kapsam (bilincli sinir): sadece TEK PARCALI (bolunmemis), sikistirilmamis
ham imajlar destekleniyor -- segment (.001/.002) ve gzip'li imajlar bu ilk
surumde kapsam disi (bkz. docs/roadmap.md).
"""

import pytsk3

# Bozuk/dongusel bir dosya sisteminde agacin sonsuz/asiri buyumesini
# onlemek icin ust sinir -- gercek bir kanit imaji bozuk/kismi olabilir,
# bu yuzden bu bir "olmayacak senaryo" degil.
MAX_ENTRIES = 300_000


class DiskTreeError(Exception):
    """Imaj hic acilamadi (dosya yok, bos, taninmayan format vb.)."""


def _walk(fs, directory, prefix, node, sayac):
    for entry in directory:
        if sayac[0] >= MAX_ENTRIES:
            raise DiskTreeError(f"Dosya sistemi {MAX_ENTRIES} dugumden fazla iceriyor, agac kesildi.")
        try:
            isim = entry.info.name.name.decode("utf-8", errors="replace")
        except AttributeError:
            continue
        if isim in (".", ".."):
            continue
        meta = entry.info.meta
        if meta is None:
            continue  # silinmis/tutarsiz girdi, meta bilgisi yok

        yol = f"{prefix}/{isim}"
        if meta.type == pytsk3.TSK_FS_META_TYPE_DIR:
            try:
                alt_dizin = entry.as_directory()
            except (OSError, IOError):
                node[isim] = {}  # acilamadi (bozuk), bos klasor olarak goster
                continue
            alt_node = {}
            node[isim] = alt_node
            sayac[0] += 1
            _walk(fs, alt_dizin, yol, alt_node, sayac)
        elif meta.type == pytsk3.TSK_FS_META_TYPE_REG:
            # Yaprak degeri: (inode, boyut) -- cift tiklamada icerigi
            # cikarmak icin gerekli (bkz. extract_file). build_path_tree'nin
            # aksine (yaprak = str yol) burada tuple -- karistirilmasinlar.
            node[isim] = (meta.addr, meta.size)
            sayac[0] += 1
        # Diger turler (sembolik link, aygit vb.) bilerek gosterilmiyor --
        # ne icerik goruntuleme ne cikarma bunlar icin anlamli.


def _tree_from_fs(fs):
    node = {}
    _walk(fs, fs.open_dir(path="/"), "", node, [0])
    return node


def open_disk_tree(image_path):
    """
    image_path: Tam Disk modunda alinan, BOLUNMEMIS ham imaj dosyasi.
    Donen: bolum listesi -- [{"description", "offset", "tree", "error"}, ...]
    "offset": bolumun imaj icindeki BAYT ofseti (FS_Info/extract_file'a
    aynen verilir). "tree": basariyla ayristirildiysa build_path_tree ile
    ayni sekilde dict/tuple karisik bir agac; basarisizsa None ve "error"
    dolu (o bolum ATLANIR, DIGER bolumler yine de gosterilir).
    Bolum tablosu (MBR/GPT) yoksa TUM imaj TEK bir "bolum" sayilir.
    """
    try:
        img = pytsk3.Img_Info(image_path)
    except (OSError, IOError) as exc:
        raise DiskTreeError(str(exc)) from exc

    try:
        vs = pytsk3.Volume_Info(img)
    except (OSError, IOError):
        vs = None

    if vs is None:
        bolumler = [{"description": None, "offset": 0}]
    else:
        bolumler = [
            {"description": part.desc.decode("utf-8", errors="replace"), "offset": part.start * vs.info.block_size}
            for part in vs
            if int(part.flags) == pytsk3.TSK_VS_PART_FLAG_ALLOC
        ]

    sonuc = []
    for bolum in bolumler:
        girdi = {"description": bolum["description"], "offset": bolum["offset"], "tree": None, "error": None}
        try:
            fs = pytsk3.FS_Info(img, offset=bolum["offset"])
            girdi["tree"] = _tree_from_fs(fs)
        except (OSError, IOError, DiskTreeError) as exc:
            girdi["error"] = str(exc)
        sonuc.append(girdi)
    return sonuc


def extract_file(image_path, offset, inode, dest_path, chunk_size=1024 * 1024):
    """Bir dosyayi (inode, open_disk_tree'nin yaprak tuple'indaki ilk deger)
    imajdan okuyup dest_path'e yazar -- ONIZLEME icin (gui_v2.py'deki agac
    dialogunda cift tiklama). Imaj sadece OKUNUYOR, hicbir sey geri
    yazilmiyor (write-blocker'siz de kanit bozulmaz)."""
    img = pytsk3.Img_Info(image_path)
    fs = pytsk3.FS_Info(img, offset=offset)
    dosya = fs.open_meta(inode=inode)
    boyut = dosya.info.meta.size
    with open(dest_path, "wb") as hedef:
        okunan = 0
        while okunan < boyut:
            veri = dosya.read_random(okunan, min(chunk_size, boyut - okunan))
            if not veri:
                break
            hedef.write(veri)
            okunan += len(veri)


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Kullanim: python disk_tree.py <imaj_dosyasi>")
        sys.exit(1)
    for bolum in open_disk_tree(sys.argv[1]):
        print(f"Bolum: {bolum['description'] or '(tum imaj)'} @ offset {bolum['offset']}")
        if bolum["error"]:
            print(f"  Ayristirilamadi: {bolum['error']}")
        else:
            print(f"  {len(bolum['tree'])} kok ogesi")
