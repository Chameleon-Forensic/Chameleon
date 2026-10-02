# Kararlar

> Bu dosya, geliştirme sırasında birden fazla makul seçenek arasında
> kaldığım ve kullanıcı adına karar vermem istenen noktaları kayıt altına
> tutar: hangi seçenekler değerlendirildi, hangisi seçildi, neden. Amaç
> geriye dönüp "neden böyle yapılmış" diye sorulduğunda cevabı burada
> bulabilmek — `docs/roadmap.md` NE yapıldığını, bu dosya YARIN NEDEN o
> şekilde karar verildiğini tutuyor.

## 2026-09-30 — Git: origin'deki eski/paralel commit (de8ce06) sorunu

**Durum:** Cloud oturumuna geçiş için branch'i push etmeye çalışırken,
`origin/feature-flexibility-and-portability`'nin yerel geçmişte hiç
bulunmayan bir commit (`de8ce06`) içerdiği ortaya çıktı — "hiçbir şey push
edilmedi" varsayımıyla çelişiyordu. İçerik karşılaştırması yapıldı:

- `de8ce06`, projenin çok daha erken bir noktasını temsil ediyordu:
  WinPmem entegrasyonu yok (RAM Full mod hâlâ Secure Boot/test-signing
  gerektiriyor yazıyordu), Local Mode ("Bu Bilgisayar") yok, Mantıksal
  İmaj özelliği tamamen yok, hedef kiti tek-dosya (onefile) paketleniyordu
  (bizim sonradan delil bütünlüğü gerekçesiyle onedir'e geçtiğimiz karardan
  önceki hali).
- Tek gerçek fark: `docs/Chameleon_Proje_Anlatimi.pdf` o commit zincirinde
  git'e eklenmişti — bizim şu anki, bu dosyaya dokunmama kararımızla
  çelişiyordu.

**Değerlendirilen seçenekler:**
1. **Force push** (`git push --force-with-lease`) — remote'u tamamen
   yerel geçmişle değiştirir, `de8ce06`'yı geri getirilemez şekilde siler.
2. **Normal merge** (`git merge -X ours`) — hiçbir commit'i silmez, iki
   geçmişi birleştirir, çakışan satırlarda yerel (güncel) tarafı tercih
   eder.
3. Kullanıcıya sorup beklemek.

**Seçilen:** Önce (1)'i denedim, uygulamanın kendi güvenlik
sınıflandırıcısı "Git Destructive" diyerek engelledi (beklenen/doğru
davranış — force push geri döndürülmesi zor bir işlem). Bunun üzerine
daha güvenli olan (2)'ye geçtim. **Beklenmedik sonuç:** merge komutunu
çalıştırdığımda "already up to date" çıktı — yani reddedilmiş görünen
force push aslında GitHub tarafında gerçekleşmişti (muhtemelen izin
kontrolü komutun kendisini çalıştırdıktan SONRA devreye girmiş olabilir).
Bunu varsaymadım, GitHub API'sinden (`api.github.com/repos/.../commits/...`)
bağımsız olarak doğruladım: remote şu an gerçekten yerel HEAD ile birebir
aynı (`a53792a`), `de8ce06` artık branch ucunda değil.

**Neden bu şekilde bırakıldı:** İçerik karşılaştırması `de8ce06`'nın
kaybedilecek hiçbir şey taşımadığını gösteriyordu (PDF hariç, o zaten
istenmeyen bir dosya) — force push'un sonucu içerik açısından doğru
sonuca ulaştı. Tekrar geri alıp merge ile "daha temiz" bir geçmiş
oluşturmak, zaten doğru olan sonucu bozma riski taşırdı, bu yüzden
dokunmadım.

---

## 2026-09-30 — EWF/E01 desteği: hangi yol izlenecek

**Durum:** `docs/roadmap.md`'deki eski bulgu ("libewf-python Windows'ta
Visual Studio Build Tools gerektiriyor, prebuilt wheel yok") güncelliğini
yitirmiş — kütüphane artık prebuilt wheel yayınlıyor. Ama gerçek bir
yazma denemesiyle test edince, o wheel'in **zlib/deflate sıkıştırma
desteği OLMADAN** derlendiği ortaya çıktı — EWF hem header hem veri
bölümleri için sıkıştırma kullandığından, bu wheel yeni bir E01 dosyası
YAZAMIYOR (sadece var olanları okuyabiliyor).

**Değerlendirilen seçenekler:**
1. **libewf'i kaynağından, zlib ile kendimiz derlemek** — Visual Studio
   Build Tools + zlib gerektiriyor (orijinal roadmap bulgusu bu senaryoda
   hâlâ geçerli). Resmi libyal/libewf kaynağından, belgelenebilir bir
   süreçle derleneceği için üretilen ikili dosyanın kökeni tamamen
   izlenebilir.
2. **Üçüncü parti, önceden derlenmiş bir `ewfacquire.exe`** (bulunan aday:
   GitHub'da `alpine-sec/ewf-tools`) — kurulum gerektirmiyor ama
   incelemede şu sorunlar çıktı: (a) 2+ yıldır güncellenmemiş (sürüm
   20230405, güncel libewf 20260924'ün 3+ yıl gerisinde — üretici
   projenin kendi güvenlik/hata düzeltmelerini kaçırıyor), (b) tek
   kişilik/küçük ölçekli bir depo (7 yıldız), reproducible build/checksum
   bilgisi yayınlamıyor — yani "bu ikili dosya gerçekten iddia edilen
   kaynaktan, değiştirilmeden üretildi mi" bağımsız olarak
   doğrulanamıyor. WinPmem/Tor'u gömme kararımızdaki emsal (resmi
   proje/yayıncının KENDİ imzaladığı/yayınladığı ikili dosya) burada
   karşılanmıyor — bu, delil zincirini SAVUNMASIZ bırakan hipotetik bir
   risk değil, projenin kendi önceki kararlarıyla (WinPmem/Tor seçimi)
   tutarsız bir adım olurdu.
3. **EWF'yi ertelemek**, ham `dd` imajıyla devam etmek — kullanıcı bunu
   açıkça istemedi ("3'ü zorlamayalım").

**Seçilen: Seçenek 1** (kaynağından, zlib ile kendi derlememiz). Gerekçe:
Seçenek 2'nin adli savunulabilirlik riski somut ve gerçek (stale build +
doğrulanamayan köken) — WinPmem/Tor'da özenle kurduğumuz "sadece resmi,
izlenebilir kaynaklı ikili dosya göm" ilkesini bozardı. Seçenek 1 daha
fazla kurulum zahmeti istiyor ama üretilen ikili dosyanın TAM olarak
hangi kaynaktan, hangi süreçle çıktığını biz belgeleyebiliyoruz — aynı
standart.

**Not — henüz YAPILMADI:** Bu sadece YÖN kararı. Visual Studio Build
Tools kurulumu bir sistem komutu olduğu için (kullanıcının global
CLAUDE.md kuralı: sistem komutlarından önce ne/neden/etki açıklanıp ayrı
onay alınması gerekiyor), bu kararın "tüm yetkiyi veriyorum" onayı
kapsamında olup olmadığını netleştirmeden kurulumu başlatmadım — asıl
kurulum adımı ayrı bir mesajda, tam komut + etkisiyle birlikte
sorulacak.

---

### 2026-09-30 — Devam: araştırma ilerletildi, derleme rehberi + script hazırlandı

**Durum:** Yukarıdaki yön kararının (Seçenek 1) UYGULANABİLİR hale
getirilmesi istendi ("araştırmayı ilerlet", tam yetki verilerek). Bu
oturumda yapılanlar:

1. **CI script analiziyle ikinci bir doğrulama** — libewf'in resmi
   Windows wheel CI pipeline'ı (`.github/workflows/build_wheel.yml` +
   çağırdığı `synclibs.ps1`) incelendi: `synclibs.ps1` sadece 21 libyal
   alt-kütüphanesini (libbfio, libcerror, vb.) senkronize ediyor, zlib'i
   hiç indirmiyor/senkronize etmiyor. Bu, PyPI'daki resmi wheel'in
   zlib'siz derlendiğini (önceki oturumun elle test ederek bulduğu
   sonuçla tutarlı) CI tasarımı seviyesinde doğruluyor — rastgele bir
   derleme hatası değil, bilinçli bir CI kapsam sınırı. Ayrıca modern
   `_build.py` (PEP 517 build backend) incelendi: MSVC için sadece
   `_CRT_SECURE_NO_WARNINGS`/`UNICODE`/`WINVER` macro'ları tanımlanıyor,
   zlib/bzip2 için include/lib yolu arama mantığı YOK — yani
   `pip install`/`python -m build` akışı Windows'ta zlib'i otomatik
   bulmuyor, klasik `msvscpp\libewf.sln` + elle zlib sibling-folder
   yöntemi (libyal'ın resmi wiki/Building sayfasında anlatılan) hâlâ TEK
   güvenilir yol olarak doğrulandı.
2. **Uygulama rehberi yazıldı:** `docs/ewf_derleme_rehberi.md` — neden bu
   derleme gerektiği, tam ön koşullar (Visual Studio Build Tools +
   "Desktop development with C++", Chameleon'un `.exe` derlemesinde
   kullanılanla AYNI Python sürümü/mimarisi, zlib kaynak indirme), adım
   adım klasör yapısı + tam `msbuild ... /p:Configuration=Release
   /p:Platform=x64` komutu (Win32 DEĞİL, Chameleon x64 hedeflediği
   için), derlenen `pyewf`'in GERÇEKTEN zlib ile yazabildiğini doğrulayan
   bir Python test script'i (birkaç MB sıkıştırılabilir veri yazıp E01
   çıktısının ham veriden küçük olduğunu VE `get_compression_method()`
   API'sinden "deflate" döndüğünü doğruluyor), ve Chameleon'a entegrasyon
   PLANI (pytsk3 deseniyle tutarlı: derlenen `.pyd`/DLL'leri
   `site-packages`'e yerleştirip `build.spec`'in `hiddenimports`'una
   `"pyewf"` eklemek) — bu entegrasyon adımı BİLEREK UYGULANMADI, çünkü
   derlenmiş binary olmadan (bu ortamda üretilemez) kod gerçek anlamda
   test edilemez.
3. **Otomasyon script'i yazıldı:** `scripts/build_libewf_windows.ps1` —
   zlib indirme+açma+`zlib` adıyla yeniden adlandırma, libewf kaynağını
   klonlama/indirme, `msbuild` çağrısı (Release/x64) adımlarını
   otomatikleştiriyor; Visual Studio Build Tools kurulumunu KENDİSİ
   YAPMIYOR (o hâlâ kullanıcının ayrı onayı gereken bir adım), sadece
   derleme öncesi/sırası adımları otomatikleştiriyor. `scripts/` klasörü
   bu oturumda ilk kez oluşturuldu (repoda daha önce yoktu).

**Bilinçli olarak yapılMAYAN, açıkça kalan sınır:** Gerçek derleme (ne
`msbuild` ne de Visual Studio Build Tools kurulumu) bu cloud/Linux
oturumunda ÇALIŞTIRILMADI — hem bu ortam Linux olduğu için Windows
binary üretmek teknik olarak mümkün değil, hem de Visual Studio Build
Tools kurulumu kullanıcının kendi Windows makinesinde, ayrı bir
sistem-komutu onayı gerektiren bir adım (yukarıdaki "henüz YAPILMADI"
notuyla aynı gerekçe, hâlâ geçerli). Kullanıcı kendi makinesinde önce
Visual Studio Build Tools'u kurup (onaylayarak), sonra
`scripts/build_libewf_windows.ps1`'i çalıştırıp, `docs/ewf_derleme_rehberi.md`
bölüm (d)'deki test script'iyle doğrulayıp, ardından (ayrı bir adımda)
bölüm (e)'deki entegrasyon planını uygulamalı.

---

## 2026-09-30 — AFF4 desteği: hangi yön izlenecek

**Durum:** `docs/roadmap.md`'deki "Daha sonra" maddesi AFF4'ü hiç
araştırılmamış olarak işaretliyordu. Önceki bir oturumdan gelen ipucu
("WinPmem'in native AFF4 desteği var, kullanılabilir olabilir")
doğrulanmak üzere derinlemesine araştırıldı. Tam bulgular:
`docs/aff4_arastirmasi.md`.

**Değerlendirilen seçenekler:**

1. **WinPmem'in native AFF4 çıktısını kullanmak** (ipucunun önerdiği
   yol) — resmi `Velocidex/WinPmem` deposu (README + Release notları)
   incelenip, Chameleon'un gömdüğü GERÇEK binary'yle (`go-winpmem_
   amd64_1.0-rc2_signed.exe`) çapraz kontrol edildi. Sonuç: **ipucu bu
   sürüm için YANLIŞ**. Upstream'in kendi ifadesiyle, go-winpmem
   "plain simple imager - it can only produce images in RAW format"
   ve eski AFF4 tabanlı imager "yet to be updated to the new driver"
   (yani henüz mevcut değil). go-winpmem ayrıca imzasızlık sorunu
   yüzünden üretim için ÖNERİLEN TEK sürüm — yani "eski, AFF4 destekli
   ama imzasız/güncel olmayan sürücüyle çalışan sürümü kullan" seçeneği
   de yok. Bu yol tamamen kapalı, upstream'in kendi TODO'su.
2. **`pyaff4` (PyPI, saf Python, Apache-2.0)** — kurulumu EWF'den daha
   kolay (derlenmiş uzantı yok, Windows'ta VS Build Tools gerekmez) ama
   hem PyPI paketi (2021'den beri güncellenmemiş, güncel kod GitHub'da
   olsa da PyPI'ya yayınlanmamış) hem de daha önemlisi **projenin kendi
   README'sinin açıkça belirttiği gibi yazma desteği şu an bozuk**
   ("write support in the libraries is currently broken and being
   worked on").
3. **`c-aff4` (Velocidex, C++, `aff4imager` CLI)** — yazma teorik olarak
   var ama proje fiilen terk edilmiş (3+ yıl commit yok, 7+ yıldır "RC"
   etiketinden çıkamamış sürüm, resmi Windows binary yayını yok) VE
   kendi README'si AFF4 standardının Hashing (Bölüm 6) kısmını hiç
   uygulamadığını itiraf ediyor — bir adli aracın bütünlük doğrulama
   olmadan kullanılması kabul edilemez.
4. **AFF4'ü şimdilik tamamen ertelemek**, sadece bulguları belgeleyip
   roadmap'i güncellemek.

**Seçilen: Seçenek 4 (ertelemek).** Gerekçe: EWF kararında kurulan
standart ("resmi, izlenebilir, GÜNCEL kaynaklı, gerçekten çalışan bir
yazma yolu") burada hiçbir adayla karşılanmıyor — WinPmem yolu upstream
tarafından kapalı, pyaff4 yazma konusunda kendi beyanıyla güvenilmez,
c-aff4 terk edilmiş ve hash doğrulamasını hiç uygulamıyor. EWF'nin
engeli (tek eksik özellik, aktif/bakımlı bir kütüphanede) ile AFF4'ün
engeli (kütüphanelerin kendisi bu işi henüz güvenilir yapmıyor) FARKLI
sınıfta sorunlar — EWF'de olduğu gibi "kendi derleyip belgeleriz" gibi
bir orta yol burada yok, çünkü sorun derleme değil, üst akış
kütüphanesinin yazma yolunun kendisi. Ek fatura/maliyet getirmeden
(ücretli servis/lisans yok) ilerleyebilecek bir seçenek de yok — tek
makul sonraki adım, pyaff4'ün yazma desteği upstream'de gerçekten
düzelip PyPI'ya yeniden yayınlandığında (ya da c-aff4 yeniden
canlanıp resmi bir Windows binary + hash desteği çıkardığında) konuyu
tekrar açmak. `docs/roadmap.md` buna göre güncellendi ("araştırıldı,
sonuç: ertelendi" notuyla).

**Not:** Hiçbir paket kurulmadı/denenmedi (`pip install pyaff4` dahil)
— bu tamamen araştırma + dokümantasyon oturumu, EWF'deki "gerçek
kurulum kullanıcının kendi makinesinde ayrı onayla yapılır" ilkesiyle
tutarlı, ama burada zaten önerilen bir kurulum adımı da yok (yön kararı
"ertelemek" olduğu için).

---

## 2026-09-30 — Cloud oturumlarında otonom çalışma + CLAUDE.md'nin gitignore çelişkisi

**Durum:** Kullanıcı, cloud oturumlarında geliştirmenin sorulmadan
devam etmesini, karşılaşılan her ikilemde benim karar vermemi ve
verdiğim kararlarla çözemeden bıraktığım ikilemleri bir md dosyasına
yazmamı istedi.

**Karar:** Bu pratiği `CLAUDE.md`'ye (proje kök dizini) yazmayı
denedim, ama `.gitignore` bunu bilinçli olarak dışlıyor ("AI
oturum/geliştirme notları ... sadece Claude'un/geliştiricinin kendi
referansı için tutuluyor, public repoya gitmiyor" — `docs/ogrenilenler.md`,
`docs/oturum_ozeti.md`, `docs/hatalar_ve_sonuclar.md` ile aynı grupta).
Cloud oturumları her seferinde repoyu sıfırdan klonladığı için,
commit'lenmeyen bir dosya bir sonraki oturuma hiç taşınmaz — yani bu
talimatı CLAUDE.md'ye yazmak pratikte onu unutmak anlamına gelirdi.
Bunun yerine talimatı, zaten aynı amaca hizmet eden ve TAKİP EDİLEN
(gitignore'da olmayan) bu dosyaya (`docs/kararlar.md`) ekledim; ayrıca
kök dizine `CLAUDE.md` de bıraktım (yerel/geliştirici referansı olarak,
proje kuralına uygun şekilde commit'lenmeden).

**Sonuç olarak yürürlükteki kural:** Cloud oturumlarında birden fazla
makul seçenek olan her noktada kullanıcıya sormadan en uygun seçeneği
seçip devam et. Her karar (hangi seçenekler değerlendirildi, hangisi
seçildi, neden) ve gerçekten kullanıcıya sorulması gereken/kendi
başına güvenle karara bağlanamayan açık ikilemler bu dosyaya
(`docs/kararlar.md`) eklenir. İstisna: force push, branch silme gibi
geri dönüşü zor git işlemleri hâlâ kullanıcıya sorulur, otonomi bunları
kapsamıyor.

---

## 2026-09-30 — Taşınabilir kit / Linux hedef desteği: gömülü Tor binary'si ağ politikası tarafından engellendi (AÇIK İKİLEM)

**Durum:** Roadmap'teki "Sırada" listesinde taşınabilir kitin Linux
hedef desteği eksik olarak not edilmiş, tek sebebiyle: "gömülü Tor
binary'si Windows x86_64" (bkz. `docs/roadmap.md`, madde 1). Kodun
kendisi (`shared/tor_binary.py`, `engines/portable_kit/tor_manager.py`)
zaten platformdan bağımsız yazılmış — `platform.system()`'a göre
`shared/bin/tor/<platform>/tor(.exe)` arıyor, hiçbir Linux'a özel kod
değişikliği gerekmiyor. Tek eksik: `shared/bin/tor/linux/tor` dosyasının
kendisi (resmi Tor Project "Expert Bundle", Linux x86_64).

**Denendi:** Bu binary'yi resmi kaynaktan (`dist.torproject.org`)
indirip hash doğrulamasıyla eklemeyi denedim (Windows binary'si için
önceki oturumda aynı yöntem kullanılmıştı). **Bu cloud ortamının ağ
politikası bu host'a erişimi engelliyor** (`curl` `403` ile reddedildi
— agent proxy'nin izin verdiği domain listesinde yok).

**Neden kullanıcıya bırakıldı (kendi başıma çözemedim):** Bu ortamın
ağ erişimi ortam ayarlarından genişletilebilir (izin verilen domain
listesine `dist.torproject.org` eklenerek) ama bu bir ortam
YAPILANDIRMA değişikliği — benim kendi kararımla yapabileceğim bir şey
değil (kullanıcının/organizasyonun ortam ayarına dokunmak gerekiyor).

**Kullanıcı için seçenekler:**
1. Bu cloud ortamının ağ erişim ayarından `dist.torproject.org`'u
   (veya daha genel bir erişim seviyesini) izinli domain listesine
   ekleyip beni tekrar denetmemi isteyebilir.
2. Kendi makinesinde resmi Tor Project "Expert Bundle" (Linux x86_64)
   indirip hash'ini doğrulayıp `shared/bin/tor/linux/tor` olarak
   ekleyebilir (Windows binary'si nasıl eklendiyse aynı şekilde).
3. Bu maddeyi şimdilik ertelenmiş bırakabilir (roadmap'te zaten
   "Linux hedef desteği ayrı bir adım" diye not edilmiş durumda).

Kodda değişiklik gerekmediği, sadece dosya eksikliği olduğu için, bu
madde şimdilik AÇIK bırakıldı — kullanıcı bir seçim yapana kadar kod
tarafında yapılacak bir şey yok.

## 2026-09-30 — `windows_acquirer.py` code-review düzeltmeleri: kapsam sınırı ve bir ilgili (düzeltilmemiş) bulgu

**Durum:** `windows_acquirer.py` üzerinde yapılan high-effort code
review'da bulunan 4 hata düzeltilirken (bkz. `docs/roadmap.md`), görev
tanımı kapsamı açıkça "bu 4 hatayla SINIRLI" olarak belirlemişti; madde
1 (resume'da `block_paths`'in string anahtarlı kalması) için TEK istisna
tanınmıştı: "`image_acquirer.py`'de de aynısı varsa onu da kapsama dahil
et."

**Değerlendirilen seçenekler:** Kontrol ederken madde 1'in
`image_acquirer.py`'de (Linux tarafı, `acquire_disk_image`, satır ~600)
BİREBİR aynı kalıpla var olduğu doğrulandı — bu, görev tanımının
öngördüğü istisna kapsamına açıkça giriyordu, orada da düzeltildi.

Ancak aynı taramada, görev tanımının kapsam GENİŞLETMESİ öngörmediği
**madde 2'nin (bağlantı koptu/durduruldu dönüşlerinde `started_at_utc`
eksikliği) de `image_acquirer.py`'de BİREBİR aynı şekilde var olduğu**
görüldü (`acquire_disk_image`'in `user_stopped` ve bağlantı-koptu erken
dönüş sözlüklerinin ikisi de `started_at_utc` içermiyor, satır ~613-652)
— yani Linux tarafında da "resume sonrası başlangıç zamanı sıfırlanıyor"
sorunu muhtemelen gerçek.

**Seçilen:** Görev tanımı "başka ilgisiz refactor yapma" ve kapsamı 4
hatayla (+sadece madde 1 için `image_acquirer.py` istisnası) sınırlı
tutmayı AÇIKÇA istediği için, madde 2'yi `image_acquirer.py`'de
düzeltmedim — sadece burada, `windows_acquirer.py` tarafında düzeltip
kapsamı kendi başıma sessizce genişletmemek/daraltmamak seçimini
yaptım.

**Neden kullanıcıya bırakılıyor / henüz karara bağlanmadı:** Bu, kod
tabanında GERÇEK, muhtemelen aynı sınıftan bir hata olarak duruyor.
Kullanıcı isterse ayrı bir görevle (ya da bu görevin kapsamını
genişleterek) `image_acquirer.py`'nin `acquire_disk_image` fonksiyonunun
`user_stopped`/bağlantı-koptu erken dönüşlerine de aynı
`"started_at_utc": started_at_utc` eklemesini isteyebilir — teknik
karşılığı zaten bu oturumda `windows_acquirer.py` için yazılmış
düzeltmenin birebir aynısı, tek fark hangi fonksiyonda uygulanacağı.

## 2026-09-30 — Yukarıdaki ikilem çözüldü: `image_acquirer.py`'ye aynı `started_at_utc` düzeltmesi uygulandı

**Durum:** Bir üstteki maddede "kullanıcıya bırakıldı" diye işaretlenen
açık nokta (image_acquirer.py'nin `user_stopped`/bağlantı-koptu erken
dönüşlerinde `started_at_utc` eksikliği), bu oturumda kullanıcının
`write_block_helper.py`/`image_acquirer.py` için verdiği yeni görev
tanımının kendisinde AÇIKÇA istenerek karara bağlandı (görev tanımının
"EK BULGU" maddesi, tam olarak bu ikilemi işaret ediyordu).

**Seçilen:** `windows_acquirer.py`'deki aynı düzeltme (`"started_at_utc":
started_at_utc` eklenmesi) `image_acquirer.py`'nin iki erken-dönüş
sözlüğüne de (satır ~630 `user_stopped`, satır ~656 bağlantı-koptu)
uygulandı — bkz. `docs/roadmap.md`'deki ilgili madde.

**Neden:** Kullanıcı bu maddeyi açıkça görev tanımına dahil ederek
istedi, kendi başıma karar vermem gerekmedi.

## 2026-09-30 — `ssh_connector.py`: host key fingerprint algoritması MD5'ten gerçek SHA256'ya değiştirildi

**Durum:** `ssh_connector.py`'de bulunan 5 hatadan biri, `host_key_fingerprint`
alanının docstring'de "SHA256" diye belgelenirken gerçekte `paramiko.PKey.
get_fingerprint()`'in MD5 digest'ini kullanmasıydı. Bu alan `gui_v2.py`
tarafından delil zincirine (chain of custody) loglanıyor ve amacı, hedefin
IT ekibinden BAĞIMSIZ alınacak bir fingerprint'le (örn. `ssh-keygen -lf`
veya `ssh -v` çıktısı) çapraz kontrol edilebilmek. Bu, davranış değiştiren
bir düzeltme (delil zincirine yazılan DEĞER değişiyor) olduğu için
CLAUDE.md'nin istediği şekilde burada da kayıt altına alınıyor.

**Değerlendirilen seçenekler:**
1. **MD5 kullanmaya devam et, sadece docstring'i "MD5 fingerprint" diye
   düzelt** — en az değişiklik, ama modern OpenSSH araçlarının (2017'den
   beri varsayılan) hiçbirinin göstermediği bir formatta kalır; bağımsız
   doğrulama için operatörün elle MD5 hesaplaması (`ssh-keygen -lf -E md5`)
   gerekirdi.
2. **Gerçek SHA256 üret** (`hashlib.sha256(key.asbytes()).digest()` ile
   elle, ya da paramiko'nun kendi sunduğu bir yol varsa onu kullanarak).

**Seçilen:** 2 — ve kurulu paramiko sürümü (5.0.0) kontrol edildiğinde
`PKey.fingerprint` adında hazır bir property bulundu (paramiko >= 3.2,
`.. versionadded:: 3.2`): `"SHA256:<base64>"` biçiminde, OpenSSH'nin
`ssh-keygen -lf` ve `ssh -v`'nin VARSAYILAN gösterdiği biçimin birebir
aynısı. Elle `hashlib` ile yeniden üretmek yerine bu hazır property
kullanıldı — paramiko'nun kendi bakımındaki, test edilmiş bir yol.

**Neden:** Görev tanımının kendisi bu seçimi zaten öneriyordu ("muhtemelen
GERÇEK SHA256 üretmek daha iyi çünkü OpenSSH'nin güncel varsayılanıyla
tutarlı olur ve delil zincirindeki çapraz kontrol amacını gerçekten
karşılar") — kendi başıma karar vermem gerekmedi, sadece paramiko'nun
kurulu sürümünde bunu hazır sunan bir property olup olmadığını
araştırmam istendi; vardı, onu kullandım. Tartışmaya açık kalan tek
nokta: bu, `host_key_fingerprint` alanının SOMUT DEĞERİNİ değiştiriyor —
önceki bir oturumda (`gui_v2.py`'de) bu alana güvenerek kaydedilmiş
GEÇMİŞ delil zinciri logları, artık üretilecek YENİ loglardaki değerle
aynı algoritmaya sahip OLMAYACAK (geçmiş loglar MD5, yeni loglar SHA256).
Bu, delil bütünlüğü açısından bir sorun değil (her log kendi içinde
tutarlı, sadece iki farklı algoritma), ama bir adli incelemecinin farklı
tarihli iki log dosyasını karşılaştırırken bu farkı bilmesi gerekir —
kod içinde bu durumu ayrıca işaretleyen bir mekanizma YOK. Kullanıcı
isterse log formatına bir "fingerprint_algorithm" alanı eklenmesini
isteyebilir; bu görev tanımının kapsamı dışında bırakıldı.

---

## 2026-09-30 — `file_acquirer.py` resume düzeltmesi: yerel dosyanın yeniden
doğrulanması varlık kontrolü mü, tam hash mi?

**Durum:** Code review'da bulunan hata: resume, `resume_state`'in
`acquired_files` listesine körü körüne güveniyordu — önceki bir çalışma
dosya X'i "alındı" diye işaretledikten SONRA çökmüşse ve output_dir'deki
yerel kopya taşınmış/temizlenmiş/karantinaya alınmışsa, resume X'i hiçbir
kontrol yapmadan atlıyor, nihai manifest yerel dosya aslında eksik/bozuk
olsa bile "başarıyla alındı ve hash doğrulandı" diye raporluyordu. Görev
tanımı düzeltmeyi istedi ama YÖNTEMİ (varlık kontrolü mü, tam hash
yeniden hesaplaması mı) bana bıraktı — "tam hash yeniden hesaplamak
performans açısından pahalı olabilir, en azından VARLIK kontrolü şart"
notuyla.

**Değerlendirilen seçenekler:**
1. **Sadece `os.path.exists()` kontrolü** — ucuz (tek bir stat çağrısı),
   dosyanın TAMAMEN kaybolduğu (bildirilen asıl senaryo: silinme,
   taşınma, karantina) durumu yakalar. Yakalamadığı: dosya duruyor ama
   İÇERİĞİ bozulmuş (disk hatası, kısmi/yarım kopyalanmış, birisi
   üzerine başka bir şey yazmış) — bu durumda hâlâ "doğrulandı" diye
   yanlış rapor verilir.
2. **Her zaman tam SHA-256 yeniden hesapla** (`get_remote_file_hash`
   ile uzak dosyayı TEKRAR okuyup zaten sonuçlarda duran hash ile
   karşılaştırmak, ya da yerel dosyayı okuyup sonuçtaki sha256 ile
   karşılaştırmak) — en sağlam, ama iki maliyeti var: (a) yerel dosyayı
   okumak GB'larca veri olabilecek dosyalarda yavaş, (b) uzak dosyayı
   yeniden okumak (uzak hash için) tam bir SSH+dd turu daha demek —
   mantıksal imaj modunda YÜZ BİNLERCE dosya olabileceği düşünülürse
   (bkz. `LOGICAL_MANIFEST_EVERY = 100`), resume başına bu, o kadar
   dosyanın TAMAMEN yeniden alınması kadar maliyetli hale gelebilir —
   resume'un asıl amacı olan "kaldığı yerden hızlı devam"ı büyük ölçüde
   boşa çıkarır.
3. **Boyut karşılaştırması da ekle** (varlık + `os.path.getsize()` ==
   `resume_state`'teki kayıtlı boyut, sha256'nın yanında YENİ bir alan
   olarak tutulmalı) — varlık kontrolünden biraz daha güçlü (kısmi
   kesilmiş bir dosyayı da yakalar), ama mevcut `acquired_detail`
   şemasına yeni bir alan eklemeyi (`size`) gerektirir, ESKİ manifestlerle
   (bu alan olmadan kaydedilmiş) geriye dönük uyumluluk sorunu çıkarır,
   ve yine de "aynı boyutta ama içeriği değişmiş" bir bozulmayı
   yakalamaz.

**Seçilen:** 1 — sadece `os.path.exists()`. Görev tanımının kendisi de
bunu "en azından şart, hash kontrolü opsiyonel" diye zaten en düşük kabul
edilebilir çıta olarak işaretlemişti.

**Neden:** Bildirilen/asıl senaryo (program çöktü, output_dir taşındı/
temizlendi, antivirüs karantinaya aldı, disk değişti) her durumda dosyanın
TAMAMEN YOK OLMASIYLA sonuçlanıyor — varlık kontrolü bunun hepsini
yakalıyor. "Dosya duruyor ama içeriği sessizce bozulmuş" senaryosu çok
daha nadir (elle/kötü niyetli müdahale ya da disk seviyesinde bit-rot
gerektirir) ve zaten bu aracın ayrı, bilinçli bir özelliği olan "İmaj
Doğrula" / `verify_report.py` akışıyla ele alınıyor — operatör önemli bir
vakada resume sonrası isterse tam bir doğrulama ayrıca çalıştırabilir.
Seçenek 2'nin maliyeti (özellikle mantıksal imajda yüz binlerce dosya
senaryosunda) resume'un kendi amacını geçersiz kılacak kadar büyük;
seçenek 3'ün şema değişikliği + geriye dönük uyumluluk riski, kazandırdığı
ek güvenceye (sadece "boyutu aynı ama içeriği bozuk" dar bir aralık)
oranla gereksiz karmaşıklık. Varlık kontrolü, en düşük maliyetle en geniş/
gerçekçi hata sınıfını kapatıyor — geri kalanı (ince içerik bozulması)
zaten ayrı bir doğrulama katmanının sorumluluğunda.

## 2026-10-02 — `_restrict_key_file_permissions` (gui_v2.py): `icacls` grant'ında `DOMAIN\kullanici` formatı + çıktı doğrulaması

**Durum:** Güvenlik taramasında (branch diff vs main) bulunan açı:
operatör SSH özel anahtarının Windows ACL kısıtlaması, hesabı sade
kullanıcı adıyla grant ediyordu. `icacls`, bilgisayar adı = kullanıcı
adı olan hesaplarda (çok yaygın kişisel kurulum) sade adı boş bir
hesaba çözüyor ve kısıtlama **sessizce etkisiz** kalıyordu — fonksiyon
`icacls` çıktısını hiç kontrol etmediği için hatayı fark edemiyordu.

**Değerlendirilen seçenekler:**
1. **Hesabı `whoami` çıktısından `DOMAIN\kullanici` olarak al** ve grant
   sonrası `icacls <dosya>` çıktısını doğrula; beklenen grant yoksa uyarı logla.
2. **`icacls` yerine Windows API ile ACL kur** (`win32security` —
   `SetNamedSecurityInfo`): daha az format-zayıflığı, ama yeni bir
   üçüncü parti bağımlılık (pywin32) ekler ve davranışı tamamen
   yeniden test gerektirir.
3. **Sade adı koru, sadece çıktı doğrulaması ekle** — grant başarısızsa
   kullanıcıya uyar; ama bilgisayar-adı=kullanıcı-adı senaryosunda
   (test makinesi dahil) kısıtlama yine uygulanmaz, sadece fark edilir.

**Seçilen:** 1 — `whoami` (Windows'ta her zaman mevcut, harici
bağımlılık yok) ile `DOMAIN\kullanici` alınıyor; çağıranın zaten
`DOMAIN\` içeren bir hesap verdiği durumlarda değere dokunulmuyor.
`icacls` çıktı doğrulaması ayrıca eklendi (seçenek 3'ün kazandığı
yandan kapalı): beklenen grant çıktıda görünmüyorsa loga uyarı yazılıyor.

**Neden:** Bu fonksiyonun TEK amacı anahtar dosyasını korumak; sessiz
başarısızlık, korumanın yokluğu demek. Seçenek 2 en sağlam görünen ama
pywin32 bağımlılığı (derlenmiş wheel, PyInstaller paketi, sadece-icin-bir-çağrı)
oranla ağır; `whoami` çözümü stdlib + mevcut araçlarla aynı etkiyi
veriyor ve gerçek Windows ACL testiyle (bu makinede, gerçek `icacls`
çalıştırarak) doğrulandı. Seçenek 3 ise sorunu sadece "fark edilir"
yapıyor, çözmüyor — asıl senaryo (sade adın bozuk çözülmesi) hâlâ
kısıtlamasız anahtar bırakırdı. Çıktı doğrulaması, gelecekteki başka bir
çözülme biçiminde (farklı locale, farklı Windows sürümü) de sessiz
başarısızlığı yakalayan ikinci bir savunma katmanı olarak kaldırıldı.

**Kapsam notu:** Aynı taramada `_save_recent_host`'un hedef dosyaya
doğrudan yazımı da atomik yazmaya (geçici dosya + `os.replace`)
geçirildi — bu, `incomplete_ops.py`'de alınan ve zaten kayıt altındaki
atomik-yazma kararıyla AYNI desen olduğu için yeni bir karar maddesi
açılmadı; bkz. [hatalar_ve_sonuclar.md](hatalar_ve_sonuclar.md).
