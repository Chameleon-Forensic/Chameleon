# Chameleon

Bir bilgisayarın diskini, dosyalarını ya da belleğini (RAM) **bozmadan**,
**SHA-256 ile bütünlüğü kanıtlanabilir** şekilde kopyalayan bir adli
bilişim (digital forensics) aracı.

Birden fazla alma yöntemini tek bir arayüzde toplar:

- `engines/ssh_engine/` — ağ üzerinden erişilebilen bir **Linux ya da
  Windows** bilgisayardan SSH ile disk/dosya imajı alır. Hedefe nasıl
  ulaşıldığına göre üç bağlantı yöntemi destekler: Doğrudan/Port
  Yönlendirme, VPN, ve hiçbir ağ erişimi olmadığı en zor durumlar için
  Tor Hidden Service ("acil kapı").
- `engines/ram_engine/` — bu makinenin kendi belleğini (RAM) yerel olarak
  imaj alır (kaynak kodu dahil değil, sadece derlenmiş hali).
- `engines/portable_kit/` — SSH erişimi hiç olmayan hedefler için sahaya
  götürülen taşınabilir kit'in Tor tarafı.

Her yöntemin kendi tanıtım sayfası vardır (ne işe yaradığı, ne zaman
kullanılacağı, gerekenler, adım adım kullanım). Özelliklerin tam listesi
için: [docs/ozellikler.md](docs/ozellikler.md).

## Çalıştırma

**Geliştirme (kaynaktan):**

```bash
pip install -r requirements.txt -r engines/ssh_engine/requirements.txt
python launcher/chameleon_gui.py
```

**Son kullanıcı (tek exe):** `pyinstaller build.spec` ile üretilen
`dist/Chameleon.exe` çift tıkla açılır, Python kurulumu gerekmez.

Açılan pencerede sol menüden bir yöntem seçilir; RAM motoru sadece
Windows'ta çalışır, tam RAM imajı almak Yönetici yetkisi ve
`engines/ram_engine/INSTALL.txt`'teki test-signing adımlarını gerektirir.

## Planlanan işler

Bkz. [docs/roadmap.md](docs/roadmap.md).
