"""
onion_auth.py
Tor v3 hidden service "client authorization" icin x25519 anahtar cifti
uretimi ve Tor'un control protokolunde bekledigi base32 kodlamasi.

Hem tasinabilir kit (hedef cihaz, ADD_ONION -> ClientAuthV3=<public>) hem de
operator tarafi (ssh_engine, ONION_CLIENT_AUTH_ADD -> x25519:<private>) bu
modulu kullanir; boylece anahtar formati iki tarafta da birebir ayni yerden
gelir.

Not: Bu, Tor'un HS master kimlik anahtari (Ed25519, imzalama) DEGIL --
sadece "kim baglanabilir" yetkilendirmesi icin x25519 (Diffie-Hellman)
anahtar cifti. Ham 32 baytlik anahtarlar oldugu icin (Ed25519'daki gibi
SHA-512 genisletmesi gerekmiyor), cryptography kutuphanesinin X25519
ham bayt cikisini dogrudan Tor'un base32 formatina ceviriyoruz.
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey


def _b32_encode(raw: bytes) -> str:
    """Tor, ClientAuthV3/ONION_CLIENT_AUTH_ADD icin base32'yi dolgusuz
    (RFC 4648 '=' karakterleri kirpilmis) ve kucuk harfle bekler."""
    return base64.b32encode(raw).decode("ascii").rstrip("=").lower()


def _b32_decode(text: str) -> bytes:
    text = text.strip().upper()
    padding = "=" * (-len(text) % 8)
    return base64.b32decode(text + padding)


def generate_keypair():
    """
    Operator icin yeni bir x25519 anahtar cifti uretir.

    Donus: (private_b32, public_b32) -- ikisi de base32, dolgusuz, kucuk harf.
      private_b32 -> operator tarafinda saklanir, Tor'a
                      'ONION_CLIENT_AUTH_ADD <onion> x25519:<private_b32>'
                      olarak verilir.
      public_b32  -> tasinabilir kit tarafinda
                      create_ephemeral_hidden_service(client_auth_v3=...)'a
                      verilir; sadece bu public key'in eslesen private'ina
                      sahip taraf hidden service'e baglanabilir.
    """
    private_key = X25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_raw = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return _b32_encode(private_raw), _b32_encode(public_raw)


def public_key_from_private(private_b32: str) -> str:
    """Bir private_b32'den (operatorun sakladigi) eslesen public_b32'yi
    yeniden turetir -- operator ilk anahtarini kaybetmeden dogrulamak
    veya kendi public'ini tekrar gormek istediginde kullanilir."""
    private_raw = _b32_decode(private_b32)
    private_key = X25519PrivateKey.from_private_bytes(private_raw)
    public_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return _b32_encode(public_raw)


if __name__ == "__main__":
    priv, pub = generate_keypair()
    print(f"Private (operator, gizli tut): {priv}")
    print(f"Public  (portable kit'e gomulur): {pub}")
    assert public_key_from_private(priv) == pub
