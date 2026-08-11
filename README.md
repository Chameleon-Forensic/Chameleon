# Chameleon

Adli bilişimde uzaktan disk imajı almak için iki farklı yöntemi bir arada sunan araç.

- `engines/ssh_engine/` — SSH ile bağlanıp hedef sunucuda `dd` çalıştırarak imaj çeken yöntem. Kaynak: [adli-imaj-projesi](https://github.com/toprakkulekcioglu/adli-imaj-projesi) / [remote-forensic-imager](https://github.com/adli-imaj/remote-forensic-imager).
- `engines/bitguard_engine/` — TLS soketi üzerinden client/server modeliyle çalışan yöntem. Kaynak: [Bit-Guard](https://github.com/MehmetEmin-Y/Bit-Guard).

İki yöntem de kendi haliyle korunuyor, aralarında kod birleştirme yapılmadı — SSH ve TLS soket mimarileri çok farklı olduğu için tek koda indirmek yerine `launcher/chameleon_gui.py` üzerinden hangisinin çalıştırılacağı seçiliyor.

## Çalıştırma

```bash
pip install -r engines/ssh_engine/requirements.txt
python launcher/chameleon_gui.py
```

Açılan ekrandan dil ve yöntem seçilir, seçilen motor ayrı bir pencerede başlar.

## Planlanan işler

Bkz. [docs/roadmap.md](docs/roadmap.md).
.
