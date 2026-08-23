"""
gui_v2.py
SSH ile Uzak İmaj Alma — CustomTkinter Grafik Arayuzu

Mevcut backend modullerini (SSHConnector/image_acquirer/hash_verifier)
hic degistirmeden kullanir; bu dosya sadece arayuz katmani.

Calistirmak icin:
    cd local_collector
    python gui_v2.py

Gereksinim:
    pip install paramiko customtkinter
"""

import datetime
import getpass
import os
import re
import sys
import threading
import tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext

import customtkinter as ctk

# Varsayilan imaj cikti yolu, script'in NEREDEN calistirildigina (cwd)
# degil, projenin kendi konumuna gore belirlenir. Aksi halde ("cwd" ile
# os.getcwd() kullanilirsa) program yanlislikla C:\Windows\System32 gibi
# bir dizinden baslatilirsa oraya yazmaya calisir ve "Permission denied"
# hatasi verir.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_IMAGE_PATH = os.path.join(PROJECT_ROOT, "images", "forensic_image.raw")

# Ortak renk paleti (chameleon/shared/theme.py) -- launcher'la ayni
# degerler, tek yerden yonetiliyor. Chameleon disinda, tek basina
# calistirildiginda bulunamazsa kendi yedek degerleriyle devam eder.
_THEME_DIR = os.path.join(PROJECT_ROOT, "..", "..", "shared")
if os.path.isdir(_THEME_DIR):
    sys.path.insert(0, _THEME_DIR)
try:
    from theme import (
        BG_MAIN, BG_PANEL, TEXT_MAIN, TEXT_SECONDARY, ACCENT, ACCENT_HOVER,
        ERROR, BORDER, OK, WARN,
    )
except ImportError:
    BG_MAIN, BG_PANEL = "#F5F5F3", "#FFFFFF"
    TEXT_MAIN, TEXT_SECONDARY = "#2B2B2B", "#6B6B6B"
    ACCENT, ACCENT_HOVER, ERROR, BORDER = "#3B5D6B", "#2C4650", "#A64545", "#DADAD8"
    OK, WARN = "#3F7D57", "#B98A2E"

# ---------------------------------------------------------------------------
# Mevcut modulleri import et (hic degistirmeden)
# ---------------------------------------------------------------------------
try:
    from ssh_connector import SSHConnector
    from image_acquirer import (
        acquire_disk_image,
        concatenate_blocks,
        local_master_hash,
        find_incomplete_manifest,
    )
    from file_acquirer import acquire_remote_tree
    from hash_verifier import verify_file, HashMismatchError, HashError
    import chain_of_custody as coc
    PARAMIKO_OK = True
except ImportError as exc:
    PARAMIKO_OK = False
    IMPORT_ERROR = str(exc)


# Rengi shared/theme.py'den gelen isimlerle esliyoruz, geri kalan kod
# COLOR_* isimlerini kullanmaya devam ediyor.
COLOR_BG = BG_MAIN
COLOR_PANEL = BG_PANEL
COLOR_TEXT = TEXT_MAIN
COLOR_SECONDARY = TEXT_SECONDARY
COLOR_BORDER = BORDER
COLOR_ACCENT = ACCENT
COLOR_ACCENT_HOVER = ACCENT_HOVER
COLOR_OK = OK
COLOR_ERR = ERROR
COLOR_WARN = WARN
COLOR_INFO = TEXT_SECONDARY


# ---------------------------------------------------------------------------
# stdout yakalama: image_acquirer.py'deki print()'leri GUI'ye yonlendirir
# ---------------------------------------------------------------------------
class StdoutRedirector:
    """sys.stdout'u yakalayıp bir callback fonksiyonuna iletir."""

    def __init__(self, callback):
        self.callback = callback
        self._orig_stdout = sys.stdout

    def write(self, text):
        self._orig_stdout.write(text)  # konsola da yaz
        self._orig_stdout.flush()
        if text:
            self.callback(text)

    def flush(self):
        self._orig_stdout.flush()


# ---------------------------------------------------------------------------
# Ana GUI Sinifi
# ---------------------------------------------------------------------------
class ForensicGUI:
    def __init__(self, root, on_back=None):
        """
        root: bu ekranin icine cizilecegi widget. Tek basina calistirildiginda
        (bkz. dosya sonu) bir Tk() root'u olur; chameleon launcher'indan
        acildiginda ise launcher'in kendi penceresindeki bir frame olur --
        pencere baslik/boyut ayarlari o durumda cagirani ilgilendirir,
        burada yapilmaz.
        on_back: verilirse baslikta bir "Geri" butonu gosterilir, tiklaninca
        bu cagirilir (launcher secim ekranina donmek icin).
        """
        self.root = root
        self.on_back = on_back
        self.root.configure(fg_color=COLOR_BG)

        self.ssh = None
        self.disks_raw = ""
        self._worker_thread = None
        self._stop_requested = False

        if not PARAMIKO_OK:
            self._show_error(f"paramiko kurulu değil:\n{IMPORT_ERROR}\n\n"
                             f"Kurmak için: pip install paramiko")
            return

        self._build_ui()
        self._log("Program başladı. SSH bilgilerini girin ve 'Bağlan' tuşuna basın.", "info")

    # -- UI Olusturma -------------------------------------------------------
    def _card(self, parent, title, expand=False):
        """
        ttk.LabelFrame yerine: basligi olan, kenarli/koseli bir CTkFrame.
        Icerik, donen ikinci (inner) frame'e eklenir. expand=True verilirse
        (log paneli gibi) disi kalan dikey alani doldurur.
        """
        outer = ctk.CTkFrame(
            parent, fg_color=COLOR_PANEL, border_color=COLOR_BORDER,
            border_width=1, corner_radius=10,
        )
        outer.pack(fill="both" if expand else "x", expand=expand, padx=12, pady=6)
        ctk.CTkLabel(
            outer, text=title, font=("Segoe UI", 12, "bold"), text_color=COLOR_ACCENT, anchor="w",
        ).pack(fill="x", padx=14, pady=(12, 2))
        inner = ctk.CTkFrame(outer, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        return inner

    def _build_ui(self):
        # === Baslik seridi ===
        header = tk.Frame(self.root, bg=COLOR_ACCENT, height=48)
        header.pack(fill="x")
        if self.on_back:
            tk.Button(
                header, text="< Geri", command=self.on_back, bg=COLOR_ACCENT, fg="white",
                activebackground=COLOR_ACCENT, activeforeground="white", relief="flat",
                font=("Segoe UI", 10), bd=0, cursor="hand2",
            ).pack(side="left", padx=(12, 0), pady=8)
        tk.Label(header, text="SSH ile Uzak İmaj Al", bg=COLOR_ACCENT, fg="white",
                 font=("Segoe UI", 14, "bold")).pack(side="left", padx=15, pady=8)
        self.lbl_conn_status = tk.Label(header, text="Bağlantı yok", bg=COLOR_ACCENT,
                                         fg="#f1c1c1", font=("Segoe UI", 10, "bold"))
        self.lbl_conn_status.pack(side="right", padx=15)

        # === SSH Baglanti Paneli ===
        conn = self._card(self.root, "SSH Bağlantı Bilgileri")

        ctk.CTkLabel(conn, text="Host:", text_color=COLOR_TEXT).grid(row=0, column=0, sticky="w", pady=4)
        self.entry_host = ctk.CTkEntry(conn, width=180)
        self.entry_host.grid(row=0, column=1, padx=6, pady=4, sticky="w")
        self.entry_host.insert(0, "192.168.1.100")

        ctk.CTkLabel(conn, text="Port:", text_color=COLOR_TEXT).grid(row=0, column=2, sticky="w", pady=4)
        self.entry_port = ctk.CTkEntry(conn, width=60)
        self.entry_port.grid(row=0, column=3, padx=6, pady=4, sticky="w")
        self.entry_port.insert(0, "22")

        ctk.CTkLabel(conn, text="Kullanıcı:", text_color=COLOR_TEXT).grid(row=1, column=0, sticky="w", pady=4)
        self.entry_user = ctk.CTkEntry(conn, width=180)
        self.entry_user.grid(row=1, column=1, padx=6, pady=4, sticky="w")

        ctk.CTkLabel(conn, text="Şifre:", text_color=COLOR_TEXT).grid(row=1, column=2, sticky="w", pady=4)
        self.entry_pass = ctk.CTkEntry(conn, width=100, show="*")
        self.entry_pass.grid(row=1, column=3, padx=6, pady=4, sticky="w")

        ctk.CTkLabel(conn, text="SSH Anahtar:", text_color=COLOR_TEXT).grid(row=2, column=0, sticky="w", pady=4)
        self.entry_key = ctk.CTkEntry(conn, width=180)
        self.entry_key.grid(row=2, column=1, padx=6, pady=4, sticky="w")
        ctk.CTkButton(
            conn, text="Gözat", command=self._browse_key, width=70,
            fg_color=COLOR_PANEL, border_width=1, border_color=COLOR_BORDER,
            text_color=COLOR_TEXT, hover_color=COLOR_BG,
        ).grid(row=2, column=2, columnspan=2, pady=4, sticky="w")

        ctk.CTkButton(
            conn, text="Bağlan ve Diskleri Listele", command=self._connect,
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
        ).grid(row=3, column=0, columnspan=4, pady=(10, 2))

        # === Ne alinacak: tam disk mi, dosya/klasor mu ===
        secim = self._card(self.root, "Ne Alınacak?")
        self.acq_type_var = tk.StringVar(value="disk")
        ctk.CTkRadioButton(
            secim, text="Tam Disk (dd)", variable=self.acq_type_var, value="disk",
            fg_color=COLOR_ACCENT, text_color=COLOR_TEXT, command=self._on_acq_type_change,
        ).grid(row=0, column=0, padx=(0, 20), pady=4, sticky="w")
        ctk.CTkRadioButton(
            secim, text="Dosya ya da Klasör", variable=self.acq_type_var, value="file",
            fg_color=COLOR_ACCENT, text_color=COLOR_TEXT, command=self._on_acq_type_change,
        ).grid(row=0, column=1, pady=4, sticky="w")

        # === Hedef Disk & Mod Paneli ===
        self.disk_card = self._card(self.root, "Hedef Disk ve İşlem Modu")
        disk = self.disk_card

        ctk.CTkLabel(disk, text="Disk (örn. /dev/sdb):", text_color=COLOR_TEXT).grid(
            row=0, column=0, sticky="w", pady=4
        )
        self.entry_disk = ctk.CTkEntry(disk, width=140)
        self.entry_disk.grid(row=0, column=1, padx=6, pady=4, sticky="w")

        self.mode_var = tk.StringVar(value="live")
        ctk.CTkRadioButton(
            disk, text="Live Acquisition", variable=self.mode_var, value="live",
            fg_color=COLOR_ACCENT, text_color=COLOR_TEXT,
        ).grid(row=0, column=2, padx=10, pady=4)
        ctk.CTkRadioButton(
            disk, text="Offline Acquisition", variable=self.mode_var, value="offline",
            fg_color=COLOR_ACCENT, text_color=COLOR_TEXT,
        ).grid(row=0, column=3, padx=10, pady=4)

        ctk.CTkLabel(disk, text="İmaj Çıktı Yolu:", text_color=COLOR_TEXT).grid(
            row=1, column=0, sticky="w", pady=4
        )
        self.entry_out = ctk.CTkEntry(disk, width=320)
        self.entry_out.grid(row=1, column=1, columnspan=2, padx=6, pady=4, sticky="w")
        self.entry_out.insert(0, DEFAULT_IMAGE_PATH)
        ctk.CTkButton(
            disk, text="Gözat", command=self._browse_out, width=70,
            fg_color=COLOR_PANEL, border_width=1, border_color=COLOR_BORDER,
            text_color=COLOR_TEXT, hover_color=COLOR_BG,
        ).grid(row=1, column=3, pady=4, sticky="w")

        # === Hedef Dosya/Klasor Paneli (acq_type == "file" iken gorunur) ===
        self.file_card = self._card(self.root, "Hedef Dosya/Klasör")
        fc = self.file_card

        ctk.CTkLabel(fc, text="Uzak Yol (örn. /home/user/belgeler):", text_color=COLOR_TEXT).grid(
            row=0, column=0, sticky="w", pady=4
        )
        self.entry_remote_path = ctk.CTkEntry(fc, width=320)
        self.entry_remote_path.grid(row=0, column=1, columnspan=2, padx=6, pady=4, sticky="w")

        ctk.CTkLabel(fc, text="Çıktı Klasörü:", text_color=COLOR_TEXT).grid(
            row=1, column=0, sticky="w", pady=4
        )
        self.entry_file_out = ctk.CTkEntry(fc, width=320)
        self.entry_file_out.grid(row=1, column=1, padx=6, pady=4, sticky="w")
        self.entry_file_out.insert(0, os.path.join(PROJECT_ROOT, "images", "dosyalar"))
        ctk.CTkButton(
            fc, text="Gözat", command=self._browse_file_out, width=70,
            fg_color=COLOR_PANEL, border_width=1, border_color=COLOR_BORDER,
            text_color=COLOR_TEXT, hover_color=COLOR_BG,
        ).grid(row=1, column=3, pady=4, sticky="w")

        ctk.CTkLabel(
            fc,
            text="Bu modda write-blocker uygulanmaz (dosya/klasör seviyesinde anlamlı değil) --\n"
                 "disk her zaman olduğu gibi, kilitlenmeden okunur.",
            text_color=COLOR_WARN, font=("Segoe UI", 10), justify="left",
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))

        # === Butonlar ===
        btn_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12, pady=6)
        self.btn_frame = btn_frame

        self.btn_acquire = ctk.CTkButton(
            btn_frame, text="İmaj Almayı Başlat", command=self._start_acquisition,
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
        )
        self.btn_acquire.pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame, text="İmaj Doğrula", command=self._verify_image,
            fg_color=COLOR_PANEL, border_width=1, border_color=COLOR_BORDER,
            text_color=COLOR_TEXT, hover_color=COLOR_BG,
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_frame, text="Log Temizle", command=self._clear_log,
            fg_color=COLOR_PANEL, border_width=1, border_color=COLOR_BORDER,
            text_color=COLOR_TEXT, hover_color=COLOR_BG,
        ).pack(side="right", padx=5)

        # === İlerleme Çubuğu ===
        prog_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        prog_frame.pack(fill="x", padx=12, pady=2)
        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ctk.CTkProgressBar(
            prog_frame, orientation="horizontal", fg_color=COLOR_BORDER,
            progress_color=COLOR_ACCENT,
        )
        self.progress.set(0)
        self.progress.pack(fill="x", pady=4)
        self.lbl_status = ctk.CTkLabel(
            prog_frame, text="Bekleniyor...", font=("Segoe UI", 10, "italic"),
            text_color=COLOR_SECONDARY, anchor="w",
        )
        self.lbl_status.pack(anchor="w")

        # === Log Ekrani ===
        log_inner = self._card(self.root, "İşlem Logu", expand=True)

        self.txt_log = scrolledtext.ScrolledText(log_inner, height=14, wrap=tk.WORD,
                                                  font=("Consolas", 10), bg="#1e1e1e", fg="#dcdcdc",
                                                  insertbackground="white", relief="flat", borderwidth=0)
        self.txt_log.pack(fill="both", expand=True)
        self.txt_log.tag_config("ok", foreground="#5fd77f")
        self.txt_log.tag_config("err", foreground="#ff6b6b")
        self.txt_log.tag_config("warn", foreground="#f0c674")
        self.txt_log.tag_config("info", foreground="#8ab4f8")
        self.txt_log.tag_config("plain", foreground="#dcdcdc")
        self.txt_log.config(state=tk.DISABLED)

        self._on_acq_type_change()

    def _on_acq_type_change(self):
        """
        Disk kartini mi, Dosya/Klasor kartini mi gosterecegimize karar
        verir. Kartlardan birini pack_forget edip digerini "before=
        self.btn_frame" ile tekrar paketleyerek her zaman dogru sirada
        (baglanti kartindan sonra, butonlardan once) kalmasini sagliyoruz
        -- aksi halde tekrar pack() cagirmak widget'i en sona atardi.
        """
        if self.acq_type_var.get() == "disk":
            self.file_card.master.pack_forget()
            self.disk_card.master.pack(fill="x", padx=12, pady=6, before=self.btn_frame)
        else:
            self.disk_card.master.pack_forget()
            self.file_card.master.pack(fill="x", padx=12, pady=6, before=self.btn_frame)

    # -- Yardimci Metodlar --------------------------------------------------
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

    def _log(self, msg, tag=None):
        """Log ekranina zaman damgali, renkli mesaj yazar (thread-safe)."""
        if tag is None:
            tag = self._detect_tag(msg)
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        def _append():
            self.txt_log.config(state=tk.NORMAL)
            self.txt_log.insert(tk.END, f"[{timestamp}] ", "plain")
            self.txt_log.insert(tk.END, msg + "\n", tag)
            self.txt_log.see(tk.END)
            self.txt_log.config(state=tk.DISABLED)
        self.root.after(0, _append)

    def _modal(self, title, msg, buttons, accent=None):
        """
        Temaya uygun kucuk bir dialog gosterir, kullanici bir butona basana
        kadar bekler. buttons: [(etiket, deger), ...]. Secilen degeri dondurur.
        Native messagebox yerine bunu kullanmamizin sebebi: sistem dialogu
        (gri, temasiz) polisajli arayuzun icinde goze batiyordu.
        """
        dialog = ctk.CTkToplevel(self.root)
        dialog.title(title)
        dialog.configure(fg_color=COLOR_PANEL)
        dialog.resizable(False, False)
        dialog.transient(self.root)

        ctk.CTkLabel(
            dialog, text=msg, font=("Segoe UI", 12), text_color=COLOR_TEXT,
            wraplength=380, justify="left",
        ).pack(padx=24, pady=(24, 16))

        result = {"value": None}

        def choose(value):
            result["value"] = value
            dialog.destroy()

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(pady=(0, 20))
        for label, value in buttons:
            ctk.CTkButton(
                btn_row, text=label, width=100, command=lambda v=value: choose(v),
                fg_color=(accent or COLOR_ACCENT), hover_color=COLOR_ACCENT_HOVER,
            ).pack(side="left", padx=6)

        dialog.update_idletasks()
        dialog.geometry(f"+{self.root.winfo_rootx() + 80}+{self.root.winfo_rooty() + 100}")
        dialog.grab_set()
        self.root.wait_window(dialog)
        return result["value"]

    def _show_error(self, msg):
        self._modal("Hata", msg, [("Tamam", True)], accent=COLOR_ERR)

    def _show_info(self, msg):
        self._modal("Bilgi", msg, [("Tamam", True)])

    def _ask_yesno(self, title, msg):
        return bool(self._modal(title, msg, [("Evet", True), ("Hayır", False)]))

    def _clear_log(self):
        self.txt_log.config(state=tk.NORMAL)
        self.txt_log.delete("1.0", tk.END)
        self.txt_log.config(state=tk.DISABLED)
        self._set_progress(0)
        self.lbl_status.configure(text="Bekleniyor...")

    def _browse_key(self):
        path = filedialog.askopenfilename(
            title="SSH Anahtarı Seç",
            filetypes=[("PEM", "*.pem"), ("Tüm Dosyalar", "*.*")]
        )
        if path:
            self.entry_key.delete(0, tk.END)
            self.entry_key.insert(0, path)

    def _browse_out(self):
        path = filedialog.asksaveasfilename(
            title="İmaj Dosyası Kaydet",
            defaultextension=".raw",
            filetypes=[("Raw Image", "*.raw"), ("Tüm Dosyalar", "*.*")]
        )
        if path:
            self.entry_out.delete(0, tk.END)
            self.entry_out.insert(0, path)

    def _browse_file_out(self):
        """Dosya/klasor modunda cikti TEK dosya degil bir KLASOR -- birden
        fazla dosya goreli yapisiyla oraya yaziliyor (bkz. file_acquirer.py)."""
        path = filedialog.askdirectory(title="Çıktı Klasörü Seç")
        if path:
            self.entry_file_out.delete(0, tk.END)
            self.entry_file_out.insert(0, path)

    def _set_status(self, text):
        self.root.after(0, lambda: self.lbl_status.configure(text=text))

    def _set_progress(self, value):
        """value: 0-100 arasi. CTkProgressBar 0-1 bekledigi icin ayrica olcekliyoruz."""
        def _update():
            self.progress_var.set(value)
            self.progress.set(value / 100)
        self.root.after(0, _update)

    def _set_conn_indicator(self, connected):
        def _update():
            if connected:
                self.lbl_conn_status.config(text="● Bağlı", fg="#8fe38f")
            else:
                self.lbl_conn_status.config(text="● Bağlantı yok", fg="#f1c1c1")
        self.root.after(0, _update)

    def _parse_progress(self, text):
        """
        image_acquirer.py'den gelen 'İlerleme: %42 (8.4 GB / 20.0 GB)'
        satirini parse edip yuzdeyi dondurur.
        """
        # image_acquirer.py "%{pct:3d}" ile sabit genislik kullaniyor, bu da
        # tek/iki haneli yuzdelerde % ile sayi arasinda bosluk birakiyor
        # (orn. "% 42") -- ikinci \s* bu yuzden gerekli, aksi halde regex
        # hicbir zaman eslesmiyor ve ilerleme cubugu guncellenmiyordu.
        m = re.search(r"[İI]lerleme:\s*%?\s*(\d+(?:\.\d+)?)", text)
        if m:
            return float(m.group(1))
        return None

    def _on_stdout(self, text):
        """StdoutRedirector'dan gelen her satiri isler."""
        pct = self._parse_progress(text)
        if pct is not None:
            self._set_progress(pct)
            self._set_status(f"İlerleme: %{pct:.1f}")
        self._log(text.rstrip("\n"))

    # -- SSH Baglanti -------------------------------------------------------
    def _connect(self):
        host = self.entry_host.get().strip()
        port_str = self.entry_port.get().strip()
        port = int(port_str) if port_str else 22
        user = self.entry_user.get().strip()
        password = self.entry_pass.get().strip() or None
        key_path = self.entry_key.get().strip() or None

        if not host or not user:
            self._show_error("Host ve kullanıcı adı zorunlu.")
            return

        self._log(f"Bağlanılıyor: {user}@{host}:{port} ...", "info")
        self.ssh = SSHConnector(
            host=host, port=port, username=user,
            password=password, key_path=key_path, strict=True
        )

        if self.ssh.connect():
            self._log(f"[BAŞARILI] Bağlantı kuruldu: {host}:{port}", "ok")
            self._set_conn_indicator(True)
            self.disks_raw = self.ssh.list_disks() or ""
            self._log("--- Mevcut Diskler ---", "info")
            self._log(self.disks_raw, "plain")
            self._set_status("Bağlantı kuruldu, diskler listelendi.")
        else:
            self._show_error("SSH bağlantısı kurulamadı.\n"
                             "Bilgileri kontrol edin veya sunucunun açık olduğundan emin olun.")
            self._set_conn_indicator(False)
            self.ssh = None

    # -- Imaj Alma ----------------------------------------------------------
    def _start_acquisition(self):
        """acq_type_var'a gore disk mi dosya/klasor mu alinacagina karar verir."""
        if self.ssh is None or not self.ssh.is_active():
            self._show_error("Önce SSH bağlantısı kurun (Bağlan ve Diskleri Listele).")
            return
        if self.acq_type_var.get() == "disk":
            self._start_disk_acquisition()
        else:
            self._start_file_acquisition()

    def _start_disk_acquisition(self):
        disk = self.entry_disk.get().strip()
        out_path = self.entry_out.get().strip()
        mode = self.mode_var.get()
        password = self.entry_pass.get().strip() or None

        if not disk:
            self._show_error("Hedef disk yolu girin (örn. /dev/sdb).")
            return
        if not disk.startswith("/dev/"):
            disk = f"/dev/{disk}"
        if not out_path:
            self._show_error("İmaj çıktı yolu seçin.")
            return

        # Disk, listelenen disklerde gorunuyor mu? (main.py'nin select_disk
        # dogrulamasiyla ayni fikir — burada engellemiyor, sadece uyariyor,
        # cunku GUI kullanicisi listeyi kaydirmadan da dogru yazmis olabilir)
        disk_name = disk.replace("/dev/", "")
        if self.disks_raw and disk_name not in self.disks_raw:
            if not self._ask_yesno(
                "Disk listede yok",
                f"'{disk_name}' listelenen disklerde görünmüyor.\n"
                f"Yine de devam edilsin mi?"
            ):
                return

        # Butonu devre disi birak (cift tiklamayi onle)
        self.btn_acquire.configure(state=tk.DISABLED)
        self._stop_requested = False
        self._set_progress(0)
        self._set_status("İmaj alma başlıyor...")
        self._log(f"\n{'='*50}", "info")
        self._log(f"MOD: {mode.upper()} | DISK: {disk} | ÇIKTI: {out_path}", "info")
        self._log(f"{'='*50}", "info")

        # stdout'u yakalama
        self._old_stdout = sys.stdout
        sys.stdout = StdoutRedirector(self._on_stdout)

        # Arka planda calistir
        self._worker_thread = threading.Thread(
            target=self._acquisition_worker,
            args=(disk, out_path, mode, password),
            daemon=True
        )
        self._worker_thread.start()

    def _acquisition_worker(self, disk, out_path, mode, password):
        """Arka plan thread'i: imaj alma islemini yurutur."""
        try:
            # Yarim kalmis manifest kontrolu
            manifest_path = None
            resume_state = None
            start_block = 0

            mevcut = find_incomplete_manifest(disk)
            if mevcut:
                manifest_path, resume_state = mevcut
                completed = len(resume_state.get("acquired_blocks", []))
                total = resume_state.get("total_blocks", 0)

                self._log(f"[UYARI] Yarım kalan işlem bulundu: {completed}/{total} blok tamamlanmış.")

                devam = self._ask_yesno(
                    "Yarım Kalan İşlem",
                    f"Bu disk için yarım kalan bir işlem bulundu.\n"
                    f"Tamamlanan: {completed}/{total} blok\n"
                    f"Devam edilsin mi?"
                )
                if devam:
                    start_block = completed
                else:
                    manifest_path = None
                    resume_state = None

            # Write-block (sadece offline modda)
            apply_wb = (mode == "offline")

            # Imaj alma
            sonuc = acquire_disk_image(
                self.ssh,
                disk,
                password,
                output_dir=os.path.dirname(out_path) or ".",
                apply_write_blocker=apply_wb,
                total_blocks=resume_state["total_blocks"] if resume_state else None,
                start_block=start_block,
                resume_state=resume_state,
                manifest_path=manifest_path,
            )

            # Baglanti tamamen kesilirse resume_from ile doner
            while sonuc is not None and "resume_from" in sonuc:
                tekrar = self._ask_yesno(
                    "Bağlantı Koptu",
                    f"Bağlantı blok {sonuc['resume_from']}'de kesildi.\n"
                    f"Tekrar bağlanıp devam edilsin mi?"
                )
                if not tekrar:
                    self._log("[BİLGİ] İşlem yarım bırakıldı. Manifest korunuyor.")
                    break
                if not self.ssh.connect():
                    self._log("[HATA] SSH bağlantısı kurulamadı.")
                    break
                sonuc = acquire_disk_image(
                    self.ssh, disk, password,
                    output_dir=os.path.dirname(out_path) or ".",
                    apply_write_blocker=apply_wb,
                    total_blocks=sonuc["total_blocks"],
                    start_block=sonuc["resume_from"],
                    resume_state=sonuc,
                    manifest_path=sonuc.get("manifest_path"),
                )

            if sonuc is None:
                self._log("[HATA] İmaj alma başarısız oldu.")
                return

            if "resume_from" in sonuc:
                self._log("[BİLGİ] İşlem yarım kaldı. Daha sonra aynı diski seçip devam edebilirsiniz.")
                return

            # Bloklari birlestir. cleanup: sadece Live disinda (Offline'da)
            # kucuk parca dosyalari birlestirme sonrasi silinir -- Live modda
            # baglanti kopup devam etmek gerekebilir, parcalar resume icin lazim.
            self._log("\n[+] Bloklar birleştiriliyor...", "info")
            imaj_yolu = concatenate_blocks(
                sonuc["block_paths"],
                sonuc["total_blocks"],
                output_dir=sonuc["output_dir"],
                output_path=out_path,
                cleanup=(mode != "live"),
            )

            if imaj_yolu is None:
                self._log("[HATA] Eksik bloklar nedeniyle imaj birleştirilemedi.")
                return

            self._log(f"[BAŞARILI] İmaj birleştirildi: {imaj_yolu}")

            # Master hash
            master_hash = local_master_hash(imaj_yolu)
            self._log(f"[+] Yerel master SHA-256: {master_hash}", "info")
            self._set_status("İmaj alma tamamlandı.")
            self._set_progress(100)

            # Kullaniciya master hash dogrulama sor
            self.root.after(0, lambda: self._ask_verify(imaj_yolu))

        except Exception as exc:
            self._log(f"[HATA] Beklenmeyen hata: {exc}")
            import traceback
            self._log(traceback.format_exc(), "err")
        finally:
            sys.stdout = self._old_stdout  # stdout'u eski haline getir
            self.root.after(0, lambda: self.btn_acquire.configure(state=tk.NORMAL))

    # -- Dosya/Klasor Alma ----------------------------------------------------
    def _start_file_acquisition(self):
        remote_path = self.entry_remote_path.get().strip()
        out_dir = self.entry_file_out.get().strip()
        password = self.entry_pass.get().strip() or None

        if not remote_path:
            self._show_error("Uzak dosya/klasör yolu girin (örn. /home/user/belgeler).")
            return
        if not out_dir:
            self._show_error("Çıktı klasörü seçin.")
            return

        self.btn_acquire.configure(state=tk.DISABLED)
        self._set_progress(0)
        self._set_status("Dosya/klasör taranıyor...")
        self._log(f"\n{'='*50}", "info")
        self._log(f"UZAK YOL: {remote_path} | ÇIKTI: {out_dir}", "info")
        self._log(f"{'='*50}", "info")

        self._worker_thread = threading.Thread(
            target=self._file_acquisition_worker,
            args=(remote_path, out_dir, password),
            daemon=True,
        )
        self._worker_thread.start()

    def _file_acquisition_worker(self, remote_path, out_dir, password):
        """Arka plan thread'i: dosya/klasor alma islemini yurutur."""
        try:
            def ilerleme(done, total):
                pct = (done * 100 / total) if total else 0
                self._set_progress(pct)
                self._set_status(f"{done}/{total} dosya alındı (%{pct:.0f})")

            manifest = acquire_remote_tree(
                self.ssh, remote_path, out_dir, password=password, progress_callback=ilerleme,
            )

            if manifest is None:
                self._log(f"[HATA] Uzak yol bulunamadı: {remote_path}")
                self._set_status("Bulunamadı.")
                return

            basarili = len(manifest["acquired"])
            basarisiz = len(manifest["failed"])
            self._log(f"[BAŞARILI] {basarili}/{manifest['total_files']} dosya alındı ve doğrulandı.")
            if basarisiz:
                self._log(f"[UYARI] {basarisiz} dosya alınamadı:")
                for yol in manifest["failed"]:
                    self._log(f"  - {yol}", "plain")
            self._log(f"[+] Manifest: {os.path.join(out_dir, 'manifest_files.json')}", "info")
            self._set_status("Dosya/klasör alma tamamlandı.")
            self._set_progress(100)

        except Exception as exc:
            self._log(f"[HATA] Beklenmeyen hata: {exc}")
            import traceback
            self._log(traceback.format_exc(), "err")
        finally:
            self.root.after(0, lambda: self.btn_acquire.configure(state=tk.NORMAL))

    def _ask_verify(self, image_path):
        """Imaj alma bitince master hash dogrulama sor."""
        ans = self._ask_yesno(
            "Doğrulama",
            "İmaj alma tamamlandı.\n"
            "Uzak diskin SHA-256 hash'ini biliyor musunuz?\n"
            "(Biliyorsanız doğrulama yapılacak)"
        )
        if ans:
            self._verify_image_with_path(image_path)

    # -- Imaj Dogrulama -----------------------------------------------------
    def _verify_image(self):
        """Menu'den 'Imaj Dogrula' butonuna basilinca."""
        path = filedialog.askopenfilename(
            title="İmaj Dosyası Seç",
            filetypes=[("Raw Image", "*.raw"), ("Tüm Dosyalar", "*.*")]
        )
        if not path:
            return
        self._verify_image_with_path(path)

    def _verify_image_with_path(self, path):
        """Beklenen hash'i alip dogrulama yapar."""
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Hash Doğrulama")
        dialog.configure(fg_color=COLOR_PANEL)
        dialog.resizable(False, False)
        dialog.transient(self.root)

        ctk.CTkLabel(
            dialog, text="Beklenen SHA-256 (uzak diskin hash'i):", text_color=COLOR_TEXT,
        ).pack(padx=20, pady=(20, 6))
        entry_hash = ctk.CTkEntry(dialog, width=420)
        entry_hash.pack(padx=20, pady=5)
        entry_hash.focus_set()

        result = {"hash": None}

        def on_ok():
            result["hash"] = entry_hash.get().strip()
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=(10, 20))
        ctk.CTkButton(
            btn_frame, text="Doğrula", command=on_ok,
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_frame, text="İptal", command=on_cancel,
            fg_color=COLOR_PANEL, border_width=1, border_color=COLOR_BORDER,
            text_color=COLOR_TEXT, hover_color=COLOR_BG,
        ).pack(side="left", padx=5)
        dialog.bind("<Return>", lambda e: on_ok())

        dialog.update_idletasks()
        dialog.geometry(f"+{self.root.winfo_rootx() + 60}+{self.root.winfo_rooty() + 80}")
        dialog.grab_set()
        self.root.wait_window(dialog)

        expected = result["hash"]
        if not expected:
            return

        self._log(f"\n--- İmaj Doğrulama: {path} ---", "info")
        try:
            result_obj = verify_file(path, expected)
            coc.log_event(
                coc.EVENT_HASH_VERIFIED,
                f"İmaj doğrulandı: {path} ({result_obj.byte_count} bayt)",
                result_obj.digest,
            )
            self._log(f"[BAŞARILI] Doğrulama OK!")
            self._log(f"  SHA-256 : {result_obj.digest}", "plain")
            self._log(f"  Boyut   : {result_obj.byte_count} bayt", "plain")
            self._show_info("İmaj doğrulandı — kaynakla birebir aynı.")
        except HashMismatchError as exc:
            coc.log_event(
                coc.EVENT_HASH_MISMATCH,
                f"Doğrulama başarısız: {path}",
                exc.actual,
            )
            self._log(f"[HATA] Hash uyuşmazlığı!")
            self._log(f"  Beklenen: {exc.expected}", "plain")
            self._log(f"  Gerçek  : {exc.actual}", "plain")
            self._show_error("Hash uyuşmazlığı — imaj bozulmuş olabilir.")
        except (HashError, FileNotFoundError, OSError) as exc:
            coc.log_event(coc.EVENT_EXAM_ERROR, f"Doğrulama hatası: {exc}")
            self._log(f"[HATA] Doğrulama hatası: {exc}")
            self._show_error(f"Doğrulama hatası: {exc}")


# ---------------------------------------------------------------------------
# Program Girisi
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.title("SSH ile Uzak İmaj Al")
    root.geometry("900x780")
    root.minsize(760, 620)
    app = ForensicGUI(root)
    root.mainloop()
