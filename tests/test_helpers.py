"""utils/helpers.py 순수 함수 단위 테스트 — DB 의존 함수 제외."""

from utils.helpers import (
    hearts_display,
    escape_html,
    truncate_name,
    _sub_tier_badge,
    pokemon_iv_total,
    iv_grade,
    iv_grade_tag,
    get_decorated_name,
    rarity_display,
    rarity_badge,
    rarity_badge_label,
    _type_emoji,
    type_badge,
    ball_emoji,
    icon_emoji,
    shiny_emoji,
    resolve_title_badge,
    time_ago,
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

    def test_with_title(self):
        result = get_decorated_name("문유", title="첫 배틀", title_emoji="squirtle", html=True)
        assert "첫 배틀" in result
        assert "문유" in result

    def test_ranked_badge(self):
        result = get_decorated_name("문유", html=True, ranked_badge="🥉")
        assert "🥉" in result


# ── rarity_display ──

class TestRarityDisplay:
    def test_common(self):
        result = rarity_display("common")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_legendary(self):
        result = rarity_display("legendary")
        assert isinstance(result, str)

    def test_unknown(self):
        result = rarity_display("nonexistent")
        assert isinstance(result, str)


# ── rarity_badge ──

class TestRarityBadge:
    def test_returns_string(self):
        assert isinstance(rarity_badge("common"), str)
        assert isinstance(rarity_badge("epic"), str)

    def test_unknown_rarity(self):
        result = rarity_badge("unknown_rarity")
        assert isinstance(result, str)


# ── rarity_badge_label ──

class TestRarityBadgeLabel:
    def test_returns_string(self):
        result = rarity_badge_label("common")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_label(self):
        from utils.helpers import RARITY_LABEL
        for rarity, label in RARITY_LABEL.items():
            result = rarity_badge_label(rarity)
            assert label in result


# ── _type_emoji ──

class TestTypeEmoji:
    def test_fire(self):
        result = _type_emoji("fire")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_unknown_type(self):
        result = _type_emoji("nonexistent_type")
        assert isinstance(result, str)


# ── type_badge ──

class TestTypeBadge:
    def test_known_pokemon(self):
        # 리자몽(6) = fire/flying
        result = type_badge(6)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_unknown_pokemon_with_fallback(self):
        result = type_badge(99999, fallback_type="water")
        assert isinstance(result, str)

    def test_unknown_pokemon_no_fallback(self):
        result = type_badge(99999)
        assert result == ""


# ── ball_emoji ──

class TestBallEmoji:
    def test_masterball(self):
        result = ball_emoji("masterball")
        assert isinstance(result, str)

    def test_unknown_ball(self):
        result = ball_emoji("nonexistent")
        assert isinstance(result, str)


# ── icon_emoji ──

class TestIconEmoji:
    def test_known_icon(self):
        result = icon_emoji("battle")
        assert isinstance(result, str)

    def test_unknown_icon(self):
        result = icon_emoji("nonexistent_icon")
        assert isinstance(result, str)


# ── shiny_emoji ──

class TestShinyEmoji:
    def test_returns_string(self):
        result = shiny_emoji()
        assert isinstance(result, str)
        assert len(result) > 0


# ── iv_grade ──

class TestIvGrade:
    def test_max(self):
        assert iv_grade(186) == "S"

    def test_zero(self):
        assert iv_grade(0) == "D"


# ── time_ago ──

class TestTimeAgo:
    def test_invalid_input(self):
        assert time_ago("invalid") == ""

    def test_none_input(self):
        assert time_ago(None) == ""

    def test_datetime_input(self):
        from datetime import datetime, timedelta
        from unittest.mock import patch
        fake_now = datetime(2026, 3, 20, 12, 0, 0)
        with patch("config.get_kst_now", return_value=fake_now):
            recent = fake_now - timedelta(seconds=30)
            result = time_ago(recent)
            assert "30초 전" == result

    def test_minutes_ago(self):
        from datetime import datetime, timedelta
        from unittest.mock import patch
        fake_now = datetime(2026, 3, 20, 12, 0, 0)
        with patch("config.get_kst_now", return_value=fake_now):
            past = fake_now - timedelta(minutes=5)
            result = time_ago(past)
            assert result == "5분 전"

    def test_hours_ago(self):
        from datetime import datetime, timedelta
        from unittest.mock import patch
        fake_now = datetime(2026, 3, 20, 12, 0, 0)
        with patch("config.get_kst_now", return_value=fake_now):
            past = fake_now - timedelta(hours=3)
            result = time_ago(past)
            assert result == "3시간 전"

    def test_yesterday(self):
        from datetime import datetime, timedelta
        from unittest.mock import patch
        fake_now = datetime(2026, 3, 20, 12, 0, 0)
        with patch("config.get_kst_now", return_value=fake_now):
            past = fake_now - timedelta(days=1)
            result = time_ago(past)
            assert result == "어제"

    def test_days_ago(self):
        from datetime import datetime, timedelta
        from unittest.mock import patch
        fake_now = datetime(2026, 3, 20, 12, 0, 0)
        with patch("config.get_kst_now", return_value=fake_now):
            past = fake_now - timedelta(days=5)
            result = time_ago(past)
            assert result == "5일 전"

    def test_iso_string_input(self):
        from datetime import datetime
        from unittest.mock import patch
        fake_now = datetime(2026, 3, 20, 12, 0, 0)
        with patch("config.get_kst_now", return_value=fake_now):
            result = time_ago("2026-03-20T11:00:00")
            assert result == "1시간 전"


# ── resolve_title_badge ──

class TestResolveTitleBadge:
    def test_valid_icon_key(self):
        result = resolve_title_badge("pikachu")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_raw_emoji_passthrough(self):
        result = resolve_title_badge("🔥")
        assert result == "🔥"

    def test_with_title_name_lookup(self):
        result = resolve_title_badge("", "첫 배틀")
        assert isinstance(result, str)
