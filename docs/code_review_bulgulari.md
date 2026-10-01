# Code Review Bulguları ve Düzeltmeler — Bu Oturum

> Bu dosya, bu oturumda yapılan correctness odaklı code review'ların
> (bulgular + düzeltmeler + regresyon testleri) tek bir yerde toplandığı
> rapordur. Kod içi daha kalıcı açıklamalar ilgili modülün başında/docstring'inde,
> roadmap'e madde madde özet de eklendi.

## Kapsam (bu oturumda review edilen modüller)

1. `src/engines/ram_engine/ram_gui.py` — RAM motoru GUI'si + WinPmem çağırma mantığı
2. `src/shared/incomplete_ops.py` — "Yarım Kalanlar" JSON kayıt defteri
3. `src/engines/ssh_engine/local_collector/gui_v2.py` — worker thread sınıfları (ConnectWorker / AcquisitionWorker / VerifyWorker) ve sinyal/slot bağlantıları
4. `src/launcher/chameleon_gui.py` — ana launcher (shell yeniden kurulumu, korunan sayfa yaşam döngüsü, PDF/CSV dışa aktarma)

---

## 1. `ram_gui.py` — RAM motoru

### Bulgu 1.1 — Popen kendisi OSError fırlatırsa `UnboundLocalError`

- **Sorun:** `_run_process_mode()` içinde `subprocess.Popen(...)` çağrısı
  `try` bloğunun İÇİNDE `proc` değişkenine atanıyor. Popen'in kendisi
  OSError fırlatırsa (örn. `exe` bulunamadı, `[WinError 2]`), `proc` hiç
  atanmamış oluyor; `except OSError` bloğu bunu bilmeden `proc.wait()`
  çağırınca `UnboundLocalError` fırlatıyordu (içteki `except Exception`
  bunu yakalayıp yutuyordu ama akış yanlış/tanimsiz davranışa düşüyordu).
- **Düzeltme:** `proc = None` ile döngü öncesi başlatıldı; `except OSError`
  içinde `proc is not None` kontrolü eklenerek yalnızca süreç gerçekten
  başladıysa `proc.wait(timeout=5)` ile beklenip zombi kalması engelleniyor.
- **Regresyon testleri:**
  - `test_run_process_mode_waits_for_process_on_oserror` — stdout okuma
    sırasında OSError simüle edilir, `proc.wait(timeout=5)` çağrıldığı
    doğrulanır (eski kodda çağrılmıyordu).
  - `test_run_process_mode_popen_oserror_beklemeden_gecer` — Popen'in
    kendisi OSError fırlatır, worker `run()` çökmeden tamamlanır ve
    "Başlatılamadı" logu kullaniciya gider (eski kodda UnboundLocalError).

### Bulgu 1.2 — Önceki oturumdan kalan yarım/bozuk test

- **Sorun:** Önceki oturumda `tests/test_ram_winpmem.py`'ye eklenmeye
  çalışılan aynı isimli test, yanlış mock'lar (`iter([])` OSError
  üretmediği için test hiçbir şeyi doğrulamıyordu), eksik `os` import'u
  (`NameError: name 'os' is not defined`) ve birbirini tutarsız tekrar eden
  yorumlarla yarım kalmıştı.
- **Düzeltme:** Test tamamen yeniden yazıldı (yukarıdaki iki test ile
  değiştirildi); gerçek bir OSError akışı simüle ediliyor.

**Sonuç:** `tests/test_ram_winpmem.py` 15/15 geçti (offscreen).

---

## 2. `incomplete_ops.py` — "Yarım Kalanlar" kayıt defteri

### Bulgu 2.1 — Read-modify-write yarış koşulu (TOCTOU)

- **Sorun:** `record_start()` / `record_finish()` `_read_all()` →
  bellekte düzenle → `_write_all()` desenini kilit (lock) olmadan
  yapıyordu. İki thread aynı anda çağırırsa (örn. RAM worker + kapanış
  sırasında launcher'ın `list_incomplete()` okuması), son yazan diğerinin
  değişikliğini ÜSTÜNE YAZIYOR — kayıt kaybı ya da silinmiş bir kaydın
  geri gelmesi mümkündü.
- **Düzeltme:** Modül düzeyinde `threading.Lock` (`_LOCK`) eklendi;
  `record_start` / `record_finish` / `list_incomplete` artık kilit
  altında atomik çalışıyor.

### Bulgu 2.2 — Yazma sırasında yarım/bozuk JSON bırakma riski

- **Sorun:** `_write_all()` doğrudan hedef dosyayı açıp yazıyordu;
  yazma ortasında çökme/elektrik kesintisi dosyayı YARIM JSON olarak
  bırakır, bir sonraki açılışta TÜM kayıtlar sessizce kaybolurdu.
- **Düzeltme:** Atomik yazma deseni: geçici dosyaya yaz → `flush()` +
  `os.fsync()` → `os.replace()` (aynı disk üzerinde atomiktir). Yazma
  hatasında geçici dosya temizleniyor.

### Bulgu 2.3 — Bozuk/yanlış tipli JSON sessizce yutuluyordu

- **Sorun:** `_read_all()` bozuk JSON'da (ve `JSONDecodeError`'da) boş
  dict dönüyordu ama hiçbir iz bırakmıyordu; dosya bir dizi (`[]`) gibi
  dict olmayan bir JSON içerseydi de aynı şekilde "boş kayıt defteri"
  gibi davranıp sonraki `_write_all()` ile dosyanın üzerine yazıyordu.
  Adli araçta sessiz veri kaybı kabul edilemez.
- **Düzeltme:** `logging` eklendi — bozuk JSON ve dict-olmayan içerik
  durumunda `logger.warning()` yazılıyor (çökme yok, davranış korunuyor
  ama artık İZ BIRAKIYOR). `FileNotFoundError` ile diğer `OSError`
  ayrıştırıldı (dosya yokluğu normal ilk-açılış durumu, uyarı gereksiz).

### Bulgu 2.4 — `record_finish()` false-yapıcı değerleri sessizce yutuyordu

- **Sorun:** `if not op_id:` kontrolü `None`, `False`, `0`, boş string
  YANINDA `0`-benzeri her değeri reddediyor ama amaçlanan "boş/None id
  gelirse hiçbir şey yapma" anlamından fazlasını da yutuyordu; string
  olmayan tipler (int vb.) sessizce geçiyor, `in` kontrolünde
  çalışıyordu. Amaçlanan sözleşme: id YA record_start'tan gelen string
  YA da hiçbir şey.
- **Düzeltme:** `isinstance(op_id, str) and op_id` — sadece gerçek bir
  string id işleniyor; diğerleri belgelenmiş şekilde sessizce reddediliyor.

### Bulgu 2.5 — `_read_all()` döndürdüğü dict'i çağıranla PAYLAŞIYOR

- **Sorun:** Dönen dict doğrudan dosyadan yüklenen nesneydi; çağıran
  tarafın yanlışlıkla üzerinde yaptığı bir değişiklik, bir sonraki
  `_write_all()` ile kalıcı hale gelebiliyordu.
- **Düzeltme:** `dict(data)` kopyası dönülüyor.

**Regresyon testleri (`tests/test_incomplete_ops.py`, 13 test):**
- Boş klasörde `list_incomplete()` boş döner
- `record_start` → `list_incomplete` → `record_finish` tam akışı
- Çok kayıtlı durumda tek silme, diğer kaydı bozmaz
- Var olmayan id ile `record_finish` çökmez
- Geçersiz id tipleri (None/False/0/""/123) kayıt defterini bozmaz
- Bozuk JSON'da çökmez + uyarı loglanır + sonra tekrar yazmaya devam eder
- Dict-olmayan JSON'da (`[]`) boş kayıt defteriyle devam eder
- Atomik yazma sonrası geçici `.tmp` dosyası KALMAZ
- 8 thread'in eşzamanlı `record_start`'ı → 8 kayıt, kimlik çakışması yok
  (kilit olmadan bu test kayıp verir)
- Okuma/yazma eşzamanlı iken çökme/veri kaybı yok
- 300 ardışık `record_start` → 300 benzersiz kayıt

**Sonuç:** `tests/test_incomplete_ops.py` 13/13 + mevcut
`test_incomplete_ops_labels.py` 1/1 geçti.

---

## 3. `gui_v2.py` — worker thread'ler (ConnectWorker / AcquisitionWorker / VerifyWorker)

### Bulgu 3.1 — [KRİTİK] `_run_windows_disk`: `segments` NameError, başarı akışında rapor kaybı

- **Sorun:** Windows disk kolu, Linux koluyla BİREBİR aynı birleştirme/hash/log
  akışını kullanıyor ama `segments` değişkenini SADECE Linux kolu
  tanımlıyordu. Windows disk imajı BAŞARIYLA bitince
  `raw_bytes = ... if segments else ...` satırı `NameError` fırlatıyordu;
  geniş `except Exception` bunu yutup sadece traceback logluyordu. Sonuç:
  rapor HİÇ kaydedilmiyor, "İmaj alma tamamlandı" durumu gösterilmiyor,
  kullanıcının eline imaj dosyası geçiyor ama raporu/hash kaydı YOK —
  adli araçta bu, delil zinciri kopması demek.
- **Düzeltme:** Kolun başında `segments = None` başlatması eklendi.
- **Regresyon:** `test_windows_disk_success_flow_does_not_hit_nameerror` —
  mock'lu tam başarı akışı, NameError olmadan rapor üretir.

### Bulgu 3.2 — Windows kolunda segment (bölünmüş imaj) özelliği sessizce yoktu

- **Sorun:** `segment_size_bytes` GUI'de seçilebiliyor ve
  `_start_disk_windows` ctx'e koyuyordu, ama `_run_windows_disk` içinde
  HİÇ kontrol edilmiyordu — kullanıcı "650 MB / 2 GB / 4 GB segment"
  seçse bile sessizce tek dosya birleştiriliyordu. Linux'ta çalışan
  özelliğin Windows'ta sessiz kaybı (kullanıcı seçimine güvenilmiyordu).
- **Düzeltme:** Linux kolundaki birebir segment akışı Windows koluna da
  eklendi (`write_segments` çağrısı, başarısızlıkta failed raporu,
  `hash_files_multi`, `raw_bytes` hesabı, doğrulama atlama logu).
- **Regresyon:** `test_windows_disk_with_segments_flow_also_works`
  (segment seçilince write_segments GERÇEKTEN çağrılıyor — eski kodda
  çağrılmıyordu) + `test_windows_disk_segments_none_keeps_concatenate_flow`
  (varsayılan akış bozulmadı).

### Değerlendirilip DOKUNULMAYAN bulgular (bilinçli karar)

- `_on_worker_ask_yesno`, worker'ın instance niteliklerine cevap yazıyor
  (`_yesno_result`/`_yesno_event`) — widget kapatılıp yeniden açılırsa
  cevap eski worker'a yazılabilir, ama mevcut tek-pencere mimaride bu
  senaryo pratik olarak erişilemez (roadmap'te not, dokunulmadı).
- `_on_connected`, `ssh.list_disks()`'i UI thread'inde çağırıyor — yavaş
  bağlantıda UI kısa süre donabilir; bu bilinçli bir sadelik tercihi
  (ayrı worker'a almak bağlantı akışını 3 parçaya böler), raporlandı ama
  değiştirilmedi.
- `StdoutRedirector` ve `_ask_yesno_blocking` (threading.Event deseni)
  incelendi, doğru — dokunulmadı.

**Sonuç:** `tests/test_gui_v2_windows_segments.py` 3/3 + mevcut
`test_acquisition_worker.py` 9/9 geçti; tüm suite 264 geçti (baseline
2 ilgisiz Windows-symlink-yetkisi fail'i dışında).

---

## 4. `chameleon_gui.py` — ana launcher

### Bulgu 4.1 — Tema/dil değişimi, korunmuş araç ekranını imha ediyordu (use-after-free)

- **Sorun:** `_build_shell()`, `setCentralWidget()` ile ESKİ central
  widget'ı (ve tüm çocuklarını) SİLER. Kullanıcı araç ekranında çalışan
  bir iş bırakıp (`_active_tool_widget`) ya da Bilgi Merkezi'ndeki
  "Geri dönüş" sayfasını (`_return_page`) AYARLAR'a gidip tema/dil
  değiştirdiğinde, bu fonksiyon o sayfaları da siler ama referanslar
  silinmiş Qt nesnelerine dönerdi — sonraki `_resume_active_tool()` /
  `_return_from_help()` çağrısı PySide6 `RuntimeError` ("Internal C++
  object already deleted") ile uygulamayı çökertiyordu.
- **Düzeltme:** `_build_shell()` yıkımdan ÖNCE yeni `_drop_preserved_pages()`
  yardımcısını çağırıyor — referansları (ve `_active_tool_kind/_method`,
  `_return_nav` metadata'sını) sıfırlıyor; Qt'nin widget'ı kendisinin
  silmesine izin veriyor, çift-silme yapılmıyor.
- **Regresyon:** `tests/test_launcher_theme_lang_state.py` (3 test) —
  tema değişimi sonrası `_active_tool_widget is None` + resume çökmez;
  dil değişimi sonrası `_return_page is None` + return çökmez; korunan
  sayfa yokken davranış değişmez.

### Bulgu 4.2 — RAM "Yeniden Başlat" prefill'i `case_notes`'u kaybediyordu

- **Sorun:** `_show_incomplete_operations` RAM kartındaki case_prefill
  dict'i case_id/examiner/custodian/organization taşıyordu ama
  case_notes'u KESİNLİKLE unutuyordu — `incomplete_ops.record_start`
  details'a koysa bile kaybolacaktı (diğer alanlarla tutarsız).
- **Düzeltme:** Prefill dict'ine `case_notes` eklendi.
- **Regresyon:** `test_ram_engine_prefill_carries_case_notes`.

### Bulgu 4.3 — PDF dışa aktarmada çıplak import çökmesi

- **Sorun:** `_export_report_pdf` içinde çıplak `import forensic_report`
  vardı — modül herhangi bir sebeple yüklenemezse (bozuk kurulum/
  paketleme hata mesajı vb.) buton tıklaması uygulamayı CRASH ederdi;
  `_show_case_history` aynı durumda düzgün bir hata mesajı gösteriyordu.
- **Düzeltme:** ImportError yakalanıp `_history_status` etiketine
  `case_history_load_error` mesajı yazılıyor (aynı desen zaten
  `_show_case_history`'de ve `_recent_case_card`'da vardı).
- **Regresyon:** `test_export_report_pdf_survives_forensic_report_import_error`
  (builtins.__import__ mock'lanarak ImportError simüle edilir).

### Değerlendirilip DOKUNULMAYAN bulgular (bilinçli karar)

- `_show_incomplete_operations` içindeki `try/except ImportError: pass`
  blokları, modül yüklenemezse SSH/RAM kaynaklarını sessizce atlıyor —
  bu bilinçli bir sadelik; sayfanın TAMAMI boş görünüyor ("kaynak yok"
  ile aynı), hata mesajı eklemek launcher'ın dağıtım kesitine (target_kit
  modu) bağımlı ekstra UI gerektirecekti, dokunulmadı.
- 6 dilin TAMAMI test edildi (strings.py'de eksik çeviri anahtarı yok —
  doğrulandı), `_apply_lang` dönüşümü doğru çalışıyor.

**Sonuç:** `tests/test_launcher_theme_lang_state.py` 3/3 +
`tests/test_launcher_case_prefill_pdf.py` 2/2 geçti; tüm suite 269 geçti
(baseline 2 ilgisiz Windows-symlink-yetkisi fail'i dışında).

---

## Değiştirilen Dosyalar

| Dosya | Değişiklik |
|---|---|
| `src/engines/ram_engine/ram_gui.py` | Popen OSError UnboundLocalError düzeltmesi |
| `tests/test_ram_winpmem.py` | Bozuk test yeniden yazıldı + 1 yeni test |
| `src/shared/incomplete_ops.py` | Lock + atomik yazma + logging + tip güvenliği |
| `tests/test_incomplete_ops.py` | Yeni: 13 regresyon testi |
| `src/engines/ssh_engine/local_collector/gui_v2.py` | Windows kolu segments NameError + eksik segment akışı |
| `tests/test_gui_v2_windows_segments.py` | Yeni: 3 regresyon testi |
| `src/launcher/chameleon_gui.py` | Tema/dil değişiminde use-after-free + 2 küçük düzeltme |
| `tests/test_launcher_theme_lang_state.py` | Yeni: 3 regresyon testi |
| `tests/test_launcher_case_prefill_pdf.py` | Yeni: 2 regresyon testi |
| `docs/roadmap.md` | "Yapıldı" listesine review maddeleri |
| `docs/code_review_bulgulari.md` | Bu rapor (yeni) |

## Test Komutu

```
QT_QPA_PLATFORM=offscreen PYTHONPATH=src pytest tests/ -q --timeout=60
```
