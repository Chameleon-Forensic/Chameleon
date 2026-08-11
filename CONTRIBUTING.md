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
├── engines/
│   ├── ssh_engine/       # SSH + dd tabanlı motor
│   └── bitguard_engine/  # TLS soket tabanlı motor (Bit-Guard projesinden)
├── launcher/              # tek giriş noktası, yöntem/dil seçim ekranı
├── shared/i18n/           # launcher'ın dil tablosu
└── docs/roadmap.md        # planlanan işler
```

İki motor bilinçli olarak ayrı tutuluyor: SSH+`dd` ile TLS soket çok
farklı ağ modelleri, tek koda indirmek yerine `launcher/chameleon_gui.py`
hangisinin çalışacağını seçiyor.

## `ssh_engine` nasıl çalışıyor

- Uzak taraf: sadece Bash + standart Linux komutları (`dd`, `blockdev`,
  `lsblk`, `sha256sum`). Uzak sunucuya ayrı bir agent kurulmuyor, her
  işlem SSH üzerinden tek satırlık komutlarla yapılıyor.
- Lokal taraf: Python 3 + `paramiko`.
- Disk 4 MB'lık parçalara (`dd bs=4M skip=N count=1`) bölünüp okunuyor;
  bu hem hash doğrulamasının hem de kesintide kaldığı yerden devam
  edebilmenin (resume) temeli.
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
  `CONNECTION_LOST`, `HASH_MISMATCH` vb.).

## Test yaklaşımı

`ssh_engine` gerçek bir SSH bağlantısı kurmadan, `run_command` /
`exec_command` taklit eden (mock) bir SSH nesnesiyle uçtan uca test
ediliyor — gerçek sunucu olmadan da akışın (write-block → chunk alma →
hash doğrulama → birleştirme → master hash) doğru çalıştığı
doğrulanabiliyor.
