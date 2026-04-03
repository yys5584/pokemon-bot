"""
데일리 별자리 운세 서비스.

swisseph로 실제 행성 위치 계산 → 해석 DB 조합 → Gemini AI 다듬기.
별자리별 하루 1회 캐싱, 행운의 포켓몬 포함.
"""

import hashlib
import json
import logging
import os
from datetime import date, datetime
from pathlib import Path

import aiohttp

import config

_log = logging.getLogger(__name__)

# ── 별자리 데이터 ──

ZODIAC_SIGNS = [
    {"name": "양자리", "symbol": "♈", "en": "Aries", "start": (3, 21), "end": (4, 19), "element": "불",
     "ruler": "화성", "mode": "활동궁", "trait": "충동적, 리더십, 에너지 과잉, 경쟁심", "body": "머리/얼굴"},
    {"name": "황소자리", "symbol": "♉", "en": "Taurus", "start": (4, 20), "end": (5, 20), "element": "땅",
     "ruler": "금성", "mode": "고정궁", "trait": "안정 추구, 소유욕, 감각적 쾌락, 완고함", "body": "목/어깨"},
    {"name": "쌍둥이자리", "symbol": "♊", "en": "Gemini", "start": (5, 21), "end": (6, 21), "element": "바람",
     "ruler": "수성", "mode": "변통궁", "trait": "호기심, 소통, 변덕, 멀티태스킹", "body": "팔/폐"},
    {"name": "게자리", "symbol": "♋", "en": "Cancer", "start": (6, 22), "end": (7, 22), "element": "물",
     "ruler": "달", "mode": "활동궁", "trait": "모성, 감정 기복, 방어적, 가정 중심", "body": "위/가슴"},
    {"name": "사자자리", "symbol": "♌", "en": "Leo", "start": (7, 23), "end": (8, 22), "element": "불",
     "ruler": "태양", "mode": "고정궁", "trait": "자존심, 관대함, 주목받고 싶음, 창의력", "body": "심장/등"},
    {"name": "처녀자리", "symbol": "♍", "en": "Virgo", "start": (8, 23), "end": (9, 22), "element": "땅",
     "ruler": "수성", "mode": "변통궁", "trait": "분석력, 완벽주의, 건강 민감, 비판적", "body": "소화기관"},
    {"name": "천칭자리", "symbol": "♎", "en": "Libra", "start": (9, 23), "end": (10, 23), "element": "바람",
     "ruler": "금성", "mode": "활동궁", "trait": "조화, 우유부단, 미적 감각, 관계 지향", "body": "신장/허리"},
    {"name": "전갈자리", "symbol": "♏", "en": "Scorpio", "start": (10, 24), "end": (11, 22), "element": "물",
     "ruler": "명왕성/화성", "mode": "고정궁", "trait": "집요함, 비밀주의, 통찰력, 질투", "body": "생식기"},
    {"name": "사수자리", "symbol": "♐", "en": "Sagittarius", "start": (11, 23), "end": (12, 21), "element": "불",
     "ruler": "목성", "mode": "변통궁", "trait": "자유, 낙관, 솔직함, 무책임", "body": "허벅지/간"},
    {"name": "염소자리", "symbol": "♑", "en": "Capricorn", "start": (12, 22), "end": (1, 19), "element": "땅",
     "ruler": "토성", "mode": "활동궁", "trait": "야망, 인내, 현실주의, 감정 억제", "body": "무릎/뼈"},
    {"name": "물병자리", "symbol": "♒", "en": "Aquarius", "start": (1, 20), "end": (2, 18), "element": "바람",
     "ruler": "천왕성/토성", "mode": "고정궁", "trait": "독립, 혁신, 반항, 박애주의", "body": "종아리/순환계"},
    {"name": "물고기자리", "symbol": "♓", "en": "Pisces", "start": (2, 19), "end": (3, 20), "element": "물",
     "ruler": "해왕성/목성", "mode": "변통궁", "trait": "직감, 공감, 현실도피, 예술적", "body": "발/림프"},
]

# 별자리 원소 → 포켓몬 타입 매핑
_ELEMENT_TYPES = {
    "불": ["fire", "dragon"],
    "땅": ["ground", "rock", "steel"],
    "바람": ["flying", "psychic", "fairy"],
    "물": ["water", "ice", "ghost"],
}

# 황도 별자리 이름 (swisseph 경도 → 별자리)
_ECLIPTIC_SIGNS = [
    "양자리", "황소자리", "쌍둥이자리", "게자리", "사자자리", "처녀자리",
    "천칭자리", "전갈자리", "사수자리", "염소자리", "물병자리", "물고기자리",
]
_ECLIPTIC_SYMBOLS = ["♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓"]

# 행성 이름
_PLANET_NAMES = {
    0: ("태양", "☉"), 1: ("달", "☽"), 2: ("수성", "☿"),
    3: ("금성", "♀"), 4: ("화성", "♂"), 5: ("목성", "♃"), 6: ("토성", "♄"),
}

# 어스펙트 정의
_ASPECTS = {
    "합(☌)": 0, "육합(⚹)": 60, "사각(□)": 90, "삼합(△)": 120, "대립(☍)": 180,
}

# ── 해석 DB ──
_interpretation_db: dict | None = None

def _load_interpretation_db() -> dict:
    """해석 DB JSON 로드 (최초 1회)."""
    global _interpretation_db
    if _interpretation_db is not None:
        return _interpretation_db
    db_path = Path(__file__).parent.parent / "data" / "horoscope_interpretations.json"
    try:
        with open(db_path, "r", encoding="utf-8") as f:
            _interpretation_db = json.load(f)
        _log.info(f"Horoscope DB loaded: {len(_interpretation_db.get('transits', {}))} planets, "
                  f"{len(_interpretation_db.get('aspects', {}))} aspect pairs")
    except Exception as e:
        _log.warning(f"Horoscope DB load failed: {e}")
        _interpretation_db = {"transits": {}, "aspects": {}}
    return _interpretation_db


# 행성 영문키 매핑 (swisseph pid → DB key)
_PLANET_DB_KEYS = {0: "sun", 1: "moon", 2: "mercury", 3: "venus", 4: "mars", 5: "jupiter", 6: "saturn"}
# 별자리 한→영 매핑
_SIGN_EN_MAP = {
    "양자리": "aries", "황소자리": "taurus", "쌍둥이자리": "gemini", "게자리": "cancer",
    "사자자리": "leo", "처녀자리": "virgo", "천칭자리": "libra", "전갈자리": "scorpio",
    "사수자리": "sagittarius", "염소자리": "capricorn", "물병자리": "aquarius", "물고기자리": "pisces",
}


def _build_interpretation_context(sign: dict, transits: dict) -> str:
    """오늘 트랜짓 기반으로 DB 해석을 조합."""
    db = _load_interpretation_db()
    transit_db = db.get("transits", {})
    aspect_db = db.get("aspects", {})

    lines = []

    # 1) 유저 별자리의 지배행성 해석을 최우선
    ruler_name = sign.get("ruler", "")
    sign_name = sign.get("name", "")

    # 2) 각 행성의 현재 별자리 해석
    for p in transits["planets"]:
        planet_ko = p["name"]
        planet_sign_ko = p["sign"]
        # pid → db key
        planet_key = None
        for pid, key in _PLANET_DB_KEYS.items():
            if _PLANET_NAMES[pid][0] == planet_ko:
                planet_key = key
                break
        if not planet_key:
            continue
        sign_key = _SIGN_EN_MAP.get(planet_sign_ko, "")
        if not sign_key:
            continue

        planet_data = transit_db.get(planet_key, {}).get(sign_key)
        if planet_data:
            is_ruler = planet_ko in ruler_name
            prefix = f"★ [지배행성] {planet_ko}→{planet_sign_ko}" if is_ruler else f"{planet_ko}→{planet_sign_ko}"
            lines.append(f"{prefix}: {planet_data['interpretation']}")
            if planet_data.get("shadow"):
                lines.append(f"  그림자: {planet_data['shadow']}")
            if planet_data.get("advice"):
                lines.append(f"  조언: {planet_data['advice']}")

    # 3) 어스펙트 해석
    for asp_text in transits.get("aspects", [])[:6]:
        # "태양합(☌)달" 형식에서 행성쌍 추출
        for asp_name in _ASPECTS:
            if asp_name in asp_text:
                parts = asp_text.split(asp_name)
                if len(parts) == 2:
                    p1_ko, p2_ko = parts[0], parts[1]
                    p1_key = next((k for pid, k in _PLANET_DB_KEYS.items() if _PLANET_NAMES[pid][0] == p1_ko), None)
                    p2_key = next((k for pid, k in _PLANET_DB_KEYS.items() if _PLANET_NAMES[pid][0] == p2_ko), None)
                    if p1_key and p2_key:
                        pair_key = f"{p1_key}_{p2_key}"
                        alt_key = f"{p2_key}_{p1_key}"
                        # 어스펙트 타입 매핑
                        asp_type_map = {"합(☌)": "conjunction", "육합(⚹)": "sextile", "사각(□)": "square",
                                        "삼합(△)": "trine", "대립(☍)": "opposition"}
                        asp_type = asp_type_map.get(asp_name, "")
                        if asp_type:
                            asp_data = aspect_db.get(pair_key, aspect_db.get(alt_key, {}))
                            interp = asp_data.get(asp_type, "")
                            if interp:
                                lines.append(f"[어스펙트] {asp_text}: {interp}")
                break

    return "\n".join(lines) if lines else ""


# ── 캐시 ──
_daily_cache: dict[str, dict] = {}  # key: "YYYY-MM-DD:sign_name"
_transit_cache: dict[str, dict] = {}  # key: "YYYY-MM-DD"


def get_zodiac_sign(birth_date: date) -> dict | None:
    """생년월일 → 별자리 정보 반환."""
    m, d = birth_date.month, birth_date.day
    for sign in ZODIAC_SIGNS:
        sm, sd = sign["start"]
        em, ed = sign["end"]
        if sm <= em:
            if (m == sm and d >= sd) or (m == em and d <= ed) or (sm < m < em):
                return sign
        else:  # 염소자리 (12/22 ~ 1/19)
            if (m == sm and d >= sd) or (m == em and d <= ed) or m > sm or m < em:
                return sign
    return None


def _calculate_transits(target_date: date) -> dict:
    """swisseph로 행성 위치 + 어스펙트 계산."""
    cache_key = str(target_date)
    if cache_key in _transit_cache:
        return _transit_cache[cache_key]

    try:
        import swisseph as swe
        swe.set_ephe_path(None)
    except ImportError:
        _log.error("swisseph not installed")
        return {"planets": [], "aspects": []}

    jd = swe.julday(target_date.year, target_date.month, target_date.day, 12.0)

    planets = []
    longitudes = {}
    for pid, (name_ko, symbol) in _PLANET_NAMES.items():
        result, _ = swe.calc_ut(jd, pid)
        lon = result[0]
        sign_idx = int(lon // 30)
        deg = lon % 30
        planets.append({
            "name": name_ko,
            "symbol": symbol,
            "longitude": round(lon, 2),
            "sign": _ECLIPTIC_SIGNS[sign_idx],
            "sign_symbol": _ECLIPTIC_SYMBOLS[sign_idx],
            "degree": round(deg, 1),
        })
        longitudes[name_ko] = lon

    # 어스펙트 계산 (태양 기준 + 주요 행성 간)
    aspects = []
    planet_names = list(longitudes.keys())
    for i in range(len(planet_names)):
        for j in range(i + 1, len(planet_names)):
            n1, n2 = planet_names[i], planet_names[j]
            diff = abs(longitudes[n1] - longitudes[n2])
            if diff > 180:
                diff = 360 - diff
            for asp_name, asp_angle in _ASPECTS.items():
                orb = 8.0
                if abs(diff - asp_angle) <= orb:
                    aspects.append(f"{n1}{asp_name}{n2}")
                    break

    result = {"planets": planets, "aspects": aspects}
    _transit_cache[cache_key] = result
    return result


def _get_lucky_pokemon(sign: dict, target_date: date) -> dict:
    """별자리 원소 기반 행운의 포켓몬 선택 (날짜별 결정론적)."""
    from models.pokemon_data import ALL_POKEMON
    from models.pokemon_base_stats import POKEMON_BASE_STATS

    element = sign["element"]
    target_types = _ELEMENT_TYPES.get(element, ["normal"])

    # 해당 타입의 포켓몬 필터링 (최종 진화형 우선)
    candidates = []
    for poke in ALL_POKEMON:
        pid = poke[0]
        stats = POKEMON_BASE_STATS.get(pid)
        if not stats:
            continue
        types = stats[-1] if isinstance(stats[-1], list) else [stats[-1]]
        if any(t in target_types for t in types):
            # 진화 가능한 포켓몬 제외 (최종 진화형만)
            if poke[7] is None:  # evolves_to == None
                candidates.append(poke)

    if not candidates:
        # fallback: 진화 여부 무관
        for poke in ALL_POKEMON:
            pid = poke[0]
            stats = POKEMON_BASE_STATS.get(pid)
            if not stats:
                continue
            types = stats[-1] if isinstance(stats[-1], list) else [stats[-1]]
            if any(t in target_types for t in types):
                candidates.append(poke)

    if not candidates:
        candidates = [ALL_POKEMON[0]]

    # 날짜 + 별자리로 시드 → 결정론적 선택
    seed = hashlib.md5(f"{target_date}:{sign['name']}".encode()).hexdigest()
    idx = int(seed, 16) % len(candidates)
    poke = candidates[idx]

    return {
        "id": poke[0],
        "name": poke[1],
        "emoji": poke[3],
        "rarity": poke[4],
    }


def _build_transit_text(transits: dict) -> str:
    """트랜짓 데이터를 AI 프롬프트용 텍스트로 변환."""
    lines = ["[오늘의 행성 배치]"]
    for p in transits["planets"]:
        lines.append(f"{p['symbol']}{p['name']}: {p['sign']}{p['sign_symbol']} {p['degree']}°")
    if transits["aspects"]:
        lines.append(f"\n[주요 어스펙트] {', '.join(transits['aspects'][:8])}")
    return "\n".join(lines)


_HOROSCOPE_SYSTEM_PROMPT = """당신은 20년 경력 서양 점성술사입니다.
아래 제공되는 전문 해석 자료를 바탕으로, 오늘 이 별자리에 해당하는 자연스러운 운세를 작성합니다.

## 역할
- 전문 해석 자료(행성 트랜짓 해석, 어스펙트 해석)가 제공됩니다.
- 이 자료들을 종합하여 오늘의 운세를 자연스러운 2~3문장으로 다듬어 주세요.
- ★ 표시된 지배행성 해석이 가장 중요합니다.

## 해석 원칙
1. ★ 표시된 지배행성 해석이 운세의 70% 이상을 차지해야 합니다. 나머지 행성은 보조적으로만.
2. 이 별자리의 성격 키워드(trait)를 반드시 운세에 녹여 넣으세요. 다른 별자리와 절대 비슷해지면 안 됩니다.
3. 제공된 해석 자료의 내용을 충실히 반영하되, 자연스러운 하나의 이야기로 엮으세요.
4. 긍정일변도 금지. 해석 자료에 부정적 내용이 있으면 반드시 반영하세요.
5. "~할 수 있습니다" 같은 애매한 표현 금지. 단정적으로.
6. 점수는 해석 자료의 톤(positive/negative/mixed)과 그림자 비중을 고려하여 1~5점.

## 출력 형식 (정확히 2줄, 빈 줄 금지)
점수: 1~5 (숫자만)
운세: 2~3문장 서술형. 연애/직장/재물/건강을 자연스럽게 녹여서 하나의 흐름으로 작성. 카테고리 라벨(연애:, 직장: 등) 붙이지 말 것."""


async def _generate_horoscope_ai(sign: dict, transits: dict, target_date: date) -> str | None:
    """Gemini로 별자리 운세 생성."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return None

    transit_text = _build_transit_text(transits)
    interpretation_context = _build_interpretation_context(sign, transits)
    ruler = sign.get("ruler", "")
    mode = sign.get("mode", "")
    trait = sign.get("trait", "")
    body = sign.get("body", "")

    user_prompt = f"""오늘 날짜: {target_date}
별자리: {sign['name']} ({sign['symbol']}, {sign['en']})
원소: {sign['element']} | 지배행성: {ruler} | 모드: {mode}
성격 키워드: {trait}
취약 부위: {body}

{transit_text}

## 전문 해석 자료 (이 내용을 바탕으로 운세를 작성하세요)
{interpretation_context}

위 해석 자료를 종합하여, {sign['name']}의 오늘 운세를 자연스러운 2~3문장으로 작성하세요.
지배행성 {ruler}의 해석을 중심(70%)으로, {sign['name']}의 고유 특성({trait})이 드러나게 작성하세요.
다른 별자리 운세와 절대 비슷해지면 안 됩니다."""

    payload = {
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": _HOROSCOPE_SYSTEM_PROMPT}]},
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 1024,
            "topP": 0.9,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    _log.warning(f"Horoscope AI: Gemini {resp.status}")
                    return None
                data = await resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    return "\n".join(p["text"] for p in parts if "text" in p).strip()
    except Exception as e:
        _log.warning(f"Horoscope AI failed: {e}")
    return None


def _parse_ai_response(text: str) -> dict:
    """AI 응답 파싱 — 서술형."""
    score = 3
    narrative = ""
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("점수:"):
            try:
                score = max(1, min(5, int(line.split(":", 1)[1].strip())))
            except (ValueError, IndexError):
                score = 3
        elif line.startswith("운세:"):
            narrative = line.split(":", 1)[1].strip()
        elif not narrative and not line.startswith("점수"):
            # 라벨 없이 바로 서술이 온 경우
            narrative = line
    stars = "★" * score + "☆" * (5 - score)
    return {"stars": stars, "narrative": narrative}


async def get_daily_horoscope(birth_date: date, user_name: str = "") -> dict | None:
    """데일리 운세 조회 (캐시 우선).

    Returns:
        {"sign": {...}, "horoscope": {...}, "lucky_pokemon": {...}, "transits": {...}}
    """
    sign = get_zodiac_sign(birth_date)
    if not sign:
        return None

    today = config.get_kst_now().date()
    cache_key = f"{today}:{sign['name']}"

    # 캐시 확인
    if cache_key in _daily_cache:
        return _daily_cache[cache_key]

    # 행성 계산
    transits = _calculate_transits(today)

    # AI 운세 생성
    ai_text = await _generate_horoscope_ai(sign, transits, today)
    ai_failed = ai_text is None
    horoscope = _parse_ai_response(ai_text) if ai_text else {
        "stars": "★★★☆☆",
        "narrative": "행성이 조용한 하루입니다. 큰 변화 없이 안정적으로 흘러가니 무리하지 말고 자신에게 집중하세요.",
    }

    # 행운의 포켓몬
    lucky_pokemon = _get_lucky_pokemon(sign, today)

    result = {
        "sign": sign,
        "horoscope": horoscope,
        "lucky_pokemon": lucky_pokemon,
        "transits": transits,
        "date": str(today),
        "ai_failed": ai_failed,
    }
    if not ai_failed:
        _daily_cache[cache_key] = result
    return result


def format_horoscope_group(data: dict, user_name: str) -> str:
    """그룹용 간결한 운세 메시지."""
    sign = data["sign"]
    h = data["horoscope"]
    lp = data["lucky_pokemon"]

    rarity_emoji = {"common": "⚪", "rare": "🔵", "epic": "🟣", "legendary": "🟡", "ultra_legendary": "🔴"}.get(lp["rarity"], "⚪")

    lines = [
        f"🌟 <b>{user_name}</b>의 오늘 운세 ({sign['symbol']} {sign['name']})",
        "",
        f"{h['stars']}",
        f"{h['narrative']}",
        "",
        f"🍀 행운의 포켓몬: {lp['emoji']} <b>{lp['name']}</b> {rarity_emoji}",
    ]
    return "\n".join(lines)


def format_horoscope_dm(data: dict, user_name: str) -> str:
    """DM용 상세 운세 메시지."""
    sign = data["sign"]
    h = data["horoscope"]
    lp = data["lucky_pokemon"]
    transits = data["transits"]

    rarity_emoji = {"common": "⚪", "rare": "🔵", "epic": "🟣", "legendary": "🟡", "ultra_legendary": "🔴"}.get(lp["rarity"], "⚪")

    # 행성 배치 요약 (상위 3개만)
    planet_summary = " · ".join(
        f"{p['symbol']}{p['sign_symbol']}{p['degree']}°"
        for p in transits["planets"][:4]
    )

    lines = [
        f"🌟 <b>{user_name}</b>의 오늘 운세",
        f"{sign['symbol']} <b>{sign['name']}</b> ({sign['en']})",
        "",
        f"{h['stars']}",
        f"{h['narrative']}",
        "",
        f"🍀 행운의 포켓몬: {lp['emoji']} <b>{lp['name']}</b> {rarity_emoji}",
        "",
        f"<i>━ {planet_summary}</i>",
    ]
    return "\n".join(lines)
