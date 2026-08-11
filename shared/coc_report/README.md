# Ortak Chain-of-Custody Rapor Formatı (planlanan, henüz YOK)

Şu an iki motor kendi rapor formatını üretiyor:

- `ssh_engine`: düz metin log (`logs/case_<tarih-saat>.log`)
- `bitguard_engine`: JSON + TXT + HTML rapor üçlüsü

Hedef: ikisinin de aynı ortak şemadan (muhtemelen JSON) üretmesi, böylece
Chameleon tek bir ürün gibi tek tip rapor çıkarsın. Bu henüz
**yapılmadı** — hangi alanların ortak şemada olacağı (host, disk, hash
algoritması, süre, kullanıcı, olay listesi...) ekip toplantısında
netleştirilmeli. Bkz. `docs/architecture.md`.
