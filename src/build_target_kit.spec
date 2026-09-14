# -*- mode: python ; coding: utf-8 -*-
"""
build_target_kit.spec
Chameleon'un SADECE hedef-taraf (Bu Cihaz Inceleniyor) modunu iceren,
sahaya goturulecek daha hafif/kafa karistirmayan bir pakete cikarir --
bkz. docs/roadmap.md. build.spec (operator icin tam paket) ile AYNI
chameleon_gui.py'yi kullanir (bkz. launcher/target_kit_main.py), ama
operator-only kodu (ssh_engine/local_collector, ram_engine) HIC
paketlemez -- ne SSH/RAM arac seti sahadaki teknik bilgisi olmayan
kisinin karsisina cikar, ne de paramiko/RamImagerCLI.exe gereksiz yere
disk kaplar.

ONEDIR (build.spec'in aksine, kasitli): bu exe delil/hedef cihazinda
calisiyor. Onefile her calistirmada tum icerigi %TEMP%\\_MEIxxxxx'e acip
sonra siler -- delil cihazina gereksiz gecici dosya yazip silmek, adli
butunluk/Locard prensibi acisindan istenmeyen bir ayak izi. Onedir
bulundugu klasorden dogrudan calisir, evidence makinesine ekstra yazma
yapmaz. Dagitim icin klasor ZIP'lenip sahaya goturulur (kullanici karari,
docs/roadmap.md).

Derlemek icin (repo kok dizininden):
    C:\\venv312\\Scripts\\python.exe -m PyInstaller build_target_kit.spec

Cikti: dist/ChameleonHedefKiti/ (klasor) icinde ChameleonHedefKiti.exe +
_internal/ -- operatorun kullandigi dist/Chameleon.exe'den (onefile,
tek dosya, degismedi) BAGIMSIZ, ayri bir cikti.
"""
import os

ROOT = os.path.abspath(SPECPATH)

datas = [
    (os.path.join(ROOT, "shared"), "shared"),
    (os.path.join(ROOT, "engines", "portable_kit", "tor_manager.py"), "engines/portable_kit"),
]

a = Analysis(
    [os.path.join(ROOT, "launcher", "target_kit_main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "stem", "stem.control", "stem.process", "stem.response", "stem.response.add_onion",
        "cryptography",
        "cryptography.hazmat.primitives.asymmetric.x25519",
        # ui_kit/icons.py (veri dosyasi olarak yuklenen shared/ altinda)
        # QSvgRenderer kullaniyor -- entry script'in dogrudan importlarinda
        # gorunmedigi icin PyInstaller bunu otomatik bulamiyor (bkz.
        # build.spec'teki AYNI not).
        "PySide6.QtSvg",
        # shared/tz_display.py'nin kullandigi zoneinfo (stdlib) icin AYNI
        # sorun -- bkz. build.spec'teki not.
        "zoneinfo",
        # shared/forensic_report.py'nin kullandigi html (stdlib) icin AYNI
        # sorun -- bkz. build.spec'teki not.
        "html",
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
    [],
    exclude_binaries=True,
    name="ChameleonHedefKiti",
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

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ChameleonHedefKiti",
)
