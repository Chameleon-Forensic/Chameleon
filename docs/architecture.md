# Chameleon Mimarisi

## Karar: iki ayrı motor, tek seçim ekranı

`ssh_engine` (SSH + paramiko üzerinden uzak sunucuda `dd`/`sha256sum`
çalıştırıp chunk çekme) ile `bitguard_engine` (TLS 1.3 soket üzerinden
client/server modeliyle chunk gönderme) tamamen farklı ağ modelleri
kullanıyor. Bu yüzden tek bir kod tabanına eritmek yerine, ikisi de
değiştirilmeden korunuyor; `launcher/chameleon_gui.py` kullanıcıya
hangisini çalıştıracağını soran ince bir seçim katmanı.

## Şu an ortak OLMAYAN, ileride ortaklaştırılması planlanan noktalar

- **Chain-of-custody rapor formatı** (`shared/coc_report/`, henüz boş)
- **Dil desteği** (`shared/i18n/`) — şu an sadece launcher'ın kendi
  metinlerini kapsıyor; motorların iç arayüzleri henüz buna bağlı değil,
  bu ayrı bir iş.

## Klasör yapısı

```
chameleon/
├── engines/
│   ├── ssh_engine/       # eski adli-imaj-projesi / remote-forensic-imager, birebir tasindi
│   └── bitguard_engine/  # eski Bit-Guard reposu, birebir tasindi
├── launcher/              # Chameleon'un tek giris noktasi
├── shared/                 # iki motorun ortaklasacagi (henuz ortaklasmamis) bilesenler
├── docs/                    # urun seviyesi dokumantasyon
└── tests/                   # henuz bos, otomatik test eklenmesi planlaniyor
```

## Neden birebir kopya, submodule değil

İki kişilik/küçük ekip için git submodule senkronizasyonu (ayrı commit,
ayrı push, `git submodule update` unutma riski) günlük geliştirmeyi
yavaşlatır. Bunun bedeli: kopyalanan dosyaların git geçmişi bu repoda
sıfırdan başlıyor — eski satır bazlı geçmiş gerekirse orijinal repolara
bakılmalı (`adli-imaj-projesi` / `remote-forensic-imager` ve `Bit-Guard`).
