"""
i18n dogrulamasi -- 6 dilin (tr/en/es/de/pt/fr) tamami, HER TR anahtarina
karsilik gelen bir cevirisi olmali; aksi halde t() sessizce tr'ye duser ve
eksik bir ceviri fark edilmeden kalir. Bu suit, gelecekte yeni bir dize
eklenip tum dillere cevrilmesi UNUTULDUGUNDA CI/test asamasinda hemen
yakalanmasini saglar.
"""

import strings


def test_all_languages_have_identical_keys():
    tr_keys = set(strings.STRINGS["tr"].keys())
    assert tr_keys, "STRINGS['tr'] bos olamaz"
    for lang, table in strings.STRINGS.items():
        keys = set(table.keys())
        missing = tr_keys - keys
        extra = keys - tr_keys
        assert not missing, f"{lang}: eksik anahtarlar: {missing}"
        assert not extra, f"{lang}: fazladan anahtarlar: {extra}"


def test_languages_list_matches_strings_dict():
    lang_codes = {code for code, _name in strings.LANGUAGES}
    assert lang_codes == set(strings.STRINGS.keys())


def test_t_falls_back_to_tr_for_unknown_language():
    assert strings.t("title", "xx") == strings.t("title", "tr")


def test_t_falls_back_to_raw_key_for_unknown_key():
    assert strings.t("__bilinmeyen_anahtar__", "tr") == "__bilinmeyen_anahtar__"


def test_t_formats_placeholders():
    result = strings.t("csv_saved", "en", path="C:/tmp/out.csv")
    assert "C:/tmp/out.csv" in result


def test_t_does_not_crash_on_malformed_format_kwargs():
    # csv_saved {path} bekliyor, yanlis bir kwarg verilirse cokmemeli
    result = strings.t("csv_saved", "en", wrong_kwarg="x")
    assert result  # bos olmayan bir seyler donmeli, exception degil


def test_no_empty_translations():
    """Bos string birakilmis bir ceviri, kullaniciya bos bir buton/etiket
    olarak gorunur -- fark edilmesi zor bir hata sinifi."""
    for lang, table in strings.STRINGS.items():
        for key, value in table.items():
            assert value != "", f"{lang}.{key} bos string"
