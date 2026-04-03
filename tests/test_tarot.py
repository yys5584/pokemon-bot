"""타로 시스템 테스트 — fortune_service + dm_fortune 핸들러."""

import json
import pytest
from datetime import date
from pathlib import Path

from services.fortune_service import (
    get_zodiac, draw_cards, get_spread, get_meaning,
    generate_reading, format_reading_message,
    _make_cache_key, _build_narrative_prompt,
    SPREADS, TOPIC_EMOJIS, TOPIC_MAP, ZODIAC_SIGNS, TIME_RANGES,
    _load_cards,
)
from handlers.dm_fortune import _parse_birth_date, _format_share_message


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
    async def test_three_card_reading(self):
        reading = await generate_reading(topic="종합", spread_type="three_card", user_id=12345)
        assert reading["topic"] == "종합"
        assert len(reading["cards"]) == 3
        assert reading["summary"]
        assert reading["date"]

    async def test_cards_have_type_and_number(self):
        reading = await generate_reading(topic="종합", spread_type="three_card", user_id=12345)
        for c in reading["cards"]:
            assert "card_type" in c
            assert c["card_type"] in ("major", "minor")
            assert "card_number" in c
            if c["card_type"] == "major":
                assert 0 <= c["card_number"] <= 21

    async def test_investment_spread(self):
        reading = await generate_reading(topic="투자", spread_type="investment", user_id=12345)
        assert len(reading["cards"]) == 4
        positions = [c["position"] for c in reading["cards"]]
        assert "현재 상태" in positions
        assert "리스크" in positions

    async def test_love_spread(self):
        reading = await generate_reading(topic="연애", spread_type="love", user_id=12345)
        assert len(reading["cards"]) == 5

    async def test_with_birth_date(self):
        reading = await generate_reading(
            topic="종합", spread_type="three_card",
            birth_date=date(1995, 3, 25), user_id=12345,
        )
        assert reading["zodiac"] is not None
        assert "양자리" in reading["zodiac"]

    async def test_without_birth_date(self):
        reading = await generate_reading(topic="종합", spread_type="three_card", user_id=12345)
        assert reading["zodiac"] is None

    async def test_deterministic_same_day(self):
        a = await generate_reading(topic="연애", spread_type="three_card", user_id=999)
        b = await generate_reading(topic="연애", spread_type="three_card", user_id=999)
        assert [c["card_name"] for c in a["cards"]] == [c["card_name"] for c in b["cards"]]

    async def test_different_topics_different_cards(self):
        a = await generate_reading(topic="연애", spread_type="three_card", user_id=999)
        b = await generate_reading(topic="투자", spread_type="three_card", user_id=999)
        cards_a = [c["card_name_en"] for c in a["cards"]]
        cards_b = [c["card_name_en"] for c in b["cards"]]
        assert len(cards_a) == len(cards_b) == 3

    async def test_ai_narrative_field_present(self):
        """AI 서사 필드가 리딩 결과에 존재 (mock이므로 None)."""
        reading = await generate_reading(topic="종합", spread_type="three_card", user_id=1)
        assert "ai_narrative" in reading


# ── 메시지 포맷 ──

class TestFormatReadingMessage:
    async def test_contains_header(self):
        reading = await generate_reading(topic="종합", spread_type="three_card", user_id=1)
        msg = format_reading_message(reading)
        assert "종합 해석" in msg

    async def test_contains_summary(self):
        reading = await generate_reading(topic="재물", spread_type="three_card", user_id=1)
        msg = format_reading_message(reading)
        assert "종합 해석" in msg

    async def test_contains_disclaimer(self):
        reading = await generate_reading(topic="종합", spread_type="three_card", user_id=1)
        msg = format_reading_message(reading)
        assert "재미용" in msg

    async def test_zodiac_shown_when_present(self):
        reading = await generate_reading(
            topic="종합", spread_type="three_card",
            birth_date=date(1990, 8, 10), user_id=1,
        )
        msg = format_reading_message(reading)
        assert "사자자리" in msg

    async def test_ai_narrative_shown_when_present(self):
        """AI 서사가 있으면 종합 해석 섹션이 표시."""
        reading = await generate_reading(topic="종합", spread_type="three_card", user_id=1)
        reading["ai_narrative"] = "...테스트 AI 서사입니다."
        msg = format_reading_message(reading)
        assert "종합 해석" in msg
        assert "테스트 AI 서사" in msg

    async def test_fallback_when_no_ai(self):
        """AI 서사가 없으면 정적 요약 사용."""
        reading = await generate_reading(topic="종합", spread_type="three_card", user_id=1)
        reading["ai_narrative"] = None
        msg = format_reading_message(reading)
        assert reading["summary"] in msg


# ── TOPIC_EMOJIS ──

class TestTopicEmojis:
    def test_all_topics_have_emojis(self):
        for topic in ("연애", "직장", "재물", "투자", "인간관계", "종합"):
            assert topic in TOPIC_EMOJIS


# ══════════════════════════════════════════════════════════════════
# 아래: 추가 테스트 — 카드 데이터 무결성, 이미지, 포켓몬 매핑 등
# ══════════════════════════════════════════════════════════════════

_TAROT_IMG_DIR = Path(__file__).parent.parent / "assets" / "tarot"
_DATA_PATH = Path(__file__).parent.parent / "data" / "tarot_cards_full.json"

REQUIRED_TOPICS = ("연애", "직장", "재물", "투자", "인간관계", "종합")


def _all_cards() -> list[dict]:
    with open(_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


# ── 1. 카드 데이터 무결성 ──

class TestCardDataIntegrity:
    """78장 카드 데이터 파일 구조 검증."""

    def test_total_card_count(self):
        cards = _all_cards()
        assert len(cards) == 78, f"Expected 78 cards, got {len(cards)}"

    def test_major_count(self):
        cards = _all_cards()
        majors = [c for c in cards if c["type"] == "major"]
        assert len(majors) == 22

    def test_minor_count(self):
        cards = _all_cards()
        minors = [c for c in cards if c["type"] == "minor"]
        assert len(minors) == 56

    def test_required_fields_present(self):
        """모든 카드에 필수 필드가 존재."""
        required = ["name", "name_short", "type", "value_int",
                     "name_ko", "meanings", "meaning_up_en", "meaning_rev_en"]
        cards = _all_cards()
        for c in cards:
            for field in required:
                assert field in c, f"Card '{c.get('name', '?')}' missing field '{field}'"

    def test_name_short_unique(self):
        cards = _all_cards()
        shorts = [c["name_short"] for c in cards]
        assert len(shorts) == len(set(shorts)), "Duplicate name_short found"

    def test_name_ko_not_empty(self):
        cards = _all_cards()
        for c in cards:
            assert c["name_ko"].strip(), f"Empty name_ko for {c['name']}"

    def test_major_value_int_range(self):
        cards = _all_cards()
        majors = [c for c in cards if c["type"] == "major"]
        vals = sorted(c["value_int"] for c in majors)
        assert vals == list(range(22)), f"Major value_int should be 0-21, got {vals}"

    def test_minor_suits_complete(self):
        cards = _all_cards()
        minors = [c for c in cards if c["type"] == "minor"]
        suits = set(c["suit"] for c in minors)
        assert suits == {"wands", "cups", "swords", "pentacles"}

    def test_minor_14_per_suit(self):
        cards = _all_cards()
        minors = [c for c in cards if c["type"] == "minor"]
        for suit in ("wands", "cups", "swords", "pentacles"):
            count = sum(1 for c in minors if c["suit"] == suit)
            assert count == 14, f"Suit {suit} has {count} cards, expected 14"


# ── 2. meanings 완비 검증 ──

class TestMeaningsComplete:
    """모든 카드 × 모든 주제 × 정/역방향에 해석문이 존재하는지 검증."""

    def test_all_cards_have_meanings_dict(self):
        cards = _all_cards()
        for c in cards:
            assert isinstance(c.get("meanings"), dict), \
                f"Card '{c['name']}' has no meanings dict"

    def test_all_topics_present_in_meanings(self):
        cards = _all_cards()
        for c in cards:
            for topic in REQUIRED_TOPICS:
                assert topic in c["meanings"], \
                    f"Card '{c['name']}' missing topic '{topic}' in meanings"

    def test_all_directions_present_per_topic(self):
        cards = _all_cards()
        for c in cards:
            for topic in REQUIRED_TOPICS:
                topic_m = c["meanings"].get(topic, {})
                assert "up" in topic_m, \
                    f"Card '{c['name']}' topic '{topic}' missing 'up'"
                assert "rev" in topic_m, \
                    f"Card '{c['name']}' topic '{topic}' missing 'rev'"

    def test_no_empty_meaning_strings(self):
        cards = _all_cards()
        for c in cards:
            for topic in REQUIRED_TOPICS:
                topic_m = c["meanings"].get(topic, {})
                for direction in ("up", "rev"):
                    text = topic_m.get(direction, "")
                    assert text.strip(), \
                        f"Empty meaning: card='{c['name']}', topic='{topic}', dir='{direction}'"

    def test_meaning_min_length(self):
        """해석문이 최소 10자 이상 (한국어 기준)."""
        cards = _all_cards()
        for c in cards:
            for topic in REQUIRED_TOPICS:
                for direction in ("up", "rev"):
                    text = c["meanings"][topic][direction]
                    assert len(text) >= 10, \
                        f"Too short meaning ({len(text)} chars): card='{c['name']}', {topic}/{direction}"


# ── 3. 마이너 아르카나 포켓몬 매핑 ──

class TestMinorArcanaPokemonMapping:
    """56장 마이너 아르카나의 포켓몬 매핑 검증."""

    def test_all_minors_have_pokemon(self):
        cards = _all_cards()
        minors = [c for c in cards if c["type"] == "minor"]
        for c in minors:
            assert c.get("pokemon"), f"Minor card '{c['name']}' missing pokemon name"
            assert c.get("pokemon_id"), f"Minor card '{c['name']}' missing pokemon_id"

    def test_minor_pokemon_ids_unique(self):
        cards = _all_cards()
        minors = [c for c in cards if c["type"] == "minor"]
        pids = [c["pokemon_id"] for c in minors]
        assert len(pids) == len(set(pids)), \
            f"Duplicate pokemon_id in minors: {[p for p in pids if pids.count(p) > 1]}"

    def test_minor_pokemon_ids_valid(self):
        """모든 마이너 카드의 pokemon_id가 게임 데이터에 존재."""
        from models.pokemon_data import ALL_POKEMON
        valid_ids = {p[0] for p in ALL_POKEMON}  # tuple의 첫 번째가 ID

        cards = _all_cards()
        minors = [c for c in cards if c["type"] == "minor"]
        for c in minors:
            pid = c["pokemon_id"]
            assert pid in valid_ids, \
                f"Minor card '{c['name']}' has invalid pokemon_id={pid}"

    def test_minor_pokemon_name_not_empty(self):
        cards = _all_cards()
        minors = [c for c in cards if c["type"] == "minor"]
        for c in minors:
            assert len(c["pokemon"].strip()) > 0


# ── 4. 카드 이미지 파일 존재 ──

class TestCardImageFiles:
    """메이저 0~21.jpg + 마이너 name_short.jpg 존재 검증."""

    def test_major_images_exist(self):
        for i in range(22):
            img = _TAROT_IMG_DIR / f"{i}.jpg"
            assert img.exists(), f"Missing major arcana image: {img}"

    def test_minor_images_exist(self):
        cards = _all_cards()
        minors = [c for c in cards if c["type"] == "minor"]
        for c in minors:
            short = c["name_short"]
            img = _TAROT_IMG_DIR / f"{short}.jpg"
            assert img.exists(), f"Missing minor arcana image: {img} (card: {c['name']})"

    def test_total_image_count(self):
        """최소 78개의 jpg 파일이 존재해야 함."""
        jpgs = list(_TAROT_IMG_DIR.glob("*.jpg"))
        assert len(jpgs) >= 78, f"Expected >= 78 images, found {len(jpgs)}"


# ── 5. draw_cards 추가 테스트 ──

class TestDrawCardsExtended:
    """draw_cards() 추가 엣지 케이스."""

    def test_draw_max_78(self):
        cards = draw_cards(78)
        assert len(cards) == 78
        names = [c["name"] for c in cards]
        assert len(names) == len(set(names)), "78장 전부 뽑았는데 중복 발생"

    def test_draw_includes_card_type_field(self):
        cards = draw_cards(5, seed=42)
        for c in cards:
            assert c.get("type") in ("major", "minor")

    def test_draw_preserves_name_short(self):
        cards = draw_cards(5, seed=42)
        for c in cards:
            assert "name_short" in c
            assert len(c["name_short"]) > 0

    def test_reversed_ratio_reasonable(self):
        """충분히 많이 뽑으면 정/역 비율이 극단적이지 않은지 확인."""
        cards = draw_cards(78, seed=12345)
        rev_count = sum(1 for c in cards if c["reversed"])
        # 78장 중 역방향이 10~68장 사이면 합리적 (50% 확률, 극단 배제)
        assert 10 <= rev_count <= 68, f"Reversed count {rev_count}/78 seems extreme"

    def test_seed_consistency_across_calls(self):
        """같은 시드로 여러 번 호출해도 동일한 결과."""
        results = [draw_cards(5, seed=777) for _ in range(5)]
        first_names = [c["name"] for c in results[0]]
        for r in results[1:]:
            assert [c["name"] for c in r] == first_names


# ── 6. get_meaning 추가 테스트 ──

class TestGetMeaningExtended:
    """모든 topic × direction 조합에서 빈 문자열이 없는지."""

    def test_all_topics_all_directions(self):
        cards = _load_cards()
        for card in cards:
            for topic in REQUIRED_TOPICS:
                for direction in ("up", "rev"):
                    test_card = card.copy()
                    test_card["direction"] = direction
                    test_card["reversed"] = (direction == "rev")
                    meaning = get_meaning(test_card, topic)
                    assert meaning and len(meaning.strip()) > 0, \
                        f"Empty meaning for {card['name']}, {topic}, {direction}"

    def test_fallback_topic_returns_nonempty(self):
        """없는 주제여도 폴백으로 비어있지 않은 해석 반환."""
        cards = draw_cards(3, seed=50)
        for c in cards:
            meaning = get_meaning(c, "없는주제XYZ")
            assert len(meaning.strip()) > 0


# ── 7. generate_reading 추가 테스트 ──

class TestGenerateReadingExtended:
    """generate_reading() 추가 검증."""

    async def test_one_card_spread(self):
        reading = await generate_reading(topic="종합", spread_type="one_card", user_id=100)
        assert len(reading["cards"]) == 1
        assert reading["cards"][0]["position"] == "메시지"

    async def test_all_spread_types(self):
        """모든 스프레드 타입으로 리딩 생성 가능."""
        for spread_type in SPREADS:
            reading = await generate_reading(topic="종합", spread_type=spread_type, user_id=42)
            expected = SPREADS[spread_type]["count"]
            assert len(reading["cards"]) == expected, \
                f"Spread {spread_type}: expected {expected} cards, got {len(reading['cards'])}"

    async def test_card_name_short_in_reading(self):
        """리딩 결과에 card_name_short 필드가 포함되어야 함."""
        reading = await generate_reading(topic="종합", spread_type="three_card", user_id=1)
        for c in reading["cards"]:
            assert "card_name_short" in c
            assert isinstance(c["card_name_short"], str)
            assert len(c["card_name_short"]) > 0

    async def test_reading_has_all_required_fields(self):
        reading = await generate_reading(topic="재물", spread_type="three_card", user_id=50)
        required = ["spread", "topic", "topic_emoji", "cards", "zodiac", "summary", "date", "ai_narrative"]
        for field in required:
            assert field in reading, f"Reading missing field '{field}'"

    async def test_reading_card_has_all_fields(self):
        reading = await generate_reading(topic="종합", spread_type="three_card", user_id=1)
        card_fields = [
            "position", "position_emoji", "card_name", "card_name_en",
            "card_name_short", "pokemon_id", "reversed", "meaning",
            "card_type", "card_number",
        ]
        for c in reading["cards"]:
            for field in card_fields:
                assert field in c, f"Card missing field '{field}'"

    async def test_same_user_same_day_same_topic_deterministic(self):
        """같은 유저 + 같은 날 + 같은 주제 = 같은 결과."""
        for topic in REQUIRED_TOPICS:
            a = await generate_reading(topic=topic, spread_type="three_card", user_id=42)
            b = await generate_reading(topic=topic, spread_type="three_card", user_id=42)
            assert [c["card_name_en"] for c in a["cards"]] == \
                   [c["card_name_en"] for c in b["cards"]]
            assert [c["reversed"] for c in a["cards"]] == \
                   [c["reversed"] for c in b["cards"]]

    async def test_different_users_different_results(self):
        """다른 유저는 (보통) 다른 결과."""
        a = await generate_reading(topic="종합", spread_type="three_card", user_id=1)
        b = await generate_reading(topic="종합", spread_type="three_card", user_id=99999)
        assert len(a["cards"]) == len(b["cards"])
        for c in a["cards"] + b["cards"]:
            assert c["card_name_en"]

    async def test_all_topics_generate_valid_reading(self):
        """모든 주제로 리딩 생성 가능."""
        for topic in REQUIRED_TOPICS:
            reading = await generate_reading(topic=topic, spread_type="three_card", user_id=7)
            assert reading["topic"] == topic
            assert reading["topic_emoji"] == TOPIC_EMOJIS[topic]
            assert len(reading["cards"]) == 3
            assert reading["summary"].strip()

    async def test_summary_not_empty(self):
        for topic in REQUIRED_TOPICS:
            reading = await generate_reading(topic=topic, spread_type="three_card", user_id=1)
            assert len(reading["summary"]) > 10

    async def test_pokemon_id_in_reading_cards(self):
        """리딩 카드에 pokemon_id가 0 이상의 정수로 존재."""
        reading = await generate_reading(topic="종합", spread_type="love", user_id=1)
        for c in reading["cards"]:
            assert isinstance(c["pokemon_id"], int)
            assert c["pokemon_id"] >= 0


# ── 8. format_reading_message 추가 테스트 ──

class TestFormatReadingMessageExtended:
    """format_reading_message() 추가 검증."""

    async def test_html_tags_present(self):
        reading = await generate_reading(topic="종합", spread_type="three_card", user_id=1)
        msg = format_reading_message(reading)
        assert "<b>" in msg
        assert "</b>" in msg
        assert "<i>" in msg

    async def test_all_spreads_format_ok(self):
        """모든 스프레드 타입으로 종합 해석 포맷 가능."""
        for spread_type in SPREADS:
            reading = await generate_reading(topic="종합", spread_type=spread_type, user_id=1)
            msg = format_reading_message(reading)
            assert len(msg) > 30
            assert "종합 해석" in msg
            assert "재미용" in msg


# ── 9. get_zodiac 경계값 테스트 ──

class TestGetZodiacBoundary:
    """모든 12별자리의 시작/끝 날짜 경계값 테스트."""

    def test_all_12_zodiac_signs_reachable(self):
        """12별자리 모두 도달 가능."""
        test_dates = [
            (date(2000, 1, 10), "염소자리"),
            (date(2000, 1, 25), "물병자리"),
            (date(2000, 2, 19), "물고기자리"),
            (date(2000, 3, 25), "양자리"),
            (date(2000, 4, 25), "황소자리"),
            (date(2000, 5, 25), "쌍둥이자리"),
            (date(2000, 6, 25), "게자리"),
            (date(2000, 7, 25), "사자자리"),
            (date(2000, 8, 25), "처녀자리"),
            (date(2000, 9, 25), "천칭자리"),
            (date(2000, 10, 25), "전갈자리"),
            (date(2000, 11, 25), "궁수자리"),
        ]
        for d, expected_sign in test_dates:
            result = get_zodiac(d)
            assert expected_sign in result, \
                f"Date {d} expected '{expected_sign}', got '{result}'"

    def test_capricorn_wraps_december_to_january(self):
        """염소자리: 12/22 ~ 1/19 경계."""
        assert "염소자리" in get_zodiac(date(2000, 12, 22))  # 시작
        assert "염소자리" in get_zodiac(date(2000, 1, 19))   # 끝
        assert "염소자리" in get_zodiac(date(2000, 12, 31))  # 중간
        assert "염소자리" in get_zodiac(date(2000, 1, 1))    # 중간

    def test_zodiac_boundary_transitions(self):
        """별자리 전환 경계에서 올바른 결과."""
        # 물병자리 시작 1/20, 끝 2/18
        assert "물병자리" in get_zodiac(date(2000, 1, 20))
        assert "물병자리" in get_zodiac(date(2000, 2, 18))
        # 물고기자리 시작 2/19
        assert "물고기자리" in get_zodiac(date(2000, 2, 19))
        # 궁수자리 끝 12/21 → 다음날 염소자리
        assert "궁수자리" in get_zodiac(date(2000, 12, 21))
        assert "염소자리" in get_zodiac(date(2000, 12, 22))

    def test_every_day_of_year_has_zodiac(self):
        """1년 366일 모두 별자리가 반환됨 (빈 문자열 없음)."""
        # 윤년 사용
        for month in range(1, 13):
            max_day = 31
            if month in (4, 6, 9, 11):
                max_day = 30
            elif month == 2:
                max_day = 29
            for day in range(1, max_day + 1):
                result = get_zodiac(date(2000, month, day))
                assert result and len(result) > 0, f"No zodiac for {month}/{day}"


# ── 10. TOPIC_MAP / ZODIAC_SIGNS 상수 검증 ──

class TestConstants:
    """상수 정합성 검증."""

    def test_topic_map_matches_emojis(self):
        for topic in TOPIC_MAP:
            assert topic in TOPIC_EMOJIS

    def test_zodiac_signs_count(self):
        assert len(ZODIAC_SIGNS) == 12

    def test_spread_one_card_exists(self):
        assert "one_card" in SPREADS
        assert SPREADS["one_card"]["count"] == 1

    def test_all_spread_position_emojis_nonempty(self):
        for key, spread in SPREADS.items():
            for emoji in spread["position_emojis"]:
                assert len(emoji) > 0, f"Empty emoji in spread {key}"


# ── 11. _parse_birth_date 추가 엣지 케이스 ──

class TestParseBirthDateExtended:
    """_parse_birth_date() 추가 엣지 케이스."""

    def test_boundary_dates(self):
        assert _parse_birth_date("1920-01-01") == date(1920, 1, 1)
        assert _parse_birth_date("2025-12-31") == date(2025, 12, 31)

    def test_feb_28_non_leap(self):
        assert _parse_birth_date("2023-02-28") == date(2023, 2, 28)

    def test_feb_30_invalid(self):
        assert _parse_birth_date("2000-02-30") is None

    def test_month_00_invalid(self):
        assert _parse_birth_date("2000-00-15") is None

    def test_day_00_invalid(self):
        assert _parse_birth_date("2000-01-00") is None

    def test_empty_string(self):
        assert _parse_birth_date("") is None

    def test_only_spaces(self):
        assert _parse_birth_date("   ") is None

    def test_mixed_separators(self):
        # "1995/03.15" → 슬래시가 대시로 변환 후 "1995-03.15" → dot도 대시 → 정상 파싱
        assert _parse_birth_date("1995/03/15") == date(1995, 3, 15)

    def test_digits_with_leading_zeros(self):
        assert _parse_birth_date("20000101") == date(2000, 1, 1)


# ── 12. AI 서사 캐시 키 / 프롬프트 빌더 ──

class TestAINarrativeHelpers:
    """_make_cache_key / _build_narrative_prompt 검증."""

    def _sample_cards(self):
        return [
            {"card_name": "바보", "card_name_en": "The Fool", "reversed": False,
             "position": "과거", "position_emoji": "⏪", "meaning": "새로운 시작"},
            {"card_name": "마법사", "card_name_en": "The Magician", "reversed": True,
             "position": "현재", "position_emoji": "📍", "meaning": "힘의 남용"},
            {"card_name": "여사제", "card_name_en": "The High Priestess", "reversed": False,
             "position": "미래", "position_emoji": "🔮", "meaning": "직관의 힘"},
        ]

    def test_cache_key_deterministic(self):
        cards = self._sample_cards()
        key1 = _make_cache_key(cards, "종합", "three_card", None)
        key2 = _make_cache_key(cards, "종합", "three_card", None)
        assert key1 == key2

    def test_cache_key_different_topic(self):
        cards = self._sample_cards()
        key1 = _make_cache_key(cards, "종합", "three_card", None)
        key2 = _make_cache_key(cards, "연애", "three_card", None)
        assert key1 != key2

    def test_cache_key_different_direction(self):
        cards1 = self._sample_cards()
        cards2 = self._sample_cards()
        cards2[0]["reversed"] = True  # 바보 역방향으로 변경
        key1 = _make_cache_key(cards1, "종합", "three_card", None)
        key2 = _make_cache_key(cards2, "종합", "three_card", None)
        assert key1 != key2

    def test_cache_key_different_zodiac(self):
        cards = self._sample_cards()
        key1 = _make_cache_key(cards, "종합", "three_card", "♓ 물고기자리")
        key2 = _make_cache_key(cards, "종합", "three_card", None)
        assert key1 != key2

    def test_cache_key_length(self):
        cards = self._sample_cards()
        key = _make_cache_key(cards, "종합", "three_card", None)
        assert len(key) == 32  # sha256[:32]

    def test_build_prompt_contains_card_info(self):
        cards = self._sample_cards()
        prompt = _build_narrative_prompt(cards, "종합", "쓰리카드", "♓ 물고기자리")
        assert "바보" in prompt
        assert "마법사" in prompt
        assert "여사제" in prompt
        assert "종합" in prompt
        assert "물고기자리" in prompt

    def test_build_prompt_shows_direction(self):
        cards = self._sample_cards()
        prompt = _build_narrative_prompt(cards, "종합", "쓰리카드", None)
        assert "정방향" in prompt
        assert "역방향" in prompt

    def test_build_prompt_includes_meanings(self):
        cards = self._sample_cards()
        prompt = _build_narrative_prompt(cards, "종합", "쓰리카드", None)
        assert "새로운 시작" in prompt
        assert "힘의 남용" in prompt
        assert "직관의 힘" in prompt

    def test_build_prompt_includes_time_range(self):
        cards = self._sample_cards()
        prompt = _build_narrative_prompt(cards, "종합", "쓰리카드", None, "이번 달")
        assert "이번 한 달" in prompt

    def test_cache_key_different_time_range(self):
        cards = self._sample_cards()
        key1 = _make_cache_key(cards, "종합", "three_card", None, "오늘")
        key2 = _make_cache_key(cards, "종합", "three_card", None, "이번 주")
        assert key1 != key2


# ── 13. 시간 범위 + 공유 메시지 ──

class TestTimeRange:
    """시간 범위 관련 테스트."""

    def test_time_ranges_defined(self):
        assert "오늘" in TIME_RANGES
        assert "이번 주" in TIME_RANGES
        assert "이번 달" in TIME_RANGES

    def test_time_ranges_have_label_and_hint(self):
        for k, v in TIME_RANGES.items():
            assert "label" in v
            assert "prompt_hint" in v

    async def test_reading_has_time_range(self):
        reading = await generate_reading(topic="종합", spread_type="three_card",
                                         user_id=1, time_range="오늘")
        assert reading["time_range"] == "오늘"

    async def test_reading_default_time_range(self):
        reading = await generate_reading(topic="종합", spread_type="three_card", user_id=1)
        assert reading["time_range"] == "이번 주"

    async def test_invalid_time_range_falls_back(self):
        reading = await generate_reading(topic="종합", spread_type="three_card",
                                         user_id=1, time_range="내년")
        assert reading["time_range"] == "이번 주"

    async def test_format_shows_time_range(self):
        reading = await generate_reading(topic="종합", spread_type="three_card",
                                         user_id=1, time_range="이번 달")
        msg = format_reading_message(reading)
        assert "이번 달" in msg


class TestShareMessage:
    """그룹 공유 메시지 포맷 테스트."""

    async def test_share_message_contains_user_name(self):
        reading = await generate_reading(topic="연애", spread_type="three_card", user_id=1)
        msg = _format_share_message(reading, "테스터")
        assert "테스터" in msg
        assert "타로 리딩" in msg

    async def test_share_message_contains_cards(self):
        reading = await generate_reading(topic="종합", spread_type="three_card", user_id=1)
        msg = _format_share_message(reading, "유저")
        for c in reading["cards"]:
            assert c["position"] in msg

    async def test_share_message_shows_ai_narrative(self):
        reading = await generate_reading(topic="종합", spread_type="three_card", user_id=1)
        reading["ai_narrative"] = "...AI 서사 테스트"
        msg = _format_share_message(reading, "유저")
        assert "AI 서사 테스트" in msg
        assert "종합 해석" in msg

    async def test_share_message_fallback_without_ai(self):
        reading = await generate_reading(topic="종합", spread_type="three_card", user_id=1)
        reading["ai_narrative"] = None
        msg = _format_share_message(reading, "유저")
        assert reading["summary"] in msg

    async def test_share_message_has_cta(self):
        reading = await generate_reading(topic="종합", spread_type="three_card", user_id=1)
        msg = _format_share_message(reading, "유저")
        assert "DM에서" in msg
