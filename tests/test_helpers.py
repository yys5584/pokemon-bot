"""utils/helpers.py 순수 함수 단위 테스트 — DB 의존 함수 제외."""

from utils.helpers import (
    hearts_display,
    escape_html,
    truncate_name,
    _sub_tier_badge,
    pokemon_iv_total,
    iv_grade_tag,
    get_decorated_name,
)


# ── hearts_display ──

class TestHeartsDisplay:
    def test_full(self):
        assert hearts_display(5) == "♥♥♥♥♥"

    def test_empty(self):
        assert hearts_display(0) == "○○○○○"

    def test_partial(self):
        assert hearts_display(3) == "♥♥♥○○"

    def test_custom_max(self):
        assert hearts_display(2, max_hearts=3) == "♥♥○"


# ── escape_html ──

class TestEscapeHtml:
    def test_ampersand(self):
        assert escape_html("A & B") == "A &amp; B"

    def test_tags(self):
        assert escape_html("<b>bold</b>") == "&lt;b&gt;bold&lt;/b&gt;"

    def test_no_change(self):
        assert escape_html("hello") == "hello"

    def test_mixed(self):
        assert escape_html("a<b>&c") == "a&lt;b&gt;&amp;c"


# ── truncate_name ──

class TestTruncateName:
    def test_short(self):
        assert truncate_name("문유") == "문유"

    def test_exact(self):
        assert truncate_name("리자몽입니다", max_len=6) == "리자몽입니다"

    def test_truncated(self):
        assert truncate_name("아주긴이름의포켓몬", max_len=5) == "아주긴이름.."

    def test_default_5(self):
        assert truncate_name("123456") == "12345.."


# ── _sub_tier_badge ──

class TestSubTierBadge:
    def test_channel_owner(self):
        assert _sub_tier_badge("channel_owner") == "👑"

    def test_basic(self):
        assert _sub_tier_badge("basic") == "⭐"

    def test_none(self):
        assert _sub_tier_badge(None) == ""

    def test_unknown(self):
        assert _sub_tier_badge("premium") == ""


# ── pokemon_iv_total ──

class TestPokemonIvTotal:
    def test_normal(self):
        p = {"iv_hp": 10, "iv_atk": 20, "iv_def": 15, "iv_spa": 25, "iv_spdef": 12, "iv_spd": 30}
        assert pokemon_iv_total(p) == 112

    def test_no_iv(self):
        """iv_hp가 None이면 0."""
        p = {"iv_hp": None}
        assert pokemon_iv_total(p) == 0

    def test_max(self):
        p = {"iv_hp": 31, "iv_atk": 31, "iv_def": 31, "iv_spa": 31, "iv_spdef": 31, "iv_spd": 31}
        assert pokemon_iv_total(p) == 186


# ── iv_grade_tag ──

class TestIvGradeTag:
    def test_no_iv(self):
        """IV 없으면 빈 문자열."""
        assert iv_grade_tag({"iv_hp": None}) == ""

    def test_with_iv(self):
        p = {"iv_hp": 31, "iv_atk": 31, "iv_def": 31, "iv_spa": 31, "iv_spdef": 31, "iv_spd": 31}
        tag = iv_grade_tag(p)
        assert tag.startswith(" [")
        assert "]" in tag

    def test_show_total(self):
        p = {"iv_hp": 31, "iv_atk": 31, "iv_def": 31, "iv_spa": 31, "iv_spdef": 31, "iv_spd": 31}
        tag = iv_grade_tag(p, show_total=True)
        assert "186" in tag


# ── get_decorated_name ──

class TestGetDecoratedName:
    def test_plain(self):
        assert get_decorated_name("문유") == "문유"

    def test_with_username(self):
        result = get_decorated_name("문유", username="moon_yu")
        assert result == "@moon_yu"

    def test_sub_badge(self):
        result = get_decorated_name("문유", html=True, sub_tier="channel_owner")
        assert "👑" in result
        assert "문유" in result

    def test_html_escape(self):
        result = get_decorated_name("A<B>", html=True)
        assert "&lt;" in result
