# AFF4 desteği araştırması

> Bu belge, `docs/roadmap.md`'nin "Daha sonra, öncelik sırası netleşmedi"
> bölümündeki "Gerçek EWF/E01 ve AFF4 desteği" maddesinin AFF4 kısmını
> araştırıyor (EWF kısmı için bkz. `docs/ewf_derleme_rehberi.md` +
> `docs/kararlar.md`). Sonuç: `docs/kararlar.md`'ye eklenen ilgili karar
> kaydında özetlendiği gibi **AFF4 entegrasyonu şimdilik ERTELENDİ** — bu
> belge o kararın dayandığı bulguları tutuyor.

## (a) AFF4 nedir

AFF4 (Advanced Forensics File Format 4), Simson Garfinkel/Michael
Cohen/Bradley Schatz tarafından tasarlanan, açık bir standart olarak
yayınlanmış (`github.com/aff4/Standard`, v1.0) adli imaj konteyner
formatıdır. Google içinde (Rekall projesi kapsamında) doğdu, şu an
Velocidex Innovations ve Schatz Forensic tarafından sürdürülüyor.

Öne çıkan özellikleri:

- **Konteyner ZIP tabanlı** — bir AFF4 hacmi, içinde ham veri
  segmentlerini (deflate ya da snappy ile sıkıştırılmış) VE RDF/Turtle
  formatında zengin metadata'yı (vaka bilgisi, hash'ler, kaynak bilgisi)
  birlikte taşıyan bir ZIP arşivi. Bu, EWF'nin kendi özel ikili header
  formatına kıyasla daha "standart" bir konteyner (herhangi bir zip
  aracıyla incelenebilir) ama EWF kadar sıkı/kompakt bir header şeması
  değil.
- **Parçalı (striped/segmented) hacim desteği** var — büyük imajları
  birden fazla dosyaya bölebiliyor, EWF'nin `.001`/`.002` segmentasyonuna
  benzer bir kullanım senaryosunu karşılıyor.
- **Açık standart** olması EWF'ye göre avantaj — EWF de facto Guidance
  Software/OpenText'in EnCase formatından türedi, libewf üzerinden açık
  kaynaklı bir okuma/yazma yolu var ama format spesifikasyonu AFF4 kadar
  resmi/bağımsız bir standart kurulunda değil.
- **Adli camiada kabul**: EWF/E01, ticari/adli araçlarda (EnCase, FTK,
  X-Ways, Autopsy, çoğu Avrupa/ABD mahkeme sunumlarında) hâlâ fiili
  standart — "E01 dosyası" ifadesi neredeyse "adli disk imajı" ile eş
  anlamlı kullanılıyor. AFF4 daha çok DFIR açık kaynak ekosisteminde
  (Velociraptor, GRR, Rekall/WinPmem'in eski AFF4 imager'ı, libtsk'in
  okuyucusu) yaygın; ticari inceleme araçlarının E01 kadar evrensel AFF4
  desteği yok (bazıları hiç desteklemiyor, bazıları sadece okuma
  desteği sunuyor). Yani "hangisi daha çok kabul görüyor" sorusunun
  cevabı EWF lehine — bu, Chameleon'un çıktısının üçüncü taraf
  araçlarda/mahkemede sorunsuz açılabilmesi açısından EWF'yi öncelikli
  kılan bir faktör.

Kaynaklar: https://www.aff4.org/, https://github.com/aff4/Standard,
https://github.com/aff4/ReferenceImages

## (b) WinPmem'in AFF4 desteği — önceki oturumun ipucu DOĞRULANAMADI

Önceki oturumdan gelen ipucu ("WinPmem'in native AFF4 desteği var,
kullanılabilir olabilir") araştırıldı ve **Chameleon'un gömdüğü sürüm
için YANLIŞ/güncelliğini yitirmiş** olduğu tespit edildi.

Gerçek durum (resmi `Velocidex/WinPmem` deposu, README + Releases
sayfası, `src/engines/ram_engine/winpmem/` altındaki gömülü binary'nin
kendisiyle çapraz kontrol edildi):

- Chameleon şu an `go-winpmem_amd64_1.0-rc2_signed.exe`'yi gömüyor
  (bkz. `src/engines/ram_engine/ram_gui.py`, `WINPMEM_PATH`, komut:
  `[WINPMEM_PATH, "acquire", out_path]`). Bu, WinPmem'in **Go ile
  yeniden yazılmış, yeni ("Golang userspace") imager**'ı — eski
  sürücüyü kullanan, imzasız yeni sürücüler yerine "eski sürücüler +
  yeni Go kullanıcı-alanı programı" kombinasyonuyla üretim için
  **TEK imzalı/kullanılabilir** sürüm (resmi Release notu: "For
  production use please use the `go-winpmem_amd64_1.0-rc2_signed.exe`
  binary... this remains the only version available for production
  use" — imzasızlık sorunu nedeniyle).
- Resmi README'de açıkça yazıyor: *"The mini in the binary name refers
  to this imager being a plain simple imager - it can only produce
  images in RAW format. In the past we release a WinPmem imager based
  on AFF4 but that one is yet to be updated to the new driver. Please
  let us know if you need the AFF4 based imager."*
- Resmi Release notu (v4.0 RC2, aynı zamanda go-winpmem'in ilk
  yayınlandığı sürüm) da aynısını doğruluyor: *"This imager is very
  simple - it can only make raw images. The AFF4 based imager may be
  back in the future but for now we can produce RAW images."* ve
  ayrıca *"There is now also an experimental Go userspace imager which
  supports 3 methods of compression (Snappy, S2 and Gzip)"* — yani
  go-winpmem sıkıştırma destekliyor (RAW akışını Snappy/S2/Gzip ile
  sıkıştırabiliyor) ama **AFF4 konteyner formatını DEĞİL**.

**Sonuç:** İpucunun kaynağı büyük olasılıkla eski (2020 öncesi, klasik
C++ tabanlı) WinPmem'in dokümantasyonu (`winpmem.velocidex.com/docs/usage`,
çeşitli üçüncü parti DFIR eğitim siteleri) — o sürümde AFF4
varsayılan/desteklenen çıktı formatıydı. Ama **Chameleon'un gömdüğü,
imzalı, üretimde kullanılabilir TEK sürüm olan go-winpmem 1.0-rc2 AFF4
YAZAMIYOR** — sadece RAW (+ isteğe bağlı Snappy/S2/Gzip sıkıştırma).
Eski AFF4 tabanlı imager'ı yeni sürücüyle çalışacak şekilde güncellemek
upstream'in kendi TODO listesinde ("yet to be updated... let us know if
you need it") — yani bu, Chameleon'un çözebileceği bir entegrasyon
sorunu değil, upstream'de henüz var olmayan bir özellik.

**Pratik sonuç:** RAM tarafında AFF4, WinPmem üzerinden "bedava" gelmez
— go-winpmem'in çıktısı hâlâ RAW `.img` (mevcut Chameleon davranışı
zaten bu, değişiklik gerekmiyor). AFF4 konteynerine sarmak istenirse,
RAW çıktıyı SONRADAN bir AFF4 kütüphanesiyle (aşağıdaki (c)) paketlemek
gerekir — WinPmem'in kendisi bunu yapmıyor.

Kaynaklar:
https://github.com/Velocidex/WinPmem (README, "How to use" bölümü),
https://github.com/Velocidex/WinPmem/releases/ (v4.0 RC2 notları)

## (c) Disk imajlama için AFF4 yazma — Python kütüphane seçenekleri

İki aday incelendi, ikisi de Apache-2.0 lisanslı (ticari/kapalı kaynak
kullanım için sorun yok, WinPmem/Tor'daki lisans emsaliyle tutarlı) ama
ikisinin de ciddi pratik engelleri var:

### 1. `pyaff4` (PyPI, `github.com/aff4/pyaff4`)

- **Kurulum kolaylığı EWF'den İYİ**: PyPI'daki wheel `py3-none-any` —
  saf Python, derlenmiş bir C uzantısı YOK. `requirements.txt`'teki tüm
  zorunlu bağımlılıklar (`rdflib`, `pyyaml`, `pynacl`, `pycryptodome`,
  `cryptography`, `lz4`, vb.) Windows'ta önceden derlenmiş wheel'lerle
  geliyor — yani libewf'in aksine Visual Studio Build Tools/zlib
  derleme zahmeti YOK. Bu, EWF'yle "aynı sınıfta bir engel" DEĞİL, daha
  kolay bir kurulum.
- **AMA — yazma desteği upstream'in kendi ifadesiyle bozuk.** Hem PyPI
  paket sayfası hem GitHub deposunun (2026'daki en güncel) README'si
  aynı cümleyi taşıyor: *"The write support in the libraries is
  currently broken and being worked on."* Bu, "bizim ortamımızda test
  edemedik" değil, **projenin kendi beyanı** — yani gerçek bir disk
  imajı yazma denemesi güvenilir sonuç vermeyebilir, upstream bunu
  bilinen/açık bir eksiklik olarak listeliyor.
- **PyPI paketi güncelliğini yitirmiş**: PyPI'daki son sürüm 0.34,
  11 Ağustos 2021 tarihli (5+ yıl önce) — GitHub deposunun kendisi
  aktif (son commit 6 Ağustos 2026, "geçen ay") olsa da, o
  güncellemeler PyPI'ya YENİDEN YAYINLANMAMIŞ. `pip install pyaff4`
  hâlâ 2021'in donmuş halini kurar; güncel kodu almak için PyPI değil
  GitHub kaynağından (`pip install git+https://github.com/aff4/pyaff4`)
  kurmak gerekir — bu da EWF kararında reddedilen "üçüncü parti,
  doğrulanabilirliği daha zayıf kaynak" sınıfına yaklaşan bir risk
  (resmi proje olsa da, PyPI'nin kendi imzalı/sürümlenmiş yayın
  sürecinin DIŞINA çıkmak demek).
- Ek risk: `requirements.txt` `rdflib==4.2.2` gibi çok eski, sabit bir
  sürüm pin'liyor (güncel rdflib 6.x/7.x) — modern bir Python 3.12
  venv'inde diğer bağımlılıklarla (Chameleon zaten `cryptography` gibi
  paketler kullanıyor) çakışma ihtimali var, denenmeden bilinemez.

Kaynak: https://pypi.org/project/pyaff4/, https://github.com/aff4/pyaff4
(README + `setup.py`/`requirements.txt` doğrudan okundu)

### 2. `c-aff4` (`github.com/Velocidex/c-aff4`, C++ kütüphane + `aff4imager` CLI)

- Yazma dahil (ZipFile + Directory tarzı hacimler, deflate/snappy)
  gerçek bir "canonical aff4imager" standalone aracı sunuyor — kağıt
  üzerinde libewf'e en yakın model (kendi derlenen bir CLI aracı).
- **Ama fiilen terk edilmiş**: son commit 24 Mart 2023 (3+ yıl önce),
  son sürüm etiketi **"3.3 RC3"**, 20 Ağustos 2019 — yani proje 7+ yıldır
  bir "RC" (release candidate) etiketinden çıkamamış, resmi/imzalı bir
  Windows binary yayını YOK (kaynak GNU autoconf/Makefile tabanlı bir
  build sistemi, Windows için ayrı bir "README.windows" var ama MSYS2/
  mingw tabanlı, libewf'in MSVC `.sln` yoluna kıyasla daha az
  belgelenmiş/test edilmiş bir yol).
- **Kendi README'sinin itiraf ettiği ciddi eksik**: "What is not yet
  supported: This implementation currently does not implement Section 6.
  Hashing of the standard. This includes verifying or generating linear
  or block hashes." — yani AFF4 standardının hash doğrulama bölümünü
  DESTEKLEMİYOR. Bir adli imajlama aracı için bütünlük/hash doğrulama
  Chameleon'un tüm mimarisinin (chain-of-custody, `report.json`'daki
  SHA-256 alanı) merkezinde — bu eksiklik tek başına diskalifiye edici.
- EWF kararındaki `ewf-tools` (alpine-sec) reddi ile AYNI gerekçe
  sınıfı burada DAHA GÜÇLÜ şekilde geçerli: orada "2 yıl güncellenmemiş,
  küçük depo" denilmişti; burada 3+ yıl güncellenmemiş, hiçbir zaman
  stabil sürüme ulaşmamış VE standardın hash bölümünü hiç
  uygulamayan bir kütüphane var.

Kaynak: https://github.com/Velocidex/c-aff4 (README + dosya listesi/
son commit tarihleri doğrudan okundu)

## (d) EWF ile karşılaştırma — derleme/kurulum zorluğu

| | EWF (libewf/pyewf) | AFF4 (pyaff4) | AFF4 (c-aff4) |
|---|---|---|---|
| Derleme gerekiyor mu | Evet (MSVC + zlib, ama TEK, belgelenmiş eksik: zlib) | Hayır (saf Python wheel) | Evet (autoconf/MSYS2, az belgelenmiş Windows yolu) |
| Yazma çalışıyor mu | **Evet** (kendi derlememizle, doğrulama script'i hazır) | **Upstream'in kendi beyanıyla BOZUK** | Teorik olarak evet ama binary yok, test edilemez |
| Bakım/güncellik | Aktif (güncel sürüm 2026) | Depo aktif ama PyPI paketi 2021'de donmuş | 3+ yıl commit yok, hiç stabil sürüm yok |
| Hash doğrulama desteği | Var (libewf standart özelliği) | Var (kütüphanede) ama yazma zaten bozuk | **YOK** (README'nin kendi itirafı) |
| Adli camiada kabul | Çok yaygın (E01 fiili standart) | Sınırlı (açık kaynak DFIR ekosisteminde) | Sınırlı |

Sonuç: EWF'nin engeli **dar ve çözülebilir** bir engeldi (tek eksik
özellik — zlib — aktif/bakımlı, iyi belgelenmiş bir kütüphanede). AFF4
tarafında iki adayın da engeli **yapısal**: pyaff4'te "derleme kolay ama
yazma upstream'in kendi ifadesiyle güvenilmez", c-aff4'te "yazma teorik
olarak var ama proje terk edilmiş ve hash doğrulamasını hiç
uygulamıyor". Bu, bir derleme bayrağıyla ya da script'le
çözülebilecek bir sorun değil — kütüphanelerin kendisi henüz bu işi
güvenilir şekilde yapmıyor.

## (e) Önerilen yön

Bkz. `docs/kararlar.md` — **"2026-09-30 — AFF4 desteği: hangi yön
izlenecek"** karar kaydı. Özet: AFF4 entegrasyonu şimdilik
ERTELENİYOR (hiçbir kütüphane kurulmadı/denenmedi, sadece araştırma +
belgeleme yapıldı, ek fatura/maliyet getiren hiçbir şey yapılmadı).
