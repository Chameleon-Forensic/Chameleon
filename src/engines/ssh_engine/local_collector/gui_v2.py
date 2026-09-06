"""
gui_v2.py
SSH ile Uzak Imaj Alma -- PySide6 arayuzu.

Mevcut backend modullerini (SSHConnector/image_acquirer/windows_acquirer/
file_acquirer/hash_verifier/tor_client) kullanir; worker thread'ler
backend fonksiyonlarini cagirip UI'ye Qt sinyalleriyle haber verir.

Ozel durum: _ask_yesno, worker thread'in ICINDEN (baglanti koptu / yarim
kalan islem bulundu senaryolarinda) COAGRILIYOR ve CEVABI BEKLIYOR. Qt'de
worker thread'den dogrudan dialog acilamaz -- ask_yesno sinyali ana
thread'e "soru sor" diye haber veriyor, worker ise KENDI
threading.Event'i ile cevabi bekliyor; ana thread'deki slot dialogu
gosterip cevabi worker nesnesinin (AYNI Python nesnesi, iki thread'den de
erisilebilir) _yesno_result niteligine yazip event'i set ediyor -- Tk'deki
wait_window() ile AYNI davranis, mekanizma farkli. (Ilk denemede
Qt.BlockingQueuedConnection + sinyal argumani olarak dict kullanildi ama
PySide6 bu tur genel nesneleri kuyruklu baglantida KOPYALIYOR, mutasyon
geri yansimiyordu -- mock testle yakalanip duzeltildi, bkz.
docs/hatalar_ve_sonuclar.md.)
"""

import datetime
import json
import os
import re
import subprocess
import sys
import threading

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QCompleter, QDialog, QFileDialog, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QPushButton, QTextEdit,
    QVBoxLayout, QWidget,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# PROJECT_ROOT, gui_v2.py'nin (bir "veri" dosyasi olarak paketlenip
# calisma aninda sys.path.insert()+import ile yuklendigi icin) KENDI
# __file__'ina gore hesaplanir -- derlenmis exe'de bu dogru sekilde
# PyInstaller'in bundled kaynaklarini (ornegin _SHARED_DIR/ui_kit) BULUR,
# o yuzden PROJECT_ROOT'un kendisi degistirilmiyor. Ama varsayilan CIKTI
# yollari (imaj/anahtar dosyalari -- YAZILACAK seyler) icin _MEIPASS
# gecici bir klasordur, uygulama kapaninca silinir. Bu ikisi icin ayri,
# derlenmis modda sys.executable'a (.exe'nin KENDI, KALICI konumu) gore
# hesaplanan bir kok kullanilir (bkz. chain_of_custody.LOG_DIR ile ayni
# gerekce, docs/roadmap.md).
if getattr(sys, "frozen", False):
    _PERSISTENT_ROOT = os.path.dirname(os.path.abspath(sys.executable))
else:
    _PERSISTENT_ROOT = PROJECT_ROOT

DEFAULT_IMAGE_PATH = os.path.join(_PERSISTENT_ROOT, "images", "forensic_image.raw")

_SHARED_DIR = os.path.join(PROJECT_ROOT, "..", "..", "shared")
if os.path.isdir(_SHARED_DIR):
    sys.path.insert(0, _SHARED_DIR)

# Vaka verisiyle (case_history.json, forensic_report.HISTORY_DIR) AYNI
# klasor -- .gitignore'daki "shared/data/" zaten kapsiyor, kisisel/vaka
# verisi hicbir zaman commit edilmez. SADECE host/port/kullanici adi
# tutulur -- parola KESINLIKLE burada saklanmaz.
if getattr(sys, "frozen", False):
    _RECENT_HOSTS_FILE = os.path.join(_PERSISTENT_ROOT, "data", "recent_ssh_hosts.json")
else:
    _RECENT_HOSTS_FILE = os.path.join(_SHARED_DIR, "data", "recent_ssh_hosts.json")
_MAX_RECENT_HOSTS = 5


def _load_recent_hosts():
    try:
        with open(_RECENT_HOSTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save_recent_host(host, port, username):
    if not host:
        return
    entries = [e for e in _load_recent_hosts() if e.get("host") != host]
    entries.insert(0, {"host": host, "port": port, "username": username})
    entries = entries[:_MAX_RECENT_HOSTS]
    try:
        os.makedirs(os.path.dirname(_RECENT_HOSTS_FILE), exist_ok=True)
        with open(_RECENT_HOSTS_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
    except OSError:
        pass
from ui_kit import theme_qt as ui, fonts, icons, widgets  # noqa: E402
from help_content import get_topic  # noqa: E402

try:
    from forensic_report import ForensicReport
except ImportError:
    ForensicReport = None

# ---------------------------------------------------------------------------
# Mevcut modulleri import et (hic degistirmeden) -- gui_v2.py ile AYNI blok
# ---------------------------------------------------------------------------
try:
    from ssh_connector import SSHConnector
    from image_acquirer import (
        acquire_disk_image,
        concatenate_blocks,
        compress_image,
        local_master_hash,
        find_incomplete_manifest,
        get_disk_description,
    )
    from file_acquirer import acquire_remote_tree, list_remote_directory
    from windows_acquirer import (
        acquire_disk_image_windows,
        acquire_remote_tree_windows,
        list_remote_directory_windows,
        get_disk_description_windows,
    )
    from hash_verifier import verify_file, HashMismatchError, HashError
    import chain_of_custody as coc
    import tor_client
    PARAMIKO_OK = True
except ImportError as exc:
    PARAMIKO_OK = False
    IMPORT_ERROR = str(exc)

try:
    from onion_auth import generate_keypair, key_fingerprint
except ImportError:
    generate_keypair = None
    key_fingerprint = None


LOG_COLORS = {
    "ok": ui.SUCCESS, "err": ui.ERROR, "warn": ui.WARNING,
    "info": ui.ACCENT, "plain": ui.TEXT_MAIN,
}


class StdoutRedirector:
    """
    AYNEN tasindi (gui_v2.py) -- sys.stdout'u yakalayip bir callback'e
    iletir. Linux disk alma (acquire_disk_image) ilerlemeyi SADECE stdout
    print()'leriyle bildiriyor (progress_callback parametresi YOK, Windows
    tarafinin aksine) -- bu yuzden bu mekanizma korunuyor.
    """

    def __init__(self, callback):
        self.callback = callback
        self._orig_stdout = sys.stdout

    def write(self, text):
        self._orig_stdout.write(text)
        self._orig_stdout.flush()
        if text:
            self.callback(text)

    def flush(self):
        self._orig_stdout.flush()


def _parse_progress(text):
    """AYNEN tasindi -- image_acquirer.py'nin 'İlerleme: %42 (...)' satirini parse eder."""
    m = re.search(r"[İI]lerleme:\s*%?\s*(\d+(?:\.\d+)?)", text)
    if m:
        return float(m.group(1))
    return None


def _restrict_key_file_permissions(path):
    """
    Operator Tor ozel anahtarini (keys/operator_tor_key.json) sadece
    mevcut kullanicinin okuyabilmesi icin izinleri kisitlar -- ayni
    makinede baska bir yerel kullanici hesabi bu dosyayi okuyamasin diye
    (dosya .gitignore'da oldugu icin commit'e girmiyor, ama diskte duz
    metin JSON olarak kaliyor). Best-effort: izin ayarlanamazsa (orn.
    dosya sistemi desteklemiyorsa) sessizce gecilir, anahtar yine de
    yazilmis/okunabilir olur -- akisi durdurmaz.
    """
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    if os.name == "nt":
        user = os.environ.get("USERNAME")
        if user:
            try:
                subprocess.run(
                    ["icacls", path, "/inheritance:r", "/grant:r", f"{user}:F"],
                    capture_output=True, check=False,
                )
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Baglanti worker'i -- Tor/VPN/Dogrudan baglanti kurma islemini arka planda
# yapar (ozellikle Tor'da tor.exe baslatma + bootstrap suresi UI'yi
# kilitlemesin diye -- tasarim sisteminin 'asla sessiz bekleme olmasin'
# kuralina uyum). Ic mantik (SSHConnector, tor_client.start_client)
# gui_v2.py'deki _connect() ile BIREBIR AYNI sirayla cagriliyor.
# ---------------------------------------------------------------------------
class ConnectWorker(QThread):
    log = Signal(str, str)
    error = Signal(str)
    connected = Signal(object, bool)  # (SSHConnector, tor_uzerinden_mi)

    def __init__(self, host, port, user, password, key_path, conn_method,
                 operator_private_key, existing_tor_handle, strict_host_key=True,
                 parent=None):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.key_path = key_path
        self.conn_method = conn_method
        self.operator_private_key = operator_private_key
        # False ise sunucunun SSH kimligi (host key) daha once hic
        # gorulmemis olsa bile baglantiya izin verilir -- sahsa ait
        # cihazlarda parmak izini teyit edecek bir yetkili olmayacagi icin.
        self.strict_host_key = strict_host_key
        self.existing_tor_handle = existing_tor_handle
        self.tor_client_handle = None

    def run(self):
        socks_proxy_port = None
        if self.conn_method == "tor":
            if not self.host.lower().endswith(".onion"):
                self.error.emit("Tor modunda Host alanına hedefin .onion adresini yazmalısınız.")
                return
            if not self.operator_private_key:
                self.error.emit("Operatör anahtarı hazır değil (onion_auth.py bulunamadı).")
                return

            if self.existing_tor_handle is not None:
                self.existing_tor_handle.close()

            self.log.emit("[i] Tor başlatılıyor, .onion adresine ulaşılmaya çalışılıyor...", "info")
            bare_onion = self.host[:-len(".onion")]
            self.tor_client_handle = tor_client.start_client(bare_onion, self.operator_private_key)
            if self.tor_client_handle is None:
                self.error.emit("Tor'a bağlanılamadı. Gömülü Tor binary'sinin kurulu olduğundan emin olun.")
                return
            socks_proxy_port = self.tor_client_handle.socks_port

        self.log.emit(f"Bağlanılıyor: {self.user}@{self.host}:{self.port} ...", "info")
        ssh = SSHConnector(
            host=self.host, port=self.port, username=self.user,
            password=self.password, key_path=self.key_path, strict=self.strict_host_key,
            socks_proxy_port=socks_proxy_port,
        )

        if ssh.connect():
            if not self.strict_host_key:
                aciklama = {
                    "learned": f"Sunucunun kimligi ilk kez ogrenilip kaydedildi: {self.user}@{self.host}:{self.port}",
                    "known": f"Sunucu, daha once ogrenilmis kimligiyle eslesti: {self.user}@{self.host}:{self.port}",
                }.get(ssh.host_key_status, f"Sunucu kimlik dogrulamasi atlanarak baglanildi: {self.user}@{self.host}:{self.port}")
                # Sunucunun GERCEK host key parmak izi de kaydediliyor --
                # onceden sadece "ogrenildi/biliniyor" yaziyordu, ileride
                # bagimsiz bir kaynaktan (orn. hedef IT yetkilisi) alinacak
                # bir parmak iziyle karsilastirilabilecek somut bir deger
                # yoktu (guvenlik incelemesinde bulunan bir bosluk).
                coc.log_event(coc.EVENT_HOST_KEY_VERIFICATION_SKIPPED, aciklama, ssh.host_key_fingerprint)
            self.connected.emit(ssh, bool(socks_proxy_port))
        else:
            self.error.emit(self._connect_error_message(ssh))
            if self.tor_client_handle is not None:
                self.tor_client_handle.close()
                self.tor_client_handle = None

    @staticmethod
    def _connect_error_message(ssh):
        """ssh.last_error_type'a gore kullaniciya NE YAPMASI gerektigini
        soyleyen, nedene ozgu bir mesaj uretir -- genel "kontrol edin"
        yerine (bkz. docs/oturum_ozeti.md, kullanicinin bu konudaki geri
        bildirimi)."""
        detay = str(ssh.last_error) if ssh.last_error else ""
        if ssh.last_error_type == "host_key":
            return (
                "Bu sunucuya daha önce hiç bağlanılmamış, kimliği doğrulanamadı.\n"
                "Yukarıdaki \"Sunucu Kimlik Doğrulama\" seçeneğinden \"Doğrulamayı atla\"yı "
                "işaretleyip tekrar deneyin."
            )
        if ssh.last_error_type == "host_key_mismatch":
            return (
                "DİKKAT: Bu sunucunun kimliği, daha önce bu bilgisayardan bağlanılan kaydıyla "
                "UYUŞMUYOR.\nBu, sunucunun gerçekten değiştiğini (örn. yeniden kurulum) ya da "
                "aranıza birinin girdiğini gösterebilir -- \"Doğrulamayı atla\" seçili olsa "
                "bile bu yüzden bağlantı reddedildi. Devam etmeden önce durumu doğrulayın."
            )
        if ssh.last_error_type == "auth":
            return "Kullanıcı adı veya şifre/anahtar yanlış görünüyor. Bilgileri kontrol edip tekrar deneyin."
        if ssh.last_error_type == "unreachable":
            return (
                "Sunucuya hiç ulaşılamadı.\nHedefte SSH servisinin çalıştığından, doğru "
                "IP/port kullandığınızdan ve aranızda bir güvenlik duvarının bağlantıyı "
                "engellemediğinden emin olun."
            )
        return f"SSH bağlantısı kurulamadı.{(' Detay: ' + detay) if detay else ''}"


# ---------------------------------------------------------------------------
# Imaj alma worker'i -- _acquisition_worker / _acquisition_worker_windows /
# _file_acquisition_worker govdeleri gui_v2.py'den BIREBIR AYNI SIRAYLA
# tasindi, sadece UI cagrilari sinyale cevrildi.
# ---------------------------------------------------------------------------
class AcquisitionWorker(QThread):
    log = Signal(str, str)
    status = Signal(str)
    progress = Signal(float)
    report_ready = Signal(object, str)
    ask_verify = Signal(str)
    ask_yesno = Signal(str, str)  # title, msg -- cevap _yesno_result/_yesno_event uzerinden doner
    finished_ok = Signal()

    def __init__(self, kind, ssh, ctx, parent=None):
        """
        kind: 'linux_disk' | 'windows_disk' | 'file'
        ctx: worker'in ihtiyac duydugu TUM degerlerin sozlugu -- widget'a
        DOKUNMADAN calisabilmesi icin cagiran taraf (ana thread) hepsini
        onceden toplayip buraya koyuyor.
        """
        super().__init__(parent)
        self.kind = kind
        self.ssh = ssh
        self.ctx = ctx
        self._old_stdout = None
        self._yesno_result = False
        self._yesno_event = threading.Event()

    def run(self):
        if self.kind == "linux_disk":
            self._run_linux_disk()
        elif self.kind == "windows_disk":
            self._run_windows_disk()
        else:
            self._run_file()

    def _ask_yesno_blocking(self, title, msg):
        """
        Worker thread'den cagirilir, ana thread'de bir dialog gosterilip
        cevaplanana kadar BLOKE olur. Onceki denemede sinyal argumani
        olarak bir dict gecirilip ana thread'deki slot'un onu doldurmasi
        planlanmisti (Qt.BlockingQueuedConnection ile) -- ama PySide6
        bu tur genel Python nesnelerini kuyruklu baglantilarda KOPYALIYOR,
        orijinal referans degil, bu yuzden mutasyon geri yansimiyordu
        (mock testle yakalandi). Bunun yerine cevap, worker'in KENDI
        ornek (instance) niteliklerine yaziliyor -- worker nesnesinin
        kendisi her iki thread'den de AYNI Python nesnesi, bu yuzden
        guvenilir.
        """
        self._yesno_event.clear()
        self.ask_yesno.emit(title, msg)
        self._yesno_event.wait()
        return self._yesno_result

    def _new_report(self, engine, method, **kwargs):
        if ForensicReport is None:
            return None
        c = self.ctx
        report = ForensicReport(
            case_id=c["case_id"], examiner=c["examiner"], custodian=c["custodian"],
            organization=c["organization"], display_timezone=self._display_timezone,
        )
        report.start(engine=engine, method=method, connection_method=c["conn_method"], **kwargs)
        return report

    def _save_report(self, report, output_dir):
        if report is None:
            return None
        try:
            path = report.save(output_dir)
            self.log.emit(f"[+] Rapor: {path}", "info")
            return path
        except OSError as exc:
            self.log.emit(f"[UYARI] Rapor yazilamadi: {exc}", "warn")
            return None

    # -- Linux tam disk -- gui_v2.py _acquisition_worker ile BIREBIR AYNI --
    def _run_linux_disk(self):
        c = self.ctx
        disk, out_path, mode, password, block_size_mb = (
            c["disk"], c["out_path"], c["mode"], c["password"], c["block_size_mb"],
        )
        compress = c.get("compress", False)
        try:
            disk_description = get_disk_description(self.ssh, disk)
        except Exception:
            disk_description = ""
        report = self._new_report(
            engine="ssh_engine", method="disk", target_os="linux",
            target_host=c["host"], source_identifier=disk, acquisition_type=mode,
            source_description=disk_description,
        )
        self._old_stdout = sys.stdout
        sys.stdout = StdoutRedirector(self._on_stdout)
        try:
            manifest_path = None
            resume_state = None
            start_block = 0

            mevcut = find_incomplete_manifest(disk)
            if mevcut:
                manifest_path, resume_state = mevcut
                completed = len(resume_state.get("acquired_blocks", []))
                total = resume_state.get("total_blocks", 0)
                self.log.emit(f"[UYARI] Yarım kalan işlem bulundu: {completed}/{total} blok tamamlanmış.", None)
                devam = self._ask_yesno_blocking(
                    "Yarım Kalan İşlem",
                    f"Bu disk için yarım kalan bir işlem bulundu.\nTamamlanan: {completed}/{total} blok\nDevam edilsin mi?",
                )
                if devam:
                    start_block = completed
                else:
                    manifest_path = None
                    resume_state = None

            apply_wb = (mode == "offline")
            if report:
                report.set_write_blocking(
                    apply_wb,
                    "Offline Acquisition" if apply_wb else (
                        "Live Acquisition -- disk aktif kullanimda, kilitlenmedi. "
                        "Bloklar bir sureye yayilarak okundugu icin imaj, diskin "
                        "TEK bir anina degil, alma suresince degisebilecek bir "
                        "durumuna karsilik gelebilir."
                    ),
                )

            sonuc = acquire_disk_image(
                self.ssh, disk, password,
                output_dir=os.path.dirname(out_path) or ".",
                block_size_mb=resume_state["block_size_mb"] if resume_state else block_size_mb,
                apply_write_blocker=apply_wb,
                total_blocks=resume_state["total_blocks"] if resume_state else None,
                start_block=start_block, resume_state=resume_state, manifest_path=manifest_path,
            )

            while sonuc is not None and "resume_from" in sonuc:
                tekrar = self._ask_yesno_blocking(
                    "Bağlantı Koptu",
                    f"Bağlantı blok {sonuc['resume_from']}'de kesildi.\nTekrar bağlanıp devam edilsin mi?",
                )
                if not tekrar:
                    self.log.emit("[BİLGİ] İşlem yarım bırakıldı. Manifest korunuyor.", None)
                    break
                if not self.ssh.connect():
                    self.log.emit("[HATA] SSH bağlantısı kurulamadı.", None)
                    break
                sonuc = acquire_disk_image(
                    self.ssh, disk, password,
                    output_dir=os.path.dirname(out_path) or ".",
                    block_size_mb=sonuc.get("block_size_mb", block_size_mb),
                    apply_write_blocker=apply_wb, total_blocks=sonuc["total_blocks"],
                    start_block=sonuc["resume_from"], resume_state=sonuc,
                    manifest_path=sonuc.get("manifest_path"),
                )

            if sonuc is None:
                if report:
                    report.finish(status="failed", output_path=out_path)
                    self._save_report(report, os.path.dirname(out_path) or ".")
                self.log.emit("[HATA] İmaj alma başarısız oldu.", None)
                return

            if "resume_from" in sonuc:
                if report:
                    report.finish(
                        status="partial", output_path=out_path,
                        chunk_size_bytes=sonuc.get("block_size_mb", 0) * 1024 * 1024,
                        chunk_count=len(sonuc.get("acquired_blocks", [])),
                        failed_items=[f"resume_from={sonuc['resume_from']}"],
                    )
                    self._save_report(report, sonuc.get("output_dir") or os.path.dirname(out_path) or ".")
                self.log.emit("[BİLGİ] İşlem yarım kaldı. Daha sonra aynı diski seçip devam edebilirsiniz.", None)
                return

            self.log.emit("\n[+] Bloklar birleştiriliyor...", "info")
            imaj_yolu = concatenate_blocks(
                sonuc["block_paths"], sonuc["total_blocks"],
                output_dir=sonuc["output_dir"], output_path=out_path, cleanup=(mode != "live"),
            )
            if imaj_yolu is None:
                if report:
                    report.finish(
                        status="failed", output_path=out_path,
                        failed_items=[str(b) for b in sonuc.get("failed_blocks", [])],
                    )
                    self._save_report(report, sonuc.get("output_dir") or os.path.dirname(out_path) or ".")
                self.log.emit("[HATA] Eksik bloklar nedeniyle imaj birleştirilemedi.", None)
                return

            self.log.emit(f"[BAŞARILI] İmaj birleştirildi: {imaj_yolu}", None)
            master_hash = local_master_hash(imaj_yolu)
            self.log.emit(f"[+] Yerel master SHA-256: {master_hash}", "info")
            raw_bytes = os.path.getsize(imaj_yolu)

            if compress:
                self.log.emit("[i] İmaj gzip ile sıkıştırılıyor (bu biraz sürebilir)...", "info")
                onceki_yol = imaj_yolu
                imaj_yolu = compress_image(imaj_yolu, remove_original=True)
                compressed_bytes = os.path.getsize(imaj_yolu)
                coc.log_event(
                    coc.EVENT_IMAGE_COMPRESSED,
                    f"İmaj sıkıştırıldı: {onceki_yol} -> {imaj_yolu} "
                    f"({raw_bytes} -> {compressed_bytes} bayt)",
                )
                self.log.emit(
                    f"[+] Sıkıştırma tamamlandı: {raw_bytes / (1024**2):.1f} MB -> "
                    f"{compressed_bytes / (1024**2):.1f} MB",
                    "ok",
                )

            self.status.emit("İmaj alma tamamlandı.")
            self.progress.emit(100)

            if report:
                bs = sonuc.get("block_size_mb", 0)
                report.finish(
                    status="success" if not sonuc.get("failed_blocks") else "partial",
                    output_path=imaj_yolu, image_hash=master_hash,
                    total_bytes=raw_bytes, chunk_size_bytes=bs * 1024 * 1024,
                    chunk_count=len(sonuc.get("acquired_blocks", [])),
                    failed_items=[str(b) for b in sonuc.get("failed_blocks", [])],
                )
                rapor_yolu = self._save_report(report, os.path.dirname(imaj_yolu) or ".")
                self.report_ready.emit(report, rapor_yolu)

            if compress:
                self.log.emit(
                    "[i] İmaj sıkıştırıldığı için otomatik doğrulama atlandı -- "
                    "gerekirse verify_report.py ile bağımsız doğrulayabilirsiniz.",
                    "info",
                )
            else:
                self.ask_verify.emit(imaj_yolu)

        except Exception as exc:
            self.log.emit(f"[HATA] Beklenmeyen hata: {exc}", None)
            import traceback
            self.log.emit(traceback.format_exc(), "err")
        finally:
            sys.stdout = self._old_stdout

    def _on_stdout(self, text):
        pct = _parse_progress(text)
        if pct is not None:
            self.progress.emit(pct)
            self.status.emit(f"İlerleme: %{pct:.1f}")
        self.log.emit(text.rstrip("\n"), None)

    # -- Windows tam disk -- gui_v2.py _acquisition_worker_windows ile AYNI --
    def _run_windows_disk(self):
        c = self.ctx
        disk_number, out_path, mode, block_size_mb = (
            c["disk_number"], c["out_path"], c["mode"], c["block_size_mb"],
        )
        compress = c.get("compress", False)
        try:
            disk_description = get_disk_description_windows(self.ssh, disk_number)
        except Exception:
            disk_description = ""
        report = self._new_report(
            engine="ssh_engine", method="disk", target_os="windows",
            target_host=c["host"], source_identifier=f"PhysicalDrive{disk_number}", acquisition_type=mode,
            source_description=disk_description,
        )
        try:
            apply_wb = (mode == "offline")
            if report:
                report.set_write_blocking(
                    apply_wb,
                    "Offline Acquisition" if apply_wb else (
                        "Live Acquisition -- disk aktif kullanimda, kilitlenmedi. "
                        "Bloklar bir sureye yayilarak okundugu icin imaj, diskin "
                        "TEK bir anina degil, alma suresince degisebilecek bir "
                        "durumuna karsilik gelebilir."
                    ),
                )

            def ilerleme(done, total):
                pct = (done * 100 / total) if total else 0
                self.progress.emit(pct)
                self.status.emit(f"İlerleme: %{pct:.0f} ({done}/{total} blok)")

            sonuc = acquire_disk_image_windows(
                self.ssh, disk_number, output_dir=os.path.dirname(out_path) or ".",
                block_size_mb=block_size_mb, apply_write_blocker=apply_wb, progress_callback=ilerleme,
            )

            while sonuc is not None and "resume_from" in sonuc:
                tekrar = self._ask_yesno_blocking(
                    "Bağlantı Koptu",
                    f"Bağlantı blok {sonuc['resume_from']}'de kesildi.\nTekrar bağlanıp devam edilsin mi?",
                )
                if not tekrar:
                    self.log.emit("[BİLGİ] İşlem yarım bırakıldı. Manifest korunuyor.", None)
                    break
                if not self.ssh.connect():
                    self.log.emit("[HATA] SSH bağlantısı kurulamadı.", None)
                    break
                sonuc = acquire_disk_image_windows(
                    self.ssh, disk_number, output_dir=sonuc["output_dir"],
                    block_size_mb=sonuc.get("block_size_mb", block_size_mb), apply_write_blocker=False,
                    total_blocks=sonuc["total_blocks"], start_block=sonuc["resume_from"],
                    resume_state=sonuc, manifest_path=sonuc.get("manifest_path"), progress_callback=ilerleme,
                )

            if sonuc is None:
                if report:
                    report.finish(status="failed", output_path=out_path)
                    self._save_report(report, os.path.dirname(out_path) or ".")
                self.log.emit("[HATA] İmaj alma başarısız oldu (Windows).", None)
                return

            if "resume_from" in sonuc:
                if report:
                    report.finish(
                        status="partial", output_path=out_path,
                        chunk_size_bytes=sonuc.get("block_size_mb", 0) * 1024 * 1024,
                        chunk_count=len(sonuc.get("acquired_blocks", [])),
                        failed_items=[f"resume_from={sonuc['resume_from']}"],
                    )
                    self._save_report(report, sonuc.get("output_dir") or os.path.dirname(out_path) or ".")
                self.log.emit("[BİLGİ] İşlem yarım kaldı. Daha sonra aynı diski seçip devam edebilirsiniz.", None)
                return

            self.log.emit("\n[+] Bloklar birleştiriliyor...", "info")
            imaj_yolu = concatenate_blocks(
                sonuc["block_paths"], sonuc["total_blocks"],
                output_dir=sonuc["output_dir"], output_path=out_path, cleanup=(mode != "live"),
            )
            if imaj_yolu is None:
                if report:
                    report.finish(
                        status="failed", output_path=out_path,
                        failed_items=[str(b) for b in sonuc.get("failed_blocks", [])],
                    )
                    self._save_report(report, sonuc.get("output_dir") or os.path.dirname(out_path) or ".")
                self.log.emit("[HATA] Eksik bloklar nedeniyle imaj birleştirilemedi.", None)
                return

            self.log.emit(f"[BAŞARILI] İmaj birleştirildi: {imaj_yolu}", None)
            master_hash = local_master_hash(imaj_yolu)
            self.log.emit(f"[+] Yerel master SHA-256: {master_hash}", "info")
            raw_bytes = os.path.getsize(imaj_yolu)

            if compress:
                self.log.emit("[i] İmaj gzip ile sıkıştırılıyor (bu biraz sürebilir)...", "info")
                onceki_yol = imaj_yolu
                imaj_yolu = compress_image(imaj_yolu, remove_original=True)
                compressed_bytes = os.path.getsize(imaj_yolu)
                coc.log_event(
                    coc.EVENT_IMAGE_COMPRESSED,
                    f"İmaj sıkıştırıldı: {onceki_yol} -> {imaj_yolu} "
                    f"({raw_bytes} -> {compressed_bytes} bayt)",
                )
                self.log.emit(
                    f"[+] Sıkıştırma tamamlandı: {raw_bytes / (1024**2):.1f} MB -> "
                    f"{compressed_bytes / (1024**2):.1f} MB",
                    "ok",
                )

            self.status.emit("İmaj alma tamamlandı.")
            self.progress.emit(100)

            if report:
                bs = sonuc.get("block_size_mb", 0)
                report.finish(
                    status="success" if not sonuc.get("failed_blocks") else "partial",
                    output_path=imaj_yolu, image_hash=master_hash,
                    total_bytes=raw_bytes, chunk_size_bytes=bs * 1024 * 1024,
                    chunk_count=len(sonuc.get("acquired_blocks", [])),
                    failed_items=[str(b) for b in sonuc.get("failed_blocks", [])],
                )
                rapor_yolu = self._save_report(report, os.path.dirname(imaj_yolu) or ".")
                self.report_ready.emit(report, rapor_yolu)

            if compress:
                self.log.emit(
                    "[i] İmaj sıkıştırıldığı için otomatik doğrulama atlandı -- "
                    "gerekirse verify_report.py ile bağımsız doğrulayabilirsiniz.",
                    "info",
                )
            else:
                self.ask_verify.emit(imaj_yolu)

        except Exception as exc:
            self.log.emit(f"[HATA] Beklenmeyen hata: {exc}", None)
            import traceback
            self.log.emit(traceback.format_exc(), "err")

    # -- Dosya/klasor -- gui_v2.py _file_acquisition_worker ile AYNI --
    def _run_file(self):
        c = self.ctx
        remote_path, out_dir, password, target_os = c["remote_path"], c["out_dir"], c["password"], c["target_os"]
        report = self._new_report(
            engine="ssh_engine", method="file", target_os=target_os,
            target_host=c["host"], source_identifier=remote_path,
            source_description="Dosya/klasor modu -- write-blocker uygulanmaz",
        )
        try:
            def ilerleme(done, total):
                pct = (done * 100 / total) if total else 0
                self.progress.emit(pct)
                self.status.emit(f"{done}/{total} dosya alındı (%{pct:.0f})")

            if target_os == "windows":
                manifest = acquire_remote_tree_windows(self.ssh, remote_path, out_dir, progress_callback=ilerleme)
            else:
                manifest = acquire_remote_tree(self.ssh, remote_path, out_dir, password=password, progress_callback=ilerleme)

            if manifest is None:
                if report:
                    report.finish(status="failed", output_path=out_dir)
                    self._save_report(report, out_dir)
                self.log.emit(f"[HATA] Uzak yol bulunamadı: {remote_path}", None)
                self.status.emit("Bulunamadı.")
                return

            basarili = len(manifest["acquired"])
            basarisiz = len(manifest["failed"])
            self.log.emit(f"[BAŞARILI] {basarili}/{manifest['total_files']} dosya alındı ve doğrulandı.", None)
            if basarisiz:
                self.log.emit(f"[UYARI] {basarisiz} dosya alınamadı:", None)
                for yol in manifest["failed"]:
                    self.log.emit(f"  - {yol}", "plain")
            self.log.emit(f"[+] Manifest: {os.path.join(out_dir, 'manifest_files.json')}", "info")
            self.status.emit("Dosya/klasör alma tamamlandı.")
            self.progress.emit(100)

            if report:
                toplam_bayt = sum(
                    os.path.getsize(a["local_path"]) for a in manifest["acquired"]
                    if os.path.exists(a["local_path"])
                )
                report.finish(
                    status="success" if not manifest["failed"] else "partial",
                    output_path=out_dir, total_bytes=toplam_bayt,
                    chunk_count=manifest["total_files"], failed_items=manifest["failed"],
                )
                rapor_yolu = self._save_report(report, out_dir)
                self.report_ready.emit(report, rapor_yolu)

        except Exception as exc:
            self.log.emit(f"[HATA] Beklenmeyen hata: {exc}", None)
            import traceback
            self.log.emit(traceback.format_exc(), "err")


class VerifyWorker(QThread):
    """hash_verifier.verify_file() buyuk dosyalarda yavas olabiliyor --
    orijinalde ana thread'de calisiyordu (bu davranisi bozmuyoruz, sadece
    UI donmasin diye burada QThread'e aldik -- is mantigi ayni)."""
    log = Signal(str, str)
    result_ok = Signal(str, int)
    result_mismatch = Signal(str, str)
    result_error = Signal(str)

    def __init__(self, path, expected, report=None, report_path=None, parent=None):
        super().__init__(parent)
        self.path = path
        self.expected = expected
        # Verilirse (az onceki alma islemine ait otomatik dogrulama --
        # bkz. _on_ask_verify), dogrulama sonucu bu rapora islenip yeniden
        # kaydedilir -- oncesinde report.json/html HER ZAMAN "verified:
        # false" yaziyordu, dogrulama basarili olsa bile hic guncellenmiyordu.
        self.report = report
        self.report_path = report_path

    def _update_report(self, matched):
        if self.report is None or self.report_path is None:
            return
        try:
            self.report.set_verification(matched)
            self.report.save(os.path.dirname(self.report_path))
        except OSError as exc:
            self.log.emit(f"[UYARI] Doğrulama sonucu rapora yazılamadı: {exc}", "warn")

    def run(self):
        try:
            result_obj = verify_file(self.path, self.expected)
            coc.log_event(
                coc.EVENT_HASH_VERIFIED,
                f"İmaj doğrulandı: {self.path} ({result_obj.byte_count} bayt)", result_obj.digest,
            )
            self._update_report(True)
            self.result_ok.emit(result_obj.digest, result_obj.byte_count)
        except HashMismatchError as exc:
            coc.log_event(coc.EVENT_HASH_MISMATCH, f"Doğrulama başarısız: {self.path}", exc.actual)
            self._update_report(False)
            self.result_mismatch.emit(exc.expected, exc.actual)
        except (HashError, FileNotFoundError, OSError) as exc:
            coc.log_event(coc.EVENT_EXAM_ERROR, f"Doğrulama hatası: {exc}")
            self.result_error.emit(str(exc))


# ---------------------------------------------------------------------------
# Uzak "Gozat" penceresi -- operator yolu elle yazmak yerine tiklayarak
# gezinebilir. Salt-okunur (list_remote_directory[_windows], find/
# Get-ChildItem), hicbir sey yazmiyor/degistirmiyor; her klasor acilisi
# chain-of-custody'ye DIRECTORY_LISTED olarak ayrica loglanir (bkz.
# file_acquirer.py/windows_acquirer.py).
# ---------------------------------------------------------------------------
class RemoteBrowseDialog(QDialog):
    def __init__(self, ssh, target_os, start_path, parent=None):
        super().__init__(parent)
        self.ssh = ssh
        self.target_os = target_os  # "linux" / "windows"
        self.current_path = start_path
        self.selected_path = None

        self.setWindowTitle("Uzak Klasör/Dosya Seç")
        self.setStyleSheet(f"background-color:{ui.BG_SURFACE};")
        self.resize(560, 420)

        layout = QVBoxLayout(self)

        path_row = QHBoxLayout()
        up_btn = widgets.SecondaryButton("↑ Yukarı")
        up_btn.clicked.connect(self._go_up)
        path_row.addWidget(up_btn)
        self.path_label = widgets.MonoLabel(self.current_path)
        path_row.addWidget(self.path_label, stretch=1)
        layout.addLayout(path_row)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.list_widget, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;"
        )
        layout.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        select_folder_btn = widgets.PrimaryButton("Bu Klasörü Seç")
        select_folder_btn.clicked.connect(self._select_current_folder)
        btn_row.addWidget(select_folder_btn)
        btn_row.addStretch()
        cancel_btn = widgets.SecondaryButton("İptal")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self._refresh()

    def _list_dir(self, path):
        if self.target_os == "windows":
            return list_remote_directory_windows(self.ssh, path)
        return list_remote_directory(self.ssh, path)

    def _refresh(self):
        self.path_label.setText(self.current_path)
        self.list_widget.clear()
        entries = self._list_dir(self.current_path)
        if entries is None:
            self.status_label.setText("Klasör okunamadı (izin yok ya da yol bulunamadı).")
            return
        if not entries:
            self.status_label.setText("(boş klasör)")
            return
        self.status_label.setText(f"{len(entries)} öge")
        for name, is_dir in entries:
            item = QListWidgetItem(icons.icon("folder" if is_dir else "file-text", color=ui.TEXT_MAIN, size=16), name)
            item.setData(Qt.ItemDataRole.UserRole, (name, is_dir))
            self.list_widget.addItem(item)

    def _join(self, base, name):
        sep = "\\" if self.target_os == "windows" else "/"
        return base.rstrip("/\\") + sep + name

    def _parent(self, path):
        sep = "\\" if self.target_os == "windows" else "/"
        trimmed = path.rstrip("/\\")
        if sep in trimmed:
            parent = trimmed.rsplit(sep, 1)[0]
            return parent if parent else sep
        return path

    def _go_up(self):
        self.current_path = self._parent(self.current_path)
        self._refresh()

    def _on_item_double_clicked(self, item):
        name, is_dir = item.data(Qt.ItemDataRole.UserRole)
        target = self._join(self.current_path, name)
        if is_dir:
            self.current_path = target
            self._refresh()
        else:
            self.selected_path = target
            self.accept()

    def _select_current_folder(self):
        self.selected_path = self.current_path
        self.accept()


# ---------------------------------------------------------------------------
# Ana widget
# ---------------------------------------------------------------------------
class ForensicWidget(QWidget):
    def __init__(self, on_back=None, on_show_help=None, initial_case_id="", initial_examiner="",
                 initial_custodian="", initial_organization="", initial_connection_method=None,
                 display_timezone=None, parent=None):
        """
        initial_connection_method: launcher'dan hangi yontem sayfasi
        ("direct"/"vpn"/"tor") ile buraya girildiyse burada gelir. VERILDIYSE
        (yani launcher'dan aciliyorsa -- ki her zaman boyle olur), asagidaki
        Baglanti Yontemi SECICISI HIC GOSTERILMEZ -- kullanici zaten launcher'da
        secim yapti, ayni secimi burada TEKRAR sormak gereksizdi (kullanici
        geri bildirimi). Sadece secili yontemin adi + ilgili bilgi paneli
        (VPN notu / Tor anahtari+uyarisi) gosterilir. initial_connection_method
        verilMEZse (arac tek basina `python gui_v2.py` ile acildiysa),
        secici tam haliyle gosterilir -- CLAUDE.md'nin 'her modul tek basina
        calisabilmeli' kurali icin gerekli.
        """
        super().__init__(parent)
        self.on_back = on_back
        # launcher icinden aciliyorsa (her zaman boyle) Bilgi Merkezi
        # sayfasina goturen callback -- standalone `python gui_v2.py`
        # calistirmasinda None kalir, bu durumda _show_help_topic() ayni
        # icerigi kucuk bir dialogda gosterir (bkz. asagisi).
        self.on_show_help = on_show_help
        self._initial_case_id = initial_case_id
        self._initial_examiner = initial_examiner
        self._initial_custodian = initial_custodian
        self._initial_organization = initial_organization
        self._display_timezone = display_timezone
        self._initial_connection_method = initial_connection_method
        self._method_locked = initial_connection_method is not None

        self.ssh = None
        self.tor_client_handle = None
        self._pid_map = {}
        self.connect_worker = None
        self._last_report = None
        self._last_report_path = None
        self.acq_worker = None
        self.verify_worker = None
        self._operator_private_key = None
        self._operator_public_key = None

        if not PARAMIKO_OK:
            self._pending_error = f"paramiko kurulu değil:\n{IMPORT_ERROR}\n\nKurmak için: pip install paramiko"
            layout = QVBoxLayout(self)
            lbl = QLabel(self._pending_error)
            lbl.setStyleSheet(f"color:{ui.ERROR};")
            layout.addWidget(lbl)
            return

        self._build_ui()
        self._log("Program başladı. SSH bilgilerini girin ve 'Bağlan' tuşuna basın.", "info")

    # -- UI Olusturma -------------------------------------------------------
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(20, 14, 20, 14)
        if self.on_back:
            back_btn = widgets.SecondaryButton("← Geri")
            back_btn.clicked.connect(self.on_back)
            header.addWidget(back_btn)
        title = QLabel("SSH ile Uzak İmaj Al")
        title.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_TITLE}px; font-weight:600;")
        header.addWidget(title)
        header.addStretch()
        self.conn_badge = widgets.StatusBadge()
        header.addWidget(self.conn_badge)
        header_w = QWidget()
        header_w.setLayout(header)
        header_w.setStyleSheet(f"background-color:{ui.BG_SURFACE}; border-bottom:1px solid {ui.BORDER};")
        outer.addWidget(header_w)

        from PySide6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        body = QVBoxLayout(inner)
        body.setContentsMargins(20, 16, 20, 16)
        body.setSpacing(ui.CARD_GAP)
        scroll.setWidget(inner)
        outer.addWidget(scroll, stretch=1)

        # === Vaka Bilgileri ===
        vaka = widgets.Card("Vaka Bilgileri")
        note = QLabel("(İsteğe bağlı -- rapor üretmiyorsanız boş bırakabilirsiniz)")
        note.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px; font-style:italic;")
        vaka.body.addWidget(note)
        self.entry_case_id = self._labeled_row(vaka.body, "Vaka No", self._initial_case_id)
        self.entry_examiner = self._labeled_row(vaka.body, "İnceleyen", self._initial_examiner)
        self.entry_custodian = self._labeled_row(vaka.body, "Cihaz Sahibi / Yetkili Kişi", self._initial_custodian)
        self.entry_organization = self._labeled_row(vaka.body, "Organizasyon", self._initial_organization)
        body.addWidget(vaka)

        # === Baglanti Yontemi ===
        self.conn_method_value = self._initial_connection_method or "direct"
        yontem = widgets.Card("Bağlantı Yöntemi")
        if self._method_locked:
            method_names = {"direct": "Doğrudan / Port Yönlendirme", "vpn": "VPN", "tor": "Tor (Acil Durum)"}
            lbl = QLabel(f"Seçili yöntem: {method_names.get(self.conn_method_value, self.conn_method_value)}")
            lbl.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_BODY}px; font-weight:600;")
            yontem.body.addWidget(lbl)
            hint = QLabel("(Yöntemi değiştirmek için \"Geri\" ile ana sayfaya dönüp farklı bir yöntem seçin.)")
            hint.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
            yontem.body.addWidget(hint)
        else:
            row = QHBoxLayout()
            self.method_group = QButtonGroup(self)
            self.radio_direct = widgets.RadioButton("Doğrudan / Port Yönlendirme")
            self.radio_vpn = widgets.RadioButton("VPN")
            self.radio_tor = widgets.RadioButton("Tor (Acil Durum)")
            self.radio_direct.setChecked(True)
            for r, val in [(self.radio_direct, "direct"), (self.radio_vpn, "vpn"), (self.radio_tor, "tor")]:
                self.method_group.addButton(r)
                row.addWidget(r)
                r.toggled.connect(self._on_conn_method_change)
            row.addStretch()
            yontem.body.addLayout(row)

        self.vpn_info = self._build_vpn_info_panel()
        self.tor_info = self._build_tor_info_panel()
        yontem.body.addWidget(self.vpn_info)
        yontem.body.addWidget(self.tor_info)
        body.addWidget(yontem)

        # === SSH Baglanti Bilgileri ===
        conn = widgets.Card("SSH Bağlantı Bilgileri")
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Host:"))
        self.entry_host = widgets.MonoInput()
        self.entry_host.setText("192.168.1.100")
        row1.addWidget(self.entry_host)
        row1.addWidget(QLabel("Port:"))
        self.entry_port = widgets.MonoInput()
        self.entry_port.setText("22")
        self.entry_port.setFixedWidth(70)
        row1.addWidget(self.entry_port)
        conn.body.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Kullanıcı:"))
        self.entry_user = widgets.Input()
        row2.addWidget(self.entry_user)
        row2.addWidget(QLabel("Şifre:"))
        self.entry_pass = widgets.Input()
        self.entry_pass.setEchoMode(QLineEdit.EchoMode.Password)
        row2.addWidget(self.entry_pass)
        conn.body.addLayout(row2)

        self._recent_hosts = _load_recent_hosts()
        if self._recent_hosts:
            completer = QCompleter([e["host"] for e in self._recent_hosts], self.entry_host)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            self.entry_host.setCompleter(completer)
            completer.activated[str].connect(self._on_recent_host_picked)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("SSH Anahtar:"))
        self.entry_key = widgets.MonoInput()
        row3.addWidget(self.entry_key)
        browse_key_btn = widgets.SecondaryButton("Gözat")
        browse_key_btn.clicked.connect(self._browse_key)
        row3.addWidget(browse_key_btn)
        conn.body.addLayout(row3)

        # === Sunucu Kimlik Dogrulama (host key) ===
        self.strict_host_key_value = True
        hk_label = QLabel("Sunucu Kimlik Doğrulama:")
        hk_label.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px; font-weight:600;")
        conn.body.addWidget(hk_label)

        hk_row = QHBoxLayout()
        self.hostkey_group = QButtonGroup(self)
        self.radio_hostkey_strict = widgets.RadioButton("Sıkı doğrula (önerilen)")
        self.radio_hostkey_skip = widgets.RadioButton("Doğrulamayı atla")
        self.radio_hostkey_strict.setChecked(True)
        for r in (self.radio_hostkey_strict, self.radio_hostkey_skip):
            self.hostkey_group.addButton(r)
            hk_row.addWidget(r)
            r.toggled.connect(self._on_hostkey_mode_change)
        hk_row.addStretch()
        conn.body.addLayout(hk_row)

        hk_hint = QLabel(
            "Sıkı doğrulama, sunucunun kimliğini kontrol ederek yanlış bir cihaza "
            "bağlanmayı önler ve genelde önerilir. Daha önce hiç bağlanılmamış bir "
            "sunucuda bu kontrol bağlantıyı engelleyebilir; böyle durumlarda ve "
            "güvendiğiniz bir ağdaysanız (doğrudan kablo, kendi kurduğunuz hotspot vb.) "
            "doğrulamayı atlayabilirsiniz. Tor (Acil Durum) modunda \"güvenilir ağ\" "
            "kavramı geçerli değildir -- oradaki asıl güvenlik operatör anahtarıdır "
            "(bkz. Bilgi Merkezi), bu yüzden Tor'da atlamayı sadece anahtarı doğru "
            "kişiden aldığınızdan eminseniz seçin."
        )
        hk_hint.setWordWrap(True)
        hk_hint.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        conn.body.addWidget(hk_hint)

        conn.body.addWidget(self._help_link("host_key_verification"))

        self.hk_warn = QLabel("Bu tercih delil zincirine ayrıca kaydedilir.")
        self.hk_warn.setWordWrap(True)
        self.hk_warn.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        self.hk_warn.setVisible(False)
        conn.body.addWidget(self.hk_warn)

        connect_row = QHBoxLayout()
        self.btn_connect = widgets.PrimaryButton("Bağlan ve Diskleri Listele")
        self.btn_connect.clicked.connect(self._connect)
        connect_row.addWidget(self.btn_connect)
        connect_row.addStretch()
        conn.body.addLayout(connect_row)
        body.addWidget(conn)

        # === Hedef Isletim Sistemi ===
        os_card = widgets.Card("Hedef İşletim Sistemi")
        os_row = QHBoxLayout()
        self.os_group = QButtonGroup(self)
        self.radio_os_linux = widgets.RadioButton("Linux (dd / bash)")
        self.radio_os_windows = widgets.RadioButton("Windows (PowerShell)")
        self.radio_os_linux.setChecked(True)
        for r in (self.radio_os_linux, self.radio_os_windows):
            self.os_group.addButton(r)
            os_row.addWidget(r)
            r.toggled.connect(self._on_target_os_change)
        os_row.addStretch()
        os_card.body.addLayout(os_row)
        body.addWidget(os_card)

        # === Ne Alinacak ===
        acq_card = widgets.Card("Ne Alınacak?")
        acq_row = QHBoxLayout()
        self.acq_group = QButtonGroup(self)
        self.radio_acq_disk = widgets.RadioButton("Tam Disk")
        self.radio_acq_file = widgets.RadioButton("Dosya ya da Klasör")
        self.radio_acq_disk.setChecked(True)
        for r in (self.radio_acq_disk, self.radio_acq_file):
            self.acq_group.addButton(r)
            acq_row.addWidget(r)
            r.toggled.connect(self._on_acq_type_change)
        acq_row.addStretch()
        acq_card.body.addLayout(acq_row)
        body.addWidget(acq_card)

        # === Hedef Disk ve Islem Modu ===
        self.disk_card = widgets.Card("Hedef Disk ve İşlem Modu")
        disk_row1 = QHBoxLayout()
        self.lbl_disk_path = QLabel("Disk (örn. /dev/sdb):")
        disk_row1.addWidget(self.lbl_disk_path)
        self.entry_disk = widgets.MonoInput()
        disk_row1.addWidget(self.entry_disk)
        self.mode_group = QButtonGroup(self)
        self.radio_live = widgets.RadioButton("Live Acquisition")
        self.radio_offline = widgets.RadioButton("Offline Acquisition")
        self.radio_live.setChecked(True)
        for r in (self.radio_live, self.radio_offline):
            self.mode_group.addButton(r)
            disk_row1.addWidget(r)
        self.disk_card.body.addLayout(disk_row1)
        self.disk_card.body.addWidget(self._help_link("live_vs_offline_acquisition"))

        disk_row2 = QHBoxLayout()
        disk_row2.addWidget(QLabel("İmaj Çıktı Yolu:"))
        self.entry_out = widgets.MonoInput()
        self.entry_out.setText(DEFAULT_IMAGE_PATH)
        disk_row2.addWidget(self.entry_out, stretch=1)
        browse_out_btn = widgets.SecondaryButton("Gözat")
        browse_out_btn.clicked.connect(self._browse_out)
        disk_row2.addWidget(browse_out_btn)
        self.disk_card.body.addLayout(disk_row2)

        disk_row3 = QHBoxLayout()
        disk_row3.addWidget(QLabel("Blok Boyutu:"))
        self.combo_block_size = QComboBox()
        self.combo_block_size.addItems(["4 MB", "16 MB", "32 MB", "64 MB"])
        self.combo_block_size.setStyleSheet(f"""
            QComboBox {{ background-color:{ui.BG_LAYER2}; color:{ui.TEXT_MAIN};
                border:1px solid {ui.BORDER}; border-radius:{ui.RADIUS}px; padding:4px 8px; }}
        """)
        disk_row3.addWidget(self.combo_block_size)
        disk_row3.addStretch()
        self.disk_card.body.addLayout(disk_row3)

        # Sadece Offline Acquisition icin anlamli -- Live modda parcalar
        # resume ihtimaline karsi zaten korunuyor (concatenate_blocks
        # cleanup=False), sikistirma o senaryoda ekstra bir adim/risk
        # olurdu. Mod degisince _on_mode_change ile devre disi/acik yapilir.
        self.check_compress = widgets.Checkbox("Sıkıştır (gzip) -- disk alanından tasarruf sağlar")
        self.check_compress.setEnabled(False)
        self.disk_card.body.addWidget(self.check_compress)

        for r in (self.radio_live, self.radio_offline):
            r.toggled.connect(self._on_mode_change)

        body.addWidget(self.disk_card)

        # === Hedef Dosya/Klasor ===
        self.file_card = widgets.Card("Hedef Dosya/Klasör")
        file_row1 = QHBoxLayout()
        self.lbl_remote_path = QLabel("Uzak Yol (örn. /home/user/belgeler):")
        file_row1.addWidget(self.lbl_remote_path)
        self.entry_remote_path = widgets.MonoInput()
        file_row1.addWidget(self.entry_remote_path, stretch=1)
        browse_remote_btn = widgets.SecondaryButton("Gözat")
        browse_remote_btn.clicked.connect(self._browse_remote_path)
        file_row1.addWidget(browse_remote_btn)
        self.file_card.body.addLayout(file_row1)

        file_row2 = QHBoxLayout()
        file_row2.addWidget(QLabel("Çıktı Klasörü:"))
        self.entry_file_out = widgets.MonoInput()
        self.entry_file_out.setText(os.path.join(_PERSISTENT_ROOT, "images", "dosyalar"))
        file_row2.addWidget(self.entry_file_out, stretch=1)
        browse_file_out_btn = widgets.SecondaryButton("Gözat")
        browse_file_out_btn.clicked.connect(self._browse_file_out)
        file_row2.addWidget(browse_file_out_btn)
        self.file_card.body.addLayout(file_row2)

        file_warn = QLabel(
            "Bu modda write-blocker uygulanmaz (dosya/klasör seviyesinde anlamlı değil) -- "
            "disk her zaman olduğu gibi, kilitlenmeden okunur."
        )
        file_warn.setWordWrap(True)
        file_warn.setStyleSheet(f"color:{ui.WARNING}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        self.file_card.body.addWidget(file_warn)
        body.addWidget(self.file_card)
        self.file_card.hide()

        # === Butonlar ===
        btn_row = QHBoxLayout()
        self.btn_acquire = widgets.PrimaryButton("İmaj Almayı Başlat")
        self.btn_acquire.clicked.connect(self._start_acquisition)
        btn_row.addWidget(self.btn_acquire)
        verify_btn = widgets.SecondaryButton("İmaj Doğrula")
        verify_btn.clicked.connect(self._verify_image)
        btn_row.addWidget(verify_btn)
        btn_row.addStretch()
        clear_btn = widgets.SecondaryButton("Log Temizle")
        clear_btn.clicked.connect(self._clear_log)
        btn_row.addWidget(clear_btn)
        body.addLayout(btn_row)

        # === Ilerleme ===
        self.progress = widgets.ProgressBar()
        body.addWidget(self.progress)
        self.status_label = QLabel("Bekleniyor...")
        self.status_label.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px; font-style:italic;")
        body.addWidget(self.status_label)

        # === Log ===
        log_card = widgets.Card("İşlem Logu")
        help_links_row = QHBoxLayout()
        help_links_row.addWidget(self._help_link("chain_of_custody", "Delil zinciri nedir?"))
        help_links_row.addWidget(self._help_link("hash_verification", "Hash doğrulaması nedir?"))
        help_links_row.addStretch()
        log_card.body.addLayout(help_links_row)
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMinimumHeight(220)
        self.txt_log.setStyleSheet(f"""
            QTextEdit {{ background-color:#0A0E14; color:{ui.TEXT_MAIN}; font-family:"{ui.FONT_MONO}";
                font-size:11px; border:1px solid {ui.BORDER}; border-radius:{ui.RADIUS}px; }}
        """)
        log_card.body.addWidget(self.txt_log)
        body.addWidget(log_card, stretch=1)

        self._on_target_os_change()
        self._on_acq_type_change()
        self._on_conn_method_change()

    def _labeled_row(self, body_layout, label_text, initial_value):
        row = QHBoxLayout()
        lbl = QLabel(f"{label_text}:")
        lbl.setFixedWidth(190)
        row.addWidget(lbl)
        entry = widgets.Input()
        entry.setText(initial_value)
        row.addWidget(entry)
        row.addStretch()
        body_layout.addLayout(row)
        return entry

    def _build_vpn_info_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 6, 0, 0)
        note = QLabel(
            "Bilgisayarınız zaten hedef ağa VPN ile bağlıysa bu modu kullanın. Host alanına "
            "hedefin VPN üzerinden erişilebilir IP'sini yazın -- bağlantı doğrudan SSH ile "
            "kurulur (Tor gibi ekstra bir katman yok), sadece delil zincirinde VPN kullanıldığı "
            "ayrıca kayıt altına alınır."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        layout.addWidget(note)
        return panel

    def _build_tor_info_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(6)

        heading = QLabel("Tor (Acil Durum) nedir?")
        heading.setStyleSheet(f"color:{ui.ACCENT_TEXT}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px; font-weight:600;")
        layout.addWidget(heading)

        what = QLabel(
            "Hedef ağa hiçbir erişiminiz/yetkiniz olmadığında (örn. şirket SSH'ı tamamen "
            "engellemiş, router'a erişiminiz yok) kullanılan son çare yöntemdir. Taşınabilir "
            "bir USB kit hedef cihazda çalıştırılır; kit kendiliğinden bir '.onion' adresi "
            "üretir ve SADECE sizin anahtarınıza sahip bağlantıları kabul eder -- adresi "
            "başka biri bilse bile bağlanamaz."
        )
        what.setWordWrap(True)
        what.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        layout.addWidget(what)

        steps_heading = QLabel("Kullanım adımları:")
        steps_heading.setStyleSheet(f"color:{ui.ACCENT_TEXT}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px; font-weight:600;")
        layout.addWidget(steps_heading)

        steps = QLabel(
            "1. Aşağıdaki kutudaki açık anahtarınızı \"Kopyala\" ile alın.\n"
            "2. Bu anahtarı, taşınabilir kiti hedef cihaza götürecek kişiye ÖNCEDEN verin (kit "
            "bu anahtarla hazırlanmış olmalı).\n"
            "3. Kit hedef cihazda çalıştırılınca bir '.onion' adresi üretir; sahadaki kişi bunu "
            "size KENDİ telefonuyla iletir (delil cihazının ağı/uygulamaları hiç kullanılmaz).\n"
            "4. Aldığınız '.onion' adresini yukarıdaki Host alanına yazın (örn. abcxyz....onion).\n"
            "5. Bu mod seçiliyken normal şekilde \"Bağlan ve Diskleri Listele\"ye basın -- "
            "bağlantı Tor ağı üzerinden, anahtarınızla doğrulanarak kurulur."
        )
        steps.setWordWrap(True)
        steps.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        layout.addWidget(steps)

        warn = QLabel(
            "⚠ YAVAŞTIR: veri Tor ağındaki birden fazla farklı sunucu üzerinden dolaşarak gider "
            "-- büyük bir disk imajı saatlerce sürebilir. Mümkünse önce Doğrudan/VPN'i deneyin, "
            "bunu gerçekten son çare olarak kullanın."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet(f"color:{ui.WARNING}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px; font-weight:600;")
        layout.addWidget(warn)

        key_heading = QLabel("Operatör Açık Anahtarınız:")
        key_heading.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px; font-weight:600;")
        layout.addWidget(key_heading)

        key_row = QHBoxLayout()
        self.entry_operator_pubkey = widgets.MonoInput()
        self.entry_operator_pubkey.setReadOnly(True)
        key_row.addWidget(self.entry_operator_pubkey)
        copy_btn = widgets.SecondaryButton("Kopyala")
        copy_btn.clicked.connect(self._copy_operator_pubkey)
        key_row.addWidget(copy_btn)
        layout.addLayout(key_row)

        # Sahadaki kisinin hedef taraf sihirbazina yapistirdigi anahtarin
        # DOGRU oldugunu telefonla teyit edebilmesi icin -- aynı kod, aynı
        # hesaplamayla (onion_auth.key_fingerprint) orada da gosteriliyor.
        self.lbl_operator_key_fingerprint = QLabel("")
        self.lbl_operator_key_fingerprint.setStyleSheet(
            f"color:{ui.ACCENT_TEXT}; font-family:'{ui.FONT_MONO}'; font-size:{ui.SIZE_HELPER}px; font-weight:600;"
        )
        layout.addWidget(self.lbl_operator_key_fingerprint)
        hint = QLabel(
            "Sahadaki kişi anahtarı yapıştırdıktan sonra kendi ekranında da bu kod "
            "belirir -- başlatmadan önce telefonla karşılaştırın."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        layout.addWidget(hint)

        return panel

    # -- Baglanti yontemi degisimi ------------------------------------------
    def _on_conn_method_change(self, *_args):
        if not self._method_locked:
            if self.radio_vpn.isChecked():
                self.conn_method_value = "vpn"
            elif self.radio_tor.isChecked():
                self.conn_method_value = "tor"
            else:
                self.conn_method_value = "direct"

        self.vpn_info.setVisible(self.conn_method_value == "vpn")
        self.tor_info.setVisible(self.conn_method_value == "tor")

        if self.conn_method_value == "tor":
            if generate_keypair is None:
                self._log("[HATA] onion_auth.py bulunamadi (shared/ eksik olabilir).", "err")
                return
            if self._operator_private_key is None:
                self._operator_private_key, self._operator_public_key = self._load_or_create_operator_key()
            self.entry_operator_pubkey.setText(self._operator_public_key or "")
            if key_fingerprint is not None and self._operator_public_key:
                self.lbl_operator_key_fingerprint.setText(f"Kod: {key_fingerprint(self._operator_public_key)}")

    def _load_or_create_operator_key(self):
        """AYNEN tasindi (gui_v2.py) -- keys/operator_tor_key.json'dan yukler/uretir."""
        import json
        key_path = os.path.join(_PERSISTENT_ROOT, "keys", "operator_tor_key.json")
        if os.path.exists(key_path):
            try:
                with open(key_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data["private"], data["public"]
            except (OSError, json.JSONDecodeError, KeyError) as e:
                self._log(f"[UYARI] Operator anahtari okunamadi, yenisi üretiliyor: {e}", "warn")

        private_b32, public_b32 = generate_keypair()
        os.makedirs(os.path.dirname(key_path), exist_ok=True)
        with open(key_path, "w", encoding="utf-8") as f:
            json.dump({"private": private_b32, "public": public_b32}, f, indent=2)
        _restrict_key_file_permissions(key_path)
        self._log(f"[+] Yeni operator anahtarı üretildi ve kaydedildi: {key_path}", "info")
        return private_b32, public_b32

    def _copy_operator_pubkey(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.entry_operator_pubkey.text())
        self._log("[+] Operatör açık anahtarı panoya kopyalandı.", "info")

    def _on_hostkey_mode_change(self, *_args):
        self.strict_host_key_value = not self.radio_hostkey_skip.isChecked()
        self.hk_warn.setVisible(not self.strict_host_key_value)

    def _help_link(self, topic_key, label="Bu ne demek? (Bilgi Merkezi'nde oku)"):
        """Bilgi Merkezi'ndeki bir konuya goturen, mavi metin gorunumlu
        kucuk bir buton."""
        btn = QPushButton(label)
        btn.setFlat(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ color:{ui.ACCENT_TEXT}; background:transparent; border:none; "
            f"text-align:left; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px; "
            f"padding:2px 0; }} QPushButton:hover {{ color:{ui.ACCENT_HOVER}; }}"
        )
        btn.clicked.connect(lambda: self._show_help_topic(topic_key))
        return btn

    def _show_help_topic(self, topic_key):
        """Bilgi Merkezi'ndeki ilgili konuya goturur. Launcher icinden
        aciliyorsa (normal kullanim) on_show_help callback'i ile SIDEBAR
        SAYFASINA dogrudan gecilir. Standalone `python gui_v2.py`
        calistirmasinda (Bilgi Merkezi sayfasi yok) ayni icerik kucuk bir
        dialogda gosterilir -- CLAUDE.md'nin 'her modul tek basina
        calisabilmeli' kurali icin."""
        if self.on_show_help is not None:
            self.on_show_help(topic_key)
            return

        from PySide6.QtWidgets import QScrollArea

        topic = get_topic(topic_key)
        if topic is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(topic["title"])
        dialog.resize(480, 420)
        layout = QVBoxLayout(dialog)

        text = QLabel(topic["body"])
        text.setWordWrap(True)
        text.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_BODY}px;")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(text)
        layout.addWidget(scroll)

        close_btn = widgets.SecondaryButton("Kapat")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        dialog.exec()

    # -- Kucuk UI durum degisimleri ------------------------------------------
    def _on_target_os_change(self, *_args):
        if self.radio_os_windows.isChecked():
            self.lbl_disk_path.setText("Disk Numarası (örn. 0):")
            self.lbl_remote_path.setText("Uzak Yol (örn. C:\\Users\\kullanici\\Belgeler):")
        else:
            self.lbl_disk_path.setText("Disk (örn. /dev/sdb):")
            self.lbl_remote_path.setText("Uzak Yol (örn. /home/user/belgeler):")

    def _on_mode_change(self, *_args):
        offline = self.radio_offline.isChecked()
        self.check_compress.setEnabled(offline)
        if not offline:
            self.check_compress.setChecked(False)

    def _on_acq_type_change(self, *_args):
        if self.radio_acq_disk.isChecked():
            self.disk_card.show()
            self.file_card.hide()
        else:
            self.file_card.show()
            self.disk_card.hide()

    def _get_block_size_mb(self):
        return int(self.combo_block_size.currentText().split()[0])

    # -- Log / durum ----------------------------------------------------
    def _log(self, msg, tag=None):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        color = LOG_COLORS.get(tag or self._detect_tag(msg), ui.TEXT_MAIN)
        self.txt_log.append(f'<span style="color:{ui.TEXT_SECONDARY}">[{timestamp}]</span> '
                             f'<span style="color:{color}">{_html_escape(msg)}</span>')

    def _detect_tag(self, msg):
        if "[BAŞARILI]" in msg or "BAŞARILI" in msg:
            return "ok"
        if "[HATA]" in msg or "HATA" in msg:
            return "err"
        if "[UYARI]" in msg or "[BİLGİ]" in msg:
            return "warn"
        if msg.startswith("---") or msg.startswith("==="):
            return "info"
        return "plain"

    def _clear_log(self):
        self.txt_log.clear()
        self.progress.set_determinate(0)
        self.status_label.setText("Bekleniyor...")

    def _set_status(self, text):
        self.status_label.setText(text)

    def _set_progress(self, value):
        self.progress.set_determinate(value)

    def _set_conn_indicator(self, connected):
        if connected:
            self.conn_badge.set_status(*widgets.StatusBadge.PRESET_CONNECTED)
        else:
            self.conn_badge.set_status(*widgets.StatusBadge.PRESET_DISCONNECTED)

    # -- Dosya sec dialoglari ------------------------------------------------
    def _browse_key(self):
        path, _ = QFileDialog.getOpenFileName(self, "SSH Anahtarı Seç", "", "PEM (*.pem);;Tüm Dosyalar (*.*)")
        if path:
            self.entry_key.setText(path)

    def _browse_out(self):
        path, _ = QFileDialog.getSaveFileName(self, "İmaj Dosyası Kaydet", self.entry_out.text(), "Raw Image (*.raw);;Tüm Dosyalar (*.*)")
        if path:
            self.entry_out.setText(path)

    def _browse_file_out(self):
        path = QFileDialog.getExistingDirectory(self, "Çıktı Klasörü Seç")
        if path:
            self.entry_file_out.setText(path)

    def _browse_remote_path(self):
        """
        'Uzak Yol' icin native QFileDialog KULLANILAMAZ -- o hep BU
        bilgisayarin diskini gosterir, SSH ile baglanilan uzak hedefin
        dosya sistemini goremez. Bunun yerine RemoteBrowseDialog, mevcut
        SSH baglantisi (self.ssh) uzerinden salt-okunur find/Get-ChildItem
        ile gezinmeyi saglar.
        """
        if self.ssh is None:
            self._show_error("Önce bağlanın (\"Bağlan ve Diskleri Listele\").")
            return
        target_os = "windows" if self.radio_os_windows.isChecked() else "linux"
        start_path = self.entry_remote_path.text().strip() or ("C:\\" if target_os == "windows" else "/")
        dialog = RemoteBrowseDialog(self.ssh, target_os, start_path, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_path:
            self.entry_remote_path.setText(dialog.selected_path)

    # -- Diyaloglar (Tk _modal'in Qt karsiligi) ------------------------------
    def _show_yesno_dialog(self, title, msg):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setStyleSheet(f"background-color:{ui.BG_SURFACE};")
        layout = QVBoxLayout(dialog)
        lbl = QLabel(msg)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; padding: 8px;")
        layout.addWidget(lbl)
        btn_row = QHBoxLayout()
        result = {"value": False}

        def _yes():
            result["value"] = True
            dialog.accept()

        yes_btn = widgets.PrimaryButton("Evet")
        yes_btn.clicked.connect(_yes)
        no_btn = widgets.SecondaryButton("Hayır")
        no_btn.clicked.connect(dialog.reject)
        btn_row.addWidget(yes_btn)
        btn_row.addWidget(no_btn)
        layout.addLayout(btn_row)
        dialog.exec()
        return result["value"]

    def _show_error(self, msg):
        dialog = QDialog(self)
        dialog.setWindowTitle("Hata")
        dialog.setStyleSheet(f"background-color:{ui.BG_SURFACE};")
        layout = QVBoxLayout(dialog)
        lbl = QLabel(msg)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{ui.ERROR}; font-family:'{ui.FONT_UI}'; padding: 8px;")
        layout.addWidget(lbl)
        ok_btn = widgets.PrimaryButton("Tamam")
        ok_btn.clicked.connect(dialog.accept)
        layout.addWidget(ok_btn)
        dialog.exec()

    def _show_info(self, msg):
        dialog = QDialog(self)
        dialog.setWindowTitle("Bilgi")
        dialog.setStyleSheet(f"background-color:{ui.BG_SURFACE};")
        layout = QVBoxLayout(dialog)
        lbl = QLabel(msg)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; padding: 8px;")
        layout.addWidget(lbl)
        ok_btn = widgets.PrimaryButton("Tamam")
        ok_btn.clicked.connect(dialog.accept)
        layout.addWidget(ok_btn)
        dialog.exec()

    # -- SSH Baglanti --------------------------------------------------------
    def _connect(self):
        host = self.entry_host.text().strip()
        port_str = self.entry_port.text().strip()
        port = int(port_str) if port_str else 22
        user = self.entry_user.text().strip()
        password = self.entry_pass.text().strip() or None
        key_path = self.entry_key.text().strip() or None

        if not host or not user:
            self._show_error("Host ve kullanıcı adı zorunlu.")
            return

        self.btn_connect.setEnabled(False)
        self.btn_connect.setText("Bağlanıyor...")
        self.conn_badge.set_status(*widgets.StatusBadge.PRESET_CONNECTING)
        self.connect_worker = ConnectWorker(
            host, port, user, password, key_path, self.conn_method_value,
            self._operator_private_key, self.tor_client_handle,
            strict_host_key=self.strict_host_key_value,
        )
        self.connect_worker.log.connect(self._log)
        self.connect_worker.error.connect(self._on_connect_error)
        self.connect_worker.connected.connect(self._on_connected)
        self.connect_worker.finished.connect(self._on_connect_finished)
        self.connect_worker.start()

    def _on_recent_host_picked(self, host):
        """Host alaninda tamamlanan onerilerden biri secilince, o hostla
        birlikte kaydedilmis port/kullanici adini da otomatik doldurur --
        boylece sadece host degil, tum baglanti bilgisi tek tikla geri gelir."""
        for entry in self._recent_hosts:
            if entry.get("host") == host:
                if entry.get("port"):
                    self.entry_port.setText(entry["port"])
                if entry.get("username"):
                    self.entry_user.setText(entry["username"])
                break

    def _on_connect_finished(self):
        self.btn_connect.setEnabled(True)
        self.btn_connect.setText("Bağlan ve Diskleri Listele")

    def _on_connect_error(self, msg):
        self._show_error(msg)
        self.conn_badge.set_status(*widgets.StatusBadge.PRESET_ERROR)
        self.ssh = None

    def _on_connected(self, ssh, via_tor):
        self.ssh = ssh
        if self.connect_worker.tor_client_handle is not None:
            self.tor_client_handle = self.connect_worker.tor_client_handle
        host = self.entry_host.text().strip()
        port = self.entry_port.text().strip()
        self._log(f"[BAŞARILI] Bağlantı kuruldu: {host}:{port}", "ok")
        # Sadece host/port/kullanici adi -- sifre asla saklanmaz.
        _save_recent_host(host, port, self.entry_user.text().strip())
        if via_tor:
            coc.log_event(coc.EVENT_TOR_CONNECTION_ESTABLISHED, f"Bağlantı Tor Hidden Service üzerinden kuruldu: {host}")
            self._log("[i] Bağlantı Tor üzerinden kuruldu (delil zinciri logunda işaretlendi).", "info")
        elif self.conn_method_value == "vpn":
            coc.log_event(coc.EVENT_VPN_CONNECTION_USED, f"Bağlantı operatörün VPN tüneli üzerinden kuruldu: {host}")
            self._log("[i] Bağlantı VPN üzerinden kuruldu (delil zinciri logunda işaretlendi).", "info")
        self._set_conn_indicator(True)
        disks_raw = ssh.list_disks() or ""
        self.disks_raw = disks_raw
        self._log("--- Mevcut Diskler ---", "info")
        self._log(disks_raw, "plain")
        self._set_status("Bağlantı kuruldu, diskler listelendi.")

    def _new_report_ctx(self):
        return {
            "case_id": self.entry_case_id.text().strip(),
            "examiner": self.entry_examiner.text().strip(),
            "custodian": self.entry_custodian.text().strip(),
            "organization": self.entry_organization.text().strip(),
            "conn_method": self.conn_method_value,
            "host": self.entry_host.text().strip(),
        }

    # -- Imaj Alma ------------------------------------------------------
    def _start_acquisition(self):
        if self.ssh is None or not self.ssh.is_active():
            self._show_error("Önce SSH bağlantısı kurun (Bağlan ve Diskleri Listele).")
            return
        if self.radio_acq_disk.isChecked():
            if self.radio_os_windows.isChecked():
                self._start_disk_windows()
            else:
                self._start_disk_linux()
        else:
            self._start_file()

    def _start_disk_windows(self):
        disk_str = self.entry_disk.text().strip()
        out_path = self.entry_out.text().strip()
        mode = "offline" if self.radio_offline.isChecked() else "live"
        if not disk_str:
            self._show_error("Hedef disk numarasını girin (örn. 0).")
            return
        try:
            disk_number = int(disk_str)
        except ValueError:
            self._show_error("Disk numarası tam sayı olmalı (örn. 0, 1) -- \\\\.\\PhysicalDriveN'deki N.")
            return
        if not out_path:
            self._show_error("İmaj çıktı yolu seçin.")
            return

        compress = mode == "offline" and self.check_compress.isChecked()
        ctx = self._new_report_ctx()
        ctx.update(disk_number=disk_number, out_path=out_path, mode=mode, block_size_mb=self._get_block_size_mb(), compress=compress)
        self._begin_acquisition("windows_disk", ctx, f"MOD: {mode.upper()} | DISK: PhysicalDrive{disk_number} | ÇIKTI: {out_path}")

    def _start_disk_linux(self):
        disk = self.entry_disk.text().strip()
        out_path = self.entry_out.text().strip()
        mode = "offline" if self.radio_offline.isChecked() else "live"
        password = self.entry_pass.text().strip() or None
        if not disk:
            self._show_error("Hedef disk yolu girin (örn. /dev/sdb).")
            return
        if not disk.startswith("/dev/"):
            disk = f"/dev/{disk}"
        if not out_path:
            self._show_error("İmaj çıktı yolu seçin.")
            return

        disk_name = disk.replace("/dev/", "")
        if getattr(self, "disks_raw", "") and disk_name not in self.disks_raw:
            if not self._show_yesno_dialog("Disk listede yok", f"'{disk_name}' listelenen disklerde görünmüyor.\nYine de devam edilsin mi?"):
                return

        compress = mode == "offline" and self.check_compress.isChecked()
        ctx = self._new_report_ctx()
        ctx.update(disk=disk, out_path=out_path, mode=mode, password=password, block_size_mb=self._get_block_size_mb(), compress=compress)
        self._begin_acquisition("linux_disk", ctx, f"MOD: {mode.upper()} | DISK: {disk} | ÇIKTI: {out_path}")

    def _start_file(self):
        remote_path = self.entry_remote_path.text().strip()
        out_dir = self.entry_file_out.text().strip()
        password = self.entry_pass.text().strip() or None
        if not remote_path:
            self._show_error("Uzak dosya/klasör yolu girin (örn. /home/user/belgeler).")
            return
        if not out_dir:
            self._show_error("Çıktı klasörü seçin.")
            return

        ctx = self._new_report_ctx()
        ctx.update(
            remote_path=remote_path, out_dir=out_dir, password=password,
            target_os="windows" if self.radio_os_windows.isChecked() else "linux",
        )
        self._begin_acquisition("file", ctx, f"UZAK YOL: {remote_path} | ÇIKTI: {out_dir}")

    def _begin_acquisition(self, kind, ctx, header_line):
        self.btn_acquire.setEnabled(False)
        self._set_progress(0)
        self._set_status("İmaj alma başlıyor...")
        self._log(f"\n{'=' * 50}", "info")
        self._log(header_line, "info")
        self._log("=" * 50, "info")

        self.acq_worker = AcquisitionWorker(kind, self.ssh, ctx)
        self.acq_worker.log.connect(self._log)
        self.acq_worker.status.connect(self._set_status)
        self.acq_worker.progress.connect(self._set_progress)
        self.acq_worker.report_ready.connect(self._show_report_summary)
        self.acq_worker.ask_verify.connect(self._on_ask_verify)
        self.acq_worker.ask_yesno.connect(self._on_worker_ask_yesno)
        self.acq_worker.finished.connect(lambda: self.btn_acquire.setEnabled(True))
        self.acq_worker.start()

    def _on_worker_ask_yesno(self, title, msg):
        """
        Ana thread'de calisir (Qt sinyal kuyruklamasi sayesinde). Cevabi
        worker'in KENDI _yesno_result/_yesno_event niteliklerine yazip
        event'i set ediyor -- worker thread _ask_yesno_blocking icinde
        event.wait() ile bekliyordu, bu satirla uyaniyor.

        self.sender() DEGIL self.acq_worker kullaniliyor: ilk denemede
        sender() kullanildi ama bir mock testte worker sonsuza kadar
        event.wait()'te tikanip kaldi -- sender()'in bu senaryoda (ozel
        QThread alt sinifindan, cross-thread queued baglanti) guvenilir
        sekilde dogru nesneyi dondurmedigi/None donduGu ve icerideki
        AttributeError'in sessizce yutulup event.set()'in HIC
        cagrilmadigi anlasildi. self.acq_worker dogrudan ve kesin.
        """
        self.acq_worker._yesno_result = self._show_yesno_dialog(title, msg)
        self.acq_worker._yesno_event.set()

    def _on_ask_verify(self, image_path):
        ans = self._show_yesno_dialog(
            "Doğrulama",
            "İmaj alma tamamlandı.\nUzak diskin SHA-256 hash'ini biliyor musunuz?\n(Biliyorsanız doğrulama yapılacak)",
        )
        if ans:
            # Bu, az once tamamlanan alma islemine ait dogrulama -- sonucu
            # (basarili/basarisiz) _last_report'a islemek icin rapor
            # nesnesini de birlikte gonderiyoruz (bkz. VerifyWorker).
            self._verify_image_with_path(image_path, report=self._last_report, report_path=self._last_report_path)

    # -- Imaj Dogrulama -----------------------------------------------------
    def _verify_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "İmaj Dosyası Seç", "", "Raw Image (*.raw);;Tüm Dosyalar (*.*)")
        if not path:
            return
        # Elle secilen keyfi bir dosya -- az onceki alma islemine ait
        # raporla ILISKILENDIRILMIYOR (yanlis rapora "dogrulandi" yazmamak
        # icin; sadece _on_ask_verify'daki otomatik akis rapor gunceller).
        self._verify_image_with_path(path)

    def _verify_image_with_path(self, path, report=None, report_path=None):
        dialog = QDialog(self)
        dialog.setWindowTitle("Hash Doğrulama")
        dialog.setStyleSheet(f"background-color:{ui.BG_SURFACE};")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Beklenen SHA-256 (uzak diskin hash'i):"))
        entry_hash = widgets.MonoInput()
        entry_hash.setFixedWidth(420)
        layout.addWidget(entry_hash)
        entry_hash.setFocus()

        result = {"hash": None}

        def on_ok():
            result["hash"] = entry_hash.text().strip()
            dialog.accept()

        btn_row = QHBoxLayout()
        ok_btn = widgets.PrimaryButton("Doğrula")
        ok_btn.clicked.connect(on_ok)
        cancel_btn = widgets.SecondaryButton("İptal")
        cancel_btn.clicked.connect(dialog.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)
        entry_hash.returnPressed.connect(on_ok)

        dialog.exec()
        expected = result["hash"]
        if not expected:
            return

        self._log(f"\n--- İmaj Doğrulama: {path} ---", "info")
        self.verify_worker = VerifyWorker(path, expected, report=report, report_path=report_path)
        self.verify_worker.result_ok.connect(self._on_verify_ok)
        self.verify_worker.result_mismatch.connect(self._on_verify_mismatch)
        self.verify_worker.result_error.connect(self._on_verify_error)
        self.verify_worker.start()

    def _on_verify_ok(self, digest, byte_count):
        self._log("[BAŞARILI] Doğrulama OK!")
        self._log(f"  SHA-256 : {digest}", "plain")
        self._log(f"  Boyut   : {byte_count} bayt", "plain")
        self._show_info("İmaj doğrulandı — kaynakla birebir aynı.")

    def _on_verify_mismatch(self, expected, actual):
        self._log("[HATA] Hash uyuşmazlığı!")
        self._log(f"  Beklenen: {expected}", "plain")
        self._log(f"  Gerçek  : {actual}", "plain")
        self._show_error("Hash uyuşmazlığı — imaj bozulmuş olabilir.")

    def _on_verify_error(self, msg):
        self._log(f"[HATA] Doğrulama hatası: {msg}")
        self._show_error(f"Doğrulama hatası: {msg}")

    # -- Rapor ozeti (ram_gui.py ile ayni desen) --------------------------
    def _show_report_summary(self, report, report_path):
        if report is None or report_path is None:
            return
        # "Imaj Dogrula" sorusu bu ozet penceresinden SONRA soruluyor
        # (bkz. _on_ask_verify) -- dogrulama sonucunun rapora islenebilmesi
        # icin (bkz. VerifyWorker) az once kaydedilen BU rapor nesnesi ve
        # yolu burada saklanmali.
        self._last_report = report
        self._last_report_path = report_path
        html_path = os.path.splitext(report_path)[0] + ".html"

        dialog = QDialog(self)
        dialog.setWindowTitle("İşlem Raporu")
        dialog.resize(480, 380)
        dialog.setStyleSheet(f"background-color:{ui.BG_DARKEST};")
        layout = QVBoxLayout(dialog)

        d = report.to_dict()
        basarili = d["result"]["status"] == "success"
        head = QLabel("✔ İşlem Tamamlandı" if basarili else f"İşlem Durumu: {d['result']['status']}")
        head.setStyleSheet(f"color:{ui.SUCCESS if basarili else ui.WARNING}; font-family:'{ui.FONT_UI}'; font-size:15px; font-weight:600;")
        layout.addWidget(head)

        image_hash = d["integrity"]["image_hash"] or ""
        satirlar = [
            ("Vaka No", d["case"]["case_id"] or "—"),
            ("İnceleyen", d["case"]["examiner"] or "—"),
            ("Cihaz Sahibi / Yetkili Kişi", d["case"]["custodian"] or "—"),
            ("Organizasyon", d["case"]["organization"] or "—"),
            ("Hedef", d["acquisition"]["target_host"] or d["acquisition"]["source_identifier"] or "—"),
            ("Bağlantı Yöntemi", d["acquisition"]["connection_method"] or "—"),
            ("SHA-256", (image_hash[:24] + "…") if image_hash else "—"),
            ("Sonuç", d["result"]["status"]),
        ]
        for etiket, deger in satirlar:
            row = QHBoxLayout()
            lbl = QLabel(f"{etiket}:")
            lbl.setFixedWidth(170)
            lbl.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
            row.addWidget(lbl)
            val = QLabel(str(deger))
            val.setWordWrap(True)
            val.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_MONO}'; font-size:{ui.SIZE_HELPER}px;")
            row.addWidget(val, stretch=1)
            layout.addLayout(row)

        layout.addStretch()
        btns = QHBoxLayout()

        def _open_html():
            try:
                os.startfile(html_path)
            except Exception as e:
                self._log(f"[UYARI] Rapor açılamadı: {e}", "warn")

        open_btn = widgets.PrimaryButton("Raporu Aç (HTML)")
        open_btn.clicked.connect(_open_html)
        btns.addWidget(open_btn)
        btns.addStretch()
        close_btn = widgets.SecondaryButton("Kapat")
        close_btn.clicked.connect(dialog.close)
        btns.addWidget(close_btn)
        layout.addLayout(btns)
        dialog.exec()


def _html_escape(text):
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
    )


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    fonts.register_fonts()
    app.setStyleSheet(ui.base_stylesheet())

    win = QMainWindow()
    win.setWindowTitle("SSH ile Uzak İmaj Al")
    win.resize(1000, 820)
    win.setCentralWidget(ForensicWidget())
    win.show()
    sys.exit(app.exec())
