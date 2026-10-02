# EWF/E01 için `libewf` + zlib derleme rehberi (Windows)

> Bu belge, `docs/kararlar.md`'deki **"EWF/E01 desteği: hangi yol
> izlenecek"** kararının (Seçenek 1: libewf'i kaynağından, zlib ile kendimiz
> derlemek) UYGULAMA rehberidir. Karar kaydı NEDEN bu yolun seçildiğini
> anlatıyor, bu belge NASIL yapılacağını adım adım anlatıyor.
>
> **Durum:** Bu rehber ve aşağıdaki `scripts/build_libewf_windows.ps1`
> script'i hazır, ama gerçek derleme henüz YAPILMADI. Derleme, Visual
> Studio Build Tools kurulumu bir sistem komutu olduğu için kullanıcının
> kendi Windows makinesinde, ayrı bir onayla yapılmalı (bkz.
> `docs/kararlar.md`'deki ilgili bölüm).

## (a) Neden bu derleme gerekiyor

PyPI'daki hazır `libewf-python` wheel'i (Windows için önceden derlenmiş,
Visual Studio Build Tools gerektirmeden `pip install` ile kurulabilen
sürüm) **zlib/deflate sıkıştırma desteği OLMADAN** derlenmiş durumda. EWF
formatı hem header hem veri bölümleri için zorunlu olarak sıkıştırma
kullandığından, bu wheel ile Chameleon **var olan bir E01 dosyasını
okuyabiliyor ama yeni bir E01 dosyası YAZAMIYOR**. Bu bulgu bir kere elle
test edilerek doğrulanmış, ardından libewf'in resmi Windows wheel CI
pipeline'ı (`.github/workflows/build_wheel.yml` + çağırdığı
`synclibs.ps1`) incelenerek ikinci kez doğrulanmıştı: `synclibs.ps1`
yalnızca 21 libyal alt-kütüphanesini (libbfio, libcerror, vb.)
senkronize ediyor, zlib'i hiç indirmiyor/senkronize etmiyor — yani PyPI
wheel'inin zlib'siz derlendiği rastgele bir hata değil, CI'ın kendi
tasarımının bir sonucu. Ayrıca modern `_build.py` (PEP 517 build
backend) incelendiğinde, MSVC için sadece `_CRT_SECURE_NO_WARNINGS`,
`UNICODE`, `WINVER=0x0501` macro'larını tanımladığı, zlib/bzip2 için
include/lib yolu arama mantığının hiç olmadığı görüldü — yani
`pip install` / `python -m build` akışı Windows'ta zlib'i otomatik
bulmuyor, aşağıdaki klasik `msvscpp\libewf.sln` + elle zlib
sibling-folder yöntemi hâlâ TEK güvenilir yol.

Kararlar.md'deki değerlendirmede, üçüncü parti önceden derlenmiş bir
`ewfacquire.exe` binary'si gömmek de bir seçenek olarak incelenmiş ama
adli savunulabilirlik riski (köken doğrulanamıyor, güncel değil)
nedeniyle reddedilmişti — bu yüzden burada anlatılan, resmi libyal/libewf
kaynağından, izlenebilir/belgelenebilir bir süreçle KENDİ derlememizdir.

## (b) Ön koşullar

1. **Visual Studio Build Tools**, "Desktop development with C++" iş
   yükü kurulu olarak. (Chameleon'un `.exe` derlemesinde zaten Visual
   Studio kullanıldığı biliniyor — bkz. `src/build.spec`'teki üstbilgi;
   aynı kurulumun bu iş yükünü içerdiği doğrulanmalı, içermiyorsa Visual
   Studio Installer'dan eklenmeli.)
2. **Python**, Chameleon'un `.exe` derlemesinde kullanılanla AYNI sürüm
   ve mimari (x64) — `src/build.spec`'in üstbilgisine göre şu an
   `C:\venv312` (Python 3.12) kullanılıyor. pyewf Python binding'lerinin
   derlenebilmesi için Python geliştirme dosyaları (başlıklar +
   `python3XX.lib`) gerekiyor — bunlar **Python.org'un kendi
   yükleyicisinin** (venv'in değil, temelindeki asıl kurulumun) bir
   parçasıdır. **Önemli:** VSDebug (Debug) derlemesi `Python3.x_d.lib`
   eksikliğinden BAŞARISIZ olur (bu dosya sadece Python'un debug
   derlemesiyle birlikte gelir, normal kurulumlarda yok) — bu yüzden
   sadece **Release** yapılandırması kullanılmalı, aşağıdaki komutlarda
   zaten öyle.
3. **zlib kaynak kodu** — https://zlib.net adresinden indirilecek (script
   bunu otomatikleştiriyor, bkz. (c)).
4. **libewf kaynak kodu** — resmi `libyal/libewf` GitHub deposu (script
   bunu da otomatikleştiriyor).
5. **PowerShell 5.1+** (Windows'ta varsayılan zaten kurulu) ve
   `msbuild.exe`'nin PATH'te olması (Visual Studio Build Tools kurulumu
   genelde "Developer PowerShell for VS" ile birlikte gelir — script bu
   ortamda çalıştırılmalı, ya da `vcvarsall.bat`/`VsDevCmd.bat` önce
   çağrılmalı).

## (c) Adım adım derleme

Aşağıdaki adımlar `scripts/build_libewf_windows.ps1` tarafından
otomatikleştiriliyor (bkz. o dosyadaki yorum satırları); elle
yapılacaksa sıra şöyle:

1. **Klasör yapısı** — libewf kaynağı ile zlib kaynağı KARDEŞ (sibling)
   klasörler olmalı, zlib klasörünün adı SÜRÜM NUMARASI OLMADAN tam
   olarak `zlib` olmalı (libewf'in derleme sistemi bunu arıyor):

   ```
   C:\ewf-build\
   ├── libewf\           <- libyal/libewf kaynağı (bu klasörün içinde msvscpp\libewf.sln var)
   └── zlib\             <- zlib kaynağı, "zlib-1.3.1" gibi bir isimden BUNA yeniden adlandırılmış
   ```

2. **zlib'i indir ve yerleştir** — https://zlib.net üzerinden en güncel
   kaynak `.zip`'i indirip `C:\ewf-build\zlib\` içine aç (üst klasör
   adında sürüm numarası varsa kaldır, klasör adı tam olarak `zlib`
   olmalı).

3. **libewf kaynağını al** — `git clone
   https://github.com/libyal/libewf.git C:\ewf-build\libewf` (ya da
   GitHub'daki en güncel "Source code" tarball'ını indirip aç).

4. **`common\config_winapi.h` içinde WINVER ayarını kontrol et** —
   libewf'in resmi build dokümantasyonu (wiki/Building) bu dosyada
   hedef Windows API sürümünün (`WINVER`) tanımlı olmasını istiyor;
   Chameleon zaten modern Windows hedeflediği için varsayılan değer
   genelde yeterli, ama dosya açılıp doğrulanmalı.

5. **`msvscpp\libewf.sln`'i Visual Studio'da aç** (ya da doğrudan
   `msbuild` ile derle — adım 6) ve pyewf projesinin ayarlarında Python
   yolunun doğru olduğunu kontrol et (libewf'in varsayılanı
   `C:\Python3.12\` gibi sabit bir yol olabilir — kullanıcının GERÇEK
   Python kurulum yoluyla, örn. Python.org kurulumunun kendisiyle,
   AYNI olmalı; venv yolu değil, venv'in temelindeki gerçek Python
   kurulumu).

6. **Derle** (Release, x64 — Chameleon x64 hedeflediği için Win32
   DEĞİL):

   ```
   msbuild msvscpp\libewf.sln /p:Configuration=Release /p:Platform=x64
   ```

7. **Çıktı** — `msvscpp\x64\Release\` altında: `libewf.dll`,
   `libewf.lib`, ve pyewf hedefi derlendiyse `pyewf.pyd` (Python sürüm
   numarasına göre adlandırılmış olabilir, örn. `pyewf.pyd` veya
   `pyewf.cp312-win_amd64.pyd`).

8. **Dağıtım için gereken yan dosyalar** — `libewf.dll`'in yanında:
   - VC++ Runtime DLL'leri (derleme makinesinde zaten varsa sorun değil,
     hedef makinede yoksa Microsoft'un "Visual C++ Redistributable"
     paketi gerekir),
   - `zlib.dll` (adım 2'de derlenen zlib'in DLL çıktısı — libewf'in
     kendi çözümü zlib'i de aynı `.sln` içinde statik/dinamik
     derleyebiliyor, `msvscpp\zlib\` altına bakılmalı),
   - (opsiyonel) `bzip2.dll`, eğer bzip2 sıkıştırmalı EWF formatı da
     destekleniyorsa (Chameleon'un ilk sürümü için zorunlu değil, EWF'nin
     varsayılan/standart yöntemi deflate/zlib).

## (d) Doğrulama — gerçekten zlib ile yazabiliyor mu?

Derleme bittikten sonra, `pyewf.pyd`'nin bulunduğu klasörü (ya da onu
kurulu Python'un `site-packages`'ine kopyaladıktan sonra) aşağıdaki
script ile test edin. İki yöntem birden kullanılıyor: (1) birkaç MB
GERÇEK (sıkıştırılabilir, örn. tekrar eden) veri yazıp çıktı E01
dosyasının boyutunun yazılan veriden KÜÇÜK olduğunu doğrulamak, (2)
libewf'in kendi API'sinden sıkıştırma yönteminin gerçekten "deflate"
olarak ayarlandığını okumak.

```python
"""
test_pyewf_zlib.py
Derlenen pyewf modulunun GERCEKTEN zlib/deflate sikistirmasiyla
E01 yazabildigini dogrular. Kullanim:
    C:\\venv312\\Scripts\\python.exe test_pyewf_zlib.py
(pyewf.pyd, bu script'in calistigi Python'un import edebilecegi bir
yerde olmali -- ayni klasor ya da site-packages.)
"""
import os
import tempfile

import pyewf

# Kolayca sikistirilabilir veri: 8 MB'lik tek bir byte'in tekrari.
# Sikistirmasiz kaydedilseydi cikti da ~8 MB olurdu; zlib gercekten
# calisiyorsa E01 cikisi bundan BELIRGIN sekilde kucuk olmali.
VERI_BOYUTU = 8 * 1024 * 1024
veri = b"\x00" * VERI_BOYUTU

with tempfile.TemporaryDirectory() as tmp:
    hedef = os.path.join(tmp, "test_pyewf")

    handle = pyewf.handle()
    # compression_method: pyewf'de "deflate" (zlib) varsayilan/istenen
    # yontem -- API'nin kendisinden okuyarak da dogruluyoruz (asagida).
    handle.open(
        [hedef + ".E01"],
        flags=pyewf.get_access_flags_write(),
    )
    handle.set_media_size(VERI_BOYUTU)
    handle.write(veri)
    handle.close()

    e01_yolu = hedef + ".E01"
    e01_boyutu = os.path.getsize(e01_yolu)

    print(f"Yazilan ham veri: {VERI_BOYUTU} bayt")
    print(f"Uretilen E01 dosyasi: {e01_boyutu} bayt")

    if e01_boyutu >= VERI_BOYUTU:
        raise SystemExit(
            "HATA: E01 dosyasi ham veriden KUCUK degil -- sikistirma "
            "calismiyor olabilir (zlib'siz derlenmis wheel ile ayni "
            "belirti)."
        )

    print("OK: E01 dosyasi ham veriden kucuk -- sikistirma calisiyor.")

    # Ikinci dogrulama: dosyayi tekrar acip libewf'in kendi API'sinden
    # sikistirma yontemini oku.
    okuma = pyewf.handle()
    okuma.open(
        pyewf.glob(e01_yolu),
        flags=pyewf.get_access_flags_read(),
    )
    try:
        yontem = okuma.get_compression_method()
        # libewf sabitleri: 1 = deflate (zlib), 2 = bzip2, 0 = yok.
        print(f"Sikistirma yontemi kodu: {yontem}")
        if yontem != 1:
            raise SystemExit(
                f"HATA: Beklenen sikistirma yontemi 'deflate' (1), "
                f"okunan: {yontem}."
            )
        print("OK: Sikistirma yontemi 'deflate' (zlib) olarak dogrulandi.")
    finally:
        okuma.close()

print("\nTUM TESTLER GECTI: pyewf zlib ile calisiyor.")
```

Not: `pyewf`'in tam API yüzeyi (metod adları, `get_compression_method`
gibi) libewf sürümüne göre küçük farklar gösterebilir — script
çalıştırıldığında bir `AttributeError` alınırsa, kurulu `pyewf`
modülünün `dir(pyewf.handle())` çıktısına bakıp en yakın karşılığı
kullanmak gerekir; bu, gerçek derlenmiş binary olmadan bu ortamda
(Linux sandbox) baştan doğrulanamayan bir noktadır.

## (e) Chameleon'a entegrasyon PLANI (henüz YAPILMADI)

Bu adım şimdi UYGULANMIYOR — derlenmiş binary olmadan kod gerçek anlamda
test edilemeyeceği için sadece plan yazılıyor. Plan, projenin pytsk3 ile
daha önce çözdüğü AYNI problem sınıfına (derlenmiş bir Python C
uzantısını `.exe`'ye bundle etmek) dayanıyor:

1. **Binary'leri projeye yerleştirme** — pytsk3 PyPI'dan önceden
   derlenmiş bir wheel olarak `pip install` ile venv'e kurulduğu için
   `site-packages` altında zaten hazır geliyor; pyewf'nin PyPI'da
   zlib'li bir wheel'i olmadığından, kendi derlediğimiz `pyewf.pyd` +
   `libewf.dll` + `zlib.dll` (+ varsa `bzip2.dll`) dosyaları AYNI şekilde
   davranması için `C:\venv312`'nin `site-packages`'ine (ya da
   `pyewf.pyd`'nin arandığı bir konuma) elle kopyalanmalı — böylece
   `import pyewf` normal bir pip paketiymiş gibi çalışır ve PyInstaller
   onu tıpkı pytsk3 gibi görür.
2. **`build.spec`'e ekleme** — `src/build.spec`'in
   `hiddenimports` listesine `pytsk3` girdisinin YANINA `"pyewf"`
   eklenmeli (aynı gerekçeyle: `disk_tree.py`/ilgili yeni EWF modülü,
   veri dosyası olarak yüklenen bir klasörün altında olduğu için
   PyInstaller'ın statik analizi bu importu göremiyor).
3. **DLL bağımlılıkları** — `libewf.dll`/`zlib.dll`/(varsa)
   `bzip2.dll`, `pyewf.pyd` ile AYNI klasörde (site-packages) olduğu
   sürece PyInstaller'ın ikili bağımlılık taraması bunları genelde
   otomatik buluyor; ama bu, gerçek derlenmiş `.pyd` olmadan bu ortamda
   doğrulanamıyor — pytsk3'te olduğu gibi (`docs/roadmap.md`'deki
   "Doğrulanmadı: gerçek derlenmiş .exe ile henüz test edilmedi" notu),
   ilk gerçek derlemede `Chameleon.exe` UI Automation ile açılıp EWF
   yazma yolu denenerek doğrulanmalı; DLL'ler otomatik gömülmezse
   `build.spec`'in `binaries=[]` listesine elle eklenmesi gerekecek.
4. **`requirements.txt`** — `pyewf`/`libewf-python`'ı BURAYA EKLEMEK
   YANLIŞ olur: PyPI'daki paket zlib'siz, `pip install -r
   requirements.txt` başka bir makinede çalıştırıldığında yine zlib'siz
   sürüm kurulur. Bunun yerine bu rehber + script'e bir referans
   (yorum satırı) eklenmeli — "bu bağımlılık pip ile değil, elle
   derlenip vendor edilmiştir" notu.
5. **Yeni bir EWF yazma modülü** — mevcut `image_acquirer.py`/
   `windows_acquirer.py`'nin `write_segments`/blok yazma deseniyle aynı
   şekilde çalışan, `pyewf.handle()` sarmalayan yeni bir modül (örn.
   `engines/ssh_engine/local_collector/ewf_writer.py` gibi, henüz
   YAZILMADI) EWF çıktı formatını Chameleon'un mevcut segment/hash
   akışına bağlayacak — bu, ayrı bir geliştirme adımı, bu rehberin
   kapsamı dışında.

Özet: derleme + doğrulama tamamlanıp `pyewf.pyd` elde edildikten SONRA,
yukarıdaki 5 adım ayrı bir oturumda (gerçek binary ile test edilerek)
uygulanmalı.
