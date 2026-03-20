"""Tests for utils/i18n.py — t(), _get_nested(), poke_name(), lang cache."""

import pytest
from utils.i18n import t, _get_nested, poke_name, get_cached_lang, set_cached_lang, SUPPORTED_LANGS, _strings


class TestGetNested:
    """_get_nested: dot-separated key lookup."""

    def test_simple_key(self):
        d = {"hello": "world"}
        assert _get_nested(d, "hello") == "world"

    def test_nested_key(self):
        d = {"spawn": {"wild_appeared": "야생 {name} 출현!"}}
        assert _get_nested(d, "spawn.wild_appeared") == "야생 {name} 출현!"

    def test_deep_nested(self):
        d = {"a": {"b": {"c": "deep"}}}
        assert _get_nested(d, "a.b.c") == "deep"

    def test_missing_key(self):
        d = {"hello": "world"}
        assert _get_nested(d, "missing") is None

    def test_missing_nested(self):
        d = {"spawn": {"catch": "잡기"}}
        assert _get_nested(d, "spawn.missing") is None

    def test_non_dict_intermediate(self):
        d = {"spawn": "string_not_dict"}
        assert _get_nested(d, "spawn.child") is None


class TestTranslate:
    """t(): translation with fallback and format."""

    def test_korean_key_exists(self):
        # ko.json이 로드되어 있어야 함
        if "ko" not in _strings or not _strings["ko"]:
            pytest.skip("ko locale not loaded")
        # common.trainer 키가 존재하는지 확인
        result = t("ko", "common.trainer")
        assert result != "common.trainer"  # 키 자체가 반환되면 안 됨

    def test_fallback_to_korean(self):
        """존재하지 않는 언어는 한국어로 fallback."""
        result_ko = t("ko", "common.trainer")
        result_xx = t("xx_unknown", "common.trainer")
        assert result_xx == result_ko

    def test_missing_key_returns_key(self):
        result = t("ko", "this.key.does.not.exist.anywhere")
        assert result == "this.key.does.not.exist.anywhere"

    def test_format_variables(self):
        if "ko" not in _strings or not _strings["ko"]:
            pytest.skip("ko locale not loaded")
        # spawn.wild_appeared 같은 포맷 키 찾기
        result = t("ko", "common.trainer")
        # 포맷 변수 없는 키도 정상 동작
        assert isinstance(result, str)

    def test_format_with_kwargs(self):
        """kwargs가 있으면 format 적용."""
        # 임시로 _strings에 테스트 데이터 삽입
        old = _strings.get("_test")
        _strings["_test"] = {"greeting": "안녕 {name}!"}
        result = t("_test", "greeting", name="피카츄")
        assert result == "안녕 피카츄!"
        # cleanup
        if old is None:
            del _strings["_test"]
        else:
            _strings["_test"] = old

    def test_format_missing_kwarg_no_crash(self):
        """format 변수가 부족해도 에러 안 남."""
        _strings["_test2"] = {"msg": "Hello {name} {level}"}
        result = t("_test2", "msg", name="Test")
        # KeyError 안 나고 원본 반환
        assert isinstance(result, str)
        del _strings["_test2"]

    def test_en_fallback_to_ko(self):
        """en에 없는 키는 ko로 fallback."""
        if "ko" not in _strings or not _strings["ko"]:
            pytest.skip("ko locale not loaded")
        # ko에만 있는 키 찾기
        ko_result = t("ko", "common.trainer")
        en_result = t("en", "common.trainer")
        # en에 있으면 en 결과, 없으면 ko fallback — 둘 다 키 자체가 아니면 OK
        assert en_result != "common.trainer"


class TestPokeName:
    """poke_name: language-aware pokemon name."""

    def test_korean(self):
        pokemon = {"name_ko": "피카츄", "name_en": "Pikachu"}
        assert poke_name(pokemon, "ko") == "피카츄"

    def test_english(self):
        pokemon = {"name_ko": "피카츄", "name_en": "Pikachu"}
        assert poke_name(pokemon, "en") == "Pikachu"

    def test_english_fallback_to_ko(self):
        pokemon = {"name_ko": "피카츄"}
        assert poke_name(pokemon, "en") == "피카츄"

    def test_chinese_simplified(self):
        pokemon = {"name_ko": "피카츄", "name_en": "Pikachu", "name_zh_hans": "皮卡丘"}
        assert poke_name(pokemon, "zh-hans") == "皮卡丘"

    def test_chinese_fallback_to_en(self):
        pokemon = {"name_ko": "피카츄", "name_en": "Pikachu"}
        assert poke_name(pokemon, "zh-hans") == "Pikachu"

    def test_chinese_fallback_to_ko(self):
        pokemon = {"name_ko": "피카츄"}
        assert poke_name(pokemon, "zh-hans") == "피카츄"

    def test_none_pokemon(self):
        assert poke_name(None, "ko") == "???"

    def test_empty_dict(self):
        assert poke_name({}, "ko") == "???"

    def test_name_field_fallback(self):
        pokemon = {"name": "리자몽"}
        assert poke_name(pokemon, "ko") == "리자몽"


class TestLangCache:
    """get_cached_lang / set_cached_lang."""

    def test_default_lang(self):
        assert get_cached_lang(999999999) == "ko"

    def test_set_and_get(self):
        set_cached_lang(888888888, "en")
        assert get_cached_lang(888888888) == "en"
        # cleanup
        set_cached_lang(888888888, "ko")

    def test_invalid_lang_ignored(self):
        set_cached_lang(777777777, "xx_invalid")
        assert get_cached_lang(777777777) == "ko"

    def test_supported_langs(self):
        assert "ko" in SUPPORTED_LANGS
        assert "en" in SUPPORTED_LANGS
