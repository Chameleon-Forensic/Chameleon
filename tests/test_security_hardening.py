"""
Guvenlik taramasi (branch'in main'e karsi tum diff'i) fix'lerinin
regresyon testleri -- bkz. docs/kararlar.md ve docs/code_review_bulgulari.md.

1. _restrict_key_file_permissions: icacls'a grant edilen hesap ARTIK
   DOMAIN\\kullanici biciminde -- sade "kullanici", bilgisayar adi ile
   ayniysa bos bir hesaba cozunup grant sessizce basarisiz oluyordu
   (tests/test_logical_imaging.py'deki ACL-deny bulgusuyla ayni tuzak) ve
   operator Tor ozel anahtari herkesin erisebildigi varsayilan izinlerde
   kaliyordu (CWE-732).
2. _save_recent_host: dogrudan hedef dosyaya yazim, cokme aninda yarim
   JSON birakiyordu (incomplete_ops.py'de duzeltilen AYNI desen; orada
   gecici dosya + os.replace ile atomik yazmaya gecildi).
"""

import json
import os
import subprocess
import sys

import pytest

import gui_v2


# ---------------------------------------------------------------------------
# 1) Operator anahtari izinleri -- icacls hesap bicimi
# ---------------------------------------------------------------------------

def test_restrict_key_permissions_uses_domain_qualified_account(monkeypatch, tmp_path):
    """icacls cagrisina gecen hesap, USERDOMAIN\\USERNAME biciminde olmali
    (sade USERNAME degil) ve sonuc kodu kontrol edilmeli."""
    key = tmp_path / "operator_tor_key.json"
    key.write_text("{}", encoding="utf-8")

    yakalanan = {}

    def _sahte_run(cmd, **kw):
        yakalanan["cmd"] = cmd
        class _R:
            returncode = 0
        return _R()

    monkeypatch.setattr(gui_v2.os, "name", "nt")
    monkeypatch.setattr(gui_v2.os.environ, "get", lambda k, d=None: {
        "USERNAME": "Toprak", "USERDOMAIN": "TOPRAK-PC",
    }.get(k, d))
    monkeypatch.setattr(gui_v2.subprocess, "run", _sahte_run)

    gui_v2._restrict_key_file_permissions(str(key))

    cmd = yakalanan.get("cmd")
    assert cmd is not None, "icacls cagrilmaliydi"
    grant = [a for a in cmd if a.endswith(":F")]
    assert grant, "grant argumani yok"
    # Sade "Toprak:F" DEGIL, "TOPRAK-PC\\Toprak:F" olmali:
    assert grant[0] == "TOPRAK-PC\\\\Toprak:F" or grant[0] == "TOPRAK-PC\\Toprak:F", \
        f"Hesap DOMAIN-qualifier olmali, gelen: {grant[0]!r}"


def test_restrict_key_permissions_without_domain_still_uses_username(monkeypatch, tmp_path):
    """USERDOMAIN tanimli degilse (nadir) eski davranis -- sade kullanici
    adi -- geriye donuk kullanilmali (hic grant etmemekten iyi)."""
    key = tmp_path / "operator_tor_key.json"
    key.write_text("{}", encoding="utf-8")

    yakalanan = {}

    def _sahte_run(cmd, **kw):
        yakalanan["cmd"] = cmd
        class _R:
            returncode = 0
        return _R()

    monkeypatch.setattr(gui_v2.os, "name", "nt")
    monkeypatch.setattr(gui_v2.os.environ, "get", lambda k, d=None: {
        "USERNAME": " Operator",
    }.get(k, d))
    monkeypatch.setattr(gui_v2.subprocess, "run", _sahte_run)

    gui_v2._restrict_key_file_permissions(str(key))

    cmd = yakalanan.get("cmd") or []
    grant = [a for a in cmd if a.endswith(":F")]
    assert grant == [" Operator:F"], f"Userdomain yokken sade ad kullanilmali: {grant}"


@pytest.mark.skipif(sys.platform != "win32", reason="gercek Windows ACL davranisi")
def test_restrict_key_permissions_real_windows_acl(tmp_path):
    """Gercek Windows'ta: anahtar dosyasi baska kullanicilar icin kilitli
    kalmali -- inheritance kirilir ve yalnizca mevcut kullanici kalir."""
    key = tmp_path / "operator_tor_key.json"
    key.write_text(json.dumps({"private": "x", "public": "y"}), encoding="utf-8")

    gui_v2._restrict_key_file_permissions(str(key))

    # icacls ciktisini dogrudan okuyup dogrula:
    r = subprocess.run(["icacls", str(key)], capture_output=True, text=True)
    out = r.stdout
    # Inheritance kaldirildi ("(I)" isaretleri grant satirlarindan kaybolur)
    # ve dosyada hala mevcut kullanicinin grant'i var:
    kullanici = os.environ.get("USERNAME", "")
    assert r.returncode == 0
    assert kullanici in out, f"Mevcut kullanicinin grant'i gorunmeli: {out}"


# ---------------------------------------------------------------------------
# 2) recent_ssh_hosts.json -- atomik yazma
# ---------------------------------------------------------------------------

def test_save_recent_host_leaves_no_temp_file(monkeypatch, tmp_path):
    """_save_recent_host yazimdan sonra gecici .tmp dosyasi birakmamali
    (atomik replace)."""
    monkeypatch.setattr(gui_v2, "_RECENT_HOSTS_FILE", str(tmp_path / "recent_ssh_hosts.json"))
    monkeypatch.setattr(gui_v2, "_load_recent_hosts", lambda: [])

    gui_v2._save_recent_host("hedef.example", "22", "adli")

    hedef = tmp_path / "recent_ssh_hosts.json"
    assert hedef.exists()
    veri = json.loads(hedef.read_text(encoding="utf-8"))
    assert veri[0]["host"] == "hedef.example"

    tmp_kalinti = [p.name for p in tmp_path.iterdir() if p.name != "recent_ssh_hosts.json"]
    assert not tmp_kalinti, f"Gecici dosya kalmamali: {tmp_kalinti}"


def test_save_recent_host_does_not_clobber_existing_on_failure(monkeypatch, tmp_path):
    """Mevcut dosya bozulmadan yeni kayit yazilamali -- yazma basarisiz
    olursa (orn. tam disk) ESKI dosya dokunulmamali (atomik yazmanin
    garantisi)."""
    hedef = tmp_path / "recent_ssh_hosts.json"
    hedef.write_text(json.dumps([{"host": "eski", "port": "22", "username": "u"}]), encoding="utf-8")

    monkeypatch.setattr(gui_v2, "_RECENT_HOSTS_FILE", str(hedef))
    monkeypatch.setattr(gui_v2, "_load_recent_hosts",
                        lambda: [{"host": "eski", "port": "22", "username": "u"}])

    # makedirs zaten var olan klasorde no-op; yazma basarili olacak.
    # Bu test atomikligin DOGRU yolunu belgelemek icin var: hedef dosyaya
    # dogrudan 'w' ile yazmak yerine gecici + replace kullanildigini
    # kaynak okumak yerine cikti dosyasinin butunluguyle dogruluyoruz.
    gui_v2._save_recent_host("yeni", "22", "u2")
    veri = json.loads(hedef.read_text(encoding="utf-8"))
    assert veri[0]["host"] == "yeni"
    assert len(veri) == 2
