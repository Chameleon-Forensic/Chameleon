"""
Chameleon ana secim ekrani.

Iki motoru (ssh_engine, bitguard_engine) birbirine karistirmadan, her
birini kendi bagimsiz alt sureci (subprocess) olarak baslatir. Motorlerin
ic kodu HIC DEGISTIRILMEDEN calisir -- bu ekran sadece hangisinin
acilacagina karar veren ince bir secim katmani (bkz. docs/architecture.md).
"""

import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, messagebox

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared", "i18n")
)
from strings import t  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SSH_ENGINE_GUI = os.path.join(
    PROJECT_ROOT, "engines", "ssh_engine", "local_collector", "gui_v2.py"
)
BITGUARD_ENGINE_GUI = os.path.join(
    PROJECT_ROOT, "engines", "bitguard_engine", "forensic_gui.py"
)


class ChameleonLauncher:
    def __init__(self, root):
        self.root = root
        self.lang = tk.StringVar(value="tr")
        self._build_ui()

    def _build_ui(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        lang = self.lang.get()
        self.root.title(t("title", lang))

        frame = ttk.Frame(self.root, padding=20)
        frame.pack(fill="both", expand=True)

        lang_frame = ttk.Frame(frame)
        lang_frame.pack(anchor="ne")
        ttk.Label(lang_frame, text=t("choose_language", lang) + ":").pack(
            side="left", padx=(0, 5)
        )
        lang_combo = ttk.Combobox(
            lang_frame, textvariable=self.lang, values=["tr", "en"], width=5, state="readonly"
        )
        lang_combo.pack(side="left")
        lang_combo.bind("<<ComboboxSelected>>", lambda e: self._build_ui())

        ttk.Label(
            frame, text=t("choose_engine", lang), font=("Segoe UI", 12, "bold")
        ).pack(pady=(20, 10))

        ttk.Button(
            frame,
            text=t("ssh_engine", lang),
            width=45,
            command=lambda: self._launch(SSH_ENGINE_GUI, "ssh_engine"),
        ).pack(pady=5)

        ttk.Button(
            frame,
            text=t("bitguard_engine", lang),
            width=45,
            command=lambda: self._launch(BITGUARD_ENGINE_GUI, "bitguard_engine"),
        ).pack(pady=5)

    def _launch(self, script_path, engine_name):
        lang = self.lang.get()
        if not os.path.isfile(script_path):
            messagebox.showerror("Chameleon", f"Dosya bulunamadi: {script_path}")
            return
        try:
            subprocess.Popen([sys.executable, script_path], cwd=os.path.dirname(script_path))
            print(f"[chameleon] {engine_name} {t('launched', lang)}")
        except OSError as exc:
            messagebox.showerror("Chameleon", f"{t('error_launch', lang)} {exc}")


if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("420x260")
    ChameleonLauncher(root)
    root.mainloop()
