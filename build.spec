# -*- mode: python ; coding: utf-8 -*-
"""
build.spec
Chameleon'u tek bir Chameleon.exe'ye paketler (PyInstaller). Arayuz
PySide6 (customtkinter'dan tamamen gecildi, eski dosyalar kaldirildi --
bkz. C:\\Users\\yasar\\.claude\\plans\\jazzy-frolicking-rivest.md).

Neden ozel bir spec dosyasi gerekiyor: ssh_engine/ram_engine modulleri
(gui_v2.py, ram_gui.py, image_acquirer.py, ui_kit/* vb.) chameleon_gui.py
tarafindan CALISMA ANINDA sys.path'e eklenip duz "import X" ile
yukleniyor (bkz. launcher/chameleon_gui.py _open_ssh_engine/
_open_ram_engine, ve dosyalarin kendi ui_kit import'u). PyInstaller bu tur
dinamik importlari otomatik kesfedemez. Cozum: onlari derlenmis modul
olarak degil, KAYNAK AGACIYLA BIREBIR AYNI GORECELI YERLESIMDE veri
(data) dosyasi olarak paketlemek -- boylece calisma aninda mevcut
sys.path.insert()+import deseni HICBIR KOD DEGISIKLIGI GEREKMEDEN aynen
calismaya devam ediyor (launcher/chameleon_gui.py'deki PROJECT_ROOT
hesaplamasi frozen modda sys._MEIPASS'a bakiyor). Ayni sebeple, bu
dinamik-yuklenen dosyalarin ihtiyac duydugu bazi alt modulleri (orn.
PySide6.QtSvg, sadece ui_kit/icons.py icinde kullaniliyor) PyInstaller
statik analizle GOREMEDIGI icin hiddenimports'a elle eklemek gerekiyor --
bu tuzaga bir kez dusuldu (bkz. docs/hatalar_ve_sonuclar.md, eskiden
tkinter.scrolledtext icin), ayni dikkat burada da gerekli.

Derlemek icin (repo kok dizininden, PySide6'nin kurulu oldugu Python ile --
bu makinede uzun yol destegi kapali oldugundan C:\\venv312 kullanildi):
    C:\\venv312\\Scripts\\python.exe -m PyInstaller build.spec

Cikti: dist/Chameleon.exe (tek dosya -- Tor binary + stem + cryptography +
PySide6 + paramiko hepsi gomulu).
"""
import os

ROOT = os.path.abspath(SPECPATH)

datas = [
    (os.path.join(ROOT, "shared"), "shared"),
    (os.path.join(ROOT, "engines", "ssh_engine", "local_collector"), "engines/ssh_engine/local_collector"),
    (os.path.join(ROOT, "engines", "ram_engine", "ram_gui.py"), "engines/ram_engine"),
    (os.path.join(ROOT, "engines", "ram_engine", "cli"), "engines/ram_engine/cli"),
    (os.path.join(ROOT, "engines", "ram_engine", "driver"), "engines/ram_engine/driver"),
    (os.path.join(ROOT, "engines", "portable_kit", "tor_manager.py"), "engines/portable_kit"),
]

a = Analysis(
    [os.path.join(ROOT, "launcher", "chameleon_gui.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "paramiko",
        "stem", "stem.control", "stem.process", "stem.response", "stem.response.add_onion",
        "cryptography",
        "cryptography.hazmat.primitives.asymmetric.x25519",
        # ui_kit/icons.py (veri dosyasi olarak yuklenen shared/ altinda,
        # bkz. yukaridaki aciklama) QSvgRenderer kullaniyor -- entry
        # script'in dogrudan importlarinda gorunmedigi icin PyInstaller
        # bunu otomatik bulamiyor.
        "PySide6.QtSvg",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Chameleon",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, "shared", "assets", "chameleon.ico"),
)
