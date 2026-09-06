#!/bin/bash
#
# disk_info.sh
# Uzak sunucudaki diskleri lsblk ile listeler.
#
# Kullanım: ./disk_info.sh
#
# NOT: Bu, MANUEL/TEK SEFERLİK TEST içindir (write_blocker.sh gibi).
# Gerçek main.py akışında disk listesi lokal taraftan, SSH üzerinden
# local_collector/ssh_connector.py'nin list_disks() fonksiyonuyla alınır
# — bu script'in uzak sunucuya kopyalanmasına gerek kalmaz.
#

set -u

if ! command -v lsblk >/dev/null 2>&1; then
    echo "[HATA] 'lsblk' komutu bulunamadi. util-linux paketi kurulu olmali." >&2
    exit 1
fi

lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT
exit $?
