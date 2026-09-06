"""
socks5.py
Tor'un yerel SOCKS proxy'si uzerinden bir .onion adresine ham TCP soketi
acan minimal bir SOCKS5 istemcisi (RFC 1928). PySocks gibi ek bir
bagimlilik eklememek icin -- ihtiyacimiz olan tek sey CONNECT komutu ve
DOMAIN adres tipi (.onion adresini YEREL cozumlemeye CALISMAMAK onemli;
sadece Tor'un kendisi cozebilir, bu yuzden ATYP=DOMAINNAME kullanilir).

paramiko'nun SSHClient.connect(sock=...) parametresine, TCP baglantisini
BIZIM actigimiz bu soketi vermek icin kullanilir.
"""
import socket
import struct


class Socks5Error(Exception):
    pass


def connect_via_socks5(proxy_host, proxy_port, dest_host, dest_port, timeout=15):
    """
    Tor'un SOCKS portuna (varsayilan 9050/9150) baglanip, uzerinden
    dest_host:dest_port'a (orn. bir .onion adresi) bir SOCKS5 CONNECT
    yapar. Basarili olursa, artik dest_host:dest_port'a baglanmis, ham
    veri aktarimina hazir bir socket.socket doner.

    dest_host cozumlenmeye calisilmaz -- ATYP=0x03 (DOMAINNAME) ile
    Tor'a oldugu gibi gonderilir, cozumleme Tor tarafinda (Tor agi
    icinde) yapilir. Bu, .onion adresleri icin ZORUNLUDUR (yerel DNS
    onlari hic cozemez).
    """
    sock = socket.create_connection((proxy_host, proxy_port), timeout=timeout)
    sock.settimeout(timeout)

    try:
        # 1) Selamlama: SOCKS5, auth yontemi olarak sadece "no auth" (0x00) sunuyoruz
        sock.sendall(b"\x05\x01\x00")
        reply = _recv_exact(sock, 2)
        if reply[0:1] != b"\x05" or reply[1:2] != b"\x00":
            raise Socks5Error(f"SOCKS5 sunucusu 'no auth' kabul etmedi: {reply!r}")

        # 2) CONNECT istegi: VER=5, CMD=1(CONNECT), RSV=0, ATYP=3(DOMAINNAME)
        dest_bytes = dest_host.encode("ascii")
        if len(dest_bytes) > 255:
            raise Socks5Error("Hedef adres 255 bayttan uzun olamaz.")
        request = (
            b"\x05\x01\x00\x03"
            + bytes([len(dest_bytes)])
            + dest_bytes
            + struct.pack(">H", dest_port)
        )
        sock.sendall(request)

        # 3) Yanit: VER=5, REP, RSV, ATYP, BND.ADDR, BND.PORT
        header = _recv_exact(sock, 4)
        if header[0:1] != b"\x05":
            raise Socks5Error(f"Gecersiz SOCKS5 yaniti: {header!r}")
        rep = header[1]
        if rep != 0x00:
            raise Socks5Error(f"SOCKS5 CONNECT basarisiz (REP=0x{rep:02x}): {_REP_MESSAGES.get(rep, 'bilinmeyen hata')}")

        atyp = header[3]
        if atyp == 0x01:  # IPv4
            _recv_exact(sock, 4 + 2)
        elif atyp == 0x03:  # DOMAINNAME
            length = _recv_exact(sock, 1)[0]
            _recv_exact(sock, length + 2)
        elif atyp == 0x04:  # IPv6
            _recv_exact(sock, 16 + 2)
        else:
            raise Socks5Error(f"Bilinmeyen ATYP: {atyp}")

        return sock

    except Exception:
        sock.close()
        raise


def _recv_exact(sock, n):
    """SOCKS5 el sikismasinda TAM olarak n bayt okur (kismi okumaya karsi)."""
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise Socks5Error("SOCKS5 el sikismasi sirasinda baglanti erken kapandi.")
        data += chunk
    return data


_REP_MESSAGES = {
    0x01: "genel sunucu hatasi",
    0x02: "kurallarca yasaklandi",
    0x03: "ag ulasilamaz",
    0x04: "host ulasilamaz",
    0x05: "baglanti reddedildi",
    0x06: "TTL suresi doldu",
    0x07: "desteklenmeyen komut",
    0x08: "desteklenmeyen adres turu",
}
