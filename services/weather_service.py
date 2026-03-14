"""Weather service: fetch real weather and boost Pokemon types accordingly."""

import logging
import httpx
from datetime import datetime, timedelta
import config

logger = logging.getLogger(__name__)

# In-memory weather cache
_cache = {
    "condition": None,   # rain, snow, thunder, fog, clear_hot, clear_night, wind, clear
    "temp": None,
    "description": "",
    "emoji": "",
    "updated_at": None,
}

# Weather → Pokemon type mapping (Gen 1 IDs)
WEATHER_BOOSTS = {
    "rain": {
        "pokemon_ids": [
            7, 8, 9,        # 꼬부기, 어니부기, 거북왕
            54, 55,          # 고라파덕, 골덕
            60, 61, 62,      # 발챙이, 슈륙챙이, 강챙이
            72, 73,          # 왕눈해, 독파리
            79, 80,          # 야돈, 야도란
            86, 87,          # 쥬쥬, 쥬레곤
            90, 91,          # 셀러, 파르셀
            98, 99,          # 크랩, 킹크랩
            116, 117,        # 쏘드라, 시드라
            118, 119,        # 콘치, 왕콘치
            120, 121,        # 별가사리, 아쿠스타
            129, 130,        # 잉어킹, 갸라도스
            131,             # 라프라스
            134,             # 샤미드
            138, 139,        # 암나이트, 암스타
        ],
        "multiplier": 3.0,
        "emoji": "🌧️",
        "label": "비 오는 날 — 물타입 포켓몬 출현↑",
    },
    "snow": {
        "pokemon_ids": [
            87,              # 쥬레곤
            91,              # 파르셀
            124,             # 루주라
            131,             # 라프라스
            144,             # 프리져
        ],
        "multiplier": 5.0,
        "emoji": "❄️",
        "label": "눈 오는 날 — 얼음타입 포켓몬 출현↑",
    },
    "thunder": {
        "pokemon_ids": [
            25, 26,          # 피카츄, 라이츄
            81, 82,          # 코일, 레어코일
            100, 101,        # 찌리리공, 붐볼
            125,             # 에레브
            135,             # 쥬피썬더
            145,             # 썬더
        ],
        "multiplier": 5.0,
        "emoji": "⛈️",
        "label": "천둥번개 — 전기타입 포켓몬 출현↑",
    },
    "fog": {
        "pokemon_ids": [
            92, 93, 94,      # 고오스, 고우스트, 팬텀
            63, 64, 65,      # 캐이시, 윤겔라, 후딘
            96, 97,          # 슬리프, 슬리퍼
            122,             # 마임맨
            124,             # 루주라
        ],
        "multiplier": 3.0,
        "emoji": "🌫️",
        "label": "안개 낀 날 — 고스트/에스퍼 출현↑",
    },
    "clear_hot": {
        "pokemon_ids": [
            4, 5, 6,         # 파이리, 리자드, 리자몽
            37, 38,          # 식스테일, 나인테일
            58, 59,          # 가디, 윈디
            77, 78,          # 포니타, 날쌩마
            126,             # 마그마
            136,             # 부스터
            146,             # 파이어
        ],
        "multiplier": 3.0,
        "emoji": "☀️",
        "label": "맑고 더운 날 — 불타입 포켓몬 출현↑",
    },
    "clear_night": {
        "pokemon_ids": [
            92, 93, 94,      # 고오스, 고우스트, 팬텀
            41, 42,          # 주뱃, 골뱃
            52, 53,          # 나옹, 페르시온
            96, 97,          # 슬리프, 슬리퍼
        ],
        "multiplier": 2.0,
        "emoji": "🌙",
        "label": "맑은 밤 — 고스트/어둠 포켓몬 출현↑",
    },
    "wind": {
        "pokemon_ids": [
            16, 17, 18,      # 구구, 피죤, 피죤투
            21, 22,          # 깨비참, 깨비드릴조
            41, 42,          # 주뱃, 골뱃
            83,              # 파오리
            84, 85,          # 두두, 두트리오
            142,             # 프테라
        ],
        "multiplier": 3.0,
        "emoji": "💨",
        "label": "바람 부는 날 — 비행타입 포켓몬 출현↑",
    },
    "clear": {
        "pokemon_ids": [
            1, 2, 3,         # 이상해씨, 이상해풀, 이상해꽃
            43, 44, 45,      # 뚜벅쵸, 냄새꼬, 라플레시아
            46, 47,          # 파라스, 파라섹트
            69, 70, 71,      # 모다피, 우츠동, 우츠보트
            102, 103,        # 아라리, 나시
            114,             # 덩쿠리
        ],
        "multiplier": 2.0,
        "emoji": "🌤️",
        "label": "맑은 날 — 풀타입 포켓몬 출현↑",
    },
}


async def fetch_weather(city: str) -> dict | None:
    """Fetch current weather from wttr.in (free, no API key needed)."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"https://wttr.in/{city}?format=j1",
                headers={"Accept-Language": "ko"},
            )
            if resp.status_code != 200:
                logger.warning(f"Weather API returned {resp.status_code}")
                return None

            data = resp.json()
            current = data["current_condition"][0]

            return {
                "temp_c": int(current.get("temp_C", 20)),
                "weather_code": int(current.get("weatherCode", 0)),
                "weather_desc": current.get("lang_ko", [{}])[0].get("value", "")
                    if current.get("lang_ko") else current.get("weatherDesc", [{}])[0].get("value", ""),
                "wind_speed": int(current.get("windspeedKmph", 0)),
                "humidity": int(current.get("humidity", 50)),
                "is_day": current.get("weatherCode", "0") not in ("395", "392"),  # approximate
            }
    except Exception as e:
        logger.error(f"Weather fetch failed: {e}")
        return None


def classify_weather(weather_data: dict) -> str:
    """Classify weather data into our condition categories."""
    if not weather_data:
        return "clear"

    code = weather_data["weather_code"]
    temp = weather_data["temp_c"]
    wind = weather_data["wind_speed"]
    hour = config.get_kst_now().hour

    # Thunder: codes 200, 201, 202, 210, 211, 212, 221, 230, 231, 232
    if code in (200, 201, 202, 210, 211, 212, 221, 230, 231, 232, 386, 389, 392, 395):
        return "thunder"

    # Snow: codes 600-622
    if code in (320, 323, 326, 329, 332, 335, 338, 350, 368, 371, 374, 377,
                600, 601, 602, 611, 612, 615, 616, 620, 621, 622):
        return "snow"

    # Rain: codes 300-531
    if code in (176, 263, 266, 281, 284, 293, 296, 299, 302, 305, 308, 311, 314, 317,
                300, 301, 302, 310, 311, 312, 313, 314, 321,
                500, 501, 502, 503, 504, 511, 520, 521, 522, 531):
        return "rain"

    # Fog: codes 701-762
    if code in (143, 248, 260, 701, 711, 721, 731, 741, 751, 761, 762):
        return "fog"

    # Wind: over 30 km/h
    if wind >= 30:
        return "wind"

    # Clear conditions
    is_night = hour >= 21 or hour < 6

    if is_night:
        return "clear_night"

    if temp >= 30:
        return "clear_hot"

    return "clear"


async def update_weather(city: str):
    """Fetch weather and update cache."""
    weather_data = await fetch_weather(city)
    if not weather_data:
        return

    condition = classify_weather(weather_data)
    boost_info = WEATHER_BOOSTS.get(condition, WEATHER_BOOSTS["clear"])

    _cache["condition"] = condition
    _cache["temp"] = weather_data["temp_c"]
    _cache["description"] = boost_info["label"]
    _cache["emoji"] = boost_info["emoji"]
    _cache["updated_at"] = config.get_kst_now()

    logger.info(
        f"Weather updated: {condition} ({weather_data['temp_c']}°C) "
        f"→ {boost_info['label']}"
    )


def get_current_weather() -> dict:
    """Get cached weather state, re-classifying if time-dependent condition may have changed."""
    result = dict(_cache)

    # 시간 기반 조건(clear_night/clear/clear_hot)은 조회 시점 기준으로 재판정
    if result.get("condition") in ("clear_night", "clear", "clear_hot") and result.get("temp") is not None:
        hour = config.get_kst_now().hour
        is_night = hour >= 21 or hour < 6

        if is_night and result["condition"] != "clear_night":
            result["condition"] = "clear_night"
        elif not is_night and result["condition"] == "clear_night":
            result["condition"] = "clear_hot" if result["temp"] >= 30 else "clear"

        boost_info = WEATHER_BOOSTS.get(result["condition"], WEATHER_BOOSTS["clear"])
        result["description"] = boost_info["label"]
        result["emoji"] = boost_info["emoji"]

    return result


def get_weather_pokemon_boost(pokemon_id: int) -> float:
    """Get spawn weight multiplier for a Pokemon based on current weather."""
    condition = _cache.get("condition")
    if not condition:
        return 1.0

    boost_info = WEATHER_BOOSTS.get(condition)
    if not boost_info:
        return 1.0

    if pokemon_id in boost_info["pokemon_ids"]:
        return boost_info["multiplier"]

    return 1.0


# Weather condition → Pokemon type mapping for custom emoji display
_WEATHER_TYPE_MAP = {
    "rain": "water",
    "snow": "ice",
    "thunder": "electric",
    "fog": "ghost",
    "clear_hot": "fire",
    "clear_night": "dark",
    "wind": "flying",
    "clear": "grass",
}


def get_weather_display() -> str:
    """Get weather display string for spawn messages (custom type emoji)."""
    if not _cache.get("condition") or not _cache.get("updated_at"):
        return ""

    # Don't show if weather data is stale (>2 hours)
    if config.get_kst_now() - _cache["updated_at"] > timedelta(hours=2):
        return ""

    from utils.helpers import _type_emoji
    type_key = _WEATHER_TYPE_MAP.get(_cache["condition"], "")
    if type_key:
        return f" {_type_emoji(type_key)}"
    return f" {_cache['emoji']}"
