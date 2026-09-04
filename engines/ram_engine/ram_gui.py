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
import json
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
DRIVER_PATH = os.path.join(RAM_ENGINE_DIR, "driver", "RamImagerDriver.sys")

_SHARED_DIR = os.path.join(RAM_ENGINE_DIR, "..", "..", "shared")
if os.path.isdir(_SHARED_DIR):
    sys.path.insert(0, _SHARED_DIR)
from ui_kit import theme_qt as ui, fonts, icons, widgets  # noqa: E402
from help_content import get_topic  # noqa: E402

try:
    from forensic_report import ForensicReport
except ImportError:
    ForensicReport = None

_COC_DIR = os.path.join(RAM_ENGINE_DIR, "..", "ssh_engine", "local_collector")
if os.path.isdir(_COC_DIR):
    sys.path.insert(0, _COC_DIR)
try:
    import chain_of_custody as coc
except ImportError:
    coc = None


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


class ProcessListWorker(QThread):
    ready = Signal(list)

    def run(self):
        self.ready.emit(list_processes())


class RamWorker(QThread):
    """
    _run_process_mode/_run_full_mode/_tail_log'un tasindigi yer. Govdeler
    ram_gui.py'deki ile BIREBIR AYNI -- degisen tek sey, widget'lara
    dogrudan dokunmak yerine sinyal yaymalari (thread-guvenli Qt koprusu).
    """
    log = Signal(str)
    status = Signal(str, str)  # (metin, renk_hex)
    report_ready = Signal(object, str)  # (ForensicReport, report_path)

    def __init__(self, mode, args, out_path, case, examiner, custodian, process_label=None, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.args = args
        self.out_path = out_path
        self.case = case
        self.examiner = examiner
        self.custodian = custodian
        self.process_label = process_label

    def run(self):
        if self.mode == "process":
            self._run_process_mode()
        else:
            self._run_full_mode()

    def _new_report(self, method, source_identifier):
        if ForensicReport is None:
            return None
        report = ForensicReport(case_id=self.case, examiner=self.examiner, custodian=self.custodian)
        report.start(
            engine="ram_engine", method=method, target_os="windows", target_host="localhost",
            source_identifier=source_identifier,
        )
        report.set_write_blocking(False, "RAM imajlama icin write-blocking kavrami gecerli degil")
        return report

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

        self.log.emit(f"$ {' '.join(args)}")
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
            exit_code = -1

        if exit_code == 0 and os.path.exists(out_path):
            self.status.emit("Tamamlandı.", ui.SUCCESS)
            if coc:
                coc.log_event(coc.EVENT_EXAM_END, f"RAM process dump tamamlandi: {out_path}")
            if report:
                dosya_hash = None
                try:
                    with open(out_path, "rb") as f:
                        dosya_hash = hashlib.sha256(f.read()).hexdigest()
                except OSError:
                    pass
                report.finish(
                    status="success", output_path=out_path, image_hash=dosya_hash,
                    total_bytes=os.path.getsize(out_path) if os.path.exists(out_path) else None,
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

    def _run_full_mode(self):
        """AYNEN tasindi -- full mod Yonetici gerektirir; ShellExecute
        'runas' ile yukseltip ilerlemeyi <output>.log dosyasini tail'leyerek
        gosteriyoruz (yukseltilmis surecin stdout'u ana surece aktarilamaz)."""
        args, out_path = self.args, self.out_path
        log_path = out_path + ".log"
        try:
            if os.path.exists(log_path):
                os.remove(log_path)
        except OSError:
            pass

        self.log.emit(f"$ {' '.join(args)} (Yönetici olarak, UAC istemi gelecek)")
        try:
            # subprocess.list2cmdline: Windows'un argv kacirma kuralini
            # (tirnak/backslash) dogru uyguluyor -- eski " ".join(...) sadece
            # bosluk varsa tirnakliyordu, icindeki " karakterini hic
            # kacirmiyordu (vaka no/inceleyen gibi serbest metin alanlarindan
            # yukseltilmis surece arguman enjeksiyonuna acikti).
            params = subprocess.list2cmdline(args[1:])
            result = ctypes.windll.shell32.ShellExecuteW(None, "runas", args[0], params, None, 1)
            if result <= 32:
                self.log.emit(f"Yükseltme başarısız (kod {result}) -- UAC reddedildi olabilir.")
                self.status.emit("Başlatılamadı / UAC reddedildi.", ui.ERROR)
                return
        except Exception as exc:
            self.log.emit(f"Başlatılamadı: {exc}")
            self.status.emit("Başlatılamadı.", ui.ERROR)
            return

        self._tail_log(log_path, out_path)

    def _tail_log(self, log_path, out_path):
        """AYNEN tasindi -- log_path'i periyodik okuyup yeni satirlari
        gosterir, ciktinin (.img dosyasinin) belirmesini bitis isareti sayar."""
        if coc:
            coc.log_event(coc.EVENT_EXAM_START, f"RAM full imaj baslatildi: {out_path}")

        last_size = 0
        waited = 0
        while waited < 3600:  # full RAM uzun surebilir, 1 saate kadar bekle
            time.sleep(1)
            waited += 1
            if os.path.exists(log_path):
                try:
                    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(last_size)
                        yeni = f.read()
                        last_size = f.tell()
                    if yeni:
                        self.log.emit(yeni.rstrip("\n"))
                except OSError:
                    pass
            if os.path.exists(out_path) and os.path.exists(out_path + ".json"):
                break

        basarili = os.path.exists(out_path) and os.path.exists(out_path + ".json")
        report = self._new_report("ram_full", "PhysicalMemory (full)")

        if basarili:
            self.status.emit("Tamamlandı.", ui.SUCCESS)
            vendor_hash = None
            vendor_bytes = None
            try:
                with open(out_path + ".json", "r", encoding="utf-8") as f:
                    vendor_meta = json.load(f)
                vendor_hash = vendor_meta.get("sha256")
                vendor_bytes = vendor_meta.get("size") or vendor_meta.get("total_size")
            except (OSError, json.JSONDecodeError) as exc:
                self.log.emit(f"[UYARI] RamImagerCLI metadata okunamadi: {exc}")

            if coc:
                coc.log_event(coc.EVENT_EXAM_END, f"RAM full imaj tamamlandi: {out_path}", vendor_hash)
            if report:
                report.finish(
                    status="success", output_path=out_path, image_hash=vendor_hash,
                    total_bytes=vendor_bytes or (os.path.getsize(out_path) if os.path.exists(out_path) else None),
                )
                rapor_yolu = self._save_report(report, os.path.dirname(out_path) or ".")
                self.report_ready.emit(report, rapor_yolu)
        else:
            self.status.emit("Bitmedi ya da hata oluştu, günlüğe bakın.", ui.ERROR)
            if coc:
                coc.log_event(coc.EVENT_EXAM_ERROR, f"RAM full imaj basarisiz/tamamlanamadi: {out_path}")
            if report:
                report.finish(status="failed", output_path=out_path)
                self._save_report(report, os.path.dirname(out_path) or ".")


class RamEngineWidget(QWidget):
    def __init__(self, on_back=None, on_show_help=None, initial_case_id="", initial_examiner="",
                 initial_custodian="", parent=None):
        super().__init__(parent)
        self.on_back = on_back
        # bkz. gui_v2.py'deki ForensicWidget.on_show_help -- ayni desen:
        # launcher icinden aciliyorsa Bilgi Merkezi sayfasina goturur,
        # standalone calistirmada None kalir (dialog fallback kullanilir).
        self.on_show_help = on_show_help
        self._pid_map = {}
        self.worker = None
        self._build_ui(initial_case_id, initial_examiner, initial_custodian)
        self._refresh_processes()

    # -- UI ------------------------------------------------------------
    def _build_ui(self, initial_case_id, initial_examiner, initial_custodian):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(ui.CARD_GAP)

        header = QHBoxLayout()
        if self.on_back:
            back_btn = widgets.SecondaryButton("← Geri")
            back_btn.clicked.connect(self.on_back)
            header.addWidget(back_btn)
        title = QLabel("RAM İmajı Al")
        title.setStyleSheet(f"color:{ui.TEXT_MAIN}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_TITLE}px; font-weight:600;")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        # === Vaka Bilgileri ===
        vaka = widgets.Card("Vaka Bilgileri")
        vaka.body.addWidget(self._note("(İsteğe bağlı -- rapor üretmiyorsanız boş bırakabilirsiniz)"))
        self.entry_case = self._labeled_input(vaka.body, "Vaka No", initial_case_id)
        self.entry_examiner = self._labeled_input(vaka.body, "İnceleyen", initial_examiner)
        self.entry_custodian = self._labeled_input(vaka.body, "Cihaz Sahibi / Yetkili Kişi", initial_custodian)
        layout.addWidget(vaka)

        # === Mod secimi ===
        mode_card = widgets.Card("Mod")
        mode_row = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.radio_process = widgets.RadioButton("Process Dump (sürücü gerekmez, hemen çalışır)")
        self.radio_full = widgets.RadioButton("Full RAM (Yönetici + sürücü gerekir)")
        self.radio_process.setChecked(True)
        for r in (self.radio_process, self.radio_full):
            self.mode_group.addButton(r)
            mode_row.addWidget(r)
        mode_row.addStretch()
        mode_card.body.addLayout(mode_row)
        self.radio_process.toggled.connect(self._on_mode_change)
        layout.addWidget(mode_card)

        # === Process modu alanlari ===
        self.process_card = widgets.Card("Process Dump")
        proc_row = QHBoxLayout()
        proc_row.addWidget(QLabel("Process:"))
        self.process_combo = QComboBox()
        self.process_combo.setMinimumWidth(340)
        self.process_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {ui.BG_LAYER2}; color: {ui.TEXT_MAIN};
                border: 1px solid {ui.BORDER}; border-radius: {ui.RADIUS}px; padding: 4px 8px;
            }}
        """)
        proc_row.addWidget(self.process_combo)
        refresh_btn = widgets.SecondaryButton("Yenile")
        refresh_btn.clicked.connect(self._refresh_processes)
        proc_row.addWidget(refresh_btn)
        proc_row.addStretch()
        self.process_card.body.addLayout(proc_row)
        layout.addWidget(self.process_card)

        # === Full mod alanlari ===
        self.full_card = widgets.Card("Full RAM")
        warn = QLabel(
            "Yönetici olarak çalıştırılmalı; imzasız sürücü için Secure Boot kapatma + "
            "test-signing + yeniden başlatma gerekir (bkz. engines/ram_engine/INSTALL.txt)."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet(f"color:{ui.ERROR}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        self.full_card.body.addWidget(warn)
        self.full_card.body.addWidget(self._help_link("ram_full_mode_driver"))
        layout.addWidget(self.full_card)
        self.full_card.hide()

        # === Cikti ===
        out_card = widgets.Card("Çıktı")
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Dosya:"))
        self.entry_out = widgets.MonoInput()
        default_out = os.path.join(os.environ.get("TEMP", "."), "ram_dump.dmp")
        self.entry_out.setText(default_out)
        out_row.addWidget(self.entry_out, stretch=1)
        browse_btn = widgets.SecondaryButton("Gözat")
        browse_btn.clicked.connect(self._browse_out)
        out_row.addWidget(browse_btn)
        out_card.body.addLayout(out_row)
        layout.addWidget(out_card)

        # === Baslat + durum + ilerleme ===
        start_row = QHBoxLayout()
        self.btn_start = widgets.PrimaryButton("Başlat")
        self.btn_start.clicked.connect(self._start)
        start_row.addWidget(self.btn_start)
        self.status_label = QLabel("Hazır")
        self.status_label.setStyleSheet(f"color:{ui.TEXT_SECONDARY}; font-family:'{ui.FONT_UI}'; font-size:{ui.SIZE_HELPER}px;")
        start_row.addWidget(self.status_label)
        start_row.addStretch()
        layout.addLayout(start_row)

        self.progress = widgets.ProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)

        # === Gunluk ===
        log_card = widgets.Card("Günlük")
        log_card.body.addWidget(self._help_link("chain_of_custody", "Delil zinciri nedir?"))
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

    def _help_link(self, topic_key, label="Bu ne demek? (Bilgi Merkezi'nde oku)"):
        """Bilgi Merkezi'ndeki bir konuya goturen, mavi metin gorunumlu
        kucuk bir buton -- bkz. gui_v2.py'deki ForensicWidget._help_link
        (ayni desen, iki dosya birbirinden bagimsiz calisabildigi icin
        kod tekrarlanir)."""
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
            self, "Çıktı Dosyası Seç", self.entry_out.text(), f"{ext[1:].upper()} dosyası (*{ext});;Tüm Dosyalar (*.*)",
        )
        if path:
            self.entry_out.setText(path)

    # -- Calistirma --------------------------------------------------------
    def _start(self):
        if not os.path.isfile(CLI_PATH):
            self._set_status(f"RamImagerCLI.exe bulunamadı: {CLI_PATH}", ui.ERROR)
            return

        out_path = self.entry_out.text().strip()
        if not out_path:
            self._set_status("Çıktı dosyası seçin.", ui.ERROR)
            return

        case = self.entry_case.text().strip()
        examiner = self.entry_examiner.text().strip()
        custodian = self.entry_custodian.text().strip()

        self.btn_start.setEnabled(False)
        self._set_status("Çalışıyor...")
        self.progress.show()
        self.progress.set_indeterminate()

        if self.radio_process.isChecked():
            secim = self.process_combo.currentText()
            pid = self._pid_map.get(secim)
            if not pid:
                self._set_status("Bir process seçin.", ui.ERROR)
                self.btn_start.setEnabled(True)
                self.progress.hide()
                return
            args = [CLI_PATH, "process", "--pid", pid, "--output", out_path]
            self.worker = RamWorker("process", args, out_path, case, examiner, custodian, process_label=secim)
        else:
            args = [CLI_PATH, "full", "--output", out_path, "--driver", DRIVER_PATH]
            if case:
                args += ["--case", case]
            if examiner:
                args += ["--examiner", examiner]
            self.worker = RamWorker("full", args, out_path, case, examiner, custodian)

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

        html_path = os.path.splitext(report_path)[0] + ".html"

        dialog = QDialog(self)
        dialog.setWindowTitle("İşlem Raporu")
        dialog.resize(480, 340)
        dialog.setStyleSheet(f"background-color:{ui.BG_DARKEST};")
        layout = QVBoxLayout(dialog)

        d = report.to_dict()
        basarili = d["result"]["status"] == "success"
        head = QLabel("✔ İşlem Tamamlandı" if basarili else f"İşlem Durumu: {d['result']['status']}")
        head.setStyleSheet(
            f"color:{ui.SUCCESS if basarili else ui.ERROR}; font-family:'{ui.FONT_UI}'; "
            f"font-size:15px; font-weight:600;"
        )
        layout.addWidget(head)

        image_hash = d["integrity"]["image_hash"] or ""
        satirlar = [
            ("Vaka No", d["case"]["case_id"] or "—"),
            ("İnceleyen", d["case"]["examiner"] or "—"),
            ("Cihaz Sahibi / Yetkili Kişi", d["case"]["custodian"] or "—"),
            ("Kaynak", d["acquisition"]["source_identifier"] or "—"),
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
                self._log(f"[UYARI] Rapor açılamadı: {e}")

        open_btn = widgets.PrimaryButton("Raporu Aç (HTML)")
        open_btn.clicked.connect(_open_html)
        btns.addWidget(open_btn)
        btns.addStretch()
        close_btn = widgets.SecondaryButton("Kapat")
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
    win.setWindowTitle("RAM İmajı Al")
    win.resize(820, 720)
    win.setCentralWidget(RamEngineWidget())
    win.show()
    sys.exit(app.exec())
