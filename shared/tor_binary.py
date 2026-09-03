"""
tor_binary.py
Gomulu Tor binary'sinin nerede oldugunu bulan tek, ortak yer -- hem
tasinabilir kit (engines/portable_kit/tor_manager.py) hem operator
tarafi (engines/ssh_engine/local_collector/tor_client.py) AYNI binary'yi
kullanir, iki kopya tutulmaz.

Yol koda gomulu DEGIL: CHAMELEON_TOR_BINARY ortam degiskeni ya da
shared/bin/tor/<platform>/tor(.exe) varsayilani kullanilir. Boylece Tor'u
ileride (guvenlik guncellemesi, yeni surum) degistirmek icin sadece o
dosyayi degistirmek yeterli olur -- kod degismesi gerekmez.
"""
import os
import platform

SHARED_DIR = os.path.dirname(os.path.abspath(__file__))


def default_tor_binary_path():
    """
    CHAMELEON_TOR_BINARY tanimliysa onu kullanir; yoksa shared/bin/tor/
    <platform>/ altindaki gomulu binary'yi arar. Bulunamazsa None doner --
    sistemde kurulu olabilecek bir 'tor'a kendiliginden guvenmiyoruz
    (versiyon/kaynak farkli olabilir, kullanicinin hicbir sey kurmamasi
    gerekiyordu).
    """
    env_path = os.environ.get("CHAMELEON_TOR_BINARY")
    if env_path and os.path.isfile(env_path):
        return env_path

    system = platform.system().lower()
    exe_name = "tor.exe" if system == "windows" else "tor"
    candidate = os.path.join(SHARED_DIR, "bin", "tor", system, exe_name)
    if os.path.isfile(candidate):
        return candidate
    return None
