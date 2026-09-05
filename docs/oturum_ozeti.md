# Bu oturumda yapılanlar — özet

## 1. Blok (chunk) boyutu ayarlanabilir hale getirildi
SSH motorunda disk imajı alırken kullanılan parça boyutu artık 4/16/32/64 MB
arasından seçilebiliyor (önceden sabit 4 MB'ydi). Yarım kalan bir işlemden
devam ederken karışıklık olmasın diye, o durumda seçim değil eski kayıttaki
boyut kullanılıyor.

## 2. Taşınabilir toplama kiti — bağlantı yöntemleri netleşti
Üç yöntem var:
- **Doğrudan / Port Yönlendirme** — operatörün hedef ağın router'ına erişimi
  olduğu, çoğu vakayı kapsayan basit yol. Ek kod gerekmedi.
- **VPN** — operatör zaten hedef ağa VPN ile bağlıysa; kod tarafında
  Doğrudan ile birebir aynı, sadece delil zincirinde ayrıca işaretleniyor.
- **Tor Hidden Service** — hiçbir ağ erişimi/yetkisi olmayan en zor durumlar
  için "acil kapı". Eski plan (kendi sunucumuzu barındırmak) tamamen terk
  edildi, yerine ücretsiz Tor ağı kullanıldı.

## 3. Tor entegrasyonu uçtan uca kuruldu
- Hedef cihaz tarafı: gömülü Tor'u başlatıp SSH'ı `.onion` adresi olarak
  yayımlıyor, sadece operatörün anahtarına sahip bağlantıları kabul ediyor.
- Operatör tarafı: kendi Tor sürecini başlatıp `.onion` adresine bağlanıyor.
- Operatörün anahtarı otomatik üretilip yerel olarak saklanıyor, arayüzden
  "Kopyala" ile taşınabilir kiti hazırlayan kişiye verilebiliyor.
- Bağlantının Tor üzerinden mi kurulduğu delil zinciri (chain-of-custody)
  logunda ayrıca işaretleniyor.
- Gerçek Tor programı (resmi Tor Project dağıtımı) indirilip projeye
  eklendi; bu makinede çalıştığı ve ürettiğimiz ayarların geçerli olduğu
  doğrulandı. **Gerçek ağ üzerinden iki cihaz arası canlı test henüz
  yapılmadı** — bu, sizinle birlikte yapılacak son adım.
- Şu an sadece Windows hedef için hazır.

## 4. Arayüzdeki eski metin düzeltildi
Ana ekrandaki "SSH ile uzak imaj al" kartının açıklaması hâlâ "sadece Linux"
diyordu — Windows desteği eklendiğinden beri güncellenmemiş kalmıştı.
Artık "Linux veya Windows hedefe SSH ile bağlanıp disk/dosya imajı alır"
yazıyor (TR ve EN).

## 5. Açılış (splash) ekranı eklendi
Oxygen Forensic Detective'in açılış ekranına benzer şekilde: uygulama
başlarken kısa süre bukalemun logosu + isim + sürüm + telif satırı
gösteriliyor, sonra ana ekrana geçiliyor. Logo, verdiğiniz görselden sadece
ikon kısmı alınıp (yazı kaldırıldı, arka plan şeffaflaştırıldı) hazırlandı.

## 6. Launcher, Oxygen tarzı sol menüye çevrildi
Ana ekran artık tek düz liste değil — kalıcı bir sol menü + sağda değişen
içerik. "SSH ile Uzak İmaj Al" TEK bir sayfa olmaktan çıkarıldı, her
bağlantı yöntemi (Doğrudan/Port Yönlendirme, VPN, Tor Acil Durum) artık
KENDİ AYRI sidebar sekmesi ve kendi tanıtım sayfasına sahip — özellikle Tor
için gerekliydi, çünkü tek sayfada karışınca (sizin de belirttiğiniz gibi)
yeterince açıklayıcı olmuyordu. Her sayfa: ne işe yaradığı, ne zaman
kullanılacağı, gerekenler (sırasıyla, numaralı) ve adım adım kullanım
içeriyor; Tor sayfasında ayrıca "bu yöntem YAVAŞTIR, birden fazla sunucu
üzerinden dolaşır" uyarısı belirgin bir kutuda var. "Başlat"a basınca önce
AYRI bir "Vaka Bilgileri" ekranı açılıyor (vaka no/inceleyen/yetkili kişi —
TAMAMEN İSTEĞE BAĞLI, boş bırakılıp geçilebilir), sonra gerçek araç
açılıyor. Dil/tema seçimi "Ayarlar" sayfasına taşındı.

## 9. Özellikler dokümanı + iki hata bulundu/düzeltildi
[docs/ozellikler.md](ozellikler.md) oluşturuldu — yazılımın tüm
özelliklerini insan diliyle anlatan ayrı bir doküman. Ayrıca derlenmiş
`.exe`'de iki gerçek hata bulunup düzeltildi (detaylar:
[hatalar_ve_sonuclar.md](hatalar_ve_sonuclar.md)):
- Pencere ikonu bukalemun logosuna hiç dönmüyordu — sebep `customtkinter`'ın
  kendi varsayılan ikonunu 200ms sonra üstüne yazması.
- "SSH motoru yüklenemedi" hatası — `tkinter.scrolledtext` gibi alt
  modüllerin PyInstaller tarafından paketlenmemesi yüzünden.

Genel teknik dersler için [ogrenilenler.md](ogrenilenler.md) eklendi.

## 7. VPN, Cihaz Sahibi, rapor sunumu, Vaka Geçmişi
- **VPN**, "Bağlantı Yöntemi"ne üçüncü seçenek olarak eklendi — kod tarafında
  "Doğrudan" ile aynı, sadece delil zincirinde ayrıca işaretleniyor.
- Vaka Bilgileri kartına **Cihaz Sahibi / Yetkili Kişi** alanı eklendi (evet,
  bu bilgi delil zinciri için önemli — kim inceledi kadar cihazın kimden
  alındığı da kayıt altına alınmalı).
- İşlem bitince artık sadece log satırı değil, **okunabilir bir rapor özeti
  penceresi** açılıyor; tam hali (`report.html`) tüm delil zinciriyle
  birlikte yazdırılabilir/paylaşılabilir tek dosya olarak kaydediliyor.
- Sol menüye **"Vaka Geçmişi"** eklendi — bugüne kadar alınan tüm imajlar
  (hangi motor, hedef, inceleyen, yetkili kişi, durum) tek listede,
  "Raporu Aç" butonuyla.

## 8. Tek tıkla kurulum (.exe)
Artık `pyinstaller build.spec` ile proje tek bir `dist/Chameleon.exe`
dosyasına paketlenebiliyor (~28MB) — kullanıcı Python kurmadan, sadece
çift tıklayarak açabiliyor. Gerçek `.exe` çalıştırılıp doğrulandı.

## 9. customtkinter → PySide6 tam geçiş + dil/tema desteği
Ürün ticari olarak satılacağı için mevcut `customtkinter` görünümü
"kurumsal" hissi vermiyordu. Verilen tasarım sistemine (hex renk paleti,
Inter/JetBrains Mono, 4-6px köşe, gölgesiz, özel radyo/checkbox, durum
rozeti) uygun yeni bir bileşen kütüphanesi (`shared/ui_kit/`) yazıldı ve
üç ekran (launcher, SSH motoru, RAM motoru) buna taşındı — **backend/iş
mantığına hiç dokunulmadı**, sadece UI katmanı değişti. Thread-güvenli
güncelleme artık Qt sinyal/slot; worker-thread-içinden-bloke-eden
"devam edilsin mi?" diyaloğu `threading.Event` deseniyle korundu (bu
sırada `Qt.BlockingQueuedConnection` + mutable dict sinyalinin PySide6'da
referans değil KOPYA taşıdığı bir mock testle keşfedildi, bkz.
[hatalar_ve_sonuclar.md](hatalar_ve_sonuclar.md)). Eski CTk dosyaları
tamamen silindi, `_qt.py` isimleri canonical isimlere döndürüldü.

Ardından **dil (TR/EN) ve tema (koyu/açık) desteği** eklendi: Ayarlar
sayfasındaki geçiş kartları artık çalışıyor. `METHOD_INFO`'daki dört
yöntemin tüm alanlarına İngilizce çeviri eklendi (önceden sadece TR
vardı, `en` seçilince yöntem sayfası `KeyError` verirdi) ve ana
sayfa/vaka bilgileri/bölüm başlıkları da dile bağlandı. Headless testle
(`QT_QPA_PLATFORM=offscreen`) dört sayfa × iki dil × iki tema exception
fırlatmadan gezildi, ekran görüntüleriyle görsel olarak da doğrulandı.

## 10. Mevcut ekranlarda görsel tutarlılık düzeltmeleri
PySide6 geçişi sonrası fark edilen 3 tutarsızlık giderildi:
- **"Vaka Bilgileri" bağımsız sayfası** — 3 giriş alanı kartsız, boş koyu
  arka plan üzerinde duruyordu ("tamamlanmamış" görünüyordu). Artık
  diğer sayfalardaki gibi tek bir kart içinde (max 640px, üstte).
- **"SSH ile Uzak İmaj Al"** — sağ üstteki durum göstergesi düz
  nokta+metinden gerçek bir pill/rozete çevrildi (bağlı=yeşil, bağlı
  değil=gri, hata=kırmızı, bağlanıyor=sarı); "Bağlan ve Diskleri
  Listele" butonuna gerçek bir yükleniyor durumu eklendi (disabled +
  "Bağlanıyor..." metni + rozet sarıya döner). Host/Port/SSH Anahtar
  zaten JetBrains Mono kullanıyordu, şifre zaten maskeliydi — kontrol
  edildi, ek değişiklik gerekmedi.
- **Yöntem tanıtım sayfaları** (Doğrudan/VPN/Tor/RAM) — "Ne zaman
  kullanılır?"/"Gerekenler"/"Adım adım kullanım" blokları artık ayrı
  birer kart, diğer ekranlarla birebir aynı stil; numaralı listelerdeki
  rakamlar yeni `StepBadge` (mavi daire + beyaz rakam) ile değişti.

Düzeltme sırasında bir kart-içi satır sarmalama hatası (`QWidget()` ile
arka plan sızıntısı, aynı ailede daha önce QLabel için çözülen soruna
benzer) bulunup giderildi — bkz. [hatalar_ve_sonuclar.md](hatalar_ve_sonuclar.md).
Tüm sayfalar headless testle (4 sayfa × 2 dil × 2 tema) ve ekran
görüntüleriyle doğrulandı.

## 11. Güvenlik denetimi (security auditor gözüyle) + 2 bulgunun düzeltilmesi
Kullanıcının isteğiyle SSH kimlik bilgileri (paramiko), Tor x25519
client-auth anahtarları, `RamImagerCLI.exe`/PowerShell/bash subprocess
çağrıları ve hardcoded secret/güvensiz varsayılan taraması yapıldı (tüm
ilgili dosyalar okunup tüm kod tabanında regex taraması çalıştırıldı).
Çoğu alan zaten güvenliydi (parola hiç komut satırına gömülmüyor, hep
SSH stdin üzerinden; host key doğrulaması varsayılan `RejectPolicy`;
tüm uzak yollar `shlex.quote`/`powershell_quote` ile kaçırılıyor; chain-
of-custody logu hiç parola/anahtar içermiyor). İki gerçek bulgu çıktı ve
ikisi de düzeltildi:
- **`ram_gui.py` "Full" (Yönetici/UAC) modda `ShellExecuteW` argüman
  kaçırma hatası** (CWE-88) — parametre string'i sadece boşluk varsa
  tırnaklıyordu, içindeki `"` karakterini kaçırmıyordu; Vaka No/İnceleyen
  gibi serbest metin alanlarından yükseltilmiş sürece argüman
  sızabiliyordu. `subprocess.list2cmdline()` ile değiştirildi (normal
  girdilerde çıktı birebir aynı — test edilip doğrulandı).
- **Tor operatör özel anahtarı düz metin, dosya izni kısıtlanmamış**
  (`keys/operator_tor_key.json`) — `gui_v2.py`'ye
  `_restrict_key_file_permissions()` eklendi (POSIX: `chmod 600`,
  Windows: `icacls` ile sadece mevcut kullanıcı). Gerçek dosyada
  `icacls` çıktısıyla doğrulandı.

Detaylar: [hatalar_ve_sonuclar.md](hatalar_ve_sonuclar.md).

## 12. Uzak "Gözat" (klasör gezinme) özelliği
Dosya/Klasör modunda önceden uzak yol elle yazılıyordu — native
`QFileDialog` sadece BU bilgisayarın diskini gösterebildiği için SSH
hedefini gösteremiyordu. Yeni `RemoteBrowseDialog` (gui_v2.py), mevcut
SSH bağlantısı üzerinden salt-okunur `find`/`Get-ChildItem` ile hedefte
klasör klasör gezinmeyi sağlıyor: `file_acquirer.list_remote_directory`/
`windows_acquirer.list_remote_directory_windows` (tek seviye, hiçbir şey
yazmıyor). Klasöre çift tıklayınca içine giriyor, dosyaya çift tıklayınca
seçip kapanıyor, "Bu Klasörü Seç" mevcut klasörü seçiyor. Her klasör
açılışı chain-of-custody'ye yeni `DIRECTORY_LISTED` olayı olarak ayrıca
loglanıyor (operatörün nereye baktığı tam izlenebilsin diye — önceden
elle yazılan bir yolun hiç izi yoktu, bu aslında delil zincirini
güçlendiriyor). İkonlar app'in kendi Lucide SVG setinden (emoji değil).
Mock SSH ile Linux+Windows listeleme, gezinme, loglama ve "bağlantı
yokken Gözat" hata durumu test edildi; ekran görüntüsüyle doğrulandı.

## 13. "Gözat" özelliği gerçek SSH hedefinde test edildi + exe yeniden derlendi
Önceki oturumda mock SSH ile test edilen "Gözat" özelliği, bu kez WSL
üzerinde gerçek bir SSH sunucusuna bağlanılarak (iç içe klasör gezinme,
olmayan yol durumu, chain-of-custody loglaması) uçtan uca doğrulandı.
Ardından güvenlik düzeltmeleri + Gözat özelliğiyle `dist/Chameleon.exe`
yeniden derlendi, sağlıklı açılıp kapandığı doğrulandı.

## 14. SSH bağlantı hataları artık nedene özgü + Sunucu Kimlik Doğrulama
Kullanıcının "hata mesajı kişiye ne yapması gerektiğini söylemeli"
geri bildirimini araştırırken asıl kök sebep bulundu: uygulama
`RejectPolicy` kullandığı için, bilgiler doğru olsa bile daha önce hiç
bağlanılmamış bir sunucuya (adli bilişimde asıl senaryo — özellikle
şahsa ait cihazlarda parmak izini teyit edecek bir yetkili genelde
olmuyor) bağlantı reddediliyordu, arayüzde bunu onaylatacak bir yol da
yoktu. Çözüm: `ssh_connector.py`'nin `connect()`'i artık başarısızlık
türünü sınıflandırıyor (host key / kimlik doğrulama / ulaşılamama /
diğer), `gui_v2.py` her biri için ayrı, çözüm gösteren bir mesaj
üretiyor. "SSH Bağlantı Bilgileri" kartına **"Sunucu Kimlik Doğrulama:
Sıkı doğrula (önerilen) / Doğrulamayı atla"** seçeneği eklendi
(varsayılan güvenli tarafta), atlanırsa delil zincirine ayrıca
kaydediliyor. Gerçek bir SSH sunucusuna (WSL) karşı üç hata türü de
ayrı ayrı test edildi.

## 15. Bilgi Merkezi sayfası eklendi
Kullanıcının "bazı seçimler kavramsal olarak kafa karıştırıcı, bunlar
için ayrı bir alan olsun" isteğiyle, `shared/help_content.py` (tek,
paylaşılan içerik kaynağı) + launcher sidebar'ına yeni **"Bilgi
Merkezi"** sekmesi eklendi. Tüm sistem tarandı, 6 kavram için detaylı
anlatım yazıldı: Sunucu Kimlik Doğrulama (Host Key), Live/Offline
Acquisition (Yazma Engelleme — daha önce hiç açıklanmıyordu), Delil
Zinciri (Chain of Custody), Hash/Bütünlük Doğrulaması, RAM "Full" Modu
(Yönetici/Sürücü/Secure Boot), Tor/.onion/Operatör Anahtarı. İlgili
ekranlardaki her "Bu ne demek?" linki, launcher içinden açıldığında
Bilgi Merkezi'ndeki ilgili karta doğrudan kaydırıyor; `gui_v2.py`/
`ram_gui.py` standalone çalıştırıldığında aynı içerik küçük bir
dialogda gösteriliyor. Headless testlerle her linkin doğru karta
kaydırdığı ekran görüntüsüyle doğrulandı.

Aynı sırada `cryptography` paketi de (pip-audit'te bulunan
PYSEC-2026-3552 için) 49.0.0 → 50.0.1'e yükseltildi — etkilenen kod
yolu (PKCS#7) projede zaten kullanılmıyordu, yine de bedelsiz olduğu
için yapıldı.

## 16. Rol seçim ekranı + hedef taraf sihirbazı eklendi
Kullanıcı, uygulamanın operatör (istemci) ve hedef (sunucu) tarafında
AYNI çalışmaması gerektiğini belirtti — hedef tarafta teknik bilgisi
olmayan biri olabileceği için. Uygulama artık her açılışta (kayıtlı
tercih yok, her seferinde farklı biri kullanıyor olabilir) önce **"Bu
bilgisayardaki kişi kimsiniz? Operatörüm / Bu Cihaz İnceleniyor"**
soruyor. "Operatörüm" mevcut launcher'ı değiştirmeden açıyor. "Bu Cihaz
İnceleniyor" seçilirse sidebar/RAM-imajı/SSH-araçları gibi operatör
araç seti HİÇ GÖSTERİLMEZ, bunun yerine 3 numaralı adımdan oluşan ayrı
bir sihirbaz açılıyor: (1) operatör anahtarını yapıştır, (2)
"Bağlantıyı Başlat" (embedded Tor'u arka planda ayağa kaldırıp hidden
service kurar, UI donmaz), (3) üretilen `.onion` adresini kopyala/
operatöre ilet + "Bağlantıyı Kapat". Pencere kapanırken/"Geri" ile
çıkılırken açık kalmış bir Tor süreci varsa otomatik kapatılıyor —
orphan process kalmıyor, gerçek Tor süreciyle doğrulandı.

**Bu arada kritik bir bug bulundu**: sihirbazı gerçek gömülü Tor'a
karşı test ederken, `engines/portable_kit/tor_manager.py`'deki
`ADD_ONION` çağrısı hiç çalışmıyormuş (yanlış parametre kombinasyonu —
detaylar [hatalar_ve_sonuclar.md](hatalar_ve_sonuclar.md)'da).
Düzeltildi, gerçek bir operatör anahtarıyla tekrar denendi — geçerli
bir `.onion` adresi üretildi. Yani **hedef tarafın gerçek Tor ağı
üzerinden hidden service kurması artık doğrulandı** — madde 3'teki
"gerçek ağ üzerinden canlı test" bunun yarısını tamamlıyor. Eksik
kalan: operatörün o gerçek `.onion` adresine bağlanıp SSH kurabildiği
(döngünün ikinci yarısı) henüz denenmedi, muhtemelen iki ayrı makine/ağ
gerektiriyor.

## 17. Host key TOFU (hatırla + karşılaştır) eklendi
"Doğrulamayı atla" modunun hiç hafızası olmadığı (aynı cihaza tekrar
bağlanılsa bile her seferinde "ilk kez görüyormuş" gibi davranması)
kullanıcıyla birlikte fark edildi. `ssh_connector.py`'ye Chameleon'a
özel bir known_hosts dosyası (`engines/ssh_engine/keys/
chameleon_known_hosts`, kullanıcının kendi SSH ayarlarına dokunmuyor)
ve yeni `_TofuPolicy` eklendi: ilk bağlantıda sunucunun kimliği
otomatik kaydediliyor, sonraki bağlantılarda o kayıtla karşılaştırılıyor.
**Kritik**: sunucunun kimliği SONRADAN değişirse, "atla" seçili olsa
bile bağlantı REDDEDİLİYOR ve kullanıcıya özel bir "DİKKAT" mesajı
gösteriliyor — bu paramiko'nun kendi davranışı, hiçbir policy bunu
atlayamıyor. Bir kez TOFU ile öğrenilen bir sunucu artık "Sıkı doğrula"
modunda da çalışıyor. Gerçek bir SSH sunucusuna (WSL) karşı dört
senaryo da (öğrenme, tanıma, sıkı modda geçerlilik, gerçekten değişen
bir anahtarın reddedilmesi) ayrı ayrı test edildi.

İlk önerilen ikinci bir iyileştirme (hedef tarafın kendi makinesine de
bir delil zinciri logu yazması) kullanıcı tarafından haklı olarak
reddedildi: hedef cihaza herhangi bir dosya yazmak, delil bütünlüğünü
zedeler (tam olarak "Live vs Offline" ayrımının önlemeye çalıştığı şey)
— bu yüzden uygulanmadı.

## 18. Bilgi Merkezi'ne gidince form/bağlantı kaybolma hatası düzeltildi
Kullanıcı, bir arac ekranındaki "Bu ne demek?" linkine basıp Bilgi
Merkezi'ne gidince, doldurduğu form alanlarının sıfırlandığını ve
"kaldığı yerden devam edemediğini" bildirdi — gerçek bir bug'dı
(detaylar [hatalar_ve_sonuclar.md](hatalar_ve_sonuclar.md)'da). Çözüm:
arac ekranından Bilgi Merkezi'ne geçilirken o ekran SİLİNMEDEN
(`_show_help_from_tool`) saklanıyor, Bilgi Merkezi'nde beliren "←
Kaldığınız yere dön" butonu (`_return_from_help`) aynı widget'ı tüm
girilmiş değerleriyle (ve varsa açık SSH bağlantısıyla) geri getiriyor.
Hem SSH hem RAM motoru ekranında, hem de "Geri" kullanılmadan başka bir
sayfaya geçilmesi durumunda (eski sayfa sessizce temizleniyor mu) test
edildi. `dist/Chameleon.exe` bu düzeltmeyle yeniden derlendi.

## 19. Bilgi Merkezi kaydırma düzeltmesi + 4 uzman ajanla kapsamlı inceleme
Bir sonraki geri bildirimde, bazı "Bu ne demek?" linklerinin (özellikle
"Delil zinciri nedir?") sanki sayfanın başına atıyormuş gibi görünmesi
bildirildi — kök neden `ensureWidgetVisible()`'ın kart zaten kısmen
görünürdeyse neredeyse hiç kaydırmaması, kartı viewport'un en altına
sıkıştırması. Kaydırma çubuğu artık doğrudan hedef kartın konumuna
ayarlanıyor, 6 konunun tümü ölçülerek doğrulandı.

Ardından kullanıcı "bu güvenilir mi, projeyi sızdırır mı" diye sordu —
kullanılan ajanların (Incident Responder, Security Architect,
Penetration Tester, Code Reviewer) bu oturumun/CLI'nin İÇİNDE, yerel
dosya okuma araçlarıyla çalışan özelleşmiş roller olduğu, hiçbir kodun
üçüncü tarafa gönderilmediği açıklandı. Bu 4 ajanla kod/tasarım
incelemesi yapıldı, bulunan TÜM gerçek sorunlar düzeltildi (detaylar
[roadmap.md](roadmap.md) ve [hatalar_ve_sonuclar.md](hatalar_ve_sonuclar.md)'da):
- **[KRİTİK]** Rapordaki "doğrulandı" alanı hiç doldurulmuyordu — düzeltildi.
- **[KRİTİK]** Delil zinciri log'u hedef cihazdaki dosya adlarıyla
  manipüle edilebiliyordu (delil kaybı + sahte kayıt enjeksiyonu) — düzeltildi.
- Hedef sihirbazında yapıştırılan anahtar hiç doğrulanmıyordu — her iki
  tarafta da görünen bir "parmak izi" koduyla düzeltildi.
- Tor kontrol protokolü komutlarına ham metin enjekte edilebiliyordu —
  format doğrulaması eklendi.
- `chameleon_known_hosts` symlink koruması + eşzamanlı TOFU yazma
  yarışı için kilit eklendi.
- `last_error_type` artık kırılgan mesaj eşleştirmesi yerine exception türüne bakıyor.
- Delil zincirine artık sunucunun gerçek host key parmak izi de kaydediliyor.
- Live Acquisition'ın tutarlılık sınırlaması artık hem Bilgi Merkezi'nde hem raporda belirtiliyor.
- Bağlantı koparıp devam edilen (resume) işlemlerde write-block durumu artık gerçekten kontrol ediliyor.
- Hedef sihirbazındaki 3 kararlılık hatası (geç gelen sinyal çökmesi,
  çift tıklama, aktif işi olan bir sayfanın sessizce silinmesi) düzeltildi.
- Reddedilen öneri: hedef cihaza delil zinciri logu yazmak — kullanıcı
  haklı olarak reddetti (delil bütünlüğünü zedeler).
- Ertelenen (mimari ölçekte, roadmap'e not edildi): log dosyasının kendi
  bütünlük koruması, operatör anahtarı yenileme, kalıcı onion kimliği.

Tüm düzeltmeler mock/gerçek SSH ve gerçek Tor ile ayrı ayrı test edildi,
`dist/Chameleon.exe` yeniden derlendi.

## 20. Erişilebilirlik denetimi + düzeltmeleri
Kullanıcı, `shared/ui_kit/` ve ekranların erişilebilirlik/tasarım
tutarlılığı açısından denetlenmesini istedi (önce "web-design-guidelines"
skill'i ve `src/components/` istendi ama bu proje bir PySide6 masaüstü
uygulaması, ikisi de bu projeye ait değildi — netleştirme sonrası elle/
kod-okuyarak denetim yapıldı). WCAG kontrast oranları matematiksel olarak
hesaplandı: kart başlıkları (koyu temada 3.35–3.66:1, gereken 4.5:1),
girdi alanı kenarlıkları (1.2:1, gereken 3:1), açık temada uyarı metni
(2.97:1) hepsi standardın altında çıktı. Daha da önemlisi, `RadioButton`
klavye odağını HİÇ çizmiyordu — Tab ile gezinirken hangi seçenekte
olduğunuz görünmüyordu (uygulama genelinde Bağlantı Yöntemi, Sunucu
Kimlik Doğrulama, Live/Offline vb. hepsi bunu kullanıyor). Kullanıcı
"evet başla" deyince: yeni bir `ACCENT_TEXT` rengi + parlatılmış
`BORDER` + koyulaştırılmış açık-tema `WARNING` eklendi, `RadioButton`'a
gerçek bir odak çerçevesi çizildi, `Input`'un odak kenarlığı
güçlendirildi, `MonoLabel`'a klavye ile seçilebilirlik eklendi,
butonlara `:focus` durumu eklendi. Headless ekran görüntüleriyle hem
koyu hem açık temada doğrulandı, tüm önceki regresyon testleri tekrar
geçti, `dist/Chameleon.exe` yeniden derlendi. Detaylar
[roadmap.md](roadmap.md)'de.

## 21. Rol seçim ekranındaki tekrarlı buton metni düzeltildi
Kullanıcı, açılıştaki rol seçim ekranında ("Operatörüm" / "Bu Cihaz
İnceleniyor") her iki kartın da aynı, generic "Bunu Seç" yazısını
taşımasını hoş bulmadığını bildirdi. `chameleon_gui.py`'deki iki
`PrimaryButton` artık kendi kartına özgü, ayrım yapan bir metin
taşıyor: Operatör kartı "Operatör Olarak Devam Et", hedef cihaz kartı
"Bu Cihazla Devam Et". Fonksiyonel bir değişiklik yok, sadece metin.

## 22. Product Manager degerlendirmesiyle 7 kucuk iyilestirme eklendi
Kullanıcı, projeyi ağırlaştırmadan/kapsam dışına taşmadan hangi küçük
özelliklerin eklenebileceğini sordu. "Product Manager" ajanı roadmap ve
mevcut mimariyi tarayıp 8 öneri çıkardı; kullanıcı hepsini detaylı
anlatıp uygulamamı istedi. Hiçbiri yeni bağımlılık gerektirmedi:
- **Rapor sürüm hatası düzeltildi** — `TOOL_VERSION` artık gerçek
  uygulama sürümünü (`shared/version.py`) okuyor, sabit "1.0" değil.
- **Rapor sidecar hash'i** — `report.json.sha256`, kaydedildiği andaki
  içeriğin hash'i.
- **Bağımsız doğrulama CLI'si** — yeni `verify_report.py`, GUI'ye hiç
  bağımlı olmadan report.json + imajı çapraz doğruluyor.
- **Yerel disk alanı ön kontrolü** — imaj almadan önce boş alan
  kontrolü, yetersizse işlem hiç başlamıyor.
- **Disk model/seri no kaydı** — `lsblk -P` (Linux) / `Get-Disk`
  (Windows) ile diskin gerçek kimliği rapora ekleniyor.
- **Son bağlanılan hedefler hafızası** — host alanı için otomatik
  tamamlama, port/kullanıcı adı otomatik dolduruluyor (şifre asla
  saklanmıyor).
- **SSH bağlantı zaman aşımı koddan ayarlanabilir** hale getirildi
  (GUI'ye yeni bir panel eklenmeden).

Yedinci öneri (Vaka Geçmişi'ne CSV dışa aktarma) uygulanırken **önemli
bir bulgu** ortaya çıktı: `docs/roadmap.md`'nin "Yapıldı" dediği
"Vaka Geçmişi" sidebar sayfası kodda hiç yok — muhtemelen
customtkinter->PySide6 geçişinde launcher kabuğu sıfırdan kurulurken
kaybolmuş. Backend (`case_history.json`/`read_history()`) sağlam, sadece
UI sayfası eksik. CSV önerisi bu yüzden uygulanmadı, roadmap.md
düzeltilip "Sırada" listesine "sayfa yeniden eklenmeli" olarak taşındı
(detaylar [hatalar_ve_sonuclar.md](hatalar_ve_sonuclar.md)'da). Her
değişiklik mock/headless testlerle ayrı ayrı doğrulandı (tamper
tespiti, disk alanı yetersizliği senaryosu, model/seri no ayrıştırma,
completer + otomatik doldurma).

## 23. Roadmap'ten 4 madde sırayla tamamlandı: Vaka Geçmişi, sıkıştırma, dosya resume, gerçek portable exe
Kullanıcı "Sırada" listesinden 1, 3, 6, 7 numaralı maddeleri sırayla
istedi:
- **Vaka Geçmişi sayfası** launcher'a geri eklendi (bir önceki bulunan
  eksiklik) + CSV dışa aktarma butonu. Bunu test ederken TÜM launcher
  sayfa geçişlerini etkileyen ortak bir `deleteLater()`/asenkronluk
  hatası bulunup düzeltildi (`_clear_content()`'e `hide()` eklendi —
  detaylar [hatalar_ve_sonuclar.md](hatalar_ve_sonuclar.md), genel ders
  [ogrenilenler.md](ogrenilenler.md)'de).
- **Offline modda isteğe bağlı gzip sıkıştırma** eklendi. Tasarım
  sisteminde ilk kez bir `Checkbox` bileşeni yazıldı (RadioButton ile
  aynı çizim/odak deseni). Delil bütünlüğü hash'i her zaman HAM içeriğe
  ait kalıyor; `verify_report.py`'ye gzip farkındalığı eklendi.
- **`file_acquirer.py`'de büyük dosya resume** — tek dosya alma artık
  disk imajlamayla AYNI blok+doğrulama+yeniden bağlanma desenini
  kullanıyor; bir dosyanın ortasında kopan bağlantı artık baştan değil
  kaldığı bloktan devam ediyor.
- **`Chameleon.exe` gerçekten portable oldu** — sadece roadmap'in
  adlandırdığı iki yol değil (LOG_DIR/HISTORY_DIR), aynı hatanın
  TOFU known_hosts ve operatör Tor anahtarında da bulunduğu ortaya
  çıktı; hepsi `sys.executable`'a göre düzeltildi.

Her madde mock SSH ve (portable düzeltmesi için) sahte `sys.frozen`/
`sys.executable` simülasyonuyla ayrı ayrı test edildi; önceki tüm
regresyon testleri tekrar geçti. Detaylar [roadmap.md](roadmap.md)'de.

## 24. Sahaya özel, hafif "hedef kiti" exe'si eklendi
Kullanıcı, sahaya götürülen exe'nin operatörün TÜM araç setini (SSH/RAM
motorları vb.) içermesinin hem gereksiz hem kafa karıştırıcı olduğunu,
sadece "Bu Cihaz İnceleniyor" sihirbazını içeren ayrı, daha hafif bir
paket önerdi. Yeni `build_target_kit.spec` + `launcher/
target_kit_main.py` (ince bir giriş noktası, `CHAMELEON_TARGET_ONLY`
ortam değişkenini ayarlayıp AYNI `chameleon_gui.py`'yi çağırır) ile
`dist/ChameleonHedefKiti.exe` üretiliyor. `ChameleonWindow` bu
değişkeni görünce rol seçim ekranını atlayıp doğrudan sihirbazı açıyor,
"Geri" butonu da (dönülecek bir yer olmadığı için) gizleniyor.
`engines/ssh_engine/local_collector/*` ve `engines/ram_engine/*` bu
derlemeye hiç paketlenmiyor.

Gerçek bir derleme yapılıp iki exe de gerçek Windows süreci olarak
başlatıldı; Windows UI Automation ile (tıklama YAPILMADAN, sadece
salt-okunur metin/buton okumasıyla) hem hedef kitinin doğrudan
sihirbaza gittiği hem tam `Chameleon.exe`'nin rol seçim ekranını hâlâ
gösterdiği doğrulandı. Boyut farkı dürüstçe ölçüldü: beklenenin aksine
küçük (~%2, PySide6/Qt ve gömülü tor.exe zaten HER İKİ tarafta da
gerekli olduğu için) — asıl kazanç kafa karışıklığının önlenmesi.
Detaylar [roadmap.md](roadmap.md)'de.

## Şu an bekleyen
- Operatörün, hedef tarafın ürettiği gerçek bir `.onion` adresine
  `tor_client.py` ile bağlanıp SSH kurabildiğinin doğrulanması (Tor
  canlı testinin "iki cihaz arası" ikinci yarısı) — sizinle birlikte
  yapılacak.
- `gui_v2.py`/`ram_gui.py`'nin kendi araç ekranları hâlâ TR-only —
  dil desteği şimdilik sadece launcher'da.
- Ertelenen mimari iyileştirmeler (bkz. madde 19): delil zinciri log
  bütünlüğü, operatör Tor anahtarı yenileme, kalıcı onion kimliği.
