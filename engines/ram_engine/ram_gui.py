"""
ram_gui.py
RAM motoru arayuzu -- vendor'in kendi RamImagerGUI.exe'si (WinForms,
bizim temamizdan habersiz) yerine, RamImagerCLI.exe'yi dogrudan
subprocess ile cagiran, chameleon'un CTk temasiyla uyumlu kendi
arayuzumuz.

RamImagerCLI.exe/RamImagerDriver.sys kaynagi bizde yok (derlenmis hali
verildi), bu yuzden onlarin davranisini degistirmiyoruz -- sadece nasil
cagirdigimizi ve sonucu nasil gosterdigimizi degistiriyoruz.
"""

import csv
import io
import os
import subprocess
import sys
import threading
import time

import customtkinter as ctk
from tkinter import filedialog

RAM_ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
CLI_PATH = os.path.join(RAM_ENGINE_DIR, "cli", "RamImagerCLI.exe")
DRIVER_PATH = os.path.join(RAM_ENGINE_DIR, "driver", "RamImagerDriver.sys")

_SHARED_DIR = os.path.join(RAM_ENGINE_DIR, "..", "..", "shared")
if os.path.isdir(_SHARED_DIR):
    sys.path.insert(0, _SHARED_DIR)
try:
    from theme import (
        BG_MAIN, BG_PANEL, TEXT_MAIN, TEXT_SECONDARY, ACCENT, ACCENT_HOVER, ERROR, BORDER, OK,
    )
except ImportError:
    BG_MAIN, BG_PANEL = "#F5F5F3", "#FFFFFF"
    TEXT_MAIN, TEXT_SECONDARY = "#2B2B2B", "#6B6B6B"
    ACCENT, ACCENT_HOVER, ERROR, BORDER, OK = "#3B5D6B", "#2C4650", "#A64545", "#DADAD8", "#3F7D57"


def list_processes():
    """
    'tasklist' ile calisan process'leri (isim, PID) dondurur -- ek bir
    kutuphane (orn. psutil) eklemeden, Windows'ta zaten var olan komutu
    kullaniyoruz.
    """
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


class RamEngineGUI:
    def __init__(self, root, on_back=None):
        """
        root: bu ekranin cizilecegi widget (ssh_engine/gui_v2.py'deki
        ForensicGUI ile ayni desen -- launcher'dan gomulebilir, tek basina
        da calisabilir).
        """
        self.root = root
        self.on_back = on_back
        self.root.configure(fg_color=BG_MAIN)
        self._proc = None
        self._log_poll_stop = False
        self._build_ui()
        self._refresh_processes()

    # -- UI ------------------------------------------------------------
    def _card(self, parent, title):
        outer = ctk.CTkFrame(
            parent, fg_color=BG_PANEL, border_color=BORDER, border_width=1, corner_radius=10,
        )
        outer.pack(fill="x", padx=12, pady=6)
        ctk.CTkLabel(
            outer, text=title, font=("Segoe UI", 12, "bold"), text_color=ACCENT, anchor="w",
        ).pack(fill="x", padx=14, pady=(12, 2))
        inner = ctk.CTkFrame(outer, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        return inner

    def _build_ui(self):
        header = ctk.CTkFrame(self.root, fg_color=ACCENT, height=48, corner_radius=0)
        header.pack(fill="x")
        if self.on_back:
            ctk.CTkButton(
                header, text="< Geri", command=self.on_back, width=70,
                fg_color=ACCENT, hover_color=ACCENT_HOVER,
            ).pack(side="left", padx=(12, 0), pady=8)
        ctk.CTkLabel(
            header, text="RAM İmajı Al", font=("Segoe UI", 14, "bold"), text_color="white",
        ).pack(side="left", padx=15, pady=8)

        # === Mod secimi ===
        mode_card = self._card(self.root, "Mod")
        self.mode_var = ctk.StringVar(value="process")
        ctk.CTkRadioButton(
            mode_card, text="Process Dump (sürücü gerekmez, hemen çalışır)",
            variable=self.mode_var, value="process", fg_color=ACCENT, text_color=TEXT_MAIN,
            command=self._on_mode_change,
        ).grid(row=0, column=0, sticky="w", pady=4, padx=(0, 20))
        ctk.CTkRadioButton(
            mode_card, text="Full RAM (Yönetici + sürücü gerekir)",
            variable=self.mode_var, value="full", fg_color=ACCENT, text_color=TEXT_MAIN,
            command=self._on_mode_change,
        ).grid(row=0, column=1, sticky="w", pady=4)

        # === Process modu alanlari ===
        self.process_card = self._card(self.root, "Process Dump")
        ctk.CTkLabel(self.process_card, text="Process:", text_color=TEXT_MAIN).grid(
            row=0, column=0, sticky="w", pady=4
        )
        self.process_var = ctk.StringVar()
        self.process_combo = ctk.CTkComboBox(
            self.process_card, variable=self.process_var, width=340, values=[],
        )
        self.process_combo.grid(row=0, column=1, padx=6, pady=4, sticky="w")
        ctk.CTkButton(
            self.process_card, text="Yenile", command=self._refresh_processes, width=80,
            fg_color=BG_PANEL, border_width=1, border_color=BORDER,
            text_color=TEXT_MAIN, hover_color=BG_MAIN,
        ).grid(row=0, column=2, padx=6, pady=4)

        # === Full mod alanlari ===
        self.full_card = self._card(self.root, "Full RAM")
        ctk.CTkLabel(self.full_card, text="Case:", text_color=TEXT_MAIN).grid(
            row=0, column=0, sticky="w", pady=4
        )
        self.entry_case = ctk.CTkEntry(self.full_card, width=200)
        self.entry_case.grid(row=0, column=1, padx=6, pady=4, sticky="w")
        ctk.CTkLabel(self.full_card, text="Examiner:", text_color=TEXT_MAIN).grid(
            row=0, column=2, sticky="w", pady=4
        )
        self.entry_examiner = ctk.CTkEntry(self.full_card, width=200)
        self.entry_examiner.grid(row=0, column=3, padx=6, pady=4, sticky="w")
        ctk.CTkLabel(
            self.full_card,
            text="Yönetici olarak çalıştırılmalı; imzasız sürücü için Secure Boot kapatma +\n"
                 "test-signing + yeniden başlatma gerekir (bkz. engines/ram_engine/INSTALL.txt).",
            text_color=ERROR, font=("Segoe UI", 10), justify="left",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))

        # === Cikti ===
        out_card = self._card(self.root, "Çıktı")
        ctk.CTkLabel(out_card, text="Dosya:", text_color=TEXT_MAIN).grid(
            row=0, column=0, sticky="w", pady=4
        )
        self.entry_out = ctk.CTkEntry(out_card, width=420)
        self.entry_out.grid(row=0, column=1, padx=6, pady=4, sticky="w")
        default_out = os.path.join(os.environ.get("TEMP", "."), "ram_dump.dmp")
        self.entry_out.insert(0, default_out)
        ctk.CTkButton(
            out_card, text="Gözat", command=self._browse_out, width=80,
            fg_color=BG_PANEL, border_width=1, border_color=BORDER,
            text_color=TEXT_MAIN, hover_color=BG_MAIN,
        ).grid(row=0, column=2, padx=6, pady=4)

        # === Baslat + durum ===
        btn_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12, pady=6)
        self.btn_start = ctk.CTkButton(
            btn_frame, text="Başlat", command=self._start, fg_color=ACCENT, hover_color=ACCENT_HOVER,
        )
        self.btn_start.pack(side="left", padx=5)
        self.status_label = ctk.CTkLabel(btn_frame, text="Hazır", text_color=TEXT_SECONDARY)
        self.status_label.pack(side="left", padx=10)

        # === Gunluk ===
        log_inner = self._card(self.root, "Günlük")
        log_inner.pack_configure(expand=True)
        self.txt_log = ctk.CTkTextbox(
            log_inner, fg_color="#1e1e1e", text_color="#dcdcdc", font=("Consolas", 10),
        )
        self.txt_log.pack(fill="both", expand=True)
        self.txt_log.configure(state="disabled")

        self._on_mode_change()

    # -- Yardimci --------------------------------------------------------
    def _log(self, msg):
        def _append():
            self.txt_log.configure(state="normal")
            self.txt_log.insert("end", msg + "\n")
            self.txt_log.see("end")
            self.txt_log.configure(state="disabled")
        self.root.after(0, _append)

    def _on_mode_change(self):
        if self.mode_var.get() == "process":
            self.process_card.master.pack(fill="x", padx=12, pady=6)
            self.full_card.master.pack_forget()
        else:
            self.full_card.master.pack(fill="x", padx=12, pady=6)
            self.process_card.master.pack_forget()

    def _refresh_processes(self):
        def worker():
            islemler = list_processes()
            values = [f"{ad} (PID {pid})" for ad, pid in islemler]
            self._pid_map = {f"{ad} (PID {pid})": pid for ad, pid in islemler}

            def _update():
                self.process_combo.configure(values=values)
                if values:
                    self.process_var.set(values[0])
            self.root.after(0, _update)
        threading.Thread(target=worker, daemon=True).start()

    def _browse_out(self):
        ext = ".dmp" if self.mode_var.get() == "process" else ".img"
        path = filedialog.asksaveasfilename(
            title="Çıktı Dosyası Seç", defaultextension=ext,
            filetypes=[(f"{ext[1:].upper()} dosyası", f"*{ext}"), ("Tüm Dosyalar", "*.*")],
        )
        if path:
            self.entry_out.delete(0, "end")
            self.entry_out.insert(0, path)

    # -- Calistirma --------------------------------------------------------
    def _start(self):
        if not os.path.isfile(CLI_PATH):
            self.status_label.configure(text=f"RamImagerCLI.exe bulunamadı: {CLI_PATH}", text_color=ERROR)
            return

        out_path = self.entry_out.get().strip()
        if not out_path:
            self.status_label.configure(text="Çıktı dosyası seçin.", text_color=ERROR)
            return

        self.btn_start.configure(state="disabled")
        self.status_label.configure(text="Çalışıyor...", text_color=TEXT_SECONDARY)

        if self.mode_var.get() == "process":
            secim = self.process_var.get()
            pid = self._pid_map.get(secim)
            if not pid:
                self.status_label.configure(text="Bir process seçin.", text_color=ERROR)
                self.btn_start.configure(state="normal")
                return
            args = [CLI_PATH, "process", "--pid", pid, "--output", out_path]
            threading.Thread(target=self._run_process_mode, args=(args,), daemon=True).start()
        else:
            case = self.entry_case.get().strip()
            examiner = self.entry_examiner.get().strip()
            args = [CLI_PATH, "full", "--output", out_path, "--driver", DRIVER_PATH]
            if case:
                args += ["--case", case]
            if examiner:
                args += ["--examiner", examiner]
            threading.Thread(target=self._run_full_mode, args=(args, out_path), daemon=True).start()

    def _run_process_mode(self, args):
        """
        process modu yukseltme (Yonetici) gerektirmedigi icin stdout
        dogrudan okunabilir -- PROJE_DOKUMANI.md'deki GUI mimarisiyle
        ayni desen.
        """
        self._log(f"$ {' '.join(args)}")
        try:
            proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for line in proc.stdout:
                self._log(line.rstrip("\n"))
            exit_code = proc.wait()
        except OSError as exc:
            self._log(f"Başlatılamadı: {exc}")
            exit_code = -1

        if exit_code == 0:
            self.status_label.configure(text="Tamamlandı.", text_color=OK)
        else:
            self.status_label.configure(text=f"Başarısız (kod {exit_code}).", text_color=ERROR)
        self.btn_start.configure(state="normal")

    def _run_full_mode(self, args, out_path):
        """
        full modu Yonetici gerektirir; Windows yukseltilmis bir surecin
        stdout'unu ana surece dogrudan aktarmaya izin vermez (ayni kisit
        vendor GUI'sinde de var, bkz. PROJE_DOKUMANI.md 4.4). Bu yuzden
        ShellExecute 'runas' ile yukseltip, ilerlemeyi CLI'nin urettigi
        <output>.log dosyasini periyodik okuyarak (tail) gosteriyoruz.
        """
        import ctypes

        log_path = out_path + ".log"
        try:
            if os.path.exists(log_path):
                os.remove(log_path)
        except OSError:
            pass

        self._log(f"$ {' '.join(args)} (Yönetici olarak, UAC istemi gelecek)")
        try:
            params = " ".join(f'"{a}"' if " " in a else a for a in args[1:])
            result = ctypes.windll.shell32.ShellExecuteW(None, "runas", args[0], params, None, 1)
            if result <= 32:
                self._log(f"Yükseltme başarısız (kod {result}) -- UAC reddedildi olabilir.")
                self.status_label.configure(text="Başlatılamadı / UAC reddedildi.", text_color=ERROR)
                self.btn_start.configure(state="normal")
                return
        except Exception as exc:
            self._log(f"Başlatılamadı: {exc}")
            self.status_label.configure(text="Başlatılamadı.", text_color=ERROR)
            self.btn_start.configure(state="normal")
            return

        self._tail_log(log_path, out_path)

    def _tail_log(self, log_path, out_path):
        """log_path'i periyodik okuyup yeni satirlari gosterir, ciktinin
        (.img dosyasinin) belirmesini bitis isareti sayar."""
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
                        self._log(yeni.rstrip("\n"))
                except OSError:
                    pass
            if os.path.exists(out_path) and os.path.exists(out_path + ".json"):
                break

        if os.path.exists(out_path) and os.path.exists(out_path + ".json"):
            self.status_label.configure(text="Tamamlandı.", text_color=OK)
        else:
            self.status_label.configure(text="Bitmedi ya da hata oluştu, günlüğe bakın.", text_color=ERROR)
        self.btn_start.configure(state="normal")


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.title("RAM İmajı Al")
    root.geometry("780x640")
    RamEngineGUI(root)
    root.mainloop()
