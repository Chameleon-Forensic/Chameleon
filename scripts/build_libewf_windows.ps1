<#
.SYNOPSIS
    libewf'i (EWF/E01 kutuphanesi) zlib sikistirma destegiyle Windows'ta
    kaynagindan derler -- docs/ewf_derleme_rehberi.md'nin (bkz. o dosya,
    bolum (a)) otomatiklestirilmis hali.

.ACIKLAMA (Turkce)
    NE YAPAR:
      1. zlib kaynak kodunu https://zlib.net adresinden indirir, acar,
         libewf'in kardesi (sibling) bir klasore, TAM OLARAK "zlib" adiyla
         (surum numarasi olmadan) yerlestirir -- libewf'in msvscpp
         derleme sistemi bu klasoru bu adla ariyor.
      2. libewf kaynak kodunu resmi libyal/libewf GitHub deposundan
         klonlar (git kuruluysa) ya da en guncel kaynak zip'ini indirip
         acar (git yoksa).
      3. msbuild ile msvscpp\libewf.sln'i Release/x64 olarak derler
         (Chameleon x64 hedefledigi icin Win32 DEGIL x64 kullanilir;
         VSDebug/Debug derlemesi Python3.x_d.lib eksikliginden basarisiz
         olur, bu yuzden SADECE Release kullanilir -- bkz. rehberin (b)
         bolumu).
      4. Derleme ciktisinin (libewf.dll, pyewf.pyd, vb.) nerede oldugunu
         ekrana yazar; dosyalari otomatik olarak Python'un
         site-packages'ine KOPYALAMAZ -- bu, kullaniciya kalan, bilinçli
         bir sonraki-adim onayi gerektiren islem (bkz.
         docs/ewf_derleme_rehberi.md bolum (e)).

    ON KOSULLAR (bu script bunlari KURMAZ, sadece varligini kontrol eder):
      - Visual Studio Build Tools, "Desktop development with C++" is
        yukuyle kurulu OLMALI, ve bu script "Developer PowerShell for VS"
        icinden (ya da vcvarsall.bat/VsDevCmd.bat cagrildiktan sonra)
        calistirilmali -- yoksa msbuild.exe PATH'te bulunamaz.
      - Python (Chameleon'un .exe derlemesinde kullanilan AYNI surum/
        mimari, varsayilan C:\venv312 -- Python 3.12 x64) kurulu olmali;
        pyewf binding'i icin Python.org kurulumunun GELISTIRME dosyalari
        (baslik + python3XX.lib) gerekiyor.
      - Internet erisimi (zlib.net + github.com).
      - git kuruluysa kullanilir (yoksa otomatik zip indirmeye duser).

    URETIR:
      <CikisKlasoru>\libewf\   -- libewf kaynak agaci (derleme burada olur)
      <CikisKlasoru>\zlib\     -- zlib kaynak agaci
      <CikisKlasoru>\libewf\msvscpp\x64\Release\ -- derleme ciktisi
        (libewf.dll, libewf.lib, pyewf*.pyd, vb.)

    NE YAPMAZ (bilincli sinir):
      - Visual Studio Build Tools'u KURMAZ -- bu ayri, kullanicinin kendi
        onayiyla yapilmasi gereken bir sistem kurulumu.
      - pip/venv'e HICBIR SEY KURMAZ/KOPYALAMAZ -- ciktiyi Chameleon'a
        entegre etmek ayri, elle yapilacak bir sonraki adim (rehberin
        (e) bolumune bakin).
      - EWF yazmayi TEST ETMEZ -- bunun icin ayrica
        docs/ewf_derleme_rehberi.md bolum (d)'deki test_pyewf_zlib.py
        script'i calistirilmali.

.PARAMETER CikisKlasoru
    zlib + libewf kaynaklarinin indirilecegi/derlenecegi kok klasor.
    Varsayilan: $env:USERPROFILE\ewf-build

.PARAMETER PythonYolu
    pyewf binding'ini derlemek icin kullanilacak Python kurulumunun kok
    klasoru (venv DEGIL, altindaki gercek Python.org kurulumu). Varsayilan:
    C:\venv312 (Chameleon'un mevcut .exe derleme ortamiyla tutarli --
    bkz. src/build.spec ustbilgisi). Kendi makinenizde farkliysa
    -PythonYolu ile gecin.

.PARAMETER Platform
    msbuild platform hedefi. Varsayilan: x64 (Chameleon x64 hedefliyor).
    Win32 SADECE ozel bir sebeple gerekiyorsa degistirin.

.ORNEK
    # Developer PowerShell for VS icinde:
    .\scripts\build_libewf_windows.ps1

.ORNEK
    .\scripts\build_libewf_windows.ps1 -CikisKlasoru D:\ewf-build -PythonYolu C:\Python312
#>

[CmdletBinding()]
param(
    [string]$CikisKlasoru = (Join-Path $env:USERPROFILE "ewf-build"),
    [string]$PythonYolu = "C:\venv312",
    [string]$Platform = "x64",
    [string]$ZlibSurumu = "1.3.1"
)

$ErrorActionPreference = "Stop"

function Yaz-Adim([string]$Metin) {
    Write-Host ""
    Write-Host "==> $Metin" -ForegroundColor Cyan
}

function Yaz-Uyari([string]$Metin) {
    Write-Host "UYARI: $Metin" -ForegroundColor Yellow
}

# --- 0. On kosul kontrolleri -------------------------------------------

Yaz-Adim "On kosullar kontrol ediliyor"

$msbuild = Get-Command msbuild.exe -ErrorAction SilentlyContinue
if (-not $msbuild) {
    throw ("msbuild.exe PATH'te bulunamadi. Bu script 'Developer " +
           "PowerShell for VS' icinden calistirilmali, ya da " +
           "vcvarsall.bat / VsDevCmd.bat once cagrilmali. Visual Studio " +
           "Build Tools + 'Desktop development with C++' is yukunun " +
           "kurulu oldugundan emin olun (bkz. docs/ewf_derleme_rehberi.md " +
           "bolum (b)).")
}
Write-Host "msbuild bulundu: $($msbuild.Source)"

if (-not (Test-Path $PythonYolu)) {
    Yaz-Uyari ("Python yolu bulunamadi: $PythonYolu -- pyewf binding " +
               "hedefi derlenemeyebilir. -PythonYolu ile dogru yolu " +
               "verin (Chameleon'un .exe derlemesinde kullanilan AYNI " +
               "surum/mimari olmali).")
}

$gitVarMi = [bool](Get-Command git.exe -ErrorAction SilentlyContinue)
if (-not $gitVarMi) {
    Yaz-Uyari "git bulunamadi -- libewf kaynak zip'i indirilerek acilacak."
}

New-Item -ItemType Directory -Force -Path $CikisKlasoru | Out-Null
$libewfKlasoru = Join-Path $CikisKlasoru "libewf"
$zlibKlasoru = Join-Path $CikisKlasoru "zlib"

# --- 1. zlib indir + kardes klasore yerlestir ---------------------------

Yaz-Adim "zlib kaynak kodu hazirlaniyor ($zlibKlasoru)"

if (Test-Path $zlibKlasoru) {
    Write-Host "zlib klasoru zaten var, indirme atlaniyor: $zlibKlasoru"
} else {
    $zlibZipUrl = "https://zlib.net/zlib$($ZlibSurumu -replace '\.', '').zip"
    $zlibZipYol = Join-Path $env:TEMP "zlib-$ZlibSurumu.zip"
    $zlibAcmaKlasoru = Join-Path $env:TEMP "zlib-acma-$([Guid]::NewGuid())"

    Write-Host "Indiriliyor: $zlibZipUrl"
    try {
        Invoke-WebRequest -Uri $zlibZipUrl -OutFile $zlibZipYol -UseBasicParsing
    } catch {
        throw ("zlib indirilemedi ($zlibZipUrl). https://zlib.net " +
               "adresinden guncel surumun dogru dosya adini kontrol edip " +
               "-ZlibSurumu parametresiyle tekrar deneyin. Orijinal hata: " +
               "$($_.Exception.Message)")
    }

    New-Item -ItemType Directory -Force -Path $zlibAcmaKlasoru | Out-Null
    Expand-Archive -Path $zlibZipYol -DestinationPath $zlibAcmaKlasoru -Force

    # Zip genelde "zlib-1.3.1" gibi TEK bir alt klasor icerir -- onu
    # bulup TAM OLARAK "zlib" adiyla hedefe tasiyoruz (surum numarasi
    # OLMADAN -- libewf'in derleme sistemi bu adi ariyor).
    $altKlasor = Get-ChildItem -Path $zlibAcmaKlasoru -Directory | Select-Object -First 1
    if (-not $altKlasor) {
        throw "zlib zip'i beklenmeyen bir yapida acildi: $zlibAcmaKlasoru"
    }
    Move-Item -Path $altKlasor.FullName -Destination $zlibKlasoru
    Remove-Item -Path $zlibAcmaKlasoru -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $zlibZipYol -Force -ErrorAction SilentlyContinue

    Write-Host "zlib hazir: $zlibKlasoru"
}

# --- 2. libewf kaynagini al ----------------------------------------------

Yaz-Adim "libewf kaynak kodu hazirlaniyor ($libewfKlasoru)"

if (Test-Path $libewfKlasoru) {
    Write-Host "libewf klasoru zaten var, indirme atlaniyor: $libewfKlasoru"
} elseif ($gitVarMi) {
    Write-Host "git clone https://github.com/libyal/libewf.git"
    & git clone --depth 1 "https://github.com/libyal/libewf.git" $libewfKlasoru
    if ($LASTEXITCODE -ne 0) {
        throw "git clone basarisiz oldu (exit code $LASTEXITCODE)."
    }
} else {
    $libewfZipUrl = "https://github.com/libyal/libewf/archive/refs/heads/main.zip"
    $libewfZipYol = Join-Path $env:TEMP "libewf-main.zip"
    $libewfAcmaKlasoru = Join-Path $env:TEMP "libewf-acma-$([Guid]::NewGuid())"

    Write-Host "Indiriliyor: $libewfZipUrl"
    Invoke-WebRequest -Uri $libewfZipUrl -OutFile $libewfZipYol -UseBasicParsing

    New-Item -ItemType Directory -Force -Path $libewfAcmaKlasoru | Out-Null
    Expand-Archive -Path $libewfZipYol -DestinationPath $libewfAcmaKlasoru -Force

    $altKlasor = Get-ChildItem -Path $libewfAcmaKlasoru -Directory | Select-Object -First 1
    if (-not $altKlasor) {
        throw "libewf zip'i beklenmeyen bir yapida acildi: $libewfAcmaKlasoru"
    }
    Move-Item -Path $altKlasor.FullName -Destination $libewfKlasoru
    Remove-Item -Path $libewfAcmaKlasoru -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $libewfZipYol -Force -ErrorAction SilentlyContinue
}

Write-Host "libewf hazir: $libewfKlasoru"

# --- 3. Cozum (.sln) dosyasinin varligini dogrula ------------------------

$slnYolu = Join-Path $libewfKlasoru "msvscpp\libewf.sln"
if (-not (Test-Path $slnYolu)) {
    throw ("Beklenen cozum dosyasi bulunamadi: $slnYolu -- libewf kaynak " +
           "agacinin yapisi degismis olabilir, docs/ewf_derleme_rehberi.md " +
           "ile karsilastirip elle kontrol edin.")
}

Yaz-Adim ("common\config_winapi.h icindeki WINVER ayarini kontrol edin " +
          "(elle) -- bkz. docs/ewf_derleme_rehberi.md bolum (c), adim 4. " +
          "Dosya: " + (Join-Path $libewfKlasoru "common\config_winapi.h"))

# --- 4. pyewf projesindeki Python yolunu bilgilendirme amacli goster ----

$pyewfVcxproj = Get-ChildItem -Path (Join-Path $libewfKlasoru "msvscpp") -Filter "pyewf*.vcxproj" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if ($pyewfVcxproj) {
    Yaz-Uyari ("pyewf proje dosyasi bulundu: $($pyewfVcxproj.FullName) -- " +
               "icindeki Python yolunun ($PythonYolu ile eslesmesi " +
               "gereken sabit bir yol olabilir, orn. C:\Python3.12\) " +
               "derlemeden ONCE Visual Studio'da ya da elle kontrol " +
               "edilmesi onerilir (bkz. rehber bolum (c), adim 5).")
}

# --- 5. msbuild ile derle (Release, verilen Platform) --------------------

Yaz-Adim "msbuild ile derleniyor (Configuration=Release, Platform=$Platform)"
Write-Host ("NOT: Debug/VSDebug KULLANILMIYOR -- Python3.x_d.lib eksikligi " +
            "nedeniyle basarisiz olur (bkz. rehber bolum (b)).")

Push-Location $libewfKlasoru
try {
    & msbuild $slnYolu "/p:Configuration=Release" "/p:Platform=$Platform"
    if ($LASTEXITCODE -ne 0) {
        throw "msbuild basarisiz oldu (exit code $LASTEXITCODE). Yukaridaki hata ciktisina bakin."
    }
} finally {
    Pop-Location
}

# --- 6. Sonuc ozeti -------------------------------------------------------

$ciktiKlasoru = Join-Path $libewfKlasoru "msvscpp\$Platform\Release"

Yaz-Adim "Derleme tamamlandi"
Write-Host "Cikti klasoru: $ciktiKlasoru"
if (Test-Path $ciktiKlasoru) {
    Get-ChildItem -Path $ciktiKlasoru -Filter "*.dll" | ForEach-Object { Write-Host "  - $($_.Name)" }
    Get-ChildItem -Path $ciktiKlasoru -Filter "*.pyd" | ForEach-Object { Write-Host "  - $($_.Name)" }
} else {
    Yaz-Uyari "Beklenen cikti klasoru bulunamadi -- msbuild ciktisini elle kontrol edin."
}

Write-Host ""
Write-Host "Sonraki adimlar (bu script tarafindan YAPILMAZ, elle onay gerektirir):" -ForegroundColor Green
Write-Host "  1. docs/ewf_derleme_rehberi.md bolum (d) -- test_pyewf_zlib.py ile zlib'in GERCEKTEN calistigini dogrulayin."
Write-Host "  2. docs/ewf_derleme_rehberi.md bolum (e) -- Chameleon'a entegrasyon PLANINI (henuz uygulanmadi) izleyin."
