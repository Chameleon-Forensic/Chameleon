"""
file_acquirer.py
Tam disk yerine, uzak sunucuda tek bir DOSYA ya da KLASOR secip almak
icin modul. image_acquirer.py'deki "once dogrula, sonra yaz" mantigini
dosya seviyesinde uygular; SSHConnector'i aynen kullanir.

Onemli fark: bu mod write-blocker UYGULAMAZ. blockdev --setro tum blok
cihazi salt-okunur yapar, tek tek dosya/klasor icin anlamli degildir --
bu yuzden dosya/klasor secimi her zaman "Live" mantigiyla (diski
kilitlemeden, oldugu gibi okuyarak) calisir.

Buyuk dosyalar artik image_acquirer.py'deki ile AYNI blok+dogrulama
desenini kullanir (dd bs=4M ile parca parca, her parca yazilmadan once
sha256sum ile dogrulanir) -- tek farkla, hedef bir blok cihazi degil
duz bir dosya. Baglanti kopmasi durumunda ensure_connection() ile ayni
sekilde yeniden baglanip KALDIGI BLOKTAN devam eder (dosyanin tamamini
bastan cekmez) -- eskiden `cat` ile dosyanin tamami TEK SEFERDE
hafizaya okunup TEK bir sha256sum ile dogrulaniyordu, kopan bir
baglanti (orn. birkaç GB'lik bir log dosyasinda) islemi bastan
baslatiyordu.
"""

import hashlib
import json
import os
import shlex
from datetime import datetime, timezone

import chain_of_custody as coc
from image_acquirer import ensure_connection, _new_tree_manifest_path, _write_manifest, delete_manifest

FILE_CHUNK_SIZE_MB = 4  # image_acquirer.BLOCK_SIZE_MB ile ayni
MAX_RETRY_PER_BLOCK = 3


def remote_path_kind(ssh, remote_path, password=None):
    """
    Uzak yolun 'file', 'dir' ya da (yoksa) None oldugunu doner.
    shlex.quote ile kacirilir (bkz. image_acquirer.py'deki ayni onlem).
    """
    safe = shlex.quote(remote_path)
    cmd = f"test -f {safe} && echo FILE || (test -d {safe} && echo DIR || echo NONE)"
    if password:
        out, _err, _code = ssh.run_command(cmd, sudo_password=password)
    else:
        out, _err, _code = ssh.run_command(cmd)
    out = (out or "").strip()
    if out == "FILE":
        return "file"
    if out == "DIR":
        return "dir"
    return None


def _find_inaccessible_dirs(ssh, root, xdev=False):
    """root altinda GIRILEMEYEN (execute izni olmayan) ya da OKUNAMAYAN
    dizinlerin yollarini tek bir `find` komutuyla toplu tespit eder.

    Neden gerekli: duz `find {root} ... -type f`, boyle bir dizinin ICINE
    hic giremez -- altindaki TUM dosyalar hicbir hata/kayit birakmadan
    sessizce listeden eksik kalir (find sadece kendi stderr'ine bir uyari
    yazar, o da hicbir yerde toplanmiyordu). Bu fonksiyon dizinin KENDISINI
    raporlar; find kendisi de o dizine giremedigi icin ICERIGININ tam
    listesi cikarilamaz -- en azindan NEREDE veri kaybi oldugu delil
    zincirinde/manifest'te iz birakir (bkz. list_remote_files/
    list_logical_files).

    Sadece sudo parolasi YOKKEN cagrilir (bkz. cagiranlardaki `if not
    password` kontrolu) -- root olarak calisirken bu izin sinifi zaten
    sorun degil."""
    safe = shlex.quote(root)
    xdev_flag = "-xdev " if xdev else ""
    cmd = f"find {safe} {xdev_flag}-type d \\( ! -readable -o ! -executable \\)"
    out, _err, _code = ssh.run_command(cmd)
    return [s for s in (out or "").splitlines() if s.strip()]


def list_remote_files(ssh, remote_dir, password=None):
    """remote_dir altindaki (recursive) tum dosyalarin (klasor haric) yollarini
    doner.

    Sudo parolasi YOKSA, `find`'in kendisinin hic GIREMEDIGI (izinsiz)
    alt dizinler ayrica tespit edilip delil zincirine EXAM_ERROR olarak
    loglanir -- aksi halde o dizinin altindaki TUM dosyalar, donen listede
    hicbir iz birakmadan eksik kalirdi (bkz. list_logical_files, ayni
    sorunu manifest'e de isleyen tam surumu icin; bu fonksiyon geriye
    dönük uyumluluk icin duz bir liste dondurmeye devam ediyor, sadece
    LOGLUYOR)."""
    safe = shlex.quote(remote_dir)
    cmd = f"find {safe} -type f"
    if password:
        out, _err, _code = ssh.run_command(cmd, sudo_password=password)
    else:
        out, _err, _code = ssh.run_command(cmd)
        for dizin in _find_inaccessible_dirs(ssh, remote_dir):
            coc.log_event(
                coc.EVENT_EXAM_ERROR,
                f"Dizine girilemedi (izin yok), altindaki dosyalar listeye hic girmedi: {dizin}",
            )
    if not out:
        return []
    return [satir for satir in out.splitlines() if satir.strip()]


def list_logical_files(ssh, remote_root, password=None):
    """
    Mantiksal imaj (bkz. docs/roadmap.md madde 0.5) icin dosya listesi.

    list_remote_files'tan farki: `-xdev` -- find, remote_root'un ait oldugu
    dosya sisteminin (bolumun) DISINA cikmaz. Boylece /proc, /sys, /dev,
    /run gibi sahte/ucucu dosya sistemleri ve baska bolumler/ag
    paylasimlari (NFS vb.) hicbir ozel dislama listesi gerekmeden disarida
    kalir -- bir mantiksal imaj tek bir HACMI (volume) temsil eder, baska
    bir bolum icin ayri alinmalidir.

    Sudo parolasi YOKSA okunamayan dosyalar (find ! -readable) TEK bir
    komutla toplu tespit edilir ve alma dongusune hic sokulmaz -- aksi
    halde her biri 4 yeniden denemeyle (hash+okuma) zaman kaybettirirdi.
    Ayni sekilde, GIRILEMEYEN (execute izni olmayan) alt dizinler de ayri
    bir taramayla (_find_inaccessible_dirs) tespit edilip onceden_basarisiz'a
    eklenir -- aksi halde duz `find -xdev -type f` boyle bir dizinin ICINE
    hic inemeyecegi icin altindaki TUM dosyalar listede HICBIR IZ
    BIRAKMADAN eksik kalirdi (adli bir arac icin ciddi bir bosluk: manifest
    "eksiksiz" gorunur ama okunamayan bir alt agacin tum icerigi delil
    zincirinde hic gorunmez). find kendisi de o dizine giremedigi icin
    ICERIGININ tam listesi cikarilamiyor -- raporlanan sadece dizinin
    KENDISI, ama en azindan NEREDE veri kaybi oldugu artik iz birakiyor.

    Donus: (dosyalar, onceden_basarisiz, dislanan) -- ikisi de {yol: sebep}.
    onceden_basarisiz BEKLENMEYEN eksikler (izin yok); dislanan bilerek
    alinmayanlar (Linux'ta -xdev ile otomatik, ayrica listelenecek bir sey yok).
    """
    safe = shlex.quote(remote_root)
    run = (lambda c: ssh.run_command(c, sudo_password=password)) if password else ssh.run_command

    out, _err, _code = run(f"find {safe} -xdev -type f")
    dosyalar = [s for s in (out or "").splitlines() if s.strip()]

    onceden_basarisiz = {}
    if not password:
        out, _err, _code = run(f"find {safe} -xdev -type f ! -readable")
        for s in (out or "").splitlines():
            if s.strip():
                onceden_basarisiz[s] = "izin yok (okunamiyor)"
        dosyalar = [d for d in dosyalar if d not in onceden_basarisiz]

        for dizin in _find_inaccessible_dirs(ssh, remote_root, xdev=True):
            onceden_basarisiz[dizin] = "dizine girilemedi (izin yok)"
    return dosyalar, onceden_basarisiz, {}


def list_remote_directory(ssh, remote_path, password=None):
    """
    remote_path'in DOGRUDAN alt ogelerini (bir seviye, -maxdepth 1) doner --
    "Gozat" ile gezinme ozelligi icin. Salt-okunur (find), hicbir sey
    yazmiyor/degistirmiyor. Her cagri chain-of-custody'ye DIRECTORY_LISTED
    olarak islenir (operatorun hedef sistemde nereye baktigi izlenebilsin).

    Donus: [(isim, is_dir), ...] -- klasorler once, sonra dosyalar, ikisi de
    kendi icinde alfabetik (buyuk/kucuk harf gozetmeksizin). Yol yoksa/
    okunamazsa None.
    """
    safe = shlex.quote(remote_path)
    cmd = f"find {safe} -mindepth 1 -maxdepth 1 -printf '%y %f\\n'"
    if password:
        out, _err, _code = ssh.run_command(cmd, sudo_password=password)
    else:
        out, _err, _code = ssh.run_command(cmd)
    if out is None:
        return None

    entries = []
    for line in out.splitlines():
        line = line.rstrip("\n")
        if not line or " " not in line:
            continue
        type_char, name = line.split(" ", 1)
        entries.append((name, type_char == "d"))
    entries.sort(key=lambda e: (not e[1], e[0].lower()))

    coc.log_event(coc.EVENT_DIRECTORY_LISTED, f"Klasor listelendi: {remote_path}")
    return entries


def get_remote_file_hash(ssh, remote_path, password=None):
    """dd/sha256sum yerine dogrudan sha256sum -- tum dosyayi tek seferde hashler.
    Artik acquire_remote_file icinde kullanilmiyor (blok blok dogrulaniyor),
    ama tek basina bagimsiz bir dogrulama araci olarak faydali oldugu icin
    korunuyor."""
    safe = shlex.quote(remote_path)
    cmd = f"sha256sum {safe}"
    if password:
        out, _err, _code = ssh.run_command(cmd, sudo_password=password)
    else:
        out, _err, _code = ssh.run_command(cmd)
    if not out:
        return None
    parcalar = out.strip().split(None, 1)
    return parcalar[0] if parcalar else None


def get_remote_file_size(ssh, remote_path, password=None):
    """Uzak dosyanin boyutunu bayt cinsinden dondurur (image_acquirer.
    get_disk_size_bytes ile ayni desen, `stat -c%s` ile)."""
    safe = shlex.quote(remote_path)
    cmd = f"stat -c%s {safe}"
    if password:
        out, _err, _code = ssh.run_command(cmd, sudo_password=password)
    else:
        out, _err, _code = ssh.run_command(cmd)
    if not out:
        return None
    try:
        return int(out.strip())
    except ValueError:
        return None


def _get_remote_file_block_hash(ssh, remote_path, block_no, block_size_mb, password):
    """image_acquirer.get_remote_block_hash ile AYNI desen, disk yerine duz dosya."""
    dd_cmd = (
        f"dd if={shlex.quote(remote_path)} bs={block_size_mb}M skip={block_no} count=1 "
        f"status=none 2>/dev/null | sha256sum"
    )
    if password:
        output, _error, _exit_status = ssh.run_command(dd_cmd, sudo_password=password)
    else:
        output, _error, _exit_status = ssh.run_command(dd_cmd)
    if not output:
        return None
    parcalar = output.strip().split(None, 1)
    return parcalar[0] if parcalar else None


def _acquire_raw_file_block(ssh, remote_path, block_no, block_size_mb, password):
    """image_acquirer.acquire_raw_block ile AYNI desen -- ham bayt icin
    run_command() degil dogrudan ssh.client.exec_command() kullanilir.

    stderr, stdout'tan SONRA ama recv_exit_status()'tan ONCE mutlaka
    okunur (bosaltilir) -- run_command()'da bulunup duzeltilen AYNI
    paramiko kanal kilitlenme deseni (bkz. ssh_connector.py/docs/
    roadmap.md) burada, run_command()'dan BAGIMSIZ bu dogrudan
    exec_command() yolunda da gecerliydi: uzak `sudo`/`dd` stderr'e
    (orn. "sudo: no tty present" gibi) kanalin flow-control penceresini
    asacak kadar yazarsa, kimse stderr'i okumadigi icin uzak taraf orada
    tikanir, exit etmez, recv_exit_status() SONSUZA KADAR bekler --  tum
    alma thread'i kilitlenir. stdout ham bayt oldugu (decode edilmiyor)
    icin set_combine_stderr(True) KULLANILMADI -- stderr stdout'a karisirsa
    blok verisi bozulurdu; bunun yerine stderr ayrica okunup atiliyor."""
    dd_cmd = (
        f"dd if={shlex.quote(remote_path)} bs={block_size_mb}M skip={block_no} count=1 "
        f"status=none"
    )
    try:
        if password:
            stdin, stdout, stderr = ssh.client.exec_command(f"sudo -S {dd_cmd}")
            stdin.write(password + "\n")
            stdin.flush()
        else:
            stdin, stdout, stderr = ssh.client.exec_command(dd_cmd)
        veri = stdout.read()
        stderr.read()  # kanal kilitlenmesin diye bosaltilir, icerigi kullanilmiyor
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            return None
        return veri
    except Exception:
        return None


def acquire_remote_file(ssh, remote_path, local_path, password=None, block_size_mb=FILE_CHUNK_SIZE_MB):
    """
    Dosyayi image_acquirer.acquire_disk_image ile AYNI desende blok blok
    ceker: her blogun uzak hash'i (dd+sha256sum) ONCE alinir, veri agdan
    cekilir, yazmadan once dogrulanir -- bozuk bir blok diske hic yazilmaz.
    Baglanti koparsa ensure_connection() ile yeniden baglanip KALDIGI
    BLOKTAN devam eder (MAX_RETRY_PER_BLOCK deneme), tum dosyayi bastan
    cekmez -- eski (tek parca `cat`) davranisin aksine.

    Kalici olarak basarisiz olunursa (bkz. MAX_RETRY_PER_BLOCK, ensure_connection),
    o ana kadar diske yazilmis YARIM/DOGRULANMAMIS dosya BIRAKILMAZ --
    local_path silinir, sadece (False, None) donulur.

    Donus: (basarili: bool, sha256: str veya None) -- imza eskiyle AYNI,
    acquire_remote_tree'nin cagirma seklinde degisiklik gerekmiyor.
    """
    if ssh.client is None:
        return False, None

    boyut = get_remote_file_size(ssh, remote_path, password=password)
    if boyut is None:
        return False, None

    block_bytes = block_size_mb * 1024 * 1024
    total_blocks = max(1, (boyut + block_bytes - 1) // block_bytes) if boyut > 0 else 1

    os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
    hasher = hashlib.sha256()
    kalici_basarisiz = False

    with open(local_path, "wb") as cikti:
        for block_no in range(total_blocks):
            retry_count = 0
            block_ok = False
            veri = None

            while retry_count <= MAX_RETRY_PER_BLOCK and not block_ok:
                if not ensure_connection(ssh):
                    kalici_basarisiz = True
                    break

                uzak_hash = _get_remote_file_block_hash(ssh, remote_path, block_no, block_size_mb, password)
                if uzak_hash is None:
                    retry_count += 1
                    continue

                veri = _acquire_raw_file_block(ssh, remote_path, block_no, block_size_mb, password)
                if veri is None:
                    retry_count += 1
                    continue

                if hashlib.sha256(veri).hexdigest() != uzak_hash:
                    retry_count += 1
                    continue

                block_ok = True

            if kalici_basarisiz or not block_ok:
                kalici_basarisiz = True
                break

            cikti.write(veri)
            hasher.update(veri)

    if kalici_basarisiz:
        # Dosya kalici olarak basarisiz oldu -- diskte kalan, ONCEKI
        # (basarili) bloklardan olusan YARIM/DOGRULANMAMIS veriyi sil.
        # Aksi halde bu dosya manifest_files.json'a HIC GIRMEDIGI halde
        # (acquire_remote_tree onu sadece failed/failed_reasons'a ekler,
        # asla acquired'a) output_dir'de KALICI olarak durur -- manifest
        # yerine dogrudan cikti klasorune bakan biri bunu gercek/dogrulanmis
        # delil sanabilir. Silme basarisiz olursa (izin, kilitli dosya vb.)
        # asil hatayi gizlemesin diye sessizce devam edilir.
        try:
            os.remove(local_path)
        except OSError:
            pass
        return False, None

    return True, hasher.hexdigest()


def _diagnose_failure(ssh, remote_path, password=None):
    """Bir dosya alinamayinca (SADECE o zaman -- basarili dosyalara ek
    maliyet yok) sebebini kisa bir metin olarak doner; mantiksal imaj
    raporunda operatorun neyin neden eksik oldugunu gorebilmesi icin."""
    safe = shlex.quote(remote_path)
    cmd = f"test -e {safe} && (test -r {safe} && echo OK || echo DENIED) || echo GONE"
    out, _err, _code = (ssh.run_command(cmd, sudo_password=password) if password else ssh.run_command(cmd))
    durum = (out or "").strip()
    if durum == "DENIED":
        return "izin yok (okunamiyor)"
    if durum == "GONE":
        return "dosya alma sirasinda kayboldu"
    return "okuma/dogrulama hatasi"


def acquire_remote_tree(ssh, remote_root, output_dir, password=None, progress_callback=None,
                         manifest_path=None, resume_state=None, host=None,
                         file_lister=None, manifest_every=1, mode="file", should_stop=None):
    """
    file_lister/manifest_every/mode: mantiksal imaj (docs/roadmap.md madde
    0.5) icin. file_lister(ssh, root, password) -> (dosyalar, onceden_
    basarisiz{yol: sebep}) verilirse klasor listesi `find -type f` yerine
    ondan gelir; manifest_every=N her N dosyada bir kalici manifest yazar
    (varsayilan 1 = eski davranis -- yuz binlerce dosyada her dosyadan
    sonra TUM manifest JSON'unu bastan yazmak O(n^2) maliyet olurdu; kesintide
    en fazla N dosya yeniden alinir, hedef dosya uzerine yazildigi icin
    zararsiz).

    Donus manifest'ine `failed_reasons` ({yol: sebep}) ve `mode` eklenir.

    remote_root bir dosya ya da klasor olabilir. Klasorse altindaki tum
    dosyalari (find -type f) tek tek acquire_remote_file ile alir, goreli
    dizin yapisini output_dir altinda korur. Tek dosyaysa dogrudan onu alir.

    progress_callback(done, total) verilirse her dosyadan sonra cagrilir.

    manifest_path/resume_state/host: docs/roadmap.md madde 0.4 -- program
    TAMAMEN kapanip yeniden acilsa bile (image_acquirer.find_incomplete_tree_manifest
    ile) kaldigi dosyadan devam edilebilmesi icin. Her dosya basariyla
    alindiktan SONRA logs/manifest_tree_<tarih-saat>.json'a (resume_state
    verilmisse AYNI dosyaya) kaydedilir -- image_acquirer.acquire_disk_image'in
    her blok sonrasi manifest guncellemesiyle AYNI desen. Bu, output_dir
    icindeki manifest_files.json'dan (islem SONUCUNUN kalici ozeti, resume
    icin degil, her zaman ayrica yazilir) FARKLI bir dosyadir.

    resume_state'teki "acquired_files"a KORU KORUNE guvenilmez -- her
    dosya, atlanmadan ONCE yerel cikti dosyasinin HALA VAR olup olmadigi
    (os.path.exists) kontrol edilir; yoksa (onceki calisma coktukten
    sonra output_dir tasinmis/temizlenmis, antivirus karantinaya almis,
    disk degismis vb.) o dosya yeniden alma dongusune geri konur. Tam
    hash yeniden dogrulamasi BILINCLI olarak yapilmiyor (bkz. docs/
    kararlar.md) -- cok dosyali bir resume'da her dosyayi yeniden hash'lemek
    pahali olurdu; varlik kontrolu en azindan "yerel dosya tamamen yok"
    durumunu (asil bildirilen senaryo) yakalar.

    should_stop: verilirse, her dosyadan ONCE (o an islenmekte olan dosya
    tamamlanmadan asla kesilmez) cagirilir; True donerse dongu erken
    biter, o ana kadarki ilerleme (kalici manifest dahil) korunur --
    "Yarim Kalanlar"da normal sekilde devam teklif edilir (bkz. gui_v2.py
    "Durdur" butonu).

    Donus: manifest dict (remote_root, total_files, acquired, failed,
    acquired_at, stopped) ya da yol bulunamadiysa None.
    """
    kind = remote_path_kind(ssh, remote_root, password=password)
    if kind is None:
        coc.log_event(coc.EVENT_EXAM_ERROR, f"Yol bulunamadi: {remote_root}")
        return None

    onceden_basarisiz = {}
    dislanan = {}
    if kind == "file":
        dosyalar = [remote_root]
        taban = os.path.dirname(remote_root)
    elif file_lister is not None:
        dosyalar, onceden_basarisiz, dislanan = file_lister(ssh, remote_root, password)
        taban = remote_root
    else:
        dosyalar = list_remote_files(ssh, remote_root, password=password)
        taban = remote_root

    if manifest_path is None:
        manifest_path = _new_tree_manifest_path()

    onceden_alinan = set((resume_state or {}).get("acquired_files", []))
    started_at_utc = (resume_state or {}).get("started_at_utc") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if onceden_alinan:
        coc.log_event(
            coc.EVENT_EXAM_RESUME,
            f"Dosya/klasor alma devam ettiriliyor: {remote_root} "
            f"({len(onceden_alinan)}/{len(dosyalar)} zaten tamamlanmis)",
        )
    else:
        coc.log_event(
            coc.EVENT_EXAM_START,
            f"Dosya/klasor alma baslatildi: {remote_root} ({len(dosyalar)} dosya)",
        )

    n_pre = len(onceden_basarisiz)
    toplam = len(dosyalar) + n_pre
    sonuclar = list((resume_state or {}).get("acquired_detail", []))
    basarisiz = list(onceden_basarisiz)
    failed_reasons = dict(onceden_basarisiz)
    acquired_files = list(onceden_alinan)
    if n_pre:
        coc.log_event(
            coc.EVENT_EXAM_ERROR,
            f"{n_pre} oge okunamadigi icin (izin yok) alma dongusune sokulmadi: {remote_root}",
        )
    if dislanan:
        coc.log_event(
            coc.EVENT_LOGICAL_EXCLUSIONS,
            f"{len(dislanan)} oge bilerek dislandi (kilitli/degisken sistem ogesi): {remote_root}",
        )

    def _yaz_kalici_manifest():
        _write_manifest(manifest_path, {
            "remote_root": remote_root,
            "host": host,
            "mode": mode,
            "total_files": toplam,
            "acquired_files": acquired_files,
            "acquired_detail": sonuclar,
            "failed_files": basarisiz,
            "started_at_utc": started_at_utc,
        })

    durduruldu = False
    for i, uzak_dosya in enumerate(dosyalar, start=1):
        if should_stop and should_stop():
            durduruldu = True
            _yaz_kalici_manifest()  # o ana kadarki ilerlemeyi kesin diske yaz
            coc.log_event(
                coc.EVENT_EXAM_STOPPED,
                f"Dosya/klasor alma kullanici tarafindan durduruldu: {remote_root} "
                f"({len(acquired_files)}/{toplam})",
            )
            break

        goreli = os.path.relpath(uzak_dosya, taban) if taban else os.path.basename(uzak_dosya)
        goreli = goreli.replace("/", os.sep)
        yerel_dosya = os.path.join(output_dir, goreli)

        if uzak_dosya in onceden_alinan:
            # Onceki calisma bu dosyayi "alindi" diye isaretlemis olabilir,
            # ama yerel cikti dosyasi o ISARETLEMEDEN SONRA kaybolmus
            # olabilir (program coktu ve output_dir'deki yarim klasor
            # tasindi/temizlendi, antivirus karantinaya aldi, output_dir'i
            # tutan disk degisti, vb.) -- resume_state'e KORU KORUNE
            # guvenip atlarsak, nihai manifest o dosyayi yerel kopya
            # yokken/bozukken "basariyla alindi ve hash dogrulandi" diye
            # raporlar. Bu yuzden atlamadan ONCE en azindan dosyanin hala
            # VAR olup olmadigi kontrol edilir (bkz. docs/kararlar.md --
            # tam hash'i burada yeniden hesaplamak, ozellikle cok dosyali
            # resume'da performans acisindan pahali oldugundan bilincli
            # olarak sadece varlik kontrolu yapiliyor).
            if os.path.exists(yerel_dosya):
                if progress_callback:
                    progress_callback(i + n_pre, toplam)
                continue
            onceden_alinan.discard(uzak_dosya)
            if uzak_dosya in acquired_files:
                acquired_files.remove(uzak_dosya)
            sonuclar[:] = [s for s in sonuclar if s.get("remote_path") != uzak_dosya]
            coc.log_event(
                coc.EVENT_EXAM_ERROR,
                f"Onceden alindi isaretli dosyanin yerel kopyasi bulunamadi, yeniden aliniyor: {uzak_dosya}",
            )

        basarili, hash_deger = acquire_remote_file(ssh, uzak_dosya, yerel_dosya, password=password)
        if basarili:
            sonuclar.append({
                "remote_path": uzak_dosya, "local_path": yerel_dosya, "sha256": hash_deger,
            })
            acquired_files.append(uzak_dosya)
            coc.log_event(coc.EVENT_BLOCK_ACQUIRED, f"Dosya alindi ve dogrulandi: {uzak_dosya}", hash_deger)
        else:
            basarisiz.append(uzak_dosya)
            failed_reasons[uzak_dosya] = _diagnose_failure(ssh, uzak_dosya, password)
            coc.log_event(
                coc.EVENT_EXAM_ERROR,
                f"Dosya alinamadi/dogrulanamadi ({failed_reasons[uzak_dosya]}): {uzak_dosya}",
            )

        # Her dosyadan sonra (manifest_every=1 iken) KALICI manifest
        # guncellenir -- boylece program kapanip yeniden acilsa bile
        # kaldigi dosyadan devam edilebilir (bkz. image_acquirer.
        # acquire_disk_image'deki AYNI desen).
        if i % manifest_every == 0:
            _yaz_kalici_manifest()

        if progress_callback:
            progress_callback(i + n_pre, toplam)

    if not durduruldu:
        coc.log_event(
            coc.EVENT_EXAM_END,
            f"Dosya/klasor alma tamamlandi: {len(sonuclar)}/{toplam} basarili, "
            f"{len(basarisiz)} basarisiz",
        )

    tamamlandi_temiz = not basarisiz and len(acquired_files) == toplam
    # Mantiksal imajda (mode != "file") bazi dosyalar KALICI olarak alinamaz
    # (kilitli/izinsiz) -- islem BITTIYSE manifest yine kaldirilir, aksi
    # halde "Yarim Kalanlar"da sonsuza kadar duran bir kayit olurdu; basarisiz
    # dosyalar zaten manifest_files.json'da sebepleriyle listeli. Kullanici
    # BILEREK durdurduysa (durduruldu=True) bu kural gecerli DEGIL -- o
    # zaman mode ne olursa olsun manifest KORUNUR, aksi halde mantiksal
    # imajda "Durdur"a basmak devam etme ihtimalini tamamen yok ederdi.
    if not durduruldu and (tamamlandi_temiz or mode != "file"):
        # Tum dosyalar eksiksiz alindi -- yarim kalmis bir islem olarak
        # tekrar sunulmamasi icin kalici manifest kaldirilir.
        delete_manifest(manifest_path)

    manifest = {
        "remote_root": remote_root,
        "mode": mode,
        "total_files": toplam,
        "acquired": sonuclar,
        "failed": basarisiz,
        "failed_reasons": failed_reasons,
        "excluded": dislanan,
        "acquired_at": datetime.now(timezone.utc).isoformat(),
        "stopped": durduruldu,
    }

    os.makedirs(output_dir, exist_ok=True)
    ozet_yolu = os.path.join(output_dir, "manifest_files.json")
    with open(ozet_yolu, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    return manifest


# Mantiksal imajda kalici manifest her N dosyada bir yazilir (bkz.
# acquire_remote_tree docstring'i -- manifest_every).
LOGICAL_MANIFEST_EVERY = 100


def acquire_logical_image(ssh, remote_root, output_dir, password=None, progress_callback=None,
                           manifest_path=None, resume_state=None, host=None, should_stop=None):
    """Mantiksal imaj (Linux): remote_root'un ait oldugu hacmin (volume)
    var olan TUM dosyalari -- bkz. list_logical_files. Silinmis veri ve bos
    alan alinmaz (o, Tam Disk modunun isi)."""
    return acquire_remote_tree(
        ssh, remote_root, output_dir, password=password, progress_callback=progress_callback,
        manifest_path=manifest_path, resume_state=resume_state, host=host,
        file_lister=list_logical_files, manifest_every=LOGICAL_MANIFEST_EVERY, mode="logical",
        should_stop=should_stop,
    )
