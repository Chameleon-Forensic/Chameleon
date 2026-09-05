"""
verify_report.py
Chameleon GUI'sinden tamamen bagimsiz, tek basina calisan dogrulama araci.

Amac: "imaji alan ile dogrulayan ayni arac/kisi olmasin" ilkesi -- bir
savunma avukati, ikinci bir uzman ya da denetci, Chameleon'un kendi GUI'sine
hic guvenmeden, sadece report.json + imaj dosyasini kullanarak ayni
sonuca ulasabilmeli.

Iki bagimsiz kontrol yapar:
  1) report.json'un KENDISI sonradan degistirilmis mi? (report.json.sha256
     sidecar dosyasiyla karsilastirilir -- bkz. forensic_report.py save())
  2) report.json'daki output_path'te duran imaj dosyasi, yine report.json'da
     kayitli image_hash ile eslesiyor mu? (hash_verifier.verify_file ile
     yeniden hesaplanir, GUI'nin ilk hesapladigi degere degil sadece
     dosyanin KENDISINE bakilir)

Kullanim:
    python verify_report.py <report.json yolu>
"""

import argparse
import gzip
import hashlib
import json
import os
import sys

from hash_verifier import HashError, HashMismatchError, compare_digests, verify_file


def _print_progress(done, total):
    if total <= 0:
        return
    pct = done * 100 // total
    bar = "#" * (pct // 2) + "-" * (50 - pct // 2)
    sys.stdout.write(f"\r  [{bar}] %{pct:3d}")
    sys.stdout.flush()
    if done >= total:
        sys.stdout.write("\n")


def check_report_integrity(report_path):
    """report.json'un kendisinin sonradan degistirilip degistirilmedigini
    kontrol eder. Sidecar (.sha256) dosyasi yoksa (eski bir rapor,
    Chameleon'un bu ozellikten once uretilmis) kontrol atlanir -- rapor
    yine de dogrulanabilir, sadece bu ek garanti eksik olur."""
    sha_path = report_path + ".sha256"
    if not os.path.isfile(sha_path):
        print(f"[i] Sidecar hash dosyasi yok ({os.path.basename(sha_path)}), "
              f"report.json'un kendisi icin bu kontrol atlaniyor.")
        return None

    with open(sha_path, "r", encoding="utf-8") as f:
        expected = f.read().strip().split()[0].lower()

    with open(report_path, "rb") as f:
        actual = hashlib.sha256(f.read()).hexdigest()

    if actual == expected:
        print("[+] report.json bütünlüğü doğrulandı (kaydedildiğinden beri değişmemiş).")
        return True

    print("[!] UYARI: report.json, kaydedildiği andan beri DEĞİŞTİRİLMİŞ.")
    print(f"    Sidecar'daki hash : {expected}")
    print(f"    Dosyanın şu anki hash'i: {actual}")
    return False


def _hash_gzip_contents(path):
    """
    gzip ile sikistirilmis bir imajin, ACILMIS (ham) icerigin SHA-256'sini
    hesaplar -- image_hash HER ZAMAN ham icerige aittir (bkz.
    image_acquirer.compress_image), .gz dosyasinin kendi baytlarina degil.
    Dosya asla tam olarak diske/hafizaya acilmadan, akis (streaming)
    halinde okunur -- buyuk imajlarda bile sabit bellek kullanir. Acilmis
    boyut onceden bilinmedigi icin (gzip formati bunu guvenilir sekilde
    vermez) burada bir ilerleme cubugu gosterilmez.
    """
    hasher = hashlib.sha256()
    with gzip.open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def check_image_hash(report_path):
    """report.json'daki output_path + image_hash'e karsi, imaj dosyasinin
    GUNCEL halinin SHA-256'sini yeniden hesaplayip karsilastirir."""
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    image_path = report.get("result", {}).get("output_path")
    expected_hash = report.get("integrity", {}).get("image_hash")

    if not image_path:
        print("[HATA] report.json'da bir 'output_path' kaydı yok, imaj doğrulanamıyor.")
        return False
    if not expected_hash:
        print("[HATA] report.json'da bir 'image_hash' kaydı yok, imaj doğrulanamıyor.")
        return False
    if not os.path.isfile(image_path):
        print(f"[HATA] İmaj dosyası bulunamadı: {image_path}")
        return False

    print(f"[i] İmaj: {image_path}")
    print(f"[i] Rapordaki hash: {expected_hash}")

    is_gzip = image_path.endswith(".gz")
    if is_gzip:
        print("[i] İmaj gzip ile sıkıştırılmış -- açılıp (decompress) ham içerik hesaplanıyor...")
        try:
            actual_hash = _hash_gzip_contents(image_path)
        except (OSError, gzip.BadGzipFile) as exc:
            print(f"\n[HATA] {exc}")
            return False
        if not compare_digests(actual_hash, expected_hash):
            print(f"\n[!] DOĞRULAMA BAŞARISIZ — açılan içerik, rapordaki hash ile eşleşmiyor.")
            print(f"    Beklenen  : {expected_hash}")
            print(f"    Hesaplanan: {actual_hash}")
            return False
    else:
        print("[i] Dosya yeniden okunup SHA-256 hesaplanıyor...")
        try:
            verify_file(image_path, expected_hash, progress=_print_progress)
        except HashMismatchError as exc:
            print(f"\n{exc}")
            print("\n[!] DOĞRULAMA BAŞARISIZ — imaj, rapordaki hash ile eşleşmiyor.")
            return False
        except (HashError, OSError) as exc:
            print(f"\n[HATA] {exc}")
            return False

    print("\n[+] DOĞRULAMA BAŞARILI — imaj, rapordaki hash ile birebir eşleşiyor.")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="verify_report",
        description="Chameleon'dan bagimsiz rapor/imaj dogrulama araci",
    )
    parser.add_argument("report_json", help="Dogrulanacak report.json dosyasinin yolu")
    args = parser.parse_args(argv)

    if not os.path.isfile(args.report_json):
        print(f"[HATA] Dosya bulunamadı: {args.report_json}")
        return 1

    print("=" * 62)
    print("  CHAMELEON — BAĞIMSIZ RAPOR/İMAJ DOĞRULAMA")
    print("=" * 62)

    report_ok = check_report_integrity(args.report_json)
    print("-" * 62)
    image_ok = check_image_hash(args.report_json)
    print("=" * 62)

    if image_ok and report_ok is not False:
        print("SONUÇ: GEÇERLİ")
        return 0
    print("SONUÇ: GEÇERSİZ")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
