"""
tor_client.py
Operator tarafi: gomulu Tor binary'sini SOCKS proxy modunda baslatir
(disariya, .onion adreslerine cikabilmek icin) ve operatorun x25519 ozel
anahtarini (shared/onion_auth.py ile uretilmis) Tor'a
ONION_CLIENT_AUTH_ADD komutuyla tanitir -- boylece client_auth_v3
gerektiren hidden service'lere baglanabilir hale gelir.

ssh_connector.py, bu modulun actigi Tor surecinin SOCKS portunu
(socks5.py uzerinden) kullanarak .onion adresine baglanir. Tor binary
yolu shared/tor_binary.py uzerinden bulunur -- portable_kit/tor_manager.py
ile AYNI binary, iki kopya tutulmaz.
"""
import os
import sys
import tempfile

import stem.process
from stem.control import Controller

_LOCAL_COLLECTOR_DIR = os.path.dirname(os.path.abspath(__file__))
_SHARED_DIR = os.path.join(_LOCAL_COLLECTOR_DIR, "..", "..", "..", "shared")
if os.path.isdir(_SHARED_DIR):
    sys.path.insert(0, _SHARED_DIR)
from tor_binary import default_tor_binary_path  # noqa: E402


class TorClientHandle:
    """Operatorun kendi Tor sureci + kontrol baglantisi icin tutucu."""

    def __init__(self, tor_process, controller, socks_port):
        self.tor_process = tor_process
        self.controller = controller
        self.socks_port = socks_port

    def close(self):
        """
        Controller'i ve Tor surecini duzgunce kapatir. take_ownership=True
        ile baslatildigi icin controller.close() zaten Tor'u sonlandirir;
        ayrica terminate/kill ile orphan process kalma ihtimalini de
        kapatiyoruz.
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


def start_client(onion_address, client_auth_private_b32, tor_binary_path=None,
                  data_dir=None, socks_port=9152, control_port=9153, on_bootstrap=None):
    """
    Operatorun kendi Tor surecini SOCKS proxy modunda baslatir ve
    onion_address ('.onion' EKI OLMADAN) icin client_auth_private_b32 ozel
    anahtarini Tor'a tanitir.

    Donus: basarili olursa TorClientHandle (socks_port, close() icin),
    olmazsa None.
    """
    tor_binary_path = tor_binary_path or default_tor_binary_path()
    if not tor_binary_path:
        print(
            "[-] Gomulu Tor binary'si bulunamadi. CHAMELEON_TOR_BINARY "
            "ortam degiskenini ayarlayin ya da shared/bin/tor/<platform>/"
            "tor(.exe) dosyasini yerlestirin."
        )
        return None

    data_dir = data_dir or tempfile.mkdtemp(prefix="chameleon_tor_client_")

    try:
        tor_process = stem.process.launch_tor_with_config(
            tor_cmd=tor_binary_path,
            config={
                "DataDirectory": data_dir,
                "ControlPort": str(control_port),
                "CookieAuthentication": "1",
                "SocksPort": str(socks_port),
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

        # stem 1.8.2'de ONION_CLIENT_AUTH_ADD icin hazir bir sarmalayici
        # yok (Tor 0.4.6+ ile gelen bir kontrol komutu, stem'in son
        # surumunden sonra eklendi) -- Controller.msg() ile ham
        # control-protokol komutu olarak gonderiyoruz.
        response = controller.msg(
            f"ONION_CLIENT_AUTH_ADD {onion_address} x25519:{client_auth_private_b32}"
        )
        if not response.is_ok():
            print(f"[-] ONION_CLIENT_AUTH_ADD basarisiz: {response}")
            controller.close()
            tor_process.terminate()
            return None
    except Exception as e:
        print(f"[-] Client auth eklenemedi: {e}")
        tor_process.terminate()
        return None

    return TorClientHandle(tor_process, controller, socks_port)


if __name__ == "__main__":
    onion = input("Hedef .onion adresi (eksiz, EKI OLMADAN): ").strip()
    priv = input("Operator ozel anahtari (base32): ").strip()

    handle = start_client(onion, priv)
    if handle is None:
        print("[-] Tor client baslatilamadi.")
    else:
        print(f"[+] Tor SOCKS proxy hazir: 127.0.0.1:{handle.socks_port}")
        input("Kapatmak icin Enter'a basin...")
        handle.close()
        print("[+] Tor sureci kapatildi.")
