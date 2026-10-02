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


def _walk(fs, kok_dizin, kok_node, sayac):
    """Dizin agacini ITERATIF (yigin/stack tabanli) gezer -- kasitli olarak
    REKURSIF DEGIL. Rekursif bir gezinme her dizin seviyesinde bir Python
    cagri (stack) frame'i tuketir; dongusel/bozuk bir dizin yapisinda
    (ör. A -> B -> A -> ...) bu, `sayac` MAX_ENTRIES'e ULASMADAN COK ONCE
    Python'un varsayilan rekursion limitine (~1000) carpip RecursionError
    firlatirdi. RecursionError bir RuntimeError'dur ve open_disk_tree'nin
    per-bolum try/except'i (OSError/IOError/DiskTreeError) bunu YAKALAMAZ --
    boylece tum open_disk_tree cagrisi cokerdi. Yigin tabanli gezinmede
    derinlik Python cagri yigina degil bu fonksiyonun kendi listesine
    baglidir (ki zaten sayac ile MAX_ENTRIES'te sinirlandirilir), bu yuzden
    RecursionError riski TAMAMEN ortadan kalkar."""
    yigin = [(kok_dizin, kok_node)]
    while yigin:
        dizin, node = yigin.pop()
        for entry in dizin:
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

            if meta.type == pytsk3.TSK_FS_META_TYPE_DIR:
                try:
                    alt_dizin = entry.as_directory()
                except (OSError, IOError):
                    node[isim] = {}  # acilamadi (bozuk), bos klasor olarak goster
                    # Basarisiz da olsa bu bir "girdi denemesi" -- sayilmazsa
                    # binlerce acilamayan-ama-DIR-tipinde-gorunen girdi iceren
                    # bozuk bir imaj MAX_ENTRIES'i hic tetiklemeden sinirsiz
                    # bellek buyumesine yol acar (bu sabitin korumaya calistigi
                    # tam olarak bu senaryo).
                    sayac[0] += 1
                    continue
                alt_node = {}
                node[isim] = alt_node
                sayac[0] += 1
                yigin.append((alt_dizin, alt_node))
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
    _walk(fs, fs.open_dir(path="/"), node, [0])
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
        # DIKKAT: her partition entry'si AYRI try/except icinde okunuyor --
        # tek bir entry'nin desc/start/flags alani None ya da beklenmedik
        # olursa (bozuk bolum tablosu), bu SADECE o bolumu "hatali" olarak
        # isaretlemeli, asagidaki per-bolum FS ayristirma izolasyonuyla
        # TUTARLI sekilde diger bolumlerin enumerasyonunu ETKILEMEMELI --
        # eskiden bu bir liste comprehension'iydi ve herhangi bir entry'de
        # patlarsa TUM open_disk_tree cagrisini cokertiyordu.
        bolumler = []
        for part in vs:
            try:
                if int(part.flags) != pytsk3.TSK_VS_PART_FLAG_ALLOC:
                    continue
                bolumler.append({
                    "description": part.desc.decode("utf-8", errors="replace"),
                    "offset": part.start * vs.info.block_size,
                    "enum_error": None,
                })
            except (AttributeError, TypeError, ValueError) as exc:
                bolumler.append({"description": None, "offset": None, "enum_error": str(exc)})

    sonuc = []
    for bolum in bolumler:
        girdi = {"description": bolum["description"], "offset": bolum["offset"], "tree": None, "error": None}
        if bolum.get("enum_error"):
            girdi["error"] = bolum["enum_error"]
            sonuc.append(girdi)
            continue
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
    if dosya.info.meta is None:
        # _walk zaten bu durumu kontrol edip atliyordu (silinmis/tutarsiz
        # girdi, meta bilgisi yok) ama extract_file inode uzerinden AYRI
        # bir parse yapiyor -- ayni riski tasir, guard'i yoksa None.size
        # erisiminde yakalanmamis AttributeError firlatirdi.
        raise DiskTreeError(f"Dosya (inode={inode}) meta bilgisi okunamadi (silinmis/tutarsiz girdi).")
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
