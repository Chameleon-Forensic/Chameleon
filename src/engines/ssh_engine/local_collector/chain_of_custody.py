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
# Mantiksal imajda (docs/roadmap.md madde 0.5) bazi ogeler BILEREK alinmadi
# (kilitli/degisken sistem dosyalari, yansima noktalari) -- imajda neyin
# NEDEN olmadigi delil zincirinde acikca gorunsun diye tek bir ozet olarak
# kaydedilir; tam liste manifest_files.json'daki "excluded" alanindadir.
EVENT_LOGICAL_EXCLUSIONS = "LOGICAL_EXCLUSIONS"
# Operator "Durdur" ile bir alma islemini bilerek yarim biraktiginda
# (bkz. gui_v2.py "Durdur" butonu) -- EXAM_ERROR (beklenmeyen hata) ya da
# CONNECTION_LOST (baglanti sorunu) ile KARISMASIN diye ayri bir olay:
# rapor okuyan kisi bunun bir ARIZA degil, operatorun kendi karari
# oldugunu acikca gorebilsin.
EVENT_EXAM_STOPPED = "EXAM_STOPPED"
# Yerel mod (SSH yok): arac incelenen bilgisayarin KENDISINDE calisiyor.
# Kaynagin canli sistem diski olup olmadigi ve ciktinin nereye yazildigi
# delil zincirinde acikca gorunsun diye alma baslarken bir kez kaydedilir.
EVENT_LOCAL_MODE = "LOCAL_MODE"

# Bu çalıştırmaya ait log dosyasının yolu (ilk log_event çağrısında oluşur)
_current_log_file = None


def _get_log_file():
    """
    Bu çalıştırma için ayrılmış log dosyasının yolunu döner; yoksa
    logs/case_<tarih-saat>-<pid>.log adında yeni bir dosya oluşturur.

    Dosya adına os.getpid() eklenmesi: sadece saniye hassasiyetli bir
    zaman damgası, iki SÜREÇ (örn. SSH motoru + RAM motoru, ya da iki GUI
    örneği) AYNI saniyede başlarsa BENZERSİZ değildir -- ikisi de aynı
    case_<timestamp>.log dosyasına yazıp olayları birbirine karıştırırdı
    (forensic_report.py'nin read_events() zaman-penceresi filtresi bunu
    AYIRAMAZ, iki vakanın delili karışabilir). PID süreçler arası
    çarpışmayı engeller; aynı sürecin kendi içindeki tüm log_event()
    çağrıları zaten bu modül-seviyesi _current_log_file önbelleği
    sayesinde hep AYNI dosyaya yazar (istenen/değişmeyen davranış).
    Mevcut "case_<tarih-saat>" ön-eki korunduğu için (sadece sona bir
    bileşen eklendi), bu formatı bugüne kadar üreten/okuyan hiçbir kod
    (grep "case_" ile kontrol edildi) bozulmaz.
    """
    global _current_log_file

    if _current_log_file is None:
        os.makedirs(LOG_DIR, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        _current_log_file = os.path.join(LOG_DIR, f"case_{timestamp}-{os.getpid()}.log")

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

    log_event()'in aksine eskiden bu fonksiyon _get_log_file()'ı hiç
    try/except'e almıyordu -- bir dosya sistemi hatası (disk dolu,
    salt-okunur, USB çıkarılmış) os.makedirs'tan gelen OSError'ı
    YAKALAMADAN çağırana (örn. forensic_report.to_dict(), gui_v2.py'nin
    özet ekranı) sızdırıp modülün kendi tasarım hedefini ("Log dosyasına
    yazılamazsa program çökmemeli") bozuyordu. Artık log_event() ile AYNI
    şekilde hatayı yakalar, çökmek yerine None döner -- çağıran taraf
    (bkz. read_events_with_status()) bunu "log dosyasına ulaşılamadı"
    olarak ele alır.
    """
    try:
        return _get_log_file()
    except OSError as e:
        print(f"[LOG HATASI] Log dosyasi yolu belirlenemedi: {e}")
        return None


def read_events(log_file_path=None, start_time_utc=None, end_time_utc=None):
    """
    Duz metin log dosyasini parse edip yapili (dict listesi) olay
    listesi olarak doner -- shared/forensic_report.py'nin ortak rapora
    "chain_of_custody" bolumunu doldurmak icin kullanir.

    start_time_utc/end_time_utc (ISO 8601 string) verilirse, sadece o
    araliktaki olaylar donulur -- log dosyasi tum oturum boyunca tek
    dosya oldugu icin (birden fazla alma islemi ayni dosyaya yazabilir),
    tek bir alma islemine ait rapor sadece kendi olaylarini icersin diye.

    Geriye donuk uyumluluk icin imza/davranis (bos liste = "olay yok" YA
    DA "log dosyasina ulasilamadi") DEGISTIRILMEDI -- iki durumu ayirt
    etmek gerekiyorsa read_events_with_status() kullanilmali.
    """
    return read_events_with_status(log_file_path, start_time_utc, end_time_utc)["events"]


def read_events_with_status(log_file_path=None, start_time_utc=None, end_time_utc=None):
    """
    read_events() ile AYNI olay listesini doner, ama ayrica log dosyasina
    gercekten ulasilip ulasilamadigini belirten "log_file_found" alanini
    ekler.

    Eskiden read_events(), log dosyasi YOKSA (silinmis/USB cikarilmis)
    SESSIZCE bos liste donuyordu -- forensic_report.to_dict() bunu
    "chain_of_custody.events: []" olarak rapora gecirip incelemeciye
    "hic olay olmadi" ile "delil kaybedildi/log'a ulasilamadi" arasindaki
    farki HIC BILDIRMIYORDU. Bu fonksiyon o ayrimi acikca doner --
    forensic_report.to_dict() "log_dosyasi_bulundu" alanini buradan
    dolduruyor.

    Donus: {"events": [dict, ...], "log_file_found": bool}
    """
    path = log_file_path
    if path is None:
        path = get_log_file_path()
        if path is None:
            # Log dosyasinin yolu bile belirlenemedi (orn. LOG_DIR
            # olusturulamadi) -- dosyaya KESINLIKLE ulasilamadi.
            return {"events": [], "log_file_found": False}

    events = []
    if not os.path.exists(path):
        return {"events": events, "log_file_found": False}

    try:
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
    except OSError as e:
        # Dosya var gibi gorunup (os.path.exists gecti) tam bu sirada
        # erisilemez hale gelmis olabilir (orn. USB tam bu anda cikarildi)
        # -- log_event()'teki AYNI gerekce: program cokmemeli, ama bu
        # durumda su ana kadar toplanan olaylar EKSIK sayilmali.
        print(f"[LOG HATASI] Log dosyasi okunamadi: {e}")
        return {"events": events, "log_file_found": False}

    return {"events": events, "log_file_found": True}


if __name__ == "__main__":
    # Modülü tek başına test etmek için küçük bir örnek akış
    log_event(EVENT_EXAM_START, "Test incelemesi baslatildi")
    log_event(EVENT_WRITE_BLOCK_APPLIED, "Disk salt-okunur yapildi: /dev/sdb")
    log_event(EVENT_BLOCK_ACQUIRED, "Blok 0 alindi", "a1b2c3d4")
    log_event(EVENT_CONNECTION_LOST, "SSH baglantisi koptu")
    log_event(EVENT_CONNECTION_RESUMED, "SSH baglantisi yeniden kuruldu")
    log_event(EVENT_EXAM_END, "Inceleme tamamlandi", "final-hash-ornek")
    print("Test tamamlandi, log dosyasi:", get_log_file_path())
