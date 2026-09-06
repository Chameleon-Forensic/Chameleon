"""
tz_display.py
Rapor/GUI'de UTC zaman damgasinin YANINA, sadece OKUNABILIRLIK icin,
kullanicinin sectigi bir saat dilimindeki karsiligini eklemek icin ortak
modul. Windows'un kendi saat dilimi listesindeki "(UTC+03:00) Istanbul"
bicimini kullanir -- birçok adli bilisim araci da (Windows uzerinde
calistiklari icin) ayni gosterimi kullanir.

ONEMLI: Bu modul HICBIR ZAMAN raporun kendi (report.json) UTC verisini
DEGISTIRMEZ -- sadece report.html/GUI gibi insan tarafindan okunan
yerlerde UTC'nin YANINA ek bir aciklama olarak eklenir. Delil olarak
gecerli olan HER ZAMAN UTC degeridir.

`zoneinfo` standart kutuphanede ama Windows'ta IANA saat dilimi
veritabanini kendisi getirmiyor -- bunun icin `tzdata` paketi (sadece
veri, kod degil) kurulu olmali (bkz. requirements.txt).
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, available_timezones

# Aday listesini makul boyutta tutmak icin: IANA'nin binlerce girdisinden
# (cogu ada/kucuk bolge) sadece yaygin kullanilan, buyuk sehir/ulke
# merkezli olanlari seciyoruz -- Windows'un kendi saat dilimi listesine
# yakin bir kapsam.
_COMMON_ZONE_KEYS = [
    "UTC",
    "Europe/London", "Europe/Lisbon", "Europe/Dublin",
    "Europe/Istanbul", "Europe/Athens", "Europe/Helsinki", "Europe/Bucharest",
    "Europe/Paris", "Europe/Berlin", "Europe/Madrid", "Europe/Rome",
    "Europe/Amsterdam", "Europe/Brussels", "Europe/Vienna", "Europe/Warsaw",
    "Europe/Zurich", "Europe/Stockholm", "Europe/Moscow",
    "America/New_York", "America/Chicago", "America/Denver",
    "America/Los_Angeles", "America/Anchorage", "America/Sao_Paulo",
    "America/Mexico_City", "America/Bogota", "America/Argentina/Buenos_Aires",
    "America/Toronto", "America/Vancouver",
    "Asia/Dubai", "Asia/Karachi", "Asia/Kolkata", "Asia/Dhaka",
    "Asia/Bangkok", "Asia/Jakarta", "Asia/Shanghai", "Asia/Hong_Kong",
    "Asia/Tokyo", "Asia/Seoul", "Asia/Singapore", "Asia/Riyadh",
    "Asia/Jerusalem", "Asia/Baghdad", "Asia/Tehran",
    "Africa/Cairo", "Africa/Johannesburg", "Africa/Lagos", "Africa/Nairobi",
    "Australia/Sydney", "Australia/Perth", "Pacific/Auckland",
]


def common_timezones():
    """
    [(iana_anahtari, "(UTC+03:00) Istanbul" bicimli etiket), ...] dondurur --
    o ANKI (guncel tarihe gore, DST dahil) UTC farkina gore artan sirada.
    Sistemde `tzdata` yoksa (kurulu olmasi gerekiyor) bos liste doner --
    cagiran taraf bunu "saat dilimi secimi devre disi" olarak yorumlamali.
    """
    available = available_timezones()
    now_utc = datetime.now(timezone.utc)
    sonuc = []
    for key in _COMMON_ZONE_KEYS:
        if key not in available:
            continue
        try:
            offset = now_utc.astimezone(ZoneInfo(key)).utcoffset()
        except Exception:
            continue
        sonuc.append((key, offset, _format_label(key, offset)))
    sonuc.sort(key=lambda x: x[1])
    return [(key, label) for key, _offset, label in sonuc]


def _format_label(key, offset):
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    h, m = divmod(abs(total_minutes), 60)
    city = key.split("/")[-1].replace("_", " ")
    if key == "UTC":
        return "UTC"
    return f"(UTC{sign}{h:02d}:{m:02d}) {city}"


def format_with_local(utc_iso, tz_key):
    """
    utc_iso: chain_of_custody/forensic_report'un kullandigi bicim, orn.
    "2026-09-05T10:00:00Z". tz_key: common_timezones()'dan bir anahtar,
    None ya da "UTC" verilirse (ya da parse/donusum basarisiz olursa)
    duz UTC metni degismeden doner.

    Donus, HER ZAMAN UTC degerini de icerir -- yerel saat SADECE ek bir
    aciklama, UTC'nin yerine gecmez.
    """
    if not utc_iso:
        return utc_iso
    if not tz_key or tz_key == "UTC":
        return utc_iso
    try:
        dt = datetime.strptime(utc_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(ZoneInfo(tz_key))
    except Exception:
        return utc_iso
    label = _format_label(tz_key, local_dt.utcoffset())
    return f"{utc_iso} (yerel: {local_dt.strftime('%Y-%m-%d %H:%M:%S')}, {label})"
