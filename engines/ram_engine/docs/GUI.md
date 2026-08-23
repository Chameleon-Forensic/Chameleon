# Test Arayüzü (GUI)

`gui/RamImagerGUI` — `RamImagerCLI.exe`'yi saran, komut satırı bilmeden test
etmek için hazırlanmış küçük bir WinForms (.NET) uygulaması. CLI'nin yerine
geçmez; sadece aynı parametreleri dolduran bir ön yüzdür.

## Derleme ve çalıştırma

Gereksinim: .NET SDK 10 (veya kurulu `Microsoft.WindowsDesktop.App` çalışma
zamanına göre `RamImagerGUI.csproj` içindeki `TargetFramework` değerini
`net8.0-windows` / `net10.0-windows` olarak ayarlayın — `dotnet --list-runtimes`
ile hangisinin kurulu olduğunu kontrol edin).

```powershell
cd gui\RamImagerGUI
dotnet build -c Release
.\bin\Release\net10.0-windows\RamImagerGUI.exe
```

## Arayüz

- **Mod**: `Process Dump` (sürücü gerekmez, varsayılan) veya `Tam RAM - full` (sürücü gerekir).
- **Process Dump modu**: açık process listesinden birini seçin, çıktı `.dmp`
  yolunu belirtin, **Başlat**'a basın.
- **Tam RAM modu**: derlenmiş `RamImagerDriver.sys` yolunu, çıktı `.img` yolunu,
  isteğe bağlı case/examiner bilgisini girin. Uygulama zaten yönetici olarak
  çalışmıyorsa, tek bu CLI çağrısı için otomatik bir **UAC istemi** gösterilir
  (GUI'nin tamamı yönetici olarak çalışmak zorunda değildir).
- **Günlük** paneli, CLI'nin canlı çıktısını (process modu) veya CLI'nin kendi
  ürettiği `.img.log` dosyasını (full mod + UAC ile ayrı süreç olarak
  yükseltildiğinde stdout yakalanamadığı için) periyodik olarak okuyup gösterir.
- **Çıktı Klasörünü Aç**: başarılı bir çalıştırmadan sonra çıktı dosyasını
  Explorer'da seçili olarak açar.

## Neden bu tasarım?

- GUI'nin manifest'i `asInvoker` — yani GUI'nin kendisi hiçbir zaman zorla
  yönetici istemez; yalnızca gerçekten yetki gerektiren tek `full` komutu
  `ShellExecute` + `runas` ile ayrıca yükseltilir. Bu, `process` modunu her
  seferinde UAC sormadan hızlıca test etmeyi sağlar.
- Yükseltilmiş (runas) bir alt süreçten `stdout` yönlendirilemediği için
  (Windows kısıtlaması), full mod ilerlemesi CLI'nin zaten yazdığı
  `<image>.img.log` dosyası periyodik olarak okunarak gösterilir
  (`MainForm.TailLogFile`).
- Process listesi her açılışta ve **Yenile** butonuyla tazelenir.
