"""
Chameleon launcher'i icin basit dil tablosu.
Motorlerin (ssh_engine, bitguard_engine) kendi ic arayuz metinleri
HENUZ buna bagli degil -- bu ilk asamada sadece launcher/chameleon_gui.py
kullaniyor (bkz. docs/roadmap.md, "Coklu dil destegi" maddesi).
"""

STRINGS = {
    "tr": {
        "title": "Chameleon - Adli Imaj Alma Araci",
        "choose_language": "Dil",
        "choose_engine": "Yontem secin:",
        "ssh_engine": "SSH Motoru (uzak Linux, dd tabanli)",
        "bitguard_engine": "BitGuard Motoru (TLS soket, client/server)",
        "launch": "Baslat",
        "launched": "baslatildi.",
        "error_launch": "Baslatilamadi:",
    },
    "en": {
        "title": "Chameleon - Forensic Imaging Tool",
        "choose_language": "Language",
        "choose_engine": "Choose method:",
        "ssh_engine": "SSH Engine (remote Linux, dd-based)",
        "bitguard_engine": "BitGuard Engine (TLS socket, client/server)",
        "launch": "Launch",
        "launched": "launched.",
        "error_launch": "Failed to launch:",
    },
}


def t(key, lang="tr"):
    return STRINGS.get(lang, STRINGS["tr"]).get(key, key)
