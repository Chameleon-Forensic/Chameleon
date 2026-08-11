# Proje Durum Özeti (test aşaması için, yeni sohbete yapıştırmak üzere)

## Proje
Adli bilişim okul projesi. SSH üzerinden uzak Linux sunucudan disk imajı
alan, 4MB chunk bazlı SHA-256 hash doğrulayan, yazılımsal write-blocker
uygulayan, chain-of-custody log tutan, bağlantı koparsa kaldığı yerden
devam edebilen (resumable), CLI + GUI arayüzlü bir Bash + Python aracı.

Kapsam ve kurallar `docs/PROJE_TALIMATI.md`'de tanımlı.

## DURUM: v1.0 MVP TAMAMLANDI — sırada GERÇEK SUNUCUDA TEST var

Şu ana kadar HER ŞEY sahte (mock) SSH ile test edildi. Gerçek bir
Linux VM'e (VirtualBox/Kali) hiç bağlanılmadı. Bu sohbette yapılacak
asıl iş bu: gerçek ortamda uçtan uca test.

## İki repo var (ikisi de senkron, aynı en son halde)
- Kişisel: `github.com/toprakkulekcioglu/adli-imaj-projesi` (adli-imaj-projesi-main klasörü, çalışma yeri)
- Ekip: `github.com/adli-imaj/remote-forensic-imager` (arkadaşların bunu kullanıyor)

## Tamamlanan modüller

**remote_agent/** (uzak Linux sunucuda, sadece Bash):
- `write_blocker.sh` — blockdev --setro/--getro, MANUEL/referans test scripti
  (gerçek akışta kullanılmıyor, onun yerine write_block_helper.py var)
- `disk_info.sh` — lsblk ile disk listeleme, MANUEL/referans

**local_collector/** (lokal makinede, Python 3 + paramiko):
- `chain_of_custody.py` — düz metin, ISO 8601 UTC zaman damgalı log.
  Olaylar: EXAM_START, EXAM_RESUME, BLOCK_ACQUIRED, CONNECTION_LOST,
  CONNECTION_RESUMED, EXAM_END, EXAM_ERROR, WRITE_BLOCK_APPLIED,
  WRITE_BLOCK_SKIPPED, HASH_VERIFIED, HASH_MISMATCH
- `ssh_connector.py` — paramiko SSH bağlantısı. GÜVENLİK: bilinmeyen host
  key strict modda REDDEDİLİR (RejectPolicy). `run_command()` artık
  (stdout, stderr, exit_code) üçlüsü döndürüyor, `get_pty` ve
  `sudo_password` parametreleri var (parola KOMUT SATIRINA GÖMÜLMEDEN,
  SSH stdin kanalından güvenli iletiliyor). `is_active()`/`reconnect()`/
  keepalive(15) ile kopan bağlantı toparlanıyor.
- `write_block_helper.py` — write_blocker.sh'ı kopyalamadan aynı mantığı
  SSH komutu olarak çalıştırır, sonucu WRITE_BLOCK_APPLIED/EXAM_ERROR loglar.
- `hash_verifier.py` — blok + imaj seviyesi SHA-256 doğrulama (ekibin
  yazdığı, sadece stdlib).
- `image_acquirer.py` — asıl imaj alma motoru: disk boyutu öğrenme, 4MB
  chunk okuma (diske yazmadan ÖNCE doğrulama), bağlantı koparsa 3 kez
  1sn/2sn/4sn artan bekleme ile yeniden bağlanma, İLERLEME ÇUBUĞU,
  KALICI RESUME (`logs/manifest_<tarih-saat>.json` — program kapanıp
  açılsa bile kaldığı yerden devam eder).
- `main.py` — CLI menü: 1) Live 2) Offline 3) Verify Image 0) Çıkış.
  Disk seçilince yarım kalan işlem varsa sorup devam ediyor. Offline
  modda write-block otomatik uygulanıyor, Live modda atlanıp loglanıyor.
  paramiko yoksa çökmüyor (sadece SSH gerektiren seçenekler kapanıyor).
- `gui.py` / `gui_v2.py` — Tkinter grafik arayüz (arka planda thread,
  aynı backend fonksiyonlarını kullanıyor). v2'de renkli log, bağlantı
  göstergesi, zaman damgası var. İkisi de aynı işi yapıyor, hangisi
  beğenilirse o kullanılacak.

**Diğer:** `requirements.txt` (paramiko), `README.md` (kurulum notu)

## Komutlar — nasıl test edilir

```bash
pip install -r requirements.txt
cd local_collector
python main.py          # CLI
# veya
python gui.py            # GUI (orijinal)
python gui_v2.py         # GUI (renkli/gelişmiş görünüm)
```

Test sırasında dikkat edilecekler:
- **SUDO/NOPASSWD**: uzak sunucudaki kullanıcının `/etc/sudoers`'ında
  `blockdev`/`dd` için NOPASSWD tanımlı olması otomatik akışın sorunsuz
  çalışması için önerilir. Tanımlı değilse main.py/gui'de girilen SSH
  parolası sudo için de kullanılıyor (güvenli, stdin üzerinden).
- Offline testini **OS diskinde DENEMEYİN** — ayrı, kullanılmayan bir
  test diski/partition seçin.
- İlk gerçek testte: bağlantı, disk listesi, write-block, imaj alma,
  ilerleme çubuğu, `logs/case_*.log` ve `logs/manifest_*.json`
  dosyalarının doğru oluşup oluşmadığını kontrol edin.

## Bilinen eksikler / sınırlamalar
- `hash_verifier.py`'deki `verify_image_against_manifest()` (tamamlanmış
  imajı blok blok yeniden doğrulama) henüz `main.py`'ye bağlanmadı,
  opsiyonel bonus.
- Gerçek sunucuda hiç test edilmedi (bu sohbetin asıl amacı bu).

## Çalışma tarzı kuralları (unutma)
- Kod yorumları Türkçe, değişken/fonksiyon isimleri İngilizce
- Yeni 3. parti kütüphane eklemeden önce SOR
- `docs/PROJE_TALIMATI.md`'nin dışına çıkma, emin olmadığında SOR
- Güvenlik: parolayı asla komut satırına gömme, sudo_password/getpass kullan
