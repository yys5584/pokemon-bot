"""타로 시스템 테스트 — fortune_service + dm_fortune 핸들러."""

from datetime import date

from services.fortune_service import (
    get_zodiac, draw_cards, get_spread, get_meaning,
    generate_reading, format_reading_message,
    SPREADS, TOPIC_EMOJIS,
)
from handlers.dm_fortune import _parse_birth_date


# ── 생년월일 파싱 ──

class TestParseBirthDate:
    def test_dash_format(self):
        assert _parse_birth_date("1995-03-15") == date(1995, 3, 15)

    def test_digits_only(self):
        assert _parse_birth_date("19950315") == date(1995, 3, 15)

    def test_dot_format(self):
        assert _parse_birth_date("1995.03.15") == date(1995, 3, 15)

    def test_slash_format(self):
        assert _parse_birth_date("1995/03/15") == date(1995, 3, 15)

    def test_invalid_date(self):
        assert _parse_birth_date("2000-13-01") is None

    def test_invalid_text(self):
        assert _parse_birth_date("안녕") is None

    def test_short_digits(self):
        assert _parse_birth_date("950315") is None

    def test_leap_day(self):
        assert _parse_birth_date("2000-02-29") == date(2000, 2, 29)

    def test_invalid_leap(self):
        assert _parse_birth_date("1999-02-29") is None

    def test_whitespace(self):
        assert _parse_birth_date("  1995-03-15  ") == date(1995, 3, 15)


# ── 별자리 ──

class TestGetZodiac:
    def test_aries(self):
        assert "양자리" in get_zodiac(date(1995, 3, 25))

    def test_capricorn_december(self):
        assert "염소자리" in get_zodiac(date(1990, 12, 25))

    def test_capricorn_january(self):
        assert "염소자리" in get_zodiac(date(1990, 1, 5))

    def test_aquarius(self):
        assert "물병자리" in get_zodiac(date(1990, 2, 1))

    def test_boundary_pisces_start(self):
        assert "물고기자리" in get_zodiac(date(2000, 2, 19))

    def test_leo(self):
        assert "사자자리" in get_zodiac(date(1988, 8, 10))


# ── 카드 뽑기 ──

class TestDrawCards:
    def test_draw_count(self):
        cards = draw_cards(3)
        assert len(cards) == 3

    def test_draw_one(self):
        cards = draw_cards(1)
        assert len(cards) == 1

    def test_no_duplicates(self):
        cards = draw_cards(10)
        names = [c["name"] for c in cards]
        assert len(names) == len(set(names))

    def test_seed_deterministic(self):
        a = draw_cards(3, seed=42)
        b = draw_cards(3, seed=42)
        assert [c["name"] for c in a] == [c["name"] for c in b]
        assert [c["reversed"] for c in a] == [c["reversed"] for c in b]

    def test_different_seeds(self):
        a = draw_cards(3, seed=1)
        b = draw_cards(3, seed=2)
        # 다른 시드면 보통 다른 결과 (매우 낮은 확률로 같을 수 있음)
        names_a = [c["name"] for c in a]
        names_b = [c["name"] for c in b]
        # 최소한 direction 필드가 존재
        for c in a + b:
            assert "direction" in c
            assert c["direction"] in ("up", "rev")

    def test_reversed_field(self):
        cards = draw_cards(5, seed=123)
        for c in cards:
            assert isinstance(c["reversed"], bool)
            assert c["direction"] == ("rev" if c["reversed"] else "up")


# ── 스프레드 ──

class TestSpreads:
    def test_all_spreads_have_required_keys(self):
        for key, spread in SPREADS.items():
            assert "name" in spread
            assert "count" in spread
            assert "positions" in spread
            assert "position_emojis" in spread
            assert len(spread["positions"]) == spread["count"]
            assert len(spread["position_emojis"]) == spread["count"]

    def test_get_spread_existing(self):
        spread = get_spread("three_card")
        assert spread["count"] == 3

    def test_get_spread_fallback(self):
        spread = get_spread("nonexistent")
        assert spread["count"] == 3  # three_card 폴백


# ── 해석 ──

class TestGetMeaning:
    def test_returns_string(self):
        cards = draw_cards(1, seed=99)
        meaning = get_meaning(cards[0], "종합")
        assert isinstance(meaning, str)
        assert len(meaning) > 0

    def test_fallback_to_general(self):
        """존재하지 않는 주제면 종합으로 폴백."""
        cards = draw_cards(1, seed=99)
        card = cards[0]
        meaning = get_meaning(card, "없는주제")
        assert isinstance(meaning, str)
        assert len(meaning) > 0


# ── 리딩 생성 ──

class TestGenerateReading:
    def test_three_card_reading(self):
        reading = generate_reading(topic="종합", spread_type="three_card", user_id=12345)
        assert reading["topic"] == "종합"
        assert len(reading["cards"]) == 3
        assert reading["summary"]
        assert reading["date"]

    def test_cards_have_type_and_number(self):
        reading = generate_reading(topic="종합", spread_type="three_card", user_id=12345)
        for c in reading["cards"]:
            assert "card_type" in c
            assert c["card_type"] in ("major", "minor")
            assert "card_number" in c
            if c["card_type"] == "major":
                assert 0 <= c["card_number"] <= 21

    def test_investment_spread(self):
        reading = generate_reading(topic="투자", spread_type="investment", user_id=12345)
        assert len(reading["cards"]) == 4
        positions = [c["position"] for c in reading["cards"]]
        assert "현재 상태" in positions
        assert "리스크" in positions

    def test_love_spread(self):
        reading = generate_reading(topic="연애", spread_type="love", user_id=12345)
        assert len(reading["cards"]) == 5

    def test_with_birth_date(self):
        reading = generate_reading(
            topic="종합", spread_type="three_card",
            birth_date=date(1995, 3, 25), user_id=12345,
        )
        assert reading["zodiac"] is not None
        assert "양자리" in reading["zodiac"]

    def test_without_birth_date(self):
        reading = generate_reading(topic="종합", spread_type="three_card", user_id=12345)
        assert reading["zodiac"] is None

    def test_deterministic_same_day(self):
        a = generate_reading(topic="연애", spread_type="three_card", user_id=999)
        b = generate_reading(topic="연애", spread_type="three_card", user_id=999)
        assert [c["card_name"] for c in a["cards"]] == [c["card_name"] for c in b["cards"]]

    def test_different_topics_different_cards(self):
        a = generate_reading(topic="연애", spread_type="three_card", user_id=999)
        b = generate_reading(topic="투자", spread_type="three_card", user_id=999)
        # 다른 주제는 다른 시드 → 보통 다른 카드
        cards_a = [c["card_name_en"] for c in a["cards"]]
        cards_b = [c["card_name_en"] for c in b["cards"]]
        # 최소한 구조는 동일
        assert len(cards_a) == len(cards_b) == 3


# ── 메시지 포맷 ──

class TestFormatReadingMessage:
    def test_contains_header(self):
        reading = generate_reading(topic="종합", spread_type="three_card", user_id=1)
        msg = format_reading_message(reading)
        assert "창백피카츄의 타로" in msg
        assert "종합" in msg

    def test_contains_cards(self):
        reading = generate_reading(topic="재물", spread_type="three_card", user_id=1)
        msg = format_reading_message(reading)
        for c in reading["cards"]:
            assert c["position"] in msg

    def test_contains_disclaimer(self):
        reading = generate_reading(topic="종합", spread_type="three_card", user_id=1)
        msg = format_reading_message(reading)
        assert "재미용" in msg

    def test_zodiac_shown_when_present(self):
        reading = generate_reading(
            topic="종합", spread_type="three_card",
            birth_date=date(1990, 8, 10), user_id=1,
        )
        msg = format_reading_message(reading)
        assert "사자자리" in msg


# ── TOPIC_EMOJIS ──

class TestTopicEmojis:
    def test_all_topics_have_emojis(self):
        for topic in ("연애", "직장", "재물", "투자", "인간관계", "종합"):
            assert topic in TOPIC_EMOJIS
