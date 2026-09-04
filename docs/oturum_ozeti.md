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

## Şu an bekleyen
- Gerçek bir SSH hedefine bağlanıp "Gözat" özelliğinin gerçek cihazda
  denenmesi (mock testler geçti, gerçek cihaz testi henüz yapılmadı).
- `dist/Chameleon.exe`'nin bu son değişikliklerle (güvenlik düzeltmeleri
  + Gözat özelliği) yeniden derlenmesi — henüz yapılmadı.
- Gerçek Tor ağı üzerinden canlı test (sizinle birlikte).
- `gui_v2.py`/`ram_gui.py`'nin kendi araç ekranları hâlâ TR-only —
  dil desteği şimdilik sadece launcher'da.
