"""
file_acquirer.py
Tam disk yerine, uzak sunucuda tek bir DOSYA ya da KLASOR secip almak
icin modul. image_acquirer.py'deki "once dogrula, sonra yaz" mantigini
dosya seviyesinde uygular; SSHConnector'i aynen kullanir.

Onemli fark: bu mod write-blocker UYGULAMAZ. blockdev --setro tum blok
cihazi salt-okunur yapar, tek tek dosya/klasor icin anlamli degildir --
bu yuzden dosya/klasor secimi her zaman "Live" mantigiyla (diski
kilitlemeden, oldugu gibi okuyarak) calisir.

Buyuk dosyalarda chunk bazli resume YOK (ilk surum) -- roadmap'te not
edildi, dosya kucukse (cogu belge/log/config dosyasi) sorun degil.
"""

import hashlib
import json
import os
import shlex
from datetime import datetime, timezone

import chain_of_custody as coc


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


def list_remote_files(ssh, remote_dir, password=None):
    """remote_dir altindaki (recursive) tum dosyalarin (klasor haric) yollarini doner."""
    safe = shlex.quote(remote_dir)
    cmd = f"find {safe} -type f"
    if password:
        out, _err, _code = ssh.run_command(cmd, sudo_password=password)
    else:
        out, _err, _code = ssh.run_command(cmd)
    if not out:
        return []
    return [satir for satir in out.splitlines() if satir.strip()]


def get_remote_file_hash(ssh, remote_path, password=None):
    """dd/sha256sum yerine dogrudan sha256sum -- tum dosyayi tek seferde hashler."""
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


def acquire_remote_file(ssh, remote_path, local_path, password=None):
    """
    Tek dosyayi HAM bayt olarak ceker (image_acquirer.acquire_raw_block ile
    ayni sebeple ssh.client.exec_command dogrudan kullanilir -- run_command
    metni utf-8'e decode eder, ikili veriyi bozar). Yazmadan ONCE hash
    dogrulanir; uyusmazsa dosya hic yazilmaz.

    Donus: (basarili: bool, sha256: str veya None)
    """
    if ssh.client is None:
        return False, None

    uzak_hash = get_remote_file_hash(ssh, remote_path, password=password)
    if uzak_hash is None:
        return False, None

    safe = shlex.quote(remote_path)
    cmd = f"cat {safe}"
    try:
        if password:
            stdin, stdout, stderr = ssh.client.exec_command(f"sudo -S {cmd}")
            stdin.write(password + "\n")
            stdin.flush()
        else:
            stdin, stdout, stderr = ssh.client.exec_command(cmd)
        veri = stdout.read()
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            return False, None
    except Exception:
        return False, None

    gercek_hash = hashlib.sha256(veri).hexdigest()
    if gercek_hash != uzak_hash:
        return False, gercek_hash

    os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
    with open(local_path, "wb") as f:
        f.write(veri)

    return True, gercek_hash


def acquire_remote_tree(ssh, remote_root, output_dir, password=None, progress_callback=None):
    """
    remote_root bir dosya ya da klasor olabilir. Klasorse altindaki tum
    dosyalari (find -type f) tek tek acquire_remote_file ile alir, goreli
    dizin yapisini output_dir altinda korur. Tek dosyaysa dogrudan onu alir.

    progress_callback(done, total) verilirse her dosyadan sonra cagrilir.

    Donus: manifest dict (remote_root, total_files, acquired, failed,
    acquired_at) ya da yol bulunamadiysa None.
    """
    kind = remote_path_kind(ssh, remote_root, password=password)
    if kind is None:
        coc.log_event(coc.EVENT_EXAM_ERROR, f"Yol bulunamadi: {remote_root}")
        return None

    if kind == "file":
        dosyalar = [remote_root]
        taban = os.path.dirname(remote_root)
    else:
        dosyalar = list_remote_files(ssh, remote_root, password=password)
        taban = remote_root

    coc.log_event(
        coc.EVENT_EXAM_START,
        f"Dosya/klasor alma baslatildi: {remote_root} ({len(dosyalar)} dosya)",
    )

    toplam = len(dosyalar)
    sonuclar = []
    basarisiz = []

    for i, uzak_dosya in enumerate(dosyalar, start=1):
        goreli = os.path.relpath(uzak_dosya, taban) if taban else os.path.basename(uzak_dosya)
        goreli = goreli.replace("/", os.sep)
        yerel_dosya = os.path.join(output_dir, goreli)

        basarili, hash_deger = acquire_remote_file(ssh, uzak_dosya, yerel_dosya, password=password)
        if basarili:
            sonuclar.append({
                "remote_path": uzak_dosya, "local_path": yerel_dosya, "sha256": hash_deger,
            })
            coc.log_event(coc.EVENT_BLOCK_ACQUIRED, f"Dosya alindi ve dogrulandi: {uzak_dosya}", hash_deger)
        else:
            basarisiz.append(uzak_dosya)
            coc.log_event(coc.EVENT_EXAM_ERROR, f"Dosya alinamadi/dogrulanamadi: {uzak_dosya}")

        if progress_callback:
            progress_callback(i, toplam)

    coc.log_event(
        coc.EVENT_EXAM_END,
        f"Dosya/klasor alma tamamlandi: {len(sonuclar)}/{toplam} basarili, "
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
