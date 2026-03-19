"""utils/parse.py 단위 테스트 — 순수 함수, 외부 의존성 없음."""

from utils.parse import (
    _strip_emoji_prefix,
    parse_args,
    parse_number,
    parse_name_arg,
    parse_select_index,
)


# ── _strip_emoji_prefix ──

class TestStripEmojiPrefix:
    def test_emoji_prefix(self):
        assert _strip_emoji_prefix("📖 도감 파이리") == "도감 파이리"

    def test_no_emoji(self):
        assert _strip_emoji_prefix("밥 3") == "밥 3"

    def test_multiple_emoji(self):
        assert _strip_emoji_prefix("🔥⚡ 배틀") == "배틀"

    def test_empty(self):
        assert _strip_emoji_prefix("") == ""

    def test_whitespace(self):
        assert _strip_emoji_prefix("  📦 내포켓몬  ") == "내포켓몬"


# ── parse_args ──

class TestParseArgs:
    def test_single_arg(self):
        assert parse_args("밥 3") == ["3"]

    def test_multiple_args(self):
        assert parse_args("밥 피카츄 3") == ["피카츄", "3"]

    def test_no_args(self):
        assert parse_args("밥") == []

    def test_emoji_prefix(self):
        assert parse_args("📖 도감 파이리") == ["파이리"]

    def test_empty(self):
        assert parse_args("") == []


# ── parse_number ──

class TestParseNumber:
    def test_number(self):
        assert parse_number("밥 3") == 3

    def test_large_number(self):
        assert parse_number("📦 내포켓몬 15") == 15

    def test_not_number(self):
        assert parse_number("밥 피카츄") is None

    def test_no_arg(self):
        assert parse_number("밥") is None

    def test_mixed(self):
        """숫자+문자 혼합은 숫자가 아님."""
        assert parse_number("밥 3마리") is None


# ── parse_name_arg ──

class TestParseNameArg:
    def test_name(self):
        assert parse_name_arg("밥 피카츄") == "피카츄"

    def test_emoji_prefix(self):
        assert parse_name_arg("📖 도감 파이리") == "파이리"

    def test_number_is_not_name(self):
        assert parse_name_arg("밥 3") is None

    def test_no_arg(self):
        assert parse_name_arg("밥") is None

    def test_strip_selector(self):
        """#N 셀렉터는 제거하고 이름만 반환."""
        assert parse_name_arg("밥 망나뇽 #2") == "망나뇽"


# ── parse_select_index ──

class TestParseSelectIndex:
    def test_selector(self):
        assert parse_select_index("밥 망나뇽 #2") == 2

    def test_no_selector(self):
        assert parse_select_index("밥 피카츄") is None

    def test_selector_only(self):
        assert parse_select_index("밥 #1") == 1

    def test_selector_with_spaces(self):
        assert parse_select_index("밥 망나뇽 #3  ") == 3
