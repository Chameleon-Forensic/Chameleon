"""
chain_of_custody.py
Delil takip (chain-of-custody) log modülü. Diğer tüm modüller, yaptıkları
işlemleri bu modül üzerinden logs/case_<tarih-saat>.log dosyasına yazar.
"""

import os
from datetime import datetime, timezone

# --- Sabitler ---
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


def log_event(event_type, description, hash_value=None):
    """
    Tek bir chain-of-custody olayını zaman damgası, işlem türü, açıklama
    ve (varsa) hash değeriyle birlikte düz metin olarak log dosyasına yazar.
    """
    # ISO 8601 UTC zaman damgası (örn. 2026-07-30T00:14:53Z)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    hash_part = hash_value if hash_value else "-"

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


if __name__ == "__main__":
    # Modülü tek başına test etmek için küçük bir örnek akış
    log_event(EVENT_EXAM_START, "Test incelemesi baslatildi")
    log_event(EVENT_WRITE_BLOCK_APPLIED, "Disk salt-okunur yapildi: /dev/sdb")
    log_event(EVENT_BLOCK_ACQUIRED, "Blok 0 alindi", "a1b2c3d4")
    log_event(EVENT_CONNECTION_LOST, "SSH baglantisi koptu")
    log_event(EVENT_CONNECTION_RESUMED, "SSH baglantisi yeniden kuruldu")
    log_event(EVENT_EXAM_END, "Inceleme tamamlandi", "final-hash-ornek")
    print("Test tamamlandi, log dosyasi:", get_log_file_path())
