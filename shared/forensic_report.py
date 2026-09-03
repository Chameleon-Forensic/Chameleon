"""
forensic_report.py
Uc motorun da (ssh_engine disk, ssh_engine dosya/klasor, ram_engine)
AYNI semayla bir "report.json" uretmesini saglayan ortak modul.

Adli bilisim standartlarinin (SWGDE, ISO/IEC 27037, ACPO Good Practice
Guide) ortak istedigi alanlar: vaka/inceleyen kimligi, kaynagin
tanimlanmasi, alma yontemi ve zamani, butunluk (hash) kaniti,
write-blocking durumu, sonuc/hata kaydi, dogrulama sonucu ve olay
(chain of custody) listesi. Bu modul bunlarin hepsini tek bir semada
toplar.

Olay listesi (chain_of_custody) icin ayri ayri log_event cagirmaya
gerek yok -- chain_of_custody.py zaten her motorun cagirdigi
coc.log_event() ile ayni oturumun tek log dosyasina yaziyor; bu modul
sadece rapor kapsanan zaman araligindaki olaylari o dosyadan okuyup
(coc.read_events) rapora gomer.
"""

import html
import json
import os
from datetime import datetime, timezone

import chain_of_custody as coc

TOOL_NAME = "Chameleon"
TOOL_VERSION = "1.0"

# Tum motorlarin ayni "Vaka Gecmisi" listesini paylasmasi icin ortak,
# tek bir dizin -- launcher'daki sidebar buradan okuyor. Kisisel/vaka
# verisi oldugu icin .gitignore'da, asla commit edilmez.
HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
HISTORY_FILE = os.path.join(HISTORY_DIR, "case_history.json")


def _now_iso():
    """chain_of_custody.py ile AYNI format (Z suffix, mikrosaniyesiz) --
    aksi halde read_events()'teki string karsilastirmasi bozulur."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ForensicReport:
    def __init__(self, case_id="", examiner="", organization="", custodian=""):
        self.case_id = case_id
        self.examiner = examiner
        self.organization = organization
        # Cihazin/verinin alindigi taraftaki yetkili kisi (orn. sirket
        # calisanı, cihaz sahibi) -- kim inceledi kadar "cihaz kimden,
        # kimin izniyle alindi" bilgisi de delil zinciri icin onemli.
        self.custodian = custodian

        self.engine = None
        self.method = None
        self.acquisition_type = None
        self.target_os = None
        self.target_host = None
        self.source_identifier = None
        self.source_description = ""
        # "direct" (dogrudan/port yonlendirme), "vpn" ya da "tor" --
        # baglanti icin agi nasil kullandigimizin kaydi.
        self.connection_method = None

        self.start_time_utc = None
        self.end_time_utc = None

        self.hash_algorithm = "SHA-256"
        self.image_hash = None
        self.total_bytes = None
        self.chunk_size_bytes = None
        self.chunk_count = None

        self.write_blocking_applied = None
        self.write_blocking_reason = ""

        self.status = "unknown"
        self.output_path = None
        self.failed_items = []

        self.verified = False
        self.verified_at_utc = None
        self.verification_hash_match = None

    def start(self, engine, method, target_os=None, target_host=None,
              source_identifier=None, acquisition_type=None, source_description="",
              connection_method=None):
        """Alma islemi baslarken cagrilir; sadece bilinen alanlari doldurur."""
        self.engine = engine
        self.method = method
        self.target_os = target_os
        self.target_host = target_host
        self.source_identifier = source_identifier
        self.acquisition_type = acquisition_type
        self.source_description = source_description
        self.connection_method = connection_method
        self.start_time_utc = _now_iso()

    def set_write_blocking(self, applied, reason=""):
        self.write_blocking_applied = applied
        self.write_blocking_reason = reason

    def finish(self, status, output_path=None, image_hash=None, total_bytes=None,
               chunk_size_bytes=None, chunk_count=None, failed_items=None):
        """Alma islemi bitince (basarili/basarisiz fark etmez) cagrilir."""
        self.end_time_utc = _now_iso()
        self.status = status
        self.output_path = output_path
        self.image_hash = image_hash
        self.total_bytes = total_bytes
        self.chunk_size_bytes = chunk_size_bytes
        self.chunk_count = chunk_count
        self.failed_items = failed_items or []

    def set_verification(self, matched):
        self.verified = True
        self.verified_at_utc = _now_iso()
        self.verification_hash_match = matched

    def to_dict(self):
        coc_log_path = coc.get_log_file_path()
        events = coc.read_events(
            log_file_path=coc_log_path,
            start_time_utc=self.start_time_utc,
            end_time_utc=self.end_time_utc,
        )
        return {
            "report_version": "1.0",
            "tool": {"name": TOOL_NAME, "version": TOOL_VERSION, "engine": self.engine, "method": self.method},
            "case": {
                "case_id": self.case_id,
                "examiner": self.examiner,
                "organization": self.organization,
                "custodian": self.custodian,
            },
            "acquisition": {
                "target_os": self.target_os,
                "target_host": self.target_host,
                "source_identifier": self.source_identifier,
                "source_description": self.source_description,
                "acquisition_type": self.acquisition_type,
                "connection_method": self.connection_method,
                "start_time_utc": self.start_time_utc,
                "end_time_utc": self.end_time_utc,
                "write_blocking_applied": self.write_blocking_applied,
                "write_blocking_reason": self.write_blocking_reason,
            },
            "integrity": {
                "hash_algorithm": self.hash_algorithm,
                "image_hash": self.image_hash,
                "total_bytes": self.total_bytes,
                "chunk_size_bytes": self.chunk_size_bytes,
                "chunk_count": self.chunk_count,
            },
            "result": {
                "status": self.status,
                "output_path": self.output_path,
                "failed_items": self.failed_items,
            },
            "verification": {
                "verified": self.verified,
                "verified_at_utc": self.verified_at_utc,
                "hash_match": self.verification_hash_match,
            },
            "chain_of_custody": {
                "log_file": coc_log_path,
                "events": events,
            },
        }

    def to_html(self):
        """
        Rapor.json'daki AYNI bilgiyi, ekranda gosterilebilir/yazdirilabilir/
        paylasilabilir tek bir HTML dosyasi olarak uretir -- delil zinciri
        olay listesi dahil. Harici bir kutuphane gerekmez (PDF degil, ama
        tarayicidan "Yazdir -> PDF olarak kaydet" ile PDF'e cevrilebilir).
        """
        d = self.to_dict()

        def esc(v):
            return html.escape("" if v is None else str(v))

        status_renk = {"success": "#3F7D57", "partial": "#B98A2E", "failed": "#A64545"}.get(d["result"]["status"], "#6B6B6B")

        satirlar = "".join(
            f"<tr><td>{esc(e.get('timestamp_utc'))}</td><td>{esc(e.get('event'))}</td>"
            f"<td>{esc(e.get('description'))}</td><td>{esc(e.get('hash') or '')}</td></tr>"
            for e in d["chain_of_custody"]["events"]
        )
        basarisiz = "".join(f"<li>{esc(x)}</li>" for x in d["result"]["failed_items"]) or "<li>—</li>"

        return f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8">
<title>Chameleon Rapor — {esc(d['case']['case_id']) or 'Vaka'}</title>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 32px; color: #222; }}
  h1 {{ margin-bottom: 0; }}
  h2 {{ border-bottom: 2px solid #3B5D6B; padding-bottom: 4px; margin-top: 32px; color: #3B5D6B; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 8px; }}
  th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; font-size: 13px; }}
  th {{ background: #f0f0f0; }}
  .kv {{ display: grid; grid-template-columns: 220px 1fr; row-gap: 4px; }}
  .kv div:nth-child(odd) {{ font-weight: 600; color: #444; }}
  .status {{ display: inline-block; padding: 2px 10px; border-radius: 10px; color: white; background: {status_renk}; }}
  .footer {{ margin-top: 40px; font-size: 11px; color: #888; }}
</style></head>
<body>
  <h1>🦎 Chameleon — Adli Bilişim Raporu</h1>
  <div>Araç: {esc(d['tool']['name'])} v{esc(d['tool']['version'])} · Motor: {esc(d['tool']['engine'])} · Yöntem: {esc(d['tool']['method'])}</div>

  <h2>Vaka Bilgileri</h2>
  <div class="kv">
    <div>Vaka No</div><div>{esc(d['case']['case_id']) or '—'}</div>
    <div>İnceleyen</div><div>{esc(d['case']['examiner']) or '—'}</div>
    <div>Cihaz Sahibi / Yetkili Kişi</div><div>{esc(d['case']['custodian']) or '—'}</div>
    <div>Organizasyon</div><div>{esc(d['case']['organization']) or '—'}</div>
  </div>

  <h2>Alma Bilgileri</h2>
  <div class="kv">
    <div>Hedef İşletim Sistemi</div><div>{esc(d['acquisition']['target_os']) or '—'}</div>
    <div>Hedef Host</div><div>{esc(d['acquisition']['target_host']) or '—'}</div>
    <div>Kaynak</div><div>{esc(d['acquisition']['source_identifier']) or '—'}</div>
    <div>Alma Türü</div><div>{esc(d['acquisition']['acquisition_type']) or '—'}</div>
    <div>Bağlantı Yöntemi</div><div>{esc(d['acquisition']['connection_method']) or '—'}</div>
    <div>Başlangıç (UTC)</div><div>{esc(d['acquisition']['start_time_utc'])}</div>
    <div>Bitiş (UTC)</div><div>{esc(d['acquisition']['end_time_utc'])}</div>
    <div>Write-Blocking</div><div>{esc(d['acquisition']['write_blocking_applied'])} — {esc(d['acquisition']['write_blocking_reason']) or '—'}</div>
  </div>

  <h2>Bütünlük (Integrity)</h2>
  <div class="kv">
    <div>Hash Algoritması</div><div>{esc(d['integrity']['hash_algorithm'])}</div>
    <div>İmaj Hash</div><div style="word-break:break-all">{esc(d['integrity']['image_hash']) or '—'}</div>
    <div>Toplam Boyut (bayt)</div><div>{esc(d['integrity']['total_bytes']) or '—'}</div>
    <div>Parça Boyutu (bayt)</div><div>{esc(d['integrity']['chunk_size_bytes']) or '—'}</div>
    <div>Parça Sayısı</div><div>{esc(d['integrity']['chunk_count']) or '—'}</div>
  </div>

  <h2>Sonuç</h2>
  <div class="kv">
    <div>Durum</div><div><span class="status">{esc(d['result']['status'])}</span></div>
    <div>Çıktı Yolu</div><div style="word-break:break-all">{esc(d['result']['output_path']) or '—'}</div>
    <div>Başarısız Öğeler</div><div><ul>{basarisiz}</ul></div>
    <div>Doğrulama Yapıldı mı</div><div>{esc(d['verification']['verified'])}</div>
    <div>Hash Eşleşmesi</div><div>{esc(d['verification']['hash_match'])}</div>
  </div>

  <h2>Delil Zinciri (Chain of Custody)</h2>
  <table>
    <tr><th>Zaman (UTC)</th><th>Olay</th><th>Açıklama</th><th>Hash</th></tr>
    {satirlar}
  </table>

  <div class="footer">Bu rapor Chameleon tarafından otomatik üretilmiştir. Log dosyası: {esc(d['chain_of_custody']['log_file'])}</div>
</body></html>"""

    def save(self, output_dir, filename="report.json"):
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

        html_path = os.path.splitext(path)[0] + ".html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(self.to_html())

        self._append_to_history(path, html_path)
        return path

    def _append_to_history(self, report_path, html_path):
        """
        Bu raporun ozetini, motor/oturum fark etmeksizin TEK bir "Vaka
        Gecmisi" listesine ekler -- launcher'daki sidebar buradan okur.
        Dosya bozuksa/okunamazsa sessizce sifirdan baslanir (gecmis
        kaybi, rapor kaydini ENGELLEMEMELI).
        """
        os.makedirs(HISTORY_DIR, exist_ok=True)
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
            if not isinstance(history, list):
                history = []
        except (OSError, json.JSONDecodeError):
            history = []

        history.append({
            "case_id": self.case_id,
            "examiner": self.examiner,
            "custodian": self.custodian,
            "engine": self.engine,
            "method": self.method,
            "target_os": self.target_os,
            "target_host": self.target_host,
            "source_identifier": self.source_identifier,
            "connection_method": self.connection_method,
            "status": self.status,
            "start_time_utc": self.start_time_utc,
            "end_time_utc": self.end_time_utc,
            "report_path": report_path,
            "html_path": html_path,
        })

        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
        except OSError:
            pass


def read_history():
    """launcher/chameleon_gui.py'nin "Vaka Geçmişi" sayfasi icin: tum
    kayitli vaka ozetlerini en yeniden en eskiye dogru dondurur."""
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
        if not isinstance(history, list):
            return []
    except (OSError, json.JSONDecodeError):
        return []
    return list(reversed(history))
