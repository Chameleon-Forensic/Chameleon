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
import platform
import re
import subprocess
import sys
import tempfile
import threading
import time

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QCompleter, QDialog, QFileDialog, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QPushButton, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
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
_I18N_DIR = os.path.join(_SHARED_DIR, "i18n")
if os.path.isdir(_I18N_DIR):
    sys.path.insert(0, _I18N_DIR)

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
    # Atomik yazma (gecici dosya + os.replace) -- dogrudan hedef dosyaya
    # 'w' ile yazim, cokme/kesinti aninda yarim JSON birakip TUM gecmis
    # kaybettirirdi (incomplete_ops.py'de duzeltilen AYNI desen).
    try:
        os.makedirs(os.path.dirname(_RECENT_HOSTS_FILE), exist_ok=True)
        tmp_yol = _RECENT_HOSTS_FILE + ".tmp"
        with open(tmp_yol, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
        os.replace(tmp_yol, _RECENT_HOSTS_FILE)
    except OSError:
        try:
            os.remove(_RECENT_HOSTS_FILE + ".tmp")
        except OSError:
            pass


def format_duration_tr(seconds):
    """Saniyeyi kisa bir TR sure metnine cevirir (45 sn / 2 dk 10 sn / 1 sa 5 dk)
    -- ram_gui.py'deki AYNI adli yardimci, iki dosya birbirinden bagimsiz
    calisabildigi icin kod tekrarlanir (bkz. CONTRIBUTING.md)."""
    saniye = max(0, int(seconds))
    if saniye < 60:
        return f"{saniye} sn"
    dakika, saniye = divmod(saniye, 60)
    if dakika < 60:
        return f"{dakika} dk {saniye} sn" if saniye else f"{dakika} dk"
    saat, dakika = divmod(dakika, 60)
    return f"{saat} sa {dakika} dk"


def build_path_tree(paths):
    """Yol listesinden ('/' ve '\\' karisik olabilir -- hedef Linux ya da
    Windows olabilir) ic ice bir sozluk agaci kurar. Klasor dugumleri kendi
    altindaki ogelerin sozlugu (dict), dosya (yaprak) dugumleri ise KENDI
    ORIJINAL TAM YOL STRING'INI deger olarak tasir -- boylece bir yaprak,
    ayirici normalize edip yeniden birlestirmeye gerek kalmadan dogrudan
    manifest'teki ilgili kayda (ör. local_path) eslenebilir (bkz.
    _show_tree_dialog). Sadece GORUNTULEME icin, alma mantigina dokunmuyor."""
    kok = {}
    for yol in paths:
        parcalar = [p for p in re.split(r"[\\/]+", yol) if p]
        if not parcalar:
            continue
        dugum = kok
        for parca in parcalar[:-1]:
            dugum = dugum.setdefault(parca, {})
        dugum[parcalar[-1]] = yol
    return kok


def _guvenli_onizleme_dosya_adi(inode, isim):
    """Tam Disk agacindaki (disk_tree.py) bir dosyanin `isim`'ini, ONIZLEME
    icin GECICI diskteki dosya adina donusturmeden once sanitize eder.

    ONEMLI: `isim` pytsk3/Sleuthkit tarafindan dizin girdisinden HAM BAYT
    olarak okunuyor -- disk_tree.py bunu hicbir OS dosya adi dogrulamasindan
    GECIRMIYOR. Kotu amacli/bozuk bir imaj, adinda '/' veya '\\' ya da '..'
    iceren bir girdi barindirabilir (path traversal, CWE-22); os.path.join
    ile dogrudan birlestirilirse bu, GECICI KLASORUN DISINA yazmaya yol
    acabilir. Bu yuzden `isim` gercek dosya adi olarak hic KULLANILMIYOR --
    sadece gorunen/orijinal ismin uzantisi (varsa, salt gosterim/raporlama
    amacli) korunuyor, dosyanin kendisi TSK'nin kendi urettigi inode
    numarasina dayanan sabit bir adla yaziliyor."""
    # Windows'ta hem '/' hem '\\' ayrac olabilir -- os.path.basename TEK
    # basina YETMEZ (ör. Linux'ta calisirken '\\' ayrac sayilmaz), bu yuzden
    # ikisini de elle temizliyoruz.
    taban_isim = isim.replace("\\", "/").rsplit("/", 1)[-1]
    _, nokta_var_mi, uzanti_ham = taban_isim.rpartition(".")
    uzanti = "".join(ch for ch in uzanti_ham if ch.isalnum())[:16] if nokta_var_mi else ""
    return f"inode{int(inode)}" + (f".{uzanti}" if uzanti else "")


from ui_kit import theme_qt as ui, fonts, icons, widgets  # noqa: E402
from help_content import get_topic  # noqa: E402
from strings import t  # noqa: E402

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
        write_segments,
        find_incomplete_manifest,
        find_incomplete_tree_manifest,
        delete_manifest,
        get_disk_description,
    )
    from file_acquirer import acquire_remote_tree, acquire_logical_image, list_remote_directory
    from windows_acquirer import (
        acquire_disk_image_windows,
        acquire_remote_tree_windows,
        acquire_logical_image_windows,
        list_remote_directory_windows,
        get_disk_description_windows,
    )
    from hash_verifier import verify_file, HashMismatchError, HashError, hash_file_multi, hash_files_multi
    from local_connector import (
        LocalConnector, is_admin, system_disk_number,
        check_output_not_on_source, check_root_output_separate,
    )
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

try:
    import disk_tree
except ImportError:
    disk_tree = None


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

    Guvenlik duzeltmesi: Windows'ta icacls'a grant edilen hesap
    DOMAIN\\kullanici biciminde OLMALI -- sade "kullanici", bilgisayar adi
    ile kullanici adi ayni/a benzer oldugunda (orn. TOPRAK\\Toprak) BOS bir
    hesaba cozunup grant sessizce BASARISIZ oluyordu (bu davranis
    tests/test_logical_imaging.py'deki ACL-deny testinde zaten
    belgelenmisti; ayni tuzak burada da gecerliydi) ve anahtar varsayilan
    (miras alinmis, baska kullanicilarin erisebildigi) izinlerde kaliyordu.
    Ayrica POSIX'te chmod sonrasi gercek izinler dogrulaniyor; group/other
    bitleri hala aciksa logger ile UYARIYORUZ (sessiz basarisizlik yok).
    """
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    if os.name == "nt":
        user = os.environ.get("USERNAME")
        domain = os.environ.get("USERDOMAIN")
        # DOMAIN\kullanici bicimi SART -- bkz. docstring ve
        # tests/test_logical_imaging.py'deki ayni bulguya dayanan test.
        hesap = f"{domain}\\{user}" if (user and domain) else user
        if hesap:
            try:
                sonuc = subprocess.run(
                    ["icacls", path, "/inheritance:r", "/grant:r", f"{hesap}:F"],
                    capture_output=True, check=False,
                )
                if sonuc.returncode != 0:
                    print(
                        f"[UYARI] Anahtar dosyasi izinleri (icacls) ayarlanamadi: "
                        f"{hesap} -- dosya varsayilan izinlerde kalmis olabilir."
                    )
            except OSError:
                pass
    else:
        # POSIX: chmod'un gercekten uygulandigini dogrula (bazı dosya
        # sistemleri, orn. bazı FAT/网络 mount'lari, chmod'u sessizce yok
        # sayar) -- group/other bitleri aciksa uyari ver.
        try:
            mod = os.stat(path).st_mode
            if mod & 0o077:
                print(
                    f"[UYARI] Anahtar dosyasi izinleri kisitlanamadi "
                    f"({oct(mod & 0o777)}) -- dosya baska kullanicilar tarafindan "
                    "okunabilir olabilir."
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
        self._eta_started_at = None
        self._eta_baslangic_oran = None
        self._durdur_bayragi = threading.Event()

    def request_stop(self):
        """Ana thread'den (GUI) cagirilir -- worker'a 'bir sonraki uygun
        noktada dur' sinyali verir. Su an islenmekte olan blok/dosya YARIDA
        KESILMEZ (asla yarim yazilmis bir sey 'alindi' sayilmaz); bir
        sonraki blok/dosya BASLAMADAN once devreye girer. Su ana kadarki
        ilerleme (kalici manifest dahil) korunur, daha sonra ayni hedef
        secilince devam teklif edilir (bkz. acquire_disk_image/
        acquire_remote_tree'deki should_stop parametresi)."""
        self._durdur_bayragi.set()

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

    def _ilerleme_metni(self, oran, ekstra=""):
        """'İlerleme: %XX (...)' metnine, o anki ÇALIŞTIRMADA ÖLÇÜLEN gerçek
        hıza göre tahmini kalan süreyi ekler (sabit bir tahmin değil -- RAM/
        WinPmem hash ilerlemesindeki AYNI yöntem, bkz. ram_gui.py.
        _emit_hash_progress). oran: 0..1 arasi tamamlanma orani.

        Devam eden (resume) bir islemde oran zaten yuksek bir yerden
        basliyor olabilir -- bu yuzden BASLANGIC oranini da saklayip sadece
        BU calistirmada kat edilen mesafeyi hiz hesabina katiyoruz; yoksa
        resume'un hemen basinda "neredeyse bitti" gibi yanlis bir tahmin
        cikardi."""
        simdi = time.monotonic()
        if self._eta_started_at is None:
            self._eta_started_at = simdi
            self._eta_baslangic_oran = oran
        gecen = simdi - self._eta_started_at
        taban = f"İlerleme: %{oran * 100:.0f}" + (f" {ekstra}" if ekstra else "")
        kat_edilen = oran - self._eta_baslangic_oran
        if kat_edilen > 0.01 and gecen > 1.0:
            hiz = kat_edilen / gecen
            kalan_sn = (1 - oran) / hiz if hiz > 0 else 0
            return f"{taban}, tahmini kalan: {format_duration_tr(kalan_sn)}"
        return taban

    def _new_report(self, engine, method, **kwargs):
        if ForensicReport is None:
            return None
        c = self.ctx
        report = ForensicReport(
            case_id=c["case_id"], examiner=c["examiner"], custodian=c["custodian"],
            organization=c["organization"], case_notes=c.get("case_notes", ""),
            display_timezone=c.get("display_timezone"),
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
        segment_size_bytes = c.get("segment_size_bytes")
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

            mevcut = find_incomplete_manifest(disk, host=c["host"])
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
                    # Reddedilen manifest diskte birakilirsa "Yarim Kalanlar"
                    # listesinde SONSUZA KADAR (silinecek bir yolu olmadan)
                    # gorunmeye devam ederdi (kullanici bildirdi) -- kullanici
                    # zaten "hayir, bununla ilgilenmiyorum" dedigi icin burada
                    # temizliyoruz.
                    delete_manifest(manifest_path)
                    manifest_path = None
                    resume_state = None

            apply_wb = (mode == "offline")
            # bkz. Windows disk kolundaki AYNI duzeltme -- start_block > 0
            # (gercek bir resume) ise acquire_disk_image write-block'u bu
            # calistirmada TEKRAR UYGULAMAZ (sadece GERCEK durumu kontrol
            # edip delil zincirine kaydeder), ama rapor eskiden hep sabit
            # apply_wb/"Offline Acquisition" yaziyordu -- write-block
            # GERCEKTEN uygulanmadigi halde uygulandigini iddia ediyordu.
            if report:
                if start_block > 0:
                    report.set_write_blocking(
                        None,
                        "Devam eden (resume) işlem -- bu çalıştırmada write-block "
                        "yeniden UYGULANMADI, sadece GERÇEK durum kontrol edilip "
                        "delil zincirine kaydedildi -- kesin sonuç için chain of "
                        "custody olay listesine bakın.",
                    )
                else:
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
                host=c["host"], should_stop=self._durdur_bayragi.is_set,
            )

            while sonuc is not None and "resume_from" in sonuc and not sonuc.get("user_stopped"):
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
                    host=c["host"], should_stop=self._durdur_bayragi.is_set,
                )

            if sonuc is None:
                if report:
                    report.finish(status="failed", output_path=out_path)
                    self._save_report(report, os.path.dirname(out_path) or ".")
                self.log.emit("[HATA] İmaj alma başarısız oldu.", None)
                return

            if "resume_from" in sonuc:
                durduruldu_mu = sonuc.get("user_stopped", False)
                if report:
                    report.finish(
                        status="partial", output_path=out_path,
                        chunk_size_bytes=sonuc.get("block_size_mb", 0) * 1024 * 1024,
                        chunk_count=len(sonuc.get("acquired_blocks", [])),
                        failed_items=["Kullanıcı tarafından durduruldu"] if durduruldu_mu
                        else [f"resume_from={sonuc['resume_from']}"],
                    )
                    self._save_report(report, sonuc.get("output_dir") or os.path.dirname(out_path) or ".")
                if durduruldu_mu:
                    self.status.emit("Durduruldu.")
                    self.log.emit(
                        f"[BİLGİ] İşlem durduruldu ({len(sonuc.get('acquired_blocks', []))}/"
                        f"{sonuc.get('total_blocks', '?')} blok). Manifest korunuyor, aynı diski seçip devam edebilirsiniz.",
                        None,
                    )
                else:
                    self.log.emit("[BİLGİ] İşlem yarım kaldı. Daha sonra aynı diski seçip devam edebilirsiniz.", None)
                return

            segments = None
            if segment_size_bytes:
                self.log.emit("\n[+] Bloklar segmentlere bölünüyor...", "info")
                segments = write_segments(
                    sonuc["block_paths"], sonuc["total_blocks"], segment_size_bytes,
                    output_dir=sonuc["output_dir"],
                    output_basename=os.path.splitext(os.path.basename(out_path))[0],
                    cleanup=(mode != "live"),
                )
                if segments is None:
                    if report:
                        report.finish(
                            status="failed", output_path=out_path,
                            failed_items=[str(b) for b in sonuc.get("failed_blocks", [])],
                        )
                        self._save_report(report, sonuc.get("output_dir") or os.path.dirname(out_path) or ".")
                    self.log.emit("[HATA] Eksik bloklar nedeniyle segmentli imaj oluşturulamadı.", None)
                    return
                imaj_yolu = segments[0]
                self.log.emit(f"[BAŞARILI] İmaj {len(segments)} segmente bölündü: {imaj_yolu} (+{len(segments) - 1} diğer)", None)
                hashes = hash_files_multi(segments)
            else:
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
                # SHA-256 + MD5 + SHA-1 TEK okuma gecisinde birlikte hesaplanir
                # (bkz. forensic_report.finish()'teki AYNI gerekce) -- sikistirma
                # varsa bile bu HAM (henuz sikistirilmamis) icerik uzerinde
                # yapilir, cunku rapordaki butunluk degeri her zaman ham
                # icerige ait kalmali.
                hashes = hash_file_multi(imaj_yolu)
            master_hash = hashes.get("sha256")
            self.log.emit(f"[+] Yerel master SHA-256: {master_hash}", "info")
            raw_bytes = sum(os.path.getsize(s) for s in segments) if segments else os.path.getsize(imaj_yolu)

            if compress and not segments:
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
                    md5_hash=hashes.get("md5"), sha1_hash=hashes.get("sha1"),
                    total_bytes=raw_bytes, chunk_size_bytes=bs * 1024 * 1024,
                    chunk_count=len(sonuc.get("acquired_blocks", [])),
                    failed_items=[str(b) for b in sonuc.get("failed_blocks", [])],
                )
                rapor_yolu = self._save_report(report, os.path.dirname(imaj_yolu) or ".")
                self.report_ready.emit(report, rapor_yolu)

            if segments:
                self.log.emit(
                    "[i] İmaj segmentlere bölündüğü için otomatik doğrulama atlandı -- "
                    "gerekirse verify_report.py ile bağımsız doğrulayabilirsiniz "
                    "(ilk segmenti verin, diğerleri otomatik bulunur).",
                    "info",
                )
            elif compress:
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
            self.status.emit(self._ilerleme_metni(pct / 100))
        self.log.emit(text.rstrip("\n"), None)

    # -- Windows tam disk -- gui_v2.py _acquisition_worker_windows ile AYNI --
    def _run_windows_disk(self):
        c = self.ctx
        disk_number, out_path, mode, block_size_mb = (
            c["disk_number"], c["out_path"], c["mode"], c["block_size_mb"],
        )
        compress = c.get("compress", False)
        segment_size_bytes = c.get("segment_size_bytes")
        try:
            disk_description = get_disk_description_windows(self.ssh, disk_number)
        except Exception:
            disk_description = ""
        report = self._new_report(
            engine="ssh_engine", method="disk", target_os="windows",
            target_host=c["host"], source_identifier=f"PhysicalDrive{disk_number}", acquisition_type=mode,
            source_description=disk_description,
        )
        # Linux kolundaki AYNI degisken -- Windows kolu birlestirme sonrasi
        # `segments` kullanıyor (hash ve log akisi); tanimlanmamis olsaydi
        # imaj BASHARIYLA bittikten sonra NameError ile rapor kaybedilirdi.
        segments = None
        try:
            apply_wb = (mode == "offline")

            def ilerleme(done, total):
                pct = (done * 100 / total) if total else 0
                self.progress.emit(pct)
                self.status.emit(self._ilerleme_metni(pct / 100, f"({done}/{total} blok)"))

            # bkz. Linux disk kolundaki AYNI kontrol -- Windows tarafinda
            # bu hic yapilmiyordu (gercek bir eksiklik, kullanici bildirdi):
            # uygulama tamamen kapanip acilsa bile disktekilerden yarim
            # kalan bir islem varsa devam etmeyi teklif ediyor.
            manifest_path = None
            resume_state0 = None
            start_block0 = 0
            mevcut = find_incomplete_manifest(f"PhysicalDrive{disk_number}", host=c["host"])
            if mevcut:
                manifest_path, resume_state0 = mevcut
                completed = len(resume_state0.get("acquired_blocks", []))
                total = resume_state0.get("total_blocks", 0)
                self.log.emit(f"[UYARI] Yarım kalan işlem bulundu: {completed}/{total} blok tamamlanmış.", None)
                devam = self._ask_yesno_blocking(
                    "Yarım Kalan İşlem",
                    f"Bu disk için yarım kalan bir işlem bulundu.\nTamamlanan: {completed}/{total} blok\nDevam edilsin mi?",
                )
                if devam:
                    start_block0 = completed
                else:
                    # bkz. Linux disk kolundaki AYNI duzeltme -- reddedilen
                    # manifest silinmezse "Yarim Kalanlar" listesinde
                    # sonsuza kadar kalirdi.
                    delete_manifest(manifest_path)
                    manifest_path = None
                    resume_state0 = None

            # set_write_blocking() BURADA, resume kontrolunden SONRA cagirilir --
            # onceden resume kontrolunden ONCE cagiriliyordu, bu yuzden bir
            # resume kabul edildiginde acquire_disk_image_windows'a GERCEKTE
            # apply_write_blocker=False gecmesine ragmen rapor hala eski
            # apply_wb/"Offline Acquisition" degerini tasiyordu -- rapor,
            # write-block GERCEKTEN uygulanmadigi halde uygulandigini iddia
            # ediyordu (kullanici bildirdi, bkz. docs/hatalar_ve_sonuclar.md).
            # start_block0 > 0 (gercek bir resume) ise, write-block bu
            # calistirmada TEKRAR uygulanmiyor -- acquire_disk_image_windows
            # zaten bu durumda GERCEK durumu (is_write_blocked_windows ile)
            # kontrol edip delil zincirine ayrica kaydediyor; rapor da bunu
            # acikca yansitir, "uygulandi" diye YANLIS bir iddiada bulunmaz.
            if report:
                if start_block0 > 0:
                    report.set_write_blocking(
                        None,
                        "Devam eden (resume) işlem -- bu çalıştırmada write-block "
                        "yeniden UYGULANMADI, sadece GERÇEK durum kontrol edilip "
                        "delil zincirine kaydedildi -- kesin sonuç için chain of "
                        "custody olay listesine bakın.",
                    )
                else:
                    report.set_write_blocking(
                        apply_wb,
                        "Offline Acquisition" if apply_wb else (
                            "Live Acquisition -- disk aktif kullanimda, kilitlenmedi. "
                            "Bloklar bir sureye yayilarak okundugu icin imaj, diskin "
                            "TEK bir anina degil, alma suresince degisebilecek bir "
                            "durumuna karsilik gelebilir."
                        ),
                    )

            sonuc = acquire_disk_image_windows(
                self.ssh, disk_number, output_dir=os.path.dirname(out_path) or ".",
                block_size_mb=resume_state0["block_size_mb"] if resume_state0 else block_size_mb,
                apply_write_blocker=apply_wb,
                total_blocks=resume_state0["total_blocks"] if resume_state0 else None,
                start_block=start_block0, resume_state=resume_state0, manifest_path=manifest_path,
                progress_callback=ilerleme, host=c["host"], should_stop=self._durdur_bayragi.is_set,
            )

            while sonuc is not None and "resume_from" in sonuc and not sonuc.get("user_stopped"):
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
                    host=c["host"], should_stop=self._durdur_bayragi.is_set,
                )

            if sonuc is None:
                if report:
                    report.finish(status="failed", output_path=out_path)
                    self._save_report(report, os.path.dirname(out_path) or ".")
                self.log.emit("[HATA] İmaj alma başarısız oldu (Windows).", None)
                return

            if "resume_from" in sonuc:
                durduruldu_mu = sonuc.get("user_stopped", False)
                if report:
                    report.finish(
                        status="partial", output_path=out_path,
                        chunk_size_bytes=sonuc.get("block_size_mb", 0) * 1024 * 1024,
                        chunk_count=len(sonuc.get("acquired_blocks", [])),
                        failed_items=["Kullanıcı tarafından durduruldu"] if durduruldu_mu
                        else [f"resume_from={sonuc['resume_from']}"],
                    )
                    self._save_report(report, sonuc.get("output_dir") or os.path.dirname(out_path) or ".")
                if durduruldu_mu:
                    self.status.emit("Durduruldu.")
                    self.log.emit(
                        f"[BİLGİ] İşlem durduruldu ({len(sonuc.get('acquired_blocks', []))}/"
                        f"{sonuc.get('total_blocks', '?')} blok). Manifest korunuyor, aynı diski seçip devam edebilirsiniz.",
                        None,
                    )
                else:
                    self.log.emit("[BİLGİ] İşlem yarım kaldı. Daha sonra aynı diski seçip devam edebilirsiniz.", None)
                return

            # bkz. Linux kolundaki AYNI akis -- segment_size_bytes GUI'de
            # secilebiliyor ve _start_disk_windows ctx'e koyuyor ama kol
            # icinde HIC kontrol edilmiyordu: kullanici "2 GB segment"
            # secse bile sessizce tek dosya birlestiriliyordu (bui bir
            # sessiz ozellik kaybiydi, simdi Linux ile ayni akis).
            segments = None
            if segment_size_bytes:
                self.log.emit("\n[+] Bloklar segmentlere bölünüyor...", "info")
                segments = write_segments(
                    sonuc["block_paths"], sonuc["total_blocks"], segment_size_bytes,
                    output_dir=sonuc["output_dir"],
                    output_basename=os.path.splitext(os.path.basename(out_path))[0],
                    cleanup=(mode != "live"),
                )
                if segments is None:
                    if report:
                        report.finish(
                            status="failed", output_path=out_path,
                            failed_items=[str(b) for b in sonuc.get("failed_blocks", [])],
                        )
                        self._save_report(report, sonuc.get("output_dir") or os.path.dirname(out_path) or ".")
                    self.log.emit("[HATA] Eksik bloklar nedeniyle segmentli imaj oluşturulamadı.", None)
                    return
                imaj_yolu = segments[0]
                self.log.emit(f"[BAŞARILI] İmaj {len(segments)} segmente bölündü: {imaj_yolu} (+{len(segments) - 1} diğer)", None)
                hashes = hash_files_multi(segments)
            else:
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
                # SHA-256 + MD5 + SHA-1 TEK okuma gecisinde birlikte hesaplanir
                # (bkz. forensic_report.finish()'teki AYNI gerekce) -- sikistirma
                # varsa bile bu HAM (henuz sikistirilmamis) icerik uzerinde
                # yapilir, cunku rapordaki butunluk degeri her zaman ham
                # icerige ait kalmali.
                hashes = hash_file_multi(imaj_yolu)
            master_hash = hashes.get("sha256")
            self.log.emit(f"[+] Yerel master SHA-256: {master_hash}", "info")
            raw_bytes = sum(os.path.getsize(s) for s in segments) if segments else os.path.getsize(imaj_yolu)

            if compress and not segments:
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
                    md5_hash=hashes.get("md5"), sha1_hash=hashes.get("sha1"),
                    total_bytes=raw_bytes, chunk_size_bytes=bs * 1024 * 1024,
                    chunk_count=len(sonuc.get("acquired_blocks", [])),
                    failed_items=[str(b) for b in sonuc.get("failed_blocks", [])],
                )
                rapor_yolu = self._save_report(report, os.path.dirname(imaj_yolu) or ".")
                self.report_ready.emit(report, rapor_yolu)

            if segments:
                self.log.emit(
                    "[i] İmaj segmentlere bölündüğü için otomatik doğrulama atlandı -- "
                    "gerekirse verify_report.py ile bağımsız doğrulayabilirsiniz "
                    "(ilk segmenti verin, diğerleri otomatik bulunur).",
                    "info",
                )
            elif compress:
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
        # Mantiksal imaj ayni kolu kullanir; sadece motor, rapor yontemi ve
        # devam (resume) manifest turu degisir.
        logical = c.get("logical", False)
        report = self._new_report(
            engine="ssh_engine", method="logical" if logical else "file", target_os=target_os,
            target_host=c["host"], source_identifier=remote_path,
            source_description=(
                "Mantiksal imaj -- kok yoldaki (tek hacim) okunabilen tum dosyalar; write-blocker uygulanmaz"
                if logical else "Dosya/klasor modu -- write-blocker uygulanmaz"
            ),
        )
        try:
            def ilerleme(done, total):
                pct = (done * 100 / total) if total else 0
                self.progress.emit(pct)
                self.status.emit(self._ilerleme_metni(pct / 100, f"({done}/{total} dosya)"))

            # bkz. disk imajlama kolundaki AYNI kontrol (docs/roadmap.md
            # madde 0.4) -- uygulama tamamen kapanip acilsa bile disktekilerden
            # bu klasor/dosya icin yarim kalan bir islem varsa devam etmeyi
            # teklif ediyor.
            tree_manifest_path = None
            tree_resume_state = None
            mevcut_tree = find_incomplete_tree_manifest(
                remote_path, host=c["host"], mode="logical" if logical else "file",
            )
            if mevcut_tree:
                tree_manifest_path, tree_resume_state = mevcut_tree
                completed = len(tree_resume_state.get("acquired_files", []))
                total = tree_resume_state.get("total_files", 0)
                self.log.emit(f"[UYARI] Yarım kalan işlem bulundu: {completed}/{total} dosya tamamlanmış.", None)
                devam = self._ask_yesno_blocking(
                    "Yarım Kalan İşlem",
                    f"Bu dosya/klasör için yarım kalan bir işlem bulundu.\nTamamlanan: {completed}/{total} dosya\nDevam edilsin mi?",
                )
                if not devam:
                    delete_manifest(tree_manifest_path)
                    tree_manifest_path = None
                    tree_resume_state = None

            if target_os == "windows":
                alici = acquire_logical_image_windows if logical else acquire_remote_tree_windows
                manifest = alici(
                    self.ssh, remote_path, out_dir, progress_callback=ilerleme,
                    manifest_path=tree_manifest_path, resume_state=tree_resume_state, host=c["host"],
                    should_stop=self._durdur_bayragi.is_set,
                )
            else:
                alici = acquire_logical_image if logical else acquire_remote_tree
                manifest = alici(
                    self.ssh, remote_path, out_dir, password=password, progress_callback=ilerleme,
                    manifest_path=tree_manifest_path, resume_state=tree_resume_state, host=c["host"],
                    should_stop=self._durdur_bayragi.is_set,
                )

            if manifest is None:
                if report:
                    report.finish(status="failed", output_path=out_dir)
                    self._save_report(report, out_dir)
                self.log.emit(f"[HATA] Uzak yol bulunamadı: {remote_path}", None)
                self.status.emit("Bulunamadı.")
                return

            durduruldu_mu = manifest.get("stopped", False)
            basarili = len(manifest["acquired"])
            basarisiz = len(manifest["failed"])
            if durduruldu_mu:
                self.log.emit(f"[BİLGİ] Durduruldu -- {basarili}/{manifest['total_files']} dosya alındı ve doğrulandı.", None)
            else:
                self.log.emit(f"[BAŞARILI] {basarili}/{manifest['total_files']} dosya alındı ve doğrulandı.", None)
            # Mantiksal imajda her basarisiz dosya icin sebep (izin yok/kilitli...)
            # da var; klasor modunda bos kalir.
            sebepler = manifest.get("failed_reasons", {})
            basarisiz_satirlari = [
                f"{yol} — {sebepler[yol]}" if sebepler.get(yol) else yol
                for yol in manifest["failed"]
            ]
            if basarisiz:
                self.log.emit(f"[UYARI] {basarisiz} dosya alınamadı:", None)
                for satir in basarisiz_satirlari:
                    self.log.emit(f"  - {satir}", "plain")
            if manifest.get("excluded"):
                self.log.emit(
                    f"[BİLGİ] {len(manifest['excluded'])} öğe bilerek alınmadı "
                    "(kilitli/sürekli değişen sistem öğeleri) — tam liste manifest'te.", "info",
                )
            self.log.emit(f"[+] Manifest: {os.path.join(out_dir, 'manifest_files.json')}", "info")
            if durduruldu_mu:
                self.status.emit("Durduruldu.")
                self.log.emit(
                    "[BİLGİ] Manifest korunuyor, aynı hedefi seçip devam edebilirsiniz.", None,
                )
            else:
                self.status.emit("Dosya/klasör alma tamamlandı.")
            self.progress.emit(100)

            if report:
                toplam_bayt = sum(
                    os.path.getsize(a["local_path"]) for a in manifest["acquired"]
                    if os.path.exists(a["local_path"])
                )
                if durduruldu_mu:
                    basarisiz_satirlari = ["Kullanıcı tarafından durduruldu"] + basarisiz_satirlari
                report.finish(
                    status="partial" if (durduruldu_mu or manifest["failed"]) else "success",
                    output_path=out_dir, total_bytes=toplam_bayt,
                    chunk_count=manifest["total_files"], failed_items=basarisiz_satirlari,
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
    def __init__(self, ssh, target_os, start_path, lang="tr", parent=None):
        super().__init__(parent)
        self.ssh = ssh
        self.target_os = target_os  # "linux" / "windows"
        self.current_path = start_path
        self.selected_path = None
        self.lang = lang

        self.setWindowTitle(t("tool_remote_browse_title", self.lang))
        self.setStyleSheet(f"background-color:{ui.BG_SURFACE};")
        self.resize(560, 420)

        layout = QVBoxLayout(self)

        path_row = QHBoxLayout()
        up_btn = widgets.SecondaryButton(t("tool_up", self.lang))
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
        select_folder_btn = widgets.PrimaryButton(t("tool_select_folder", self.lang))
        select_folder_btn.clicked.connect(self._select_current_folder)
        btn_row.addWidget(select_folder_btn)
        btn_row.addStretch()
        cancel_btn = widgets.SecondaryButton(t("btn_cancel", self.lang))
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
            self.status_label.setText(t("tool_folder_read_error", self.lang))
            return
        if not entries:
            self.status_label.setText(t("tool_empty_folder", self.lang))
            return
        self.status_label.setText(t("tool_item_count", self.lang, count=len(entries)))
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
                 initial_custodian="", initial_organization="", initial_case_notes="",
                 initial_connection_method=None,
                 display_timezone=None, lang="tr", parent=None):
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
        self.lang = lang or "tr"
        self._initial_case_id = initial_case_id
        self._initial_examiner = initial_examiner
        self._initial_custodian = initial_custodian
        self._initial_organization = initial_organization
        self._initial_case_notes = initial_case_notes
        self._display_timezone = display_timezone
        self._initial_connection_method = initial_connection_method
        self._method_locked = initial_connection_method is not None
        # "Bu bilgisayar" modu: SSH yok, arac incelenen makinenin kendisinde
        # calisir (bkz. local_connector.py).
        self._local_mode = initial_connection_method == "local"

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
            self._pending_error = t("tool_paramiko_missing", self.lang, exc=IMPORT_ERROR)
            layout = QVBoxLayout(self)
            lbl = QLabel(self._pending_error)
            lbl.setStyleSheet(f"color:{ui.ERROR};")
            layout.addWidget(lbl)
            return

        self._build_ui()
        self._log(t("tool_startup_log", self.lang), "info")

    # -- UI Olusturma -------------------------------------------------------
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(20, 14, 20, 14)
        if self.on_back:
            back_btn = widgets.SecondaryButton(t("btn_back", self.lang))
            back_btn.clicked.connect(self.on_back)
            header.addWidget(back_btn)
        title = QLabel(t("tool_local_title" if self._local_mode else "tool_ssh_title", self.lang))
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
        # launcher icinden aciliyorsa (on_back doluysa, ki her zaman boyle)
        # vaka bilgileri zaten ayri bir on-ekranda (chameleon_gui.py.
        # _show_case_info) bir kez toplanip initial_* olarak buraya
        # geciriliyor -- kart burada TEKRAR gosterilirse ayni alanlar iki kez
        # sorulmus gibi kafa karistiriyordu (kullanici bildirdi, ayni sorun
        # ram_gui.py'de de vardi, oradaki AYNI desenle duzeltildi). Alanlar
        # (entry_case_id vb.) worker'in okuyabilmesi icin yine olusturuluyor,
        # sadece ekranda GORUNMUYOR. Standalone calistirmada (on_back yok)
        # kart gorunur kalir -- tek vaka bilgisi girisi orasi.
        vaka = widgets.Card(t("case_info_title", self.lang))
        note = QLabel(t("case_info_note", self.lang))
        note.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px; font-style:italic;")
        vaka.body.addWidget(note)
        self.entry_case_id = self._labeled_row(vaka.body, t("field_case_id", self.lang), self._initial_case_id)
        self.entry_examiner = self._labeled_row(vaka.body, t("field_examiner", self.lang), self._initial_examiner)
        self.entry_custodian = self._labeled_row(vaka.body, t("field_custodian", self.lang), self._initial_custodian)
        self.entry_organization = self._labeled_row(vaka.body, t("field_organization", self.lang), self._initial_organization)
        notes_lbl = QLabel(f"{t('field_case_notes', self.lang)}:")
        notes_lbl.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_BODY}px;")
        vaka.body.addWidget(notes_lbl)
        self.entry_case_notes = QTextEdit()
        self.entry_case_notes.setPlainText(self._initial_case_notes)
        self.entry_case_notes.setFixedHeight(60)
        vaka.body.addWidget(self.entry_case_notes)
        if self.on_back:
            vaka.hide()
        body.addWidget(vaka)

        # === Baglanti Yontemi ===
        self.conn_method_value = self._initial_connection_method or "direct"
        yontem = widgets.Card(t("tool_conn_method_card", self.lang))
        if self._method_locked:
            method_names = {"direct": t("nav_direct", self.lang), "vpn": t("nav_vpn", self.lang), "tor": t("nav_tor", self.lang)}
            lbl = QLabel(t("tool_selected_method", self.lang, method=method_names.get(self.conn_method_value, self.conn_method_value)))
            lbl.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_BODY}px; font-weight:600;")
            yontem.body.addWidget(lbl)
            hint = QLabel(t("tool_change_method_hint", self.lang))
            hint.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
            yontem.body.addWidget(hint)
        else:
            row = QHBoxLayout()
            self.method_group = QButtonGroup(self)
            self.radio_direct = widgets.RadioButton(t("nav_direct", self.lang))
            self.radio_vpn = widgets.RadioButton(t("nav_vpn", self.lang))
            self.radio_tor = widgets.RadioButton(t("nav_tor", self.lang))
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
        self._ssh_only_cards = [yontem]

        # === SSH Baglanti Bilgileri ===
        conn = widgets.Card(t("tool_ssh_conn_card", self.lang))
        row1 = QHBoxLayout()
        row1.addWidget(QLabel(t("tool_host_label", self.lang)))
        self.entry_host = widgets.MonoInput()
        self.entry_host.setText("192.168.1.100")
        row1.addWidget(self.entry_host)
        row1.addWidget(QLabel(t("tool_port_label", self.lang)))
        self.entry_port = widgets.MonoInput()
        self.entry_port.setText("22")
        self.entry_port.setFixedWidth(70)
        row1.addWidget(self.entry_port)
        conn.body.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel(t("tool_user_label", self.lang)))
        self.entry_user = widgets.Input()
        row2.addWidget(self.entry_user)
        row2.addWidget(QLabel(t("tool_password_label", self.lang)))
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
        row3.addWidget(QLabel(t("tool_ssh_key_label", self.lang)))
        self.entry_key = widgets.MonoInput()
        row3.addWidget(self.entry_key)
        browse_key_btn = widgets.SecondaryButton(t("btn_browse", self.lang))
        browse_key_btn.clicked.connect(self._browse_key)
        row3.addWidget(browse_key_btn)
        conn.body.addLayout(row3)

        # === Sunucu Kimlik Dogrulama (host key) ===
        self.strict_host_key_value = True
        hk_label = QLabel(t("tool_hostkey_verification_label", self.lang))
        hk_label.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px; font-weight:600;")
        conn.body.addWidget(hk_label)

        hk_row = QHBoxLayout()
        self.hostkey_group = QButtonGroup(self)
        self.radio_hostkey_strict = widgets.RadioButton(t("tool_hostkey_strict", self.lang))
        self.radio_hostkey_skip = widgets.RadioButton(t("tool_hostkey_skip", self.lang))
        self.radio_hostkey_strict.setChecked(True)
        for r in (self.radio_hostkey_strict, self.radio_hostkey_skip):
            self.hostkey_group.addButton(r)
            hk_row.addWidget(r)
            r.toggled.connect(self._on_hostkey_mode_change)
        hk_row.addStretch()
        conn.body.addLayout(hk_row)

        hk_hint = QLabel(t("tool_hostkey_hint", self.lang))
        hk_hint.setWordWrap(True)
        hk_hint.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        conn.body.addWidget(hk_hint)

        conn.body.addWidget(self._help_link("host_key_verification"))

        self.hk_warn = QLabel(t("tool_hostkey_coc_note", self.lang))
        self.hk_warn.setWordWrap(True)
        self.hk_warn.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        self.hk_warn.setVisible(False)
        conn.body.addWidget(self.hk_warn)

        connect_row = QHBoxLayout()
        self.btn_connect = widgets.PrimaryButton(t("tool_btn_connect", self.lang))
        self.btn_connect.clicked.connect(self._connect)
        connect_row.addWidget(self.btn_connect)
        connect_row.addStretch()
        conn.body.addLayout(connect_row)
        body.addWidget(conn)
        self._ssh_only_cards.append(conn)

        # === Hedef Isletim Sistemi ===
        os_card = widgets.Card(t("tool_target_os_card", self.lang))
        self._ssh_only_cards.append(os_card)
        os_row = QHBoxLayout()
        self.os_group = QButtonGroup(self)
        self.radio_os_linux = widgets.RadioButton(t("tool_os_linux", self.lang))
        self.radio_os_windows = widgets.RadioButton(t("tool_os_windows", self.lang))
        self.radio_os_linux.setChecked(True)
        for r in (self.radio_os_linux, self.radio_os_windows):
            self.os_group.addButton(r)
            os_row.addWidget(r)
            r.toggled.connect(self._on_target_os_change)
        os_row.addStretch()
        os_card.body.addLayout(os_row)
        body.addWidget(os_card)

        # === Ne Alinacak ===
        acq_card = widgets.Card(t("tool_what_card", self.lang))
        acq_row = QHBoxLayout()
        self.acq_group = QButtonGroup(self)
        self.radio_acq_disk = widgets.RadioButton(t("tool_acq_full_disk", self.lang))
        self.radio_acq_file = widgets.RadioButton(t("tool_acq_file_folder", self.lang))
        self.radio_acq_logical = widgets.RadioButton(t("tool_acq_logical", self.lang))
        self.radio_acq_disk.setChecked(True)
        for r in (self.radio_acq_disk, self.radio_acq_file, self.radio_acq_logical):
            self.acq_group.addButton(r)
            acq_row.addWidget(r)
            r.toggled.connect(self._on_acq_type_change)
        acq_row.addStretch()
        acq_card.body.addLayout(acq_row)
        body.addWidget(acq_card)

        # === Hedef Disk ve Islem Modu ===
        self.disk_card = widgets.Card(t("tool_disk_mode_card", self.lang))
        disk_row1 = QHBoxLayout()
        self.lbl_disk_path = QLabel(t("tool_disk_path_label", self.lang))
        disk_row1.addWidget(self.lbl_disk_path)
        self.entry_disk = widgets.MonoInput()
        disk_row1.addWidget(self.entry_disk)
        self.mode_group = QButtonGroup(self)
        self.radio_live = widgets.RadioButton(t("tool_live_acq", self.lang))
        self.radio_offline = widgets.RadioButton(t("tool_offline_acq", self.lang))
        self.radio_live.setChecked(True)
        for r in (self.radio_live, self.radio_offline):
            self.mode_group.addButton(r)
            disk_row1.addWidget(r)
        self.disk_card.body.addLayout(disk_row1)
        self.disk_card.body.addWidget(self._help_link("live_vs_offline_acquisition"))

        disk_row2 = QHBoxLayout()
        disk_row2.addWidget(QLabel(t("tool_image_out_label", self.lang)))
        self.entry_out = widgets.MonoInput()
        self.entry_out.setText(DEFAULT_IMAGE_PATH)
        disk_row2.addWidget(self.entry_out, stretch=1)
        browse_out_btn = widgets.SecondaryButton(t("btn_browse", self.lang))
        browse_out_btn.clicked.connect(self._browse_out)
        disk_row2.addWidget(browse_out_btn)
        self.disk_card.body.addLayout(disk_row2)

        disk_row3 = QHBoxLayout()
        disk_row3.addWidget(QLabel(t("tool_block_size_label", self.lang)))
        self.combo_block_size = QComboBox()
        self.combo_block_size.addItems([
            t("tool_block_size_4mb", self.lang), t("tool_block_size_16mb", self.lang),
            t("tool_block_size_32mb", self.lang), t("tool_block_size_64mb", self.lang),
        ])
        self.combo_block_size.setStyleSheet(f"""
            QComboBox {{ background-color:{ui.BG_LAYER2}; color:{ui.TEXT_MAIN};
                border:1px solid {ui.BORDER}; border-radius:{ui.RADIUS}px; padding:4px 8px; }}
        """)
        disk_row3.addWidget(self.combo_block_size)
        disk_row3.addStretch()
        self.disk_card.body.addLayout(disk_row3)

        # Buyuk bir imaji FAT32 (4 GB dosya siniri) gibi sabit boyutlu bir
        # hedefe tasinabilir kilmak icin -- FTK Imager'in "Raw (dd) -
        # split" ciktisindaki AYNI .001/.002/... adlandirmasi (bkz.
        # image_acquirer.write_segments()). Varsayilan "Bölme Yok" --
        # segmentli cikti, tek dosyaya gore ekstra bir adim oldugu icin
        # sadece gercekten gerektiginde acikca secilmeli.
        disk_row4 = QHBoxLayout()
        disk_row4.addWidget(QLabel(t("tool_segment_size_label", self.lang)))
        self.combo_segment_size = QComboBox()
        self.combo_segment_size.addItem(t("tool_segment_none", self.lang), None)
        self.combo_segment_size.addItem(t("tool_segment_650mb", self.lang), 650 * 1024 * 1024)
        self.combo_segment_size.addItem(t("tool_segment_2gb", self.lang), 2 * 1024 * 1024 * 1024)
        self.combo_segment_size.addItem(t("tool_segment_4gb", self.lang), 4 * 1000 * 1000 * 1000)
        self.combo_segment_size.setStyleSheet(f"""
            QComboBox {{ background-color:{ui.BG_LAYER2}; color:{ui.TEXT_MAIN};
                border:1px solid {ui.BORDER}; border-radius:{ui.RADIUS}px; padding:4px 8px; }}
        """)
        disk_row4.addWidget(self.combo_segment_size)
        disk_row4.addStretch()
        self.disk_card.body.addLayout(disk_row4)
        self.combo_segment_size.currentIndexChanged.connect(self._on_mode_change)
        self.disk_card.body.addWidget(self._hint_label("tool_segment_hint"))

        # Sadece Offline Acquisition icin anlamli -- Live modda parcalar
        # resume ihtimaline karsi zaten korunuyor (concatenate_blocks
        # cleanup=False), sikistirma o senaryoda ekstra bir adim/risk
        # olurdu. Mod degisince _on_mode_change ile devre disi/acik yapilir.
        self.check_compress = widgets.Checkbox(t("tool_compress_checkbox", self.lang))
        self.check_compress.setEnabled(False)
        self.disk_card.body.addWidget(self.check_compress)
        self.disk_card.body.addWidget(self._hint_label("tool_compress_hint"))

        for r in (self.radio_live, self.radio_offline):
            r.toggled.connect(self._on_mode_change)

        body.addWidget(self.disk_card)

        # === Hedef Dosya/Klasor ===
        self.file_card = widgets.Card(t("tool_file_folder_card", self.lang))
        file_row1 = QHBoxLayout()
        self.lbl_remote_path = QLabel(t("tool_remote_path_label", self.lang))
        file_row1.addWidget(self.lbl_remote_path)
        self.entry_remote_path = widgets.MonoInput()
        file_row1.addWidget(self.entry_remote_path, stretch=1)
        browse_remote_btn = widgets.SecondaryButton(t("btn_browse", self.lang))
        browse_remote_btn.clicked.connect(self._browse_remote_path)
        file_row1.addWidget(browse_remote_btn)
        self.file_card.body.addLayout(file_row1)

        file_row2 = QHBoxLayout()
        file_row2.addWidget(QLabel(t("tool_output_folder_label", self.lang)))
        self.entry_file_out = widgets.MonoInput()
        self.entry_file_out.setText(os.path.join(_PERSISTENT_ROOT, "images", "dosyalar"))
        file_row2.addWidget(self.entry_file_out, stretch=1)
        browse_file_out_btn = widgets.SecondaryButton(t("btn_browse", self.lang))
        browse_file_out_btn.clicked.connect(self._browse_file_out)
        file_row2.addWidget(browse_file_out_btn)
        self.file_card.body.addLayout(file_row2)

        file_warn = QLabel(t("tool_file_mode_warn", self.lang))
        file_warn.setWordWrap(True)
        file_warn.setStyleSheet(f"color:{ui.WARNING}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        self.file_card.body.addWidget(file_warn)
        body.addWidget(self.file_card)
        self.file_card.hide()

        # === Mantiksal Imaj === (bkz. docs/roadmap.md madde 0.5) Klasor
        # modundan farki: kok yol (bir disk bolumu) icindeki OKUNABILEN her
        # dosyayi alir, alinamayanlari NEDENIYLE raporlar.
        self.logical_card = widgets.Card(t("tool_logical_card", self.lang))
        logical_row1 = QHBoxLayout()
        self.lbl_logical_root = QLabel(t("tool_logical_root_label", self.lang))
        logical_row1.addWidget(self.lbl_logical_root)
        self.entry_logical_root = widgets.MonoInput()
        self.entry_logical_root.setText("/")
        logical_row1.addWidget(self.entry_logical_root, stretch=1)
        self.logical_card.body.addLayout(logical_row1)

        logical_row2 = QHBoxLayout()
        logical_row2.addWidget(QLabel(t("tool_output_folder_label", self.lang)))
        self.entry_logical_out = widgets.MonoInput()
        self.entry_logical_out.setText(os.path.join(_PERSISTENT_ROOT, "images", "mantiksal"))
        logical_row2.addWidget(self.entry_logical_out, stretch=1)
        browse_logical_out_btn = widgets.SecondaryButton(t("btn_browse", self.lang))
        browse_logical_out_btn.clicked.connect(self._browse_logical_out)
        logical_row2.addWidget(browse_logical_out_btn)
        self.logical_card.body.addLayout(logical_row2)

        logical_note = QLabel(t("tool_logical_note", self.lang))
        logical_note.setWordWrap(True)
        logical_note.setStyleSheet(f"color:{ui.WARNING}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        self.logical_card.body.addWidget(logical_note)
        body.addWidget(self.logical_card)
        self.logical_card.hide()

        # === Butonlar ===
        btn_row = QHBoxLayout()
        self.btn_acquire = widgets.PrimaryButton(t("tool_btn_start_acquisition", self.lang))
        self.btn_acquire.clicked.connect(self._start_acquisition)
        btn_row.addWidget(self.btn_acquire)
        self.btn_stop = widgets.SecondaryButton(t("tool_btn_stop_acquisition", self.lang))
        self.btn_stop.clicked.connect(self._stop_acquisition)
        self.btn_stop.hide()
        btn_row.addWidget(self.btn_stop)
        verify_btn = widgets.SecondaryButton(t("tool_btn_verify_image", self.lang))
        verify_btn.clicked.connect(self._verify_image)
        btn_row.addWidget(verify_btn)
        btn_row.addStretch()
        clear_btn = widgets.SecondaryButton(t("tool_btn_clear_log", self.lang))
        clear_btn.clicked.connect(self._clear_log)
        btn_row.addWidget(clear_btn)
        body.addLayout(btn_row)

        # === Ilerleme ===
        self.progress = widgets.ProgressBar()
        body.addWidget(self.progress)
        self.status_label = QLabel(t("tool_status_waiting", self.lang))
        self.status_label.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px; font-style:italic;")
        body.addWidget(self.status_label)

        # === Log ===
        log_card = widgets.Card(t("tool_log_card", self.lang))
        help_links_row = QHBoxLayout()
        help_links_row.addWidget(self._help_link("chain_of_custody", t("tool_help_link_coc", self.lang)))
        help_links_row.addWidget(self._help_link("hash_verification", t("tool_help_link_hash", self.lang)))
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
        if self._local_mode:
            self._setup_local_mode(body)

    def _setup_local_mode(self, body):
        """Yerel mod: SSH'e ozgu kartlar (yontem/baglanti/hedef OS) gizlenir, OS
        Windows'a sabitlenir, baglanti hazir sayilir. Ekranin geri kalani
        (ne alinacak, cikti, log, rapor) SSH moduyla AYNI -- ayni kod calisir."""
        for card in self._ssh_only_cards:
            card.hide()
        self.radio_os_windows.setChecked(True)
        self.conn_method_value = "local"
        # Rapordaki "hedef" alani bu bilgisayarin adi olur.
        self.entry_host.setText(platform.node())

        # Blok boyutu aciklamalari ("yavas/kararsiz baglanti" vb.) SSH
        # uzerinden ag hizina gore secim icin anlamli -- yerel modda ag hic
        # yok, sadece duz MB degeri sorulmasi yeterli (kullanici bildirdi).
        self.combo_block_size.clear()
        self.combo_block_size.addItems(["4 MB", "16 MB", "32 MB", "64 MB"])
        self.combo_block_size.setCurrentIndex(3)  # 64 MB -- yerel okumada ag hizi kisiti yok

        info = widgets.Card(t("tool_local_info_card", self.lang))
        lbl = QLabel(t("tool_local_info", self.lang))
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        info.body.addWidget(lbl)
        # Vaka Bilgileri karti (varsa) en ustte kalsin, bilgi karti hemen altina
        body.insertWidget(1, info)

        # Yönetici değilse görünür ama sessiz bir uyarı şeridi (bilgi kartının
        # ÜSTÜNDE); yöneticiyse hiçbir şey gösterilmez.
        self.admin_banner = None
        if not is_admin():
            self.admin_banner = QLabel(t("tool_local_admin_banner", self.lang))
            self.admin_banner.setWordWrap(True)
            self.admin_banner.setStyleSheet(
                f"color:{ui.WARNING}; background-color:{ui.BG_SURFACE}; border:1px solid {ui.WARNING}; "
                f"border-radius:{ui.RADIUS}px; padding:8px 12px; "
                f"font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px; font-weight:600;"
            )
            body.insertWidget(1, self.admin_banner)

        self.ssh = LocalConnector()
        self._set_conn_indicator(True)
        self._log(f"[i] Yerel mod: bu bilgisayar ({platform.node()}) incelenecek, SSH kullanılmıyor.", "info")
        if not is_admin():
            self._log(f"[UYARI] {t('tool_local_err_admin', self.lang)}", "warn")
        self.disks_raw = self.ssh.list_disks()
        self._log("--- Mevcut Diskler ---", "info")
        self._log(self.disks_raw or "(disk listelenemedi)", "plain")
        self._set_status(t("tool_status_connected_disks", self.lang))

    def _local_precheck(self, disk_number=None, root_path=None, out_path=None):
        """Yerel modda kaynaga yazmayi/riskli kosulu onleyen kontroller. Sorun
        varsa kullaniciya hata gosterip False doner. Disk modu icin disk_number,
        mantiksal/dosya modu icin root_path verilir."""
        if disk_number is not None and not is_admin():
            kod = "admin"
        elif disk_number is not None:
            kod = check_output_not_on_source(self.ssh, disk_number, out_path)
        else:
            kod = check_root_output_separate(self.ssh, root_path, out_path)
        hata_anahtari = {
            "admin": "tool_local_err_admin",
            "output_on_source": "tool_local_err_output_on_source",
            "output_disk_unknown": "tool_local_err_output_unknown",
        }.get(kod)
        if hata_anahtari:
            self._show_error(t(hata_anahtari, self.lang))
            return False

        if disk_number is not None:
            sistem_mi = disk_number == system_disk_number(self.ssh)
            if sistem_mi:
                if self.radio_offline.isChecked():
                    self._show_error(t("tool_local_err_system_offline", self.lang))
                    return False
                if not self._show_yesno_dialog(
                    t("tool_local_system_live_title", self.lang), t("tool_local_system_live_msg", self.lang),
                ):
                    return False
            coc.log_event(
                coc.EVENT_LOCAL_MODE,
                f"Yerel imaj: kaynak PhysicalDrive{disk_number}"
                f"{' (CALISAN SISTEM DISKI, canli)' if sistem_mi else ''}, cikti: {out_path}, bilgisayar: {platform.node()}",
            )
        else:
            coc.log_event(
                coc.EVENT_LOCAL_MODE,
                f"Yerel imaj: kaynak yol {root_path}, cikti: {out_path}, bilgisayar: {platform.node()}",
            )
        return True

    def _hint_label(self, key):
        """Form alanlarının altındaki küçük, satır kaydıran açıklama metni."""
        lbl = QLabel(t(key, self.lang))
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        return lbl

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
        note = QLabel(t("tool_vpn_note", self.lang))
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        layout.addWidget(note)
        return panel

    def _build_tor_info_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(6)

        heading = QLabel(t("tool_tor_heading", self.lang))
        heading.setStyleSheet(f"color:{ui.ACCENT_TEXT}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px; font-weight:600;")
        layout.addWidget(heading)

        what = QLabel(t("tool_tor_what", self.lang))
        what.setWordWrap(True)
        what.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        layout.addWidget(what)

        steps_heading = QLabel(t("tool_tor_steps_heading", self.lang))
        steps_heading.setStyleSheet(f"color:{ui.ACCENT_TEXT}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px; font-weight:600;")
        layout.addWidget(steps_heading)

        steps = QLabel(t("tool_tor_steps", self.lang))
        steps.setWordWrap(True)
        steps.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        layout.addWidget(steps)

        warn = QLabel(t("tool_tor_warn", self.lang))
        warn.setWordWrap(True)
        warn.setStyleSheet(f"color:{ui.WARNING}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px; font-weight:600;")
        layout.addWidget(warn)

        key_heading = QLabel(t("tool_tor_key_heading", self.lang))
        key_heading.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px; font-weight:600;")
        layout.addWidget(key_heading)

        key_row = QHBoxLayout()
        self.entry_operator_pubkey = widgets.MonoInput()
        self.entry_operator_pubkey.setReadOnly(True)
        key_row.addWidget(self.entry_operator_pubkey)
        copy_btn = widgets.SecondaryButton(t("btn_copy", self.lang))
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
        hint = QLabel(t("tool_tor_key_confirm_hint", self.lang))
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
                self.lbl_operator_key_fingerprint.setText(t("tool_key_code_label", self.lang, code=key_fingerprint(self._operator_public_key)))

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

    def _help_link(self, topic_key, label=None):
        """Bilgi Merkezi'ndeki bir konuya goturen, mavi metin gorunumlu
        kucuk bir buton."""
        if label is None:
            label = t("btn_read_in_help_center", self.lang)
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

        topic = get_topic(topic_key, self.lang)
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

        close_btn = widgets.SecondaryButton(t("btn_close", self.lang))
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        dialog.exec()

    # -- Kucuk UI durum degisimleri ------------------------------------------
    def _on_target_os_change(self, *_args):
        # Mantiksal imajin kok yolu, kullanici elle degistirmediyse (hala
        # eski OS'in varsayilani) yeni OS'in varsayilanina gecer.
        eski_varsayilan, yeni_varsayilan = ("/", "C:\\") if self.radio_os_windows.isChecked() else ("C:\\", "/")
        if self.entry_logical_root.text().strip() == eski_varsayilan:
            self.entry_logical_root.setText(yeni_varsayilan)
        if self.radio_os_windows.isChecked():
            self.lbl_disk_path.setText(t("tool_disk_number_label", self.lang))
            self.lbl_remote_path.setText(t("tool_remote_path_label_win", self.lang))
        else:
            self.lbl_disk_path.setText(t("tool_disk_path_label", self.lang))
            self.lbl_remote_path.setText(t("tool_remote_path_label", self.lang))

    def _on_mode_change(self, *_args):
        offline = self.radio_offline.isChecked()
        # Segmentli (.001/.002/...) cikti ile gzip sikistirma birlikte
        # anlamli degil -- sikistirma TEK bir dosya uzerinde calisir,
        # segmentlerin sadece ILKINI sikistirmak yanlis olur. Ikisi
        # karsilikli dislanir.
        segmenting = self._get_segment_size_bytes() is not None
        self.check_compress.setEnabled(offline and not segmenting)
        if not offline or segmenting:
            self.check_compress.setChecked(False)

    def _on_acq_type_change(self, *_args):
        self.disk_card.setVisible(self.radio_acq_disk.isChecked())
        self.file_card.setVisible(self.radio_acq_file.isChecked())
        self.logical_card.setVisible(self.radio_acq_logical.isChecked())

    def _get_block_size_mb(self):
        return int(self.combo_block_size.currentText().split()[0])

    def _get_segment_size_bytes(self):
        """None doner -- bolme yok, tek dosya (varsayilan)."""
        return self.combo_segment_size.currentData()

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
        self.status_label.setText(t("tool_status_waiting", self.lang))

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
        path, _ = QFileDialog.getOpenFileName(self, t("tool_dialog_ssh_key_select", self.lang), "", t("tool_filter_pem", self.lang))
        if path:
            self.entry_key.setText(path)

    def _browse_out(self):
        path, _ = QFileDialog.getSaveFileName(self, t("tool_dialog_save_image", self.lang), self.entry_out.text(), t("tool_filter_raw", self.lang))
        if path:
            self.entry_out.setText(path)

    def _browse_file_out(self):
        path = QFileDialog.getExistingDirectory(self, t("tool_dialog_output_folder", self.lang))
        if path:
            self.entry_file_out.setText(path)

    def _browse_logical_out(self):
        path = QFileDialog.getExistingDirectory(self, t("tool_dialog_output_folder", self.lang))
        if path:
            self.entry_logical_out.setText(path)

    def _browse_remote_path(self):
        """
        'Uzak Yol' icin native QFileDialog KULLANILAMAZ -- o hep BU
        bilgisayarin diskini gosterir, SSH ile baglanilan uzak hedefin
        dosya sistemini goremez. Bunun yerine RemoteBrowseDialog, mevcut
        SSH baglantisi (self.ssh) uzerinden salt-okunur find/Get-ChildItem
        ile gezinmeyi saglar.
        """
        if self.ssh is None:
            self._show_error(t("tool_err_connect_first_browse", self.lang))
            return
        target_os = "windows" if self.radio_os_windows.isChecked() else "linux"
        start_path = self.entry_remote_path.text().strip() or ("C:\\" if target_os == "windows" else "/")
        dialog = RemoteBrowseDialog(self.ssh, target_os, start_path, lang=self.lang, parent=self)
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

        yes_btn = widgets.PrimaryButton(t("btn_yes", self.lang))
        yes_btn.clicked.connect(_yes)
        no_btn = widgets.SecondaryButton(t("btn_no", self.lang))
        no_btn.clicked.connect(dialog.reject)
        btn_row.addWidget(yes_btn)
        btn_row.addWidget(no_btn)
        layout.addLayout(btn_row)
        dialog.exec()
        return result["value"]

    def _show_error(self, msg):
        dialog = QDialog(self)
        dialog.setWindowTitle(t("dialog_title_error", self.lang))
        dialog.setStyleSheet(f"background-color:{ui.BG_SURFACE};")
        layout = QVBoxLayout(dialog)
        lbl = QLabel(msg)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{ui.ERROR}; font-family:'{ui.FONT_UI}'; padding: 8px;")
        layout.addWidget(lbl)
        ok_btn = widgets.PrimaryButton(t("btn_ok", self.lang))
        ok_btn.clicked.connect(dialog.accept)
        layout.addWidget(ok_btn)
        dialog.exec()

    def _show_info(self, msg):
        dialog = QDialog(self)
        dialog.setWindowTitle(t("dialog_title_info", self.lang))
        dialog.setStyleSheet(f"background-color:{ui.BG_SURFACE};")
        layout = QVBoxLayout(dialog)
        lbl = QLabel(msg)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; padding: 8px;")
        layout.addWidget(lbl)
        ok_btn = widgets.PrimaryButton(t("btn_ok", self.lang))
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
            self._show_error(t("tool_err_host_user_required", self.lang))
            return

        self.btn_connect.setEnabled(False)
        self.btn_connect.setText(t("tool_btn_connecting", self.lang))
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
        self.btn_connect.setText(t("tool_btn_connect", self.lang))

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
        self._set_status(t("tool_status_connected_disks", self.lang))

    def _new_report_ctx(self):
        return {
            "case_id": self.entry_case_id.text().strip(),
            "examiner": self.entry_examiner.text().strip(),
            "custodian": self.entry_custodian.text().strip(),
            "organization": self.entry_organization.text().strip(),
            "case_notes": self.entry_case_notes.toPlainText().strip(),
            "conn_method": self.conn_method_value,
            "host": self.entry_host.text().strip(),
            "display_timezone": self._display_timezone,
        }

    # -- Imaj Alma ------------------------------------------------------
    def _start_acquisition(self):
        if self.ssh is None or not self.ssh.is_active():
            self._show_error(t("tool_err_connect_first", self.lang))
            return
        if self.radio_acq_disk.isChecked():
            if self.radio_os_windows.isChecked():
                self._start_disk_windows()
            else:
                self._start_disk_linux()
        elif self.radio_acq_logical.isChecked():
            self._start_file(logical=True)
        else:
            self._start_file()

    def _start_disk_windows(self):
        disk_str = self.entry_disk.text().strip()
        out_path = self.entry_out.text().strip()
        mode = "offline" if self.radio_offline.isChecked() else "live"
        if not disk_str:
            self._show_error(t("tool_err_disk_number_required", self.lang))
            return
        try:
            disk_number = int(disk_str)
        except ValueError:
            self._show_error(t("tool_err_disk_number_invalid", self.lang))
            return
        if not out_path:
            self._show_error(t("tool_err_output_path_required", self.lang))
            return
        if self._local_mode and not self._local_precheck(disk_number=disk_number, out_path=out_path):
            return

        compress = mode == "offline" and self.check_compress.isChecked()
        ctx = self._new_report_ctx()
        ctx.update(disk_number=disk_number, out_path=out_path, mode=mode, block_size_mb=self._get_block_size_mb(), compress=compress, segment_size_bytes=self._get_segment_size_bytes())
        self._begin_acquisition("windows_disk", ctx, f"MOD: {mode.upper()} | DISK: PhysicalDrive{disk_number} | ÇIKTI: {out_path}")

    def _start_disk_linux(self):
        disk = self.entry_disk.text().strip()
        out_path = self.entry_out.text().strip()
        mode = "offline" if self.radio_offline.isChecked() else "live"
        password = self.entry_pass.text().strip() or None
        if not disk:
            self._show_error(t("tool_err_disk_path_required", self.lang))
            return
        if not disk.startswith("/dev/"):
            disk = f"/dev/{disk}"
        if not out_path:
            self._show_error(t("tool_err_output_path_required", self.lang))
            return

        disk_name = disk.replace("/dev/", "")
        if getattr(self, "disks_raw", "") and disk_name not in self.disks_raw:
            if not self._show_yesno_dialog(t("tool_disk_not_listed_title", self.lang), t("tool_disk_not_listed_msg", self.lang, disk=disk_name)):
                return

        compress = mode == "offline" and self.check_compress.isChecked()
        ctx = self._new_report_ctx()
        ctx.update(disk=disk, out_path=out_path, mode=mode, password=password, block_size_mb=self._get_block_size_mb(), compress=compress, segment_size_bytes=self._get_segment_size_bytes())
        self._begin_acquisition("linux_disk", ctx, f"MOD: {mode.upper()} | DISK: {disk} | ÇIKTI: {out_path}")

    def _start_file(self, logical=False):
        """logical=True: mantiksal imaj (kok yol + cikti klasoru ayri alanlardan
        okunur, ayni worker kolu `logical` bayragiyla farkli motoru cagirir)."""
        if logical:
            remote_path = self.entry_logical_root.text().strip()
            out_dir = self.entry_logical_out.text().strip()
        else:
            remote_path = self.entry_remote_path.text().strip()
            out_dir = self.entry_file_out.text().strip()
        password = self.entry_pass.text().strip() or None
        if not remote_path:
            self._show_error(t("tool_err_remote_path_required", self.lang))
            return
        if not out_dir:
            self._show_error(t("tool_err_output_folder_required", self.lang))
            return
        if self._local_mode and not self._local_precheck(root_path=remote_path, out_path=out_dir):
            return

        ctx = self._new_report_ctx()
        ctx.update(
            remote_path=remote_path, out_dir=out_dir, password=password,
            target_os="windows" if self.radio_os_windows.isChecked() else "linux",
            logical=logical,
        )
        etiket = "MANTIKSAL İMAJ KÖKÜ" if logical else "UZAK YOL"
        self._begin_acquisition("file", ctx, f"{etiket}: {remote_path} | ÇIKTI: {out_dir}")

    def _begin_acquisition(self, kind, ctx, header_line):
        self.btn_acquire.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_stop.show()
        self._set_progress(0)
        self._set_status(t("tool_status_acquisition_starting", self.lang))
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
        self.acq_worker.finished.connect(self._on_acquisition_finished)
        self.acq_worker.start()

    def _on_acquisition_finished(self):
        self.btn_acquire.setEnabled(True)
        self.btn_stop.hide()

    def _stop_acquisition(self):
        """'Durdur' butonu -- su an islenmekte olan blok/dosya yarida
        kesilmez, worker bir sonraki uygun noktada temiz sekilde durur
        (bkz. AcquisitionWorker.request_stop). Yanlislikla tiklamaya
        karsi onay isteniyor -- bu, kismen alinmis bir imaji "iptal"
        degil "duraklat" olarak gormek gerektigini de hatirlatir."""
        if self.acq_worker is None:
            return
        if not self._show_yesno_dialog(t("tool_stop_confirm_title", self.lang), t("tool_stop_confirm_msg", self.lang)):
            return
        self.btn_stop.setEnabled(False)
        self.acq_worker.request_stop()

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
            t("tool_ask_verify_title", self.lang),
            t("tool_ask_verify_msg", self.lang),
        )
        if ans:
            # Bu, az once tamamlanan alma islemine ait dogrulama -- sonucu
            # (basarili/basarisiz) _last_report'a islemek icin rapor
            # nesnesini de birlikte gonderiyoruz (bkz. VerifyWorker).
            self._verify_image_with_path(image_path, report=self._last_report, report_path=self._last_report_path)

    # -- Imaj Dogrulama -----------------------------------------------------
    def _verify_image(self):
        path, _ = QFileDialog.getOpenFileName(self, t("tool_dialog_select_image", self.lang), "", t("tool_filter_raw", self.lang))
        if not path:
            return
        # Elle secilen keyfi bir dosya -- az onceki alma islemine ait
        # raporla ILISKILENDIRILMIYOR (yanlis rapora "dogrulandi" yazmamak
        # icin; sadece _on_ask_verify'daki otomatik akis rapor gunceller).
        self._verify_image_with_path(path)

    def _verify_image_with_path(self, path, report=None, report_path=None):
        dialog = QDialog(self)
        dialog.setWindowTitle(t("tool_verify_dialog_title", self.lang))
        dialog.setStyleSheet(f"background-color:{ui.BG_SURFACE};")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(t("tool_verify_expected_label", self.lang)))
        entry_hash = widgets.MonoInput()
        entry_hash.setFixedWidth(420)
        layout.addWidget(entry_hash)
        entry_hash.setFocus()

        result = {"hash": None}

        def on_ok():
            result["hash"] = entry_hash.text().strip()
            dialog.accept()

        btn_row = QHBoxLayout()
        ok_btn = widgets.PrimaryButton(t("btn_verify", self.lang))
        ok_btn.clicked.connect(on_ok)
        cancel_btn = widgets.SecondaryButton(t("btn_cancel", self.lang))
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
        self._show_info(t("tool_verify_ok_msg", self.lang))

    def _on_verify_mismatch(self, expected, actual):
        self._log("[HATA] Hash uyuşmazlığı!")
        self._log(f"  Beklenen: {expected}", "plain")
        self._log(f"  Gerçek  : {actual}", "plain")
        self._show_error(t("tool_verify_mismatch_msg", self.lang))

    def _on_verify_error(self, msg):
        self._log(f"[HATA] Doğrulama hatası: {msg}")
        self._show_error(t("tool_verify_error_fmt", self.lang, msg=msg))

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
        dialog.setWindowTitle(t("tool_report_dialog_title", self.lang))
        dialog.resize(480, 380)
        dialog.setStyleSheet(f"background-color:{ui.BG_DARKEST};")
        layout = QVBoxLayout(dialog)

        d = report.to_dict()
        basarili = d["result"]["status"] == "success"
        head = QLabel(t("tool_report_done", self.lang) if basarili else t("tool_report_status_fmt", self.lang, status=d['result']['status']))
        head.setStyleSheet(f"color:{ui.SUCCESS if basarili else ui.WARNING}; font-family:'{ui.FONT_UI}'; font-size:15px; font-weight:600;")
        layout.addWidget(head)

        image_hash = d["integrity"]["image_hash"] or ""
        md5_hash = d["integrity"]["md5_hash"] or ""
        sha1_hash = d["integrity"]["sha1_hash"] or ""
        satirlar = [
            (t("field_case_id", self.lang), d["case"]["case_id"] or "—"),
            (t("field_examiner", self.lang), d["case"]["examiner"] or "—"),
            (t("field_custodian", self.lang), d["case"]["custodian"] or "—"),
            (t("field_organization", self.lang), d["case"]["organization"] or "—"),
            (t("label_target", self.lang), d["acquisition"]["target_host"] or d["acquisition"]["source_identifier"] or "—"),
            (t("tool_conn_method_card", self.lang), d["acquisition"]["connection_method"] or "—"),
            ("SHA-256", (image_hash[:24] + "…") if image_hash else "—"),
            ("MD5", (md5_hash[:24] + "…") if md5_hash else "—"),
            ("SHA-1", (sha1_hash[:24] + "…") if sha1_hash else "—"),
            (t("label_result", self.lang), d["result"]["status"]),
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

        open_btn = widgets.PrimaryButton(t("btn_open_report_html", self.lang))
        open_btn.clicked.connect(_open_html)
        btns.addWidget(open_btn)

        # Agac gorunumu Dosya/Klasor ve Mantiksal Imaj'da MANIFEST'ten,
        # Tam Disk'te ise (pytsk3 varsa) HAM IMAJIN kendisinden kuruluyor
        # -- bkz. disk_tree.py. Segmentli (.001/.002) ve gzip'li imajlar
        # bu ilk surumde kapsam disi (disk_tree tek parcali ham imaj
        # varsayiyor), bu yuzden onlarda buton hic gorunmuyor.
        method = d["tool"]["method"]
        if method in ("file", "logical"):
            manifest_yolu = os.path.join(d["result"]["output_path"] or "", "manifest_files.json")
            if os.path.isfile(manifest_yolu):
                tree_btn = widgets.SecondaryButton(t("btn_view_tree", self.lang))
                tree_btn.clicked.connect(lambda: self._show_tree_dialog(manifest_yolu))
                btns.addWidget(tree_btn)
        elif method == "disk" and disk_tree is not None:
            imaj_yolu = d["result"]["output_path"] or ""
            segmentli = re.search(r"\.\d{3,}$", imaj_yolu) is not None
            if imaj_yolu and os.path.isfile(imaj_yolu) and not imaj_yolu.endswith(".gz") and not segmentli:
                tree_btn = widgets.SecondaryButton(t("btn_view_tree", self.lang))
                tree_btn.clicked.connect(lambda p=imaj_yolu: self._show_disk_tree_dialog(p))
                btns.addWidget(tree_btn)

        btns.addStretch()
        close_btn = widgets.SecondaryButton(t("btn_close", self.lang))
        close_btn.clicked.connect(dialog.close)
        btns.addWidget(close_btn)
        layout.addLayout(btns)
        dialog.exec()

    def _show_tree_dialog(self, manifest_yolu):
        """Alinan dosya/klasor agacini gosterir -- manifest_files.json'daki
        HEDEFTEKI orijinal yollardan kurulur (build_path_tree), cift
        tiklamada karsilik gelen YEREL dosya acilir. Hoca istegi (bkz.
        docs/roadmap.md)."""
        try:
            with open(manifest_yolu, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            self._show_error(t("tool_tree_load_error", self.lang, exc=exc))
            return

        acquired = manifest.get("acquired", [])
        yollar = [a["remote_path"] for a in acquired]
        yerel_karsilik = {a["remote_path"]: a["local_path"] for a in acquired}
        agac = build_path_tree(yollar)

        dialog = QDialog(self)
        dialog.setWindowTitle(t("tool_tree_dialog_title", self.lang))
        dialog.resize(520, 480)
        dialog.setStyleSheet(f"background-color:{ui.BG_DARKEST};")
        layout = QVBoxLayout(dialog)

        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setStyleSheet(f"""
            QTreeWidget {{ background-color:{ui.BG_LAYER2}; color:{ui.TEXT_MAIN};
                border:1px solid {ui.BORDER}; border-radius:{ui.RADIUS}px; }}
        """)

        def _doldur(ebeveyn, dugum):
            # klasorler once, sonra dosyalar -- ikisi de kendi icinde alfabetik
            # (list_remote_directory'deki sunum kuraliyla AYNI).
            for isim, deger in sorted(dugum.items(), key=lambda kv: (isinstance(kv[1], str), kv[0].lower())):
                oge = QTreeWidgetItem(ebeveyn, [isim])
                if isinstance(deger, dict):
                    oge.setIcon(0, icons.icon("folder", color=ui.ACCENT_TEXT, size=16))
                    _doldur(oge, deger)
                else:
                    oge.setIcon(0, icons.icon("file-text", size=16))
                    oge.setData(0, Qt.ItemDataRole.UserRole, yerel_karsilik.get(deger))

        # remote_root'un kendisi de paths'lerin BASINDA aynen geciyor (ör.
        # remote_root="/data", yollar "/data/sub/..." gibi) -- kok etiketi
        # olarak ayrica gosterildigi icin, agacta o segmentleri TEKRAR
        # dugum olarak eklemeyip dogrudan ALTINDAKI alt agaca iniyoruz;
        # yoksa "/data" hem kok etiketinde hem "data" diye bir alt dugumde
        # ikilenmis olurdu.
        remote_root = manifest.get("remote_root", "/")
        alt_agac = agac
        for parca in re.split(r"[\\/]+", remote_root):
            if not parca:
                continue
            if isinstance(alt_agac, dict) and isinstance(alt_agac.get(parca), dict):
                alt_agac = alt_agac[parca]
            else:
                alt_agac = agac  # beklenmedik durum -- tam agaci goster, veri kaybetme
                break

        kok_oge = QTreeWidgetItem(tree, [remote_root])
        kok_oge.setIcon(0, icons.icon("hard-drive", color=ui.ACCENT_TEXT, size=16))
        _doldur(kok_oge, alt_agac)
        kok_oge.setExpanded(True)

        def _cift_tikla(oge, _sutun):
            yerel = oge.data(0, Qt.ItemDataRole.UserRole)
            if yerel and os.path.exists(yerel):
                try:
                    os.startfile(yerel)
                except OSError as exc:
                    self._log(f"[UYARI] Dosya açılamadı: {exc}", "warn")

        tree.itemDoubleClicked.connect(_cift_tikla)
        layout.addWidget(tree)

        close_btn = widgets.SecondaryButton(t("btn_close", self.lang))
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)
        dialog.exec()

    def _show_disk_tree_dialog(self, image_path):
        """Tam Disk (ham blok) imajinda dosya sistemini pytsk3 ile
        ayristirip agac gosterir -- _show_tree_dialog'un aksine bir
        manifest'ten degil, DOGRUDAN imajin kendisinden kurulur (bkz.
        disk_tree.py). Birden fazla bolum (MBR/GPT) varsa her biri ayri
        bir kok dugum olarak gosterilir; bir bolum ayristirilamazsa (ör.
        taninmayan/bos dosya sistemi) SADECE o bolumde hata gosterilir,
        digerleri etkilenmez. Cift tiklamada dosya icerigi GECICI bir
        dosyaya cikarilip acilir -- imaj hicbir zaman yazilmiyor."""
        try:
            bolumler = disk_tree.open_disk_tree(image_path)
        except disk_tree.DiskTreeError as exc:
            self._show_error(t("tool_disk_tree_error_fmt", self.lang, exc=exc))
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(t("tool_tree_dialog_title", self.lang))
        dialog.resize(520, 480)
        dialog.setStyleSheet(f"background-color:{ui.BG_DARKEST};")
        layout = QVBoxLayout(dialog)

        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setStyleSheet(f"""
            QTreeWidget {{ background-color:{ui.BG_LAYER2}; color:{ui.TEXT_MAIN};
                border:1px solid {ui.BORDER}; border-radius:{ui.RADIUS}px; }}
        """)

        def _doldur(ebeveyn, dugum):
            # klasorler once, sonra dosyalar -- diger agac gorunumleriyle AYNI kural.
            for isim, deger in sorted(dugum.items(), key=lambda kv: (isinstance(kv[1], tuple), kv[0].lower())):
                oge = QTreeWidgetItem(ebeveyn, [isim])
                if isinstance(deger, dict):
                    oge.setIcon(0, icons.icon("folder", color=ui.ACCENT_TEXT, size=16))
                    _doldur(oge, deger)
                else:
                    inode, _boyut = deger
                    oge.setIcon(0, icons.icon("file-text", size=16))
                    oge.setData(0, Qt.ItemDataRole.UserRole, (bolum["offset"], inode, isim))

        for bolum in bolumler:
            etiket = bolum["description"] or t("tool_tree_whole_image", self.lang)
            kok_oge = QTreeWidgetItem(tree, [etiket])
            kok_oge.setIcon(0, icons.icon("hard-drive", color=ui.ACCENT_TEXT, size=16))
            if bolum["error"]:
                hata_oge = QTreeWidgetItem(kok_oge, [t("tool_tree_partition_error_fmt", self.lang, exc=bolum["error"])])
                hata_oge.setIcon(0, icons.icon("alert-triangle", color=ui.WARNING, size=16))
            else:
                _doldur(kok_oge, bolum["tree"])
            kok_oge.setExpanded(True)

        def _cift_tikla(oge, _sutun):
            veri = oge.data(0, Qt.ItemDataRole.UserRole)
            if not veri:
                return
            offset, inode, isim = veri
            # isim SANITIZE EDILMEDEN kullanilmaz -- bkz. _guvenli_onizleme_
            # dosya_adi docstring'i (path traversal, CWE-22).
            guvenli_ad = _guvenli_onizleme_dosya_adi(inode, isim)
            gecici_kok = tempfile.gettempdir()
            gecici_yol = os.path.join(gecici_kok, f"chameleon_onizleme_{guvenli_ad}")
            # Savunma derinligi: sanitize mantiginda ileride bir hata olsa
            # bile, nihai yol gercekten gecici klasorun ALTINDA kalmiyorsa
            # cikarma islemi YAPILMAZ.
            gercek_yol = os.path.realpath(gecici_yol)
            gercek_kok = os.path.realpath(gecici_kok)
            if gercek_yol != gercek_kok and not gercek_yol.startswith(gercek_kok + os.sep):
                self._log("[UYARI] Onizleme yolu gecici klasor disinda, cikarma iptal edildi.", "warn")
                return
            try:
                disk_tree.extract_file(image_path, offset, inode, gecici_yol)
                os.startfile(gecici_yol)
            except (OSError, disk_tree.DiskTreeError) as exc:
                self._log(f"[UYARI] Dosya çıkarılamadı: {exc}", "warn")

        tree.itemDoubleClicked.connect(_cift_tikla)
        layout.addWidget(tree)

        close_btn = widgets.SecondaryButton(t("btn_close", self.lang))
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)
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
    win.setWindowTitle(t("tool_ssh_title", "tr"))
    win.resize(1000, 820)
    win.setCentralWidget(ForensicWidget())
    win.show()
    sys.exit(app.exec())
