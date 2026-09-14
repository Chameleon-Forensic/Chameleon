"""onion_auth.py icin testler -- ozellikle is_valid_key_b32() (bkz. guvenlik
denetiminde bulunan control-protokol enjeksiyon riski, docs/roadmap.md)
ve key_fingerprint()'in her iki tarafta AYNI kodu uretmesi (operator <->
sahadaki kisi arasindaki sozlu teyit mekanizmasinin temeli)."""

import onion_auth as oa


def test_generate_keypair_produces_valid_b32():
    private_b32, public_b32 = oa.generate_keypair()
    assert oa.is_valid_key_b32(private_b32)
    assert oa.is_valid_key_b32(public_b32)
    assert private_b32 != public_b32


def test_public_key_from_private_is_deterministic():
    private_b32, public_b32 = oa.generate_keypair()
    rederived = oa.public_key_from_private(private_b32)
    assert rederived == public_b32


def test_is_valid_key_b32_rejects_wrong_length():
    assert not oa.is_valid_key_b32("kisa")
    assert not oa.is_valid_key_b32("a" * 51)
    assert not oa.is_valid_key_b32("a" * 53)


def test_is_valid_key_b32_rejects_injection_attempts():
    """Guvenlik regresyonu: CR/LF veya kontrol-protokol komut ayraci
    icin baska karakterler tasiyan bir 'anahtar', Tor'a HAM olarak
    gonderilmeden ONCE burada reddedilmeli."""
    valid_len = "a" * 52
    assert not oa.is_valid_key_b32(valid_len + "\r\nQUIT")
    assert not oa.is_valid_key_b32("a" * 26 + "\n" + "a" * 25)
    assert not oa.is_valid_key_b32("ABCDEF" + "a" * 46)  # buyuk harf gecersiz


def test_is_valid_key_b32_rejects_empty_and_none():
    assert not oa.is_valid_key_b32("")
    assert not oa.is_valid_key_b32(None)


def test_key_fingerprint_is_deterministic_and_formatted():
    _priv, pub = oa.generate_keypair()
    fp1 = oa.key_fingerprint(pub)
    fp2 = oa.key_fingerprint(pub)
    assert fp1 == fp2, "ayni public key AYNI parmak izini uretmeli"
    assert len(fp1) == 14  # XXXX-XXXX-XXXX
    assert fp1.count("-") == 2


def test_key_fingerprint_differs_for_different_keys():
    _p1, pub1 = oa.generate_keypair()
    _p2, pub2 = oa.generate_keypair()
    assert oa.key_fingerprint(pub1) != oa.key_fingerprint(pub2)
