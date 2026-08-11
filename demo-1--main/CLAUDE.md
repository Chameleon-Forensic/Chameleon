# Proje: Adli Bilişim - Uzaktan İmaj Alma Sistemi

## Amaç
Uzaktaki bir Linux sunucudan, ağ üzerinden (SSH) disk imajı almak;
alım sırasında hash (SHA-256) ile veri bütünlüğünü garanti etmek;
yazılımsal write-blocker ile hedef diske yazma işlemlerini engellemek;
tüm işlemleri chain-of-custody (delil takip) log'una kaydetmek.

## Kapsam (3 günlük MVP)
- Live Acquisition (sunucu çalışırken imaj alma) — öncelik
- Yazılımsal write-blocker (blockdev --setro tabanlı)
- Chunk bazlı SHA-256 hash hesaplama + doğrulama
- İlerleme çubuğu (transfer yüzdesi)
- Hata yönetimi (bağlantı kopması, erişim reddi vb. çökmeden loglanır)
- Chain-of-custody log dosyası (zaman, IP, hash algoritması, süre, kullanıcı)
- Offline acquisition (simüle, mount edilmemiş disk senaryosu)
- Snapshot acquisition (LVM tabanlı) — vakit kalırsa

## Hedef İşletim Sistemi
- Uzak sunucu (agent çalışacak yer): Linux
- Lokal toplayıcı: OS bağımsız (Python)

## Klasör Yapısı
- remote_agent/     -> uzak sunucuda çalışan kod (disk okuma, write-blocker)
- local_collector/  -> lokal bilgisayarda çalışan kod (alma, hash doğrulama, arayüz)
- docs/             -> mimari diyagram, sunum notları
- logs/             -> örnek/test log çıktıları (gerçek imaj dosyaları BURAYA KONMAZ)

## Kod Kuralları
- Dil: Python 3
- Kod içi açıklamalar/yorumlar: Türkçe
- Değişken ve fonksiyon isimleri: İngilizce
- Her modül bağımsız test edilebilir olmalı (agent ve collector ayrı ayrı çalıştırılabilsin)

## Notlar
- Bu bir okul projesi (adli bilişim dersi), 3 günlük süre kısıtı var.
- Gerçek fiziksel write-blocker donanımı YOK, tamamen yazılımsal engel yapılıyor.
- Ekip: siber güvenlik + adli bilişim tecrübesi, elektrik-elektronik mühendisi,
  bilgisayar mühendisi + 3 kişi daha (5-6 kişilik ekip).
