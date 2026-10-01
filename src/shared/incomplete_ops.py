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
import logging
import os
import sys
import threading
import uuid
from datetime import datetime, timezone

_logger = logging.getLogger(__name__)

_LOCK = threading.Lock()

# Kayıt defteri dosyası, okuma/yazma işlemleri _LOCK ile korunur.
# Birden fazla thread (Qt worker'ları vb.) aynı anda record_start /
# record_finish / list_incomplete çağrıldığında read-modify-write
# yarış koşulunu (race condition) engellemek için kullanılır.

# Geçici dosya üzerinden yazıp ardından kaldıra ('os.replace' — atomic
# taşınma) ile WRITE sırasında yarım dosya bırakılmasını önler.
_WIP_SUFFIX = ".incomplete_ops.json.tmp"


# Vaka gecmisi/organizasyon verisiyle AYNI kalici konum (bkz.
# forensic_report.HISTORY_DIR'deki ayni gerekce) -- derlenmis modda
# sys.executable'a, kaynaktan calisirken __file__'a gore.
if getattr(sys, "frozen", False):
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "data")
else:
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

REGISTRY_PATH = os.path.join(DATA_DIR, "incomplete_ops.json")


def _read_all():
    """Kayıt defterini okur; bozuk JSON veya dosya yoksa boş dict döner.

    Döndürülen dict, aynı anda birden fazla çağrıcınınregistry'ye
    müdahale etmesini engellemek için kopyadır (shallow copy).
    """
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except OSError:
        return {}
    except json.JSONDecodeError:
        _logger.warning(
            "incomplete_ops.json bozuk veya geçersiz — boş kayıt defteriyle "
            "devam ediliyor (mevcut kayıtlar kaybediliyor)."
        )
        return {}
    if not isinstance(data, dict):
        _logger.warning(
            "incomplete_ops.json beklenmedik bir tip içeriyor — "
            "boş kayıt defteriyle devam ediliyor."
        )
        return {}
    # Çağrıyı yapan tarafın döndürüleni yanlışlıkla özkaynağı
    # değiştirmesini engellemek için kopya dön.
    return dict(data)


def _write_all(kayitlar):
    """Kayıt defterini *atomic* şekilde yazar (geçici dosya + os.replace).

    Aynı anda birden fazla işlemin dosyaya yazması durumunda oluşabilecek
    yarım/garip bir JSON dosyası bırakılmasını önler.
    """
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except OSError:
        _logger.warning(
            "incomplete_ops.json kayıt klasörü oluşturulamadı — "
            "kayıtlar kaydedilemiyor."
        )
        return
    tmp_path = REGISTRY_PATH + _WIP_SUFFIX
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(kayitlar, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, REGISTRY_PATH)
    except OSError as exc:
        _logger.warning(
            "incomplete_ops.json kaydı yazılamadı: %s", exc
        )
        # Geçici dosya artık varsa temizle (k Urban, boş zip klasörü gibi).
        try:
            os.remove(tmp_path)
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
    with _LOCK:
        kayitlar = _read_all()
        if op_id in kayitlar:
            # Çokatik, ama uuid4 hex[:12] çakışma ihtimali çok düşük;
            # güvenlik/kaçak kayıt yaratmamak için yeniden denen.
            op_id = uuid.uuid4().hex[:12]
            kayitlar[op_id] = {
                "kind": kind,
                "label": label,
                "details": details or {},
                "started_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        else:
            kayitlar[op_id] = {
                "kind": kind,
                "label": label,
                "details": details or {},
                "started_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        _write_all(kayitlar)
    return op_id


def record_finish(op_id):
    """Islem (basarili ya da basarisiz) BITINCE cagrilir -- kaydi kaldirir.

    op_id string olmali (record_start tarafından döndürülen UUID-hex).
    None, False, 0 gibi false-yapici değerler (ve bos string) desteklenmez;
    bunlar için sessizce dönülür.
    """
    if not isinstance(op_id, str) or not op_id:
        return
    with _LOCK:
        kayitlar = _read_all()
        if op_id in kayitlar:
            del kayitlar[op_id]
            _write_all(kayitlar)


def list_incomplete():
    """Hala acik (islem bitmeden birakilmis) tum kayitlari (id, veri) olarak dondurur."""
    with _LOCK:
        return list(_read_all().items())
