"""
데일리 별자리 운세 서비스.

swisseph로 실제 행성 위치 계산 → Gemini AI 해석 생성.
별자리별 하루 1회 캐싱, 행운의 포켓몬 포함.
"""

import hashlib
import logging
import os
from datetime import date, datetime

import aiohttp

import config

_log = logging.getLogger(__name__)

# ── 별자리 데이터 ──

ZODIAC_SIGNS = [
    {"name": "양자리", "symbol": "♈", "en": "Aries", "start": (3, 21), "end": (4, 19), "element": "불"},
    {"name": "황소자리", "symbol": "♉", "en": "Taurus", "start": (4, 20), "end": (5, 20), "element": "땅"},
    {"name": "쌍둥이자리", "symbol": "♊", "en": "Gemini", "start": (5, 21), "end": (6, 21), "element": "바람"},
    {"name": "게자리", "symbol": "♋", "en": "Cancer", "start": (6, 22), "end": (7, 22), "element": "물"},
    {"name": "사자자리", "symbol": "♌", "en": "Leo", "start": (7, 23), "end": (8, 22), "element": "불"},
    {"name": "처녀자리", "symbol": "♍", "en": "Virgo", "start": (8, 23), "end": (9, 22), "element": "땅"},
    {"name": "천칭자리", "symbol": "♎", "en": "Libra", "start": (9, 23), "end": (10, 23), "element": "바람"},
    {"name": "전갈자리", "symbol": "♏", "en": "Scorpio", "start": (10, 24), "end": (11, 22), "element": "물"},
    {"name": "사수자리", "symbol": "♐", "en": "Sagittarius", "start": (11, 23), "end": (12, 21), "element": "불"},
    {"name": "염소자리", "symbol": "♑", "en": "Capricorn", "start": (12, 22), "end": (1, 19), "element": "땅"},
    {"name": "물병자리", "symbol": "♒", "en": "Aquarius", "start": (1, 20), "end": (2, 18), "element": "바람"},
    {"name": "물고기자리", "symbol": "♓", "en": "Pisces", "start": (2, 19), "end": (3, 20), "element": "물"},
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


_HOROSCOPE_SYSTEM_PROMPT = """당신은 서양 점성술 전문가입니다.
실제 천문학적 행성 배치(트랜짓) 데이터를 기반으로 운세를 해석합니다.
반드시 제공된 행성 위치와 어스펙트를 근거로 해석하세요.
너무 뻔하거나 긍정일변도가 아닌, 구체적이고 날카로운 조언을 해주세요.

반드시 아래 7줄을 빠짐없이 모두 출력하세요. 마크다운 사용 금지.
각 줄은 반드시 해당 라벨로 시작해야 합니다:

종합: ★★★★ (★ 1~5개)
한줄: 오늘은 직감을 믿어야 할 때 (15자 이내)
연애: 진심을 표현하면 좋은 반응 (20자 이내)
직장: 새 프로젝트 제안에 적기 (20자 이내)
재운: 충동구매 주의, 저축 우선 (20자 이내)
건강: 수분 섭취와 스트레칭 필수 (20자 이내)
조언: 작은 변화가 큰 흐름을 만듭니다 (25자 이내)"""


async def _generate_horoscope_ai(sign: dict, transits: dict, target_date: date) -> str | None:
    """Gemini로 별자리 운세 생성."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return None

    transit_text = _build_transit_text(transits)
    user_prompt = f"""오늘 날짜: {target_date}
별자리: {sign['name']} ({sign['symbol']}, {sign['en']})
원소: {sign['element']}

{transit_text}

위 행성 배치를 기반으로 {sign['name']}의 오늘 운세를 해석해주세요.
어스펙트 중 이 별자리에 직접 영향을 주는 것을 중심으로 해석하세요."""

    payload = {
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": _HOROSCOPE_SYSTEM_PROMPT}]},
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 1024,
            "topP": 0.9,
        },
    }
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
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
    """AI 응답 파싱."""
    result = {"stars": "★★★", "summary": "", "love": "", "work": "", "money": "", "health": "", "advice": ""}
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("종합:"):
            result["stars"] = line.split(":", 1)[1].strip()
        elif line.startswith("한줄:"):
            result["summary"] = line.split(":", 1)[1].strip()
        elif line.startswith("연애:"):
            result["love"] = line.split(":", 1)[1].strip()
        elif line.startswith("직장:"):
            result["work"] = line.split(":", 1)[1].strip()
        elif line.startswith("재운:"):
            result["money"] = line.split(":", 1)[1].strip()
        elif line.startswith("건강:"):
            result["health"] = line.split(":", 1)[1].strip()
        elif line.startswith("조언:"):
            result["advice"] = line.split(":", 1)[1].strip()
    return result


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
    horoscope = _parse_ai_response(ai_text) if ai_text else {
        "stars": "★★★",
        "summary": "행성이 조용한 하루",
        "love": "평온한 관계 유지",
        "work": "꾸준함이 빛나는 날",
        "money": "무리한 지출 자제",
        "health": "가벼운 산책 추천",
        "advice": "오늘은 자신에게 집중하세요",
    }

    # 행운의 포켓몬
    lucky_pokemon = _get_lucky_pokemon(sign, today)

    result = {
        "sign": sign,
        "horoscope": horoscope,
        "lucky_pokemon": lucky_pokemon,
        "transits": transits,
        "date": str(today),
    }
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
        f"💫 {h['stars']}  {h['summary']}",
        f"❤️ {h['love']}",
        f"💼 {h['work']}",
        f"💰 {h['money']}",
        f"🏥 {h['health']}",
        f"📌 {h['advice']}",
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
        f"💫 {h['stars']}  {h['summary']}",
        "",
        f"❤️ 연애  {h['love']}",
        f"💼 직장  {h['work']}",
        f"💰 재운  {h['money']}",
        f"🏥 건강  {h['health']}",
        f"📌 조언  {h['advice']}",
        "",
        f"🍀 행운의 포켓몬: {lp['emoji']} <b>{lp['name']}</b> {rarity_emoji}",
        "",
        f"<i>━ {planet_summary}</i>",
        "",
        "🔮 더 자세한 리딩 → /타로",
    ]
    return "\n".join(lines)
