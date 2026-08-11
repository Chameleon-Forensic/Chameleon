# Chameleon

İki ayrı adli bilişim uzaktan imaj alma motorunu tek bir seçim ekranı
altında birleştiren araç.

- **SSH Motoru** (`engines/ssh_engine/`) — SSH + paramiko üzerinden uzak
  Linux sunucudan `dd`/`sha256sum` ile chunk bazlı imaj alma, yazılımsal
  write-blocker, kalıcı resume, chain-of-custody log.
- **BitGuard Motoru** (`engines/bitguard_engine/`) — TLS 1.3 soket
  üzerinden client/server modeliyle chunk bazlı self-healing transfer,
  JSON/TXT/HTML chain-of-custody raporu, E01/AFF4-benzeri konteynerler.

İki motor da kendi orijinal repolarından birebir taşındı ve bağımsız
çalışır (bkz. `docs/architecture.md`).

## Çalıştırma

```bash
pip install -r engines/ssh_engine/requirements.txt
python launcher/chameleon_gui.py
```

Açılan ekrandan hangi motorun başlatılacağı seçilir.

## Dokümantasyon

- Mimari kararlar: [`docs/architecture.md`](docs/architecture.md)
- Planlanan geliştirmeler: [`docs/roadmap.md`](docs/roadmap.md)
- SSH motorunun kapsam/kuralları: [`engines/ssh_engine/PROJE_TALIMATI.md`](engines/ssh_engine/PROJE_TALIMATI.md)
