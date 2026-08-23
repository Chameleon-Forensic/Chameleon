# Yapılacaklar / fikirler

## Yapıldı

- SSH motoru (`ssh_engine`) ve RAM imaj motoru (`ram_engine`) tek launcher'dan seçilebiliyor.
- Launcher ve SSH motoru tam CustomTkinter (açık/koyu tema, tutarlı renk paleti).
- Güvenlik: `disk_path` artık `shlex.quote` ile korunuyor (komut enjeksiyonu kapatıldı, `image_acquirer.py` + `write_block_helper.py`).
- Çift disk alanı sorunu çözüldü: `concatenate_blocks(..., cleanup=...)` — Live modda parçalar korunuyor (resume için), Offline modda birleştirme sonrası otomatik siliniyor. Hem GUI hem CLI güncellendi, test edildi.
- RAM motoru artık kendi CTk arayüzümüzle (`engines/ram_engine/ram_gui.py`) çalışıyor — `RamImagerGUI.exe` (vendor'in WinForms programı) hiç açılmıyor, `RamImagerCLI.exe` doğrudan çağrılıyor. Launcher'a aynı pencerede gömüldü (SSH motoru gibi). Process Dump modu gerçek bir process (notepad) üzerinde test edildi, çalıştı. Full mod yazıldı ama Yönetici + test-signing gerektirdiği için henüz gerçek makinede test edilmedi.
- Dosya/klasör seçme eklendi (`file_acquirer.py`) — `ssh_engine` ekranında "Ne Alınacak?" seçimiyle Tam Disk / Dosya ya da Klasör arasında geçiliyor. Tek dosya ya da tüm klasör (recursive, `find -type f`) alınabiliyor, her dosya `sha256sum` ile yazmadan önce doğrulanıyor, goreli klasör yapısı korunuyor, `manifest_files.json` üretiliyor. Write-blocker bu modda uygulanmıyor (dosya seviyesinde anlamsız, her zaman Live gibi çalışır). Mock SSH ile hem tek dosya hem klasör senaryosu, GUI'nin gerçek worker thread'i üzerinden uçtan uca test edildi.
- Varsayılan tema koyu yapıldı (`shared/theme.py` + launcher + her iki motorun standalone girişi).

## Sırada

0. **Tek tıkla kurulum** — kullanıcı `pip install` ile uğraşmamalı. `PyInstaller --onefile --windowed` ile launcher'ı (ve içine `ssh_engine`'i) tek bir `.exe`'ye paketlemek gerekiyor; `ram_engine` zaten kendi derlenmiş halinde geliyor. Şu an geliştirme sırasında `pip install` kullanılıyor ama nihai teslim tek exe olmalı.
1. **Taşınabilir toplama kiti** — SSH erişimi olmayan (şirket politikası vb.) durumlar için: flash bellekten çalışan bağımsız bir uygulama, hedefte yerel olarak imaj alır (disk ve/veya `ram_engine`), sonucu TLS ile şifreleyip bir porttan operatöre gönderir. `ssh_engine`'deki chunk + hash + resume deseni buraya da taşınacak. Bu şu ana kadarki en büyük parça, kendi başına bir motor.
2. **Ortak rapor formatı** — `ssh_engine` düz metin log üretiyor, `ram_engine` kendi `.img.json`'ını üretiyor, dosya/klasör modu kendi `manifest_files.json`'ını üretiyor. Üçünü de aynı şemadan (case, examiner, hash, zaman) üretmek "tek ürün" hissini güçlendirir.
3. **Sıkıştırma seçeneği** — sunucu/hedef aktif değilse (Offline Acquisition), kullanıcıya sıkıştırılmış (örn. gzip) imaj alma seçeneği sunulmalı; disk alanı tasarrufu sağlar, resume ihtiyacı olmayan senaryolarda mantıklı.
4. **Windows hedefler için de aynı temel akış** — şu an `ssh_engine` sadece uzak Linux sunucuları hedefliyor (SSH+`dd`), `ram_engine` sadece yerel Windows RAM'i. Ürünün "temel özellikler" seviyesinde Windows VE Linux hedeflerinde aynı işlemleri (disk imajı alma, hash doğrulama, chain-of-custody) yapabilmesi gerekiyor — şu an bu simetri yok.
5. **Full RAM modunun gerçek makinede test edilmesi** — `ram_gui.py`'deki full mod kodu yazıldı (ShellExecute+runas ile yükseltme, `.img.log` tail'leme) ama Yönetici + Secure Boot/test-signing gerektirdiği için ben test edemedim; kullanıcı kendi makinesinde denemeli.
6. **Büyük dosyalarda resume** — `file_acquirer.py` şu an dosyaları tek seferde (chunk'sız) çekiyor; çok büyük tek dosyalarda (örn. birkaç GB'lık bir log) bağlantı koparsa baştan başlar. `image_acquirer.py`'deki chunk+resume deseni ileride buraya da taşınabilir.

## Daha sonra, öncelik sırası netleşmedi

- Gerçek EWF/E01 ve AFF4 desteği
- Büyük imajları `.001`/`.002` gibi parçalara bölme
- Gerçek PKI/CA doğrulaması (taşınabilir kitin TLS'i için)
- Aynı anda birden fazla istemciden imaj alma
- `ram_engine`'in sürücüsünü gerçek bir sertifikayla imzalamak (şu an test-signing + reboot gerekiyor)
- Vaka geçmişi tutan merkezi bir veritabanı (SQLite)
- Ağ hızına göre değişen chunk boyutu
- Otomatik testler (pytest) — `ssh_engine`'de mock SSH deseni zaten var, oradan genişletilebilir
- Çoklu dil desteği — launcher'da başladı, motorların kendi arayüzüne henüz yayılmadı
