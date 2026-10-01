"""
ram_gui.py
RAM motoru arayuzu -- vendor'in kendi RamImagerGUI.exe'si (WinForms,
bizim temamizdan habersiz) yerine, RamImagerCLI.exe'yi dogrudan subprocess
ile cagiran, PySide6 ile yazilmis kendi arayuzumuz. Worker thread
(RamWorker) RamImagerCLI.exe cagrisini/ShellExecute yukseltmeyi/log
tail'lemeyi yurutup UI'ye Qt sinyalleriyle haber verir.

RamImagerCLI.exe/RamImagerDriver.sys kaynagi bizde yok (derlenmis hali
verildi), bu yuzden onlarin davranisini degistirmiyoruz -- sadece nasil
cagirdigimizi ve sonucu nasil gosterdigimizi degistiriyoruz.
"""

import csv
import ctypes
import hashlib
import io
import os
import subprocess
import sys
import time

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
    QMainWindow, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

RAM_ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
CLI_PATH = os.path.join(RAM_ENGINE_DIR, "cli", "RamImagerCLI.exe")
# Full RAM icin kullanilan arac (Velocidex WinPmem, Apache 2.0, degistirilmemis
# resmi surum -- bkz. winpmem/THIRD_PARTY_LICENSES.txt). Vendor'in
# RamImagerDriver.sys'i imzasiz oldugu icin Full modda calismiyordu (Error 577,
# gercek makinede dogrulandi); RamImagerCLI.exe SADECE Process Dump modunda
# kullaniliyor (o mod surucu gerektirmiyor).
WINPMEM_PATH = os.path.join(RAM_ENGINE_DIR, "winpmem", "go-winpmem_amd64_1.0-rc2_signed.exe")

_SHARED_DIR = os.path.join(RAM_ENGINE_DIR, "..", "..", "shared")
if os.path.isdir(_SHARED_DIR):
    sys.path.insert(0, _SHARED_DIR)
_I18N_DIR = os.path.join(_SHARED_DIR, "i18n")
if os.path.isdir(_I18N_DIR):
    sys.path.insert(0, _I18N_DIR)
from ui_kit import theme_qt as ui, fonts, icons, widgets  # noqa: E402
from help_content import get_topic  # noqa: E402
from strings import t  # noqa: E402

try:
    from forensic_report import ForensicReport
except ImportError:
    ForensicReport = None

try:
    import incomplete_ops
except ImportError:
    incomplete_ops = None

_COC_DIR = os.path.join(RAM_ENGINE_DIR, "..", "ssh_engine", "local_collector")
if os.path.isdir(_COC_DIR):
    sys.path.insert(0, _COC_DIR)
try:
    import chain_of_custody as coc
except ImportError:
    coc = None
try:
    from hash_verifier import hash_file_multi
except ImportError:
    hash_file_multi = None


def list_processes():
    """AYNEN tasindi (ram_gui.py) -- tasklist ile calisan process listesi."""
    try:
        out = subprocess.check_output(
            ["tasklist", "/fo", "csv", "/nh"],
            text=True, encoding="oem", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        return []
    sonuc = []
    for row in csv.reader(io.StringIO(out)):
        if len(row) >= 2 and row[1].isdigit():
            sonuc.append((row[0], row[1]))
    return sorted(sonuc, key=lambda x: x[0].lower())


def build_winpmem_elevate_params(args, log_path):
    """
    ShellExecuteW ile 'cmd.exe'yi 'runas' verbiyle yukseltmek icin parametre
    metni. Full RAM araci kendi log dosyasini yazmiyor ve yukseltilmis
    surecin stdout'u ana surece aktarilamiyor (bkz. RamWorker._run_full_mode_winpmem
    docstring'i) -- bu yuzden ciktiyi 'cmd /c' ile log_path'e yonlendiriyoruz.

    cmd.exe'nin bilinen kurali: /c'den sonraki metnin ILK ve SON karakteri
    tirnaksa bu DIS ciftini siler -- komut zaten kendi ic tirnaklarini
    tasiyorsa (list2cmdline exe yolunu tirnaklar) bu, ic tirnaklardan birini
    yanlislikla disari tasir ve yolu bozar. Duzeltme: butun metni bir kat
    daha tirnak icine alip cmd'nin silecegi disari fazladan bir kat eklemek --
    standart, belgelenmis is-around.

    Sonunda basarili/basarisiz FARK ETMEKSIZIN surec bitince yazilan bir
    CHAMELEON_DONE isareti eklenir -- tail donguesu boylece WinPmem'in
    KENDI "Completed imaging" satirini beklemek yerine surecin GERCEKTEN
    bittigini (hata ile de olsa) kesin bilir, 3600 saniyelik zaman asimini
    beklemek zorunda kalmaz.
    """
    komut = subprocess.list2cmdline(args)
    yonlendirilmis = f'{komut} > "{log_path}" 2>&1 & echo CHAMELEON_DONE>>"{log_path}"'
    return f'/c "{yonlendirilmis}"'


def winpmem_log_finished(log_text):
    """cmd /c zinciri (basarili ya da basarisiz) bittiginde True doner."""
    return "CHAMELEON_DONE" in log_text


def format_duration_tr(seconds):
    """Saniyeyi kisa bir TR sure metnine cevirir (45 sn / 2 dk 10 sn / 1 sa 5 dk)."""
    saniye = max(0, int(seconds))
    if saniye < 60:
        return f"{saniye} sn"
    dakika, saniye = divmod(saniye, 60)
    if dakika < 60:
        return f"{dakika} dk {saniye} sn" if saniye else f"{dakika} dk"
    saat, dakika = divmod(dakika, 60)
    return f"{saat} sa {dakika} dk"


def winpmem_log_succeeded(log_text):
    """WinPmem'in kendi bastigi basari satirini arar (bkz. gercek makinede
    dogrulanan cikti: 'Completed imaging in ...')."""
    return "Completed imaging" in log_text


class ProcessListWorker(QThread):
    ready = Signal(list)

    def run(self):
        self.ready.emit(list_processes())


class RamWorker(QThread):
    """
    _run_process_mode/_run_full_mode_winpmem'in calistigi yer. Widget'lara
    dogrudan dokunmak yerine sinyal yayar (thread-guvenli Qt koprusu).
    """
    log = Signal(str)
    status = Signal(str, str)  # (metin, renk_hex)
    report_ready = Signal(object, str)  # (ForensicReport, report_path)

    def __init__(self, mode, args, out_path, case, examiner, custodian, organization="",
                 case_notes="", display_timezone=None, process_label=None, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.args = args
        self.out_path = out_path
        self.case = case
        self.examiner = examiner
        self.custodian = custodian
        self.organization = organization
        self.case_notes = case_notes
        self.display_timezone = display_timezone
        self.process_label = process_label
        self._hash_started_at = None
        self._hash_last_emit = 0.0

    def run(self):
        if self.mode == "process":
            self._run_process_mode()
        else:
            self._run_full_mode_winpmem()

    def _new_report(self, method, source_identifier):
        if ForensicReport is None:
            return None
        report = ForensicReport(
            case_id=self.case, examiner=self.examiner, custodian=self.custodian,
            organization=self.organization, case_notes=self.case_notes,
            display_timezone=self.display_timezone,
        )
        report.start(
            engine="ram_engine", method=method, target_os="windows", target_host="localhost",
            source_identifier=source_identifier,
        )
        report.set_write_blocking(False, "RAM imajlama icin write-blocking kavrami gecerli degil")
        return report

    def _emit_hash_progress(self, islenen, toplam):
        """hash_file_multi'nin progress callback'i -- kalan sureyi SABIT bir
        tahmin yerine O ANKI OLCULEN gercek hiza gore hesaplar, boylece RAM
        boyutuna ve donanima (disk/CPU hizi) otomatik uyar. Sinyal trafigini
        bogmamak icin en fazla saniyede bir guncellenir."""
        simdi = time.monotonic()
        if self._hash_started_at is None:
            self._hash_started_at = simdi
        if simdi - self._hash_last_emit < 1.0 and islenen < toplam:
            return
        self._hash_last_emit = simdi
        yuzde = (islenen * 100 / toplam) if toplam else 0
        gecen = simdi - self._hash_started_at
        if islenen > 0 and gecen > 0.5:
            hiz = islenen / gecen
            kalan_sn = (toplam - islenen) / hiz if hiz > 0 else 0
            self.status.emit(
                f"Doğrulanıyor (hash hesaplanıyor)... %{yuzde:.0f}, tahmini kalan: {format_duration_tr(kalan_sn)}", None,
            )
        else:
            self.status.emit(f"Doğrulanıyor (hash hesaplanıyor)... %{yuzde:.0f}", None)

    def _save_report(self, report, output_dir):
        if report is None:
            return None
        try:
            path = report.save(output_dir)
            self.log.emit(f"Rapor: {path}")
            return path
        except OSError as exc:
            self.log.emit(f"[UYARI] Rapor yazilamadi: {exc}")
            return None

    def _run_process_mode(self):
        """AYNEN tasindi -- process modu yukseltme gerektirmedigi icin
        stdout dogrudan okunabilir. RamImagerCLI process modunda hash
        uretmiyor, dosyayi kendimiz hashliyoruz."""
        args, out_path, process_label = self.args, self.out_path, self.process_label
        report = self._new_report("ram_process", process_label)
        if coc:
            coc.log_event(coc.EVENT_EXAM_START, f"RAM process dump baslatildi: {process_label}")

        # "Yarim Kalanlar" listesi icin -- gercek resume degil (bir process
        # dump kaldigi yerden devam edemez), sadece "basladi, bitirmedi"
        # kaydi. Uygulama/surec BITMEDEN once kapanirsa bu kayit silinmez,
        # launcher acilista yarim kalmis olarak gorur (bkz. incomplete_ops.py).
        op_id = None
        if incomplete_ops:
            op_id = incomplete_ops.record_start(
                "ram_process", process_label,
                details={
                    "case_id": self.case, "examiner": self.examiner,
                    "custodian": self.custodian, "organization": self.organization,
                    "out_path": out_path,
                },
            )

        try:
            self.log.emit(f"$ {' '.join(args)}")
            proc = None  # Popen'in kendisi OSError fırlatırsa proc atanmamış kalmasın
            try:
                proc = subprocess.Popen(
                    args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, creationflags=subprocess.CREATE_NO_WINDOW,
                )
                for line in proc.stdout:
                    self.log.emit(line.rstrip("\n"))
                exit_code = proc.wait()
            except OSError as exc:
                self.log.emit(f"Başlatılamadı: {exc}")
                # Süreç başladıysa (okuma sırasında hata olduysa) bekleyip
                # zombi kalmasını engelle; Popen başarısızsa beklenecek süreç yok.
                if proc is not None:
                    try:
                        proc.wait(timeout=5)
                    except Exception:
                        pass
                exit_code = -1

            if exit_code == 0 and os.path.exists(out_path):
                self.status.emit("Tamamlandı.", ui.SUCCESS)
                if coc:
                    coc.log_event(coc.EVENT_EXAM_END, f"RAM process dump tamamlandi: {out_path}")
                if report:
                    dosya_hash = None
                    md5_hash = None
                    sha1_hash = None
                    try:
                        with open(out_path, "rb") as f:
                            veri = f.read()
                        # Dosya zaten SHA-256 icin TAMAMEN belleğe okundu --
                        # MD5/SHA-1'i de AYNI veri uzerinden hesaplamak
                        # ekstra I/O gerektirmiyor (bkz. forensic_report.
                        # finish()'teki AYNI gerekce, docs/hatalar_ve_sonuclar.md).
                        dosya_hash = hashlib.sha256(veri).hexdigest()
                        md5_hash = hashlib.md5(veri).hexdigest()
                        sha1_hash = hashlib.sha1(veri).hexdigest()
                    except OSError:
                        pass
                    except ValueError:
                        pass  # FIPS -- bkz. forensic_report.py'deki AYNI gerekce
                    report.finish(
                        status="success", output_path=out_path, image_hash=dosya_hash,
                        total_bytes=os.path.getsize(out_path) if os.path.exists(out_path) else None,
                        md5_hash=md5_hash, sha1_hash=sha1_hash,
                    )
                    rapor_yolu = self._save_report(report, os.path.dirname(out_path) or ".")
                    self.report_ready.emit(report, rapor_yolu)
            else:
                self.status.emit(f"Başarısız (kod {exit_code}).", ui.ERROR)
                if coc:
                    coc.log_event(coc.EVENT_EXAM_ERROR, f"RAM process dump basarisiz (kod {exit_code}): {process_label}")
                if report:
                    report.finish(status="failed", output_path=out_path)
                    self._save_report(report, os.path.dirname(out_path) or ".")
        finally:
            if incomplete_ops and op_id:
                incomplete_ops.record_finish(op_id)

    def _run_full_mode_winpmem(self):
        """Full RAM -- Yonetici (UAC) gerektirir; ShellExecuteW 'runas' ile
        yukseltilmis 'cmd.exe' cagrilir, cikti 'cmd /c' ile log_path'e
        yonlendirilir (bkz. build_winpmem_elevate_params) -- yukseltilmis
        surecin stdout'u ana surece dogrudan aktarilamiyor. Gercek makinede
        dogrulandi (bkz. docs/roadmap.md): kullanilan surucu imzali oldugu
        icin test-signing/Secure Boot degisikligi GEREKMIYOR, sadece o anki
        UAC onayi yeterli. Pencere gizli (SW_HIDE) baslatilir -- ilerleme
        zaten uygulamanin kendi gunluk paneline aktariliyor, ayri bir konsol
        penceresine gerek yok."""
        args, out_path = self.args, self.out_path
        log_path = out_path + ".log"
        try:
            if os.path.exists(log_path):
                os.remove(log_path)
        except OSError:
            pass

        self.log.emit(f"$ {' '.join(args)} (Yönetici olarak, UAC istemi gelecek)")
        try:
            params = build_winpmem_elevate_params(args, log_path)
            result = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", params, None, 0)
            if result <= 32:
                msg = f"Yükseltme başarısız (kod {result}) -- UAC reddedildi olabilir."
                self.log.emit(msg)
                self.status.emit("Başlatılamadı / UAC reddedildi.", ui.ERROR)
                if coc:
                    coc.log_event(coc.EVENT_EXAM_ERROR, msg)
                return
        except Exception as exc:
            self.log.emit(f"Başlatılamadı: {exc}")
            self.status.emit("Başlatılamadı.", ui.ERROR)
            return

        self._tail_log_winpmem(log_path, out_path)

    def _tail_log_winpmem(self, log_path, out_path):
        """_tail_log ile AYNI desen, iki fark: (1) bitis isareti vendor'in
        .json'u degil CHAMELEON_DONE isareti (hem basari hem hata icin --
        WinPmem'in kendi basari satiri ayrica aranir); (2) vendor'in hazir
        hash'i olmadigi icin imaj bitince SHA-256/MD5/SHA-1 kendimiz
        hesaplaniyor (_run_process_mode'daki AYNI gerekce)."""
        if coc:
            coc.log_event(coc.EVENT_EXAM_START, f"RAM full imaj (WinPmem) baslatildi: {out_path}")

        op_id = None
        if incomplete_ops:
            op_id = incomplete_ops.record_start(
                "ram_full", "PhysicalMemory (full, WinPmem)",
                details={
                    "case_id": self.case, "examiner": self.examiner,
                    "custodian": self.custodian, "organization": self.organization,
                    "out_path": out_path,
                },
            )

        last_size = 0
        waited = 0
        tam_log = ""
        has_log = False  # log_path hiç oluşmadı mı?
        while waited < 3600:  # full RAM uzun surebilir, 1 saate kadar bekle
            time.sleep(1)
            waited += 1
            if os.path.exists(log_path):
                has_log = True
                try:
                    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(last_size)
                        yeni = f.read()
                        last_size = f.tell()
                    if yeni:
                        self.log.emit(yeni.rstrip("\n"))
                        tam_log += yeni
                except OSError:
                    pass
            if winpmem_log_finished(tam_log):
                break
            # log_path hiç oluşmadı ve 30 sn geçti -- ShellExecute başarısız (UAC reddedildi vb.)
            if waited >= 30 and not has_log:
                self.status.emit("Log dosyası oluşmadı, yükseltme başarısız olabilir.", ui.ERROR)
                if coc:
                    coc.log_event(coc.EVENT_EXAM_ERROR, f"RAM full imaj (WinPmem) log dosyası oluşmadı: {log_path}")
                break

        basarili = winpmem_log_succeeded(tam_log) and os.path.exists(out_path)
        report = self._new_report("ram_full_winpmem", "PhysicalMemory (full, WinPmem)")

        if basarili:
            # "Tamamlandı" BURADA degil, asagida (hash+rapor GERCEKTEN
            # bitince) yaziliyor -- 26+ GB'lik bir imajda SHA-256/MD5/SHA-1
            # hesaplamasi dakikalar surebilir; "Tamamlandı" ONCEDEN yazilirsa
            # ilerleme cubugu (haklı olarak) donmeye devam ederken ekran
            # "bitti" diyor, kullanici bunu hata saniyor (bkz. docs/roadmap.md).
            self.status.emit("Doğrulanıyor (hash hesaplanıyor)... (süre RAM boyutuna ve donanıma göre değişir)", None)
            image_hash = md5_hash = sha1_hash = None
            if hash_file_multi and os.path.isfile(out_path):
                try:
                    hashler = hash_file_multi(out_path, progress=self._emit_hash_progress)
                    image_hash = hashler.get("sha256")
                    md5_hash = hashler.get("md5")
                    sha1_hash = hashler.get("sha1")
                except (OSError, ValueError):
                    pass
            if coc:
                coc.log_event(coc.EVENT_EXAM_END, f"RAM full imaj (WinPmem) tamamlandi: {out_path}", image_hash)
            if report:
                report.finish(
                    status="success", output_path=out_path, image_hash=image_hash,
                    total_bytes=os.path.getsize(out_path) if os.path.exists(out_path) else None,
                    md5_hash=md5_hash, sha1_hash=sha1_hash,
                )
                rapor_yolu = self._save_report(report, os.path.dirname(out_path) or ".")
                self.report_ready.emit(report, rapor_yolu)
            if incomplete_ops and op_id:
                incomplete_ops.record_finish(op_id)
            self.status.emit("Tamamlandı.", ui.SUCCESS)
        else:
            self.status.emit("Bitmedi ya da hata oluştu, günlüğe bakın.", ui.ERROR)
            if coc:
                coc.log_event(coc.EVENT_EXAM_ERROR, f"RAM full imaj (WinPmem) basarisiz/tamamlanamadi: {out_path}")
            if report:
                report.finish(status="failed", output_path=out_path)
                self._save_report(report, os.path.dirname(out_path) or ".")
            # bkz. _tail_log'daki AYNI gerekce -- kayit "acik" kalir.


class RamEngineWidget(QWidget):
    def __init__(self, on_back=None, on_show_help=None, initial_case_id="", initial_examiner="",
                 initial_custodian="", initial_organization="", initial_case_notes="",
                 display_timezone=None, lang="tr", parent=None):
        super().__init__(parent)
        self.on_back = on_back
        # bkz. gui_v2.py'deki ForensicWidget.on_show_help -- ayni desen:
        # launcher icinden aciliyorsa Bilgi Merkezi sayfasina goturur,
        # standalone calistirmada None kalir (dialog fallback kullanilir).
        self.on_show_help = on_show_help
        self.lang = lang or "tr"
        self._pid_map = {}
        self.worker = None
        # launcher'in chameleon_gui._widget_should_persist'i okuyor -- None
        # iken (hic islem bitmemisken) ekran "Geri" ile Ana Sayfa'ya
        # gidilince SILINMIYOR, doldurulmus alanlar kaybolmuyor. gui_v2.py'
        # deki _last_report ile AYNI desen/isim, bkz. o dosyadaki aciklama.
        self._last_report = None
        self._display_timezone = display_timezone
        self._build_ui(initial_case_id, initial_examiner, initial_custodian, initial_organization, initial_case_notes)
        self._refresh_processes()

    # -- UI ------------------------------------------------------------
    def _build_ui(self, initial_case_id, initial_examiner, initial_custodian, initial_organization="", initial_case_notes=""):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(20, 14, 20, 14)
        if self.on_back:
            back_btn = widgets.SecondaryButton(t("btn_back", self.lang))
            back_btn.clicked.connect(self.on_back)
            header.addWidget(back_btn)
        title = QLabel(t("tool_ram_title", self.lang))
        title.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_TITLE}px; font-weight:600;")
        header.addWidget(title)
        header.addStretch()
        header_w = QWidget()
        header_w.setLayout(header)
        header_w.setStyleSheet(f"background-color:{ui.BG_SURFACE}; border-bottom:1px solid {ui.BORDER};")
        outer.addWidget(header_w)

        # Icerik (kartlar + gunluk) kaydirilabilir bir alana sarilir --
        # bu sarmalayici PySide6 gecisinde eksik kalmisti (gui_v2.py'deki
        # ayni deseni burada da uyguluyoruz): Vaka Bilgileri/Mod/Full RAM
        # kartlari eklenince toplam icerik pencere boyunu asiyordu ve
        # kaydirma HICBIR sekilde mumkun degildi -- alttaki kartlara/
        # Baslat butonuna hic erisilemiyordu (kullanici bildirdi).
        from PySide6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(ui.CARD_GAP)
        scroll.setWidget(inner)
        outer.addWidget(scroll, stretch=1)

        # === Vaka Bilgileri ===
        # launcher icinden acilirken (on_back doluysa) vaka bilgileri zaten
        # ayri bir on-ekranda (chameleon_gui.py._show_case_info) bir kez
        # toplanip initial_* olarak buraya geciriliyor -- kart burada TEKRAR
        # gosterilirse ayni alanlar iki kez sorulmus gibi kafa karistiriyordu
        # (kullanici bildirdi). Alanlar (entry_case vb.) worker'in okuyabilmesi
        # icin yine olusturuluyor, sadece ekranda GORUNMUYOR. Standalone
        # calistirmada (on_back yok, ayri bir on-ekran da yok) kart gorunur
        # kalir -- tek vaka bilgisi girisi orasi.
        vaka = widgets.Card(t("case_info_title", self.lang))
        vaka.body.addWidget(self._note(t("case_info_note", self.lang)))
        self.entry_case = self._labeled_input(vaka.body, t("field_case_id", self.lang), initial_case_id)
        self.entry_examiner = self._labeled_input(vaka.body, t("field_examiner", self.lang), initial_examiner)
        self.entry_custodian = self._labeled_input(vaka.body, t("field_custodian", self.lang), initial_custodian)
        self.entry_organization = self._labeled_input(vaka.body, t("field_organization", self.lang), initial_organization)
        notes_lbl = QLabel(f"{t('field_case_notes', self.lang)}:")
        notes_lbl.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_BODY}px;")
        vaka.body.addWidget(notes_lbl)
        self.entry_case_notes = QPlainTextEdit()
        self.entry_case_notes.setPlainText(initial_case_notes)
        self.entry_case_notes.setFixedHeight(60)
        vaka.body.addWidget(self.entry_case_notes)
        if self.on_back:
            vaka.hide()
        layout.addWidget(vaka)

        # === Mod secimi ===
        mode_card = widgets.Card(t("tool_mode_card", self.lang))
        mode_row = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.radio_process = widgets.RadioButton(t("tool_ram_process_radio", self.lang))
        self.radio_full = widgets.RadioButton(t("tool_ram_full_radio", self.lang))
        self.radio_process.setChecked(True)
        for r in (self.radio_process, self.radio_full):
            self.mode_group.addButton(r)
            mode_row.addWidget(r)
        mode_row.addStretch()
        mode_card.body.addLayout(mode_row)
        self.radio_process.toggled.connect(self._on_mode_change)
        layout.addWidget(mode_card)

        # === Process modu alanlari ===
        self.process_card = widgets.Card(t("tool_process_card", self.lang))
        proc_row = QHBoxLayout()
        proc_row.addWidget(QLabel(t("tool_process_label", self.lang)))
        self.process_combo = QComboBox()
        self.process_combo.setMinimumWidth(340)
        self.process_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {ui.BG_LAYER2}; color: {ui.TEXT_MAIN};
                border: 1px solid {ui.BORDER}; border-radius: {ui.RADIUS}px; padding: 4px 8px;
            }}
        """)
        proc_row.addWidget(self.process_combo)
        refresh_btn = widgets.SecondaryButton(t("btn_refresh", self.lang))
        refresh_btn.clicked.connect(self._refresh_processes)
        proc_row.addWidget(refresh_btn)
        proc_row.addStretch()
        self.process_card.body.addLayout(proc_row)
        layout.addWidget(self.process_card)

        # === Full mod alanlari ===
        self.full_card = widgets.Card(t("tool_full_card", self.lang))
        warn = QLabel(t("tool_full_warn", self.lang))
        warn.setWordWrap(True)
        warn.setStyleSheet(f"color:{ui.ERROR}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        self.full_card.body.addWidget(warn)
        self.full_card.body.addWidget(self._help_link("ram_full_mode_driver"))

        layout.addWidget(self.full_card)
        self.full_card.hide()

        # === Cikti ===
        out_card = widgets.Card(t("tool_output_card", self.lang))
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel(t("tool_file_label", self.lang)))
        self.entry_out = widgets.MonoInput()
        default_out = os.path.join(os.environ.get("TEMP", "."), "ram_dump.dmp")
        self.entry_out.setText(default_out)
        out_row.addWidget(self.entry_out, stretch=1)
        browse_btn = widgets.SecondaryButton(t("btn_browse", self.lang))
        browse_btn.clicked.connect(self._browse_out)
        out_row.addWidget(browse_btn)
        out_card.body.addLayout(out_row)
        layout.addWidget(out_card)

        # === Baslat + durum + ilerleme ===
        start_row = QHBoxLayout()
        self.btn_start = widgets.PrimaryButton(t("btn_start", self.lang))
        self.btn_start.clicked.connect(self._start)
        start_row.addWidget(self.btn_start)
        self.status_label = QLabel(t("tool_ready_status", self.lang))
        self.status_label.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        start_row.addWidget(self.status_label)
        start_row.addStretch()
        layout.addLayout(start_row)

        self.progress = widgets.ProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)

        # === Gunluk ===
        log_card = widgets.Card(t("tool_ram_log_card", self.lang))
        log_card.body.addWidget(self._help_link("chain_of_custody", t("tool_help_link_coc", self.lang)))
        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMinimumHeight(200)
        self.txt_log.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: #0A0E14; color: {ui.TEXT_MAIN};
                font-family: "{ui.FONT_MONO}"; font-size: 11px;
                border: 1px solid {ui.BORDER}; border-radius: {ui.RADIUS}px;
            }}
        """)
        log_card.body.addWidget(self.txt_log)
        layout.addWidget(log_card, stretch=1)

        self._on_mode_change()

    def _note(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px; font-style: italic;")
        return lbl

    def _help_link(self, topic_key, label=None):
        """Bilgi Merkezi'ndeki bir konuya goturen, mavi metin gorunumlu
        kucuk bir buton -- bkz. gui_v2.py'deki ForensicWidget._help_link
        (ayni desen, iki dosya birbirinden bagimsiz calisabildigi icin
        kod tekrarlanir)."""
        if label is None:
            label = t("btn_read_in_help_center", self.lang)
        btn = QPushButton(label)
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ color:{ui.ACCENT_TEXT}; background:transparent; border:none; "
            f"text-align:left; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px; "
            f"padding:2px 0; }} QPushButton:hover {{ color:{ui.ACCENT_HOVER}; }}"
        )
        btn.clicked.connect(lambda: self._show_help_topic(topic_key))
        return btn

    def _show_help_topic(self, topic_key):
        """bkz. gui_v2.py'deki ForensicWidget._show_help_topic -- ayni
        mantik: launcher icinden aciliyorsa Bilgi Merkezi sayfasina
        goturur, standalone calistirmada kucuk bir dialogda gosterir."""
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

    def _labeled_input(self, body_layout, label_text, initial_value):
        row = QHBoxLayout()
        lbl = QLabel(f"{label_text}:")
        lbl.setFixedWidth(180)
        lbl.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_BODY}px;")
        row.addWidget(lbl)
        entry = widgets.Input()
        entry.setText(initial_value)
        row.addWidget(entry)
        row.addStretch()
        body_layout.addLayout(row)
        return entry

    # -- Yardimci --------------------------------------------------------
    def _log(self, msg):
        self.txt_log.appendPlainText(msg)

    def _set_status(self, text, color=None):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            f"color:{color or ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;"
        )

    def _on_mode_change(self):
        if self.radio_process.isChecked():
            self.process_card.show()
            self.full_card.hide()
        else:
            self.full_card.show()
            self.process_card.hide()

    def _refresh_processes(self):
        self._proc_worker = ProcessListWorker(self)
        self._proc_worker.ready.connect(self._on_processes_ready)
        self._proc_worker.start()

    def _on_processes_ready(self, islemler):
        self._pid_map = {f"{ad} (PID {pid})": pid for ad, pid in islemler}
        self.process_combo.clear()
        self.process_combo.addItems(list(self._pid_map.keys()))

    def _browse_out(self):
        ext = ".dmp" if self.radio_process.isChecked() else ".img"
        path, _ = QFileDialog.getSaveFileName(
            self, t("tool_dialog_select_output_file", self.lang), self.entry_out.text(),
            f"{t('tool_file_type_fmt', self.lang, ext=ext[1:].upper())} (*{ext});;{t('tool_filter_all_files', self.lang)}",
        )
        if path:
            self.entry_out.setText(path)

    # -- Calistirma --------------------------------------------------------
    def _start(self):
        if self.radio_process.isChecked():
            if not os.path.isfile(CLI_PATH):
                self._set_status(t("tool_cli_not_found", self.lang, path=CLI_PATH), ui.ERROR)
                return
        elif not os.path.isfile(WINPMEM_PATH):
            self._set_status(t("tool_full_tool_not_found", self.lang, path=WINPMEM_PATH), ui.ERROR)
            return

        out_path = self.entry_out.text().strip()
        if not out_path:
            self._set_status(t("tool_select_output_file", self.lang), ui.ERROR)
            return

        case = self.entry_case.text().strip()
        examiner = self.entry_examiner.text().strip()
        custodian = self.entry_custodian.text().strip()
        organization = self.entry_organization.text().strip()
        case_notes = self.entry_case_notes.toPlainText().strip()

        self.btn_start.setEnabled(False)
        self._set_status(t("tool_running_status", self.lang))
        self.progress.show()
        self.progress.set_indeterminate()

        if self.radio_process.isChecked():
            secim = self.process_combo.currentText()
            pid = self._pid_map.get(secim)
            if not pid:
                self._set_status(t("tool_select_process", self.lang), ui.ERROR)
                self.btn_start.setEnabled(True)
                self.progress.hide()
                return
            args = [CLI_PATH, "process", "--pid", pid, "--output", out_path]
            self.worker = RamWorker(
                "process", args, out_path, case, examiner, custodian,
                organization=organization, case_notes=case_notes,
                display_timezone=self._display_timezone, process_label=secim,
            )
        else:
            args = [WINPMEM_PATH, "acquire", out_path]
            self.worker = RamWorker(
                "full", args, out_path, case, examiner, custodian,
                organization=organization, case_notes=case_notes,
                display_timezone=self._display_timezone,
            )

        self.worker.log.connect(self._log)
        self.worker.status.connect(self._set_status)
        self.worker.report_ready.connect(self._show_report_summary)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_worker_finished(self):
        self.btn_start.setEnabled(True)
        self.progress.hide()

    def _show_report_summary(self, report, report_path):
        """gui_v2.py'deki ile ayni desen -- islem bitince delil zinciri
        raporunu ozet olarak sunar, tam hali (report.html) icin buton verir."""
        if report is None or report_path is None:
            return
        # bkz. self._last_report aciklamasi (__init__) -- bir rapor
        # URETILDI, ekran artik "bitmis" sayilir.
        self._last_report = report

        html_path = os.path.splitext(report_path)[0] + ".html"

        dialog = QDialog(self)
        dialog.setWindowTitle(t("tool_report_dialog_title", self.lang))
        dialog.resize(480, 340)
        dialog.setStyleSheet(f"background-color:{ui.BG_DARKEST};")
        layout = QVBoxLayout(dialog)

        d = report.to_dict()
        basarili = d["result"]["status"] == "success"
        head = QLabel(t("tool_report_done", self.lang) if basarili else t("tool_report_status_fmt", self.lang, status=d['result']['status']))
        head.setStyleSheet(
            f"color:{ui.SUCCESS if basarili else ui.ERROR}; font-family:'{ui.FONT_UI}'; "
            f"font-size:15px; font-weight:600;"
        )
        layout.addWidget(head)

        image_hash = d["integrity"]["image_hash"] or ""
        md5_hash = d["integrity"]["md5_hash"] or ""
        sha1_hash = d["integrity"]["sha1_hash"] or ""
        satirlar = [
            (t("field_case_id", self.lang), d["case"]["case_id"] or "—"),
            (t("field_examiner", self.lang), d["case"]["examiner"] or "—"),
            (t("field_custodian", self.lang), d["case"]["custodian"] or "—"),
            (t("field_organization", self.lang), d["case"]["organization"] or "—"),
            (t("label_source", self.lang), d["acquisition"]["source_identifier"] or "—"),
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
                self._log(f"[UYARI] Rapor açılamadı: {e}")

        open_btn = widgets.PrimaryButton(t("btn_open_report_html", self.lang))
        open_btn.clicked.connect(_open_html)
        btns.addWidget(open_btn)
        btns.addStretch()
        close_btn = widgets.SecondaryButton(t("btn_close", self.lang))
        close_btn.clicked.connect(dialog.close)
        btns.addWidget(close_btn)
        layout.addLayout(btns)

        dialog.exec()


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    fonts.register_fonts()
    app.setStyleSheet(ui.base_stylesheet())

    win = QMainWindow()
    win.setWindowTitle(t("tool_ram_title", "tr"))
    win.resize(820, 720)
    win.setCentralWidget(RamEngineWidget())
    win.show()
    sys.exit(app.exec())
