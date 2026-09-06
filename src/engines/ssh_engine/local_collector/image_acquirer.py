"""
image_acquirer.py
Uzak diskten blok blok (varsayilan 4 MB, hash_verifier.CHUNK_SIZE ile ayni)
imaj alma modulu.

Roadmap'e (Gorev 2, main.py'deki yorum blogu) uygun akis:

    1) apply_write_block(ssh, disk)      -> kaynak disk salt-okunur yapilir
    2) her blok icin:
         uzak_hash = get_remote_block_hash(...)      # sha256sum, dd'den ONCE
         veri      = acquire_raw_block(...)           # ham bayt, agdan
         verify_chunk(veri, uzak_hash, index=blok_no) # diske yazmadan ONCE dogrula
         -> basarisizsa blok ATILIR, diske YAZILMAZ, yeniden istenir
         -> basariliysa coc.EVENT_BLOCK_ACQUIRED loglanir
    3) bloklar concatenate_blocks() ile tek imaj dosyasinda birlestirilir
    4) main.verify_image_and_log() ile master (SHA-256) dogrulamasi yapilir

Tum olaylar chain_of_custody.py uzerinden logs/case_<tarih-saat>.log
dosyasina islenir.
"""

import getpass
import gzip
import json
import os
import re
import shlex
import shutil
import sys
import time
from datetime import datetime, timezone

import chain_of_custody as coc
from hash_verifier import (
    CHUNK_SIZE,
    HashMismatchError,
    parse_sha256sum_output,
    verify_chunk,
    hash_file,
)
from ssh_connector import SSHConnector
from write_block_helper import apply_write_block, is_write_blocked

BLOCK_SIZE_MB = CHUNK_SIZE // (1024 * 1024)  # hash_verifier ile birebir ayni (4 MB)

# Script'in NEREDEN calistirildigina (cwd) degil, kendi konumuna gore
# cozulur — aksi halde program yanlislikla farkli bir dizinden (orn.
# C:\Windows\System32) baslatilirsa oraya yazmaya calisip "Permission
# denied" hatasi verir (bkz. remote_agent/write_blocker.sh'daki ayni
# sinif hata icin uygulanan SCRIPT_DIR cozumu).
#
# Derlenmis (.exe) modda bu, __file__ yerine sys.executable'a gore
# hesaplanir -- aksi halde PyInstaller'in gecici _MEIPASS klasorune
# duser (chain_of_custody.LOG_DIR ile ayni gerekce, bkz. docs/roadmap.md).
if getattr(sys, "frozen", False):
    _PERSISTENT_ROOT = os.path.dirname(os.path.abspath(sys.executable))
    IMAGE_DIR = os.path.join(_PERSISTENT_ROOT, "images")
    MANIFEST_DIR = os.path.join(_PERSISTENT_ROOT, "logs")
else:
    IMAGE_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "images"
    )
    # manifest_<tarih-saat>.json dosyalari, chain_of_custody.py'nin log/
    # klasoruyle ayni yerde tutulur (docs/PROJE_TALIMATI.md madde 6).
    MANIFEST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")

MAX_RETRY_PER_BLOCK = 3


def _new_manifest_path():
    """logs/manifest_<tarih-saat>.json icin yeni, benzersiz bir yol uretir."""
    os.makedirs(MANIFEST_DIR, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return os.path.join(MANIFEST_DIR, f"manifest_{timestamp}.json")


def _write_manifest(path, state):
    """Su anki ilerleme durumunu JSON olarak diske yazar (her blok sonrasi cagrilir)."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except OSError as e:
        print(f"[-] Manifest yazilamadi: {e}")


def load_manifest(path):
    """Bir manifest dosyasini okur; bozuk/eksikse None doner."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def find_incomplete_manifest(disk_path=None):
    """
    logs/ klasorunde yarim kalmis (acquired_blocks < total_blocks) bir
    manifest olup olmadigina bakar. Bulursa (yol, veri) tuple'i, bulamazsa
    None doner. disk_path verilirse sadece o diske ait manifestler dikkate
    alinir (en yeniden en eskiye dogru taranir).
    """
    if not os.path.isdir(MANIFEST_DIR):
        return None

    adaylar = sorted(
        f for f in os.listdir(MANIFEST_DIR)
        if f.startswith("manifest_") and f.endswith(".json")
    )

    for dosya_adi in reversed(adaylar):
        yol = os.path.join(MANIFEST_DIR, dosya_adi)
        veri = load_manifest(yol)
        if veri is None:
            continue
        if disk_path is not None and veri.get("disk_path") != disk_path:
            continue
        if len(veri.get("acquired_blocks", [])) < veri.get("total_blocks", 0):
            return yol, veri

    return None


def delete_manifest(path):
    """Islem tum bloklarla basariyla bitince manifest dosyasini kaldirir."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError as e:
        print(f"[-] Manifest silinemedi: {e}")


def get_disk_size_bytes(ssh, disk_path, password=None):
    """
    Uzak diskin toplam boyutunu bayt cinsinden dondurur.
    Sabit blok sayisi varsayimi yerine gercek boyuttan hesaplama yapmayi
    saglar.

    Parola, run_command()'in sudo_password mekanizmasiyla stdin uzerinden
    guvenli sekilde iletilir; komut metnine hic gomulmez (shell injection
    ve `ps aux` ile gorunme riskini onlemek icin).
    """
    # disk_path kullanicidan (GUI/CLI) geliyor; shlex.quote olmadan f-string'e
    # gomulurse shell injection riski var -- parola icin zaten uygulanan
    # ayni korumayi disk_path icin de burada saglıyoruz.
    safe_disk_path = shlex.quote(disk_path)
    if password:
        output, _error, _exit_status = ssh.run_command(
            f"blockdev --getsize64 {safe_disk_path}", sudo_password=password
        )
    else:
        output, _error, _exit_status = ssh.run_command(
            f"sudo blockdev --getsize64 {safe_disk_path}", get_pty=True
        )

    if output is None:
        return None
    try:
        return int(output.strip())
    except (ValueError, AttributeError):
        return None


def get_disk_description(ssh, disk_path):
    """
    Diskin model/seri numarasini alir -- rapora sadece /dev/sdb gibi bir
    yol degil, diskin gercek/benzersiz kimligini de yazabilmek icin
    (ISO/IEC 27037'nin istedigi "delilin benzersiz tanimlanmasi"
    gereksinimi -- ayni yol farkli zamanlarda farkli fiziksel diske
    karsilik gelebilir, seri no ise degismez).

    -P (key="value") formati kullanilir: duz kolon ciktisinda MODEL
    alani bosluk icerebilir (orn. "Virtual Disk"), bu da kolonlarin
    yanlis hizalanmasina/parcalanmasina yol acar. -P bu riski ortadan
    kaldirir. Okunamazsa (ornegin cok eski bir util-linux surumu -P'yi
    desteklemiyorsa) sessizce bos donulur -- bu bilgi olmadan da rapor
    gecerlidir, sadece daha az detaylidir.
    """
    safe_disk_path = shlex.quote(disk_path)
    output, _error, _exit_status = ssh.run_command(
        f"lsblk -d -n -P -o MODEL,SERIAL {safe_disk_path}"
    )
    if not output:
        return ""
    model = re.search(r'MODEL="([^"]*)"', output)
    serial = re.search(r'SERIAL="([^"]*)"', output)
    model_val = (model.group(1) if model else "").strip()
    serial_val = (serial.group(1) if serial else "").strip()
    parts = []
    if model_val:
        parts.append(f"Model: {model_val}")
    if serial_val:
        parts.append(f"Seri No: {serial_val}")
    return ", ".join(parts)


def get_remote_block_hash(ssh, disk_path, block_no, block_size_mb, password):
    """
    Uzak sunucuda dd ile okunan bloğun SHA-256 özetini sha256sum ile
    hesaplatir. Metin tabanli bir komut oldugu icin ssh_connector'in
    run_command() (decode edilmis) arayuzunu kullanir.

    Parola komut metnine gomulmez, run_command()'in sudo_password
    mekanizmasiyla stdin uzerinden guvenli sekilde iletilir (sadece dd
    kismi sudo gerektirir; sha256sum, pipe'tan okudugu icin sudo'suz
    calisir).
    """
    dd_cmd = (
        f"dd if={shlex.quote(disk_path)} bs={block_size_mb}M skip={block_no} count=1 "
        f"conv=noerror,sync status=none 2>/dev/null | sha256sum"
    )
    if password:
        output, _error, _exit_status = ssh.run_command(dd_cmd, sudo_password=password)
    else:
        output, _error, _exit_status = ssh.run_command(f"sudo {dd_cmd}", get_pty=True)

    if not output:
        return None
    try:
        return parse_sha256sum_output(output)
    except Exception as e:
        print(f"[-] Blok {block_no} icin uzak hash ayristirilamadi: {e}")
        return None


def acquire_raw_block(ssh, disk_path, block_no, block_size_mb, password):
    """
    Belirtilen bloğu uzak sunucudan HAM bayt olarak ceker. Bu, tek
    yerdir cunku veri decode EDILMEDEN okunmalidir; bu yuzden
    ssh.client.exec_command() dogrudan kullanilir (run_command() metni
    utf-8'e decode eder ve ikili veriyi bozar).

    Parola komut metnine gomulmez (shell injection / `ps aux`'ta gorunme
    riski nedeniyle); run_command()'deki ile ayni yontemle stdin uzerinden
    dogrudan iletilir.
    """
    if ssh.client is None:
        print("[-] Once SSH baglantisi kurulmalidir.")
        return None

    dd_cmd = (
        f"dd if={shlex.quote(disk_path)} bs={block_size_mb}M skip={block_no} count=1 "
        f"conv=noerror,sync status=none"
    )

    try:
        if password:
            stdin, stdout, stderr = ssh.client.exec_command(f"sudo -S {dd_cmd}")
            stdin.write(password + "\n")
            stdin.flush()
        else:
            stdin, stdout, stderr = ssh.client.exec_command(
                f"sudo {dd_cmd}", get_pty=True
            )

        raw_data = stdout.read()
        error = stderr.read().decode("utf-8", errors="replace")
        exit_status = stdout.channel.recv_exit_status()

        if exit_status != 0 and error:
            print(f"[-] Blok {block_no} alma hatasi (Kod {exit_status}): {error}")
            return None

        return raw_data

    except Exception as e:
        print(f"[-] Blok {block_no} alinirken beklenmeyen hata: {e}")
        return None


def ensure_connection(ssh, wait_seconds=(1, 2, 4)):
    """
    Transport artik aktif degilse (firewall/NAT/cloud LB tarafindan bosta
    kapatilmis olabilir), baglantiyi ayni kimlik bilgileriyle yeniden
    kurmayi dener. Basarili -> True, tum denemeler basarisiz -> False.

    docs/PROJE_TALIMATI.md madde 6: "3 kez, artan bekleme suresiyle (1sn,
    2sn, 4sn) yeniden baglanmayi dener" — varsayilan wait_seconds bunu
    birebir uygular.

    chain_of_custody.py'de tanimli ama daha once hic kullanilmayan
    EVENT_CONNECTION_LOST / EVENT_CONNECTION_RESUMED tam bu senaryo icin.
    """
    if ssh.is_active():
        return True

    print("[-] SSH baglantisi koptu, yeniden baglaniliyor...")
    coc.log_event(
        coc.EVENT_CONNECTION_LOST,
        "SSH baglantisi koptu (transport artik aktif degil)",
    )

    max_attempts = len(wait_seconds)
    for attempt, wait in enumerate(wait_seconds, start=1):
        time.sleep(wait)
        if ssh.reconnect():
            coc.log_event(
                coc.EVENT_CONNECTION_RESUMED,
                f"SSH baglantisi yeniden kuruldu (deneme {attempt}/{max_attempts})",
            )
            print("[+] SSH baglantisi yeniden kuruldu, kaldigi yerden devam ediliyor.")
            return True

    coc.log_event(
        coc.EVENT_EXAM_ERROR,
        f"SSH baglantisi {max_attempts} denemede yeniden kurulamadi, "
        f"imaj alma durduruluyor",
    )
    return False


def _print_progress(done_blocks, total_blocks, block_size_mb):
    """
    docs/PROJE_TALIMATI.md madde 6 ornegine uygun tek satirlik ilerleme
    cubugu: 'İlerleme: %42 (8.4 GB / 20 GB)' seklinde \\r ile guncellenir.
    """
    if total_blocks <= 0:
        return
    pct = done_blocks * 100 // total_blocks
    done_gb = (done_blocks * block_size_mb) / 1024
    total_gb = (total_blocks * block_size_mb) / 1024
    print(
        f"\rİlerleme: %{pct:3d} ({done_gb:.1f} GB / {total_gb:.1f} GB)",
        end="",
        flush=True,
    )
    if done_blocks >= total_blocks:
        print()


def acquire_disk_image(
    ssh,
    disk_path,
    password,
    output_dir=IMAGE_DIR,
    block_size_mb=BLOCK_SIZE_MB,
    total_blocks=None,
    apply_write_blocker=True,
    start_block=0,
    resume_state=None,
    manifest_path=None,
):
    """
    Uzak diski blok blok cekip her bloğu diske yazmadan once dogrular.

    start_block > 0 verilirse (onceki bir cagridan donen "resume_from"
    degeri), islem EXAM_START yerine EXAM_RESUME ile loglanir ve write-block
    tekrar uygulanmaz varsayilir (disk zaten salt-okunur durumda olmali).
    resume_state verilirse (onceki donus sozlugu), acquired_blocks/
    block_paths bastan baslamak yerine devam ettirilir.

    manifest_path verilmezse yeni bir logs/manifest_<tarih-saat>.json
    dosyasi olusturulur; verilirse (resume durumunda) ayni dosya guncellenir.
    Her basarili/basarisiz bloktan sonra manifest diske yazilir — boylece
    program tamamen kapanip yeniden acilsa bile (main.py ->
    find_incomplete_manifest ile) kaldigi yerden devam edilebilir.

    Donus degeri, concatenate_blocks() ve master hash dogrulamasi icin
    gereken tum bilgiyi tasiyan bir sozluktur:

        {
            "total_blocks": int,
            "acquired_blocks": [int, ...],
            "failed_blocks": [int, ...],
            "block_paths": {int: str},
            "block_size_mb": int,
            "manifest_path": str,
        }

    Write-block basarisiz olursa (veya disk boyutu okunamazsa) None doner
    ve islem hic baslamaz — delil butunlugu ilk adimda garanti edilir.
    """
    os.makedirs(output_dir, exist_ok=True)

    if manifest_path is None:
        manifest_path = _new_manifest_path()

    if start_block > 0:
        coc.log_event(
            coc.EVENT_EXAM_RESUME,
            f"Imaj alma blok {start_block}'dan devam ettiriliyor: {disk_path}",
        )
        # Disk onceki calistirmada salt-okunur yapilmis OLABILIR -- ama
        # blockdev --setro KALICI DEGIL, hedef aradan gecen surede yeniden
        # baslatildiysa disk tekrar yazilabilir hale gelmis olabilir. Hangi
        # modla baslandigi manifestte tutulmadigi icin (bilerek varsayimda
        # bulunmuyoruz) --setro'yu KORU/tekrar dene yerine sadece GERCEK
        # durumu kontrol edip delil zincirine dogru sekilde kaydediyoruz --
        # yorumu (Live'da normal / Offline'da incelenmeli) rapor okuyana birakiyoruz.
        hala_salt_okunur = is_write_blocked(ssh, disk_path, password=password)
        if hala_salt_okunur is True:
            coc.log_event(
                coc.EVENT_WRITE_BLOCK_APPLIED,
                f"Devam ederken kontrol edildi: disk hala salt-okunur: {disk_path}",
            )
        elif hala_salt_okunur is False:
            coc.log_event(
                coc.EVENT_WRITE_BLOCK_SKIPPED,
                f"Devam ederken kontrol edildi: disk salt-okunur DEGIL (Live modda "
                f"beklenen bir durum; Offline modda bekleniyorsa incelenmeli): {disk_path}",
            )
        apply_write_blocker = False
    else:
        coc.log_event(coc.EVENT_EXAM_START, f"Imaj alma baslatildi: {disk_path}")

    if apply_write_blocker:
        if not apply_write_block(ssh, disk_path, password=password):
            print("[-] Write-block uygulanamadi, guvenlik icin islem durduruluyor.")
            coc.log_event(
                coc.EVENT_EXAM_ERROR,
                f"Write-block uygulanamadi, imaj alma durduruldu: {disk_path}",
            )
            return None
    else:
        coc.log_event(
            coc.EVENT_WRITE_BLOCK_SKIPPED,
            f"Write-block atlandi (kullanici tercihi): {disk_path}",
        )

    if total_blocks is None:
        disk_size = get_disk_size_bytes(ssh, disk_path, password=password)
        if disk_size is None:
            print("[-] Disk boyutu okunamadi, islem durduruluyor.")
            coc.log_event(coc.EVENT_EXAM_ERROR, f"Disk boyutu okunamadi: {disk_path}")
            return None
        block_bytes = block_size_mb * 1024 * 1024
        total_blocks = (disk_size + block_bytes - 1) // block_bytes
        print(
            f"[i] Disk boyutu: {disk_size} bayt ({disk_size / (1024**3):.2f} GB) "
            f"-> {total_blocks} blok (blok basi {block_size_mb} MB)"
        )
        coc.log_event(
            coc.EVENT_EXAM_START,
            f"Disk boyutu tespit edildi: {disk_size} bayt, {total_blocks} blok "
            f"planlaniyor: {disk_path}",
        )

    if start_block == 0:
        # Saatler surebilecek bir aktarimin sonda "yerel disk doldu" ile
        # yarim kalmasini onlemek icin -- resume durumunda (start_block > 0)
        # bu kontrol atlanir, o zaten kismen yer kaplamis bir islemi devam
        # ettiriyor.
        needed_bytes = total_blocks * block_size_mb * 1024 * 1024
        free_bytes = shutil.disk_usage(output_dir).free
        if free_bytes < needed_bytes:
            print(
                f"[-] Yerel diskte yeterli bos alan yok: gereken ~"
                f"{needed_bytes / (1024**3):.2f} GB, bos ~{free_bytes / (1024**3):.2f} GB. "
                f"Islem baslatilmiyor."
            )
            coc.log_event(
                coc.EVENT_EXAM_ERROR,
                f"Yerel diskte yeterli bos alan yok (gereken ~{needed_bytes} bayt, "
                f"bos ~{free_bytes} bayt), imaj alma baslatilmadi: {disk_path}",
            )
            return None

    if resume_state:
        acquired_blocks = list(resume_state.get("acquired_blocks", []))
        failed_blocks = list(resume_state.get("failed_blocks", []))
        block_paths = dict(resume_state.get("block_paths", {}))
    else:
        acquired_blocks = []
        failed_blocks = []
        block_paths = {}

    for block_no in range(start_block, total_blocks):
        retry_count = 0
        block_ok = False

        while retry_count <= MAX_RETRY_PER_BLOCK and not block_ok:
            if not ensure_connection(ssh):
                # Baglanti hicbir sekilde geri gelmiyor: burada zorla devam
                # etmek yerine islemi durduruyoruz. Su ana kadar alinan
                # bloklar diskte duruyor; ayni cagriyi start_block=block_no
                # ile tekrar calistirarak kaldigi yerden devam edilebilir.
                coc.log_event(
                    coc.EVENT_EXAM_ERROR,
                    f"Baglanti kurulamadigi icin imaj alma blok {block_no}'da "
                    f"durduruldu (kaldigi yerden devam icin start_block={block_no})",
                )
                print(
                    f"[-] Baglanti kurulamadi. Devam etmek icin scripti "
                    f"start_block={block_no} ile yeniden calistirin."
                )
                return {
                    "total_blocks": total_blocks,
                    "acquired_blocks": acquired_blocks,
                    "failed_blocks": failed_blocks,
                    "block_paths": block_paths,
                    "block_size_mb": block_size_mb,
                    "output_dir": output_dir,
                    "manifest_path": manifest_path,
                    "resume_from": block_no,
                }

            uzak_hash = get_remote_block_hash(
                ssh, disk_path, block_no, block_size_mb, password
            )
            if uzak_hash is None:
                coc.log_event(
                    coc.EVENT_CONNECTION_LOST,
                    f"Blok {block_no} icin uzak hash alinamadi (deneme {retry_count + 1})",
                )
                retry_count += 1
                continue

            veri = acquire_raw_block(ssh, disk_path, block_no, block_size_mb, password)
            if veri is None:
                coc.log_event(
                    coc.EVENT_CONNECTION_LOST,
                    f"Blok {block_no} agdan alinamadi (deneme {retry_count + 1})",
                )
                retry_count += 1
                continue

            try:
                sonuc = verify_chunk(veri, uzak_hash, index=block_no)
            except HashMismatchError as exc:
                coc.log_event(
                    coc.EVENT_HASH_MISMATCH,
                    f"Blok {block_no} bozuk, yeniden isteniyor "
                    f"(deneme {retry_count + 1}/{MAX_RETRY_PER_BLOCK + 1})",
                    exc.actual,
                )
                retry_count += 1
                continue  # blogu yeniden iste, diske YAZMA

            block_path = os.path.join(output_dir, f"block_{block_no:06d}.dd")
            with open(block_path, "wb") as f:
                f.write(veri)

            coc.log_event(
                coc.EVENT_BLOCK_ACQUIRED,
                f"Blok {block_no} alindi ve dogrulandi",
                sonuc.digest,
            )

            block_paths[block_no] = block_path
            acquired_blocks.append(block_no)
            block_ok = True

        if not block_ok:
            failed_blocks.append(block_no)
            print(
                f"[-] Blok {block_no}: {MAX_RETRY_PER_BLOCK + 1} denemede "
                f"basarisiz, atlaniyor."
            )
            coc.log_event(
                coc.EVENT_EXAM_ERROR,
                f"Blok {block_no} {MAX_RETRY_PER_BLOCK + 1} denemede "
                f"alinamadi/dogrulanamadi",
            )

        # Her blok sonrasi (basarili ya da basarisiz) ilerleme goster ve
        # manifest'i guncelle — boylece program kapanip yeniden acilsa bile
        # kaldigi yerden devam edilebilir.
        _print_progress(block_no + 1, total_blocks, block_size_mb)
        _write_manifest(manifest_path, {
            "disk_path": disk_path,
            "total_blocks": total_blocks,
            "block_size_mb": block_size_mb,
            "output_dir": output_dir,
            "acquired_blocks": acquired_blocks,
            "failed_blocks": failed_blocks,
            "block_paths": block_paths,
        })

    coc.log_event(
        coc.EVENT_EXAM_END,
        f"Imaj alma tamamlandi: {len(acquired_blocks)}/{total_blocks} blok "
        f"basarili, {len(failed_blocks)} blok basarisiz",
    )

    if not failed_blocks and len(acquired_blocks) == total_blocks:
        # Tum bloklar eksiksiz alindi, yarim kalmis bir islem olarak
        # tekrar sunulmamasi icin manifest kaldirilir.
        delete_manifest(manifest_path)

    return {
        "total_blocks": total_blocks,
        "acquired_blocks": acquired_blocks,
        "failed_blocks": failed_blocks,
        "block_paths": block_paths,
        "block_size_mb": block_size_mb,
        "output_dir": output_dir,
        "manifest_path": manifest_path,
    }


def concatenate_blocks(block_paths, total_blocks, output_dir=IMAGE_DIR, output_path=None,
                        cleanup=False):
    """
    Sirali kucuk blok dosyalarini tek bir imaj dosyasinda birlestirir.

    output_dir, acquire_disk_image()'in donus degerindeki (sonuc["output_dir"])
    ile ayni klasor olmalidir — aksi halde blok dosyalari bulunamaz.

    Eksik blok varsa (hicbir deneme basarili olmadiysa) birlestirme
    YAPILMAZ ve None doner — yarim/tutarsiz bir imajin butun gibi
    sunulmasi engellenir.

    cleanup=True verilirse, birlestirme basarili olduktan sonra kucuk
    block_*.dd parcalari diskten silinir (aksi halde hem parcalar hem
    birlesik imaj ayni anda durur, imajin 2 kati yer kaplar). Bu SADECE
    "Live Acquisition" DISINDAKI modlarda True gecilmeli -- Live modda
    baglanti kopup devam etmek gerekebilir, parcalar resume icin lazim.
    """
    if output_path is None:
        output_path = os.path.join(output_dir, "full_image.dd")

    for i in range(total_blocks):
        if i not in block_paths:
            print(f"[-] Blok {i} eksik, birlestirme yapilamiyor.")
            return None

    with open(output_path, "wb") as cikti:
        for i in range(total_blocks):
            with open(block_paths[i], "rb") as parca:
                cikti.write(parca.read())

    if cleanup:
        for i in range(total_blocks):
            try:
                os.remove(block_paths[i])
            except OSError as e:
                print(f"[-] Blok {i} dosyasi silinemedi ({block_paths[i]}): {e}")
        print(f"[i] {total_blocks} parca dosyasi temizlendi (birlesik imaj korunuyor).")

    return output_path


def compress_image(image_path, remove_original=True):
    """
    Tamamlanmis, HAM (birlestirilmis) imaji gzip ile sikistirir --
    "<image_path>.gz" olarak yazar. SADECE disk alani tasarrufu icindir;
    delil butunlugu imaj SIKISTIRILMADAN ONCE (bu fonksiyon cagrilmadan
    once) hesaplanmis master hash'e dayanir -- o hash HAM icerige aittir,
    .gz dosyasinin kendi baytlarina degil (rapor/verify_report.py bunu
    acikca belirtir/ hesaba katar).

    remove_original=True (varsayilan): sikistirma basariyla bitince ham
    dosya silinir -- aksi halde hem ham hem sikistirilmis kopya ayni anda
    durur, ozelligin butun amaci (disk alani tasarrufu) bosa cikar.

    Buyuk dosyalarda sabit bellek kullanimi icin akis (streaming) halinde
    kopyalanir -- tum imaj hafizaya yuklenmez.
    """
    compressed_path = image_path + ".gz"
    with open(image_path, "rb") as kaynak, gzip.open(compressed_path, "wb") as hedef:
        shutil.copyfileobj(kaynak, hedef, length=1024 * 1024)

    if remove_original:
        os.remove(image_path)

    return compressed_path


def local_master_hash(image_path):
    """
    Birlestirilmis yerel imajin SHA-256 master hash'ini hesaplar.
    main.verify_image_and_log() ile ayni algoritmayi (hash_verifier.hash_file)
    kullanir; boylece iki modul arasinda tutarsizlik olmaz.
    """
    result = hash_file(image_path)
    return result.digest


def ana_program():
    # Modulu tek basina test etmek icin: diger modullerle (ssh_connector.py,
    # write_block_helper.py) ayni desende input()/getpass ile sorar.
    HOST = input("SSH Host: ").strip()
    PORT_INPUT = input("SSH Port [22]: ").strip()
    PORT = int(PORT_INPUT) if PORT_INPUT else 22
    USERNAME = input("SSH Kullanici adi: ").strip()
    PASSWORD = getpass.getpass(
        "SSH Sifre (bos birakilabilir, NOPASSWD sudo icin): "
    ).strip() or None
    DISK_PATH = input("Hedef disk [/dev/sda]: ").strip() or "/dev/sda"

    if not HOST or not USERNAME:
        print("[HATA] Host ve kullanici adi bos birakilamaz.")
        return

    ssh = SSHConnector(
        host=HOST, port=PORT, username=USERNAME, password=PASSWORD, strict=True
    )

    try:
        if not ssh.connect():
            print("[-] SSH baglantisi kurulamadi.")
            return

        sonuc = acquire_disk_image(ssh, DISK_PATH, PASSWORD)
        if sonuc is None:
            return

        # ensure_connection() zaten her blokta tekrar-baglanmayi dener; ama
        # baglanti bir turlu geri gelmezse acquire_disk_image "resume_from"
        # ile birlikte donup fonksiyondan cikar. Burada bu durumu yakalayip
        # islemi (manuel kapat-ac yerine) otomatik olarak devam ettiriyoruz.
        MAX_RESUME_ATTEMPTS = 20
        resume_attempt = 0
        while "resume_from" in sonuc and resume_attempt < MAX_RESUME_ATTEMPTS:
            resume_attempt += 1
            print(
                f"[i] Baglanti koptu, otomatik devam deneniyor "
                f"({resume_attempt}/{MAX_RESUME_ATTEMPTS}), "
                f"kaldigi blok: {sonuc['resume_from']}"
            )
            sonuc = acquire_disk_image(
                ssh,
                DISK_PATH,
                PASSWORD,
                total_blocks=sonuc["total_blocks"],
                start_block=sonuc["resume_from"],
                resume_state=sonuc,
                manifest_path=sonuc.get("manifest_path"),
            )
            if sonuc is None:
                return

        if "resume_from" in sonuc:
            print(
                f"[-] {MAX_RESUME_ATTEMPTS} otomatik devam denemesinden sonra "
                f"hala baglanti kurulamadi. Blok {sonuc['resume_from']}'dan "
                f"devam etmek icin scripti tekrar calistirin."
            )
            return

        imaj_yolu = concatenate_blocks(
            sonuc["block_paths"], sonuc["total_blocks"], output_dir=sonuc["output_dir"]
        )
        if imaj_yolu is None:
            print("[-] Eksik bloklar nedeniyle imaj birlestirilemedi.")
            return

        master_hash = local_master_hash(imaj_yolu)
        print(f"[+] Imaj tamamlandi: {imaj_yolu}")
        print(f"[+] Yerel master SHA-256: {master_hash}")
        print("[i] Master hash'i uzak diskin hash'iyle karsilastirmak icin "
              "main.py -> Verify Image (secenek 3) kullanilabilir.")

    finally:
        ssh.close()


if __name__ == "__main__":
    ana_program()