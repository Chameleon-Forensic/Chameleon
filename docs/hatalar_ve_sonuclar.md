# Hatalar ve Sonuçlar

Karşılaşılan somut hataların kaydı: ne bozuktu, kök neden neydi, nasıl
düzeltildi, nasıl doğrulandı. Genel/tekrar edilebilir teknik dersler için
[ogrenilenler.md](ogrenilenler.md)'e bakın.

---

## Komut enjeksiyonu açığı (`disk_path` / `remote_path`)

**Belirti:** Kullanıcıdan (GUI) gelen disk/dosya yolu, uzak komutlara
`shlex.quote()` olmadan f-string ile gömülüyordu — özel karakter içeren
bir yol, uzak sunucuda istenmeyen bir komut çalıştırabilirdi.

**Kök neden:** `image_acquirer.py` ve `write_block_helper.py`'de komut
metni oluşturulurken kaçırma (escaping) atlanmıştı.

**Çözüm:** İlgili tüm yerlerde `shlex.quote()` eklendi (Linux tarafı);
Windows tarafında karşılığı olarak `powershell_quote()` (kendi yazdığımız
fonksiyon) + `-LiteralPath` kullanıldı, `disk_number` her yerde `int()`'e
zorlandı.

**Sonuç:** Enjeksiyon denemesi (özel karakterli bir yol) mock SSH ile
test edildi, komutun artık güvenli tek parça string olarak gittiği
doğrulandı.

---

## Pencere ikonu bukalemun logosuna hiç dönmüyordu

**Belirti:** Launcher penceresinin sol üstündeki ikon (başlık çubuğu),
`shared/assets/chameleon_icon.png`'yi ayarlamaya rağmen hep genel/mavi bir
simge olarak kalıyordu.

**İlk (yanlış) teşhis:** `.ico` dosyasının 256×256 boyutundaki girdisinin
PNG-sıkıştırmalı olması yüzünden Tk'nin `iconbitmap()`'i sessizce
başarısız olduğu sanıldı; `iconphoto()` (PNG) tek başına kullanıldı ama
sorun DEVAM ETTİ.

**Gerçek kök neden:** `customtkinter`'ın kendisi, `CTk()`/`CTkToplevel()`
kurucusunda, kullanıcı KENDİ `iconbitmap()` metodunu (CTk'nin izlediği,
`_iconbitmap_method_called` bayrağını işaretleyen versiyon) hiç
çağırmadıysa, 200ms sonra kendi varsayılan logosunu baslığa basıyor
(`ctk_tk.py` → `_windows_set_titlebar_icon`). `iconphoto()` bu izlemeyi
tetiklemediği için CTk sessizce üstüne yazıyordu.

**Çözüm:** `self.root.iconbitmap(ICON_ICO)` çağrısına geri dönüldü (CTk'nin
kendi metodundan geçtiği için artık üstüne yazılmıyor); `iconphoto()` ek
güvence olarak sonrasında da bırakıldı. Aynı düzeltme splash ekranı
(`CTkToplevel`) için de uygulandı.

**Sonuç:** Kod okunarak (`customtkinter/windows/ctk_tk.py` kaynağı)
kesinleştirildi. Derlenmiş exe'de görsel doğrulama, bu ortamda ekran
görüntüsü alma güvenilir çalışmadığı için (başka pencereleri yakalıyordu)
kullanıcı tarafından yapılacak.

---

## Derlenmiş `.exe`'de "SSH motoru yüklenemedi"

**Belirti:** Kaynaktan (`python launcher/chameleon_gui.py`) çalıştırılınca
sorun yokken, `dist/Chameleon.exe`'de "SSH ile Uzak İmaj Al" sayfasında
"Başlat"a basınca "SSH motoru yüklenemedi: cannot import name
'scrolledtext' from 'tkinter'" hatası alınıyordu.

**Kök neden:** `gui_v2.py`, PyInstaller'ın derleme-zamanı analizine değil,
`chameleon_gui.py`'nin ÇALIŞMA ANINDA `sys.path.insert()` + `import`
etmesine dayanıyor (bkz. `build.spec`'teki açıklama). PyInstaller, bu
şekilde yüklenen dosyaların `from tkinter import scrolledtext,
messagebox, filedialog` gibi ihtiyaçlarını STATİK ANALİZLE GÖREMEZ —
sadece `chameleon_gui.py`'nin (giriş noktası) doğrudan yaptığı
importları görür. `scrolledtext`/`messagebox`/`filedialog` bu yüzden
paketlenmemiş, exe içinde `tkinter` çekirdeği var ama bu alt modüller
yoktu.

**Teşhis yöntemi:** 28MB'lık tam exe'yi tekrar tekrar derlemek yerine,
sadece `gui_v2 import`'unu test eden minik bir `console=True` teşhis
exe'si (`diag.spec` + `diag_entry.py`) yazıldı — saniyeler içinde tam
`traceback` görüldü, ekran görüntüsüne hiç gerek kalmadı.

**Çözüm:** `build.spec`'in `hiddenimports` listesine `tkinter.scrolledtext`,
`tkinter.messagebox`, `tkinter.filedialog` eklendi.

**Sonuç:** Aynı teşhis exe'siyle hem `gui_v2` hem `ram_gui` importunun
artık temiz geçtiği doğrulandı ("IMPORT OK"). Gerçek `Chameleon.exe`
yeniden derlendi.

---

## "Vaka Bilgileri" ve "Doğrudan/Port Yönlendirme" bilgi sayfaları kart sisteminin dışında kalmıştı

**Belirti:** Launcher'daki bağımsız "Vaka Bilgileri" adım sayfası, 3 giriş
alanını kart/panel olmadan doğrudan koyu arka plan üzerine seriyordu —
tamamlanmamış görünüyordu. Aynı şekilde yöntem tanıtım sayfalarındaki
("Ne zaman kullanılır?", "Gerekenler", "Adım adım kullanım") metin
blokları da kartsız, düz metin olarak duruyordu — diğer ekranlardaki
(SSH motoru, RAM motoru) tutarlı kart görünümüyle çelişiyordu.

**Kök neden:** Bu iki sayfa, launcher'ın customtkinter→PySide6 geçişi
sırasında (`gui_v2.py`/`ram_gui.py`'nin aksine) bileşen kütüphanesindeki
`widgets.Card`'ı hiç kullanmadan, elle QLabel/QWidget dizilimiyle
yazılmıştı — geçiş sırasında gözden kaçmış, işlevsel olarak çalıştığı
için fark edilmemişti.

**Çözüm:** "Vaka Bilgileri" sayfasındaki 3 alan + "Devam Et" butonu tek
bir `widgets.Card()` içine alındı (max 640px genişlik, sayfanın üst
kısmına sola yaslı). Yöntem tanıtım sayfasındaki üç bölüm de artık ayrı
birer `widgets.Card(başlık)` — bu sayede mavi/uppercase başlık stili de
otomatik geldi (Card'ın kendi başlık mantığı). Numaralı listelerdeki
("Gerekenler", "Adım adım kullanım") rakamlar, yeni eklenen
`widgets.StepBadge` (mavi daire + beyaz rakam) ile değiştirildi.

**Sonuç:** Headless (`QT_QPA_PLATFORM=offscreen`) testle her iki sayfa
+ tüm yöntem sayfaları hem TR/EN hem koyu/açık temada hatasız gezildi;
`widget.grab()` ekran görüntüleriyle kart yapısının diğer sayfalarla
birebir aynı olduğu görsel olarak doğrulandı.

---

## Kart içine sarmalanan satırlar arka planında koyu bir kutu bırakıyordu

**Belirti:** Yukarıdaki düzeltme sırasında, numaralı adım satırlarını
(`StepBadge` + metin) karta eklerken ilk denemede her satırın arkasında
kartın kendi renginden (BG_SURFACE) daha koyu bir dikdörtgen görünüyordu.

**Kök neden:** Satırı `QHBoxLayout` içine koyup sonra bunu bir
`row_w = QWidget(); row_w.setLayout(row)` ile sarmalayıp `card.body.
addWidget(row_w)` yapmak, o ara `QWidget`'ın da global `QWidget {
background-color: BG_DARKEST }` kuralını miras almasına yol açtı — aynı
ailede daha önce QLabel'lar için çözülen soruna benzer (bkz.
[ogrenilenler.md](ogrenilenler.md)).

**Çözüm:** Ara `QWidget` kaldırıldı, `card.body.addLayout(row)` ile
layout doğrudan karta eklendi (`_home_card`'daki mevcut doğru desenle
aynı).

**Sonuç:** Ekran görüntüsüyle doğrulandı, kutu kayboldu.

---

## RAM motoru "Full" modda ShellExecuteW argüman kaçırma hatası (CWE-88)

**Belirti:** Güvenlik denetimi sırasında bulundu (kullanıcı istekli
security-auditor incelemesi). `ram_gui.py`'nin `_run_full_mode()`'u,
Yönetici (UAC) olarak yükseltilmiş `RamImagerCLI.exe` sürecine giden
parametreleri şöyle kuruyordu:

```python
params = " ".join(f'"{a}"' if " " in a else a for a in args[1:])
```

Bu, sadece BOŞLUK varsa tırnaklıyordu, içindeki `"` karakterini hiç
kaçırmıyordu.

**Kök neden:** `args` listesine `--case`/`--examiner` doğrudan serbest
metin "Vaka No"/"İnceleyen" alanlarından giriyordu
(`self.entry_case.text()`, hiç sanitize edilmeden). Bir operatör bu
alana `"` karakteri içeren bir metin yazarsa, `"foo" & calc.exe ""` gibi
bir string üretilip **elevated (UAC onaylı)** sürece giden argüman
sınırı bozulabiliyordu — ekstra/değiştirilmiş argümanlar kapalı kutu
`RamImagerCLI.exe`'ye geçebilirdi. Process modu bu riski taşımıyordu
(düz `subprocess.Popen` liste formu, `ShellExecuteW` kullanmıyor).

**Çözüm:** `subprocess.list2cmdline(args[1:])` ile değiştirildi — Python
stdlib'in kendi, Windows argv kaçırma kuralını (tırnak/backslash) doğru
uygulayan fonksiyonu; kendi kaçırma mantığını yazmaktan daha güvenli.

**Sonuç:** Normal girdilerde (boşluk içeren ama tırnak içermeyen metin)
eski ve yeni kod BİREBİR AYNI çıktıyı üretiyor (test edilip doğrulandı)
— davranış değişikliği yok. `"` içeren girdilerde eskiden argüman sınırı
bozuluyordu, artık `"foo\" & calc.exe \""` gibi tek bir argüman olarak
kalıyor.

---

## Tor operatör özel anahtarı düz metin, dosya izni kısıtlanmamış (CWE-312)

**Belirti:** Güvenlik denetimi sırasında bulundu. `keys/
operator_tor_key.json` (operatörün Tor client-auth x25519 özel anahtarı
— bir vakaya kimin bağlanabileceğini belirleyen TEK yetkilendirme
mekanizması) düz metin JSON olarak yazılıyordu, dosya izni hiç
sıkılaştırılmıyordu.

**Kök neden:** `gui_v2.py`'deki `_load_or_create_operator_key()`, dosyayı
`open(key_path, "w")` ile yazdıktan sonra herhangi bir izin ayarlaması
yapmıyordu. `.gitignore`'da olduğu için commit'e girmiyordu (iyi), ama
diskte kalan dosya, aynı makineye erişimi olan başka bir yerel kullanıcı
tarafından okunabilirdi.

**Çözüm:** `_restrict_key_file_permissions(path)` eklendi — POSIX'te
`os.chmod(path, 0o600)`, Windows'ta ek olarak `icacls path /inheritance:r
/grant:r <kullanici>:F` (kalıtımlı izinleri kaldırıp sadece mevcut
kullanıcıya erişim veriyor). Anahtar üretildiği anda (`_load_or_create_
operator_key()` içinde, dosya yazıldıktan hemen sonra) çağrılıyor.

**Sonuç:** Gerçek bir test dosyasında uygulanıp `icacls` çıktısıyla
doğrulandı (`TOPRAKY\yasar:(F)` — sadece mevcut kullanıcı). Dosya normal
şekilde okunup yazılabiliyor, akış bozulmadı.

---

## "Bu ne demek?" linkiyle Bilgi Merkezi'ne gidince arac ekranindaki form/baglanti kayboluyordu

**Belirti:** SSH/RAM arac ekranında bir "Bu ne demek?" linkine tıklayıp
Bilgi Merkezi'ne gidildiğinde, geri dönmenin (sidebar'dan tekrar o
motoru açmanın) TEK yolu motoru baştan açmaktı — doldurulmuş tüm form
alanları (host, kullanıcı adı, vaka no vb.) ve varsa kurulmuş bir SSH
bağlantısı sıfırlanıyordu. Kullanıcı geri bildirdi: "bir yerde bilgi
al'a basıp bilgi merkezine gidince tekrar başa dönüp boşlukları tekrar
doldurmak gerekiyor."

**Kök neden:** `_show_help()`, her çağrıldığında `_clear_content()`'i
çağırıyordu — bu da o an ekranda duran sayfayı (`ForensicWidget`/
`RamEngineWidget` dahil) `deleteLater()` ile GERÇEKTEN siliyordu. Bu,
sidebar'dan doğrudan gezinme için doğru davranış (her sayfa bağımsız,
saklanacak bir şey yok), ama bir arac ekranındaki linkten gelindiğinde
yanlış — kullanıcının o ana kadarki tüm girdisini yok ediyordu.

**Çözüm:** `on_show_help` callback'i, arac ekranlarına özel yeni bir
giriş noktasına (`_show_help_from_tool`) bağlandı. Bu metod, Bilgi
Merkezi'ne geçmeden ÖNCE mevcut sayfayı `stack_layout`'tan SİLMEDEN
çıkarıp (`takeAt()`, `deleteLater()` çağrılmadan) `self._return_page`'de
canlı tutuyor. Bilgi Merkezi sayfasında bu durumda bir "← Kaldığınız
yere dön" butonu beliriyor (`_return_from_help`), tıklanınca AYNI widget
instance'ı (tüm doldurulmuş alanları ve varsa açık SSH bağlantısıyla
birlikte) `stack_layout`'a geri ekleniyor, sidebar'daki aktif seçim de
eski haline dönüyor. Eski widget'ları `deleteLater()` ile kaldırırken
`hide()`'ın da hemen (senkron) çağrılması gerekti — `deleteLater()` tek
başına bir sonraki event loop turunu beklediği için, headless testte
Bilgi Merkezi içeriğinin "geri dön"den sonra bir an ekranda kalmaya
devam ettiği (eski widget silinmeden yeni widget'ın altında/üstünde
görünmez ama hâlâ boyalı) yakalandı.

**Sonuç:** Hem SSH hem RAM motoru ekranında test edildi: forma değer
girilip "Bu ne demek?"e basıldı, Bilgi Merkezi'nde ilgili konuya
kaydırıldığı ve "Geri dön" butonunun göründüğü doğrulandı, geri
dönülünce AYNI widget instance'ının (Python nesne kimliğiyle
karşılaştırılarak) ve girilen tüm değerlerin korunduğu doğrulandı.
Ayrıca "Geri" kullanılmadan başka bir sidebar sayfasına geçilip
sonra tekrar bir arac ekranından Bilgi Merkezi'ne gidilmesi de (eski,
"unutulmuş" sayfanın sessizce temizlenip crash olmadığı) test edildi.

---

## Bilgi Merkezi'nde bazı konulara giden linkler sanki sayfanın başına atıyormuş gibi görünüyordu

**Belirti:** Yukarıdaki düzeltmeden hemen sonra kullanıcı bildirdi:
"Delil Zinciri Nedir?" gibi bazı linkler tıklanınca Bilgi Merkezi
açılıyordu ama sanki ilgili karta değil, sayfanın en başına gidiyormuş
gibi hissettiriyordu.

**Kök neden:** Kaydırma `scroll.ensureWidgetVisible(target, 0, 20)` ile
yapılıyordu. Bu fonksiyon, hedef widget viewport'ta KISMEN bile olsa
zaten görünüyorsa, sadece "tam görünür olması için gereken en az"
miktarda kaydırıyor — hedefi viewport'un ÜSTÜNE getirmeye çalışmıyor.
Ölçüldüğünde: "Delil Zinciri" kartı sayfanın 3. kartıydı ve kaydırılmamış
haldeyken viewport'un ALT kenarına zaten kısmen giriyordu (795-1052px
aralığında, viewport 0-900px) — bu yüzden `ensureWidgetVisible` neredeyse
hiç kaydırmadı (224/1136), kart viewport'un en altına sıkışmış kaldı ve
gözden kolayca kaçıyordu. Sayfanın başındaki kartlarda (host key gibi)
bu fark hiç belli olmuyordu çünkü zaten en az kaydırma gerekiyordu.

**Çözüm:** `ensureWidgetVisible` yerine kaydırma çubuğu doğrudan
`target.y() - 16` değerine ayarlanıyor (`_show_help`'teki
`_scroll_to_target()`) — bu, hedef kartın ÜSTÜNÜ viewport'un hemen
üstüne getiriyor, "buraya geldin" hissi net oluyor. Sayfanın sonuna
yakın kartlarda (altında yeterli boş içerik olmadığında) doğal olarak
scrollbar'ın maksimumunda kalıyor — bu beklenen/doğru davranış, herhangi
bir "anchor" linkte olduğu gibi.

**Sonuç:** 6 konunun tümü ölçülerek doğrulandı — ilk 4 konu kartı
viewport'un tam 16px üstüne yerleştiriyor, son 2 konu (sayfanın sonuna
yakın) scrollbar'ın izin verdiği maksimuma kadar kaydırıp kartı olabildiğince
öne getiriyor. Önceki "Geri dön" (form/bağlantı koruma) testleri de bu
değişiklikten etkilenmediği doğrulandı. `dist/Chameleon.exe` yeniden
derlendi.

---

## `tor_manager.py`'de `ADD_ONION` hiç çalışmıyordu (yanlış key_type/key_content)

**Belirti:** Hedef taraf sihirbazı (`_show_target_wizard`) ilk kez
gerçek gömülü Tor'a karşı test edilirken, "Bağlantıyı Başlat" her zaman
`"[-] Hidden service olusturulamadi: ADD_ONION response didn't have an
OK status: Failed to decode ED25519-V3 key"` hatasıyla başarısız oluyordu.

**Kök neden:** `engines/portable_kit/tor_manager.py`'deki
`start_hidden_service()`, `controller.create_ephemeral_hidden_service()`'i
`key_type="ED25519-V3"` ile çağırıyordu, `key_content` parametresi ise
belirtilmediği için varsayılanı (`"BEST"`) kullanıyordu. `stem`, bu
ikisini `"ADD_ONION %s:%s" % (key_type, key_content)` şeklinde birleştirip
Tor'a `ADD_ONION ED25519-V3:BEST` gönderiyor — Tor bunu "ED25519-V3
türünde, HAZIR bir anahtar, içeriği tam olarak 'BEST' metni" olarak
yorumlayıp bu metni anahtar verisi gibi decode etmeye çalışıp
reddediyordu. Doğrusu: `key_type` varsayılanında (`"NEW"` = "yeni bir
anahtar SEN üret") kalmalı, `key_content="ED25519-V3"` (üretilecek
anahtarın türü) verilmeliydi. Bu kod daha önce sadece mock'lanmış
Tor/stem ile test edilmişti (bkz. `docs/roadmap.md`'deki "gerçek Tor
ağı üzerinden canlı test henüz yapılmadı" notu) — mock, gerçek Tor'un
`ADD_ONION` parametre doğrulamasını hiç taklit etmediği için bu hata
hiç yakalanmamıştı.

**Çözüm:** `key_type="ED25519-V3"` satırı kaldırıldı, yerine
`key_content="ED25519-V3"` eklendi (`key_type` varsayılan `"NEW"`'da
bırakıldı).

**Sonuç:** Gerçek bir operatör anahtarıyla (`onion_auth.generate_keypair()`)
tekrar denendi — geçerli, gerçek bir `.onion` adresi üretildi
(`r5z5xf...onion`). "Bağlantıyı Kapat" butonunun Tor sürecini
gerçekten sonlandırdığı da `tasklist` ile ayrıca doğrulandı (orphan
process kalmıyor).

---

## Rapordaki "doğrulandı" alanı GUI akışında hiç doldurulmuyordu

**Belirti:** 4 uzman ajanla (Incident Responder/adli bilişim bakış açısı)
yapılan bir inceleme sırasında bulundu: operatör "İmaj Doğrula" ile
başarıyla doğrulama yapsa bile, `report.json`/`report.html`'deki
`verification.verified` alanı HER ZAMAN `false` kalıyordu.

**Kök neden:** `gui_v2.py`, işlem bitince `report.save()`'i HEMEN
çağırıyor, "Uzak diskin hash'ini biliyor musunuz?" sorusunu bundan
SONRA soruyordu. `ForensicReport.set_verification()` -- raporun
`verified`/`hash_match` alanlarını dolduran TEK yer -- sadece `main.py`
CLI'sinde, GUI'de hiç kullanılmayan bir yolda çağrılıyordu. Yani GUI'nin
ürettiği rapor, gerçek doğrulama sonucundan tamamen bağımsızdı.

**Çözüm:** `gui_v2.py`'ye `_last_report`/`_last_report_path` eklendi
(`_show_report_summary`'de doldurulur). `VerifyWorker` artık bunları
alıp doğrulama sonucunda `report.set_verification(matched)` çağırıp
`report.save()`'i TEKRAR çalıştırıyor. `set_verification()`, doğrulama
zamanı raporun `end_time_utc`'sinden sonraysa bu alanı genişletiyor --
aksi halde `HASH_VERIFIED` olayı, raporun kendi `read_events()` zaman
penceresi dışında kalıp olay listesine hiç girmezdi (rapor "verified:
true" derken, aynı rapordaki olay listesi bunu doğrulayan hiçbir kayıt
göstermezdi). `forensic_report.py`'nin `_append_to_history()`'si de
aynı `report_path` için ikinci `save()` çağrısında artık Vaka
Geçmişi'ne yeni bir satır EKLEMİYOR, mevcut satırı GÜNCELLİYOR (aksi
halde her doğrulama, aynı vakayı listede iki kez gösterirdi).

**Sonuç:** Gerçek bir dosya + gerçek SHA-256 hash ile uçtan uca test
edildi: doğrulama öncesi `verified: false`, doğrulama sonrası
`verified: true, hash_match: true`, `HASH_VERIFIED` olayı raporun kendi
olay listesinde, Vaka Geçmişi'nde tek (duplike olmayan) satır.

---

## Delil zinciri log'u, hedef cihazdaki dosya adlarıyla manipüle edilebiliyordu

**Belirti:** Aynı inceleme turunda (Penetration Tester ajanı) bulundu.
`chain_of_custody.py` log satırlarını `|` ile ayırıyor
(`f"[{ts}] | {event_type} | {description} | {hash_part}"`,
`read_events()` tam 4 parça bekliyor). `description` çoğu zaman HEDEF
cihazdaki dosya/klasör adlarından geliyor (`file_acquirer.py`:
`f"Dosya alindi ve dogrulandi: {uzak_dosya}"` gibi) -- yani incelenen
tarafın (şüpheli/cihaz sahibi) kontrolünde olabilecek veri.

**Kök neden:** Dosya adı sanitize edilmeden doğrudan log satırına
gömülüyordu. İki somut saldırı senaryosu:
- **Delil kaybı**: dosya adında `|` varsa, satır 5 parçaya bölünüyor,
  `len(parts) != 4` kontrolü kaydı SESSİZCE düşürüyor -- o dosyanın
  alındığına dair kayıt raporda hiç görünmüyor.
- **Sahte kayıt enjeksiyonu**: dosya adında satır sonu + elle kurgulanmış
  `[ts] | EVENT | .. | hash` deseni varsa, `read_events()` bunu
  BAĞIMSIZ, meşru bir log satırı olarak parse edip rapora gömüyor.

**Çözüm:** Yeni `_sanitize_log_field()`, yazmadan önce `description`
(ve `hash_value`) içindeki `|`'ı görsel olarak benzer ama farklı bir
sembolle (`¦`, kırık dikey çizgi), satır sonlarını (`\n`/`\r`) boşlukla
değiştiriyor -- dosya adı okunaklılığı bozulmadan, parçalama artık
kırılmıyor.

**Sonuç:** Her iki senaryo da (adında `|` olan dosya, adında sahte log
satırı denemesi olan dosya) ayrı ayrı test edildi -- ikisinde de artık
2 satır yazılıyor, 2 olay okunuyor, hiçbir kayıt düşmüyor/sahte kayıt
oluşmuyor.

---

## Rol seçim ekranında iki kart da aynı generic buton metnini taşıyordu

**Belirti:** Kullanıcı, açılıştaki rol seçim ekranında ("Operatörüm" /
"Bu Cihaz İnceleniyor") her iki kartın altındaki butonun da aynı,
ayrım yapmayan "Bunu Seç" yazısını taşımasını bildirdi.

**Kök neden:** `chameleon_gui.py`'de iki `PrimaryButton` da aynı sabit
metinle oluşturulmuştu, kartın kendi kimliğine göre özelleştirilmemişti.

**Çözüm:** Operatör kartının butonu "Operatör Olarak Devam Et", hedef
cihaz kartının butonu "Bu Cihazla Devam Et" oldu — her ikisi de kendi
kartının ne yaptığını buton metninde de yansıtıyor.

**Sonuç:** Saf metin değişikliği, davranışta fark yok; headless
ekran görüntüsüyle iki butonun da taşmadan doğru göründüğü doğrulandı.

---

## Rapordaki TOOL_VERSION, gerçek uygulama sürümünden bağımsız, sabit "1.0" yazıyordu

**Belirti:** `report.json`'un `tool.version` alanı her zaman `"1.0"`
gösteriyordu — uygulamanın gerçek sürümü (`shared/version.py` ->
`VERSION = "0.1.0"`) çoktan değişmiş olsa bile.

**Kök neden:** `forensic_report.py`'de `TOOL_VERSION = "1.0"` ayrı,
sabit bir string olarak tanımlanmıştı; `shared/version.py`'deki tek,
ortak sürüm numarasından hiç okunmuyordu.

**Çözüm:** `TOOL_VERSION`, `from version import VERSION as TOOL_VERSION`
ile `shared/version.py`'den okunacak şekilde değiştirildi. Artık tek bir
yerden (`version.py`) yönetilen sürüm, launcher/splash ekranıyla rapor
arasında tutarlı.

**Sonuç:** `forensic_report.ForensicReport().to_dict()["tool"]["version"]`
`"0.1.0"` döndüğü doğrulandı.

---

## "Vaka Geçmişi" sidebar sayfası — doküman "yapıldı" diyor, kodda yok

**Belirti:** Vaka Geçmişi listesine bir CSV dışa aktarma butonu eklenmek
istenirken, `launcher/chameleon_gui.py`'de "Vaka Geçmişi" diye bir
sidebar sekmesi/sayfası ARANDI ve BULUNAMADI (`grep -i history/gecmi`
sıfır sonuç verdi; sidebar `nav_items` listesi sadece Ana Sayfa /
Doğrudan / VPN / Tor / RAM / Bilgi Merkezi / Ayarlar içeriyor).

**Kök neden (kesin değil, en olası açıklama):** `docs/roadmap.md`'de bu
sayfa "Yapıldı" olarak, ekran görüntüsüyle doğrulanmış şekilde
kayıtlıydı — yani BİR ZAMANLAR gerçekten vardı. Muhtemel açıklama: daha
sonraki bir "Yapıldı" maddesi olan **`customtkinter` → PySide6 tam
geçişi**, launcher'ın tüm kabuğunu (sidebar dahil) sıfırdan yeniden
kurdu; bu geçiş sırasında Vaka Geçmişi sayfası yeniden inşa edilmeyi
unutulmuş olmalı. Backend (`forensic_report.py`'deki
`shared/data/case_history.json` + `read_history()`) hiç bozulmadı, her
rapor kaydında hâlâ güncelleniyor — sadece onu gösteren UI kayboldu.

**Çözüm:** Şimdilik düzeltilmedi — kapsam dışı, büyük bir sayfa yeniden
inşası gerektiriyor (bkz. `docs/roadmap.md` "Sırada" madde 1). Bunun
yerine roadmap.md'deki yanlış "Yapıldı" iddiası düzeltildi ve doğru not
eklendi.

**Ders:** Bir "Yapıldı" maddesinin ekran görüntüsüyle doğrulanmış olması,
SONRAKİ bir büyük refactor'dan (özellikle "kabuğu sıfırdan kur" türünden)
sağ çıktığının garantisi değil — böyle bir refactor sonrası eski
"Yapıldı" listesinin kritik UI sayfaları için hızlı bir gözden geçirmesi
faydalı olurdu.

---

## `_clear_content()` içinde `deleteLater()` asenkronluğu, hızlı ardışık sayfa geçişlerinde eski widget'ları "canlı" bırakıyordu

**Belirti:** Yeni eklenen "Vaka Geçmişi" sayfası headless testte iki kez
art arda çağrılınca (`_show_case_history()` → `_show_case_history()`),
`findChildren()` önceki çağrının "CSV Olarak Dışa Aktar" butonunu da
döndürdü -- sanki iki buton varmış gibi. Gerçek kullanımda (bir kullanıcı
sidebar'da tek tek tıkladığında) fark edilmez çünkü tıklamalar arasında
Qt olay döngüsünün nefes alacak zamanı olur, ama teorik olarak HER
sayfa geçişinde (`_clear_content()` sadece bu sayfaya özel değil, TÜM
launcher sayfaları bunu kullanıyor) aynı sınıf bir yarış durumu var.

**Kök neden:** `_clear_content()`, eski sayfanın widget'ını
`deleteLater()` ile siliyordu. `deleteLater()` ASENKRON'dur -- widget,
bir sonraki olay döngüsü turuna kadar hâlâ geçerli, sorgulanabilir bir
QObject olarak kalır. Bu, projede DAHA ÖNCE Bilgi Merkezi'nde bulunan
AYNI hata sınıfı (bkz. yukarıdaki "Bilgi Merkezi kaydırma düzeltmesi..."
maddesindeki not) — ama o zamanki düzeltme sadece o tek ekrana
uygulanmıştı, kaynak fonksiyon (`_clear_content()`) düzeltilmemişti.

**Çözüm:** `_clear_content()`'e `w.hide()` eklendi, `w.deleteLater()`'dan
hemen önce -- artık widget mantıksal olarak da (`isVisible()` üzerinden)
anında "yok" sayılıyor, silinme gerçekleşene kadarki aralıkta hiçbir yan
etki kalmıyor. Bu, TÜM launcher sayfa geçişlerini kapsayan genel bir
düzeltme (sadece Vaka Geçmişi'ni değil).

**Sonuç:** Aynı sayfa art arda (event loop'a hiç dönmeden) defalarca
çağrılıp `isVisible()` filtresiyle widget sayımı yapıldı, artık her
zaman doğru (tek) sonuç veriyor.

---

## `Chameleon.exe` derlenmiş modda beş farklı yazılabilir yolu geçici `_MEIPASS` klasörüne yazıyordu

**Belirti:** Roadmap'te "portable yapma" görevi sadece `chain_of_custody.
LOG_DIR` ve `forensic_report.HISTORY_DIR`'ı adlandırıyordu; bunları
düzeltirken aynı `__file__`-bağımlı desenin ayrıca `image_acquirer.
IMAGE_DIR`/`MANIFEST_DIR`, `ssh_connector.CHAMELEON_KNOWN_HOSTS` (TOFU
öğrenilen sunucu kimlikleri) ve `gui_v2.py`'deki operatör Tor anahtarı
yolu + varsayılan çıktı yolları + son bağlantılar dosyasında da AYNEN
tekrarlandığı bulundu.

**Kök neden:** Hepsi `os.path.dirname(os.path.abspath(__file__))` (ya da
ondan türetilen bir yol) kullanıyordu. Kaynaktan çalışırken bu doğru
sonucu verir, ama derlenmiş `.exe`'de PyInstaller'ın veri-dosyası olarak
paketlediği modüllerin (bu proje `sys.path.insert()+import` deseniyle
çalıştığı için `gui_v2.py`/`chain_of_custody.py` gibi dosyalar birer
veri dosyası olarak paketleniyor) `__file__`'ı, her çalıştırmada silinen
GEÇİCİ `_MEIPASS` klasörünü gösterir -- salt-okunur, PAKETLENMİŞ
kaynaklar (ikonlar, fontlar, gömülü `tor.exe`) için bu DOĞRU davranış,
ama YAZILABİLİR/kalıcı olması gereken veriler için yanlış.

**Çözüm:** Her dosyada `getattr(sys, "frozen", False)` kontrolü eklendi;
derlenmiş modda `sys.executable`'ın (exe'nin kendi, KALICI konumu)
dizini kullanılıyor, kaynaktan çalışırken eski `__file__`-bağımlı
hesaplama hiç değişmeden korunuyor. Salt-okunur paketlenmiş kaynakların
(`shared/ui_kit`, `shared/tor_binary.py`, `RamImagerCLI.exe` vb.)
yolları BİLİNÇLİ olarak dokunulmadı -- onlar zaten `_MEIPASS`'ta olması
gereken yerdeler.

**Sonuç:** `sys.frozen`/`sys.executable` sahte bir `.exe` yoluna
ayarlanarak (gerçek bir derleme yapmadan) her 4 modül + `gui_v2.py`
yeniden import edildi, tüm yolların beklenen kalıcı konuma (`sys.
executable`'ın dizini + `logs`/`images`/`keys`/`data`) çözüldüğü
doğrulandı; kaynaktan çalışırken (`sys.frozen` yok) hiçbir yolun
DEĞİŞMEDİĞİ ayrıca regresyonla teyit edildi. Detaylar
[roadmap.md](roadmap.md)'de.

---

## Operasyonel notlar (hata değil, tekrar karşılaşılabilecek sürtünmeler)

- **Git Bash'te `tar` ile Windows sürücü harfi (`C:\...`) sorunu**: `tar`,
  `C:` içeren yolu "uzak host:dosya" olarak yorumlayıp
  `Cannot connect to C: resolve failed` hatası veriyordu. Çözüm: POSIX
  stilinde `/c/Users/...` yolu kullanmak ya da `--force-local` bayrağı.
- **PyInstaller derlemesi `PermissionError: [WinError 5]` ile
  patlıyordu**: `dist/Chameleon.exe` hâlâ çalışan bir örnek tarafından
  kilitliyken yeniden derlemeye çalışmak bu hatayı veriyor. Çözüm:
  derlemeden önce `Get-Process | Where-Object ProcessName -like
  "*Chameleon*" | Stop-Process -Force`.
- **WSL'de test için açılan `sshd`, socket-activation yüzünden ilk
  bağlantıda "Unable to connect" veriyordu**: `service ssh start`
  Ubuntu'da varsayılan olarak `ssh.socket`'i (systemd socket
  activation) tetikliyor — port dinlemede görünse de, gerçek `sshd`
  süreci ilk TCP bağlantısı gelene kadar başlamıyor, bu da paramiko'nun
  ilk denemesinin "Unable to connect to port 22" ile başarısız olmasına
  yol açıyordu (ikinci deneme genelde başarılı oluyordu, kararsız bir
  test deneyimi). Çözüm: `systemctl disable/stop ssh.socket` ile
  socket-activation'ı kapatıp `service ssh start` ile `sshd`'yi
  doğrudan/kalıcı çalıştırmak.
