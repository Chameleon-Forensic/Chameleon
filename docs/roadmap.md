# Yapılacaklar / fikirler

BitGuard'ın kendi projesinde planlayıp henüz yapmadığı şeyler:

- Gerçek EWF/E01 ve AFF4 desteği (`libewf`, `pyaff4`)
- SSH ile kurulumsuz uzak imajlama (güvenlik riski yüzünden kapatılmıştı)
- Büyük imajları `.001`/`.002` gibi parçalara bölme
- Gerçek PKI/CA doğrulaması (şu an TLS sadece şifreliyor)
- RAM imajlama (WinPmem/LiME gerekir, OS kullanıcı modundan erişimi bloke ediyor)
- Aynı anda birden fazla istemciden imaj alma
- .exe'yi kod imzalama (SmartScreen uyarısını kaldırmak için)
- Vaka geçmişi tutan merkezi bir veritabanı (SQLite)
- Ağ hızına göre değişen chunk boyutu (şu an sabit 4MB)
- Otomatik testler (pytest)

Bize ait, ek olarak düşündüğümüz:

- Çoklu dil desteği (TR/EN) — launcher'da başladı, motorların kendi arayüzüne henüz yayılmadı
- İki motorun ortak bir rapor formatı kullanması (şu an ikisi de kendi formatını üretiyor)
