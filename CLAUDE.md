# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

200 satırlık kodu 50 satrda yaz gibi şeyler sçyledim ama description eklemen gereken yerlerde eklemeyi unutma ne yaptığını anlayabilmek için gerekli. 
# Proje: Chameleon

Birden fazla adli bilişim imaj alma yöntemini tek launcher altında birleştiren bir araç. Proje detayları, klasör yapısı ve `ssh_engine`'in teknik kısıtları için [CONTRIBUTING.md](CONTRIBUTING.md)'yi oku — bu dosya onu tekrar etmez, sadece kod yazarken dikkat edilmesi gerekenleri özetler.

## Kapsam

- `engines/ssh_engine/` — bizim geliştirdiğimiz, SSH+`dd` tabanlı motor. Serbestçe geliştirilebilir.
- `engines/ram_engine/` — başka bir kaynaktan (ders hocası) gelen, sadece derlenmiş hali verilen RAM imaj aracı. Kaynak kodu yok — içeriğini değiştiremeyiz, sadece `subprocess` ile çağırabiliriz. Windows-only.
- `launcher/`, `shared/` — motorları birleştiren ortak katman.

Not: Bu projeye başka bir ekiple (BitGuard) birleşme denendi, anlaşamayıp iptal edildi — o kod artık repoda yok. Geçmişi merak edersen `git log` yeterli, ayrıca not tutmaya gerek yok.

## Dosya haritası (hangi kod nerede)

| Aradığın şey | Dosya |
|---|---|
| SSH bağlantısı (paramiko, host key doğrulama) | `engines/ssh_engine/local_collector/ssh_connector.py` |
| Chunk okuma, hash doğrulama, resume/manifest mantığı (tam disk) | `engines/ssh_engine/local_collector/image_acquirer.py` |
| Tek dosya/klasör alma (find + sha256sum + cat, write-blocker'sız) | `engines/ssh_engine/local_collector/file_acquirer.py` |
| SHA-256 hesaplama/karşılaştırma (chunk + dosya bazlı) | `engines/ssh_engine/local_collector/hash_verifier.py` |
| write-blocker (`blockdev --setro`) çağrısı | `engines/ssh_engine/local_collector/write_block_helper.py` |
| Chain-of-custody log yazımı | `engines/ssh_engine/local_collector/chain_of_custody.py` |
| SSH motoru arayüzü (CTk, form + log paneli, disk/dosya mod seçimi) | `engines/ssh_engine/local_collector/gui_v2.py` |
| SSH motoru CLI (GUI'siz) | `engines/ssh_engine/local_collector/main.py` |
| Uzak sunucudaki write-blocker/disk listeleme scriptleri (referans, gerçek akışta kullanılmıyor) | `engines/ssh_engine/remote_agent/*.sh` |
| RAM motoru arayüzü (CTk, `RamImagerCLI.exe`'yi çağırır) | `engines/ram_engine/ram_gui.py` |
| RAM motoru (derlenmiş, kaynak yok) | `engines/ram_engine/cli/RamImagerCLI.exe` (vendor'in `RamImagerGUI.exe`'si artık kullanılmıyor) |
| Launcher (seçim ekranı, iki motoru da aynı pencerede gömer) | `launcher/chameleon_gui.py` |
| Ortak renk paleti | `shared/theme.py` |
| Dil tablosu (TR/EN) | `shared/i18n/strings.py` |
| Planlanan işler | `docs/roadmap.md` |

Yeni bir şey ararken önce bu tabloya bak, klasörleri baştan taramaya gerek yok.

## Kurallar

- Kod içi yorumlar Türkçe, değişken/fonksiyon isimleri İngilizce.
- Her modül tek başına çalıştırılabilir/test edilebilir kalmalı.
- Yeni üçüncü parti kütüphane eklemeden önce sor (şu an izinli: `paramiko`, `customtkinter`).
- `docs/roadmap.md`'de listelenmeyen büyük bir özelliği kendi başına ekleme; kapsam dışı bir şey fark edersen önce sor.
- Değişiklik yaptıktan sonra dur, ne yaptığını özetle — otomatik olarak bir sonraki işe geçme.
- `README.md` ve `CONTRIBUTING.md` insanlar için yazılıyor: buralara AI'ya yönelik talimat/meta yorum ekleme, o tür içerik burada (CLAUDE.md) kalsın.

## Arayüz

Launcher `customtkinter` ile yazılıyor, düz `tkinter` değil — varsayılan Tkinter görünümü kullanıcıyı rahatsız etti ("sıradan/AI görünümü" dendi). Renkler tek yerde: `shared/theme.py` (açık/koyu iki palet + `set_mode()`/`get_mode()`). Yeni bir ekran/bileşen eklerken renkleri buradan oku, dosya içinde tekrar tanımlama. Kullanıcı arayüzden açık/koyu tema arasında geçiş yapabiliyor (launcher üst barındaki geçiş düğmesi) — koyu tema VirtualBox Manager'ın görünümüne yakın olacak şekilde ayarlandı.

`ssh_engine/local_collector/gui_v2.py` da aynı paleti okuyor (`from theme import ...`, `chameleon/shared` dizinine göreli yol ile) — motor tek başına (`python gui_v2.py`) çalıştırıldığında da bulunamazsa dosyanın en üstündeki ASCII yedek renklere düşer.

Hata mesajları da tek tip/resmi kalıp olmasın ("İşlem başarısız oldu, kod: 1" gibi) — gündelik, kısa ve neyin ters gittiğini gerçekten anlatan cümleler kullan. Modal `messagebox` yerine, launcher'daki gibi sessiz bir durum satırı tercih edilebilir.

**Türkçe karakterler:** Arayüzde görünen her metin gerçek Türkçe karakterlerle yazılır (ğ, ş, ı, ö, ü, ç, İ) — "Baglan" değil "Bağlan", "Sifre" değil "Şifre". Tek istisna: bir metin başka bir dosyada regex/string eşleştirmeyle okunuyorsa (örn. `image_acquirer.py`'nin bastığı "İlerleme: %.." satırını `gui_v2.py`'nin regex'i okuyor), iki tarafı da birlikte güncelle ve regex'i hem `İ` hem `I` kabul edecek şekilde tolerant yaz (`[İI]lerleme` gibi) — aksi halde biri diğerini kırar.

## Test yaklaşımı

`ssh_engine` için gerçek SSH bağlantısı kurmadan, `run_command`/`exec_command`'ı taklit eden mock bir SSH nesnesiyle uçtan uca test yapılıyor (bkz. CONTRIBUTING.md → Test yaklaşımı). Değişiklik yapınca aynı yöntemle test et.
