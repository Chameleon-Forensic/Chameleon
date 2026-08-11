# Chameleon Roadmap

BitGuard ekibinin kendi projesinde "geliştirilebilir alan" olarak
işaretlediği, henüz **yapılmamış** maddeler (durumları ekip toplantısında
netleştirilecek):

1. Gerçek EWF/E01 ve AFF4 format uyumluluğu (`libewf`, `pyaff4` entegrasyonu)
2. SSH üzerinden kurulumsuz uzak imajlama — BitGuard'da güvenlik/karmaşıklık
   riski nedeniyle devre dışı bırakılmıştı. **Not:** Chameleon'da `ssh_engine`
   zaten bunu farklı bir yaklaşımla yapıyor; iki motor arasında kavramsal
   çakışma var mı, toplantıda konuşulmalı.
3. Büyük imajları `.001/.002...` şeklinde parçalara bölme (split imaging)
4. Gerçek PKI/CA tabanlı kimlik doğrulama (şu an TLS sadece şifreliyor,
   sertifika yetkilisi doğrulaması yok)
5. Bellek (RAM) imajlama — kullanıcı modundan doğrudan erişim OS tarafından
   engellendiği için WinPmem/LiME gibi çekirdek modülü gerektirir
6. Çoklu istemci / eşzamanlı imajlama desteği
7. Dijital kod imzalama (code signing) — Windows SmartScreen uyarısını
   kaldırmak için ticari sertifika gerekir
8. Merkezi vaka yönetimi (SQLite tabanlı "vaka geçmişi" görünümü)
9. Adaptif chunk boyutlandırma (şu an ikisi de sabit 4MB kullanıyor)
10. Otomatik test kapsamı (pytest ile birim/entegrasyon testleri — `tests/`
    klasörü bunun için ayrıldı, şu an boş)

## Chameleon'a özel yeni madde

- **Çoklu dil desteği (TR/EN)** — launcher seviyesinde başladı
  (`shared/i18n/strings.py`), motorların kendi arayüzlerine yayılması
  ayrı, daha büyük bir iş.

Hangi maddelerin bu ürünleşme aşamasında hedefleneceği ekip toplantısında
netleştirilecek; bu liste şimdilik sadece envanterdir, taahhüt değildir.
