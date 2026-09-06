#!/bin/bash
#
# write_blocker.sh
# Hedef diski yazılımsal olarak salt-okunur (read-only) hale getirir,
# durumu doğrular ve sonucu hem ekrana hem log dosyasına yazar.
#
# Kullanım: ./write_blocker.sh /dev/sdX
#
# ============================================================================
# DİKKAT — BU SCRIPT SADECE MANUEL/TEK SEFERLİK TEST İÇİNDİR.
# main.py ÜZERİNDEN ÇALIŞAN GERÇEK AKIŞTA KULLANILMAZ, yerine
# local_collector/write_block_helper.py KULLANILIR (bu script'i uzak
# sunucuya kopyalamadan, doğrudan SSH komutlarıyla aynı işlemi yapar ve
# log'unu LOKAL bilgisayarda, chain_of_custody.py üzerinden tutar).
# Bu script'in kendi log'u UZAK SUNUCUDA oluşur (SCRIPT_DIR/logs) — bu,
# hedef diske değil ama uzak sunucunun dosya sistemine yazmak anlamına
# gelir; gerçek delil edinim akışında istenmeyen bir yan etkidir.
# ============================================================================

set -u

# --- Ayarlar ---
# Log klasörünü script'in kendi bulunduğu klasörün İÇİNDE oluşturur (bir üst
# klasöre çıkmaz). Böylece script tek başına (proje yapısının geri kalanı
# olmadan) başka bir sunucuya kopyalansa bile her zaman kendi yanında logs/
# klasörü açar, dışarıdaki klasör yapısına bağımlı olmaz.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/logs"
LOG_FILE="${LOG_DIR}/case_$(date +%Y%m%d-%H%M%S).log"

# --- Yardımcı fonksiyon: hem ekrana hem log dosyasına yazar ---
log_message() {
    local level="$1"
    local message="$2"
    local timestamp
    timestamp=$(date "+%Y-%m-%d %H:%M:%S")
    local line="[${timestamp}] [${level}] ${message}"

    echo "${line}"

    # Log klasörü yoksa oluştur (sessizce geçmemek için hata kontrolü var)
    mkdir -p "${LOG_DIR}" 2>/dev/null
    echo "${line}" >> "${LOG_FILE}" 2>/dev/null
}

# --- Parametre kontrolü ---
if [ $# -ne 1 ]; then
    log_message "HATA" "Kullanım: $0 /dev/DISK (disk yolu parametre olarak verilmedi)"
    exit 1
fi

DISK="$1"

# --- Yetki kontrolü (blockdev genelde root ister) ---
if [ "$(id -u)" -ne 0 ]; then
    log_message "HATA" "Bu script root yetkisi gerektirir (blockdev için). 'sudo' ile calistirin."
    exit 1
fi

# --- Disk var mi kontrolu ---
if [ ! -b "${DISK}" ]; then
    log_message "HATA" "Disk bulunamadi veya blok cihazi degil: ${DISK}"
    exit 1
fi

# --- blockdev komutu sistemde var mi kontrolu ---
if ! command -v blockdev >/dev/null 2>&1; then
    log_message "HATA" "'blockdev' komutu bulunamadi. util-linux paketi kurulu olmali."
    exit 1
fi

log_message "BILGI" "Write-blocker islemi basliyor: ${DISK}"

# --- Diski salt-okunur yap ---
if ! blockdev --setro "${DISK}" 2>>"${LOG_FILE}"; then
    log_message "HATA" "blockdev --setro basarisiz oldu: ${DISK} (yetki reddi olabilir)"
    exit 1
fi

# --- Durumu dogrula ---
RO_STATUS=$(blockdev --getro "${DISK}" 2>>"${LOG_FILE}")

if [ "${RO_STATUS}" = "1" ]; then
    log_message "BASARILI" "Diskseti salt-okunur olarak dogrulandi: ${DISK} (getro=1)"
    exit 0
else
    log_message "HATA" "Diskseti salt-okunur olarak dogrulanamadi: ${DISK} (getro=${RO_STATUS})"
    exit 1
fi
