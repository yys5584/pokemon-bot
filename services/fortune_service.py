"""포켓몬 타로 리딩 서비스 — 창백피카츄의 타로.

78장 카드 데이터 + 스프레드 엔진 + 해석 조합.
"""

from __future__ import annotations

import json
import logging
import random
from datetime import date, datetime
from pathlib import Path

import config

_log = logging.getLogger(__name__)

# ── 카드 데이터 로드 ──

_TAROT_DATA_PATH = Path(__file__).parent.parent / "data" / "tarot_cards_full.json"
_FALLBACK_PATH = Path(__file__).parent.parent / "data" / "tarot_cards.json"

_cards: list[dict] | None = None


def _load_cards() -> list[dict]:
    global _cards
    if _cards is not None:
        return _cards
    path = _TAROT_DATA_PATH if _TAROT_DATA_PATH.exists() else _FALLBACK_PATH
    with open(path, encoding="utf-8") as f:
        _cards = json.load(f)
    _log.info(f"Tarot cards loaded: {len(_cards)} cards from {path.name}")
    return _cards


# ── 별자리 ──

ZODIAC_SIGNS = [
    ("♒ 물병자리", (1, 20), (2, 18)),
    ("♓ 물고기자리", (2, 19), (3, 20)),
    ("♈ 양자리", (3, 21), (4, 19)),
    ("♉ 황소자리", (4, 20), (5, 20)),
    ("♊ 쌍둥이자리", (5, 21), (6, 21)),
    ("♋ 게자리", (6, 22), (7, 22)),
    ("♌ 사자자리", (7, 23), (8, 22)),
    ("♍ 처녀자리", (8, 23), (9, 22)),
    ("♎ 천칭자리", (9, 23), (10, 23)),
    ("♏ 전갈자리", (10, 24), (11, 22)),
    ("♐ 궁수자리", (11, 23), (12, 21)),
    ("♑ 염소자리", (12, 22), (1, 19)),
]


def get_zodiac(birth_date: date) -> str:
    """생년월일로 별자리 반환."""
    m, d = birth_date.month, birth_date.day
    for name, (sm, sd), (em, ed) in ZODIAC_SIGNS:
        if sm <= em:
            if (m == sm and d >= sd) or (m == em and d <= ed) or (sm < m < em):
                return name
        else:  # 염소자리 (12월~1월)
            if (m == sm and d >= sd) or (m == em and d <= ed) or m > sm or m < em:
                return name
    return "♑ 염소자리"


# ── 카드 뽑기 ──

def draw_cards(count: int = 3, seed: int | None = None) -> list[dict]:
    """카드 뽑기 — 랜덤 N장 + 정/역방향 결정."""
    cards = _load_cards()
    rng = random.Random(seed) if seed else random.Random()

    deck = list(range(len(cards)))
    rng.shuffle(deck)
    drawn_indices = deck[:count]

    result = []
    for idx in drawn_indices:
        card = cards[idx].copy()
        card["reversed"] = rng.random() < 0.5  # 50% 확률 역방향
        card["direction"] = "rev" if card["reversed"] else "up"
        result.append(card)

    return result


# ── 스프레드 ──

SPREADS = {
    "three_card": {
        "name": "쓰리카드",
        "count": 3,
        "positions": ["과거", "현재", "미래"],
        "position_emojis": ["⏪", "📍", "🔮"],
    },
    "one_card": {
        "name": "원카드",
        "count": 1,
        "positions": ["메시지"],
        "position_emojis": ["🔮"],
    },
    "investment": {
        "name": "투자 스프레드",
        "count": 4,
        "positions": ["현재 상태", "기회", "리스크", "조언"],
        "position_emojis": ["📊", "✨", "⚠️", "💡"],
    },
    "love": {
        "name": "연애 스프레드",
        "count": 5,
        "positions": ["내 마음", "상대 에너지", "관계 현재", "장애물", "잠재력"],
        "position_emojis": ["💕", "💜", "🤝", "🚧", "🌟"],
    },
}


def get_spread(spread_type: str) -> dict:
    """스프레드 정보 반환."""
    return SPREADS.get(spread_type, SPREADS["three_card"])


# ── 해석 가져오기 ──

def get_meaning(card: dict, topic: str) -> str:
    """카드 + 주제 + 방향에 맞는 해석문 반환."""
    direction = card.get("direction", "up")
    meanings = card.get("meanings", {})
    topic_meanings = meanings.get(topic, {})
    text = topic_meanings.get(direction, "")

    if not text:
        # 폴백: 종합 해석 사용
        text = meanings.get("종합", {}).get(direction, "")

    if not text:
        # 최종 폴백: 영문 원본
        if direction == "up":
            text = f"...{card.get('meaning_up_en', '카드가 속삭이고 있어요...')[:100]}"
        else:
            text = f"...{card.get('meaning_rev_en', '카드가 조용히 말하고 있어요...')[:100]}"

    return text


# ── 종합 리딩 생성 ──

TOPIC_MAP = {
    "연애": "연애",
    "직장": "직장",
    "재물": "재물",
    "투자": "투자",
    "인간관계": "인간관계",
    "종합": "종합",
}

TOPIC_EMOJIS = {
    "연애": "💕",
    "직장": "💼",
    "재물": "💰",
    "투자": "📈",
    "인간관계": "🤝",
    "종합": "🌟",
}


def generate_reading(
    topic: str = "종합",
    spread_type: str = "three_card",
    birth_date: date | None = None,
    user_id: int | None = None,
) -> dict:
    """타로 리딩 생성 — 카드 뽑기 + 해석 조합.

    Returns:
        {
            "spread": spread_info,
            "topic": topic,
            "cards": [{"card": ..., "position": ..., "meaning": ...}, ...],
            "zodiac": str | None,
            "summary": str,
        }
    """
    spread = get_spread(spread_type)

    # 시드: user_id + 날짜 기반 (같은 날 같은 유저는 같은 결과)
    today = config.get_kst_now().date()
    seed = None
    if user_id:
        seed = hash((user_id, today.toordinal(), topic))

    drawn = draw_cards(spread["count"], seed=seed)

    # 해석 조합
    reading_cards = []
    for i, card in enumerate(drawn):
        position = spread["positions"][i] if i < len(spread["positions"]) else f"카드 {i+1}"
        pos_emoji = spread["position_emojis"][i] if i < len(spread["position_emojis"]) else "🃏"
        meaning = get_meaning(card, topic)

        dir_label = "" if not card.get("reversed") else " 🔄"
        name_ko = card.get("name_ko", card["name"])
        pokemon = card.get("pokemon", "")
        pokemon_label = f" ({pokemon})" if pokemon else ""

        reading_cards.append({
            "position": position,
            "position_emoji": pos_emoji,
            "card_name": f"{name_ko}{pokemon_label}{dir_label}",
            "card_name_en": card["name"],
            "pokemon_id": card.get("pokemon_id", 0),
            "reversed": card.get("reversed", False),
            "meaning": meaning,
            "card_type": card.get("type", "minor"),
            "card_number": card.get("value_int", -1),
        })

    # 별자리
    zodiac = get_zodiac(birth_date) if birth_date else None

    # 종합 요약 (창백피카츄 톤)
    summary = _generate_summary(reading_cards, topic, zodiac)

    return {
        "spread": spread,
        "topic": topic,
        "topic_emoji": TOPIC_EMOJIS.get(topic, "🔮"),
        "cards": reading_cards,
        "zodiac": zodiac,
        "summary": summary,
        "date": today.isoformat(),
    }


def _generate_summary(cards: list[dict], topic: str, zodiac: str | None) -> str:
    """3장 카드를 종합한 요약 멘트 (창백피카츄 톤)."""
    # 정방향 카드 수로 전체 분위기 결정
    positive_count = sum(1 for c in cards if not c["reversed"])
    total = len(cards)

    if positive_count == total:
        mood = "...후후, 아주 좋은 기운이 가득해요."
    elif positive_count >= total / 2:
        mood = "...전체적으로 좋은 흐름이에요. 다만, 조심할 부분도 있어요."
    elif positive_count > 0:
        mood = "...쉽지 않은 시기지만, 빛이 보여요."
    else:
        mood = "...많이 힘든 시기네요. 하지만 괜찮아요, 이것도 지나가요."

    zodiac_line = f"\n{zodiac}의 당신에게 보내는 메시지예요." if zodiac else ""

    advice_pool = [
        "오늘 하루, 자신에게 조금 더 다정해지세요.",
        "작은 것부터 시작해봐요. 그게 가장 큰 용기예요.",
        "당신은 생각보다 강한 사람이에요.",
        "쉬어가도 괜찮아요. 멈추는 것도 전진이에요.",
        "마음이 가는 대로 따라가봐요. 그게 답이에요.",
        "오늘은 좋아하는 걸 하나만 해보세요.",
    ]

    rng = random.Random(hash((config.get_kst_today(), topic)))
    advice = rng.choice(advice_pool)

    return f"{mood}{zodiac_line}\n\n💫 {advice}"


# ── 메시지 포맷 ──

def format_reading_message(reading: dict) -> str:
    """리딩 결과를 텔레그램 메시지로 포맷."""
    topic_emoji = reading["topic_emoji"]
    topic = reading["topic"]
    spread_name = reading["spread"]["name"]

    lines = [
        f"🔮 <b>창백피카츄의 타로 리딩</b>",
        f"{topic_emoji} 주제: <b>{topic}</b> | {spread_name}",
        "",
        "...카드를 넘기고 있어요...",
        "",
    ]

    for c in reading["cards"]:
        lines.append(f"{c['position_emoji']} <b>[{c['position']}]</b> {c['card_name']}")
        lines.append(f"  {c['meaning']}")
        lines.append("")

    lines.append(f"━━━━━━━━━━━━━━")
    lines.append(reading["summary"])

    if reading.get("zodiac"):
        lines.append(f"\n{reading['zodiac']}")

    lines.append(f"\n<i>⚠️ 재미용 리딩이며 실제 조언이 아닙니다</i>")

    return "\n".join(lines)
