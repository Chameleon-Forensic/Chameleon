import getpass
import os

try:
    from ssh_connector import SSHConnector
except ImportError:
    SSHConnector = None
    print("[HATA] paramiko kurulu degil. Kurmak icin: pip install paramiko --break-system-packages")
    print("(SSH gerektiren secenekler kullanilamayacak, sadece Verify Image calisir.)\n")

import chain_of_custody as coc
import file_acquirer
import image_acquirer
import windows_acquirer
from hash_verifier import HashError, HashMismatchError, verify_file


def print_menu():
    print("\n====================================")
    print(" Remote Server Forensic Image Tool")
    print("====================================")
    print("1. Tam Disk Imaji Al (Live/Offline)")
    print("2. Dosya/Klasor Al")
    print("3. Mantiksal Imaj Al (bir hacmin tum okunabilen dosyalari)")
    print("4. Verify Image (hash check)")
    print("0. Exit")


def get_ssh_connection():

    print("\n--- SSH Connection Information ---")

    host = input("SSH Host: ").strip()

    while True:
        port_input = input("SSH Port [22]: ").strip()
        if not port_input:
            port = 22
            break
        try:
            port = int(port_input)
            break
        except ValueError:
            print("Sayisal bir port girin.")

    username = input("SSH Username: ").strip()

    print("\nAuthentication Method")
    print("1. Password")
    print("2. SSH Key")

    auth = input("Select: ").strip()

    password = None
    key_path = None

    if auth == "1":
        password = getpass.getpass("Password: ")

    elif auth == "2":
        key_path = input("SSH Key Path: ").strip()

    else:
        print("Invalid authentication method.")
        return None

    return SSHConnector(
        host=host,
        port=port,
        username=username,
        password=password,
        key_path=key_path,
        strict=True
    )


def select_target_os():
    """Hangi motor kolunun (image_acquirer/file_acquirer vs windows_acquirer)
    kullanilacagini belirler -- GUI'deki OS radyo secimiyle AYNI amac."""
    while True:
        print("\nHedef Isletim Sistemi")
        print("1. Linux")
        print("2. Windows")
        secim = input("Secim: ").strip()
        if secim == "1":
            return "linux"
        if secim == "2":
            return "windows"
        print("Gecersiz secim.")


def _parse_lsblk_names(disks_output):
    """
    ssh_connector.list_disks()'in ciktisi ("lsblk -o NAME,SIZE,TYPE,FSTYPE,
    MOUNTPOINT,MODEL,SERIAL", agac gorunumu acik) satir satir ayrıstirilir,
    sadece gercek NAME kolonu (ilk whitespace-ayrilmis token) alinir.
    lsblk, alt bolumleri "├─sda1" / "└─sda1" gibi agac-cizim karakterleriyle
    gosterdigi icin bu karakterler NAME'den temizlenir -- aksi halde SIZE/
    MODEL/SERIAL kolonlarindaki rastgele bir alt string ya da bu cizim
    karakterleri yuzunden gercek olmayan bir isim "bulundu" sanilabilir.
    """
    names = []
    for line in (disks_output or "").splitlines():
        line = line.strip()
        if not line:
            continue
        token = line.split()[0]
        name = token.lstrip("│├└─ \t")
        if name and name != "NAME":
            names.append(name)
    return names


def select_disk(disks_output):
    """
    Kullanicidan hedef disk yolunu ister, lsblk ciktisindaki NAME kolonunda
    gercekten var olup olmadigini dogrular; bulunamazsa tekrar sorar.
    SADECE Linux hedef icin -- Windows'ta disk numarasi dogrudan sorulur
    (select_windows_disk_number).
    """
    gecerli_isimler = _parse_lsblk_names(disks_output)
    while True:
        raw = input("\nHedef disk (orn. /dev/sdb): ").strip()
        if not raw:
            print("Disk yolu bos olamaz.")
            continue

        disk_path = raw if raw.startswith("/dev/") else f"/dev/{raw}"
        disk_name = disk_path.replace("/dev/", "")

        if disk_name and disk_name in gecerli_isimler:
            return disk_path

        print(f"'{disk_name}' listede bulunamadi, tekrar deneyin.")


def select_windows_disk_number():
    """GUI'deki 'Disk Numarasi' alaniyla AYNI -- Windows'ta lsblk yok,
    PhysicalDriveN icin sadece N sayisi sorulur."""
    while True:
        raw = input("\nHedef disk numarasi (ör. 0 -- PhysicalDrive0 icin): ").strip()
        try:
            return int(raw)
        except ValueError:
            print("Sayisal bir disk numarasi girin.")


def ask_live_or_offline():
    while True:
        print("\n1. Live Acquisition (write-block uygulanmaz)")
        print("2. Offline Acquisition (write-block uygulanir)")
        secim = input("Secim: ").strip()
        if secim == "1":
            return "live"
        if secim == "2":
            return "offline"
        print("Gecersiz secim.")


def show_progress(done, total):
    """hash_verifier'in ilerleme geri cagrisi: konsolda tek satirlik cubuk."""
    if total <= 0:
        return
    pct = done * 100 // total
    bar = "#" * (pct // 2) + "-" * (50 - pct // 2)
    print(f"\r  [{bar}] %{pct:3d}", end="", flush=True)
    if done >= total:
        print()


def show_tree_progress(done, total):
    """Dosya/Klasor + Mantiksal Imaj icin -- show_progress ile AYNI cubuk,
    sadece etiket 'dosya' bazli (blok degil)."""
    if total <= 0:
        return
    pct = done * 100 // total
    bar = "#" * (pct // 2) + "-" * (50 - pct // 2)
    print(f"\r  [{bar}] %{pct:3d} ({done}/{total} dosya)", end="", flush=True)
    if done >= total:
        print()


def verify_image_and_log(image_path, expected_master):
    """
    Yerel imajin master hash'ini uzak diskin hash'iyle karsilastirir ve
    sonucu chain-of-custody log'una isler.

    hash_verifier nesne dondurur, chain_of_custody duz metin bekler; bu
    fonksiyon ikisi arasindaki koprudur.
    """
    try:
        result = verify_file(image_path, expected_master, progress=show_progress)

    except HashMismatchError as exc:
        coc.log_event(
            coc.EVENT_HASH_MISMATCH,
            f"Imaj dogrulama BASARISIZ: {image_path} | beklenen={exc.expected}",
            exc.actual,
        )
        print(f"\n{exc}")
        print("\nDELIL BUTUNLUGU BOZULMUS — imaj kaynakla ayni degil.")
        return False

    except (HashError, FileNotFoundError, OSError) as exc:
        coc.log_event(coc.EVENT_EXAM_ERROR, f"Dogrulama hatasi: {exc}")
        print(f"\nHATA: {exc}")
        return False

    coc.log_event(
        coc.EVENT_HASH_VERIFIED,
        f"Imaj dogrulandi: {image_path} ({result.byte_count} bayt)",
        result.digest,
    )
    print("\nDOGRULAMA BASARILI — imaj kaynakla birebir ayni.")
    print(f"  SHA-256 : {result.digest}")
    print(f"  Boyut   : {result.byte_count} bayt")
    return True


def handle_verify_image():
    """Menu secenegi 4: mevcut bir imaj dosyasini hash ile dogrular."""
    print("\n--- Image Verification ---")

    image_path = input("Imaj dosyasi yolu: ").strip().strip('"')
    if not image_path:
        print("Imaj yolu bos olamaz.")
        return

    expected = input("Beklenen SHA-256 (uzak diskin hash'i): ").strip()
    if not expected:
        print("Beklenen hash bos olamaz.")
        return

    verify_image_and_log(image_path, expected)


def _resume_disk_loop(ssh, sonuc, tekrar_cagir):
    """Baglanti tamamen kesilirse acquire_disk_image[_windows] "resume_from"
    ile doner; kullaniciya sorup elle tekrar denenir (manifest korunur,
    silinmez). Linux/Windows disk kollarinin İKİSİ de bu dongüyü kullanir --
    fonksiyon imzalari (disk_path/disk_number) farkli oldugu icin gercek
    cagri tekrar_cagir(resume_from, resume_state, manifest_path) uzerinden
    cagirana birakilir."""
    while sonuc is not None and "resume_from" in sonuc:
        tekrar = input(
            f"\nBaglanti tamamen kesildi (blok {sonuc['resume_from']}'de). "
            f"Tekrar baglanip devam edilsin mi? (E/H): "
        ).strip().upper()
        if tekrar != "E":
            print("Islem yarim birakildi, manifest korunuyor; daha sonra ayni diski secip devam edebilirsiniz.")
            return None
        if not ssh.connect():
            print("SSH baglantisi kurulamadi.")
            return None
        sonuc = tekrar_cagir(sonuc["resume_from"], sonuc, sonuc.get("manifest_path"))
    return sonuc


def _finish_disk_acquisition(sonuc, mode):
    """Bloklari birlestirir, master hash'i basar, dogrulama sorar --
    Linux/Windows disk kollarinin ORTAK kuyruk kismi (concatenate_blocks/
    local_master_hash OS'a bagli degil)."""
    if sonuc is None:
        return

    imaj_yolu = image_acquirer.concatenate_blocks(
        sonuc["block_paths"], sonuc["total_blocks"], output_dir=sonuc["output_dir"],
        cleanup=(mode != "live"),
    )
    if imaj_yolu is None:
        print("\nEksik bloklar nedeniyle imaj birlestirilemedi.")
        return

    master_hash = image_acquirer.local_master_hash(imaj_yolu)
    print(f"\nImaj tamamlandi: {imaj_yolu}")
    print(f"Yerel master SHA-256: {master_hash}")

    uzak_hash = input(
        "\nUzak diskin master hash'i (varsa dogrulama icin, yoksa bos gecin): "
    ).strip()
    if uzak_hash:
        verify_image_and_log(imaj_yolu, uzak_hash)


def handle_disk_acquisition(ssh, target_os):
    mode = ask_live_or_offline()
    apply_wb = (mode == "offline")

    if target_os == "linux":
        print("\nAvailable Disks")
        print("----------------")
        disks = ssh.list_disks()
        if disks:
            print(disks)
        else:
            print("No disks found.")
            return
        target_disk = select_disk(disks)
        hedef_adi = target_disk
    else:
        target_disk = select_windows_disk_number()
        hedef_adi = f"PhysicalDrive{target_disk}"

    # Yarim kalmis bir islem var mi (program kapatilip yeniden acilmis
    # olabilir)? docs/PROJE_TALIMATI.md madde 6 -- Linux/Windows AYNI
    # (host-bazli) manifest deposunu kullanir.
    manifest_path = None
    resume_state = None
    start_block = 0
    mevcut_manifest = image_acquirer.find_incomplete_manifest(hedef_adi, host=ssh.host)
    if mevcut_manifest:
        manifest_path, resume_state = mevcut_manifest
        cevap = input(
            f"\nYarim kalan bir islem bulundu ({len(resume_state['acquired_blocks'])}/"
            f"{resume_state['total_blocks']} blok tamamlanmis: {hedef_adi}). "
            f"Devam edilsin mi? (E/H): "
        ).strip().upper()
        if cevap == "E":
            start_block = len(resume_state["acquired_blocks"])
        else:
            manifest_path = None
            resume_state = None

    if target_os == "linux":
        sonuc = image_acquirer.acquire_disk_image(
            ssh, target_disk, ssh.password,
            apply_write_blocker=apply_wb,
            total_blocks=resume_state["total_blocks"] if resume_state else None,
            start_block=start_block, resume_state=resume_state,
            manifest_path=manifest_path, host=ssh.host,
        )
        sonuc = _resume_disk_loop(ssh, sonuc, lambda sb, rs, mp: image_acquirer.acquire_disk_image(
            ssh, target_disk, ssh.password, apply_write_blocker=False,
            total_blocks=rs["total_blocks"], start_block=sb, resume_state=rs,
            manifest_path=mp, host=ssh.host,
        ))
    else:
        sonuc = windows_acquirer.acquire_disk_image_windows(
            ssh, target_disk, output_dir=image_acquirer.IMAGE_DIR,
            apply_write_blocker=apply_wb,
            total_blocks=resume_state["total_blocks"] if resume_state else None,
            start_block=start_block, resume_state=resume_state,
            manifest_path=manifest_path, host=ssh.host,
        )
        sonuc = _resume_disk_loop(ssh, sonuc, lambda sb, rs, mp: windows_acquirer.acquire_disk_image_windows(
            ssh, target_disk, output_dir=rs["output_dir"], apply_write_blocker=False,
            total_blocks=rs["total_blocks"], start_block=sb, resume_state=rs,
            manifest_path=mp, host=ssh.host,
        ))

    _finish_disk_acquisition(sonuc, mode)


def handle_tree_acquisition(ssh, target_os, logical):
    """Dosya/Klasor (logical=False) ve Mantiksal Imaj (logical=True) --
    ikisi de ayni sekilde calisir, sadece cagrilan fonksiyon ve varsayilan
    cikti klasoru degisir (GUI'deki file_card/logical_card ile AYNI ayrim)."""
    etiket = "kok yolu (bir hacim, ör. C:\\ ya da /)" if logical else "dosya/klasor yolu"
    remote_path = input(f"\nUzak {etiket}: ").strip()
    if not remote_path:
        print("Yol bos olamaz.")
        return

    varsayilan_alt = "mantiksal" if logical else "dosyalar"
    varsayilan_cikti = os.path.join(image_acquirer.IMAGE_DIR, varsayilan_alt)
    cikti_girisi = input(f"Cikti klasoru [{varsayilan_cikti}]: ").strip()
    out_dir = cikti_girisi or varsayilan_cikti

    mode = "logical" if logical else "file"
    manifest_path = None
    resume_state = None
    mevcut = image_acquirer.find_incomplete_tree_manifest(remote_path, host=ssh.host, mode=mode)
    if mevcut:
        manifest_path, resume_state = mevcut
        completed = len(resume_state.get("acquired_files", []))
        total = resume_state.get("total_files", 0)
        cevap = input(
            f"\nYarim kalan bir islem bulundu ({completed}/{total} dosya tamamlanmis: "
            f"{remote_path}). Devam edilsin mi? (E/H): "
        ).strip().upper()
        if cevap != "E":
            image_acquirer.delete_manifest(manifest_path)
            manifest_path = None
            resume_state = None

    if target_os == "linux":
        alici = file_acquirer.acquire_logical_image if logical else file_acquirer.acquire_remote_tree
        manifest = alici(
            ssh, remote_path, out_dir, password=ssh.password, progress_callback=show_tree_progress,
            manifest_path=manifest_path, resume_state=resume_state, host=ssh.host,
        )
    else:
        alici = windows_acquirer.acquire_logical_image_windows if logical else windows_acquirer.acquire_remote_tree_windows
        manifest = alici(
            ssh, remote_path, out_dir, progress_callback=show_tree_progress,
            manifest_path=manifest_path, resume_state=resume_state, host=ssh.host,
        )

    if manifest is None:
        print(f"\nUzak yol bulunamadi: {remote_path}")
        return

    basarili = len(manifest["acquired"])
    basarisiz = manifest["failed"]
    print(f"\n{basarili}/{manifest['total_files']} dosya alindi ve dogrulandi.")
    if basarisiz:
        sebepler = manifest.get("failed_reasons", {})
        print(f"{len(basarisiz)} dosya alinamadi:")
        for yol in basarisiz:
            sebep = sebepler.get(yol)
            print(f"  - {yol}" + (f" ({sebep})" if sebep else ""))
    if manifest.get("excluded"):
        print(f"{len(manifest['excluded'])} oge bilerek alinmadi (kilitli/degisken sistem ogeleri).")
    print(f"Manifest: {os.path.join(out_dir, 'manifest_files.json')}")


def main():

    while True:

        print_menu()

        choice = input("\nSelection: ").strip()

        if choice == "0":
            print("Program terminated.")
            break

        # Dogrulama yerel bir dosya uzerinde calisir, SSH baglantisi gerektirmez.
        if choice == "4":
            handle_verify_image()
            continue

        if choice not in ("1", "2", "3"):
            print("Invalid selection.")
            continue

        if SSHConnector is None:
            print("\n[HATA] paramiko kurulu degil, bu secenek kullanilamaz.")
            print("Kurmak icin: pip install paramiko --break-system-packages")
            continue

        target_os = select_target_os()
        ssh = get_ssh_connection()

        if ssh is None:
            continue

        try:
            if not ssh.connect():
                print("SSH connection failed.")
                continue

            print("\nConnected successfully.\n")

            if choice == "1":
                handle_disk_acquisition(ssh, target_os)
            elif choice == "2":
                handle_tree_acquisition(ssh, target_os, logical=False)
            else:
                handle_tree_acquisition(ssh, target_os, logical=True)

        finally:
            ssh.close()


if __name__ == "__main__":
    main()
