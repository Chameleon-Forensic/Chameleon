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
