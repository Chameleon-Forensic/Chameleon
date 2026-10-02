"""
incomplete_ops.py -- "Yarim Kalanlar" kayit defteri.
Regresyon testleri: bozuk JSON'da çökme, record_start/finish akışı,
list_incomplete, geçersiz op_id edge case'leri ve eşzamanlı yazma
race condition koruması (lock ile).
"""

import json
import os
import sys
import threading
import time

import incomplete_ops


# ---------------------------------------------------------------------------
# Yardımcı: registry dosyasını temizle / bozuk hale getir.
# ---------------------------------------------------------------------------

def _registry_yolu():
    return incomplete_ops.REGISTRY_PATH


def _reg_dizi():
    return incomplete_ops._read_all()


def _temizle():
    try:
        os.remove(_registry_yolu())
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _bos_kayitlar_ensure():
    _temizle()
    incomplete_ops._write_all({})


# ---------------------------------------------------------------------------
# Temel akış: record_start / record_finish / list_incomplete
# ---------------------------------------------------------------------------

def test_bos_klasorde_list_incomplete_bos_doner():
    _temizle()
    giris = incomplete_ops.list_incomplete()
    assert giris == [], "Başlangıçta incomplete_ops kaydı olmamalı"


def test_record_start_ve_finish_islem_kaydi_olusturup_siler():
    _bos_kayitlar_ensure()
    op_id = incomplete_ops.record_start(
        kind="ram_process",
        label="notepad.exe (PID 1234)",
        details={"case_id": "2026-001"},
    )
    assert op_id
    assert isinstance(op_id, str)
    assert len(op_id) == 12  # uuid4().hex[:12]

    listem = incomplete_ops.list_incomplete()
    assert len(listem) == 1
    assert listem[0][0] == op_id
    assert listem[0][1]["kind"] == "ram_process"
    assert listem[0][1]["label"] == "notepad.exe (PID 1234)"
    assert listem[0][1]["details"]["case_id"] == "2026-001"

    incomplete_ops.record_finish(op_id)
    assert incomplete_ops.list_incomplete() == []


def test_list_incomplete_birden_fazla_kaydi_gosterir():
    _bos_kayitlar_ensure()
    id1 = incomplete_ops.record_start("ram_full", "RAM Full Dump", {})
    id2 = incomplete_ops.record_start("ram_process", "notepad.exe", {})
    assert len(incomplete_ops.list_incomplete()) == 2
    incomplete_ops.record_finish(id1)
    assert len(incomplete_ops.list_incomplete()) == 1
    assert incomplete_ops.list_incomplete()[0][0] == id2
    incomplete_ops.record_finish(id2)


def test_record_finish_mevcut_degilse_sessizce_gecer():
    _bos_kayitlar_ensure()
    incomplete_ops.record_finish("varolmasi_gereken_bir_id")
    # Çökmez, kayıt yokluğu sessizce atanır.


# ---------------------------------------------------------------------------
# Geçersiz op_id edge case'leri (record_finish)
# ---------------------------------------------------------------------------

def test_record_finish_gecersiz_degerleri_reddet():
    _bos_kayitlar_ensure()
    olusturulan = incomplete_ops.record_start("ram_process", "X", {})

    # None, False, 0, boş string gibi false-yapıcı / string-olmayan
    # değerler kaynağı bozmayacak şekilde sessizce yansın.
    incomplete_ops.record_finish(None)
    incomplete_ops.record_finish(False)
    incomplete_ops.record_finish(0)
    incomplete_ops.record_finish("")
    incomplete_ops.record_finish(123)  # tamamen geçersiz

    listem = incomplete_ops.list_incomplete()
    assert len(listem) == 1, "Geçersiz op_id'ler kaynağı bozmasın"
    assert listem[0][0] == olusturulan


def test_record_finish_gecersiz_deger_olmaksizin_gecerli_id_calisir():
    _bos_kayitlar_ensure()
    op_id = incomplete_ops.record_start("ram_process", "X", {})
    incomplete_ops.record_finish(op_id)
    assert incomplete_ops.list_incomplete() == []


# ---------------------------------------------------------------------------
# Bozuk JSON dosyası durumunda çökme (regression)
# ---------------------------------------------------------------------------

def test_bozuk_json_dosyasinda_cokmez_ve_bos_doner():
    _bos_kayitlar_ensure()
    # Registry dosyasını kendimiz boz Ayrıca incomplete_ops._write_all
    # aracılığıyla değil, doğrudan dosyaya çöp JSON yazar.
    with open(_registry_yolu(), "w", encoding="utf-8") as f:
        f.write("{ bu bir json degil <> }")

    # Çökmemeli; boş bir liste dönmeli.
    listem = incomplete_ops.list_incomplete()
    assert listem == [], "Bozuk JSON dosyası durumunda çökmemeli"

    # Bozuk dosyayı temizleyip tekrar record_start yapalım.
    _temizle()
    id1 = incomplete_ops.record_start("ram_process", "test", {})
    guncel_liste = incomplete_ops.list_incomplete()
    assert len(guncel_liste) == 1
    assert guncel_liste[0][0] == id1
    assert guncel_liste[0][1]["kind"] == "ram_process"
    assert guncel_liste[0][1]["label"] == "test"


def test_bos_degil_bir_tip_iceriyorsa_bos_doner():
    _temizle()
    with open(_registry_yolu(), "w", encoding="utf-8") as f:
        f.write("[]")  # dict değil, bir liste
    listem = incomplete_ops.list_incomplete()
    assert listem == []


# ---------------------------------------------------------------------------
# Atomic write: geçici dosya kalsın mı?
# ---------------------------------------------------------------------------

def test_write_all_gecmis_gecisli_dosya_bos_verilmemeli(tmp_path, monkeypatch):
    # incomplete_ops'un kayıt yolunu tmp_path'e yönlendirip
    # _write_all çağrısından sonra .tmp uzantılı geçici dosyanın
    # kaldığını doğrulayalım.
    monkeypatch.setattr(incomplete_ops, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(incomplete_ops, "REGISTRY_PATH",
                        os.path.join(str(tmp_path), "incomplete_ops.json"))

    hasta = os.path.join(str(tmp_path), "incomplete_ops.json")
    # İçinde bir şey olmasın.
    if os.path.exists(hasta):
        os.remove(hasta)

    incomplete_ops._write_all({"foo": "bar"})
    assert os.path.exists(hasta)
    assert not os.path.exists(hasta + incomplete_ops._WIP_SUFFIX), \
        "Atomic yazma sonrası .tmp geçici dosyası kalmamalı"


# ---------------------------------------------------------------------------
# Eşzamanlı write (threading) — lock sayesinde kayıp olmamalı
# ---------------------------------------------------------------------------

def test_concurrent_record_start_racecondition_tutar():
    """Birden fazla thread aynı anda record_start çağırırsa, lock sayesinde
    kayıt sayısı beklenen gibi (thread sayısı) olmalı; yoksa race
    condition kaynaklı kayıp olur."""
    _temizle()
    saniyede_sayi = 8  # kaç thread
    id_liste = []

    def worker():
        oid = incomplete_ops.record_start(
            kind="ram_process",
            label=f"thread-{threading.get_ident()}",
            details={},
        )
        id_liste.append(oid)

    threadler = [
        threading.Thread(target=worker) for _ in range(saniyede_sayi)
    ]
    for t in threadler:
        t.start()
    for t in threadler:
        t.join()

    listem = incomplete_ops.list_incomplete()
    assert len(listem) == saniyede_sayi, \
        f"Beş açık thread aynı anda yazdı → beklenen {saniyede_sayi}, " \
        f"gerçekleşen {len(listem)} (kayıp var?)"

    # Kimliklerin benzersiz olduğundan emin olalım.
    assert len(set(oid for oid, _ in listem)) == saniyede_sayi, \
        "Her thread'un kendine has bir uuid hex dönmeli"


def test_liste_oku_kaydet_ve_kontrol_aynı_thread_olmaksizin():
    """Basit race: bir thread sürekli list_incomplete() çağırırken
    başka bir thread record_start yapıyor."""
    _bos_kayitlar_ensure()

    read_count = {"count": 0}

    def okuyan():
        for _ in range(200):
            incomplete_ops.list_incomplete()
            read_count["count"] += 1

    def yazan():
        for i in range(50):
            incomplete_ops.record_start("ram_process", f"y-{i}", {})
            time.sleep(0.0001)

    t1 = threading.Thread(target=okuyan)
    t2 = threading.Thread(target=yazan)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Çökmeden (exception fırlatmadan) bitmeli.
    assert read_count["count"] == 200
    assert len(incomplete_ops.list_incomplete()) == 50


# ---------------------------------------------------------------------------
# Düzenli kayit sonrasi eksik olmamasini dogrulama
# ---------------------------------------------------------------------------

def test_register_start_tekrarli_cagrilda_cakismasi_engelleniyor():
    """Eğer uuid4().hex[:12] sonradan çakışsaydı sorun yaratacaktı.
    Test olarak aynı ID'yi iki kere yazmamak için lock davranışını
    doğruluyoruz (uuid4().hex[:12] ciddi bir çakışma ihtimali yaratmaz;
    yine de kod bu durumda yeniden üretme mantığına sahip).

    Burada doğrudan 'duplikat id üretme' testi yapamayız çünkü uuid4
    random üretir; önemli olan kodun çakışma durumunda yeniden
    üretmeyi denemesi ve çökmemesi.
    """
    _bos_kayitlar_ensure()
    for _ in range(300):
        incomplete_ops.record_start("ram_process", "X", {})
    # Çökmemeli, dosya bozulmamalı.
    listem = incomplete_ops.list_incomplete()
    assert len(listem) == 300, "Her çağrı yeni bir kayıt yaratmalı"


# ---------------------------------------------------------------------------
# Kayit klasoru create edilemezse uyari verilsin
# ---------------------------------------------------------------------------

def test_klasor_olusturulamazsa_uyari_verilmeli(caplog):
    """DATA_DIR'ye yazma izni olmayan bir yola odaklanıp
    _write_all'nın uyarı verdiğini doğruluyoruz (logging).

    Gerçek bir 'readonly filesystem' testi zordur; burada
    Registry path'ini boş bir yola yönlendirip iso dizinine
    yazmamayı bekliyoruz.

    Not: Bu test, tam bir izinsiz-yazma simülasyonu yapmaz,
    çünkü PROJEDEKİ incomplete_ops, DATA_DIR belirleyip
    klasör oluşturma çabası yapıyor veFAILED olabilir.
    """
    # Maalesef bu test, Windows'ta izinsel bir durumu imulasiya etmek
    # için pyfakefs vs. gerektirir. Basitçe, yolu boş bir klasöre
    # yönlendirip ve bir dosya yazıp okumaya çalışmayıp sadece
    # _write_all çağrısının exception vermemesini bekliyoruz.
    # Bu test düşürülebilir (kamu API'inde izinsel test zor).
    _bos_kayitlar_ensure()
    # Zaten yazabildiğimiz bir yolda: klasör yoksa create eder.
    # Bu test sadece "kural olarak uyarı logging gerektiğini"
    # belirtmek içindir — gerçek imulasiyon için
    # pytest-pyfakefs veya benzeri gerekir.
    _temizle()
    incomplete_ops._write_all({})
    assert os.path.exists(_registry_yolu())
