"""
Chameleon ana secim ekrani.

Iki motor da (ssh_engine, ram_engine) artik kendi Python/CTk arayuzumuz
oldugu icin ayri pencere/subprocess acmiyoruz -- ayni pencerenin icinde
bir ekrandan digerine geciyoruz (bkz. _show_ssh_engine, _show_ram_engine,
_show_selection). RamImagerGUI.exe (vendor'in kendi WinForms programi)
artik hic kullanilmiyor; onun yerine RamImagerCLI.exe'yi dogrudan cagiran
engines/ram_engine/ram_gui.py kullaniliyor.
"""

import os
import sys

import customtkinter as ctk

SHARED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared")
sys.path.insert(0, SHARED_DIR)
sys.path.insert(0, os.path.join(SHARED_DIR, "i18n"))
from strings import t  # noqa: E402
import theme  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SSH_ENGINE_DIR = os.path.join(PROJECT_ROOT, "engines", "ssh_engine", "local_collector")
RAM_ENGINE_DIR = os.path.join(PROJECT_ROOT, "engines", "ram_engine")

ctk.set_appearance_mode("dark")


class ChameleonLauncher:
    def __init__(self, root):
        self.root = root
        self.lang = ctk.StringVar(value="tr")
        self.mode = ctk.StringVar(value=theme.get_mode())
        self.root.configure(fg_color=theme.BG_MAIN)
        self.content = None
        self._show_selection()

    def _clear(self):
        if self.content is not None:
            self.content.destroy()
        self.content = ctk.CTkFrame(self.root, fg_color=theme.BG_MAIN)
        self.content.pack(fill="both", expand=True)

    def _toggle_theme(self, _value=None):
        theme.set_mode(self.mode.get())
        ctk.set_appearance_mode(theme.get_mode())
        self.root.configure(fg_color=theme.BG_MAIN)
        self._show_selection()

    # -- Secim ekrani --------------------------------------------------
    def _show_selection(self):
        self._clear()
        lang = self.lang.get()
        self.root.title(t("title", lang))

        top = ctk.CTkFrame(self.content, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=(20, 0))

        ctk.CTkLabel(
            top, text=f"🦎 {t('title', lang)}", font=("Segoe UI", 22, "bold"),
            text_color=theme.TEXT_MAIN,
        ).pack(side="left")

        lang_switch = ctk.CTkSegmentedButton(
            top,
            values=["tr", "en"],
            variable=self.lang,
            command=lambda _: self._show_selection(),
            fg_color=theme.BG_PANEL,
            selected_color=theme.ACCENT,
            selected_hover_color=theme.ACCENT_HOVER,
            unselected_color=theme.BG_PANEL,
            text_color=theme.TEXT_MAIN,
        )
        lang_switch.pack(side="right")

        mode_switch = ctk.CTkSegmentedButton(
            top,
            values=["light", "dark"],
            variable=self.mode,
            command=self._toggle_theme,
            fg_color=theme.BG_PANEL,
            selected_color=theme.ACCENT,
            selected_hover_color=theme.ACCENT_HOVER,
            unselected_color=theme.BG_PANEL,
            text_color=theme.TEXT_MAIN,
        )
        mode_switch.pack(side="right", padx=(0, 10))

        ctk.CTkLabel(
            self.content, text=t("subtitle", lang), font=("Segoe UI", 13),
            text_color=theme.TEXT_SECONDARY,
        ).pack(anchor="w", padx=26, pady=(0, 18))

        self._engine_card(t("ssh_engine", lang), t("ssh_engine_desc", lang), self._show_ssh_engine)
        self._engine_card(t("ram_engine", lang), t("ram_engine_desc", lang), self._show_ram_engine)

        self.status_label = ctk.CTkLabel(
            self.content, text="", font=("Segoe UI", 11), text_color=theme.TEXT_SECONDARY
        )
        self.status_label.pack(anchor="w", padx=26, pady=(6, 16))

    def _engine_card(self, title, desc, command):
        card = ctk.CTkFrame(
            self.content, fg_color=theme.BG_PANEL, border_color=theme.BORDER,
            border_width=1, corner_radius=12,
        )
        card.pack(fill="x", padx=24, pady=6)

        text_col = ctk.CTkFrame(card, fg_color="transparent")
        text_col.pack(side="left", fill="both", expand=True, padx=16, pady=12)
        ctk.CTkLabel(
            text_col, text=title, font=("Segoe UI", 14, "bold"), text_color=theme.TEXT_MAIN,
            anchor="w",
        ).pack(fill="x")
        ctk.CTkLabel(
            text_col, text=desc, font=("Segoe UI", 11), text_color=theme.TEXT_SECONDARY,
            anchor="w",
        ).pack(fill="x")

        ctk.CTkButton(
            card, text="Aç", width=64, fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
            command=command,
        ).pack(side="right", padx=16)

    # -- SSH motoru: ayni pencerede goster -------------------------------
    def _show_ssh_engine(self):
        if SSH_ENGINE_DIR not in sys.path:
            sys.path.insert(0, SSH_ENGINE_DIR)
        try:
            from gui_v2 import ForensicGUI
        except ImportError as exc:
            self.status_label.configure(
                text=f"SSH motoru yuklenemedi: {exc}", text_color=theme.ERROR
            )
            return

        self._clear()
        # ForensicGUI artik kendi CTk widget'larini kuruyor, ayni tema
        # katmaninda kalmasi icin duz Frame yerine CTkFrame kullaniyoruz.
        inner = ctk.CTkFrame(self.content, fg_color=theme.BG_MAIN)
        inner.pack(fill="both", expand=True)
        ForensicGUI(inner, on_back=self._show_selection)

    # -- RAM motoru: ayni pencerede goster -------------------------------
    def _show_ram_engine(self):
        if RAM_ENGINE_DIR not in sys.path:
            sys.path.insert(0, RAM_ENGINE_DIR)
        try:
            from ram_gui import RamEngineGUI
        except ImportError as exc:
            self.status_label.configure(
                text=f"RAM motoru yuklenemedi: {exc}", text_color=theme.ERROR
            )
            return

        self._clear()
        inner = ctk.CTkFrame(self.content, fg_color=theme.BG_MAIN)
        inner.pack(fill="both", expand=True)
        RamEngineGUI(inner, on_back=self._show_selection)


if __name__ == "__main__":
    root = ctk.CTk()
    root.minsize(700, 500)
    ChameleonLauncher(root)
    # Pencere ciziminden hemen sonra cagrilirsa bazi ortamlarda gec
    # uygulaniyor; kisa bir after ile daha guvenilir calisiyor.
    root.after(10, lambda: root.state("zoomed"))
    root.mainloop()
