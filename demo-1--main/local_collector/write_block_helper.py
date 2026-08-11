"""
write_block_helper.py
remote_agent/write_blocker.sh ile ayni mantigi (blockdev --setro + --getro
dogrulama), dosyayi uzak sunucuya kopyalamadan, dogrudan SSH komutu olarak
calistiran yardimci modul. ssh_connector.py'nin run_command() fonksiyonunu
kullanir.
"""

import chain_of_custody as coc


def _run_blockdev(ssh, flag, disk_path, password):
    """
    blockdev komutunu sudo ile calistirir. password verilirse, komut
    metnine hic gomulmeden ssh_connector.run_command()'in sudo_password
    mekanizmasiyla (stdin uzerinden) guvenli sekilde iletilir. password
    verilmezse (NOPASSWD sudo yapilandirmasi varsa) get_pty=True ile
    dogrudan calistirilir.
    """
    if password:
        return ssh.run_command(f"blockdev {flag} {disk_path}", sudo_password=password)
    return ssh.run_command(f"sudo blockdev {flag} {disk_path}", get_pty=True)


def apply_write_block(ssh, disk_path, password=None):
    """
    Hedef diski (disk_path, orn. '/dev/sdb') SSH uzerinden salt-okunur yapar
    ve blockdev --getro ile dogrular. Basarili olursa True, olmazsa False
    doner; sonucu chain_of_custody.py'ye WRITE_BLOCK_APPLIED ya da
    EXAM_ERROR olarak loglar.

    password verilirse (NOPASSWD sudo yoksa gerekir), parola stdin
    uzerinden guvenli sekilde gecilir — komut satirina asla yazilmaz
    (bkz. ssh_connector.run_command).
    """
    setro_out, setro_err, setro_exit = _run_blockdev(ssh, "--setro", disk_path, password)
    if setro_out is None:
        coc.log_event(
            coc.EVENT_EXAM_ERROR,
            f"Write-block komutu calistirilamadi (SSH hatasi): {disk_path}",
        )
        return False

    getro_out, getro_err, getro_exit = _run_blockdev(ssh, "--getro", disk_path, password)
    if getro_out is None:
        coc.log_event(
            coc.EVENT_EXAM_ERROR,
            f"Write-block dogrulama komutu calistirilamadi (SSH hatasi): {disk_path}",
        )
        return False

    if getro_out.strip() == "1":
        coc.log_event(
            coc.EVENT_WRITE_BLOCK_APPLIED,
            f"Disk salt-okunur yapildi ve dogrulandi: {disk_path}",
        )
        return True

    coc.log_event(
        coc.EVENT_EXAM_ERROR,
        f"Write-block dogrulanamadi (getro={getro_out.strip()!r}): {disk_path} | "
        f"setro_stderr: {(setro_err or '').strip() or '-'} (exit={setro_exit}), "
        f"getro_stderr: {(getro_err or '').strip() or '-'} (exit={getro_exit})",
    )
    return False


if __name__ == "__main__":
    # Modulu tek basina test etmek icin: gercek bir SSH baglantisi kurup
    # verilen diske write-block uygular
    import getpass

    from ssh_connector import SSHConnector

    HOST = input("SSH Host: ").strip()
    PORT_INPUT = input("SSH Port [22]: ").strip()
    PORT = int(PORT_INPUT) if PORT_INPUT else 22
    USERNAME = input("SSH Kullanici adi: ").strip()
    PASSWORD = getpass.getpass("SSH Sifre (bos birakilabilir): ").strip() or None
    DISK_PATH = input("Hedef disk (orn. /dev/sdb): ").strip()

    if not HOST or not USERNAME or not DISK_PATH:
        print("[HATA] Host, kullanici adi ve disk yolu bos birakilamaz.")
        exit(1)

    ssh = SSHConnector(host=HOST, port=PORT, username=USERNAME,
                        password=PASSWORD, strict=True)
    try:
        if ssh.connect():
            basarili = apply_write_block(ssh, DISK_PATH, password=PASSWORD)
            print("Write-block basarili." if basarili else "Write-block basarisiz.")
    finally:
        ssh.close()
