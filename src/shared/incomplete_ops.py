"""
incomplete_ops.py
"Yarim Kalanlar" listesi (docs/roadmap.md, madde 0) icin genel amacli
kayit defteri -- SSH disk imajlama zaten KENDI manifest sistemine sahip
(image_acquirer.list_incomplete_manifests, chunk-bazli gercek resume),
bu modul ona DOKUNMAZ. Burasi, gercek resume'u OLMAYAN/olmasi pratik
olmayan islemler icin (RAM motoru: bir process/full dump kaldigi yerden
devam edemez, tek seferlik bir islemdir) sadece "basladi, bitirmedi"
bilgisini kalici tutar -- kullaniciya launcher'da gosterip "yeniden
baslat" kolayligi sunmak icin (gercek resume degil).

Kayit, RamWorker islem baslarken record_start() ile acilir, basarili/
basarisiz BITTIGINDE record_finish() ile kapatilir (kayit silinir).
Uygulama/surec islem ORTASINDA aniden kapanirsa (crash, force-kill),
kayit silinmeden kalir -- launcher acilista bunu "yarim kalmis" olarak
gorur.
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone

# Vaka gecmisi/organizasyon verisiyle AYNI kalici konum (bkz.
# forensic_report.HISTORY_DIR'deki ayni gerekce) -- derlenmis modda
# sys.executable'a, kaynaktan calisirken __file__'a gore.
if getattr(sys, "frozen", False):
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "data")
else:
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

REGISTRY_PATH = os.path.join(DATA_DIR, "incomplete_ops.json")


def _read_all():
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _write_all(kayitlar):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(kayitlar, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


def record_start(kind, label, details=None):
    """
    Bir islem baslarken cagrilir. kind: 'ram_process' | 'ram_full' gibi bir
    tur etiketi. label: kullaniciya gosterilecek kisa aciklama (orn.
    "notepad.exe (PID 1234)"). details: ekstra bilgi (case_id, examiner,
    organization, custodian, output_path vb. -- "yeniden baslat" icin
    gerekebilecek her sey). Donen id, record_finish() icin saklanmali.
    """
    op_id = uuid.uuid4().hex[:12]
    kayitlar = _read_all()
    kayitlar[op_id] = {
        "kind": kind,
        "label": label,
        "details": details or {},
        "started_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    _write_all(kayitlar)
    return op_id


def record_finish(op_id):
    """Islem (basarili ya da basarisiz) BITINCE cagrilir -- kaydi kaldirir."""
    if not op_id:
        return
    kayitlar = _read_all()
    if op_id in kayitlar:
        del kayitlar[op_id]
        _write_all(kayitlar)


def list_incomplete():
    """Hala acik (islem bitmeden birakilmis) tum kayitlari (id, veri) olarak dondurur."""
    return list(_read_all().items())
