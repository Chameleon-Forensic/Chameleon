"""
gui_v2.py
Adli Imaj Alma Sistemi v1.0 — Tkinter Grafik Arayuzu (gelistirilmis gorunum)

gui.py ile AYNI backend mantigini kullanir (mevcut modullere hic
dokunmadan, ayni SSHConnector/image_acquirer/hash_verifier cagrilari).
Fark sadece gorsel: tema, renkli log satirlari, zaman damgali log,
baglanti durumu gostergesi, hedef diskin listede olup olmadigini
kontrol eden bir uyari.

Calistirmak icin:
    cd local_collector
    python gui_v2.py

Gereksinim:
    pip install paramiko
"""

import datetime
import getpass
import os
import re
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext

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
    from hash_verifier import verify_file, HashMismatchError, HashError
    import chain_of_custody as coc
    PARAMIKO_OK = True
except ImportError as exc:
    PARAMIKO_OK = False
    IMPORT_ERROR = str(exc)


# ---------------------------------------------------------------------------
# Renk paleti
# ---------------------------------------------------------------------------
COLOR_BG = "#f4f6f8"
COLOR_ACCENT = "#2c5f8a"
COLOR_OK = "#1e7e34"
COLOR_ERR = "#c0392b"
COLOR_WARN = "#b7791f"
COLOR_INFO = "#2c3e50"


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
    def __init__(self, root):
        self.root = root
        self.root.title("Adli Imaj Alma Sistemi v1.0")
        self.root.geometry("900x780")
        self.root.minsize(760, 620)
        self.root.configure(bg=COLOR_BG)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=COLOR_BG, font=("Segoe UI", 10))
        style.configure("TLabelframe", background=COLOR_BG, font=("Segoe UI", 10, "bold"))
        style.configure("TLabelframe.Label", background=COLOR_BG, foreground=COLOR_ACCENT,
                         font=("Segoe UI", 10, "bold"))
        style.configure("TFrame", background=COLOR_BG)
        style.configure("TLabel", background=COLOR_BG)
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 9, "italic"), foreground=COLOR_INFO)

        self.ssh = None
        self.disks_raw = ""
        self._worker_thread = None
        self._stop_requested = False

        if not PARAMIKO_OK:
            self._show_error(f"paramiko kurulu degil:\n{IMPORT_ERROR}\n\n"
                             f"Kurmak icin: pip install paramiko")
            return

        self._build_ui()
        self._log("Program basladi. SSH bilgilerini girin ve 'Baglan' tusuna basin.", "info")

    # -- UI Olusturma -------------------------------------------------------
    def _build_ui(self):
        # === Baslik seridi ===
        header = tk.Frame(self.root, bg=COLOR_ACCENT, height=48)
        header.pack(fill="x")
        tk.Label(header, text="🛡  Adli Imaj Alma Sistemi", bg=COLOR_ACCENT, fg="white",
                 font=("Segoe UI", 14, "bold")).pack(side="left", padx=15, pady=8)
        self.lbl_conn_status = tk.Label(header, text="● Baglanti yok", bg=COLOR_ACCENT,
                                         fg="#f1c1c1", font=("Segoe UI", 10, "bold"))
        self.lbl_conn_status.pack(side="right", padx=15)

        # === SSH Baglanti Paneli ===
        conn_frame = ttk.LabelFrame(self.root, text="SSH Baglanti Bilgileri", padding=10)
        conn_frame.pack(fill="x", padx=12, pady=(10, 5))

        ttk.Label(conn_frame, text="Host:").grid(row=0, column=0, sticky="w", pady=3)
        self.entry_host = ttk.Entry(conn_frame, width=28)
        self.entry_host.grid(row=0, column=1, padx=5, pady=3, sticky="w")
        self.entry_host.insert(0, "192.168.1.100")

        ttk.Label(conn_frame, text="Port:").grid(row=0, column=2, sticky="w", pady=3)
        self.entry_port = ttk.Entry(conn_frame, width=6)
        self.entry_port.grid(row=0, column=3, padx=5, pady=3, sticky="w")
        self.entry_port.insert(0, "22")

        ttk.Label(conn_frame, text="Kullanici:").grid(row=1, column=0, sticky="w", pady=3)
        self.entry_user = ttk.Entry(conn_frame, width=28)
        self.entry_user.grid(row=1, column=1, padx=5, pady=3, sticky="w")

        ttk.Label(conn_frame, text="Sifre:").grid(row=1, column=2, sticky="w", pady=3)
        self.entry_pass = ttk.Entry(conn_frame, width=15, show="*")
        self.entry_pass.grid(row=1, column=3, padx=5, pady=3, sticky="w")

        ttk.Label(conn_frame, text="SSH Anahtar:").grid(row=2, column=0, sticky="w", pady=3)
        self.entry_key = ttk.Entry(conn_frame, width=28)
        self.entry_key.grid(row=2, column=1, padx=5, pady=3, sticky="w")
        ttk.Button(conn_frame, text="Gozat", command=self._browse_key, width=8).grid(
            row=2, column=2, columnspan=2, pady=3, sticky="w"
        )

        ttk.Button(conn_frame, text="🔌 Baglan & Diskleri Listele", style="Accent.TButton",
                   command=self._connect).grid(row=3, column=0, columnspan=4, pady=8)

        # === Hedef Disk & Mod Paneli ===
        disk_frame = ttk.LabelFrame(self.root, text="Hedef Disk ve Islem Modu", padding=10)
        disk_frame.pack(fill="x", padx=12, pady=5)

        ttk.Label(disk_frame, text="Disk (orn. /dev/sdb):").grid(row=0, column=0, sticky="w", pady=3)
        self.entry_disk = ttk.Entry(disk_frame, width=22)
        self.entry_disk.grid(row=0, column=1, padx=5, pady=3, sticky="w")

        self.mode_var = tk.StringVar(value="live")
        ttk.Radiobutton(disk_frame, text="🟢 Live Acquisition", variable=self.mode_var,
                        value="live").grid(row=0, column=2, padx=10, pady=3)
        ttk.Radiobutton(disk_frame, text="🔒 Offline Acquisition", variable=self.mode_var,
                        value="offline").grid(row=0, column=3, padx=10, pady=3)

        ttk.Label(disk_frame, text="Imaj Cikti Yolu:").grid(row=1, column=0, sticky="w", pady=3)
        self.entry_out = ttk.Entry(disk_frame, width=45)
        self.entry_out.grid(row=1, column=1, columnspan=2, padx=5, pady=3, sticky="w")
        self.entry_out.insert(0, os.path.join(os.getcwd(), "forensic_image.raw"))
        ttk.Button(disk_frame, text="Gozat", command=self._browse_out, width=8).grid(
            row=1, column=3, pady=3, sticky="w"
        )

        # === Butonlar ===
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=12, pady=6)

        self.btn_acquire = ttk.Button(btn_frame, text="▶  Imaj Almayi Baslat",
                                       style="Accent.TButton", command=self._start_acquisition)
        self.btn_acquire.pack(side="left", padx=5)

        ttk.Button(btn_frame, text="✓ Imaj Dogrula", command=self._verify_image).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="🗑 Log Temizle", command=self._clear_log).pack(side="right", padx=5)

        # === Ilerleme Cubugu ===
        prog_frame = ttk.Frame(self.root)
        prog_frame.pack(fill="x", padx=12, pady=2)
        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ttk.Progressbar(prog_frame, variable=self.progress_var,
                                       orient="horizontal", mode="determinate", length=400)
        self.progress.pack(fill="x", pady=2)
        self.lbl_status = ttk.Label(prog_frame, text="Bekleniyor...", style="Status.TLabel")
        self.lbl_status.pack(anchor="w")

        # === Log Ekrani ===
        log_frame = ttk.LabelFrame(self.root, text="Islem Logu", padding=5)
        log_frame.pack(fill="both", expand=True, padx=12, pady=(5, 10))

        self.txt_log = scrolledtext.ScrolledText(log_frame, height=18, wrap=tk.WORD,
                                                  font=("Consolas", 10), bg="#1e1e1e", fg="#dcdcdc",
                                                  insertbackground="white")
        self.txt_log.pack(fill="both", expand=True)
        self.txt_log.tag_config("ok", foreground="#5fd77f")
        self.txt_log.tag_config("err", foreground="#ff6b6b")
        self.txt_log.tag_config("warn", foreground="#f0c674")
        self.txt_log.tag_config("info", foreground="#8ab4f8")
        self.txt_log.tag_config("plain", foreground="#dcdcdc")
        self.txt_log.config(state=tk.DISABLED)

    # -- Yardimci Metodlar --------------------------------------------------
    def _detect_tag(self, msg):
        if "[BASARILI]" in msg or "BASARILI" in msg:
            return "ok"
        if "[HATA]" in msg or "HATA" in msg:
            return "err"
        if "[UYARI]" in msg or "[BILGI]" in msg:
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

    def _show_error(self, msg):
        messagebox.showerror("Hata", msg)

    def _show_info(self, msg):
        messagebox.showinfo("Bilgi", msg)

    def _ask_yesno(self, title, msg):
        return messagebox.askyesno(title, msg)

    def _clear_log(self):
        self.txt_log.config(state=tk.NORMAL)
        self.txt_log.delete("1.0", tk.END)
        self.txt_log.config(state=tk.DISABLED)
        self.progress_var.set(0)
        self.lbl_status.config(text="Bekleniyor...")

    def _browse_key(self):
        path = filedialog.askopenfilename(
            title="SSH Anahtar Sec",
            filetypes=[("PEM", "*.pem"), ("Tum Dosyalar", "*.*")]
        )
        if path:
            self.entry_key.delete(0, tk.END)
            self.entry_key.insert(0, path)

    def _browse_out(self):
        path = filedialog.asksaveasfilename(
            title="Imaj Dosyasi Kaydet",
            defaultextension=".raw",
            filetypes=[("Raw Image", "*.raw"), ("Tum Dosyalar", "*.*")]
        )
        if path:
            self.entry_out.delete(0, tk.END)
            self.entry_out.insert(0, path)

    def _set_status(self, text):
        self.root.after(0, lambda: self.lbl_status.config(text=text))

    def _set_progress(self, value):
        self.root.after(0, lambda: self.progress_var.set(value))

    def _set_conn_indicator(self, connected):
        def _update():
            if connected:
                self.lbl_conn_status.config(text="● Bagli", fg="#8fe38f")
            else:
                self.lbl_conn_status.config(text="● Baglanti yok", fg="#f1c1c1")
        self.root.after(0, _update)

    def _parse_progress(self, text):
        """
        image_acquirer.py'den gelen 'Ilerleme: %42 (8.4 GB / 20.0 GB)'
        satirini parse edip yuzdeyi dondurur.
        """
        m = re.search(r"Ilerleme:\s*%?(\d+(?:\.\d+)?)", text)
        if m:
            return float(m.group(1))
        return None

    def _on_stdout(self, text):
        """StdoutRedirector'dan gelen her satiri isler."""
        pct = self._parse_progress(text)
        if pct is not None:
            self._set_progress(pct)
            self._set_status(f"Ilerleme: %{pct:.1f}")
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
            self._show_error("Host ve kullanici adi zorunlu.")
            return

        self._log(f"Baglaniliyor: {user}@{host}:{port} ...", "info")
        self.ssh = SSHConnector(
            host=host, port=port, username=user,
            password=password, key_path=key_path, strict=True
        )

        if self.ssh.connect():
            self._log(f"[BASARILI] Baglanti kuruldu: {host}:{port}", "ok")
            self._set_conn_indicator(True)
            self.disks_raw = self.ssh.list_disks() or ""
            self._log("--- Mevcut Diskler ---", "info")
            self._log(self.disks_raw, "plain")
            self._set_status("Baglanti kuruldu, diskler listelendi.")
        else:
            self._show_error("SSH baglantisi kurulamadi.\n"
                             "Bilgileri kontrol edin veya sunucunun acik oldugundan emin olun.")
            self._set_conn_indicator(False)
            self.ssh = None

    # -- Imaj Alma ----------------------------------------------------------
    def _start_acquisition(self):
        if self.ssh is None or not self.ssh.is_active():
            self._show_error("Once SSH baglantisi kurun (Baglan & Diskleri Listele).")
            return

        disk = self.entry_disk.get().strip()
        out_path = self.entry_out.get().strip()
        mode = self.mode_var.get()
        password = self.entry_pass.get().strip() or None

        if not disk:
            self._show_error("Hedef disk yolu girin (orn. /dev/sdb).")
            return
        if not disk.startswith("/dev/"):
            disk = f"/dev/{disk}"
        if not out_path:
            self._show_error("Imaj cikti yolu secin.")
            return

        # Disk, listelenen disklerde gorunuyor mu? (main.py'nin select_disk
        # dogrulamasiyla ayni fikir — burada engellemiyor, sadece uyariyor,
        # cunku GUI kullanicisi listeyi kaydirmadan da dogru yazmis olabilir)
        disk_name = disk.replace("/dev/", "")
        if self.disks_raw and disk_name not in self.disks_raw:
            if not self._ask_yesno(
                "Disk listede yok",
                f"'{disk_name}' listelenen disklerde gorunmuyor.\n"
                f"Yine de devam edilsin mi?"
            ):
                return

        # Butonu devre disi birak (cift tiklamayi onle)
        self.btn_acquire.config(state=tk.DISABLED)
        self._stop_requested = False
        self.progress_var.set(0)
        self._set_status("Imaj alma basliyor...")
        self._log(f"\n{'='*50}", "info")
        self._log(f"MOD: {mode.upper()} | DISK: {disk} | CIKTI: {out_path}", "info")
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

                self._log(f"[UYARI] Yarim kalan islem bulundu: {completed}/{total} blok tamamlanmis.")

                devam = self._ask_yesno(
                    "Yarim Kalan Islem",
                    f"Bu disk icin yarim kalan bir islem bulundu.\n"
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
                    "Baglanti Koptu",
                    f"Baglanti blok {sonuc['resume_from']}'de kesildi.\n"
                    f"Tekrar baglanip devam edilsin mi?"
                )
                if not tekrar:
                    self._log("[BILGI] Islem yarim birakildi. Manifest korunuyor.")
                    break
                if not self.ssh.connect():
                    self._log("[HATA] SSH baglantisi kurulamadi.")
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
                self._log("[HATA] Imaj alma basarisiz oldu.")
                return

            if "resume_from" in sonuc:
                self._log("[BILGI] Islem yarim kaldi. Daha sonra ayni diski secip devam edebilirsiniz.")
                return

            # Bloklari birlestir
            self._log("\n[+] Bloklar birlestiriliyor...", "info")
            imaj_yolu = concatenate_blocks(
                sonuc["block_paths"],
                sonuc["total_blocks"],
                output_dir=sonuc["output_dir"],
                output_path=out_path,
            )

            if imaj_yolu is None:
                self._log("[HATA] Eksik bloklar nedeniyle imaj birlestirilemedi.")
                return

            self._log(f"[BASARILI] Imaj birlestirildi: {imaj_yolu}")

            # Master hash
            master_hash = local_master_hash(imaj_yolu)
            self._log(f"[+] Yerel master SHA-256: {master_hash}", "info")
            self._set_status("Imaj alma tamamlandi.")
            self.progress_var.set(100)

            # Kullaniciya master hash dogrulama sor
            self.root.after(0, lambda: self._ask_verify(imaj_yolu))

        except Exception as exc:
            self._log(f"[HATA] Beklenmeyen hata: {exc}")
            import traceback
            self._log(traceback.format_exc(), "err")
        finally:
            sys.stdout = self._old_stdout  # stdout'u eski haline getir
            self.root.after(0, lambda: self.btn_acquire.config(state=tk.NORMAL))

    def _ask_verify(self, image_path):
        """Imaj alma bitince master hash dogrulama sor."""
        ans = self._ask_yesno(
            "Dogrulama",
            "Imaj alma tamamlandi.\n"
            "Uzak diskin SHA-256 hash'ini biliyor musunuz?\n"
            "(Biliyorsaniz dogrulama yapilacak)"
        )
        if ans:
            self._verify_image_with_path(image_path)

    # -- Imaj Dogrulama -----------------------------------------------------
    def _verify_image(self):
        """Menu'den 'Imaj Dogrula' butonuna basilinca."""
        path = filedialog.askopenfilename(
            title="Imaj Dosyasi Sec",
            filetypes=[("Raw Image", "*.raw"), ("Tum Dosyalar", "*.*")]
        )
        if not path:
            return
        self._verify_image_with_path(path)

    def _verify_image_with_path(self, path):
        """Beklenen hash'i alip dogrulama yapar."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Hash Dogrulama")
        dialog.geometry("500x130")
        dialog.configure(bg=COLOR_BG)
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Beklenen SHA-256 (uzak diskin hash'i):").pack(pady=8)
        entry_hash = ttk.Entry(dialog, width=70)
        entry_hash.pack(pady=5)
        entry_hash.focus_set()

        result = {"hash": None}

        def on_ok():
            result["hash"] = entry_hash.get().strip()
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=8)
        ttk.Button(btn_frame, text="Dogrula", style="Accent.TButton", command=on_ok).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Iptal", command=on_cancel).pack(side="left", padx=5)
        dialog.bind("<Return>", lambda e: on_ok())

        self.root.wait_window(dialog)

        expected = result["hash"]
        if not expected:
            return

        self._log(f"\n--- Imaj Dogrulama: {path} ---", "info")
        try:
            result_obj = verify_file(path, expected)
            coc.log_event(
                coc.EVENT_HASH_VERIFIED,
                f"Imaj dogrulandi: {path} ({result_obj.byte_count} bayt)",
                result_obj.digest,
            )
            self._log(f"[BASARILI] Dogrulama OK!")
            self._log(f"  SHA-256 : {result_obj.digest}", "plain")
            self._log(f"  Boyut   : {result_obj.byte_count} bayt", "plain")
            self._show_info("Imaj dogrulandi — kaynakla birebir ayni.")
        except HashMismatchError as exc:
            coc.log_event(
                coc.EVENT_HASH_MISMATCH,
                f"Dogrulama basarisiz: {path}",
                exc.actual,
            )
            self._log(f"[HATA] Hash uyusmazligi!")
            self._log(f"  Beklenen: {exc.expected}", "plain")
            self._log(f"  Gercek  : {exc.actual}", "plain")
            self._show_error("Hash uyusmazligi — imaj bozulmus olabilir.")
        except (HashError, FileNotFoundError, OSError) as exc:
            coc.log_event(coc.EVENT_EXAM_ERROR, f"Dogrulama hatasi: {exc}")
            self._log(f"[HATA] Dogrulama hatasi: {exc}")
            self._show_error(f"Dogrulama hatasi: {exc}")


# ---------------------------------------------------------------------------
# Program Girisi
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = ForensicGUI(root)
    root.mainloop()
