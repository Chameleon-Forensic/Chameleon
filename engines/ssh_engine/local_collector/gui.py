"""
gui.py
Adli Imaj Alma Sistemi v1.0 — Tkinter Grafik Arayuzu

Mevcut modulleri (ssh_connector, image_acquirer, hash_verifier, vb.)
hic degistirmeden kullanir. Imaj alma islemi arka planda (thread)
calisir, GUI donmaz.

Calistirmak icin:
    cd local_collector
    python gui.py

Gereksinim:
    pip install paramiko
"""

import getpass
import os
import re
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext

# Varsayilan imaj cikti yolu, script'in NEREDEN calistirildigina (cwd)
# degil, projenin kendi konumuna gore belirlenir. Aksi halde ("cwd" ile
# os.getcwd() kullanilirsa) program yanlislikla C:\Windows\System32 gibi
# bir dizinden baslatilirsa oraya yazmaya calisir ve "Permission denied"
# hatasi verir.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_IMAGE_PATH = os.path.join(PROJECT_ROOT, "images", "forensic_image.raw")

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
        self.root.geometry("850x750")
        self.root.minsize(700, 600)

        self.ssh = None
        self.disks_raw = ""
        self._worker_thread = None
        self._stop_requested = False

        if not PARAMIKO_OK:
            self._show_error(f"paramiko kurulu degil:\n{IMPORT_ERROR}\n\n"
                             f"Kurmak icin: pip install paramiko")
            return

        self._build_ui()
        self._log("Program basladi. SSH bilgilerini girin ve 'Baglan' tusuna basin.")

    # -- UI Olusturma -------------------------------------------------------
    def _build_ui(self):
        # === SSH Baglanti Paneli ===
        conn_frame = ttk.LabelFrame(self.root, text="SSH Baglanti Bilgileri", padding=10)
        conn_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(conn_frame, text="Host:").grid(row=0, column=0, sticky="w", pady=2)
        self.entry_host = ttk.Entry(conn_frame, width=28)
        self.entry_host.grid(row=0, column=1, padx=5, pady=2, sticky="w")
        self.entry_host.insert(0, "192.168.1.100")

        ttk.Label(conn_frame, text="Port:").grid(row=0, column=2, sticky="w", pady=2)
        self.entry_port = ttk.Entry(conn_frame, width=6)
        self.entry_port.grid(row=0, column=3, padx=5, pady=2, sticky="w")
        self.entry_port.insert(0, "22")

        ttk.Label(conn_frame, text="Kullanici:").grid(row=1, column=0, sticky="w", pady=2)
        self.entry_user = ttk.Entry(conn_frame, width=28)
        self.entry_user.grid(row=1, column=1, padx=5, pady=2, sticky="w")

        ttk.Label(conn_frame, text="Sifre:").grid(row=1, column=2, sticky="w", pady=2)
        self.entry_pass = ttk.Entry(conn_frame, width=15, show="*")
        self.entry_pass.grid(row=1, column=3, padx=5, pady=2, sticky="w")

        ttk.Label(conn_frame, text="SSH Anahtar:").grid(row=2, column=0, sticky="w", pady=2)
        self.entry_key = ttk.Entry(conn_frame, width=28)
        self.entry_key.grid(row=2, column=1, padx=5, pady=2, sticky="w")
        ttk.Button(conn_frame, text="Gozat", command=self._browse_key, width=8).grid(
            row=2, column=2, columnspan=2, pady=2, sticky="w"
        )

        ttk.Button(conn_frame, text="Baglan & Diskleri Listele", command=self._connect).grid(
            row=3, column=0, columnspan=4, pady=8
        )

        # === Hedef Disk & Mod Paneli ===
        disk_frame = ttk.LabelFrame(self.root, text="Hedef Disk ve Islem Modu", padding=10)
        disk_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(disk_frame, text="Disk (orn. /dev/sdb):").grid(row=0, column=0, sticky="w", pady=2)
        self.entry_disk = ttk.Entry(disk_frame, width=22)
        self.entry_disk.grid(row=0, column=1, padx=5, pady=2, sticky="w")

        self.mode_var = tk.StringVar(value="live")
        ttk.Radiobutton(disk_frame, text="Live Acquisition", variable=self.mode_var,
                        value="live").grid(row=0, column=2, padx=10, pady=2)
        ttk.Radiobutton(disk_frame, text="Offline Acquisition", variable=self.mode_var,
                        value="offline").grid(row=0, column=3, padx=10, pady=2)

        ttk.Label(disk_frame, text="Imaj Cikti Yolu:").grid(row=1, column=0, sticky="w", pady=2)
        self.entry_out = ttk.Entry(disk_frame, width=45)
        self.entry_out.grid(row=1, column=1, columnspan=2, padx=5, pady=2, sticky="w")
        self.entry_out.insert(0, DEFAULT_IMAGE_PATH)
        ttk.Button(disk_frame, text="Gozat", command=self._browse_out, width=8).grid(
            row=1, column=3, pady=2, sticky="w"
        )

        # === Butonlar ===
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=5)

        self.btn_acquire = ttk.Button(btn_frame, text="Imaj Almayi Baslat", command=self._start_acquisition)
        self.btn_acquire.pack(side="left", padx=5)

        ttk.Button(btn_frame, text="Imaj Dogrula", command=self._verify_image).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Log Temizle", command=self._clear_log).pack(side="right", padx=5)

        # === Ilerleme Cubugu ===
        prog_frame = ttk.Frame(self.root)
        prog_frame.pack(fill="x", padx=10, pady=2)
        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ttk.Progressbar(prog_frame, variable=self.progress_var,
                                       orient="horizontal", mode="determinate", length=400)
        self.progress.pack(fill="x", pady=2)
        self.lbl_status = ttk.Label(prog_frame, text="Bekleniyor...")
        self.lbl_status.pack(anchor="w")

        # === Log Ekrani ===
        log_frame = ttk.LabelFrame(self.root, text="Islem Logu", padding=5)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.txt_log = scrolledtext.ScrolledText(log_frame, height=18, wrap=tk.WORD,
                                                  font=("Consolas", 10))
        self.txt_log.pack(fill="both", expand=True)
        self.txt_log.config(state=tk.DISABLED)

    # -- Yardimci Metodlar --------------------------------------------------
    def _log(self, msg):
        """Log ekranina mesaj yazar (thread-safe)."""
        def _append():
            self.txt_log.config(state=tk.NORMAL)
            self.txt_log.insert(tk.END, msg + "\n")
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
        # Ilerleme satirini parse et
        pct = self._parse_progress(text)
        if pct is not None:
            self._set_progress(pct)
            self._set_status(f"Ilerleme: %{pct:.1f}")
        # Log ekranina yaz
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

        self._log(f"Baglaniliyor: {user}@{host}:{port} ...")
        self.ssh = SSHConnector(
            host=host, port=port, username=user,
            password=password, key_path=key_path, strict=True
        )

        if self.ssh.connect():
            self._log(f"[BASARILI] Baglanti kuruldu: {host}:{port}")
            self.disks_raw = self.ssh.list_disks() or ""
            self._log("--- Mevcut Diskler ---")
            self._log(self.disks_raw)
            self._set_status("Baglanti kuruldu, diskler listelendi.")
        else:
            self._show_error("SSH baglantisi kurulamadi.\n"
                             "Bilgileri kontrol edin veya sunucunun acik oldugundan emin olun.")
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

        # Butonu devre disi birak (cift tiklamayi onle)
        self.btn_acquire.config(state=tk.DISABLED)
        self._stop_requested = False
        self.progress_var.set(0)
        self._set_status("Imaj alma basliyor...")
        self._log(f"\n{'='*50}")
        self._log(f"MOD: {mode.upper()} | DISK: {disk} | CIKTI: {out_path}")
        self._log(f"{'='*50}")

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

                # GUI thread'inden sor (after ile)
                self._log(f"[UYARI] Yarim kalan islem bulundu: {completed}/{total} blok tamamlanmis.")

                # Kullaniciya sor (thread-safe degil ama messagebox thread-safe calisir)
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
            self._log("\n[+] Bloklar birlestiriliyor...")
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
            self._log(f"[+] Yerel master SHA-256: {master_hash}")
            self._set_status("Imaj alma tamamlandi.")
            self.progress_var.set(100)

            # Kullaniciya master hash dogrulama sor
            self.root.after(0, lambda: self._ask_verify(imaj_yolu))

        except Exception as exc:
            self._log(f"[HATA] Beklenmeyen hata: {exc}")
            import traceback
            self._log(traceback.format_exc())
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
        # Basit input dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("Hash Dogrulama")
        dialog.geometry("500x120")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Beklenen SHA-256 (uzak diskin hash'i):").pack(pady=5)
        entry_hash = ttk.Entry(dialog, width=70)
        entry_hash.pack(pady=5)

        result = {"hash": None}

        def on_ok():
            result["hash"] = entry_hash.get().strip()
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=5)
        ttk.Button(btn_frame, text="Dogrula", command=on_ok).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Iptal", command=on_cancel).pack(side="left", padx=5)

        self.root.wait_window(dialog)

        expected = result["hash"]
        if not expected:
            return

        self._log(f"\n--- Imaj Dogrulama: {path} ---")
        try:
            result_obj = verify_file(path, expected)
            coc.log_event(
                coc.EVENT_HASH_VERIFIED,
                f"Imaj dogrulandi: {path} ({result_obj.byte_count} bayt)",
                result_obj.digest,
            )
            self._log(f"[BASARILI] Dogrulama OK!")
            self._log(f"  SHA-256 : {result_obj.digest}")
            self._log(f"  Boyut   : {result_obj.byte_count} bayt")
            self._show_info("Imaj dogrulandi — kaynakla birebir ayni.")
        except HashMismatchError as exc:
            coc.log_event(
                coc.EVENT_HASH_MISMATCH,
                f"Dogrulama basarisiz: {path}",
                exc.actual,
            )
            self._log(f"[HATA] Hash uyusmazligi!")
            self._log(f"  Beklenen: {exc.expected}")
            self._log(f"  Gercek  : {exc.actual}")
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
