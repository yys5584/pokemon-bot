"""포켓몬 타로 리딩 서비스 — 신비로운 피카의 타로.

78장 카드 데이터 + 스프레드 엔진 + 해석 조합 + AI 서사 생성.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
from datetime import date, datetime
from pathlib import Path

import aiohttp

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
    ("♎ 천칭자리", (9, 23), (10, 22)),
    ("♏ 전갈자리", (10, 23), (11, 21)),
    ("♐ 궁수자리", (11, 22), (12, 21)),
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

# ── 시간 범위 ──

TIME_RANGES = {
    "이번 주": {"label": "📆 이번 주", "prompt_hint": "이번 한 주"},
    "이번 달": {"label": "🗓️ 이번 달", "prompt_hint": "이번 한 달"},
}
DEFAULT_TIME_RANGE = "이번 주"


async def generate_reading(
    topic: str = "종합",
    spread_type: str = "three_card",
    birth_date: date | None = None,
    user_id: int | None = None,
    time_range: str = "이번 주",
    situation: str | None = None,
    gender: str | None = None,
) -> dict:
    """타로 리딩 생성 — 카드 뽑기 + 해석 조합 + AI 서사.

    Returns:
        {
            "spread": spread_info,
            "topic": topic,
            "time_range": str,
            "cards": [{"card": ..., "position": ..., "meaning": ...}, ...],
            "zodiac": str | None,
            "summary": str,
            "ai_narrative": str | None,
        }
    """
    reading = generate_reading_cards(topic, spread_type, birth_date, user_id, time_range)
    await enrich_reading_with_ai(reading, situation=situation, gender=gender)
    return reading


def generate_reading_cards(
    topic: str = "종합",
    spread_type: str = "three_card",
    birth_date: date | None = None,
    user_id: int | None = None,
    time_range: str = "이번 주",
) -> dict:
    """카드 뽑기 + 정적 해석만 (AI 없이 즉시 반환)."""
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
            "card_name_short": card.get("name_short", ""),
            "pokemon_id": card.get("pokemon_id", 0),
            "reversed": card.get("reversed", False),
            "meaning": meaning,
            "card_type": card.get("type", "minor"),
            "card_number": card.get("value_int", -1),
        })

    # 별자리
    zodiac = get_zodiac(birth_date) if birth_date else None

    # 시간 범위 검증
    if time_range not in TIME_RANGES:
        time_range = DEFAULT_TIME_RANGE

    summary = _generate_summary(reading_cards, topic, zodiac)

    return {
        "spread": spread,
        "topic": topic,
        "topic_emoji": TOPIC_EMOJIS.get(topic, "🔮"),
        "time_range": time_range,
        "cards": reading_cards,
        "zodiac": zodiac,
        "summary": summary,
        "ai_narrative": None,
        "date": today.isoformat(),
    }


async def enrich_reading_with_ai(
    reading: dict,
    situation: str | None = None,
    gender: str | None = None,
) -> None:
    """기존 reading에 AI 해석을 추가 (in-place 업데이트)."""
    cards = reading["cards"]
    topic = reading["topic"]
    spread = reading["spread"]
    zodiac = reading.get("zodiac")
    time_range = reading.get("time_range", DEFAULT_TIME_RANGE)
    spread_type = spread.get("type", "three_card")

    ai_narrative = await get_ai_narrative(
        cards, topic, spread_type, spread["name"], zodiac, time_range,
        situation=situation, gender=gender,
    )

    ai_summary = ""
    if ai_narrative:
        positions = [c["position"] for c in cards]
        card_meanings, ai_summary = _parse_ai_card_meanings(ai_narrative, positions)
        for c in cards:
            if c["position"] in card_meanings:
                c["meaning"] = card_meanings[c["position"]]

    if ai_summary:
        reading["summary"] = ai_summary
        reading["ai_narrative"] = ai_summary
    elif ai_narrative:
        reading["ai_narrative"] = ai_narrative


def _generate_summary(cards: list[dict], topic: str, zodiac: str | None) -> str:
    """3장 카드를 종합한 요약 멘트 (신비로운 피카 톤)."""
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


# ── AI 서사 생성 (Gemini Flash) ──

_NARRATIVE_SYSTEM_PROMPT = """당신은 서양 타로 전문가입니다. 존댓말, 담백하고 명확한 톤.

## 시제 규칙 (반드시 준수)
- 과거 포지션 → 과거형 ("~했습니다", "~였습니다")
- 현재 포지션 → 현재형 ("~하고 있습니다", "~입니다")
- 미래 포지션 → 미래형 ("~할 것입니다", "~될 수 있습니다")

## 역할
아래 "카드별 레퍼런스"를 참고하되, 질문자의 상황에 맞게 해석을 재구성하세요.
레퍼런스를 그대로 복사하지 마세요. 질문자 상황이 핵심입니다.

## 출력 형식 (정확히 따를 것)
각 카드를 [포지션명] 라벨로 시작. 카드명을 반복하지 마세요.
1줄째: 이 카드가 상징하는 핵심 의미 한 줄 (카드 자체의 설명)
2~3줄째: 질문자 상황에 맞춘 해석

마지막에 [인사이트]로 세 카드를 관통하는 하나의 통찰을 1~2문장으로 전하세요.
- 개별 카드 해석을 요약하거나 반복하지 마세요. 이미 다 읽었습니다.
- 과거/현재/미래 언급 금지. 카드 이름 언급 금지.
- 세 카드가 함께 가리키는 공통 테마나 흐름을 한 단어로 짚고, 그에 따른 구체적 행동 조언을 주세요.
- 예: "지금 필요한 건 '기다림'입니다. 결과를 재촉하지 말고, 이번 주는 준비에 집중하세요."

## 금지
- 카드명/방향 반복 금지 (이미 UI에 표시됨)
- "...후후", "...아," 등 감탄사/여운 표현 금지
- 이모지, HTML, 마크다운 금지
- 바넘효과성 문장 금지 ("마음이 힘들었을 거예요", "지친 시간이 있었겠네요" 등 누구에게나 맞는 말)
- 점술적 예언("반드시 ~할 것입니다") 금지
- 카드 원래 의미에서 벗어난 해석 금지"""


def _build_narrative_prompt(
    cards: list[dict], topic: str, spread_name: str,
    zodiac: str | None, time_range: str = "이번 주",
    situation: str | None = None, gender: str | None = None,
) -> str:
    """AI에게 보낼 유저 프롬프트 구성."""
    time_hint = TIME_RANGES.get(time_range, {}).get("prompt_hint", time_range)
    gender_label = {"M": "남성", "F": "여성"}.get(gender, "")
    lines = [f"주제: {topic} | 스프레드: {spread_name} | 기간: {time_hint}"]
    if gender_label:
        lines.append(f"질문자 성별: {gender_label}")
    if situation:
        lines.append(f"질문자 상황: {situation}")
    else:
        lines.append("질문자 상황: 미제공")
    lines.append("")

    for c in cards:
        direction = "역방향" if c["reversed"] else "정방향"
        lines.append(f"[{c['position']}] {c['card_name']} ({direction})")
        lines.append(f"레퍼런스: {c['meaning']}")
        lines.append("")

    if zodiac:
        lines.append(f"별자리: {zodiac}")

    lines.append(f"\n'{time_hint}' 관점에서 각 카드별 해석(2~3문장) + [인사이트](1~2문장)를 작성하세요.")
    lines.append("질문자 상황에 맞춰 해석을 조정하세요. 레퍼런스를 그대로 쓰지 마세요.")
    lines.append("[인사이트]는 카드 내용 요약이 아닙니다. 세 카드의 공통 테마를 한 단어로 짚고 행동 조언만 쓰세요.")
    return "\n".join(lines)


def _make_cache_key(
    cards: list[dict], topic: str, spread_type: str,
    zodiac: str | None, time_range: str = "이번 주",
    situation: str | None = None, gender: str | None = None,
) -> str:
    """카드 조합 + 주제 + 별자리 + 시간범위 + 상황 + 성별로 캐시 키 생성."""
    card_parts = []
    for c in cards:
        name = c.get("card_name_en", c.get("card_name", ""))
        direction = "rev" if c["reversed"] else "up"
        card_parts.append(f"{name}:{direction}")
    raw = f"{','.join(card_parts)}|{topic}|{spread_type}|{zodiac or 'none'}|{time_range}|{situation or 'none'}|{gender or 'none'}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


async def get_ai_narrative(
    cards: list[dict],
    topic: str,
    spread_type: str,
    spread_name: str,
    zodiac: str | None,
    time_range: str = "이번 주",
    situation: str | None = None,
    gender: str | None = None,
) -> str | None:
    """AI 서사 생성 (캐시 우선, 미스 시 Gemini Flash 호출).

    Returns:
        AI 서사 텍스트 또는 None (실패/비활성 시).
    """
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return None

    cache_key = _make_cache_key(cards, topic, spread_type, zodiac, time_range, situation, gender)

    # 1. DB 캐시 조회
    try:
        from database.connection import get_db
        pool = await get_db()
        row = await pool.fetchrow(
            "SELECT ai_narrative FROM tarot_ai_cache WHERE cache_key = $1",
            cache_key,
        )
        if row:
            _log.info(f"Tarot AI cache HIT: {cache_key[:8]}...")
            return row["ai_narrative"]
    except Exception as e:
        _log.warning(f"Tarot AI cache lookup failed: {e}")

    # 2. Gemini Flash 호출
    user_prompt = _build_narrative_prompt(cards, topic, spread_name, zodiac, time_range, situation, gender)

    payload = {
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": _NARRATIVE_SYSTEM_PROMPT}]},
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": 2048,
            "topP": 0.9,
        },
    }

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

    narrative = None
    for attempt in range(2):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 429:
                        _log.warning("Tarot AI: Gemini 429, skipping")
                        return None
                    if resp.status != 200:
                        _log.warning(f"Tarot AI: Gemini {resp.status}")
                        return None

                    data = await resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        text_parts = [p["text"] for p in parts if "text" in p]
                        narrative = "\n".join(text_parts).strip()
                    break
        except Exception as e:
            _log.warning(f"Tarot AI call failed (attempt {attempt+1}): {e}")
            if attempt == 0:
                continue
            return None

    if not narrative:
        return None

    # 3. DB 캐시 저장
    cards_summary = ", ".join(
        f"{c['card_name']}({'역' if c['reversed'] else '정'})"
        for c in cards
    )
    try:
        from database.connection import get_db
        pool = await get_db()
        await pool.execute(
            """INSERT INTO tarot_ai_cache (cache_key, topic, spread_type, cards_summary, ai_narrative, zodiac)
               VALUES ($1, $2, $3, $4, $5, $6)
               ON CONFLICT (cache_key) DO NOTHING""",
            cache_key, topic, spread_type, cards_summary, narrative, zodiac,
        )
        _log.info(f"Tarot AI cache STORE: {cache_key[:8]}...")
    except Exception as e:
        _log.warning(f"Tarot AI cache store failed: {e}")

    return narrative


def _parse_ai_card_meanings(ai_text: str, positions: list[str]) -> tuple[dict[str, str], str]:
    """AI 응답에서 카드별 해석과 종합을 분리.

    Returns:
        (card_meanings: {position: text}, summary: text)
    """
    card_meanings = {}
    summary = ""
    current_key = None
    current_lines = []

    for line in ai_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            if current_key:
                current_lines.append("")
            continue

        # [포지션명] 또는 [인사이트] 감지
        matched = False
        if stripped.startswith("[인사이트]") or stripped.startswith("[종합]"):
            if current_key:
                card_meanings[current_key] = "\n".join(current_lines).strip()
            current_key = "_summary_"
            tag_len = len("[인사이트]") if stripped.startswith("[인사이트]") else len("[종합]")
            current_lines = [stripped[tag_len:].strip()]
            matched = True
        else:
            for pos in positions:
                tag = f"[{pos}]"
                if stripped.startswith(tag):
                    if current_key:
                        if current_key == "_summary_":
                            summary = "\n".join(current_lines).strip()
                        else:
                            card_meanings[current_key] = "\n".join(current_lines).strip()
                    current_key = pos
                    current_lines = [stripped[len(tag):].strip()]
                    matched = True
                    break

        if not matched and current_key:
            current_lines.append(stripped)

    # 마지막 블록
    if current_key:
        text = "\n".join(current_lines).strip()
        if current_key == "_summary_":
            summary = text
        else:
            card_meanings[current_key] = text

    return card_meanings, summary


# ── 메시지 포맷 ──

def format_reading_message(reading: dict) -> str:
    """종합 해석 메시지 포맷 (카드별 해석은 페이지에서 이미 표시됨)."""
    topic_emoji = reading["topic_emoji"]
    topic = reading["topic"]
    time_range = reading.get("time_range", "이번 주")
    time_label = TIME_RANGES.get(time_range, {}).get("label", f"📆 {time_range}")

    lines = [
        f"🌙 <b>종합 해석</b>",
        f"{topic_emoji} {topic} | {time_label}",
        "",
    ]

    # AI 서사가 있으면 풍부한 종합 해석, 없으면 정적 폴백
    ai_narrative = reading.get("ai_narrative")
    if ai_narrative:
        lines.append(ai_narrative)
    else:
        lines.append(reading.get("summary", ""))

    lines.append(f"\n<i>⚠️ 재미용 리딩이며 실제 조언이 아닙니다</i>")

    return "\n".join(lines)
