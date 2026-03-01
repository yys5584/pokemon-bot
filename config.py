"""Game configuration constants."""

import os
from dotenv import load_dotenv

load_dotenv()

# --- Admin ---
# Comma-separated Telegram user IDs (set in .env)
ADMIN_IDS = [
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
]

# --- Rarity System ---
RARITY_WEIGHTS = {
    "common": 50,
    "rare": 30,
    "epic": 15,
    "legendary": 5,
}

# Midnight bonus (2am-5am KST): rare+ doubled
RARITY_WEIGHTS_MIDNIGHT = {
    "common": 30,
    "rare": 35,
    "epic": 25,
    "legendary": 10,
}

RARITY_EMOJI = {
    "common": "🟢",
    "rare": "🔵",
    "epic": "🟣",
    "legendary": "🟡",
}

RARITY_LABEL = {
    "common": "일반",
    "rare": "희귀",
    "epic": "레어",
    "legendary": "전설",
}

# --- Catch Rates (by rarity, base) ---
CATCH_RATES = {
    "common": 0.70,
    "rare": 0.40,
    "epic": 0.15,
    "legendary": 0.03,
}

# --- Spawn System ---
SPAWN_WINDOW_SECONDS = 60          # Time to catch after spawn
SPAWN_MIN_GAP_HOURS = 2            # Minimum hours between spawns
SPAWN_MIN_MEMBERS = 10             # Minimum members for spawns
MIDNIGHT_BONUS_START = 2           # 2:00 AM KST
MIDNIGHT_BONUS_END = 5             # 5:00 AM KST
SPAWN_RETRY_MIN_SECONDS = 1800     # 30 min retry if no activity
SPAWN_RETRY_MAX_SECONDS = 3600     # 60 min retry if no activity

# Small-group optimized spawn count per day
SPAWN_TIERS = [
    # (min_members, max_members, spawns_per_day)
    (10, 29, 2),
    (30, 49, 3),
    (50, 99, 4),
    (100, 499, 5),
    # 500+: use formula 2 + floor((members - 10) / 500)
]

# --- Catch Limits (Anti-abuse) ---
MAX_CATCH_ATTEMPTS_PER_DAY = 5
CONSECUTIVE_CATCH_COOLDOWN = 2     # After N consecutive catches, skip next

# --- Nurture System ---
MAX_FRIENDSHIP = 5
FEED_PER_DAY = 3                   # /밥 per pokemon per day
PLAY_PER_DAY = 2                   # /놀기 per pokemon per day
FRIENDSHIP_PER_FEED = 1            # +1 per feed
FRIENDSHIP_PER_PLAY = 1            # +1 per play

# --- Title System ---
TITLES = [
    # (min_pokemon_count, title_text, emoji)
    (151, "챔피언", "👑"),
    (120, "포켓몬 마스터", "🏆"),
    (75, "포켓몬 트레이너", "⭐"),
    (45, "포켓몬 수집가", "📦"),
    (15, "초보 트레이너", "🔰"),
]

# Special title
LEGEND_HUNTER_THRESHOLD = 3        # 전설 3마리 이상
LEGEND_HUNTER_TITLE = ("레전드 헌터", "🐉")

# --- Unlockable Titles ---
# title_id: (name, emoji, description, check_type, threshold)
# check_type: pokedex, legendary, catch_fail, midnight_catch, master_ball_own,
#             love_count, trade, common_catch, rare_catch, streak, first_catch,
#             master_ball_use, total_catch
UNLOCKABLE_TITLES = {
    # 도감 기반
    "beginner":     ("초보 트레이너",   "🔰", "도감 15종 달성",          "pokedex", 15),
    "collector":    ("포켓몬 수집가",   "📦", "도감 45종 달성",          "pokedex", 45),
    "trainer":      ("포켓몬 트레이너", "⭐", "도감 75종 달성",          "pokedex", 75),
    "master":       ("포켓몬 마스터",   "🏆", "도감 120종 달성",         "pokedex", 120),
    "champion":     ("챔피언",         "👑", "도감 151종 완성!",        "pokedex", 151),
    "living_dex":   ("살아있는 도감",   "📖", "도감 100종 달성",         "pokedex", 100),
    # 전설
    "legend_hunter":("레전드 헌터",    "🐉", "전설 포켓몬 3마리 포획",   "legendary", 3),
    # 활동 기반
    "first_catch":  ("여정의 시작",    "🌱", "첫 포켓몬 포획",          "first_catch", 1),
    "catch_master": ("잡기의 달인",    "🎯", "포획 성공 100회",         "total_catch", 100),
    "run_expert":   ("도망가 전문가",   "💨", "포획 실패 50회",          "catch_fail", 50),
    "owl":          ("올빼미족",       "🦉", "심야(2~5시) 포획 10회",    "midnight_catch", 10),
    "masterball_rich":("마볼 부자",    "🟣", "마스터볼 5개 보유",        "master_ball_own", 5),
    "decisive":     ("결단의 트레이너", "⚡", "마스터볼 사용 1회",        "master_ball_use", 1),
    "love_fan":     ("문유 광팬",      "💕", "???",                    "love_count", 20),
    "trader":       ("교환의 신",      "🤝", "교환 10회 완료",          "trade", 10),
    # 수집 특화
    "furry":        ("퍼리수집가",     "🐾", "일반 포켓몬 50마리 포획",  "common_catch", 50),
    "rare_hunter":  ("레어 헌터",      "💎", "에픽+전설 10마리 포획",    "rare_catch", 10),
    # 출석
    "diligent":     ("개근상",         "📅", "7일 연속 출석",           "streak", 7),
}

# --- Trade Evolution Pokemon IDs ---
TRADE_EVOLUTION_MAP = {
    64: 65,    # 윤겔라 -> 후딘
    67: 68,    # 근육몬 -> 괴력몬
    75: 76,    # 데구리 -> 딱구리
    93: 94,    # 고우스트 -> 팬텀
}

# --- Eevee Evolution ---
EEVEE_ID = 133
EEVEE_EVOLUTIONS = [134, 135, 136]  # 샤미드, 쥬피썬더, 부스터

# --- Message Templates ---
MSG_SPAWN = "🌿 야생의 {emoji} {name}이(가) 나타났다!\nㅊ 입력으로 잡기 (60초)"
MSG_CATCH_SUCCESS = "딸깍! ✨ {user} — {emoji} {name} 포획!"
MSG_CATCH_FAIL = "흔들흔들... 💨 도망갔다!"
MSG_CATCH_FIRST = "🌟 {user} — {emoji} {name} 포획! (이 방 최초)"
MSG_CATCH_ATTEMPT = "🎯 {user} 도전!"

# --- Event Templates ---
EVENT_TEMPLATES = {
    "스폰2배": {
        "event_type": "spawn_boost",
        "multiplier": 2.0,
        "target": None,
        "description": "🎪 스폰 2배! 전체 채팅방 스폰 횟수 2배",
    },
    "포획2배": {
        "event_type": "catch_boost",
        "multiplier": 2.0,
        "target": None,
        "description": "🎯 포획률 2배! 모든 포켓몬 포획 확률 2배",
    },
    "전설출현": {
        "event_type": "rarity_boost",
        "multiplier": 5.0,
        "target": "legendary",
        "description": "🌟 전설 출현! 전설 포켓몬 출현률 5배",
    },
    "에픽출현": {
        "event_type": "rarity_boost",
        "multiplier": 3.0,
        "target": "epic",
        "description": "💎 에픽 출현! 에픽 포켓몬 출현률 3배",
    },
    "레어출현": {
        "event_type": "rarity_boost",
        "multiplier": 2.0,
        "target": "rare",
        "description": "🔵 레어 출현! 희귀 포켓몬 출현률 2배",
    },
    "이브이데이": {
        "event_type": "pokemon_boost",
        "multiplier": 10.0,
        "target": "133",
        "description": "🦊 이브이 데이! 이브이 출현률 대폭 증가",
    },
    "피카츄데이": {
        "event_type": "pokemon_boost",
        "multiplier": 10.0,
        "target": "25",
        "description": "⚡ 피카츄 데이! 피카츄 출현률 대폭 증가",
    },
    "친밀도2배": {
        "event_type": "friendship_boost",
        "multiplier": 2.0,
        "target": None,
        "description": "💕 친밀도 2배! 밥/놀기 효과 2배",
    },
}
