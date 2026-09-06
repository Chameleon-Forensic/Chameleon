# Chameleon — Özellikler

Chameleon, bir bilgisayarın diskini, dosyalarını ya da belleğini (RAM) **bozmadan**,
**SHA-256 ile bütünlüğü kanıtlanabilir** şekilde kopyalayan bir adli bilişim
(digital forensics) aracıdır. Bu doküman, yazılımın sunduğu özellikleri anlatır.

## 1. İki alma yöntemi

### SSH ile Uzak İmaj Alma
Ağ üzerinden erişilebilen bir **Linux ya da Windows** bilgisayardan, SSH
bağlantısı üzerinden imaj alır. Hedef cihaza herhangi bir program kurulması
gerekmez — sadece çalışan bir SSH sunucusu (Linux: `sshd`, Windows: OpenSSH
Server) yeterlidir.

- **Tam Disk**: Diskin tamamı, parça parça (chunk) alınır. Her parça diske
  yazılmadan önce SHA-256 ile doğrulanır — bozuk/eksik bir parça asla imaja
  karışmaz.
  - **Live Acquisition**: Disk aktif kullanımdayken (write-block uygulanmadan)
  - **Offline Acquisition**: Disk salt-okunur (write-blocked) hale getirilerek
  - **Ayarlanabilir parça (blok) boyutu**: 4 / 16 / 32 / 64 MB arasından seçilebilir
  - **Bağlantı koparsa devam edilebilir (resume)**: Yarım kalan bir işlem,
    kaldığı yerden tekrar başlatılabilir
  - **Yerel disk alanı ön kontrolü**: İmaj almaya başlamadan önce, yerel
    çıktı konumunda yeterli boş alan olup olmadığı kontrol edilir —
    saatler süren bir aktarımın sonda "disk doldu"ya çarpması önlenir
- **Tek Dosya / Klasör**: Tüm diski değil, belirli bir dosyayı ya da klasörü
  (alt klasörleriyle birlikte) alır; her dosya kendi SHA-256'sı ile doğrulanır.
  Büyük dosyalar da (tam disk gibi) parça parça alınır -- bağlantı bir dosyanın
  ortasında koparsa, o dosya baştan değil kaldığı parçadan devam eder.
  - **Sıkıştırma (gzip, sadece Offline modda)**: Tam disk imajı isteğe bağlı
    olarak gzip ile sıkıştırılıp diskten tasarruf edilebilir. Delil bütünlüğü
    hash'i her zaman sıkıştırılmamış içeriğe aittir.

### RAM İmajı Alma (Windows, yerel)
Bu bilgisayarın kendi belleğini imaj alır — uzak bağlantı gerekmez.
- **Process Dump**: Tek bir çalışan programın belleği. Yönetici yetkisi
  gerekmez, hızlıdır.
- **Full (Tam Bellek)**: Tüm sistem belleği. Yönetici yetkisi ve önceden
  hazırlanmış bir sürücü (driver) gerektirir.

## 2. Üç bağlantı yöntemi

Hedefe nasıl ulaşıldığına göre üç seçenek sunulur, hangisinin kullanılacağı
duruma göre değişir:

- **Doğrudan / Port Yönlendirme** — hedefe aynı ağdan ya da router'da bir port
  yönlendirme kuralıyla doğrudan ulaşılabiliyorsa. En basit ve en hızlı yol.
- **VPN** — operatörün bilgisayarı zaten hedefin ağına bir VPN tüneliyle
  bağlıysa. Teknik olarak Doğrudan ile aynıdır, sadece hangi ağ yolunun
  kullanıldığı delil zincirinde ayrıca kayıt altına alınır.
- **Tor (Acil Durum)** — hedef ağa **hiçbir** erişim/yetki yoksa kullanılan
  son çare. Sahaya götürülen bir taşınabilir kit, hedef cihazda çalıştırılınca
  Tor ağı üzerinden dışarıya açılan bir adres (`.onion`) oluşturur; bu adrese
  sadece operatörün özel anahtarına sahip olan bağlanabilir. Router'da hiçbir
  ayar gerekmez, ama veri aktarımı Tor ağındaki birden fazla sunucu üzerinden
  geçtiği için **yavaştır**.

## 3. Bütünlük ve delil zinciri (chain of custody)

- Her blok/dosya, diske yazılmadan **önce** SHA-256 ile doğrulanır.
- İşlem tamamlanınca isteğe bağlı olarak **İmaj Doğrula** ile bütünlük tekrar
  kontrol edilebilir.
- Her önemli olay (işlem başlangıcı/bitişi, write-block uygulanması, blok
  alınması, bağlantı kopması/toparlanması, hash uyuşmazlığı, hangi ağ yolunun
  — doğrudan/VPN/Tor — kullanıldığı) zaman damgalı olarak bir günlük dosyasına
  yazılır.
- **Vaka Bilgileri**: Vaka No, İnceleyen, Cihaz Sahibi/Yetkili Kişi ve
  Organizasyon bilgisi kaydedilebilir. Bu bilgiler **tamamen isteğe
  bağlıdır** — kendi rapor sürecinizi kullanıyorsanız boş bırakılabilir.
- **Otomatik rapor**: Her işlem sonunda, vaka bilgileri, hedef bilgisi, hash,
  boyut, sonuç ve tam delil zinciri olay listesini içeren bir rapor
  (`report.json` + yazdırılabilir `report.html`) otomatik üretilir. İşlem
  bitince ekranda bir özet de gösterilir. Tam disk alımlarında kaynağın
  sadece yolu (`/dev/sdb` gibi) değil, gerçek disk modeli/seri numarası da
  rapora yazılır (kalıcı, benzersiz bir kaynak kimliği için).
- **UTC yanında isteğe bağlı yerel saat gösterimi**: Ayarlar sayfasından
  bir saat dilimi seçilirse, `report.html`'deki UTC zaman damgalarının
  yanına "(UTC+03:00) Istanbul" gibi bir yerel saat karşılığı eklenir —
  sadece okunabilirlik içindir, `report.json`'daki (kanıt niteliğindeki)
  değer her zaman saf UTC kalır.
- **Rapor bütünlüğü**: `report.json` kaydedilirken yanına bir `.sha256`
  dosyası da yazılır — raporun kendisinin sonradan değiştirilip
  değiştirilmediği bağımsız olarak kontrol edilebilir.
- **Bağımsız doğrulama aracı**: `verify_report.py`, Chameleon'un kendi
  arayüzüne hiç ihtiyaç duymadan (komut satırından) bir raporu ve imajı
  çapraz doğrular — ikinci bir uzman/denetçi aynı sonuca bağımsız
  ulaşabilir.
- **Vaka Geçmişi**: Bugüne kadar alınan tüm imajlar (hangi motor, hedef,
  inceleyen, yetkili kişi, sonuç) tek bir listede, sol menüden erişilebilir.
  Liste CSV olarak dışa aktarılabilir.

## 4. Güvenlik

- Kullanıcıdan gelen tüm değerler (disk yolu, dosya yolu vb.) uzak komutlara
  gömülmeden önce kaçırılır (shell/PowerShell enjeksiyonuna karşı).
- SSH host key doğrulaması varsayılan olarak sıkı (strict) modda çalışır —
  bilinmeyen bir sunucuya sessizce bağlanılmaz. Bunun mümkün olmadığı
  durumlar için (örn. şahsa ait, ilk kez bağlanılan bir cihaz) "Doğrulamayı
  atla" seçilebilir — bu modda bile sunucunun kimliği ilk bağlantıda
  kaydedilir ve sonraki bağlantılarda karşılaştırılır; kimlik SONRADAN
  değişirse (olası bir müdahale sinyali) bağlantı yine reddedilir.
- Tor bağlantısında kimlik doğrulama (client authorization) zorunludur —
  `.onion` adresini ele geçiren biri, operatörün özel anahtarı olmadan
  bağlanamaz.
- Parolalar uzak komut satırına hiçbir zaman yazılmaz; SSH kanalı üzerinden
  güvenli şekilde iletilir.

## 5. Kullanılabilirlik

- Açık/koyu tema, Türkçe/İngilizce dil desteği.
- SSH ekranındaki Host alanı, önceki başarılı bağlantıları hatırlar — bir
  öneri seçildiğinde port/kullanıcı adı da otomatik doldurulur (parola
  hiçbir zaman hatırlanmaz).
- Sol menülü, her yöntemin kendi tanıtım sayfasına sahip olduğu bir arayüz —
  her sayfa ne işe yaradığını, ne zaman kullanılacağını, gerekenleri ve adım
  adım kullanımı anlatır.
- **Bilgi Merkezi**: kafa karıştırıcı olabilecek kavramların (sunucu kimlik
  doğrulama, Live/Offline Acquisition, delil zinciri, hash doğrulaması, RAM
  Full modu, Tor/.onion/operatör anahtarı) sade dilde anlatıldığı ayrı bir
  sayfa. İlgili ekranlardaki "Bu ne demek?" linkleri doğrudan o konuya götürür.
- Tek bir `.exe` olarak paketlenebilir — kullanıcı Python kurmadan
  çalıştırabilir. Gerçek anlamda taşınabilir (portable): vaka geçmişi,
  loglar, öğrenilen sunucu kimlikleri ve operatör anahtarı `.exe`'nin
  bulunduğu klasöre kaydedilir — USB'den farklı bir bilgisayara taşınıp
  çalıştırıldığında bu veriler kaybolmaz/sıfırlanmaz.

## 6. Rol seçimi: operatör mü, hedef taraf mı?

Uygulama açılışta önce "Bu bilgisayardaki kişi kimsiniz?" diye sorar:

- **Operatörüm (İnceleyen)** — yukarıda anlatılan tüm araçlara (SSH/RAM
  motorları, Bilgi Merkezi, Ayarlar) sahip normal ekran açılır.
- **Bu Cihaz İnceleniyor** — sahada, teknik bilgisi olmayabilecek bir
  kişi için: operatörün araç seti hiç gösterilmez, bunun yerine sadece 3
  adımdan oluşan bir sihirbaz açılır (operatör anahtarını yapıştır →
  bağlantıyı başlat → oluşan adresi operatöre ilet). Bu, Tor (Acil Durum)
  yönteminde sahaya götürülen "taşınabilir kit"in arayüzüdür. Bu ekranda
  dil seçimi olmadığı için tüm metinler Türkçe VE İngilizce birlikte
  gösterilir.
- Sahaya götürülecek **ayrı, daha hafif bir `.exe`** de var
  (`dist/ChameleonHedefKiti.exe`) — sadece bu sihirbazı içerir, rol
  seçimi bile göstermez; operatör araç seti (SSH/RAM motorları) hiç
  paketlenmediği için teknik bilgisi olmayan kişi ilgisiz bir menüyle
  hiç karşılaşmaz.
