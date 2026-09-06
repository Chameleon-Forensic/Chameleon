"""
hash_verifier.py — Bütünlük Doğrulama Modülü (Görev 3)
Forensic Remote Imager v1.0

Bu modül, adli bilişimde "delil bütünlüğü" (evidence integrity) prensibinin
kod karşılığıdır. Görevi tek cümleyle: uzak sunucudan okunan verinin, yerel
diske yazılan veriyle bit düzeyinde aynı olduğunu matematiksel olarak
kanıtlamak.

İki seviyede doğrulama yapılır:

  1) Blok seviyesi  — Uzak taraf her 4 MB'lık bloğun SHA-256 özetini
     `sha256sum` ile hesaplar. Yerel taraf aynı bloğu ağdan aldıktan sonra
     kendi özetini hesaplar. İkisi tutmuyorsa blok ağda bozulmuştur; o blok
     diske yazılmadan reddedilir ve yeniden istenir.

  2) İmaj seviyesi  — Aktarım bittiğinde imajın tamamının tek bir SHA-256
     özeti (master hash) alınır ve uzak taraftaki diskin özetiyle
     karşılaştırılır. Bu, "elimdeki imaj o diskin birebir kopyasıdır"
     iddiasının mahkemede savunulabilir dayanağıdır.

Bu modül hiçbir dış kütüphaneye bağımlı değildir — yalnızca Python standart
kütüphanesi kullanılır (hashlib, hmac). Böylece analist cihazında kurulum
gerektirmeden çalışır.

Diğer modüllerin kullanacağı arayüz:

    image_acquirer.py  ->  verify_chunk(veri, uzak_hash, index)
    main.py            ->  hash_file(imaj_yolu), verify_file(...)
    chain_of_custody.py->  HashResult.to_dict(), VerificationReport.to_dict()
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Mapping, Optional, Union

# --------------------------------------------------------------------------
# Sabitler
# --------------------------------------------------------------------------

#: Projede kullanılan özet algoritması. Roadmap v1.0 SHA-256 öngörür.
ALGORITHM = "sha256"

#: Roadmap'te tanımlı blok boyutu (dd bs=4M ile birebir aynı olmak zorunda).
CHUNK_SIZE = 4 * 1024 * 1024

#: Dosya özetlenirken kullanılan okuma tamponu. Blok boyutundan bağımsızdır;
#: sadece bellek kullanımını sınırlar.
READ_BUFFER_SIZE = 1 * 1024 * 1024

_HEX_DIGITS = frozenset("0123456789abcdef")

#: Kullanıcıya ilerleme bildirmek için: progress(islenen_bayt, toplam_bayt)
ProgressCallback = Callable[[int, int], None]

PathLike = Union[str, Path]


# --------------------------------------------------------------------------
# Hatalar
# --------------------------------------------------------------------------


class HashError(Exception):
    """Bu modülün ürettiği tüm hataların ortak atası."""


class InvalidDigestError(HashError):
    """Verilen metin geçerli bir SHA-256 özeti değil (uzunluk/karakter hatası)."""


class HashMismatchError(HashError):
    """
    Beklenen ve hesaplanan özetler tutmuyor.

    Adli açıdan kritik hata tipidir: tetiklendiği anda eldeki veri delil
    niteliğini kaybetmiştir. Çağıran modül bu hatayı yutmamalı, en azından
    chain-of-custody log'una işlemelidir.
    """

    def __init__(self, expected: str, actual: str, context: str = "") -> None:
        self.expected = expected
        self.actual = actual
        self.context = context
        where = f" [{context}]" if context else ""
        super().__init__(
            f"HASH UYUSMAZLIGI{where}\n"
            f"  Beklenen : {expected}\n"
            f"  Hesaplanan: {actual}"
        )


# --------------------------------------------------------------------------
# Veri yapıları
# --------------------------------------------------------------------------


def _utc_now() -> str:
    """Adli kayıtlarda yerel saat kullanılmaz; UTC ve ISO 8601 zorunludur."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class HashResult:
    """Tek bir özetleme işleminin sonucu ve delil kaydı için üstverisi."""

    algorithm: str
    digest: str
    byte_count: int
    source: str  # "local" (yerelde hesaplandi) | "remote" (uzaktan geldi)
    computed_at: str
    duration_seconds: float

    def to_dict(self) -> dict:
        """chain_of_custody.py'nin JSON'a yazabilmesi için sözlük hâli."""
        return {
            "algorithm": self.algorithm,
            "digest": self.digest,
            "byte_count": self.byte_count,
            "source": self.source,
            "computed_at": self.computed_at,
            "duration_seconds": round(self.duration_seconds, 4),
        }

    @property
    def throughput_mbps(self) -> float:
        """Saniyede kaç MB özetlendiği (rapor/sunum için)."""
        if self.duration_seconds <= 0:
            return 0.0
        return (self.byte_count / (1024 * 1024)) / self.duration_seconds

    def __str__(self) -> str:
        return f"{self.algorithm}:{self.digest} ({self.byte_count} bayt, {self.source})"


@dataclass(frozen=True)
class ChunkDigest:
    """İmaj dosyası içindeki tek bir 4 MB'lık bloğun özeti."""

    index: int
    digest: str
    byte_count: int
    offset: int


@dataclass
class VerificationReport:
    """
    İmajın tamamının manifest'e karşı yeniden doğrulanmasının sonucu.

    Aktarım bittikten sonra çalıştırılır: yerel imaj dosyası baştan sona
    okunur, her bloğun özeti manifest'te kayıtlı özetle karşılaştırılır ve
    aynı okuma sırasında imajın master hash'i de hesaplanır.
    """

    image_path: str
    algorithm: str
    chunk_size: int
    verified_at: str
    total_chunks: int = 0
    matched: list = field(default_factory=list)
    mismatched: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    unexpected: list = field(default_factory=list)
    master: Optional[HashResult] = None
    expected_master: Optional[str] = None
    duration_seconds: float = 0.0

    @property
    def master_ok(self) -> Optional[bool]:
        """Master hash karşılaştırması. Beklenen değer verilmediyse None."""
        if self.expected_master is None or self.master is None:
            return None
        return compare_digests(self.master.digest, self.expected_master)

    @property
    def ok(self) -> bool:
        """İmaj her yönüyle temiz mi? Rapordaki tek bakılacak alan budur."""
        return (
            not self.mismatched
            and not self.missing
            and not self.unexpected
            and self.master_ok is not False
        )

    def to_dict(self) -> dict:
        return {
            "image_path": self.image_path,
            "algorithm": self.algorithm,
            "chunk_size": self.chunk_size,
            "verified_at": self.verified_at,
            "duration_seconds": round(self.duration_seconds, 4),
            "result": "PASS" if self.ok else "FAIL",
            "total_chunks": self.total_chunks,
            "matched_count": len(self.matched),
            "mismatched": self.mismatched,
            "missing": self.missing,
            "unexpected": self.unexpected,
            "master_hash": self.master.to_dict() if self.master else None,
            "expected_master_hash": self.expected_master,
            "master_hash_ok": self.master_ok,
        }

    def summary(self) -> str:
        """Terminalde kullanıcıya gösterilecek insan okunur özet."""
        lines = [
            "=" * 62,
            "  BUTUNLUK DOGRULAMA RAPORU",
            "=" * 62,
            f"  Imaj          : {self.image_path}",
            f"  Algoritma     : {self.algorithm.upper()}",
            f"  Blok boyutu   : {self.chunk_size // (1024 * 1024)} MB",
            f"  Dogrulama ani : {self.verified_at}",
            f"  Sure          : {self.duration_seconds:.2f} sn",
            "-" * 62,
            f"  Toplam blok   : {self.total_chunks}",
            f"  Dogrulanan    : {len(self.matched)}",
            f"  Uyusmayan     : {len(self.mismatched)}",
            f"  Eksik         : {len(self.missing)}",
            f"  Fazladan      : {len(self.unexpected)}",
        ]
        if self.master:
            lines.append("-" * 62)
            lines.append(f"  Master hash   : {self.master.digest}")
            if self.expected_master:
                lines.append(f"  Beklenen      : {self.expected_master}")
                lines.append(f"  Eslesme       : {'EVET' if self.master_ok else 'HAYIR'}")
        lines.append("=" * 62)
        lines.append(f"  SONUC: {'GECERLI (PASS)' if self.ok else 'GECERSIZ (FAIL)'}")
        lines.append("=" * 62)
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Özet metni doğrulama ve karşılaştırma
# --------------------------------------------------------------------------


def _digest_length(algorithm: str = ALGORITHM) -> int:
    """Algoritmanın onaltılık gösterimdeki karakter sayısı (SHA-256 -> 64)."""
    try:
        return hashlib.new(algorithm).digest_size * 2
    except ValueError as exc:
        raise HashError(f"Desteklenmeyen algoritma: {algorithm}") from exc


def normalize_digest(value: str, *, algorithm: str = ALGORITHM) -> str:
    """
    Bir hash metnini karşılaştırmaya hazır hâle getirir.

    Uzak sunucudan gelen çıktıda baştaki/sondaki boşluklar veya büyük harf
    olabilir. Bunları temizlemeden karşılaştırmak, aslında aynı olan iki
    özeti "farklı" göstererek yanlış alarm üretir.

    Raises:
        InvalidDigestError: metin geçerli bir özet değilse.
    """
    if not isinstance(value, str):
        raise InvalidDigestError(
            f"Hash degeri metin olmali, {type(value).__name__} alindi."
        )

    cleaned = value.strip().lower()
    expected_len = _digest_length(algorithm)

    if len(cleaned) != expected_len:
        raise InvalidDigestError(
            f"{algorithm.upper()} ozeti {expected_len} karakter olmali, "
            f"{len(cleaned)} karakter alindi: {cleaned[:32]!r}..."
        )

    if not set(cleaned) <= _HEX_DIGITS:
        raise InvalidDigestError(
            f"Ozet yalnizca onaltilik karakter icermeli: {cleaned[:32]!r}..."
        )

    return cleaned


def parse_sha256sum_output(output: str, *, algorithm: str = ALGORITHM) -> str:
    """
    Uzak sunucudaki `sha256sum` komutunun çıktısından özeti ayıklar.

    Beklenen biçim:  "<64 karakter hash>  <dosya adi>"
    Örnek         :  "e3b0c44...b855  /dev/sda"

    SSH oturumunda çıktının başına uyarı satırları karışabildiği için
    (örn. "Warning: Permanently added..."), satırlar taranır ve özet gibi
    görünen ilk belirteç döndürülür.

    Raises:
        InvalidDigestError: çıktıda geçerli bir özet bulunamazsa.
    """
    if not output or not output.strip():
        raise InvalidDigestError("Uzak sunucudan bos sha256sum ciktisi geldi.")

    for line in output.splitlines():
        token = line.strip().lstrip("\\").split()  # GNU coreutils kacisli ad
        if not token:
            continue
        try:
            return normalize_digest(token[0], algorithm=algorithm)
        except InvalidDigestError:
            continue

    raise InvalidDigestError(
        f"sha256sum ciktisinda gecerli ozet bulunamadi: {output.strip()[:120]!r}"
    )


def compare_digests(left: str, right: str, *, algorithm: str = ALGORITHM) -> bool:
    """
    İki özeti güvenli biçimde karşılaştırır.

    `hmac.compare_digest` kullanılır: karşılaştırma süresi içeriğe bağlı
    değişmediği için zamanlama saldırılarına kapalıdır. Bu senaryoda saldırı
    riski düşüktür, ancak adli bir aracın karşılaştırmayı standart yöntemle
    yapması savunulabilirlik açısından tercih edilir.
    """
    return hmac.compare_digest(
        normalize_digest(left, algorithm=algorithm),
        normalize_digest(right, algorithm=algorithm),
    )


# --------------------------------------------------------------------------
# Özet hesaplama
# --------------------------------------------------------------------------


def hash_bytes(
    data: bytes,
    *,
    algorithm: str = ALGORITHM,
    source: str = "local",
) -> HashResult:
    """
    Bellekteki bir veri bloğunun özetini hesaplar.

    image_acquirer.py, ağdan aldığı 4 MB'lık bloğu diske YAZMADAN ÖNCE bu
    fonksiyonla özetler. Bozuk verinin imaj dosyasına hiç değmemesi esastır.
    """
    started = time.perf_counter()
    digest = hashlib.new(algorithm, data).hexdigest()
    return HashResult(
        algorithm=algorithm,
        digest=digest,
        byte_count=len(data),
        source=source,
        computed_at=_utc_now(),
        duration_seconds=time.perf_counter() - started,
    )


def hash_file(
    path: PathLike,
    *,
    algorithm: str = ALGORITHM,
    progress: Optional[ProgressCallback] = None,
    buffer_size: int = READ_BUFFER_SIZE,
) -> HashResult:
    """
    Bir dosyanın tamamının özetini hesaplar (master hash).

    Dosya parça parça okunur; 500 GB'lık bir imaj bile sabit bellekle
    özetlenir. `progress` verilirse her tampon sonrası çağrılır.

    Raises:
        FileNotFoundError: dosya yoksa.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Dosya bulunamadi: {path}")

    total = path.stat().st_size
    hasher = hashlib.new(algorithm)
    processed = 0
    started = time.perf_counter()

    with path.open("rb") as handle:
        while True:
            block = handle.read(buffer_size)
            if not block:
                break
            hasher.update(block)
            processed += len(block)
            if progress is not None:
                progress(processed, total)

    return HashResult(
        algorithm=algorithm,
        digest=hasher.hexdigest(),
        byte_count=processed,
        source="local",
        computed_at=_utc_now(),
        duration_seconds=time.perf_counter() - started,
    )


def iter_chunk_digests(
    path: PathLike,
    *,
    chunk_size: int = CHUNK_SIZE,
    algorithm: str = ALGORITHM,
) -> Iterator[ChunkDigest]:
    """
    Bir imaj dosyasını bloklara ayırıp her bloğun özetini sırayla üretir.

    Blok sınırları uzak taraftaki `dd bs=4M skip=N count=1` çağrılarıyla
    birebir örtüşür; bu yüzden `chunk_size` değeri image_acquirer.py ile
    aynı olmak zorundadır.

    Son blok, dosya boyutu tam katı değilse `chunk_size`'dan küçüktür.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Dosya bulunamadi: {path}")

    with path.open("rb") as handle:
        index = 0
        offset = 0
        while True:
            block = handle.read(chunk_size)
            if not block:
                break
            yield ChunkDigest(
                index=index,
                digest=hashlib.new(algorithm, block).hexdigest(),
                byte_count=len(block),
                offset=offset,
            )
            index += 1
            offset += len(block)


# --------------------------------------------------------------------------
# Doğrulama işlemleri
# --------------------------------------------------------------------------


def verify_chunk(
    data: bytes,
    expected_digest: str,
    *,
    index: Optional[int] = None,
    algorithm: str = ALGORITHM,
) -> HashResult:
    """
    Ağdan alınan bir bloğun, uzak taraftaki özetiyle aynı olduğunu doğrular.

    image_acquirer.py'nin her blok için çağıracağı fonksiyon budur.

    Returns:
        HashResult: doğrulama başarılıysa yerel özet (log'a yazılmak üzere).

    Raises:
        HashMismatchError: blok ağda bozulmuşsa. Çağıran taraf bu bloğu
            diske yazmamalı, aynı bloğu yeniden istemelidir.

    Örnek:
        >>> sonuc = verify_chunk(veri, uzak_hash, index=42)
        >>> manifest.kaydet(42, sonuc.digest)
    """
    result = hash_bytes(data, algorithm=algorithm)
    expected = normalize_digest(expected_digest, algorithm=algorithm)

    if not compare_digests(result.digest, expected, algorithm=algorithm):
        context = f"blok #{index}" if index is not None else "blok"
        raise HashMismatchError(expected, result.digest, context)

    return result


def verify_file(
    path: PathLike,
    expected_digest: str,
    *,
    algorithm: str = ALGORITHM,
    progress: Optional[ProgressCallback] = None,
) -> HashResult:
    """
    Yerel imajın master hash'ini, uzak diskin hash'iyle karşılaştırır.

    Aktarımın son adımıdır. Başarılı dönerse "elimdeki imaj, kaynak diskin
    birebir kopyasıdır" ifadesi kanıtlanmış olur.

    Raises:
        HashMismatchError: imaj kaynakla aynı değilse.
    """
    result = hash_file(path, algorithm=algorithm, progress=progress)
    expected = normalize_digest(expected_digest, algorithm=algorithm)

    if not compare_digests(result.digest, expected, algorithm=algorithm):
        raise HashMismatchError(expected, result.digest, f"imaj {Path(path).name}")

    return result


def verify_image_against_manifest(
    path: PathLike,
    expected_chunks: Mapping[int, str],
    *,
    chunk_size: int = CHUNK_SIZE,
    algorithm: str = ALGORITHM,
    expected_master: Optional[str] = None,
    progress: Optional[ProgressCallback] = None,
) -> VerificationReport:
    """
    Tamamlanmış imajı, manifest'teki blok özetlerine karşı baştan doğrular.

    Bu fonksiyon özellikle KESİNTİDEN SONRA DEVAM EDEN (resumable) aktarımlar
    için önemlidir: farklı oturumlarda, farklı zamanlarda yazılmış bloklar tek
    bir dosyada birleşir. Bu kontrol, o birleşimin bütün olarak sağlam
    olduğunu gösterir.

    Dosya YALNIZCA BİR KEZ okunur; aynı geçişte hem blok özetleri hem master
    hash hesaplanır. 500 GB'lık bir imajda ikinci bir tam okuma yapmamak
    doğrulama süresini yarıya indirir.

    Args:
        expected_chunks: manifest'ten gelen {blok_indeksi: ozet} eşlemesi.
        expected_master: uzak diskin master hash'i (varsa).

    Returns:
        VerificationReport: `ok` alanı tek bakılacak sonuçtur. Bu fonksiyon
        uyuşmazlıkta hata FIRLATMAZ — tüm blokları tarayıp eksiksiz bir rapor
        üretir, çünkü hangi blokların bozulduğunu bilmek adli açıdan
        "bozuldu" bilgisinden daha değerlidir.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Dosya bulunamadi: {path}")

    total_size = path.stat().st_size

    report = VerificationReport(
        image_path=str(path),
        algorithm=algorithm,
        chunk_size=chunk_size,
        verified_at=_utc_now(),
    )

    # Manifest JSON'dan geldiginde anahtarlar metin olabilir; int'e cevrilir.
    normalized_expected = {
        int(idx): normalize_digest(value, algorithm=algorithm)
        for idx, value in expected_chunks.items()
    }

    master = hashlib.new(algorithm)
    processed = 0
    seen: set = set()
    index = 0
    started = time.perf_counter()

    with path.open("rb") as handle:
        while True:
            block = handle.read(chunk_size)
            if not block:
                break

            offset = processed
            digest = hashlib.new(algorithm, block).hexdigest()
            master.update(block)  # ayni blok, ayni gecis: ikinci okuma yok

            seen.add(index)
            report.total_chunks += 1
            processed += len(block)
            if progress is not None:
                progress(processed, total_size)

            expected = normalized_expected.get(index)
            if expected is None:
                report.unexpected.append(
                    {"index": index, "digest": digest, "offset": offset}
                )
            elif compare_digests(digest, expected, algorithm=algorithm):
                report.matched.append(index)
            else:
                report.mismatched.append(
                    {
                        "index": index,
                        "offset": offset,
                        "expected": expected,
                        "actual": digest,
                    }
                )

            index += 1

    report.missing = sorted(set(normalized_expected) - seen)
    report.duration_seconds = time.perf_counter() - started
    report.master = HashResult(
        algorithm=algorithm,
        digest=master.hexdigest(),
        byte_count=processed,
        source="local",
        computed_at=_utc_now(),
        duration_seconds=report.duration_seconds,
    )
    if expected_master is not None:
        report.expected_master = normalize_digest(expected_master, algorithm=algorithm)

    return report


# --------------------------------------------------------------------------
# Komut satırı arayüzü — modülü tek başına test/demo etmek için
# --------------------------------------------------------------------------


def _print_progress(done: int, total: int) -> None:
    if total <= 0:
        return
    pct = done * 100 // total
    bar = "#" * (pct // 2) + "-" * (50 - pct // 2)
    mb = done / (1024 * 1024)
    sys.stderr.write(f"\r  [{bar}] %{pct:3d}  ({mb:.1f} MB)")
    sys.stderr.flush()
    if done >= total:
        sys.stderr.write("\n")


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hash_verifier",
        description="Forensic Remote Imager — butunluk dogrulama araci",
    )
    parser.add_argument("dosya", help="Ozeti alinacak / dogrulanacak dosya")
    parser.add_argument(
        "-e",
        "--beklenen",
        help="Beklenen SHA-256 ozeti. Verilirse dogrulama yapilir.",
    )
    parser.add_argument(
        "-b",
        "--bloklar",
        action="store_true",
        help="Her 4 MB'lik blogun ozetini ayri ayri listele",
    )
    parser.add_argument(
        "-s",
        "--sessiz",
        action="store_true",
        help="Ilerleme cubugunu gizle",
    )
    args = parser.parse_args(argv)

    progress = None if args.sessiz else _print_progress

    try:
        if args.bloklar:
            print(f"{'INDEKS':>8}  {'OFFSET':>14}  {'BOYUT':>10}  OZET")
            for chunk in iter_chunk_digests(args.dosya):
                print(
                    f"{chunk.index:>8}  {chunk.offset:>14}  "
                    f"{chunk.byte_count:>10}  {chunk.digest}"
                )
            return 0

        if args.beklenen:
            result = verify_file(args.dosya, args.beklenen, progress=progress)
            print("\nDOGRULAMA BASARILI — dosya beklenen ozetle birebir ayni.")
            print(f"  SHA-256 : {result.digest}")
            print(f"  Boyut   : {result.byte_count} bayt")
            print(f"  Hiz     : {result.throughput_mbps:.1f} MB/sn")
            return 0

        result = hash_file(args.dosya, progress=progress)
        print(f"\n  SHA-256 : {result.digest}")
        print(f"  Boyut   : {result.byte_count} bayt")
        print(f"  Zaman   : {result.computed_at}")
        print(f"  Hiz     : {result.throughput_mbps:.1f} MB/sn")
        return 0

    except HashMismatchError as exc:
        print(f"\n{exc}", file=sys.stderr)
        print("\nDOGRULAMA BASARISIZ — dosya kaynakla ayni degil.", file=sys.stderr)
        return 2
    except (HashError, FileNotFoundError, OSError) as exc:
        print(f"\nHATA: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
