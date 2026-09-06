# Chameleon — geliştirme notları

Bu dosya projeye katkı verecek herkes (yeni katılan biri ya da bir kod
asistanı) için: kod stili, klasör yapısı ve `ssh_engine`'in teknik
kısıtları burada.

## Kod stili

- Kod içi yorumlar Türkçe, değişken/fonksiyon isimleri İngilizce.
- Her modül tek başına çalıştırılıp test edilebilir olacak şekilde yazılıyor.
- Gereksiz soyutlama yok; basit ve okunabilir tutuluyor.

## Klasör yapısı

```
chameleon/
├── src/
│   ├── engines/
│   │   ├── ssh_engine/       # SSH tabanlı, Linux VE Windows hedefi destekler
│   │   │   └── local_collector/  # gui_v2.py, image_acquirer.py, tor_client.py, socks5.py, vb.
│   │   ├── ram_engine/       # Windows'ta yerel çalışan RAM imaj aracı (sadece derlenmiş hali, kaynak yok)
│   │   └── portable_kit/     # Taşınabilir kit'in HEDEF cihazda çalışan Tor tarafı
│   ├── launcher/              # tek giriş noktası: sol sidebar navigasyon, splash ekranı
│   ├── shared/
│   │   ├── theme.py           # ortak renk paleti (açık/koyu)
│   │   ├── i18n/strings.py    # launcher'ın dil tablosu (TR/EN)
│   │   ├── forensic_report.py # ortak rapor şeması (report.json + report.html + vaka geçmişi)
│   │   ├── onion_auth.py      # Tor client-auth anahtar üretimi (x25519)
│   │   ├── tor_binary.py      # gömülü Tor binary'sinin yolunu bulan ortak modül
│   │   ├── tz_display.py      # UTC yaninda yerel saat gosterimi (sadece report.html)
│   │   ├── version.py         # tek surum numarasi
│   │   ├── assets/            # logo (chameleon_icon.png, chameleon.ico)
│   │   └── bin/tor/windows/   # gömülü Tor binary'si (tor.exe)
│   ├── build.spec             # PyInstaller: tek Chameleon.exe üretir (operatör, tam paket)
│   └── build_target_kit.spec  # PyInstaller: ChameleonHedefKiti.exe üretir (SADECE hedef-taraf, hafif)
└── docs/roadmap.md        # planlanan işler
```

Tüm kod `src/` altında toplanıyor; `README.md`/`CONTRIBUTING.md`/
`.gitignore`/`requirements.txt` gibi standart proje dosyaları GitHub
konvansiyonuna uyması için kök dizinde kalıyor.

`ssh_engine` artık hem Linux hem Windows hedefi destekliyor (bkz.
aşağıdaki bölüm). `ram_engine` SSH gerektirmeden bu makinede çalışıyor —
ikisi tek koda indirilemeyecek kadar farklı, bilinçli olarak ayrı
tutuluyor. `src/launcher/chameleon_gui.py` hangisinin çalışacağını seçtiren
ince bir katman; her yöntemin kendi tanıtım sayfasını da o dosyadaki
`METHOD_INFO` sözlüğü barındırıyor.

`ram_engine` hakkında bilmen gerekenler: `src/engines/ram_engine/docs/`
içinde zaten var, tekrar etmiyoruz — özellikle `USAGE.md` (CLI
parametreleri) ve `PROJE_DOKUMANI.md` (mimari, IOCTL sözleşmesi, bilinen
sınırlamalar) faydalı. Kısaca: `process` modu sürücü gerektirmez ve
hemen çalışır, `full` modu (gerçek fiziksel RAM) imzasız bir test
sürücüsü kullandığı için hedef makinede Secure Boot kapatma + test
signing + reboot gerektiriyor.

## `ssh_engine` nasıl çalışıyor

- Uzak taraf (Linux): sadece Bash + standart Linux komutları (`dd`,
  `blockdev`, `lsblk`, `sha256sum`). Uzak taraf (Windows): PowerShell
  (`Get-Disk`, `Get-FileHash`, `Get-ChildItem`) — ham veri SSH metin
  kanalından bozulmadan geçmesi için Base64 ile taşınıyor. İkisinde de
  ayrı bir agent kurulmuyor, her işlem SSH üzerinden komutlarla yapılıyor.
- Lokal taraf: Python 3 + `paramiko`.
- Disk, ayarlanabilir boyutta parçalara bölünüp okunuyor (4/16/32/64 MB,
  varsayılan 4 MB — `dd bs=<N>M skip=K count=1`); bu hem hash
  doğrulamasının hem de kesintide kaldığı yerden devam edebilmenin
  (resume) temeli.
- Her parça diske yazılmadan önce SHA-256 ile doğrulanıyor; uyuşmazsa
  sadece o parça yeniden isteniyor.
- Bağlantı koparsa 1sn/2sn/4sn aralıklarla 3 kez yeniden bağlanmayı
  dener; olmazsa hangi parçadan devam edileceğini `logs/manifest_*.json`
  içinde saklayıp kontrollü şekilde durur.
- sudo parolası hiçbir zaman komut satırına yazılmıyor, SSH stdin
  kanalından iletiliyor (shell injection ve `ps aux`'ta görünme riskine
  karşı).
- Live modda write-blocker uygulanmıyor (disk aktif kullanımda olabilir);
  Offline modda uygulanıyor.
- Chain-of-custody logu düz metin, `logs/case_<tarih-saat>.log`, olay
  türleri sabit isimlerle (`EXAM_START`, `BLOCK_ACQUIRED`,
  `CONNECTION_LOST`, `HASH_MISMATCH`, `TOR_CONNECTION_ESTABLISHED`,
  `VPN_CONNECTION_USED` vb.). Her işlem sonunda bu log,
  `src/shared/forensic_report.py` tarafından vaka bilgileri, bütünlük ve
  sonuç bilgisiyle birlikte `report.json` + yazdırılabilir `report.html`
  olarak paketlenir; her rapor ayrıca `src/shared/data/case_history.json`
  içindeki ortak vaka geçmişine de eklenir (launcher'daki "Vaka Geçmişi"
  sayfası bunu okur).

### Bağlantı yöntemleri

Üç yöntem var, hepsi aynı SSH akışına bağlanıyor:

- **Doğrudan / Port Yönlendirme** — mevcut Host/Port alanları, ek kod yok.
- **VPN** — kod tarafında Doğrudan ile birebir aynı (operatör zaten VPN
  tünelinde), sadece delil zincirinde ayrıca işaretleniyor.
- **Tor (Acil Durum)** — hedef ağa hiç erişim olmadığında. `onion_auth.py`
  operatör için x25519 anahtar çifti üretir; `portable_kit/tor_manager.py`
  hedef cihazda gömülü Tor'u başlatıp `client_auth_v3` ile korunan bir v3
  Hidden Service kurar; `ssh_engine/local_collector/tor_client.py`
  operatör tarafında Tor'u SOCKS proxy modunda başlatıp
  `ONION_CLIENT_AUTH_ADD` ile özel anahtarı tanıtır; `socks5.py` paramiko'yu
  `.onion` adresine bağlamak için elle yazılmış minimal bir SOCKS5
  istemcisidir (PySocks gibi ek bağımlılık yok). Gömülü Tor binary'si
  `src/shared/bin/tor/windows/tor.exe` — yolu koda gömülü değil,
  `src/shared/tor_binary.py` üzerinden bulunuyor (`CHAMELEON_TOR_BINARY`
  ortam değişkeniyle override edilebilir).

## Tek exe paketleme (PyInstaller)

`cd src && pyinstaller build.spec` → `src/dist/Chameleon.exe`.
`gui_v2.py`/`ram_gui.py` gibi modüller derleme zamanında değil ÇALIŞMA
ZAMANINDA `sys.path`'e eklenip `import` ediliyor (bkz. `chameleon_gui.py`
`_show_ssh_engine`/`_show_ram_engine`) — bu yüzden PyInstaller'ın statik
analizi onların bağımlılıklarını (özellikle
`tkinter.scrolledtext/messagebox/filedialog` gibi alt modülleri)
OTOMATİK GÖREMEZ. `build.spec`'teki `hiddenimports` listesi bunu telafi
ediyor; yeni bir tkinter alt modülü ya da üçüncü parti kütüphane
eklenirse orası da güncellenmeli.

Ayrıca `cd src && pyinstaller build_target_kit.spec` →
`src/dist/ChameleonHedefKiti.exe`: sahaya götürülecek, SADECE hedef-taraf
(Bu Cihaz İnceleniyor) modunu içeren, operatör araçları (SSH/RAM
motorları, dolayısıyla `paramiko`) hiç paketlenmemiş ayrı bir derleme.
Giriş noktası `src/launcher/target_kit_main.py` — `CHAMELEON_TARGET_ONLY`
ortam değişkenini `chameleon_gui` import edilmeden önce ayarlar,
`ChameleonWindow` bunu görünce rol seçim ekranını atlayıp doğrudan hedef
sihirbazını açar. Aynı `chameleon_gui.py` kullanılır, kod tekrarlanmaz.

## Test yaklaşımı

`ssh_engine` gerçek bir SSH bağlantısı kurmadan, `run_command` /
`exec_command` taklit eden (mock) bir SSH nesnesiyle uçtan uca test
ediliyor — gerçek sunucu olmadan da akışın (write-block → chunk alma →
hash doğrulama → birleştirme → master hash) doğru çalıştığı
doğrulanabiliyor. Tor tarafı da aynı şekilde `stem`'in Controller/process
çağrıları mock'lanarak test ediliyor — gerçek Tor ağına bağlanmadan.
