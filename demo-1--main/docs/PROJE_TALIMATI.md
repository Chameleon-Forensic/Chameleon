# PROJE TALİMATI (v2 — GÜNCEL VE NİHAİ)

Bu dosya, eski PROJE_TALIMATI.md'nin yerine geçer. Claude Code, kod
yazarken bu dosyanın dışına ÇIKMAMALIDIR. Belirsiz bir durumda kendi
kararını vermek yerine DURMALI ve soru sormalıdır.

---

## 1. PROJENİN TEK CÜMLELİK TANIMI

SSH üzerinden bağlanan, hedef diski önce yazılımsal write-blocker ile
kilitleyen, sonra 4 MB'lık parçalar (chunk) hâlinde okuyup ağ üzerinden
aktaran, her parçayı hash'leyen, bağlantı koptuğunda kaldığı parçadan
devam edebilen (resumable), tüm süreci chain-of-custody log'una yazan ve
Live/Offline modlarını destekleyen bir Bash + Python aracıdır.

Bu, projenin **v1.0 (MVP)** sürümüdür. v2.0 (RAM imajı, LVM/VSS snapshot,
sıfır-disk-ayak-izi) SADECE sunumda "gelecek vizyonu" olarak anlatılacak,
KOD OLARAK YAZILMAYACAKTIR.

## 2. KESİN TEKNİK SINIRLAR (DEĞİŞTİRİLEMEZ)

- Hedef işletim sistemi: SADECE Debian/Ubuntu tabanlı Linux.
- Uzak taraf dili: SADECE Bash + standart Linux komutları (dd, blockdev,
  lsblk, sha256sum, date, id). Uzak sunucuya Python, Go veya başka bir
  dil/derleyici KURULMASINI GEREKTİRME. Uzak sunucuda hiçbir agent/servis
  ÇALIŞTIRMA — her işlem, SSH üzerinden gönderilen tek satırlık komutlarla
  yapılmalı.
- Lokal taraf dili: Python 3 (standart kütüphane + paramiko).
- Bağlantı yöntemi: SADECE SSH (paramiko ile). Ek şifreleme katmanı
  (mTLS, özel TLS soketi vb.) KURMA — SSH zaten şifrelidir, yeterlidir.
- Disk okuma aracı: SADECE `dd`. `dc3dd`, `ewfacquire`, `guymager`,
  başka bir agent/binary KULLANMA.
- Chunk (parça) boyutu: 4 MB, `dd`'nin `bs=4M skip=N count=1` parametreleri
  ile tek tek çekilecek (N = blok numarası). Bu, resumable transfer'in de
  temelini oluşturur.
- Hash algoritması: SADECE SHA-256.
- Arayüz: SADECE komut satırı (CLI), ama menü tabanlı — kullanıcı komut
  ezberlemez, rakam seçip Enter'a basar (bkz. madde 6, main.py).
- Yeni üçüncü parti kütüphane eklemeden önce SOR. Varsayılan izinli
  kütüphaneler: `hashlib`, `paramiko`, `argparse` (sadece iç kullanım
  için, kullanıcıya parametre yazdırma), `logging`, `time`, `os`, `sys`,
  `json` (sadece manifest dosyası için, log dosyası için DEĞİL).
- Write-blocker SADECE offline modda ve SADECE hedefin işletim sisteminin
  kendi çalıştığı ana disk OLMAYAN disklerde uygulanır. Canlı/aktif
  kullanımda olan bir diske blockdev --setro asla otomatik uygulanmaz.

## 3. KAPSAM DIŞI (v1.0'DA YAZILMAYACAK)

- Go veya başka bir dilde uzak ajan
- mTLS / ek TLS katmanı
- Snapshot / LVM tabanlı edinim
- RAM/bellek imajı alma
- E01 (Expert Witness Format) formatı
- Grafik arayüz (GUI) veya web dashboard
- Çoklu kullanıcı / yetkilendirme sistemi
- Bulut depolama entegrasyonu
- Otomatik PDF rapor üretimi
- İmaj dosyasının şifrelenmesi

Bunlar istenirse SADECE sunumun "v2.0 Vizyonu" bölümünde metin olarak
anlatılır, kod yazılmaz.

## 4. KLASÖR YAPISI (SABİT — DEĞİŞTİRME)

```
adli-imaj-projesi/
├── remote_agent/
│   ├── write_blocker.sh      -> [BİTTİ] diski salt-okunur yapar/doğrular
│   └── disk_info.sh          -> [BİTTİ] lsblk ile disk listeleme (manuel/
│                                 referans script; gerçek akışta disk
│                                 listesi ssh_connector.list_disks() ile
│                                 lokal taraftan alınır)
├── local_collector/
│   ├── ssh_connector.py      -> SSH bağlantısı kurma (paramiko)
│   ├── image_acquirer.py     -> dd skip/count ile chunk okuma + resumable
│   │                             transfer + progress bar
│   ├── hash_verifier.py      -> SHA-256 chunk + toplam imaj hash hesaplama
│   ├── chain_of_custody.py   -> düz metin log modülü
│   └── main.py                 -> CLI menü, tüm modülleri birleştiren
│                                  giriş noktası
├── logs/
│   ├── case_<tarih-saat>.log       -> chain-of-custody logları
│   └── manifest_<tarih-saat>.json  -> resumable transfer ilerleme kaydı
├── docs/                      -> bu dosya + mimari diyagram + sunum notları
└── tests/                     -> varsa test scriptleri
```

**Not — iki ayrı `logs/` klasörü vardır (kasıtlı, karıştırılmamalı):**
- `remote_agent/logs/` : `write_blocker.sh` gibi UZAK sunucuda çalışan
  script'lerin logları. Script kendi konumunun içinde bu klasörü açar,
  proje köküne bağımlı değildir — çünkü uzak sunucuya sadece
  `remote_agent/` içeriği kopyalanır, projenin geri kalanı oraya gitmez.
  Bu log fiziksel olarak UZAK sunucuda kalır.
- `logs/` (proje kökü) : `chain_of_custody.py` gibi LOKAL tarafta çalışan
  Python modüllerinin logları. Bu log fiziksel olarak sizin
  bilgisayarınızda (lokal toplayıcının çalıştığı makinede) kalır.

Bu ayrım, iki tarafın fiziksel olarak farklı makinelerde çalışmasından
kaynaklanır; birleştirilmeyecektir.

## 5. GELİŞTİRME SIRASI (BU SIRAYLA İLERLE, ATLAMA)

1. ~~`remote_agent/write_blocker.sh`~~ — **BİTTİ**
2. ~~`local_collector/chain_of_custody.py`~~ — **BİTTİ**
3. ~~`local_collector/ssh_connector.py`~~ — **BİTTİ**
4. ~~`local_collector/image_acquirer.py`~~ — **BİTTİ** (manifest.json ile
   kalıcı resume + progress bar dahil, bkz. madde 6)
5. ~~`local_collector/hash_verifier.py`~~ — **BİTTİ**
6. ~~`local_collector/main.py`~~ — **BİTTİ** (image_acquirer entegre,
   resume sorusu soruyor, master hash sonunda opsiyonel doğrulama sunuyor)
7. Uçtan uca test (VirtualBox test sunucusunda)

Her adım bitince DUR, teste hazır olduğunu bildir, bir sonraki adıma
kendiliğinden geçme.

## 6. MODÜL DAVRANIŞ KURALLARI

### write_blocker.sh — TAMAMLANDI, değişiklik gerekmiyor

### chain_of_custody.py
- Format: DÜZ METİN (JSON/JSONL DEĞİL). Her satır: zaman damgası + olay
  türü + açıklama/detaylar.
- Loglanacak olay türleri (sabit isimler kullan):
  `EXAM_START`, `EXAM_RESUME`, `BLOCK_ACQUIRED`, `CONNECTION_LOST`,
  `CONNECTION_RESUMED`, `EXAM_END`, `EXAM_ERROR`, `WRITE_BLOCK_APPLIED`,
  `WRITE_BLOCK_SKIPPED`
- Log dosyası: `logs/case_<tarih-saat>.log`, her yeni çalıştırmada YENİ
  dosya (üzerine yazma).
- Tek başına test edilebilir küçük bir örnek (`if __name__ == "__main__"`
  içinde) ekle.

### ssh_connector.py
- paramiko ile SSH bağlantısı kurar, host/kullanıcı/anahtar dosyası
  parametre olarak alır.
- Bağlantı hatasında (kimlik doğrulama, zaman aşımı, host bulunamadı)
  try/except ile yakalar, anlamlı hata mesajı verir, çökmez.
- Basit komut çalıştırma fonksiyonu içermeli (örn. `run_command(cmd)`),
  `image_acquirer.py` bunu kullanacak.
- **Sudoers gereksinimi**: Test/demo sunucusunda, SSH ile bağlanılan
  kullanıcının `/etc/sudoers` dosyasında `blockdev` ve `dd` gibi komutlar
  için NOPASSWD tanımlı olması gerekir. Aksi halde otomatik akışta
  çalıştırılan `sudo ...` komutları parola isteyip akışı durdurur/asılı
  bırakabilir — `get_pty=True` sadece "no tty present" hatasını önler,
  parola isteme ihtiyacını ortadan kaldırmaz.

### write_block_helper.py
- `write_blocker.sh`'ı uzak sunucuya kopyalamadan, aynı mantığı
  (`blockdev --setro` + `--getro` doğrulama) `ssh_connector.py`'nin
  `run_command()` fonksiyonuyla doğrudan SSH komutu olarak çalıştırır.
- Sonucu `chain_of_custody.py`'ye `WRITE_BLOCK_APPLIED` ya da
  `EXAM_ERROR` olarak loglar.
- `main.py` tarafından SADECE Offline modda çağrılır; Live modda
  atlanır (bkz. madde 6, main.py bölümü).

### image_acquirer.py (chunk + resumable + progress bar) — TAMAMEN BİTTİ
- Disk boyutunu önce öğrenir: `blockdev --getsize64 /dev/DISK` — YAPILDI.
- Her chunk için SSH üzerinden veri ve hash'i İKİ AYRI adımda alıyor:
  önce `dd ... | sha256sum` ile uzak hash, sonra ham `dd` ile veri —
  sebebi: veri decode edilmeden (ham bayt) okunması gerektiği için
  `run_command()`'ın (utf-8 decode eden) arayüzü kullanılamıyor, ham okuma
  ayrı bir yoldan (`ssh.client.exec_command` doğrudan) yapılıyor.
- Her chunk diske yazılmadan ÖNCE `hash_verifier.verify_chunk()` ile
  doğrulanıyor; uyuşmazsa `HASH_MISMATCH` loglanıp blok yeniden isteniyor.
- Bağlantı koparsa: 3 kez, artan bekleme süresiyle (1sn, 2sn, 4sn) yeniden
  bağlanmayı dener (`ssh_connector.py`'nin `reconnect()`'i ile) — YAPILDI.
  3 denemede de olmazsa `CONNECTION_LOST`/`EXAM_ERROR` loglanıp kontrollü
  şekilde durur, hangi bloktan devam edileceği (`resume_from`) döner.
- Her chunk başarıyla alınıp doğrulandığında `BLOCK_ACQUIRED` loglanıyor —
  YAPILDI.
- **Resumable mantık (kalıcı)**: Her bloktan sonra `logs/manifest_<tarih-
  saat>.json` dosyasına o ana kadarki durum (`acquired_blocks`,
  `failed_blocks`, `block_paths`, `total_blocks`) yazılır. `main.py`,
  disk seçildikten sonra `find_incomplete_manifest()` ile aynı diske ait
  yarım kalmış bir manifest arar; bulursa "Yarım kalan bir işlem bulundu,
  devam edilsin mi? (E/H)" diye sorar — evet derse kaldığı bloktan devam
  eder. İşlem tüm bloklarla eksiksiz biterse manifest silinir.
- **Progress bar**: Her chunk sonrası `\r` ile aynı satırda güncellenen
  `İlerleme: %42 (8.4 GB / 20.0 GB)` formatında ilerleme gösterilir.
- **Parola güvenliği**: sudo parolası hiçbir komut metnine gömülmez;
  `ssh_connector.run_command()`'ın `sudo_password` parametresiyle
  doğrudan SSH stdin kanalından iletilir (shell injection ve `ps aux`'ta
  görünme riskine karşı).

### hash_verifier.py
- Chunk hash'lerini image_acquirer.py'den alır (fonksiyon çağrısıyla,
  ayrı bir dosyaya yazmadan, bellek içinde tutarak).
- Transfer bitince tüm imaj dosyasının toplam SHA-256'sını hesaplar
  (`hashlib` ile, dosyayı da chunk chunk okuyarak, tek seferde belleğe
  yükleme).
- Sonucu chain_of_custody.py üzerinden `EXAM_END` olayına final_hash
  olarak yazar.

### main.py (CLI menü)
Program açıldığında şu menüyü göstermeli:
```
=== Adli İmaj Alma Sistemi (v1.0) ===
1) Live Acquisition (sunucu çalışırken imaj al)
2) Offline Acquisition (kullanılmayan diskten imaj al)
3) Çıkış
Seçiminiz:
```
- Kullanıcı 1 veya 2 seçince: host, kullanıcı adı, SSH anahtar yolu,
  hedef disk gibi bilgileri TEK TEK, kısa sorularla ister (uzun bir
  komut satırı parametre listesi YAZDIRMA, argparse'ı sadece iç
  kullanım için tut, kullanıcıya doğrudan komut satırı parametresi
  yazdırma).
- Eğer aynı klasörde yarım kalmış bir manifest dosyası varsa, kullanıcıya
  "Yarım kalan bir işlem bulundu, devam edilsin mi? (E/H)" diye sorar.
- Snapshot seçeneği BU AŞAMADA menüde YER ALMAYACAK.

Live ve Offline modların write-blocker davranışı FARKLIDIR:
- Live Acquisition modunda: write-blocker UYGULANMAZ. Hedef disk aktif
  olarak işletim sistemi tarafından kullanıldığı için (loglar, swap,
  geçici dosyalar sürekli yazılıyor), diski salt-okunur yapmak sistemi
  bozabilir/kilitleyebilir. Bu modda disk sadece dd ile okunur, write-
  blocker adımı ATLANIR. chain_of_custody.py'ye "Live Acquisition -
  write-block uygulanmadı, hedef disk aktif kullanımdaydı" notu
  WRITE_BLOCK_APPLIED yerine WRITE_BLOCK_SKIPPED türünde loglanır.
- Offline Acquisition modunda: write-blocker UYGULANIR (write_blocker.sh
  çalıştırılır, WRITE_BLOCK_APPLIED olayı loglanır), çünkü hedef disk
  aktif kullanımda değildir, kilitlemek güvenlidir.
main.py, kullanıcının seçtiği moda göre bu farklı davranışı otomatik
uygulamalı, kullanıcıya ayrıca sormamalı.

## 7. HATA YÖNETİMİ GENEL KURALI

Her modül, karşılaşabileceği hataları (bağlantı kopması, yetki reddi,
disk bulunamadı, hash uyuşmazlığı) try/except ile yakalamalı, programı
çökertmemeli, hatayı hem terminale hem log dosyasına yazmalıdır. Sessizce
geçilen (pas geçilen) hiçbir hata olmamalı.

## 8. KOD STİLİ

- Kod içi yorumlar: Türkçe
- Değişken/fonksiyon isimleri: İngilizce
- Her fonksiyonun başında kısa bir docstring olmalı
- Gereksiz karmaşık/"akıllı" kod YAZMA, okunabilir ve basit tut

## 9. CLAUDE CODE'A GENEL UYARI

- Bu dosyada YAZMAYAN hiçbir özelliği kendi inisiyatifinle EKLEME.
- Emin olmadığın her noktada kod yazmadan ÖNCE SOR.
- Bir modülü bitirdiğinde özet ver (ne yazdın, nasıl test edilir), otomatik
  olarak bir sonraki modüle GEÇME.
- Test ortamı sanal makinedir (VirtualBox, Ubuntu Server). Gerçek/üretim
  sunucusu YOKTUR.
- Ekip arkadaşlarından gelen farklı mimarili kod parçaları (Go ajanı,
  Python uzak ajanı, argparse tabanlı CLI vb.) varsa, SADECE bu dosyadaki
  mimariye uyanları referans al, uymayanları KULLANMA.
