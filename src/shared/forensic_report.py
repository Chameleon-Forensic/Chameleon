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

import hashlib
import html
import json
import os
import sys
from datetime import datetime, timezone

import chain_of_custody as coc
import tz_display
from version import VERSION as TOOL_VERSION

TOOL_NAME = "Chameleon"

# Tum motorlarin ayni "Vaka Gecmisi" listesini paylasmasi icin ortak,
# tek bir dizin -- launcher'daki sidebar buradan okuyor. Kisisel/vaka
# verisi oldugu icin .gitignore'da, asla commit edilmez.
#
# Derlenmis (.exe) modda __file__ yerine sys.executable'a gore hesaplanir --
# aksi halde vaka gecmisi PyInstaller'in her calistirmada silinen gecici
# _MEIPASS klasorune yazilir, uygulama kapaninca tamamen kaybolur (bkz.
# ssh_connector.CHAMELEON_KNOWN_HOSTS ile ayni gerekce, docs/roadmap.md).
if getattr(sys, "frozen", False):
    HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "data")
else:
    HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
HISTORY_FILE = os.path.join(HISTORY_DIR, "case_history.json")
TAGS_FILE = os.path.join(HISTORY_DIR, "case_tags.json")


def _now_iso():
    """chain_of_custody.py ile AYNI format (Z suffix, mikrosaniyesiz) --
    aksi halde read_events()'teki string karsilastirmasi bozulur."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ForensicReport:
    def __init__(self, case_id="", examiner="", organization="", custodian="", display_timezone=None):
        self.case_id = case_id
        self.examiner = examiner
        self.organization = organization
        # Cihazin/verinin alindigi taraftaki yetkili kisi (orn. sirket
        # calisanı, cihaz sahibi) -- kim inceledi kadar "cihaz kimden,
        # kimin izniyle alindi" bilgisi de delil zinciri icin onemli.
        self.custodian = custodian
        # SADECE report.html'de (insan tarafindan okunan) UTC zaman
        # damgalarinin YANINA eklenen bir yerel saat aciklamasi icin --
        # tz_display.common_timezones()'dan bir IANA anahtari (orn.
        # "Europe/Istanbul") ya da None/"UTC" (hic eklenmez). report.json'un
        # KENDISI (to_dict()) bundan HIC etkilenmez, hep saf UTC kalir --
        # delil olarak gecerli olan deger budur.
        self.display_timezone = display_timezone

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
        self.md5_hash = None
        self.sha1_hash = None
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
               chunk_size_bytes=None, chunk_count=None, failed_items=None,
               md5_hash=None, sha1_hash=None):
        """Alma islemi bitince (basarili/basarisiz fark etmez) cagrilir.

        md5_hash/sha1_hash: cagiran taraf bunlari ZATEN hesapladiysa (orn.
        hash_verifier.hash_file_multi ile SHA-256'yla AYNI okuma gecisinde)
        buraya dogrudan verilir -- boylece dosya IKINCI KEZ okunmaz. Eskiden
        bu ikisi HER ZAMAN burada, SHA-256 hesaplandiktan SONRA dosyayi
        bastan sona tekrar okuyarak hesaplaniyordu; buyuk bir disk imajinda
        (100+ GB) bu, imaj alma suresini neredeyse ikiye katliyordu (bkz.
        docs/hatalar_ve_sonuclar.md). Verilmezlerse (henuz tum cagiran
        yerler guncellenmedigi icin, orn. eski/ozel bir cagri) asagidaki
        FALLBACK ile eskisi gibi dosyadan hesaplanir -- davranis hicbir
        cagiran icin BOZULMAZ, sadece guncellenenler icin hizlanir.
        """
        self.end_time_utc = _now_iso()
        self.status = status
        self.output_path = output_path
        self.image_hash = image_hash
        self.total_bytes = total_bytes
        self.chunk_size_bytes = chunk_size_bytes
        self.chunk_count = chunk_count
        self.failed_items = failed_items or []

        if md5_hash is not None or sha1_hash is not None:
            self.md5_hash = md5_hash
            self.sha1_hash = sha1_hash
            return

        # FALLBACK: cagiran md5_hash/sha1_hash gecirmedi -- eski davranis
        # (dosyayi burada, IKINCI KEZ, bastan sona okuyarak hesapla).
        # Birincil butunluk degeri SHA-256 (image_hash) olarak kalir --
        # chunk dogrulama/resume/verify_report.py hep onu kullanir. Dosya
        # yoksa/okunamiyorsa (ornegin basarisiz islem, ya da klasor
        # modunda tek bir "output_path" olmamasi) sessizce None birakilir.
        if output_path and os.path.isfile(output_path):
            try:
                md5 = hashlib.md5()
                sha1 = hashlib.sha1()
                with open(output_path, "rb") as f:
                    for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
                        md5.update(block)
                        sha1.update(block)
                self.md5_hash = md5.hexdigest()
                self.sha1_hash = sha1.hexdigest()
            except OSError:
                pass
            except ValueError:
                # FIPS uyumlu OpenSSL derlemelerinde hashlib.md5()/sha1()
                # "kisitli algoritma" diye ValueError firlatir (gorev
                # yapan/kanun uygulayici makinelerde beklenmedik degil).
                # SHA-256 zaten birincil butunluk degeri, MD5/SHA-1 sadece
                # ek/uyumluluk alani -- bu yuzden burada rapor kaydini
                # BOZMADAN sessizce None birakiyoruz.
                pass

    def set_verification(self, matched):
        self.verified = True
        self.verified_at_utc = _now_iso()
        self.verification_hash_match = matched
        # Dogrulama, alma islemi bitince (end_time_utc) SONRA yapilir --
        # to_dict()'teki coc.read_events() penceresi end_time_utc'de
        # kapandigi icin, bunu genisletmezsek HASH_VERIFIED olayi diskteki
        # log dosyasinda olsa bile bu raporun kendi "chain_of_custody.events"
        # listesine hic girmezdi (rapor "verified: true" derken, ayni
        # rapordaki olay listesi bunu dogrulayan hicbir kayit gostermezdi).
        if self.end_time_utc and self.verified_at_utc > self.end_time_utc:
            self.end_time_utc = self.verified_at_utc

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
                "md5_hash": self.md5_hash,
                "sha1_hash": self.sha1_hash,
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
    <div>Başlangıç (UTC)</div><div>{esc(tz_display.format_with_local(d['acquisition']['start_time_utc'], self.display_timezone))}</div>
    <div>Bitiş (UTC)</div><div>{esc(tz_display.format_with_local(d['acquisition']['end_time_utc'], self.display_timezone))}</div>
    <div>Write-Blocking</div><div>{esc(d['acquisition']['write_blocking_applied'])} — {esc(d['acquisition']['write_blocking_reason']) or '—'}</div>
  </div>

  <h2>Bütünlük (Integrity)</h2>
  <div class="kv">
    <div>Hash Algoritması</div><div>{esc(d['integrity']['hash_algorithm'])}</div>
    <div>İmaj Hash</div><div style="word-break:break-all">{esc(d['integrity']['image_hash']) or '—'}</div>
    <div>MD5</div><div style="word-break:break-all">{esc(d['integrity']['md5_hash']) or '—'}</div>
    <div>SHA-1</div><div style="word-break:break-all">{esc(d['integrity']['sha1_hash']) or '—'}</div>
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

  <div class="footer">Bu rapor Chameleon tarafından otomatik üretilmiştir. Log dosyası: {esc(d['chain_of_custody']['log_file'])}
  {"<br>Parantez içindeki yerel saat SADECE okunabilirlik içindir; delil olarak geçerli olan değer her zaman UTC'dir." if self.display_timezone and self.display_timezone != "UTC" else ""}</div>
</body></html>"""

    def save(self, output_dir, filename="report.json"):
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, filename)
        report_bytes = json.dumps(self.to_dict(), indent=2, ensure_ascii=False).encode("utf-8")
        with open(path, "wb") as f:
            f.write(report_bytes)

        html_path = os.path.splitext(path)[0] + ".html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(self.to_html())

        # report.json'un KENDISI sonradan degistirilirse (rapor uzerinde
        # oynama) bunu ayrica fark edebilmek icin -- rapor bir kere
        # kaydedildikten sonra bu hash'e karsi tekrar dogrulanabilir.
        # save() dogrulama sonrasi TEKRAR cagrildiginda (set_verification)
        # bu dosya da guncel icerige gore YENIDEN yazilir -- kasitli:
        # sidecar her zaman "su an diskteki report.json'un hash'i" olmali.
        sha256_path = path + ".sha256"
        with open(sha256_path, "w", encoding="utf-8") as f:
            f.write(f"{hashlib.sha256(report_bytes).hexdigest()}  {filename}\n")

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

        entry = {
            "case_id": self.case_id,
            "examiner": self.examiner,
            "custodian": self.custodian,
            "organization": self.organization,
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
        }
        # save() dogrulama sonrasi TEKRAR cagrilabilir (bkz. set_verification
        # kullanan gui_v2.py) -- ayni report_path icin ikinci bir satir
        # EKLEMEK yerine mevcut kaydi guncelliyoruz, aksi halde Vaka
        # Gecmisi'nde ayni vaka iki kez gorunurdu.
        for i, h in enumerate(history):
            if h.get("report_path") == report_path:
                history[i] = entry
                break
        else:
            history.append(entry)

        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
        except OSError:
            pass


def export_pdf(report_json_path, pdf_path):
    """
    Diskteki bir report.json'dan (Vaka Gecmisi'nden -- artik canli bir
    ForensicReport nesnesi yok, sadece kaydedilmis dosya var), to_html()
    ile AYNI bolumleri (Vaka/Alma/Butunluk/Sonuc/Delil Zinciri) iceren
    tek sayfalik(*) bir PDF uretir. (*sayfa sayisi delil zinciri olay
    sayisina gore buyur.)

    report.json HER ZAMAN saf UTC tutar (display_timezone kaydedilmez,
    bkz. to_dict()) -- bu yuzden PDF'te de zaman damgalari hep UTC,
    to_html()'deki yerel saat eklentisi burada YOK (kayitli dosyadan
    o bilgi geri kazanilamaz, ki zaten delil olarak gecerli olan UTC).
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    )

    with open(report_json_path, "r", encoding="utf-8") as f:
        d = json.load(f)

    # ReportLab'in yerlesik fontlari (Helvetica vb.) WinAnsi/Latin-1 ile
    # sinirli -- Turkce'ye ozgu I/i/s/g karakterlerini (Latin Extended-A)
    # icermiyor, siyah kutu olarak basiliyorlardi. Qt arayuzu icin zaten
    # gomulu olan (shared/assets/fonts/Inter.ttf, SIL OFL) fontu burada da
    # kullaniyoruz -- yeni bir font dosyasi eklemeye gerek kalmadi. Ayri
    # bir bold TTF'i yok; "<b>" etiketlerinin patlamamasi icin "Inter-Bold"
    # adini AYNI dosyaya esliyoruz (gorsel olarak kalin cikmaz, ama en
    # azindan hatasiz render edilir).
    _font_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "assets", "fonts", "Inter.ttf"
    )
    if "Inter" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("Inter", _font_path))
        pdfmetrics.registerFont(TTFont("Inter-Bold", _font_path))
        pdfmetrics.registerFontFamily("Inter", normal="Inter", bold="Inter-Bold")

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontName="Inter-Bold", fontSize=16)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName="Inter-Bold",
                         textColor=colors.HexColor("#3B5D6B"), spaceBefore=14, spaceAfter=4)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontName="Inter")

    def g(*keys):
        cur = d
        for k in keys:
            cur = (cur or {}).get(k)
        return "—" if cur in (None, "") else str(cur)

    def kv_table(rows):
        data = [[Paragraph(f"<b>{label}</b>", body), Paragraph(value, body)] for label, value in rows]
        tbl = Table(data, colWidths=[55 * mm, 115 * mm])
        tbl.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
        ]))
        return tbl

    story = [
        Paragraph("Chameleon — Adli Bilişim Raporu", h1),
        Paragraph(f"Araç: {g('tool', 'name')} v{g('tool', 'version')} · "
                  f"Motor: {g('tool', 'engine')} · Yöntem: {g('tool', 'method')}", body),

        Paragraph("Vaka Bilgileri", h2),
        kv_table([
            ("Vaka No", g("case", "case_id")),
            ("İnceleyen", g("case", "examiner")),
            ("Cihaz Sahibi / Yetkili Kişi", g("case", "custodian")),
            ("Organizasyon", g("case", "organization")),
        ]),

        Paragraph("Alma Bilgileri", h2),
        kv_table([
            ("Hedef İşletim Sistemi", g("acquisition", "target_os")),
            ("Hedef Host", g("acquisition", "target_host")),
            ("Kaynak", g("acquisition", "source_identifier")),
            ("Alma Türü", g("acquisition", "acquisition_type")),
            ("Bağlantı Yöntemi", g("acquisition", "connection_method")),
            ("Başlangıç (UTC)", g("acquisition", "start_time_utc")),
            ("Bitiş (UTC)", g("acquisition", "end_time_utc")),
            ("Write-Blocking", f"{g('acquisition', 'write_blocking_applied')} — "
                                f"{g('acquisition', 'write_blocking_reason')}"),
        ]),

        Paragraph("Bütünlük (Integrity)", h2),
        kv_table([
            ("Hash Algoritması", g("integrity", "hash_algorithm")),
            ("İmaj Hash", g("integrity", "image_hash")),
            ("MD5", g("integrity", "md5_hash")),
            ("SHA-1", g("integrity", "sha1_hash")),
            ("Toplam Boyut (bayt)", g("integrity", "total_bytes")),
            ("Parça Boyutu (bayt)", g("integrity", "chunk_size_bytes")),
            ("Parça Sayısı", g("integrity", "chunk_count")),
        ]),

        Paragraph("Sonuç", h2),
        kv_table([
            ("Durum", g("result", "status")),
            ("Çıktı Yolu", g("result", "output_path")),
            ("Başarısız Öğeler", ", ".join(d.get("result", {}).get("failed_items") or []) or "—"),
            ("Doğrulama Yapıldı mı", g("verification", "verified")),
            ("Hash Eşleşmesi", g("verification", "hash_match")),
        ]),

        Paragraph("Delil Zinciri (Chain of Custody)", h2),
    ]

    events = d.get("chain_of_custody", {}).get("events") or []
    header_row = [Paragraph(f"<b>{h}</b>", body) for h in ("Zaman (UTC)", "Olay", "Açıklama", "Hash")]
    event_rows = [header_row]
    for e in events:
        event_rows.append([
            Paragraph(str(e.get("timestamp_utc") or ""), body),
            Paragraph(str(e.get("event") or ""), body),
            Paragraph(str(e.get("description") or ""), body),
            Paragraph(str(e.get("hash") or ""), body),
        ])
    events_tbl = Table(event_rows, colWidths=[32 * mm, 38 * mm, 70 * mm, 30 * mm], repeatRows=1)
    events_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F0F0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(events_tbl)

    doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                             leftMargin=18 * mm, rightMargin=18 * mm,
                             topMargin=16 * mm, bottomMargin=16 * mm)
    doc.build(story)


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


def read_tags():
    """Vaka Gecmisi'ndeki kullanici tanimli etiketleri dondurur --
    {report_path: etiket_metni} seklinde. Dosya yoksa/bozuksa bos sozluk
    doner (etiketsiz gorunum, veri kaybi degil)."""
    try:
        with open(TAGS_FILE, "r", encoding="utf-8") as f:
            tags = json.load(f)
        if not isinstance(tags, dict):
            return {}
    except (OSError, json.JSONDecodeError):
        return {}
    return tags


def set_tag(report_path, tag_text):
    """Bir vakanin etiketini kaydeder/gunceller. tag_text bos ise
    etiket tamamen kaldirilir (dosyada gereksiz bos anahtar birikmesin)."""
    os.makedirs(HISTORY_DIR, exist_ok=True)
    tags = read_tags()
    tag_text = (tag_text or "").strip()
    if tag_text:
        tags[report_path] = tag_text
    else:
        tags.pop(report_path, None)
    try:
        with open(TAGS_FILE, "w", encoding="utf-8") as f:
            json.dump(tags, f, indent=2, ensure_ascii=False)
    except OSError:
        pass
