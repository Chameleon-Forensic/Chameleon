"""
local_connector.py
"Bu bilgisayar (yerel)" modu icin SSHConnector'in yerine gecen kucuk sinif.

Neden var: windows_acquirer.py'nin disk/mantiksal imaj/dosya kodu hedefle
SADECE ssh.run_command("PowerShell komutu") uzerinden konusuyor. Ayni komutlari
BU bilgisayarda calistiran bir nesne verirsek, o kodun HEPSI (rapor, hash,
manifest, sikistirma, parcalama dahil) degismeden yerelde calisir -- ayri bir
imaj motoru yazmak gerekmez. Sadece ham disk bloklari icin, her blokta
PowerShell + Base64 yerine dogrudan okuyan hizli bir yol var (bkz.
read_local_block, windows_acquirer.py'de is_local ile secilir).

Sadece Windows'ta anlamli (PowerShell + \\\\.\\PhysicalDriveN).
"""

import base64
import ctypes
import os
import subprocess

# Konsolsuz (pencereli) exe'de her PowerShell cagrisinda siyah pencere
# cakmasin diye -- sadece Windows'ta tanimli.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class LocalConnector:
    """SSHConnector'in, windows_acquirer/image_acquirer'in kullandigi yuzeyi."""

    is_local = True

    def __init__(self):
        # disk numarasi -> bayt; ham okumada son blogu diskin sonunu
        # asmayacak sekilde kirpmak icin (bkz. read_local_block).
        self.disk_sizes = {}

    # -- Baglanti yuzeyi: yerelde "baglanti" hep var --------------------
    def connect(self):
        return True

    def reconnect(self):
        return True

    def is_active(self):
        return True

    def close(self):
        pass

    def run_command(self, command, get_pty=False, sudo_password=None):
        """(stdout, stderr, exit_code) doner -- SSHConnector.run_command ile ayni
        sozlesme. Komut -EncodedCommand ile verilir: tirnak/ozel karakter
        kacirma sorunu olmaz."""
        script = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; " + command
        encoded = base64.b64encode(script.encode("utf-16-le")).decode()
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                capture_output=True, timeout=600, creationflags=_NO_WINDOW,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None, None, None
        return r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace"), r.returncode

    def list_disks(self):
        """Yerel fiziksel diskler: numara, model, boyut, uzerindeki surucu
        harfleri; sistem diski isaretli (image alinacak diski secerken lazim)."""
        sistem = system_disk_number(self)
        out, _err, _code = self.run_command(
            "Get-Disk | ForEach-Object { $d = $_; "
            "$harf = (Get-Partition -DiskNumber $d.Number -ErrorAction SilentlyContinue | "
            "Where-Object DriveLetter | ForEach-Object { $_.DriveLetter + ':' }) -join ' '; "
            "'{0}|{1}|{2:N1}|{3}' -f $d.Number, $d.FriendlyName, ($d.Size / 1GB), $harf }"
        )
        satirlar = []
        for satir in (out or "").splitlines():
            parcalar = satir.strip().split("|")
            if len(parcalar) != 4:
                continue
            no, model, gb, harfler = parcalar
            isaret = "  [SİSTEM DİSKİ]" if sistem is not None and no == str(sistem) else ""
            satirlar.append(f"Disk {no}: {model} — {gb} GB — {harfler or '(harf yok)'}{isaret}")
        return "\n".join(satirlar)


# ---------------------------------------------------------------------------
# Guvenlik kontrolleri -- yerel modda "kaynak diske yazma" riskini onler
# ---------------------------------------------------------------------------
def is_admin():
    """Ham diske (\\\\.\\PhysicalDriveN) okumak icin yonetici yetkisi gerekir."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def _disk_number_for_letter(ssh, letter):
    out, _err, _code = ssh.run_command(f"(Get-Partition -DriveLetter '{letter}' -ErrorAction Stop).DiskNumber")
    try:
        return int((out or "").strip())
    except ValueError:
        return None


def system_disk_number(ssh):
    """Calisan Windows'un kurulu oldugu fiziksel diskin numarasi (bulunamazsa None)."""
    harf = (os.environ.get("SystemDrive") or "C:")[0]
    return _disk_number_for_letter(ssh, harf)


def disk_number_of_path(ssh, path):
    """path'in bulundugu yerel diskin numarasi. Surucu harfi yoksa (UNC/ag
    yolu gibi) ya da bulunamazsa None -- cagiran taraf ikisini ayirt etmek
    icin has_local_drive_letter'a bakar."""
    if not has_local_drive_letter(path):
        return None
    return _disk_number_for_letter(ssh, os.path.splitdrive(path)[0][0])


def has_local_drive_letter(path):
    surucu = os.path.splitdrive(str(path))[0]
    return len(surucu) == 2 and surucu[1] == ":"


def check_output_not_on_source(ssh, source_disk_number, output_path):
    """Cikti kaynak diskle AYNI fiziksel diskteyse hata metni, degilse None.
    Kaynak diske yazmak delili degistirir -- yerel modun en temel kurali.
    Ag yolu (UNC) yerel disk degildir, serbest; harfli ama diski
    belirlenemeyen yol ise guvenli tarafta kalinip reddedilir."""
    if not has_local_drive_letter(output_path):
        return None
    cikti_diski = disk_number_of_path(ssh, output_path)
    if cikti_diski is None:
        return "output_disk_unknown"
    if cikti_diski == source_disk_number:
        return "output_on_source"
    return None


def check_root_output_separate(ssh, root_path, output_path):
    """Mantiksal/dosya modu icin ayni kontrol: cikti, taranan koku icermemeli
    ve kokle ayni fiziksel diskte olmamali (yoksa cikti kendi kendini de tarar
    ve kaynagi degistirir)."""
    kok = os.path.normcase(os.path.abspath(root_path)).rstrip("\\") + "\\"
    cikti = os.path.normcase(os.path.abspath(output_path)).rstrip("\\") + "\\"
    if cikti.startswith(kok):
        return "output_on_source"
    kok_diski = disk_number_of_path(ssh, root_path)
    if kok_diski is None:
        return None  # kok yerel bir harf degil ya da belirlenemedi -- cikti kontrolu yukaridakiyle sinirli
    return check_output_not_on_source(ssh, kok_diski, output_path)


def disk_device_path(disk_number):
    """Testlerde sahte bir dosyayla degistirilebilsin diye ayri bir fonksiyon."""
    return f"\\\\.\\PhysicalDrive{int(disk_number)}"


def read_local_block(ssh, disk_number, block_no, block_size_mb):
    """Bir blogu ham diskten dogrudan okur (PowerShell/Base64 yok). Blok
    beklenen uzunlukta okunamazsa None -- cagiran retry eder. Son blok diskin
    sonuna gore kirpilir (ham cihazda sona tasan okuma hata verebiliyor)."""
    from windows_acquirer import get_disk_size_bytes_windows  # dongusel import olmasin diye burada

    blok_bayt = block_size_mb * 1024 * 1024
    ofset = block_no * blok_bayt
    boyut = ssh.disk_sizes.get(disk_number)
    if boyut is None:
        boyut = get_disk_size_bytes_windows(ssh, disk_number)
        if boyut is None:
            return None
        ssh.disk_sizes[disk_number] = boyut
    uzunluk = min(blok_bayt, boyut - ofset)
    if uzunluk <= 0:
        return None
    try:
        with open(disk_device_path(disk_number), "rb", buffering=0) as f:
            f.seek(ofset)
            parcalar, kalan = [], uzunluk
            while kalan > 0:
                p = f.read(kalan)
                if not p:
                    return None  # beklenenden erken bitti -- eksik blok kabul edilmez
                parcalar.append(p)
                kalan -= len(p)
    except OSError:
        return None
    return b"".join(parcalar)
