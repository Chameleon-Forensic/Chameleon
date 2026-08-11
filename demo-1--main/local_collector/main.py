import getpass

try:
    from ssh_connector import SSHConnector
except ImportError:
    SSHConnector = None
    print("[HATA] paramiko kurulu degil. Kurmak icin: pip install paramiko --break-system-packages")
    print("(SSH gerektiren secenekler kullanilamayacak, sadece Verify Image calisir.)\n")

import chain_of_custody as coc
import image_acquirer
from hash_verifier import HashError, HashMismatchError, verify_file


def print_menu():
    print("\n====================================")
    print(" Remote Server Forensic Image Tool")
    print("====================================")
    print("1. Live Acquisition")
    print("2. Offline Acquisition")
    print("3. Verify Image (hash check)")
    print("0. Exit")


def get_ssh_connection():

    print("\n--- SSH Connection Information ---")

    host = input("SSH Host: ").strip()

    port_input = input("SSH Port [22]: ").strip()
    port = int(port_input) if port_input else 22

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


def select_disk(disks_output):
    """
    Kullanicidan hedef disk yolunu ister, lsblk ciktisinda gercekten var
    olup olmadigini dogrular; bulunamazsa tekrar sorar.
    """
    while True:
        raw = input("\nHedef disk (orn. /dev/sdb): ").strip()
        if not raw:
            print("Disk yolu bos olamaz.")
            continue

        disk_path = raw if raw.startswith("/dev/") else f"/dev/{raw}"
        disk_name = disk_path.replace("/dev/", "")

        if disk_name and disk_name in disks_output:
            return disk_path

        print(f"'{disk_name}' listede bulunamadi, tekrar deneyin.")


def show_progress(done, total):
    """hash_verifier'in ilerleme geri cagrisi: konsolda tek satirlik cubuk."""
    if total <= 0:
        return
    pct = done * 100 // total
    bar = "#" * (pct // 2) + "-" * (50 - pct // 2)
    print(f"\r  [{bar}] %{pct:3d}", end="", flush=True)
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
    """Menu secenegi 3: mevcut bir imaj dosyasini hash ile dogrular."""
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


def main():

    while True:

        print_menu()

        choice = input("\nSelection: ").strip()

        if choice == "0":
            print("Program terminated.")
            break

        # Dogrulama yerel bir dosya uzerinde calisir, SSH baglantisi gerektirmez.
        if choice == "3":
            handle_verify_image()
            continue

        if choice not in ["1", "2"]:
            print("Invalid selection.")
            continue

        if SSHConnector is None:
            print("\n[HATA] paramiko kurulu degil, bu secenek kullanilamaz.")
            print("Kurmak icin: pip install paramiko --break-system-packages")
            continue

        ssh = get_ssh_connection()

        if ssh is None:
            continue

        try:

            if not ssh.connect():
                print("SSH connection failed.")
                continue

            print("\nConnected successfully.\n")

            print("Available Disks")
            print("----------------")

            disks = ssh.list_disks()

            if disks:
                print(disks)
            else:
                print("No disks found.")
                continue

            target_disk = select_disk(disks)

            # Yarim kalmis bir islem var mi (program kapatilip yeniden
            # acilmis olabilir)? docs/PROJE_TALIMATI.md madde 6, main.py.
            manifest_path = None
            resume_state = None
            start_block = 0

            mevcut_manifest = image_acquirer.find_incomplete_manifest(target_disk)
            if mevcut_manifest:
                manifest_path, resume_state = mevcut_manifest
                cevap = input(
                    f"\nYarim kalan bir islem bulundu ({len(resume_state['acquired_blocks'])}/"
                    f"{resume_state['total_blocks']} blok tamamlanmis: {target_disk}). "
                    f"Devam edilsin mi? (E/H): "
                ).strip().upper()
                if cevap == "E":
                    start_block = len(resume_state["acquired_blocks"])
                else:
                    manifest_path = None
                    resume_state = None

            # write-block, image_acquirer.acquire_disk_image icinde uygulanir:
            # Offline modda (choice == "2") uygulanir, Live modda atlanip
            # WRITE_BLOCK_SKIPPED loglanir.
            sonuc = image_acquirer.acquire_disk_image(
                ssh,
                target_disk,
                ssh.password,
                apply_write_blocker=(choice == "2"),
                total_blocks=resume_state["total_blocks"] if resume_state else None,
                start_block=start_block,
                resume_state=resume_state,
                manifest_path=manifest_path,
            )

            # Baglanti tamamen kesilirse acquire_disk_image "resume_from" ile
            # doner; kullaniciya sorup elle tekrar denenebilir (manifest
            # korunur, silinmez).
            while sonuc is not None and "resume_from" in sonuc:
                tekrar = input(
                    f"\nBaglanti tamamen kesildi (blok {sonuc['resume_from']}'de). "
                    f"Tekrar baglanip devam edilsin mi? (E/H): "
                ).strip().upper()
                if tekrar != "E":
                    print("Islem yarim birakildi, manifest korunuyor; daha sonra ayni diski secip devam edebilirsiniz.")
                    sonuc = None
                    break
                if not ssh.connect():
                    print("SSH baglantisi kurulamadi.")
                    sonuc = None
                    break
                sonuc = image_acquirer.acquire_disk_image(
                    ssh,
                    target_disk,
                    ssh.password,
                    apply_write_blocker=(choice == "2"),
                    total_blocks=sonuc["total_blocks"],
                    start_block=sonuc["resume_from"],
                    resume_state=sonuc,
                    manifest_path=sonuc.get("manifest_path"),
                )

            if sonuc is None:
                continue

            imaj_yolu = image_acquirer.concatenate_blocks(
                sonuc["block_paths"], sonuc["total_blocks"], output_dir=sonuc["output_dir"]
            )
            if imaj_yolu is None:
                print("\nEksik bloklar nedeniyle imaj birlestirilemedi.")
                continue

            master_hash = image_acquirer.local_master_hash(imaj_yolu)
            print(f"\nImaj tamamlandi: {imaj_yolu}")
            print(f"Yerel master SHA-256: {master_hash}")

            uzak_hash = input(
                "\nUzak diskin master hash'i (varsa dogrulama icin, yoksa bos gecin): "
            ).strip()
            if uzak_hash:
                verify_image_and_log(imaj_yolu, uzak_hash)

        finally:
            ssh.close()


if __name__ == "__main__":
    main()