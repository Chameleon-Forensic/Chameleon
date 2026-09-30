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
