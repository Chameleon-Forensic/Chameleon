# Proje: Chameleon

İki adli bilişim uzaktan imaj alma motorunu tek launcher altında birleştiren bir araç. Proje detayları, klasör yapısı ve `ssh_engine`'in teknik kısıtları için [CONTRIBUTING.md](CONTRIBUTING.md)'yi oku — bu dosya onu tekrar etmez, sadece kod yazarken dikkat edilmesi gerekenleri özetler.

## Kapsam

- `engines/ssh_engine/` — bizim geliştirdiğimiz, SSH+`dd` tabanlı motor. Serbestçe geliştirilebilir.
- `engines/bitguard_engine/` — başka bir ekibin (BitGuard) projesi, birebir taşındı. Buradaki koda dokunmadan önce sor; sahibi biz değiliz.
- `launcher/`, `shared/` — iki motoru birleştiren ortak katman, henüz erken aşamada.

## Kurallar

- Kod içi yorumlar Türkçe, değişken/fonksiyon isimleri İngilizce.
- Her modül tek başına çalıştırılabilir/test edilebilir kalmalı.
- Yeni üçüncü parti kütüphane eklemeden önce sor.
- `docs/roadmap.md`'de listelenmeyen büyük bir özelliği kendi başına ekleme; kapsam dışı bir şey fark edersen önce sor.
- Değişiklik yaptıktan sonra dur, ne yaptığını özetle — otomatik olarak bir sonraki işe geçme.
- `README.md` ve `CONTRIBUTING.md` insanlar için yazılıyor: buralara AI'ya yönelik talimat/meta yorum ekleme, o tür içerik burada (CLAUDE.md) kalsın.

## Test yaklaşımı

`ssh_engine` için gerçek SSH bağlantısı kurmadan, `run_command`/`exec_command`'ı taklit eden mock bir SSH nesnesiyle uçtan uca test yapılıyor (bkz. CONTRIBUTING.md → Test yaklaşımı). Değişiklik yapınca aynı yöntemle test et.
