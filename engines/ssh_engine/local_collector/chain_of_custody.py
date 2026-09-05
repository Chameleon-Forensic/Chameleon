"""
chain_of_custody.py
Delil takip (chain-of-custody) log modülü. Diğer tüm modüller, yaptıkları
işlemleri bu modül üzerinden logs/case_<tarih-saat>.log dosyasına yazar.
"""

import os
import sys
from datetime import datetime, timezone

# --- Sabitler ---
# Derlenmis (.exe) modda __file__'in bulundugu yer PyInstaller'in her
# calistirmada silinen GECICI _MEIPASS klasorudur -- loglar buraya
# yazilirsa uygulama kapaninca kaybolur, USB'den farkli bir bilgisayarda
# calistirilinca hicbir gecmis kalmaz. sys.executable (.exe'nin KENDI
# konumu) ise KALICIDIR. Kaynaktan calisirken (sys.frozen yok) mevcut
# davranis (bkz. docs/roadmap.md "Sirada" -- portable yapma maddesi)
# hic degismez.
if getattr(sys, "frozen", False):
    LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "logs")
else:
    LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")

# İşlem türleri (madde 6'da belirtilen sabit olay isimleri)
EVENT_EXAM_START = "EXAM_START"
EVENT_EXAM_RESUME = "EXAM_RESUME"
EVENT_BLOCK_ACQUIRED = "BLOCK_ACQUIRED"
EVENT_CONNECTION_LOST = "CONNECTION_LOST"
EVENT_CONNECTION_RESUMED = "CONNECTION_RESUMED"
EVENT_EXAM_END = "EXAM_END"
EVENT_EXAM_ERROR = "EXAM_ERROR"
EVENT_WRITE_BLOCK_APPLIED = "WRITE_BLOCK_APPLIED"
EVENT_WRITE_BLOCK_SKIPPED = "WRITE_BLOCK_SKIPPED"
EVENT_HASH_VERIFIED = "HASH_VERIFIED"
EVENT_HASH_MISMATCH = "HASH_MISMATCH"
# Baglanti Tor Hidden Service uzerinden mi (acil durum, NAT/firewall
# asma) yoksa dogrudan/port-yonlendirmeli SSH ile mi kuruldu -- raporu
# okuyan kisi hangi tasima yonteminin kullanildigini gorebilsin diye.
EVENT_TOR_CONNECTION_ESTABLISHED = "TOR_CONNECTION_ESTABLISHED"
# Baglanti operatorun VPN tuneli uzerinden kuruldu -- Tor gibi ekstra bir
# tasima katmani degil (SSH dogrudan kuruluyor), sadece delil zincirinde
# hangi ag yolunun kullanildigi kayit altina aliniyor.
EVENT_VPN_CONNECTION_USED = "VPN_CONNECTION_USED"
# Uzak "Gozat" (klasor gezinme) ozelligiyle bir klasorun icerigi listelendi
# -- salt-okunur (find/Get-ChildItem), hicbir sey yazilmiyor/degistirilmiyor,
# ama operatorun hedef sistemde TAM OLARAK nereye baktigi izlenebilsin diye
# her listeleme ayri bir olay olarak kaydedilir.
EVENT_DIRECTORY_LISTED = "DIRECTORY_LISTED"
# Operator, sunucunun SSH kimligini (host key) known_hosts'a onceden eklenmis
# olmasini beklemek yerine dogrulamadan atlamayi sectiginde loglanir -- oyle
# bir hedefte (orn. sahsa ait cihaz) parmak izini teyit edecek bir yetkili
# genelde olmadigi icin bu secenek var, ama delil zincirinde ortadaki adam
# saldirisina karsi bu korumanin aktif OLMADIGI acikca kayit altina alinmali.
EVENT_HOST_KEY_VERIFICATION_SKIPPED = "HOST_KEY_VERIFICATION_SKIPPED"
# Tamamlanmis imaj gzip ile sikistirildi (sadece Offline Acquisition,
# kullanici tercihi) -- raporun image_hash'i HAM (sikistirilmamis) icerige
# ait kalir, output_path ise artik .gz dosyasini gosterir; bu olay bu
# donusumun ne zaman/ne oranda oldugunu delil zincirinde acikca kaydeder.
EVENT_IMAGE_COMPRESSED = "IMAGE_COMPRESSED"

# Bu çalıştırmaya ait log dosyasının yolu (ilk log_event çağrısında oluşur)
_current_log_file = None


def _get_log_file():
    """
    Bu çalıştırma için ayrılmış log dosyasının yolunu döner; yoksa
    logs/case_<tarih-saat>.log adında yeni bir dosya oluşturur.
    """
    global _current_log_file

    if _current_log_file is None:
        os.makedirs(LOG_DIR, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        _current_log_file = os.path.join(LOG_DIR, f"case_{timestamp}.log")

    return _current_log_file


def _sanitize_log_field(text):
    """
    Log satırları '|' ile ayrılan düz metin (bkz. read_events()). description
    (ve bazen hash_value) çoğu zaman HEDEF cihazdaki dosya/klasör adlarından
    geliyor -- yani incelenen tarafın (şüpheli/cihaz sahibi) kontrolünde
    olabilecek veri. İçinde '|' ya da satır sonu varsa: (a) read_events()
    parça sayısı uyuşmadığı için o KAYDI SESSİZCE DÜŞÜRÜR (delil kaybı
    gibi görünür), (b) bir satır sonuna sahte "[ts] | EVENT | .. | hash"
    deseni eklenirse SAHTE bir log kaydı enjekte edilebilir. Bu yüzden
    yazılmadan önce kaçırılıyor -- '|' görsel olarak benzeyen ama aynı
    karakter OLMAYAN bir sembolle ('¦', kırık dikey çizgi) değiştiriliyor,
    satır sonları boşlukla -- dosya adı okunaklılığını bozmadan.
    """
    if text is None:
        return text
    text = str(text).replace("|", "¦")
    return text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def log_event(event_type, description, hash_value=None):
    """
    Tek bir chain-of-custody olayını zaman damgası, işlem türü, açıklama
    ve (varsa) hash değeriyle birlikte düz metin olarak log dosyasına yazar.
    """
    # ISO 8601 UTC zaman damgası (örn. 2026-07-30T00:14:53Z)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    description = _sanitize_log_field(description)
    hash_part = _sanitize_log_field(hash_value) if hash_value else "-"

    line = f"[{timestamp}] | {event_type} | {description} | {hash_part}"

    try:
        log_file = _get_log_file()
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:
        # Log dosyasına yazılamazsa program çökmemeli, en azından terminale bildirilmeli
        print(f"[LOG HATASI] Log dosyasına yazilamadi: {e}")

    return line


def get_log_file_path():
    """
    Bu çalıştırma için kullanılan log dosyasının tam yolunu döner (henüz
    oluşturulmadıysa oluşturur).
    """
    return _get_log_file()


def read_events(log_file_path=None, start_time_utc=None, end_time_utc=None):
    """
    Duz metin log dosyasini parse edip yapili (dict listesi) olay
    listesi olarak doner -- shared/forensic_report.py'nin ortak rapora
    "chain_of_custody" bolumunu doldurmak icin kullanir.

    start_time_utc/end_time_utc (ISO 8601 string) verilirse, sadece o
    araliktaki olaylar donulur -- log dosyasi tum oturum boyunca tek
    dosya oldugu icin (birden fazla alma islemi ayni dosyaya yazabilir),
    tek bir alma islemine ait rapor sadece kendi olaylarini icersin diye.
    """
    path = log_file_path or get_log_file_path()
    events = []
    if not os.path.exists(path):
        return events

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) != 4:
                continue
            ts_raw, event_type, description, hash_part = parts
            ts = ts_raw.strip("[]")

            if start_time_utc and ts < start_time_utc:
                continue
            if end_time_utc and ts > end_time_utc:
                continue

            events.append({
                "timestamp_utc": ts,
                "event": event_type,
                "description": description,
                "hash": None if hash_part == "-" else hash_part,
            })
    return events


if __name__ == "__main__":
    # Modülü tek başına test etmek için küçük bir örnek akış
    log_event(EVENT_EXAM_START, "Test incelemesi baslatildi")
    log_event(EVENT_WRITE_BLOCK_APPLIED, "Disk salt-okunur yapildi: /dev/sdb")
    log_event(EVENT_BLOCK_ACQUIRED, "Blok 0 alindi", "a1b2c3d4")
    log_event(EVENT_CONNECTION_LOST, "SSH baglantisi koptu")
    log_event(EVENT_CONNECTION_RESUMED, "SSH baglantisi yeniden kuruldu")
    log_event(EVENT_EXAM_END, "Inceleme tamamlandi", "final-hash-ornek")
    print("Test tamamlandi, log dosyasi:", get_log_file_path())
