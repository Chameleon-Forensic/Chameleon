# Kullanım

## `process` modu (sürücü gerekmez)

Belirli bir process'in belleğini `.dmp` dosyasına yazar (Task Manager'ın
"Create dump file" özelliğiyle aynı API'yi kullanır).

```powershell
.\RamImagerCLI.exe process --pid 4821 --output C:\evidence\proc_4821.dmp
```

Parametreler:
- `--pid` : Hedef process ID (Task Manager / `Get-Process` ile bulunabilir)
- `--output` : Çıktı `.dmp` dosyasının tam yolu

## `full` modu (tam fiziksel RAM - sürücü gerekir)

```powershell
.\RamImagerCLI.exe full `
    --output C:\evidence\ram.img `
    --driver C:\tools\RamImagerDriver.sys `
    --case "CASE-2026-08-13" `
    --examiner "Ad Soyad"
```

Parametreler:
- `--output` : Çıktı `.img` dosyasının tam yolu (yanına `.json` ve `.log` dosyaları da yazılır)
- `--driver` : Derlenmiş `RamImagerDriver.sys` dosyasının yolu
- `--case` (opsiyonel) : Vaka/case adı, metadata'ya yazılır
- `--examiner` (opsiyonel) : İncelemeyi yapan kişi, metadata'ya yazılır

Bu komut **Yönetici (Administrator)** olarak çalıştırılmalıdır; aksi halde
`RunFullMode` elevation kontrolünde hemen hata verir.

### Üretilen dosyalar

| Dosya | İçerik |
|---|---|
| `ram.img` | Ham fiziksel bellek görüntüsü (byte-for-byte, okunamayan sayfalar sıfırla dolu) |
| `ram.img.json` | Case adı, examiner, başlangıç/bitiş zamanı (UTC), toplam boyut, SHA-256, bellek aralıkları |
| `ram.img.log` | Zaman damgalı ilerleme/hata günlüğü |

### Bütünlük doğrulama

`ram.img.json` içindeki `sha256` alanını, imajı aldıktan sonra bağımsız olarak
doğrulayın:

```powershell
Get-FileHash C:\evidence\ram.img -Algorithm SHA256
```

Bu değer, `ram.img.json` içindeki `sha256` ile eşleşmelidir; eşleşmezse imaj
bozulmuş veya sonradan değiştirilmiş olabilir.

## Servis/temizlik notu

`full` modu her çalıştırmada `RamImagerDriver` adında geçici bir kernel servisi
kurar, kullanır ve iş bitince **otomatik olarak durdurup siler**
(`ServiceInstaller::StopAndRemove`). Araç beklenmedik şekilde sonlanırsa (örn.
işlem sonlandırılırsa), servisi elle temizlemek için:

```powershell
sc.exe stop RamImagerDriver
sc.exe delete RamImagerDriver
```
