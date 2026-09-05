# Öğrenilenler

Bu proje boyunca ortaya çıkan, ileride tekrar karşılaşabileceğimiz teknik
dersler. Belirli bir hatanın adım adım çözümü için
[hatalar_ve_sonuclar.md](hatalar_ve_sonuclar.md)'a bakın — burası daha çok
"neden böyle davranıyor, bir dahaki sefere nasıl yaklaşmalı" notları.

## PyInstaller + çalışma-anında-yüklenen modüller

`gui_v2.py`/`ram_gui.py` gibi dosyalar derleme zamanında `import` edilmiyor,
`chameleon_gui.py` onları `sys.path.insert()` ile çalışma anında ekleyip
sıradan `import X` yapıyor. PyInstaller'ın statik analizi SADECE
`Analysis()`'e verilen giriş dosyasını (ve onun düz `import` ettiklerini)
tarar — bu yüzden çalışma-anında-yüklenen dosyaların üçüncü parti/`tkinter`
alt modül ihtiyaçlarını **asla otomatik keşfedemez**. Böyle bir dosyada yeni
bir `import` eklerken (özellikle `tkinter.X`, ki bunlar genelde unutuluyor)
`build.spec`'in `hiddenimports` listesine elle eklemek gerekiyor. Aksi
halde exe derlenir, çalışır, ama tam o modül yüklenmeye çalışıldığı anda
`ModuleNotFoundError`/`ImportError` ile patlar — derleme sırasında hiçbir
uyarı vermez.

**Pratik yöntem**: `grep -rhoE "from tkinter import [a-zA-Z_., ]+" <dinamik yuklenen dizinler>` ile tüm tkinter alt-modül kullanımlarını tara, hepsini hiddenimports'a ekle. Kuşkulu bir üçüncü parti importta da aynısını yap.

**Daha hızlı doğrulama yöntemi**: Tüm 28MB'lık exe'yi her seferinde
yeniden derlemek yerine, sadece SORUNLU importu test eden minik, ayrı bir
`diag.spec` + `diag_entry.py` (console=True) ile saniyeler içinde
doğrulamak çok daha hızlı bir geri bildirim döngüsü sağlıyor.

## customtkinter kendi varsayılan pencere ikonunu 200ms sonra basıyor

`CTk()`/`CTkToplevel()` kurucusu, kullanıcı KENDİ `iconbitmap()` metodunu
(CTk'nin override ettiği, `_iconbitmap_method_called` bayrağını işaretleyen
versiyon) hiç çağırmadıysa, `self.after(200, self._windows_set_titlebar_icon)`
ile 200ms sonra kendi varsayılan customtkinter logosunu (mavi "C" ikonu)
sessizce baslığa basıyor. `tkinter`'ın standart `iconphoto()` fonksiyonu bu
izlemeyi TETİKLEMİYOR — yani `iconphoto()` ile ikon ayarlasanız bile 200ms
sonra CTk onun üstüne kendi ikonunu yazıyor, hiçbir hata/uyarı vermeden.

**Çözüm**: `iconphoto()` değil, `self.root.iconbitmap(path.ico)` (CTk'nin
kendi izlediği metot) çağırmak. Zamanlamayla (daha geç bir `.after()` ile
yeniden uygulamak) çözmeye çalışmak İŞE YARAMAZ çünkü CTk'nin kendi
override'ı da bir `.after()` — hangisinin önce/sonra çalışacağı garanti
değil ve yarış (race) koşuluna girer. Bayrak tabanlı çözüm (doğru metodu
çağırmak) zamanlamadan bağımsız, kalıcı bir çözüm.

## Tor v3 Hidden Service client authorization

Client authorization (kimin bağlanabileceği kısıtlaması), Hidden Service'in
kendi kimlik anahtarından (Ed25519, imzalama) TAMAMEN AYRI bir mekanizma:
x25519 (Diffie-Hellman) anahtar çifti kullanıyor. Bu önemli çünkü x25519
anahtarları HAM 32 baytlık skaler değerler — Ed25519'daki gibi SHA-512
genişletmesi/"expanded key" formatı gerektirmiyor. `cryptography`
kütüphanesinin `X25519PrivateKey`'i doğrudan kullanılabiliyor, format
karmaşası yok. Tor, bu anahtarları base32 (RFC 4648, dolgusuz, küçük harf)
bekliyor.

`stem` kütüphanesi (v1.8.2), `ADD_ONION`'ın `client_auth_v3` parametresini
`create_ephemeral_hidden_service()` üzerinden destekliyor ama
`ONION_CLIENT_AUTH_ADD` (istemci tarafında anahtar tanıtma) için hazır bir
sarmalayıcı YOK — bu komut Tor 0.4.6 ile geldi, stem'in son sürümünden
sonra. Çözüm: `Controller.msg()` ile ham control-protokol komutu göndermek.

## SOCKS5 ile `.onion` adresine bağlanırken ATYP=DOMAINNAME şart

`.onion` adresleri normal DNS ile ASLA çözülemez — sadece Tor'un kendisi
çözebilir. SOCKS5 CONNECT isteğinde hedef adresi ATYP=0x01 (IPv4) değil,
ATYP=0x03 (DOMAINNAME) ile, adresi OLDUĞU GİBİ (yerel olarak çözmeye
çalışmadan) göndermek gerekiyor. Yerel `socket.getaddrinfo()` gibi bir şeye
önce uğratmak sessizce başarısız olur ya da yanlış sonuç verir.

## "Kısa bağlantı kodu" bir rendezvous sunucusu olmadan mümkün değil

56 karakterlik (280 bit) bir `.onion` adresini gerçekten 6-8 haneye
indirmek, bir arama/eşleştirme sunucusu (rendezvous) olmadan bilgi
kuramsal olarak imkansız — orta kısmı "bir yerden" geri getirmenin tek
yolu onu bir yerde saklamış olmak, ki bu tam kaçınmak istediğimiz sunucu
bağımlılığını geri getiriyor. Kısaltma istekleri geldiğinde önce bunu
netleştirmek gerekiyor: gerçek kısaltma mı isteniyor (imkansız), yoksa
görsel/insan-dostu bir SUNUM biçimi mi (QR kod, gruplu metin — bunlar
mümkün, veri tam olarak taşınıyor sadece daha kolay aktarılıyor).

## VPN, taşıma katmanında Doğrudan bağlantıyla birebir aynı

VPN "bağlantı yöntemi" olarak ayrı bir seçenek gibi görünse de, SSH
bağlantısı kurulduğu anda kod açısından hiçbir farkı yok — VPN sadece
hedefin IP'sini operatörün ağından erişilebilir hale getiriyor, SSH yine
doğrudan kuruluyor (Tor'daki gibi bir SOCKS/proxy katmanı YOK). Bu yüzden
VPN desteği eklemek yeni bağlantı kodu gerektirmedi, sadece delil
zincirinde hangi ağ yolunun kullanıldığının ayrıca işaretlenmesi
(loglama/rapor alanı) yeterliydi.

## Qt'de kart içine satır sarmalarken bare `QWidget()` kullanma

Bir kartın (`Card`, arka planı `BG_SURFACE`) içine birden fazla widget'ı
tek satırda gruplamak için `row = QHBoxLayout(); row_w = QWidget();
row_w.setLayout(row); card.body.addWidget(row_w)` deseni YANLIŞ —
`base_stylesheet()`'teki genel `QWidget { background-color: BG_DARKEST }`
kuralı bu ara `QWidget`'a da uygulanıyor, kartın kendi rengiyle
(`BG_SURFACE`) çelişip görünür bir koyu kutu bırakıyor (aynı ailede,
daha önce QLabel'lar için keşfedilen sorunla — bkz. `theme_qt.py`'deki
`QLabel{background:transparent}` notu). **Doğru yöntem**: ara `QWidget`
hiç yaratmadan `card.body.addLayout(row)` — `QVBoxLayout.addLayout()` bir
layout'u doğrudan başka bir layout'a ekleyebiliyor, gereksiz widget'a
gerek yok. Bir sayfa/kart dışına (genel koyu arka plan üzerine) satır
eklerken bu sorun görünmüyor çünkü iki rengin ikisi de `BG_DARKEST` —
sadece BG_SURFACE'lı bir kartın İÇİNDE fark ediliyor, bu da hatayı ilk
bakışta atlamayı kolaylaştırıyor.

## Qt Style Sheets'te `rgba()` alfa değeri 0-255, CSS'teki 0-1 değil

Durum rozeti (StatusBadge) gibi "soluk renkli arka plan" (tint) gereken
bir pill/badge tasarlarken `rgba(r, g, b, a)` yazarken CSS alışkanlığıyla
`a`'yı 0-1 arasında ondalık yazmak (örn. `rgba(34,197,94,0.15)`) Qt'de
SESSİZCE YANLIŞ yorumlanıyor (Qt Style Sheets belgelemesi: alfa da 0-255
tam sayı). Doğrusu `rgba(34,197,94,38)` gibi (38 ≈ 255'in %15'i).

## Taşınabilir kit: operatör anahtarı SAHA ZİYARETİNDEN ÖNCE hazır olmalı

Tor Hidden Service'in client-auth mekanizması, HANGİ operatör
anahtarının kabul edileceğini hizmet OLUŞTURULURKEN bilmek zorunda. Yani
operatörün x25519 anahtar çiftini saha ziyaretinden SONRA üretmesi işe
yaramaz — kit'in kendisi (ya da onu hazırlayan kişi) o anahtarın AÇIK
kısmını önceden bilmeli. Bu, launcher akışında "Tor" seçilince anahtarın
otomatik üretilip gösterilmesinin ve kullanıcıya "bunu SAHA ZİYARETİNDEN
ÖNCE iletin" diye açıkça hatırlatılmasının sebebi.

## paramiko'nun host-key doğrulama katmanları: hangisi neyi kontrol ediyor

`SSHClient`'ta host-key kontrolü üç ayrı katmandan geçiyor ve bunları
karıştırmak kolay:

1. `load_system_host_keys()` → OS'un kendi genel dosyasını (`/etc/ssh/
   ssh_known_hosts`) `_system_host_keys`'e yükler.
2. `load_host_keys(path)` → BELİRLİ bir dosyayı `_host_keys`'e yükler
   VE `_host_keys_filename`'i o path'e ayarlar (sonradan otomatik
   kaydetme buraya bağlı). **Dosya yoksa `IOError` fırlatır** — önce
   dosyanın var olduğundan emin olunmalı (gerekirse boş dosya
   oluşturup sonra yüklemek).
3. `set_missing_host_key_policy(policy)` → sunucunun anahtarı YUKARIDAKİ
   İKİ KAYNAKTA DA yoksa (`missing_host_key()` SADECE bu durumda
   çağrılır) ne yapılacağını belirler: `RejectPolicy` (reddet),
   `WarningPolicy` (uyarıp kabul et, HİÇBİR ŞEY KAYDETMEZ — bir dahaki
   bağlantıda yine "bilinmiyor" muamelesi görür), `AutoAddPolicy`
   (kabul et VE `_host_keys_filename` ayarlıysa diske kaydet — TOFU
   için bu kullanılmalı, `WarningPolicy` değil).

**En önemli kısım**: sunucunun anahtarı yukarıdaki kaynaklarda ZATEN
VARSA ama gelen anahtar UYUŞMUYORSA, policy'nin hiçbir etkisi yok —
paramiko doğrudan `BadHostKeyException` fırlatıyor. Yani bir kez
"TOFU" ile bir host öğrenildikten sonra, o host'un kimliği değişirse
(gerçek bir MITM ya da sunucu yeniden kurulumu), `AutoAddPolicy`/
`WarningPolicy` fark etmeksizin bağlantı KESİN olarak reddediliyor —
bu davranış "atla" gibi gevşek bir moddan bile bağımsız, üstüne
yazılamıyor. (Bkz. `ssh_connector.py`'deki `_TofuPolicy` + host key
TOFU eklenmesi, `docs/roadmap.md`.)

## stem'in `create_ephemeral_hidden_service()`'inde `key_type` ile `key_content` farklı şeyler

`key_type`: "ADD_ONION"'a hangi TÜRDE bir anahtar geldiğini söylüyor —
`"NEW"` = "bana yeni bir anahtar üret", `"ED25519-V3"`/`"RSA1024"` =
"sana HAZIR bir anahtar veriyorum, bu türde". `key_content`: `key_type`
`"NEW"` ise ÜRETİLECEK anahtarın türünü (`"BEST"`/`"ED25519-V3"`),
`key_type` hazır bir anahtarsa o anahtarın KENDİSİNİ (base64) taşıyor.
stem bu ikisini olduğu gibi `"ADD_ONION %s:%s"`'e yapıştırıyor — hiçbir
doğrulama yapmıyor. Yani `key_type="ED25519-V3"` yazıp `key_content`'i
varsayılanında (`"BEST"`) bırakmak, Tor'a "BEST" kelimesini GERÇEK bir
anahtar sanıp decode etmesini söylüyor ve sessizce/anlaşılmaz bir
hatayla reddediliyor. Yeni bir anahtar türü belirlemek istendiğinde
DOKUNULMASI gereken parametre `key_content`, `key_type` değil (bkz.
[hatalar_ve_sonuclar.md](hatalar_ve_sonuclar.md)'daki tam vaka).

## Qt QListWidgetItem'da emoji yerine SVG ikon kullan

`RemoteBrowseDialog` ilk yazıldığında klasör/dosya ögeleri "📁"/"📄"
emoji karakterleriyle işaretlenmişti — headless (`QT_QPA_PLATFORM=
offscreen`) test ortamında bunlar kutu (☐) olarak render oldu, çünkü
Inter gibi bir metin fontu emoji glif içermiyor ve headless ortamda
sistemin renkli emoji fontuna (Segoe UI Emoji vb.) düşme garantisi yok.
Gerçek Windows masaüstünde muhtemelen çalışırdı ama platform/ortama
bağımlı bir varsayım oluyordu. **Çözüm**: `icons.icon("folder"/
"file-text", ...)` ile app'in kendi Lucide SVG setinden `QIcon` üretip
`QListWidgetItem(icon, text)` ile vermek — hem headless'ta güvenilir
render oluyor hem de geri kalan arayüzle (aynı ikon seti, aynı stil)
tutarlı kalıyor. Genel kural: bu projede metin içine emoji gömmek yerine
her zaman `shared/ui_kit/icons.py` kullanılmalı.

## Boşluk içerebilecek alanlarda `lsblk`/benzeri araçların duz kolon ciktisina guvenme

Disk model/seri no'yu rapora eklemek icin `lsblk -o MODEL,SERIAL` gibi
duz, bosluk-ayrilmis kolon ciktisi kullanmak cazip görünüyor, ama MODEL
alani genelde bosluk icerir (orn. "Samsung SSD 860 EVO", "Virtual
Disk") -- bu da kolonlarin kacmasina/yanlis parcalanmaya yol acar.
Coz: `lsblk -P` (key="value" cifti, satir basina bir cihaz) formatini
kullanip regex ile (`MODEL="([^"]*)"`) cekmek -- deger ne kadar bosluk
icerirse icersin tirnak isaretleri sinirlari kesin belirliyor. Ayni
sinif sorun `Get-Disk`'in duz metin ciktisinda da var; orada
`ConvertTo-Json` ile ayni cozum uygulanabilir. Genel kural: bir komut
ciktisindan, degeri bosluk icerebilecek bir alani parse edecekseniz,
o aracin sagladigi yapisal/key-value formatini (varsa) tercih edin,
duz kolon hizalamasina guvenmeyin.

## Qt'de deleteLater() kullanan HER fonksiyona hide() de ekle, sadece belirtiyi gorulen ekrana degil

Bu projede AYNI hata iki kez, iki farkli yerde bulundu: once Bilgi
Merkezi'nde (eski sayfa "Geri" sonrasi bir an gorunur kaliyordu), sonra
Vaka Gecmisi sayfasi eklenirken tekrar (`_clear_content()`'te). Ikisinin
de kok nedeni AYNIYDI (`deleteLater()`'in asenkron olmasi -- widget bir
sonraki olay dongusune kadar hala "var" sayilir), ama ilk duzeltme
SADECE o zamanki belirtiyi gosteren tek ekrana uygulanmisti, ortak
kaynak fonksiyon (`_clear_content()`, TUM launcher sayfa gecislerinin
kullandigi) duzeltilmemisti. Genel kural: `X.deleteLater()` yazan HER
yere, hemen once `X.hide()` de eklenmeli -- bu, belirti nerede
gorulurse gorulsun, PAYLASILAN silme fonksiyonunun kendisinde
yapilmali, tek tek cagiran yerlerde degil. Aksi halde ayni sinif hata,
farkli bir ekranda yeniden "kesfedilir".
