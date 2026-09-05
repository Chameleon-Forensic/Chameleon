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
    delete_manifest,
    ensure_connection,
)

MAX_RETRY_PER_BLOCK = 3


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
        f"if ($read -lt {length}) {{ $buf = $buf[0..([Math]::Max($read-1,0))] }}; "
    )


def get_remote_block_hash_windows(ssh, disk_number, block_no, block_size_mb):
    """Blogu SUNUCUDA hashler, veri gondermez -- sadece SHA-256 hex doner."""
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
    else:
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


def acquire_remote_file_windows(ssh, remote_path, local_path):
    """Dosyayi Base64 olarak ceker, yazmadan ONCE hash dogrular."""
    uzak_hash = get_remote_file_hash_windows(ssh, remote_path)
    if uzak_hash is None:
        return False, None

    safe = powershell_quote(remote_path)
    ps = f"[Convert]::ToBase64String([System.IO.File]::ReadAllBytes({safe}))"
    out, _err, _code = ssh.run_command(ps)
    if not out:
        return False, None
    try:
        veri = base64.b64decode(out.strip())
    except Exception:
        return False, None

    gercek_hash = hashlib.sha256(veri).hexdigest()
    if gercek_hash != uzak_hash:
        return False, gercek_hash

    os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
    with open(local_path, "wb") as f:
        f.write(veri)

    return True, gercek_hash


def acquire_remote_tree_windows(ssh, remote_root, output_dir, progress_callback=None):
    """file_acquirer.acquire_remote_tree ile ayni davranis, Windows yollari
    (ters slash) ve PowerShell komutlariyla."""
    kind = remote_path_kind_windows(ssh, remote_root)
    if kind is None:
        coc.log_event(coc.EVENT_EXAM_ERROR, f"Yol bulunamadi (Windows): {remote_root}")
        return None

    norm_root = remote_root.replace("\\", "/")
    if kind == "file":
        dosyalar = [remote_root]
        taban = norm_root.rsplit("/", 1)[0] if "/" in norm_root else ""
    else:
        dosyalar = list_remote_files_windows(ssh, remote_root)
        taban = norm_root

    coc.log_event(
        coc.EVENT_EXAM_START,
        f"Dosya/klasor alma baslatildi (Windows): {remote_root} ({len(dosyalar)} dosya)",
    )

    toplam = len(dosyalar)
    sonuclar = []
    basarisiz = []

    for i, uzak_dosya in enumerate(dosyalar, start=1):
        norm_dosya = uzak_dosya.replace("\\", "/")
        goreli = os.path.relpath(norm_dosya, taban) if taban else os.path.basename(norm_dosya)
        goreli = goreli.replace("/", os.sep)
        yerel_dosya = os.path.join(output_dir, goreli)

        basarili, hash_deger = acquire_remote_file_windows(ssh, uzak_dosya, yerel_dosya)
        if basarili:
            sonuclar.append({"remote_path": uzak_dosya, "local_path": yerel_dosya, "sha256": hash_deger})
            coc.log_event(coc.EVENT_BLOCK_ACQUIRED, f"Dosya alindi ve dogrulandi (Windows): {uzak_dosya}", hash_deger)
        else:
            basarisiz.append(uzak_dosya)
            coc.log_event(coc.EVENT_EXAM_ERROR, f"Dosya alinamadi/dogrulanamadi (Windows): {uzak_dosya}")

        if progress_callback:
            progress_callback(i, toplam)

    coc.log_event(
        coc.EVENT_EXAM_END,
        f"Dosya/klasor alma tamamlandi (Windows): {len(sonuclar)}/{toplam} basarili, "
        f"{len(basarisiz)} basarisiz",
    )

    manifest = {
        "remote_root": remote_root,
        "total_files": toplam,
        "acquired": sonuclar,
        "failed": basarisiz,
        "acquired_at": datetime.now(timezone.utc).isoformat(),
    }

    os.makedirs(output_dir, exist_ok=True)
    manifest_path = os.path.join(output_dir, "manifest_files.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    return manifest
