# RamImager - Kullanım Kılavuzu

Bu kılavuz, RamImager aracını (CLI + GUI) kuran/çalıştıran kişiler içindir.
Geliştirme/derleme detayları için [BUILD.md](BUILD.md), mimari için
[ARCHITECTURE.md](ARCHITECTURE.md), yasal çerçeve için [LEGAL.md](LEGAL.md)
dosyalarına bakın.

> **Yasal uyarı:** Bu araç yalnızca üzerinde açık yetkiniz olan sistemlerde
> kullanılmalıdır. Ayrıntılar için [LEGAL.md](LEGAL.md).

---

## 1. Araç ne yapar?

| Mod | Ne yapar | Sürücü gerekir mi | Yönetici gerekir mi |
|---|---|---|---|
| `process` | Tek bir process'in belleğini `.dmp` dosyasına yazar (`MiniDumpWriteDump`) | Hayır | Genelde hayır |
| `full` | Tüm fiziksel RAM'i `.img` dosyasına döker (FTK Imager "Capture Memory" benzeri) | Evet (`RamImagerDriver.sys`) | Evet |

İki arayüz sunulur:
- **RamImagerCLI.exe** — komut satırı aracı (asıl mantığı içerir)
- **RamImagerGUI.exe** — CLI'yi saran, formlarla dolduran basit bir test arayüzü

---

## 2. Sistem gereksinimleri

- Windows 10/11, **x64**
- `process` modu: ek bir şey gerekmez (yönetici olmadan da genelde çalışır)
- `full` modu:
  - Yönetici (Administrator) oturumu
  - Derlenmiş `RamImagerDriver.sys`
  - **Secure Boot kapalı** (UEFI/BIOS ayarı) — açıksa imzasız/test-imzalı sürücü kesinlikle yüklenmez
  - Test signing açık (`bcdedit /set testsigning on`) + yeniden başlatma — ya da gerçek bir EV/attestation imzası
- GUI için: `Microsoft.WindowsDesktop.App` çalışma zamanı (10.x veya proje dosyasında hedeflenen sürüm)

---

## 3. Hızlı başlangıç

### 3.1. Zaten derlenmiş dosyalarınız varsa

```powershell
# process modu - hemen çalışır
.\RamImagerCLI.exe process --pid 1234 --output C:\evidence\proc_1234.dmp
```

### 3.2. Kaynaktan derleyecekseniz

```powershell
# CLI (sürücü gerekmez)
cmake -S . -B build -A x64
cmake --build build --config Release

# Sürücü (full modu için)
winget install --id Microsoft.WindowsWDK.10.0.26100
.\driver\build_driver.ps1

# GUI (opsiyonel)
cd gui\RamImagerGUI
dotnet build -c Release
```

Detaylı derleme talimatı: [BUILD.md](BUILD.md).

---

## 4. CLI kullanımı

### 4.1. `process` modu

```powershell
RamImagerCLI.exe process --pid <PID> --output <yol.dmp>
```

| Parametre | Açıklama |
|---|---|
| `--pid` | Hedef process ID'si (`Get-Process` veya Task Manager ile bulunur) |
| `--output` | Çıktı `.dmp` dosyasının tam yolu |

Örnek:
```powershell
RamImagerCLI.exe process --pid 4821 --output C:\evidence\proc_4821.dmp
```

### 4.2. `full` modu

```powershell
RamImagerCLI.exe full --output <yol.img> --driver <RamImagerDriver.sys yolu> [--case AD] [--examiner AD]
```

| Parametre | Açıklama |
|---|---|
| `--output` | Çıktı `.img` dosyasının tam yolu (yanına `.json` ve `.log` da yazılır) |
| `--driver` | Derlenmiş `RamImagerDriver.sys` yolu |
| `--case` (opsiyonel) | Vaka/case adı, metadata'ya yazılır |
| `--examiner` (opsiyonel) | İncelemeyi yapan kişi, metadata'ya yazılır |

Örnek (Yönetici PowerShell'de çalıştırılmalı):
```powershell
RamImagerCLI.exe full `
    --output C:\evidence\ram.img `
    --driver C:\tools\RamImagerDriver.sys `
    --case "CASE-2026-08-13" `
    --examiner "Ad Soyad"
```

Üretilen dosyalar:

| Dosya | İçerik |
|---|---|
| `ram.img` | Ham fiziksel bellek görüntüsü (okunamayan sayfalar sıfırla dolu) |
| `ram.img.json` | Case adı, examiner, zaman damgası, toplam boyut, SHA-256, bellek aralıkları |
| `ram.img.log` | Zaman damgalı işlem günlüğü |

### 4.3. Bütünlük doğrulama

```powershell
Get-FileHash C:\evidence\ram.img -Algorithm SHA256
```

Bu değer `ram.img.json` içindeki `sha256` alanıyla eşleşmelidir.

---

## 5. GUI kullanımı

```powershell
gui\RamImagerGUI\bin\Release\net10.0-windows\RamImagerGUI.exe
```

Adımlar:
1. **Mod** seçin: `Process Dump` (varsayılan, sürücü gerekmez) veya `Tam RAM - full`.
2. **Process Dump**: listeden bir process seçin, çıktı yolunu belirleyin.
3. **Tam RAM**: sürücü (`.sys`) yolunu, çıktı yolunu, isterseniz case/examiner girin.
4. **Başlat**'a basın. `full` modda GUI kendisi yönetici değilse otomatik bir UAC istemi çıkar (sadece o tek komut için).
5. **Günlük** panelinde ilerlemeyi izleyin; bitince **Çıktı Klasörünü Aç** ile sonucu görün.

Ayrıntılar: [GUI.md](GUI.md).

---

## 6. Başka bir bilgisayara taşıma

Derlenmiş dosyaları tek klasörde toplayan paketleme betiği:

```powershell
.\scripts\package_release.ps1
```

`dist\RamImager\` klasörü şunları içerir: `cli\RamImagerCLI.exe`,
`driver\RamImagerDriver.sys`, `gui\...\RamImagerGUI.exe`, ilgili dokümanlar ve
hedef makinede izlenecek adımları anlatan **`INSTALL.txt`**.

Bu klasörü hedef makineye kopyalayıp `INSTALL.txt`'yi takip edin. Unutmayın:
`full` modu için hedef makinede yine de Secure Boot kapatma + test signing
açma + reboot gerekir (imzasız sürücü olduğu için) — `process` modu ek işlem
gerektirmeden direkt çalışır.

---

## 7. Sorun giderme

| Hata / durum | Olası neden | Çözüm |
|---|---|---|
| `CreateService failed (error 5)` | Yönetici olarak çalıştırılmadı | PowerShell'i "Yönetici olarak çalıştır" ile açın |
| `StartService failed (error 577)` | Sürücü imzalanmamış / test signing kapalı | `scripts\enable_test_signing.ps1` çalıştırıp reboot edin |
| `StartService failed (error 1275)` | Sürücü ilkesi (Driver Signature Enforcement) engelliyor | Secure Boot'u kapatın (UEFI), test signing açık olsun |
| `IOCTL_RAMIMAGER_GET_RANGE_COUNT failed (error 5)` | Cihaz Administrator olmayan bağlamda açılmaya çalışılıyor | Yönetici olarak çalıştırın |
| GUI açılmıyor / ".NET yükleyin" hatası | Hedef .NET çalışma zamanı kurulu değil | `dotnet --list-runtimes` ile kontrol edin, `RamImagerGUI.csproj`'daki `TargetFramework`'ü kurulu sürümle eşleştirip yeniden derleyin |
| `full` modda GUI günlüğü ilerlemiyor | Sürücü servisi başlamamış olabilir (bkz. yukarıdaki hatalar) | `.img.log` dosyasını doğrudan açıp kontrol edin |

Servis beklenmedik şekilde sistemde kalırsa elle temizleyin:
```powershell
sc.exe stop RamImagerDriver
sc.exe delete RamImagerDriver
```

---

## 8. Sıkça Sorulan Sorular

**S: Sürücü olmadan tam RAM alabilir miyim?**
Hayır. Windows Vista'dan beri kullanıcı modu uygulamaları fiziksel belleğe
doğrudan erişemez; bu yüzden imzalı/test-imzalı bir kernel sürücü şarttır.

**S: Sürücüyü her makinede yeniden derlemem mi gerekiyor?**
Hayır, derlenmiş `.sys` dosyasını taşıyabilirsiniz (bkz. bölüm 6), ama hedef
makinede Secure Boot/test signing ayarları yine de gerekir.

**S: Üretimde (gerçek olay müdahalesinde) test signing kullanabilir miyim?**
Önerilmez. Test signing tüm sistemin imza politikasını gevşetir. Üretim için
EV kod imzalama sertifikası + Microsoft attestation signing kullanın (bkz.
[BUILD.md](BUILD.md)).

**S: `.img` dosyası neden bazı yerlerde sıfır?**
Okunamayan (reserved/mapped olmayan) fiziksel sayfalar, adres hizalamasını
bozmamak için sıfırla doldurulur; bu davranış FTK Imager gibi ticari
araçlarla aynıdır.
