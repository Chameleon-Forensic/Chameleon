"""
target_kit_main.py
Chameleon'un SADECE hedef-taraf (Bu Cihaz Inceleniyor) modu icin ayri,
daha hafif bir .exe'nin giris noktasi -- bkz. build_target_kit.spec.

Operatorun kullandigi tam Chameleon.exe (SSH/RAM motorlari, Bilgi
Merkezi, Vaka Gecmisi vb.) ile AYNI chameleon_gui.py'yi kullanir --
kod tekrarlanmaz. Tek fark: CHAMELEON_TARGET_ONLY ortam degiskeni,
chameleon_gui import edilmeden ONCE ayarlanir; ChameleonWindow bunu
gorunce rol secim ekranini hic gostermeden dogrudan hedef sihirbazini
acar (bkz. chameleon_gui.py -> ChameleonWindow.__init__).

Bu .exe'yi derleyen build_target_kit.spec, operator-only kodu
(engines/ssh_engine/local_collector/*, engines/ram_engine/*) hic
paketlemez -- bu yuzden dosya boyutu daha kucuk, ve sahadaki teknik
bilgisi olmayan kisi hicbir zaman ilgisiz bir SSH/RAM arac seti
gormez.
"""

import os
import sys

os.environ["CHAMELEON_TARGET_ONLY"] = "1"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chameleon_gui  # noqa: E402

if __name__ == "__main__":
    chameleon_gui.main()
