# Chameleon

Adli bilişimde imaj almak için birden fazla yöntemi tek bir arayüzde toplayan araç.

- `engines/ssh_engine/` — SSH ile bağlanıp hedef sunucuda `dd` çalıştırarak imaj çeken yöntem. Kaynak: [adli-imaj-projesi](https://github.com/toprakkulekcioglu/adli-imaj-projesi) / [remote-forensic-imager](https://github.com/adli-imaj/remote-forensic-imager).
- `engines/ram_engine/` — hedef Windows makinede yerel olarak çalışan, fiziksel RAM imajı alan araç (kaynak kod dahil değil, sadece derlenmiş hali).

Her yöntem kendi haliyle korunuyor, launcher hangisinin çalıştırılacağını seçtiriyor. `ssh_engine` uzak bir Linux sunucuyu hedefler; `ram_engine` ise SSH gerektirmez, doğrudan bu makinede çalışır.

## Çalıştırma

```bash
pip install -r requirements.txt -r engines/ssh_engine/requirements.txt
python launcher/chameleon_gui.py
```

Açılan ekrandan dil ve yöntem seçilir, seçilen motor ayrı bir pencerede başlar. RAM motoru sadece Windows'ta çalışır; tam RAM imajı almak Yönetici yetkisi ve `engines/ram_engine/INSTALL.txt`'teki test-signing adımlarını gerektirir.

## Planlanan işler

Bkz. [docs/roadmap.md](docs/roadmap.md).
