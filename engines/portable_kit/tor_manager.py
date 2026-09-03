"""
tor_manager.py
Tasinabilir kit'in HEDEF cihazda calisan tarafi: gomulu Tor binary'sini
baslatir, SSH portunu (22) yayimlayan bir v3 Hidden Service olusturur ve
bunu sadece operatorun x25519 public anahtarina (shared/onion_auth.py)
sahip istemcilere acar -- rastgele biri .onion adresini bilse bile
baglanamaz.

Tor binary yolu koda gomulu DEGIL, shared/tor_binary.py uzerinden bulunur
(CHAMELEON_TOR_BINARY ortam degiskeni ya da shared/bin/tor/<platform>/
varsayilani). Boylece Tor'u ileride (orn. bir guvenlik guncellemesiyle)
degistirmek icin sadece o dosyayi degistirmek yeterli olur, kod degismesi
gerekmez. Operator tarafi (ssh_engine/local_collector/tor_client.py) da
AYNI binary'yi ve AYNI anahtar formatini kullanir.
"""
import os
import sys
import tempfile

import stem.process
from stem.control import Controller

PORTABLE_KIT_DIR = os.path.dirname(os.path.abspath(__file__))

# shared/ -- Tor binary yolu ve onion_auth.py (anahtar formati) iki
# motorda da (portable_kit + ssh_engine) AYNI yerden gelsin diye ortak.
_SHARED_DIR = os.path.join(PORTABLE_KIT_DIR, "..", "..", "shared")
if os.path.isdir(_SHARED_DIR):
    sys.path.insert(0, _SHARED_DIR)
from tor_binary import default_tor_binary_path  # noqa: E402


class HiddenServiceHandle:
    """Calisan bir Tor sureci + olusturulan hidden service icin tutucu."""

    def __init__(self, tor_process, controller, onion_address):
        self.tor_process = tor_process
        self.controller = controller
        self.onion_address = onion_address  # '.onion' EKI OLMADAN, 56 karakter

    def close(self):
        """
        Controller'i ve Tor surecini duzgunce kapatir. take_ownership=True
        ile baslatildigi icin controller.close() zaten Tor'u sonlandirir;
        burada ayrica terminate/kill ile orphan process kalma ihtimalini
        de kapatiyoruz (testte/gercek kullanimda hizli ve kesin kapanis icin).
        """
        try:
            self.controller.close()
        except Exception:
            pass
        if self.tor_process and self.tor_process.poll() is None:
            self.tor_process.terminate()
            try:
                self.tor_process.wait(timeout=5)
            except Exception:
                self.tor_process.kill()


def start_hidden_service(operator_public_key_b32, ssh_port=22, tor_binary_path=None,
                          data_dir=None, control_port=9151, on_bootstrap=None):
    """
    Gomulu Tor'u baslatir ve sadece operator_public_key_b32'nin ozel
    anahtarina sahip istemcilere acik bir v3 hidden service olusturur.

    ssh_port: yerel sshd hangi porttaysa (genelde 22).
    data_dir: verilmezse gecici bir klasor kullanilir (kit kapaninca zaten
      kalici bir sey saklanmiyor -- hizmet her calistirmada yeni/gecici).
    control_port: Tor'un kontrol portu; portable kit tek basina calistigi
      icin celisme riski dusuk, yine de disaridan degistirilebilir birakildi.

    Donus: basarili olursa HiddenServiceHandle, olmazsa None.
    """
    tor_binary_path = tor_binary_path or default_tor_binary_path()
    if not tor_binary_path:
        print(
            "[-] Gomulu Tor binary'si bulunamadi. CHAMELEON_TOR_BINARY "
            "ortam degiskenini ayarlayin ya da shared/bin/tor/<platform>/"
            "tor(.exe) dosyasini yerlestirin."
        )
        return None

    data_dir = data_dir or tempfile.mkdtemp(prefix="chameleon_tor_")

    try:
        tor_process = stem.process.launch_tor_with_config(
            tor_cmd=tor_binary_path,
            config={
                "DataDirectory": data_dir,
                "ControlPort": str(control_port),
                "CookieAuthentication": "1",
                # Bu tarafta disariya cikan bir baglanti gerekmiyor, sadece
                # hidden service yayimlaniyor -- SOCKS'u kapatmak saldiri
                # yuzeyini kucultur.
                "SocksPort": "0",
            },
            take_ownership=True,
            init_msg_handler=on_bootstrap,
            timeout=90,
        )
    except Exception as e:
        print(f"[-] Tor baslatilamadi: {e}")
        return None

    try:
        controller = Controller.from_port(port=control_port)
        controller.authenticate()

        port_mapping = 22 if ssh_port == 22 else {22: f"127.0.0.1:{ssh_port}"}
        response = controller.create_ephemeral_hidden_service(
            port_mapping,
            key_type="ED25519-V3",
            client_auth_v3=operator_public_key_b32,
            await_publication=True,
            timeout=60,
        )
    except Exception as e:
        print(f"[-] Hidden service olusturulamadi: {e}")
        tor_process.terminate()
        return None

    return HiddenServiceHandle(tor_process, controller, response.service_id)


if __name__ == "__main__":
    from onion_auth import generate_keypair

    print("[i] Test icin gecici bir operator anahtari uretiliyor...")
    priv, pub = generate_keypair()
    print(f"    (gercek kullanimda bu anahtar operatorden onceden gelir)")

    handle = start_hidden_service(pub)
    if handle is None:
        print("[-] Hidden service baslatilamadi.")
    else:
        print(f"[+] Hidden service hazir: {handle.onion_address}.onion")
        input("Kapatmak icin Enter'a basin...")
        handle.close()
        print("[+] Tor sureci kapatildi.")
