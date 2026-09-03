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
