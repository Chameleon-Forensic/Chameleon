"""
Chameleon launcher'i icin basit dil tablosu.
Motorlerin (ssh_engine, ram_engine) kendi ic arayuz metinleri HENUZ buna
bagli degil -- bu ilk asamada sadece launcher/chameleon_gui.py kullaniyor.
"""

STRINGS = {
    "tr": {
        "title": "Chameleon",
        "subtitle": "Digital Forensics Acquisition Engine",
        "choose_language": "Dil",
        "choose_engine": "Yöntem seç",
        "ssh_engine": "SSH ile uzak imaj al",
        "ssh_engine_desc": "Linux veya Windows hedefe SSH ile bağlanıp disk/dosya imajı alır",
        "ram_engine": "RAM imajı al (Windows, yerel)",
        "ram_engine_desc": "Bu makinede çalışır, uzak bağlantı gerekmez",
        "launched": "açıldı.",
        "error_launch": "Başlatılamadı, dosya bulunamadı mı diye kontrol et:",
        "missing_file": "Bu dosya olması gereken yerde değil:",
    },
    "en": {
        "title": "Chameleon",
        "subtitle": "Digital Forensics Acquisition Engine",
        "choose_language": "Language",
        "choose_engine": "Choose method",
        "ssh_engine": "Remote image over SSH",
        "ssh_engine_desc": "Connects to a Linux or Windows target over SSH, images disk/files",
        "ram_engine": "RAM image (Windows, local)",
        "ram_engine_desc": "Runs on this machine, no remote connection needed",
        "launched": "started.",
        "error_launch": "Couldn't start it, check if the file is missing:",
        "missing_file": "This file isn't where it should be:",
    },
}


def t(key, lang="tr"):
    return STRINGS.get(lang, STRINGS["tr"]).get(key, key)
