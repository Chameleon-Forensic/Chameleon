# Code Review Bulguları ve Düzeltmeler — Bu Oturum

> Bu dosya, bu oturumda yapılan correctness odaklı code review'ların
> (bulgular + düzeltmeler + regresyon testleri) tek bir yerde toplandığı
> rapordur. Kod içi daha kalıcı açıklamalar ilgili modülün başında/docstring'inde,
> roadmap'e madde madde özet de eklendi.

## Kapsam (bu oturumda review edilen modüller)

1. `src/engines/ram_engine/ram_gui.py` — RAM motoru GUI'si + WinPmem çağırma mantığı
2. `src/shared/incomplete_ops.py` — "Yarım Kalanlar" JSON kayıt defteri

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

## Değiştirilen Dosyalar

| Dosya | Değişiklik |
|---|---|
| `src/engines/ram_engine/ram_gui.py` | Popen OSError UnboundLocalError düzeltmesi |
| `tests/test_ram_winpmem.py` | Bozuk test yeniden yazıldı + 1 yeni test |
| `src/shared/incomplete_ops.py` | Lock + atomik yazma + logging + tip güvenliği |
| `tests/test_incomplete_ops.py` | Yeni: 13 regresyon testi |
| `docs/roadmap.md` | "Yapıldı" listesine 2 madde (bu dosyadaki özetlerin kısaltılmışı) |
| `docs/code_review_bulgulari.md` | Bu rapor (yeni) |

## Test Komutu

```
QT_QPA_PLATFORM=offscreen PYTHONPATH=src pytest tests/ -q --timeout=60
```
