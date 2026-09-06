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
import hashlib
import re

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

# x25519 anahtarlarinin (32 bayt ham veri) base32/dolgusuz/kucuk harf
# kodlamasi HER ZAMAN 52 karakter uretir (bkz. generate_keypair()).
_B32_KEY_RE = re.compile(r"^[a-z2-7]{52}$")


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


def is_valid_key_b32(text: str) -> bool:
    """
    Bir x25519 anahtarinin (public ya da private) beklenen bicimde
    (52 karakter, base32 dolgusuz kucuk harf) olup olmadigini kontrol
    eder. Guvenlik denetiminde bulunan bir bosluk icin eklendi: hem
    tor_client.py'nin ONION_CLIENT_AUTH_ADD hem tor_manager.py'nin
    ClientAuthV3 degeri Tor'a HAM control-protokol komutu icine
    yerlestiriliyordu, formati hic dogrulanmadan -- yapistirilan/
    dosyadan okunan deger CR/LF gibi kontrol karakterleri icerirse
    (bozuk kopyalama, elle duzenleme, gelecekte baska bir girdi yolu)
    ayni control-protokol mesajina ikinci, istenmeyen bir komut
    enjekte edilebilirdi. Bu fonksiyon her iki tarafta da (dosyadan
    okunan operator anahtari ve GUI'de yapistirilan anahtar) kullanim
    ONCESI cagrilir.
    """
    if not text:
        return False
    return bool(_B32_KEY_RE.match(text.strip()))


def key_fingerprint(public_b32: str) -> str:
    """
    Bir operator ACIK anahtarindan, telefonla sesli okunup karsi tarafla
    karsilastirilabilecek kisa bir kod uretir (orn. "3F2A-9C11-88DE").
    Hem operator ekraninda (kendi anahtarinin yaninda) hem sahadaki kisinin
    hedef taraf sihirbazinda (yapistirdigi anahtarin yaninda) AYNI hash
    fonksiyonuyla gosterilir -- boylece sahadaki kisi, operatore anahtari
    dogru yapistirdigini sozlu olarak teyit ettirebilir. Guvenlik denetiminde
    bulunan gercek bir bosluk icin eklendi: onceden yapistirilan anahtar hic
    dogrulanmiyordu, yanlis/saldirgan bir anahtar da sessizce kabul edilirdi.
    """
    digest = hashlib.sha256(public_b32.strip().encode("utf-8")).hexdigest().upper()
    return "-".join(digest[i:i + 4] for i in range(0, 12, 4))


if __name__ == "__main__":
    priv, pub = generate_keypair()
    print(f"Private (operator, gizli tut): {priv}")
    print(f"Public  (portable kit'e gomulur): {pub}")
    assert public_key_from_private(priv) == pub
