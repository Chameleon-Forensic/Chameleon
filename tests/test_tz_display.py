"""tz_display.py icin testler -- UTC'nin yaninda gosterilen yerel saatin
DELIL DEGERINI (report.json) HIC etkilememesi gereken, sadece
report.html'deki sunumu degistiren bir ozellik oldugu icin bu ayrimin
korundugunu dogrulamak kritik."""

import tz_display as tzd


def test_common_timezones_includes_utc_and_istanbul():
    zones = dict(tzd.common_timezones())
    assert "UTC" in zones
    assert "Europe/Istanbul" in zones
    assert zones["UTC"] == "UTC"
    assert "Istanbul" in zones["Europe/Istanbul"]


def test_common_timezones_sorted_by_offset():
    # UTC (+00:00) listede en once gelmeyebilir -- negatif ofsetli
    # (orn. America/Anchorage, UTC-09:00) bolgeler ondan once siralanir.
    # GUI'de UTC'nin AYRICA ilk siraya konmasi (bkz. _show_case_info)
    # bu fonksiyonun degil, cagiran tarafin sorumlulugu. Burada sadece
    # genel siralamanin GERCEKTEN artan oldugunu dogruluyoruz.
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    now_utc = datetime.now(timezone.utc)
    zones = tzd.common_timezones()
    offsets = [now_utc.astimezone(ZoneInfo(key)).utcoffset() for key, _label in zones]
    assert offsets == sorted(offsets), "common_timezones() artan ofsete gore sirali olmali"


def test_format_with_local_returns_unchanged_for_utc():
    raw = "2026-01-01T10:00:00Z"
    assert tzd.format_with_local(raw, "UTC") == raw
    assert tzd.format_with_local(raw, None) == raw


def test_format_with_local_appends_local_time_for_other_zone():
    raw = "2026-01-01T10:00:00Z"
    result = tzd.format_with_local(raw, "Europe/Istanbul")
    assert raw in result, "orijinal UTC degeri HER ZAMAN korunmali"
    assert "yerel" in result
    assert "13:00:00" in result  # Istanbul UTC+3


def test_format_with_local_handles_empty_input():
    assert tzd.format_with_local("", "Europe/Istanbul") == ""
    assert tzd.format_with_local(None, "Europe/Istanbul") is None


def test_format_with_local_handles_malformed_input_gracefully():
    # bozuk bir tarih string'i cökertmemeli, oldugu gibi geri donmeli
    assert tzd.format_with_local("bozuk-tarih", "Europe/Istanbul") == "bozuk-tarih"
