"""
windows_acquirer.py
SSH uzerinden Windows hedeften disk ve dosya/klasor almak icin modul --
file_acquirer.py/image_acquirer.py'nin (Linux/bash) PowerShell karsiligi.
Ayni "once dogrula, sonra yaz" mantigi, ayni chain_of_custody kullanimi.

Neden farkli: Windows'ta dd/blockdev/sha256sum/find/cat yok, PowerShell
kullanilir. Ham veri (disk blogu ya da dosya icerigi) SSH'nin metin
kanalindan bozulmadan gecebilmesi icin Base64 ile kodlanip gonderilir --
Linux tarafindaki gibi ayri bir "ham bayt kanali" (exec_command dogrudan)
gerekmez, tek tip run_command() yeterli olur.

Guvenlik: kullanicidan gelen her yol powershell_quote() ile kacirilir --
shlex.quote'un PowerShell karsiligi. Bu olmadan f-string ile komuta
gomulen bir yol, ic ice PowerShell komutu calistirilmasina (enjeksiyon)
yol acar (bkz. image_acquirer.py'deki shlex.quote duzeltmesi, ayni sinif
risk burada da gecerli).
"""

import base64
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone

import chain_of_custody as coc
from image_acquirer import (
    _new_manifest_path,
    _new_tree_manifest_path,
    _write_manifest,
    delete_manifest,
    ensure_connection,
)

MAX_RETRY_PER_BLOCK = 3
# bkz. file_acquirer.LOGICAL_MANIFEST_EVERY (dongusel import olmasin diye burada tekrar)
LOGICAL_MANIFEST_EVERY = 100


def powershell_quote(value):
    """
    PowerShell tek tirnakli string icin guvenli kacirma: icerideki her tek
    tirnak (') iki tek tirnaga ('') cevrilir, sonuc tek tirnak icine
    alinir. Boylece kullanicidan gelen bir yolun icine gizlenmis ; ya da
    baska bir PowerShell komutu, ayri bir komut olarak calismaz -- hep tek
    parca bir string degeri olarak kalir.
    """
    return "'" + str(value).replace("'", "''") + "'"


# ---------------------------------------------------------------------------
# Disk (tam fiziksel disk) -- PhysicalDrive numarasi ile calisir
# ---------------------------------------------------------------------------
def apply_write_block_windows(ssh, disk_number):
    """blockdev --setro karsiligi: Set-Disk -IsReadOnly $true + dogrulama."""
    cmd = (
        f"Set-Disk -Number {int(disk_number)} -IsReadOnly $true; "
        f"(Get-Disk -Number {int(disk_number)}).IsReadOnly"
    )
    out, _err, _code = ssh.run_command(cmd)
    basarili = (out or "").strip().lower() == "true"
    if basarili:
        coc.log_event(
            coc.EVENT_WRITE_BLOCK_APPLIED,
            f"Disk salt-okunur yapildi (Windows): PhysicalDrive{disk_number}",
        )
    else:
        coc.log_event(
            coc.EVENT_EXAM_ERROR,
            f"Write-block basarisiz (Windows): PhysicalDrive{disk_number}",
        )
    return basarili


def is_write_blocked_windows(ssh, disk_number):
    """apply_write_block_windows()'un aksine hicbir sey DEGISTIRMEZ, SADECE
    diskin O ANDA salt-okunur olup olmadigini kontrol eder -- resume
    sirasinda "onceden oyleydi, hala oyledir" varsayimini korumak yerine
    gercekten dogrulamak icin (bkz. write_block_helper.is_write_blocked,
    ayni gerekce -- Windows'ta da bu ayar reboot'ta kalici degil).
    Donus: True/False, ya da None (kontrol edilemedi -- SSH hatasi)."""
    out, _err, _code = ssh.run_command(f"(Get-Disk -Number {int(disk_number)}).IsReadOnly")
    if out is None:
        return None
    return out.strip().lower() == "true"


def get_disk_size_bytes_windows(ssh, disk_number):
    cmd = f"(Get-Disk -Number {int(disk_number)}).Size"
    out, _err, _code = ssh.run_command(cmd)
    try:
        return int((out or "").strip())
    except (ValueError, AttributeError):
        return None


def get_disk_description_windows(ssh, disk_number):
    """image_acquirer.get_disk_description ile ayni amac (Windows karsiligi):
    diskin model/seri numarasini alir. ConvertTo-Json kullanilir -- FriendlyName
    genelde bosluk icerir (orn. "Virtual HD"), duz metin ciktisi guvenilir
    parse edilemez."""
    cmd = (
        f"(Get-Disk -Number {int(disk_number)} | "
        f"Select-Object -Property FriendlyName,SerialNumber | ConvertTo-Json -Compress)"
    )
    out, _err, _code = ssh.run_command(cmd)
    if not out:
        return ""
    try:
        data = json.loads(out.strip())
    except (ValueError, TypeError):
        return ""
    model_val = str(data.get("FriendlyName") or "").strip()
    serial_val = str(data.get("SerialNumber") or "").strip()
    parts = []
    if model_val:
        parts.append(f"Model: {model_val}")
    if serial_val:
        parts.append(f"Seri No: {serial_val}")
    return ", ".join(parts)


def _block_read_script(disk_number, offset, length):
    """Belirtilen fiziksel diskten offset..offset+length araligini okuyan
    ortak PowerShell govdesi. $buf degiskeninde ham bayt kalir."""
    return (
        f"$fs = [System.IO.File]::Open('\\\\.\\PhysicalDrive{int(disk_number)}', "
        f"'Open', 'Read', 'ReadWrite'); "
        f"$fs.Seek({offset}, 'Begin') | Out-Null; "
        f"$buf = New-Object byte[] {length}; "
        f"$read = $fs.Read($buf, 0, {length}); "
        f"$fs.Close(); "
        # $read = 0 (orn. bozuk USB koprusu) icin $buf[0..($read-1)] = $buf[0..-1]
        # PowerShell'de BOS DIZI degil 1 ELEMANLI ($buf[0], yani 0x00) bir dizi
        # doner -- "sahte" bu tek bayt, bagimsiz okunan iki kopyada (hash +
        # veri) AYNI sekilde uretilip hash karsilastirmasini YANLISLIKLA
        # gecirir. $read=0 durumu ayrica ele alinip GERCEKTEN bos dizi dondurulur.
        f"if ($read -le 0) {{ $buf = [byte[]]@() }} elseif ($read -lt {length}) {{ $buf = $buf[0..($read-1)] }}; "
    )


def get_remote_block_hash_windows(ssh, disk_number, block_no, block_size_mb):
    """Blogu SUNUCUDA hashler, veri gondermez -- sadece SHA-256 hex doner."""
    if getattr(ssh, "is_local", False):
        # Yerel mod: PowerShell yerine dogrudan okuma (bkz. local_connector).
        # Ayni blok acquire_raw_block_windows'ta BAGIMSIZ olarak bir kez daha
        # okunup karsilastirilir -- kararsiz okumayi (bozuk USB koprusu vb.)
        # yakalayan uzak moddaki kontrolun aynisi.
        from local_connector import read_local_block
        veri = read_local_block(ssh, disk_number, block_no, block_size_mb)
        return hashlib.sha256(veri).hexdigest() if veri is not None else None
    offset = block_no * block_size_mb * 1024 * 1024
    length = block_size_mb * 1024 * 1024
    ps = (
        _block_read_script(disk_number, offset, length)
        + "$sha = [System.Security.Cryptography.SHA256]::Create(); "
        + "$hash = $sha.ComputeHash($buf); "
        + "[System.BitConverter]::ToString($hash).Replace('-','').ToLower()"
    )
    out, _err, _code = ssh.run_command(ps)
    out = (out or "").strip()
    return out or None


def acquire_raw_block_windows(ssh, disk_number, block_no, block_size_mb):
    """Blogu Base64 olarak ceker (SSH metin kanalindan guvenle gecsin diye)."""
    if getattr(ssh, "is_local", False):
        from local_connector import read_local_block
        return read_local_block(ssh, disk_number, block_no, block_size_mb)
    offset = block_no * block_size_mb * 1024 * 1024
    length = block_size_mb * 1024 * 1024
    ps = _block_read_script(disk_number, offset, length) + "[Convert]::ToBase64String($buf)"
    out, _err, _code = ssh.run_command(ps)
    if not out:
        return None
    try:
        return base64.b64decode(out.strip())
    except Exception:
        return None


def acquire_disk_image_windows(
    ssh,
    disk_number,
    output_dir,
    block_size_mb=4,
    total_blocks=None,
    apply_write_blocker=True,
    start_block=0,
    resume_state=None,
    manifest_path=None,
    progress_callback=None,
    host=None,
    should_stop=None,
):
    """
    image_acquirer.acquire_disk_image ile ayni akis (write-block -> her
    blok icin uzak hash + veri + dogrulama -> manifest), Windows/PowerShell
    komutlarini kullanir. concatenate_blocks/local_master_hash/
    find_incomplete_manifest OS'a bagli olmadigi icin image_acquirer.py'den
    aynen kullanilabilir.
    """
    os.makedirs(output_dir, exist_ok=True)
    if manifest_path is None:
        manifest_path = _new_manifest_path()

    # bkz. image_acquirer.py'deki AYNI gerekce: "Yarim Kalanlar" listesinde
    # gosterilebilmesi icin, resume'da ORIJINAL baslangic zamani korunur.
    started_at_utc = (resume_state or {}).get("started_at_utc") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if start_block > 0:
        coc.log_event(
            coc.EVENT_EXAM_RESUME,
            f"Imaj alma blok {start_block}'dan devam ettiriliyor (Windows): PhysicalDrive{disk_number}",
        )
        # bkz. image_acquirer.py'deki AYNI duzeltme: -IsReadOnly reboot'ta
        # kalici degil, "onceden oyleydi" varsaymak yerine gercek durumu
        # kontrol edip delil zincirine kaydediyoruz.
        hala_salt_okunur = is_write_blocked_windows(ssh, disk_number)
        if hala_salt_okunur is True:
            coc.log_event(
                coc.EVENT_WRITE_BLOCK_APPLIED,
                f"Devam ederken kontrol edildi (Windows): disk hala salt-okunur: PhysicalDrive{disk_number}",
            )
        elif hala_salt_okunur is False:
            coc.log_event(
                coc.EVENT_WRITE_BLOCK_SKIPPED,
                f"Devam ederken kontrol edildi (Windows): disk salt-okunur DEGIL "
                f"(Live modda beklenen bir durum; Offline modda bekleniyorsa incelenmeli): "
                f"PhysicalDrive{disk_number}",
            )
        elif hala_salt_okunur is None:
            # SSH cagrisi basarisiz oldu -- diskin o anki durumu BILINMIYOR.
            # True/False dallarinin amaci bu durumu delil zincirine kaydetmekti;
            # sessizce atlanirsa "hala salt-okunur mu?" sorusu icin HICBIR
            # kayit kalmaz, oysa tam bu yuzden kontrol ediliyordu.
            coc.log_event(
                coc.EVENT_EXAM_ERROR,
                f"Devam ederken kontrol edilemedi (Windows, SSH hatasi): disk "
                f"PhysicalDrive{disk_number}'in salt-okunur durumu DOGRULANAMADI, "
                f"delil zincirine bakilmali",
            )
        apply_write_blocker = False
    else:
        coc.log_event(coc.EVENT_EXAM_START, f"Imaj alma baslatildi (Windows): PhysicalDrive{disk_number}")

    if apply_write_blocker:
        if not apply_write_block_windows(ssh, disk_number):
            coc.log_event(
                coc.EVENT_EXAM_ERROR,
                f"Write-block uygulanamadi, imaj alma durduruldu (Windows): PhysicalDrive{disk_number}",
            )
            return None
    elif start_block == 0:
        # bkz. image_acquirer.py'deki AYNI duzeltme -- start_block > 0
        # (resume) durumu yukarida (satir ~191-212) zaten GERCEK sebeple
        # ayrica logland, burada tekrar "kullanici tercihi" YANLIS olurdu.
        coc.log_event(
            coc.EVENT_WRITE_BLOCK_SKIPPED,
            f"Write-block atlandi (Windows, kullanici tercihi): PhysicalDrive{disk_number}",
        )

    if total_blocks is None:
        disk_size = get_disk_size_bytes_windows(ssh, disk_number)
        if disk_size is None:
            coc.log_event(coc.EVENT_EXAM_ERROR, f"Disk boyutu okunamadi (Windows): PhysicalDrive{disk_number}")
            return None
        block_bytes = block_size_mb * 1024 * 1024
        total_blocks = (disk_size + block_bytes - 1) // block_bytes

    if start_block == 0:
        # bkz. image_acquirer.py'deki AYNI kontrol: saatler surebilecek bir
        # aktarimin sonda "yerel disk doldu" ile yarim kalmasini onler.
        needed_bytes = total_blocks * block_size_mb * 1024 * 1024
        free_bytes = shutil.disk_usage(output_dir).free
        if free_bytes < needed_bytes:
            coc.log_event(
                coc.EVENT_EXAM_ERROR,
                f"Yerel diskte yeterli bos alan yok (gereken ~{needed_bytes} bayt, "
                f"bos ~{free_bytes} bayt), imaj alma baslatilmadi (Windows): "
                f"PhysicalDrive{disk_number}",
            )
            return None

    if resume_state:
        acquired_blocks = list(resume_state.get("acquired_blocks", []))
        failed_blocks = list(resume_state.get("failed_blocks", []))
        # json.load'dan gelen manifestte anahtarlar STRING'dir ("0", "1", ...) --
        # int'e cevrilmezse asagida YENI eklenen (int anahtarli) bloklarla
        # karisir ve concatenate_blocks/write_segments'teki "i not in
        # block_paths" (int i) kontrolu resume ONCESI alinan hicbir blogu
        # BULAMAZ (hepsi "eksik" sayilir, oysa hepsi diskte ve dogrulanmis).
        block_paths = {int(k): v for k, v in resume_state.get("block_paths", {}).items()}
    else:
        acquired_blocks = []
        failed_blocks = []
        block_paths = {}

    for block_no in range(start_block, total_blocks):
        if should_stop and should_stop():
            coc.log_event(
                coc.EVENT_EXAM_STOPPED,
                f"Imaj alma kullanici tarafindan durduruldu, blok {block_no}'da "
                f"(Windows, kaldigi yerden devam icin start_block={block_no})",
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
                "user_stopped": True,
                "started_at_utc": started_at_utc,
            }

        retry_count = 0
        block_ok = False

        while retry_count <= MAX_RETRY_PER_BLOCK and not block_ok:
            if not ensure_connection(ssh):
                # Baglanti hicbir sekilde geri gelmiyor: burada zorla devam
                # etmek yerine islemi durduruyoruz -- ayni image_acquirer.py
                # deseni. Su ana kadar alinan bloklar diskte duruyor; ayni
                # cagriyi start_block=block_no ile tekrar calistirarak
                # kaldigi yerden devam edilebilir.
                coc.log_event(
                    coc.EVENT_EXAM_ERROR,
                    f"Baglanti kurulamadigi icin imaj alma blok {block_no}'da durduruldu "
                    f"(Windows, kaldigi yerden devam icin start_block={block_no})",
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
                    "started_at_utc": started_at_utc,
                }

            uzak_hash = get_remote_block_hash_windows(ssh, disk_number, block_no, block_size_mb)
            if uzak_hash is None:
                coc.log_event(
                    coc.EVENT_CONNECTION_LOST,
                    f"Blok {block_no} icin uzak hash alinamadi (Windows, deneme {retry_count + 1})",
                )
                retry_count += 1
                continue

            veri = acquire_raw_block_windows(ssh, disk_number, block_no, block_size_mb)
            if veri is None:
                coc.log_event(
                    coc.EVENT_CONNECTION_LOST,
                    f"Blok {block_no} agdan alinamadi (Windows, deneme {retry_count + 1})",
                )
                retry_count += 1
                continue

            gercek_hash = hashlib.sha256(veri).hexdigest()
            if gercek_hash != uzak_hash:
                coc.log_event(
                    coc.EVENT_HASH_MISMATCH,
                    f"Blok {block_no} bozuk, yeniden isteniyor (Windows, "
                    f"deneme {retry_count + 1}/{MAX_RETRY_PER_BLOCK + 1})",
                    gercek_hash,
                )
                retry_count += 1
                continue

            block_path = os.path.join(output_dir, f"block_{block_no:06d}.dd")
            with open(block_path, "wb") as f:
                f.write(veri)

            coc.log_event(coc.EVENT_BLOCK_ACQUIRED, f"Blok {block_no} alindi ve dogrulandi (Windows)", gercek_hash)
            block_paths[block_no] = block_path
            acquired_blocks.append(block_no)
            block_ok = True

        if not block_ok:
            failed_blocks.append(block_no)
            coc.log_event(
                coc.EVENT_EXAM_ERROR,
                f"Blok {block_no} {MAX_RETRY_PER_BLOCK + 1} denemede alinamadi/dogrulanamadi (Windows)",
            )

        if progress_callback:
            progress_callback(block_no + 1, total_blocks)

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump({
                "disk_path": f"PhysicalDrive{disk_number}",
                "total_blocks": total_blocks,
                "block_size_mb": block_size_mb,
                "output_dir": output_dir,
                "acquired_blocks": acquired_blocks,
                "failed_blocks": failed_blocks,
                "block_paths": block_paths,
                "host": host,
                "started_at_utc": started_at_utc,
                "target_os": "windows",
            }, f, indent=2)

    coc.log_event(
        coc.EVENT_EXAM_END,
        f"Imaj alma tamamlandi (Windows): {len(acquired_blocks)}/{total_blocks} blok basarili, "
        f"{len(failed_blocks)} blok basarisiz",
    )

    if not failed_blocks and len(acquired_blocks) == total_blocks:
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


# ---------------------------------------------------------------------------
# Dosya/Klasor
# ---------------------------------------------------------------------------
def remote_path_kind_windows(ssh, remote_path):
    safe = powershell_quote(remote_path)
    ps = (
        f"if (Test-Path -LiteralPath {safe} -PathType Leaf) {{ 'FILE' }} "
        f"elseif (Test-Path -LiteralPath {safe} -PathType Container) {{ 'DIR' }} "
        f"else {{ 'NONE' }}"
    )
    out, _err, _code = ssh.run_command(ps)
    out = (out or "").strip()
    return {"FILE": "file", "DIR": "dir"}.get(out)


def list_remote_directory_windows(ssh, remote_path):
    """
    file_acquirer.list_remote_directory ile ayni davranis, PowerShell ile.
    remote_path'in DOGRUDAN alt ogelerini doner, salt-okunur (Get-ChildItem),
    hicbir sey yazmiyor/degistirmiyor. Her cagri chain-of-custody'ye
    DIRECTORY_LISTED olarak islenir.

    Donus: [(isim, is_dir), ...] -- klasorler once, sonra dosyalar.
    """
    safe = powershell_quote(remote_path)
    ps = (
        f"Get-ChildItem -LiteralPath {safe} -Force -ErrorAction SilentlyContinue | "
        "ForEach-Object { $t = if ($_.PSIsContainer) { 'd' } else { 'f' }; \"$t $($_.Name)\" }"
    )
    out, _err, _code = ssh.run_command(ps)
    if out is None:
        return None

    entries = []
    for line in out.splitlines():
        line = line.rstrip("\r\n")
        if not line or " " not in line:
            continue
        type_char, name = line.split(" ", 1)
        entries.append((name, type_char == "d"))
    entries.sort(key=lambda e: (not e[1], e[0].lower()))

    coc.log_event(coc.EVENT_DIRECTORY_LISTED, f"Klasor listelendi (Windows): {remote_path}")
    return entries


def list_remote_files_windows(ssh, remote_dir):
    safe = powershell_quote(remote_dir)
    ps = f"Get-ChildItem -LiteralPath {safe} -Recurse -File | ForEach-Object {{ $_.FullName }}"
    out, _err, _code = ssh.run_command(ps)
    if not out:
        return []
    return [satir for satir in out.splitlines() if satir.strip()]


def get_remote_file_hash_windows(ssh, remote_path):
    safe = powershell_quote(remote_path)
    ps = f"(Get-FileHash -LiteralPath {safe} -Algorithm SHA256).Hash.ToLower()"
    out, _err, _code = ssh.run_command(ps)
    out = (out or "").strip()
    return out or None


# Mantiksal imaj (docs/roadmap.md madde 0.5) icin: dosya sistemini tarayip
# HER dosyayi alan bir modda tek `ReadAllBytes` cagrisi iki sorunlu --
# birkac GB'lik bir dosya bellege sigmaz / .NET'in 2 GB dizi sinirina takilir,
# ve File.ReadAllBytes paylasimi kisitli acar (baska bir islem yazmak icin
# actiysa, orn. calisan bir log dosyasi, okuyamaz). Bu yuzden dosyalar
# FileShare ReadWrite+Delete ile acilir; kucuk dosyalar TEK bir SSH
# cagrisinda (hash+veri birlikte), buyukler Linux tarafiyla AYNI blok+
# dogrulama desenini kullanir.
SMALL_FILE_LIMIT = 4 * 1024 * 1024
FILE_BLOCK_MB = 4

# HResult -> sebep. Hata METNI yerine istisna turu/HResult kullaniliyor:
# metin isletim sisteminin diline gore degisir (Turkce Windows'ta Turkce).
_HRESULT_REASONS = {
    -2147024864: "kilitli (baska bir islem kullaniyor)",   # ERROR_SHARING_VIOLATION
    -2147024863: "kilitli (baska bir islem kullaniyor)",   # ERROR_LOCK_VIOLATION
}


def _explain_ps_error(type_name, hresult):
    if type_name == "UnauthorizedAccessException":
        return "izin yok (erisim engellendi)"
    if type_name in ("FileNotFoundException", "DirectoryNotFoundException"):
        return "dosya alma sirasinda kayboldu"
    try:
        sebep = _HRESULT_REASONS.get(int(hresult))
    except (TypeError, ValueError):
        sebep = None
    return sebep or f"okuma hatasi ({type_name})"


# Bu sebepler tekrar denemekle duzelmez -- yeniden deneme dongusu bosuna
# zaman kaybetmesin (binlerce kilitli dosyali bir sistem imajinda onemli).
_PERMANENT_REASON_PREFIXES = ("kilitli", "izin yok", "dosya alma sirasinda kayboldu")


def _parse_ps_error(out):
    """'ERR|<TurAdi>|<HResult>' ise sebep metnini, degilse None doner."""
    if not out or not out.startswith("ERR|"):
        return None
    parcalar = out.split("|", 2)
    tur = parcalar[1] if len(parcalar) > 1 else ""
    hresult = parcalar[2] if len(parcalar) > 2 else ""
    return _explain_ps_error(tur, hresult)


def _file_open_prefix(path):
    return (
        f"$ErrorActionPreference = 'Stop'; try {{ "
        f"$fs = [System.IO.File]::Open({powershell_quote(path)}, 'Open', 'Read', 'ReadWrite, Delete'); "
        f"try {{ "
    )


# PowerShell .NET metot cagrisindaki istisnalari MethodInvocationException
# icine sarar -- gercek tur/HResult InnerException'dadir (gercek PowerShell'le
# calisan tests/test_logical_imaging.py'nin yakaladigi bir hata).
_FILE_CLOSE_SUFFIX = (
    " } finally { $fs.Close() } "
    "} catch { $x = $_.Exception; if ($x.InnerException) { $x = $x.InnerException }; "
    "'ERR|' + $x.GetType().Name + '|' + $x.HResult }"
)

# $buf'a $len bayt (dosya bitene kadar) doldurur -- FileStream.Read'in tek
# cagrida tam okumasi garanti degildir.
_FILL_BUF = (
    "$r = 0; while ($r -lt $len) { $n = $fs.Read($buf, $r, $len - $r); if ($n -le 0) { break }; $r += $n }; "
)
_HASH_BUF = (
    "$h = [System.BitConverter]::ToString("
    "[System.Security.Cryptography.SHA256]::Create().ComputeHash($buf, 0, $r)).Replace('-','').ToLower(); "
)


def _small_or_large_script(path):
    return (
        _file_open_prefix(path)
        + f"$len = $fs.Length; if ($len -le {SMALL_FILE_LIMIT}) {{ $buf = New-Object byte[] $len; "
        + _FILL_BUF + _HASH_BUF
        + "'S|' + $h + '|' + [Convert]::ToBase64String($buf, 0, $r) } else { 'L|' + $len }"
        + _FILE_CLOSE_SUFFIX
    )


def _file_block_script(path, offset, length, want_data):
    cikti = "[Convert]::ToBase64String($buf, 0, $r)" if want_data else "$h"
    return (
        _file_open_prefix(path)
        + f"$fs.Seek({offset}, 'Begin') | Out-Null; $len = {length}; $buf = New-Object byte[] $len; "
        + _FILL_BUF + ("" if want_data else _HASH_BUF)
        + cikti
        + _FILE_CLOSE_SUFFIX
    )


def acquire_remote_file_windows(ssh, remote_path, local_path, reason_out=None):
    """
    Dosyayi alir, yazmadan ONCE hash dogrular. Kucuk dosya (<= 4 MB) TEK SSH
    cagrisinda; buyuk dosya blok blok (Linux'taki acquire_remote_file ile AYNI
    desen: uzak hash -> veri -> yerel dogrulama, blok basina yeniden deneme,
    baglanti koparsa KALDIGI BLOKTAN devam).

    reason_out (dict) verilirse basarisizlikta reason_out["reason"]'a kisa bir
    sebep yazilir (kilitli/izin yok/...) -- mantiksal imaj raporu icin.
    Donus: (basarili, sha256_veya_None) -- imza eskiyle AYNI.
    """
    def _fail(sebep):
        if reason_out is not None:
            reason_out["reason"] = sebep
        return False, None

    def _run(ps):
        return (ssh.run_command(ps)[0] or "").strip()

    if getattr(ssh, "client", True) is None:
        return _fail("baglanti yok")

    ilk = None
    for _ in range(MAX_RETRY_PER_BLOCK + 1):
        if not ensure_connection(ssh):
            return _fail("baglanti koptu")
        ilk = _run(_small_or_large_script(remote_path))
        sebep = _parse_ps_error(ilk)
        if sebep and sebep.startswith(_PERMANENT_REASON_PREFIXES):
            return _fail(sebep)
        if ilk and not sebep:
            break
    else:
        return _fail(_parse_ps_error(ilk) or "okuma/dogrulama hatasi")

    os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)

    if ilk.startswith("S|"):
        parcalar = ilk.split("|", 2)
        try:
            veri = base64.b64decode(parcalar[2]) if len(parcalar) > 2 else b""
        except Exception:
            return _fail("okuma/dogrulama hatasi")
        gercek_hash = hashlib.sha256(veri).hexdigest()
        if gercek_hash != parcalar[1]:
            return _fail("dogrulama hatasi (hash uyusmuyor)")
        with open(local_path, "wb") as f:
            f.write(veri)
        return True, gercek_hash

    if not ilk.startswith("L|"):
        return _fail("okuma/dogrulama hatasi")

    try:
        boyut = int(ilk.split("|", 1)[1])
    except ValueError:
        return _fail("okuma/dogrulama hatasi")

    block_bytes = FILE_BLOCK_MB * 1024 * 1024
    total_blocks = (boyut + block_bytes - 1) // block_bytes
    hasher = hashlib.sha256()
    with open(local_path, "wb") as cikti:
        for block_no in range(total_blocks):
            offset = block_no * block_bytes
            length = min(block_bytes, boyut - offset)
            veri = None
            for _ in range(MAX_RETRY_PER_BLOCK + 1):
                if not ensure_connection(ssh):
                    break
                uzak_hash = _run(_file_block_script(remote_path, offset, length, want_data=False))
                if not uzak_hash or uzak_hash.startswith("ERR|"):
                    continue
                b64 = _run(_file_block_script(remote_path, offset, length, want_data=True))
                if not b64 or b64.startswith("ERR|"):
                    continue
                try:
                    aday = base64.b64decode(b64)
                except Exception:
                    continue
                if hashlib.sha256(aday).hexdigest() == uzak_hash:
                    veri = aday
                    break
            if veri is None:
                cikti.close()
                try:
                    os.remove(local_path)  # yarim/dogrulanmamis dosya gercek bir kopya gibi durmasin
                except OSError:
                    pass
                return _fail(f"blok {block_no} okunamadi/dogrulanamadi")
            cikti.write(veri)
            hasher.update(veri)
    return True, hasher.hexdigest()


# ---------------------------------------------------------------------------
# Mantiksal imaj (docs/roadmap.md madde 0.5)
# ---------------------------------------------------------------------------
# Hacim kokundeki, SISTEM tarafindan surekli acik/kilitli tutulan dosyalar --
# canli sistemde okunamazlar, imaj icinde anlam tasimazlar. Bilerek
# dislanir ve raporda "dislanan" olarak ayri listelenir (basarisiz DEGIL).
_WINDOWS_EXCLUDED_ROOT_FILES = {
    "pagefile.sys": "sanal bellek dosyasi (surekli kilitli)",
    "hiberfil.sys": "hazirda bekletme dosyasi (surekli kilitli)",
    "swapfile.sys": "uygulama takas dosyasi (surekli kilitli)",
}
_WINDOWS_EXCLUDED_DIR_NAME = "system volume information"


def _logical_walk_script(root):
    """Yansima noktalarini (junction/symlink -- dongu riski) ATLAYAN, gizli/
    sistem ogeleri (-Force) DAHIL, erisilemeyen klasorleri 'ERR|' ile
    raporlayan ozyinelemeli tarama. Cikti satirlari: F|<dosya>, ERR|<klasor>,
    SKIP|<klasor>."""
    return (
        "$ErrorActionPreference = 'SilentlyContinue'; "
        "function W($d) { $e = $null; "
        "$items = Get-ChildItem -LiteralPath $d -Force -ErrorVariable e -ErrorAction SilentlyContinue; "
        "if ($e) { 'ERR|' + $d }; "
        "foreach ($i in $items) { "
        "if ($i.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { continue }; "
        "if ($i.PSIsContainer) { "
        f"if ($i.Name -ieq '{_WINDOWS_EXCLUDED_DIR_NAME}') {{ 'SKIP|' + $i.FullName }} else {{ W $i.FullName }} "
        "} else { 'F|' + $i.FullName } } }; "
        f"W {powershell_quote(root)}"
    )


def list_logical_files_windows(ssh, remote_root, password=None):
    """file_acquirer.list_logical_files'in Windows karsiligi -- bkz. orasi.
    Donus: (dosyalar, onceden_basarisiz, dislanan) -- ikisi de {yol: sebep}."""
    out, _err, _code = ssh.run_command(_logical_walk_script(remote_root))
    kok = remote_root.rstrip("\\/").lower()
    dosyalar, onceden_basarisiz, dislanan = [], {}, {}
    for satir in (out or "").splitlines():
        satir = satir.rstrip("\r\n")
        tur, _, yol = satir.partition("|")
        if not yol:
            continue
        if tur == "F":
            # Sadece hacim KOKUNDEKI sistem dosyalari dislanir (baska bir
            # klasordeki ayni adli bir dosya normal bir kullanici dosyasidir).
            rel = yol[len(kok) + 1:] if yol.lower().startswith(kok + "\\") else None
            if rel is not None and "\\" not in rel and rel.lower() in _WINDOWS_EXCLUDED_ROOT_FILES:
                dislanan[yol] = _WINDOWS_EXCLUDED_ROOT_FILES[rel.lower()]
            else:
                dosyalar.append(yol)
        elif tur == "ERR":
            onceden_basarisiz[yol] = "klasor okunamadi (izin yok)"
        elif tur == "SKIP":
            dislanan[yol] = "sistem klasoru (erisim kisitli, degisken)"
    return dosyalar, onceden_basarisiz, dislanan


def acquire_remote_tree_windows(ssh, remote_root, output_dir, progress_callback=None,
                                 manifest_path=None, resume_state=None, host=None,
                                 file_lister=None, manifest_every=1, mode="file", should_stop=None):
    """file_acquirer.acquire_remote_tree ile ayni davranis (resume destegi
    dahil, bkz. o fonksiyonun docstring'i -- docs/roadmap.md madde 0.4),
    Windows yollari (ters slash) ve PowerShell komutlariyla.
    file_lister/manifest_every/mode: mantiksal imaj icin, bkz. orasi.
    should_stop: bkz. file_acquirer.acquire_remote_tree docstring'i (AYNI)."""
    kind = remote_path_kind_windows(ssh, remote_root)
    if kind is None:
        coc.log_event(coc.EVENT_EXAM_ERROR, f"Yol bulunamadi (Windows): {remote_root}")
        return None

    norm_root = remote_root.replace("\\", "/")
    onceden_basarisiz = {}
    dislanan = {}
    if kind == "file":
        dosyalar = [remote_root]
        taban = norm_root.rsplit("/", 1)[0] if "/" in norm_root else ""
    elif file_lister is not None:
        dosyalar, onceden_basarisiz, dislanan = file_lister(ssh, remote_root, None)
        taban = norm_root
    else:
        dosyalar = list_remote_files_windows(ssh, remote_root)
        taban = norm_root

    if manifest_path is None:
        manifest_path = _new_tree_manifest_path()

    onceden_alinan = set((resume_state or {}).get("acquired_files", []))
    started_at_utc = (resume_state or {}).get("started_at_utc") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if onceden_alinan:
        coc.log_event(
            coc.EVENT_EXAM_RESUME,
            f"Dosya/klasor alma devam ettiriliyor (Windows): {remote_root} "
            f"({len(onceden_alinan)}/{len(dosyalar)} zaten tamamlanmis)",
        )
    else:
        coc.log_event(
            coc.EVENT_EXAM_START,
            f"Dosya/klasor alma baslatildi (Windows): {remote_root} ({len(dosyalar)} dosya)",
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
            f"{n_pre} klasor okunamadigi icin (izin yok) taranamadi (Windows): {remote_root}",
        )
    if dislanan:
        coc.log_event(
            coc.EVENT_LOGICAL_EXCLUSIONS,
            f"{len(dislanan)} oge bilerek dislandi (kilitli/degisken sistem ogesi, Windows): {remote_root}",
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
            _yaz_kalici_manifest()
            coc.log_event(
                coc.EVENT_EXAM_STOPPED,
                f"Dosya/klasor alma kullanici tarafindan durduruldu (Windows): {remote_root} "
                f"({len(acquired_files)}/{toplam})",
            )
            break

        if uzak_dosya in onceden_alinan:
            if progress_callback:
                progress_callback(i + n_pre, toplam)
            continue

        norm_dosya = uzak_dosya.replace("\\", "/")
        goreli = os.path.relpath(norm_dosya, taban) if taban else os.path.basename(norm_dosya)
        goreli = goreli.replace("/", os.sep)
        yerel_dosya = os.path.join(output_dir, goreli)

        sebep_bilgisi = {}
        basarili, hash_deger = acquire_remote_file_windows(ssh, uzak_dosya, yerel_dosya, reason_out=sebep_bilgisi)
        if basarili:
            sonuclar.append({"remote_path": uzak_dosya, "local_path": yerel_dosya, "sha256": hash_deger})
            acquired_files.append(uzak_dosya)
            coc.log_event(coc.EVENT_BLOCK_ACQUIRED, f"Dosya alindi ve dogrulandi (Windows): {uzak_dosya}", hash_deger)
        else:
            basarisiz.append(uzak_dosya)
            failed_reasons[uzak_dosya] = sebep_bilgisi.get("reason", "okuma/dogrulama hatasi")
            coc.log_event(
                coc.EVENT_EXAM_ERROR,
                f"Dosya alinamadi/dogrulanamadi (Windows, {failed_reasons[uzak_dosya]}): {uzak_dosya}",
            )

        if i % manifest_every == 0:
            _yaz_kalici_manifest()

        if progress_callback:
            progress_callback(i + n_pre, toplam)

    if not durduruldu:
        coc.log_event(
            coc.EVENT_EXAM_END,
            f"Dosya/klasor alma tamamlandi (Windows): {len(sonuclar)}/{toplam} basarili, "
            f"{len(basarisiz)} basarisiz",
        )

    # Mantiksal imajda bazi dosyalar KALICI olarak alinamaz -- bkz.
    # file_acquirer.acquire_remote_tree'deki AYNI gerekce (durduruldu
    # durumunda mode ne olursa olsun manifest KORUNUR, orasindaki AYNI not).
    if not durduruldu and ((not basarisiz and len(acquired_files) == toplam) or mode != "file"):
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


def acquire_logical_image_windows(ssh, remote_root, output_dir, progress_callback=None,
                                   manifest_path=None, resume_state=None, host=None, should_stop=None):
    """Mantiksal imaj (Windows): remote_root'un (orn. C:\\) var olan TUM
    dosyalari; kilitli hacim-koku sistem dosyalari dislanir, okunamayanlar
    sebepleriyle raporlanir. file_acquirer.acquire_logical_image'in karsiligi."""
    return acquire_remote_tree_windows(
        ssh, remote_root, output_dir, progress_callback=progress_callback,
        manifest_path=manifest_path, resume_state=resume_state, host=host,
        file_lister=list_logical_files_windows, manifest_every=LOGICAL_MANIFEST_EVERY, mode="logical",
        should_stop=should_stop,
    )
