"""Game configuration constants."""

import os
import datetime as _dt
import zoneinfo as _zi
from dotenv import load_dotenv

# --- Timezone (KST) ---
KST = _zi.ZoneInfo("Asia/Seoul")

def get_kst_now() -> _dt.datetime:
    """KST 기준 현재 시각."""
    return _dt.datetime.now(KST)

def get_kst_today() -> str:
    """KST 기준 오늘 날짜 (YYYY-MM-DD)."""
    return get_kst_now().strftime("%Y-%m-%d")

def get_kst_hour() -> int:
    """KST 기준 현재 시각 (0-23)."""
    return get_kst_now().hour

load_dotenv()

# --- Admin ---
# Comma-separated Telegram user IDs (set in .env)
ADMIN_IDS = [
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
]

# --- URLs ---
BOT_CHANNEL_URL = "https://t.me/tg_poke"
DASHBOARD_URL = "https://tgpoke.com"

# --- Rarity System ---
RARITY_WEIGHTS = {
    "common": 49.5,           # ~49.7%
    "rare": 30,               # ~30.2%
    "epic": 15,               # ~15.1%
    "legendary": 4,           # ~4.0%
    "ultra_legendary": 1.5,   # ~1.5%
}

# Midnight bonus (2am-5am KST): rare+ 추가 부스트
RARITY_WEIGHTS_MIDNIGHT = {
    "common": 40,             # ~40%
    "rare": 30,               # ~30%
    "epic": 20,               # ~20%
    "legendary": 8,           # ~8%
    "ultra_legendary": 2,     # ~2%
}

RARITY_EMOJI = {
    "common": "🟢",
    "rare": "🔵",
    "epic": "🟣",
    "legendary": "🟡",
    "ultra_legendary": "🔴",
}

RARITY_LABEL = {
    "common": "일반",
    "rare": "희귀",
    "epic": "에픽",
    "legendary": "전설",
    "ultra_legendary": "초전설",
}

# --- Catch Rates (by rarity, base) ---
# 참고용: 실제 포획률은 pokemon_master.catch_rate (DB) 사용
CATCH_RATES = {
    "common": 0.80,
    "rare": 0.50,
    "epic": 0.15,
    "legendary": 0.05,
    "ultra_legendary": 0.03,
}

# --- Spawn System ---
SPAWN_WINDOW_SECONDS = 60          # Time to catch after spawn
SPAWN_MIN_GAP_HOURS = 2            # Minimum hours between spawns
SPAWN_MIN_MEMBERS = 10             # Minimum members for spawns
MIDNIGHT_BONUS_START = 2           # 2:00 AM KST
MIDNIGHT_BONUS_END = 5             # 5:00 AM KST
SPAWN_RETRY_MIN_SECONDS = 1800     # 30 min retry if no activity
SPAWN_RETRY_MAX_SECONDS = 3600     # 60 min retry if no activity
SPAWN_COOLDOWN_SECONDS = 300       # 5 min minimum between spawns
SPAWN_MAX_DAILY = 12               # Absolute max spawns per day per chat (regardless of multiplier)

# --- Arcade Channel (30초마다 강제스폰) ---
ARCADE_CHAT_IDS: set[int] = set()  # 채팅방 등록 후 chat_id 추가
ARCADE_SPAWN_INTERVAL = 30         # 초 (관리자 등록 아케이드)
ARCADE_TICKET_SPAWN_INTERVAL = 60  # 초 (티켓 아케이드)
ARCADE_SPAWN_WINDOW = 25           # 초 (포획 제한시간, 겹침 방지)

# --- Auto-delete Timers (seconds) ---
AUTO_DEL_CATCH_CMD = 3          # ㅊ 명령어 삭제 (바로)
AUTO_DEL_CATCH_ATTEMPT = 5      # "🎯 도전!" 메시지 삭제
AUTO_DEL_CATCH_RESULT = 15      # 포획 성공/실패 결과 삭제
AUTO_DEL_SPAWN_ESCAPE = 10      # 도망 메시지 삭제
AUTO_DEL_FORCE_SPAWN_CMD = 3    # 강스/강스권 명령어 삭제
AUTO_DEL_FORCE_SPAWN_RESP = 10  # 강스 응답 메시지 삭제

# Small-group optimized spawn count per day
SPAWN_TIERS = [
    # (min_members, max_members, spawns_per_day)
    (10, 49, 2),
    (50, 499, 3),
    (500, 999, 4),
    (1000, 99999, 5),
]

# --- Catch Limits (Anti-abuse) ---
MAX_CATCH_ATTEMPTS_PER_DAY = 20
CONSECUTIVE_CATCH_COOLDOWN = 2     # After N consecutive catches, skip next

# --- Nurture System ---
MAX_FRIENDSHIP = 5
FEED_PER_DAY = 3                   # /밥 per pokemon per day
PLAY_PER_DAY = 2                   # /놀기 per pokemon per day
FRIENDSHIP_PER_FEED = 1            # +1 per feed
FRIENDSHIP_PER_PLAY = 1            # +1 per play

# --- Trade ---
TRADE_BP_COST = 150                # 교환 시 BP 비용

# --- Marketplace ---
MARKET_FEE_RATE = 0.05             # 5% 판매 수수료
MARKET_MIN_PRICE = 100             # 최소 등록가 (BP)
MARKET_PAGE_SIZE = 5               # 페이지당 목록 수
MARKET_MAX_ACTIVE_LISTINGS = 10    # 유저당 최대 동시 등록 수
MARKET_LISTING_EXPIRE_DAYS = 7     # 등록 만료 기간 (일)

# --- Daily Missions ---
MISSION_POOL = {
    "catch":  {"label": "포켓몬 포획", "icon": "gotcha",   "target": 3},
    "feed":   {"label": "밥주기",     "icon": "ham",      "target": 3},
    "play":   {"label": "놀아주기",   "icon": "game",     "target": 2},
    "battle": {"label": "배틀 승리",  "icon": "battle",   "target": 1},
    "trade":  {"label": "교환 완료",  "icon": "exchange",  "target": 1},
}
MISSION_COUNT = 4                 # 하루 미션 수 (풀에서 랜덤 선택)
MISSION_REWARD_BP = 50            # 개별 미션 보상 BP
MISSION_REWARD_HYPER = 1          # 개별 미션 보상 하이퍼볼
MISSION_ALLCLEAR_MASTER = 1       # 전체 완료 보상 마스터볼

# --- Group Trade ---
GROUP_TRADE_TIMEOUT = 300          # 5분 자동 만료 (초)
GROUP_TRADE_BP_COST = 50           # 그룹 교환 비용 (BP)

# --- Title System ---
TITLES = [
    # (min_pokemon_count, title_text, emoji)
    (386, "그랜드마스터", "💫"),
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
    # 1세대 도감 기반 (관동)
    "beginner":     ("초보 트레이너",   "caterpie",   "1세대 도감 15종 달성",     "pokedex_gen1", 15),
    "collector":    ("포켓몬 수집가",   "rattata",    "1세대 도감 45종 달성",     "pokedex_gen1", 45),
    "trainer":      ("포켓몬 트레이너", "pikachu",    "1세대 도감 75종 달성",     "pokedex_gen1", 75),
    "master":       ("포켓몬 마스터",   "charmander", "1세대 도감 120종 달성",    "pokedex_gen1", 120),
    "champion":     ("챔피언",         "crown",      "1세대 도감 151종 완성!",   "pokedex_gen1", 151),
    "living_dex":   ("살아있는 도감",   "bulbasaur",  "1세대 도감 100종 달성",    "pokedex_gen1", 100),
    # 2세대 도감 기반 (성도)
    "gen2_starter":   ("성도의 초보",    "chikorita",  "2세대 도감 15종 달성",   "pokedex_gen2", 15),
    "gen2_collector": ("성도 수집가",    "bellsprout",  "2세대 도감 45종 달성",   "pokedex_gen2", 45),
    "gen2_trainer":   ("성도 트레이너",  "eevee",      "2세대 도감 75종 달성",   "pokedex_gen2", 75),
    "gen2_master":    ("성도 마스터",    "victini",    "2세대 도감 100종 완성!", "pokedex_gen2", 100),
    # 3세대 도감 기반 (호연)
    "gen3_starter":   ("호연의 초보",    "squirtle",   "3세대 도감 15종 달성",   "pokedex_gen3", 15),
    "gen3_collector": ("호연 수집가",    "abra",       "3세대 도감 45종 달성",   "pokedex_gen3", 45),
    "gen3_trainer":   ("호연 트레이너",  "snorlax",    "3세대 도감 75종 달성",   "pokedex_gen3", 75),
    "gen3_master":    ("호연 마스터",    "moltres",    "3세대 도감 135종 완성!", "pokedex_gen3", 135),
    # 전체 도감
    "grand_master":   ("그랜드마스터",   "mew",        "전체 도감 386종 완성!",  "pokedex_all", 386),
    # 전설
    "legend_hunter":("레전드 헌터",    "dratini",    "전설 포켓몬 3마리 포획",   "legendary", 3),
    # 활동 기반
    "first_catch":  ("여정의 시작",    "bulbasaur",  "첫 포켓몬 포획",          "first_catch", 1),
    "catch_master": ("잡기의 달인",    "mankey",     "포획 성공 100회",         "total_catch", 100),
    "run_expert":   ("도망가 전문가",   "zubat",      "포획 실패 50회",          "catch_fail", 50),
    "owl":          ("올빼미족",       "venonat",    "심야(2~5시) 포획 10회",    "midnight_catch", 10),
    "masterball_rich":("마볼 부자",    "meowth",     "마스터볼 5개 보유",        "master_ball_own", 5),
    "decisive":     ("결단의 트레이너", "pikachu",    "마스터볼 사용 1회",        "master_ball_use", 1),
    "love_fan":     ("문유 광팬",      "jigglypuff", "???",                    "love_count", 20),
    "trader":       ("교환의 신",      "abra",       "교환 10회 완료",          "trade", 10),
    # 수집 특화
    "furry":        ("퍼리수집가",     "eevee",      "일반 포켓몬 50마리 포획",  "common_catch", 50),
    "rare_hunter":  ("레어 헌터",      "articuno",   "에픽+전설 10마리 포획",    "rare_catch", 10),
    # 출석
    "diligent":     ("개근상",         "snorlax",    "7일 연속 출석",           "streak", 7),
    # 배틀 칭호
    "battle_first":    ("첫 배틀",       "squirtle",   "배틀 1회 참여",     "battle_total", 1),
    "battle_fighter":  ("배틀 파이터",   "mankey",     "배틀 5승 달성",     "battle_wins", 5),
    "battle_champion": ("배틀 챔피언",   "charmander", "배틀 20승 달성",    "battle_wins", 20),
    "battle_legend":   ("배틀 레전드",   "crown",      "배틀 50승 달성",    "battle_wins", 50),
    "battle_streak3":  ("연승 전사",     "moltres",    "3연승 달성",        "battle_streak", 3),
    "battle_streak10": ("무적의 전사",   "psyduck",    "10연승 달성",       "battle_streak", 10),
    "battle_sweep":    ("완벽한 승리",   "victini",    "무피해 완승",       "battle_sweep", 1),
    "partner_set":     ("나의 파트너",   "pikachu",    "파트너 포켓몬 지정", "partner_set", 1),
    # 튜토리얼
    "tutorial_grad":   ("내 꿈은 피카츄!", "pikachu",  "튜토리얼 완료",     "tutorial_complete", 1),
    # 뉴비 여정 졸업
    "newbie_graduate": ("신예 트레이너",   "gotcha",   "뉴비 여정 졸업",    "journey_graduate", 1),
}

# --- Trade Evolution Pokemon IDs ---
TRADE_EVOLUTION_MAP = {
    # Gen 1
    64: 65,    # 윤겔라 -> 후딘
    67: 68,    # 근육몬 -> 괴력몬
    75: 76,    # 데구리 -> 딱구리
    93: 94,    # 고우스트 -> 팬텀
    # Gen 2 (cross-gen trade evolutions)
    61: 186,   # 강챙이 -> 왕구리
    79: 199,   # 야도란 -> 야도킹
    95: 208,   # 롱스톤 -> 강철톤
    117: 230,  # 시드라 -> 킹드라
    123: 212,  # 스라크 -> 핫삼
    137: 233,  # 폴리곤 -> 폴리곤2
    # Gen 3
    349: 350,  # 빈티나 -> 밀로틱
    366: 367,  # 진주몽 -> 헌테일
}

# --- Eevee Evolution ---
EEVEE_ID = 133
EEVEE_EVOLUTIONS = [134, 135, 136, 196, 197]  # 샤미드, 쥬피썬더, 부스터, 에브이, 블래키

# --- Message Templates ---
MSG_SPAWN = "🌿 야생의 {emoji} {name}이(가) 나타났다!\nㅊ 입력으로 잡기 (60초)"
MSG_CATCH_SUCCESS = "딸깍! {user} — {emoji} {name} 포획!"
MSG_CATCH_FAIL = "흔들흔들... 💨 도망갔다!"
MSG_CATCH_FIRST = "🌟 {user} — {emoji} {name} 포획! (이 방 최초)"
MSG_CATCH_ATTEMPT = "{ball} {user} 포켓볼을 던졌다!"

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
    "초전설출현": {
        "event_type": "rarity_boost",
        "multiplier": 5.0,
        "target": "ultra_legendary",
        "description": "🔴 초전설 출현! 초전설 포켓몬 출현률 5배",
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
    "이로치2배": {
        "event_type": "shiny_boost",
        "multiplier": 2.0,
        "target": None,
        "description": "✨ 이로치 2배! 이로치 출현 확률 2배",
    },
}

# ============================================================
# Battle System
# ============================================================

# --- IV (Individual Values) System ---
IV_MIN = 0
IV_MAX = 31
IV_MULT_MIN = 0.85        # IV 0 = 0.85x
IV_MULT_RANGE = 0.30      # IV 31 = 1.15x (0.85 + 0.30)
IV_SHINY_MIN = 10         # 이로치 최소 IV (10~31)
IV_STAT_COUNT = 6          # 6스탯: HP, ATK, DEF, SPA, SPDEF, SPD

# IV grade thresholds (total of 6 stats, max=186)
IV_GRADE_THRESHOLDS = [
    (160, "S", ""),   # ~86%+ (top ~0.3%)
    (120, "A", ""),   # ~65%+ (top ~12%)
    (93,  "B", ""),   # ~50%+
    (62,  "C", ""),   # ~33%+
    (0,   "D", ""),   # bottom ~8%
]

def get_iv_grade(total: int) -> tuple[str, str]:
    """Return (grade_letter, display) for an IV total (0~186)."""
    for threshold, grade, display in IV_GRADE_THRESHOLDS:
        if total >= threshold:
            return grade, display
    return "D", ""

# --- Battle Stats ---
RARITY_BASE_STAT = {
    "common": 65, "rare": 85, "epic": 110, "legendary": 150,
    "ultra_legendary": 180,
}

# Phase 2 (실제 베이스스탯) 레어리티 보정 배율
# 커먼/레어의 원작 베이스스탯이 낮아 격차가 너무 큼 → 보정
RARITY_BATTLE_MULT = {
    "common": 1.15,          # +15% 보정
    "rare": 1.05,            # +5% 보정
    "epic": 1.0,
    "legendary": 1.0,
    "ultra_legendary": 1.0,   # 보정 없음 (이미 최강 — 코스트 구조로 필수 편성 유도)
}

STAT_SPREADS = {
    "offensive":  {"hp": 0.9, "atk": 1.3, "def": 0.8, "spa": 1.3, "spdef": 0.8, "spd": 1.0},
    "defensive":  {"hp": 1.2, "atk": 0.8, "def": 1.3, "spa": 0.8, "spdef": 1.3, "spd": 0.8},
    "balanced":   {"hp": 1.0, "atk": 1.0, "def": 1.0, "spa": 1.0, "spdef": 1.0, "spd": 1.0},
    "speedy":     {"hp": 0.8, "atk": 1.0, "def": 0.7, "spa": 1.0, "spdef": 0.7, "spd": 1.4},
}

FRIENDSHIP_BONUS = 0.04  # 친밀도 1당 +4% (최대 5 = +20%)

# 진화 단계별 스탯 보정 (1단 < 2단 < 최종)
EVOLUTION_STAGE_MULT = {1: 0.85, 2: 0.92, 3: 1.0}

# --- Type System (18종 풀타입) ---
TYPE_EMOJI = {
    "normal": "⚪", "fire": "🔥", "water": "💧", "grass": "🌿",
    "electric": "⚡", "ice": "❄️", "fighting": "👊", "poison": "☠️",
    "ground": "🌍", "flying": "🕊️", "psychic": "🔮", "bug": "🐛",
    "rock": "🪨", "ghost": "👻", "dragon": "🐉", "dark": "🌑",
    "steel": "⚙️", "fairy": "🧚",
}

TYPE_NAME_KO = {
    "normal": "노말", "fire": "불꽃", "water": "물", "grass": "풀",
    "electric": "전기", "ice": "얼음", "fighting": "격투", "poison": "독",
    "ground": "땅", "flying": "비행", "psychic": "에스퍼", "bug": "벌레",
    "rock": "바위", "ghost": "고스트", "dragon": "드래곤", "dark": "악",
    "steel": "강철", "fairy": "페어리",
}

# 타입 상성: key가 value 리스트 타입에 효과적 (1.3x)
TYPE_ADVANTAGE = {
    "normal":   [],
    "fire":     ["grass", "ice", "bug", "steel"],
    "water":    ["fire", "ground", "rock"],
    "grass":    ["water", "ground", "rock"],
    "electric": ["water", "flying"],
    "ice":      ["grass", "ground", "flying", "dragon"],
    "fighting": ["normal", "ice", "rock", "dark", "steel"],
    "poison":   ["grass", "fairy"],
    "ground":   ["fire", "electric", "poison", "rock", "steel"],
    "flying":   ["grass", "fighting", "bug"],
    "psychic":  ["fighting", "poison"],
    "bug":      ["grass", "psychic", "dark"],
    "rock":     ["fire", "ice", "flying", "bug"],
    "ghost":    ["psychic", "ghost"],
    "dragon":   ["dragon"],
    "dark":     ["psychic", "ghost"],
    "steel":    ["ice", "rock", "fairy"],
    "fairy":    ["fighting", "dragon", "dark"],
}

# 타입 면역: key 타입 공격이 value 리스트 타입에 무효 (0x, 본가 동일)
TYPE_IMMUNITY = {
    "normal":   ["ghost"],
    "fighting": ["ghost"],
    "poison":   ["steel"],
    "ground":   ["flying"],
    "electric": ["ground"],
    "psychic":  ["dark"],
    "ghost":    ["normal"],
    "dragon":   ["fairy"],
}

# 타입 내성: key 타입으로 공격 시 value 리스트 타입이 반감 (0.5x, 본가 Gen6+ 동일)
TYPE_RESISTANCE = {
    "normal":   ["rock", "steel"],
    "fire":     ["fire", "water", "rock", "dragon"],
    "water":    ["water", "grass", "dragon"],
    "grass":    ["fire", "grass", "poison", "flying", "bug", "dragon", "steel"],
    "electric": ["grass", "electric", "dragon"],
    "ice":      ["fire", "water", "ice", "steel"],
    "fighting": ["poison", "flying", "psychic", "bug", "fairy"],
    "poison":   ["poison", "ground", "rock", "ghost"],
    "ground":   ["grass", "bug"],
    "flying":   ["electric", "rock", "steel"],
    "psychic":  ["psychic", "steel"],
    "bug":      ["fire", "fighting", "poison", "flying", "ghost", "steel", "fairy"],
    "rock":     ["fighting", "ground", "steel"],
    "ghost":    ["dark"],
    "dragon":   ["steel"],
    "dark":     ["fighting", "dark", "fairy"],
    "steel":    ["fire", "water", "electric", "steel"],
    "fairy":    ["fire", "poison", "steel"],
}

# --- Battle Rules ---
BATTLE_CHALLENGE_TIMEOUT = 30       # 도전 대기 시간 (초)
BATTLE_COOLDOWN_SAME = 300          # 같은 상대 쿨다운 (5분)
BATTLE_COOLDOWN_GLOBAL = 60         # 전체 배틀 쿨다운 (1분)
BATTLE_MAX_ROUNDS = 50              # 최대 라운드
BATTLE_TEAM_MIN = 1                 # 최소 팀원
BATTLE_TEAM_MAX = 6                 # 최대 팀원
BATTLE_HP_MULTIPLIER = 2             # 전투 HP 배수 (체력 2배 → 긴 전투)
BATTLE_CRIT_RATE = 0.10             # 크리티컬 확률 10%
BATTLE_CRIT_MULT = 1.5              # 크리티컬 배수
BATTLE_TYPE_ADVANTAGE_MULT = 2.0    # 타입 유리 (본가 동일)
BATTLE_TYPE_DISADVANTAGE_MULT = 0.5 # 타입 불리 (본가 동일)
BATTLE_PARTNER_ATK_BONUS = 0.05     # 파트너 ATK 보너스 5%
BATTLE_SKILL_RATE = 0.30             # 고유기술 발동 확률 30%
BATTLE_BASE_POWER = 130              # 기본 기술위력 (본가 스타일 데미지 공식)

# --- BP (Battle Points) ---
BP_WIN_BASE = 20                    # 승리 기본 BP
BP_WIN_PER_ENEMY = 2               # 상대 팀 사이즈당 추가 BP
BP_LOSE = 5                         # 패배 참여 보상
BP_PERFECT_WIN = 50                 # 무피해 완승 보너스
BP_STREAK_BONUS = 10                # 3연승마다 추가
BP_MASTERBALL_COST = 200            # 마스터볼 1개 가격
BP_MASTERBALL_DAILY_LIMIT = 3       # 마스터볼 일일 구매 제한
BP_MASTERBALL_PRICES = [200, 300, 500]  # 점진적 가격 (1/2/3번째)
BP_FORCE_SPAWN_TICKET_COST = 500      # 강제스폰권 가격 (이벤트: 무료, 원래 500)
BP_POKEBALL_RESET_COST = 200          # 포켓볼 초기화(100개) 가격 (이벤트: 무료, 원래 200)
BP_HYPER_BALL_COST = 20              # 하이퍼볼 1회 사용 BP
HYPER_BALL_CATCH_MULTIPLIER = 3.0    # 하이퍼볼 포획률 배수

# --- Arcade Pass ---
ARCADE_PASS_COST = 200               # 아케이드 이용권 가격 (BP)
ARCADE_PASS_DURATION = 3600          # 이용권 지속시간 (초) = 1시간
ARCADE_PASS_DAILY_LIMIT = 3          # 일일 구매 제한

# --- Shiny System ---
SHINY_RATE_NATURAL = 0.10            # 자연 스폰 이로치 확률 10%
SHINY_RATE_FORCE = 0.02              # 강제스폰 이로치 확률 2%
SHINY_RATE_ARCADE = 0.01             # 아케이드 이로치 확률 1%

# ─── 채팅방 레벨 시스템 ─────────────────────────────────
# (level, required_cxp, spawn_bonus, shiny_boost_pct, rarity_boosts, special)
CHAT_LEVEL_TABLE = [
    # (level, required_cxp, spawn_bonus, shiny_boost_pct, rarity_boosts, special)
    # Lv.10 ≈ 60일 (일일캡 50 CXP 기준), 모든 값 50 단위
    (1,  0,     0, 0.0, {},                                    None),
    (2,  100,   1, 0.2, {},                                    None),
    (3,  200,   1, 0.4, {"epic": 1.10},                        None),
    (4,  300,   2, 0.6, {"epic": 1.10, "legendary": 1.05},     "daily_shiny"),
    (5,  500,   2, 0.8, {"epic": 1.10, "legendary": 1.05},     "hall_of_fame"),
    (6,  750,   3, 1.0, {"epic": 1.15, "legendary": 1.05},     None),
    (7,  1050,  3, 1.2, {"epic": 1.15, "legendary": 1.10},     None),
    (8,  1500,  3, 1.4, {"epic": 1.15, "legendary": 1.10},     "auto_arcade"),
    (9,  2100,  4, 1.7, {"epic": 1.20, "legendary": 1.10},     None),
    (10, 3000,  4, 2.0, {"epic": 1.20, "legendary": 1.15},     "leaderboard"),
]

CXP_PER_CATCH = 1
CXP_PER_BATTLE = 2
CXP_PER_TRADE = 1
CXP_PER_FORCE_SPAWN = 1
CXP_DAILY_CAP = 50
AUTO_ARCADE_DURATION = 3600          # Lv.8 자동 아케이드 (1시간, 초)


def get_chat_level_info(cxp: int) -> dict:
    """CXP로 현재 레벨 + 혜택 조회."""
    result = CHAT_LEVEL_TABLE[0]
    for row in CHAT_LEVEL_TABLE:
        if cxp >= row[1]:
            result = row
        else:
            break
    level, _req, spawn_bonus, shiny_pct, rarity_boosts, _special = result

    # 다음 레벨까지 필요 CXP
    next_cxp = None
    for row in CHAT_LEVEL_TABLE:
        if row[1] > cxp:
            next_cxp = row[1]
            break

    # 이 레벨 이하 모든 special 혜택 수집
    specials = set()
    for row in CHAT_LEVEL_TABLE:
        if row[0] <= level and row[5]:
            specials.add(row[5])

    return {
        "level": level,
        "spawn_bonus": spawn_bonus,
        "shiny_boost_pct": shiny_pct,
        "rarity_boosts": rarity_boosts,
        "specials": specials,
        "next_cxp": next_cxp,
    }

# --- Battle Titles ---
# title_id: (name, emoji, description, check_type, threshold)
BATTLE_TITLES = {
    "battle_first":    ("첫 배틀",       "squirtle",   "배틀 1회 참여",     "battle_total", 1),
    "battle_fighter":  ("배틀 파이터",   "mankey",     "배틀 5승 달성",     "battle_wins", 5),
    "battle_champion": ("배틀 챔피언",   "charmander", "배틀 20승 달성",    "battle_wins", 20),
    "battle_legend":   ("배틀 레전드",   "crown",      "배틀 50승 달성",    "battle_wins", 50),
    "battle_streak3":  ("연승 전사",     "moltres",    "3연승 달성",        "battle_streak", 3),
    "battle_streak10": ("무적의 전사",   "psyduck",    "10연승 달성",       "battle_streak", 10),
    "battle_sweep":    ("완벽한 승리",   "victini",    "무피해 완승",       "battle_sweep", 1),
    "partner_set":     ("나의 파트너",   "pikachu",    "파트너 포켓몬 지정", "partner_set", 1),
}

# Merge battle titles into main UNLOCKABLE_TITLES so they appear in 칭호목록 and can be equipped
UNLOCKABLE_TITLES.update(BATTLE_TITLES)

# --- Tournament ---
TOURNAMENT_REG_HOUR = 21        # 등록 시작 시각 (21시 KST)
TOURNAMENT_START_HOUR = 22      # 대회 시작 시각 (22시 KST)
TOURNAMENT_MIN_PLAYERS = 4      # 최소 참가자
TOURNAMENT_PRIZE_1ST_MB = 5     # 우승 마스터볼
TOURNAMENT_PRIZE_1ST_SHINY = "ultra_legendary"  # 우승 이로치 레어리티
TOURNAMENT_PRIZE_2ND_MB = 3     # 준우승 마스터볼
TOURNAMENT_PRIZE_2ND_SHINY = "legendary"        # 준우승 이로치 레어리티
TOURNAMENT_PRIZE_SEMI_MB = 2    # 4강 마스터볼
TOURNAMENT_PRIZE_SEMI_SHINY = "epic"      # 4강 이로치 레어리티
TOURNAMENT_PRIZE_QUARTER_MB = 2     # 8강 탈락 마스터볼
TOURNAMENT_PRIZE_R16_MB = 1         # 16강 탈락 마스터볼
TOURNAMENT_PRIZE_PARTICIPANT_MB = 1  # 그 외 참가자 마스터볼

# --- Tournament Titles ---
TOURNAMENT_TITLES = {
    "tournament_first": ("쉬었음청년",     "champion_first",    "임시대회 우승자",  "tournament_first", 1),
    "inaugural_champ":  ("초대 챔피언",    "champion_first",    "최초 공식 토너먼트 우승자", "inaugural_champ", 1),
    "tournament_champ": ("토너먼트 챔피언", "champion",      "토너먼트 우승 1회",       "tournament_win", 1),
}
UNLOCKABLE_TITLES.update(TOURNAMENT_TITLES)

# --- Title Buffs (착용 시 효과) ---
# title_id -> {"daily_masterball": int, "extra_feed": int}
TITLE_BUFFS = {
    "inaugural_champ": {"daily_masterball": 1, "extra_feed": 1},
    "tournament_champ": {"extra_feed": 1},
}

def get_title_buff_by_name(title_name: str) -> dict | None:
    """착용 중인 칭호 이름으로 버프 dict 반환. 없으면 None."""
    for title_id, buff in TITLE_BUFFS.items():
        if UNLOCKABLE_TITLES[title_id][0] == title_name:
            return buff
    return None

# 버프가 있는 칭호 이름 목록 (DB 쿼리용)
BUFF_TITLE_NAMES = [UNLOCKABLE_TITLES[tid][0] for tid in TITLE_BUFFS]

# ─── 랭크전 (시즌 배틀) ─────────────────────────────────

# --- Ranked Tiers ---
RANKED_TIERS = [
    # (tier_key, name, icon, min_rp)
    ("bronze",   "브론즈",     "🥉", 0),
    ("silver",   "실버",       "🥈", 300),
    ("gold",     "골드",       "🏅", 600),
    ("platinum", "플래티넘",   "💎", 1000),
    ("diamond",  "다이아",     "💠", 1500),
    ("master",   "마스터",     "👑", 2000),
    # 챌린저: RP 기반이 아니라 마스터 Top 10 중 자동 부여
    ("challenger", "챌린저",   "⚔️", 99999),
]
# 챌린저 티어는 RP 임계값이 아닌 마스터 Top 10에게 동적 부여
CHALLENGER_TOP_N = 10

SEASON_DURATION_WEEKS = 2  # 시즌 기간 (주)

def get_tier(rp: int) -> tuple:
    """RP로 현재 티어 (key, name, icon) 반환. 챌린저는 별도 로직."""
    result = RANKED_TIERS[0]
    for t in RANKED_TIERS:
        if t[0] == "challenger":
            break  # 챌린저는 RP 기반이 아님
        if rp >= t[3]:
            result = t
        else:
            break
    return result[0], result[1], result[2]

def get_tier_index(tier_key: str) -> int:
    """티어 키로 인덱스 반환 (bronze=0 ... challenger=6)."""
    for i, t in enumerate(RANKED_TIERS):
        if t[0] == tier_key:
            return i
    return 0

# --- RP (Rank Points) ---
RP_WIN_BASE = 30                # 승리 기본 RP
RP_LOSE_BASE = 20               # 패배 기본 차감
RP_LOSE_PROTECTED = 15          # 브론즈/실버 보호 차감
RP_TIER_DIFF_MAX = 10           # 티어차 보정 최대 ±10
RP_TIER_DIFF_PER = 5            # 티어 1단계당 보정
RP_STREAK_PER = 2               # 연승 1회당 RP
RP_STREAK_MAX = 10              # 연승 보너스 최대
RP_SOFT_RESET_MULT = 0.4        # 시즌 소프트 리셋 배율 (2주 시즌)

# --- Ranked Cost System (팀 편성 코스트) ---
RANKED_COST = {
    "common": 1,
    "rare": 2,
    "epic": 4,
    "legendary": 5,
    "ultra_legendary": 6,
}
RANKED_COST_LIMIT = 18          # 6마리 팀 총 코스트 상한
RANKED_TEAM_SIZE = 6            # 팀 필수 인원
RANKED_ULTRA_MAX = 1            # 초전설 최대 편성 수

# --- Ranked Cooldowns ---
RANKED_COOLDOWN_SAME = 1800     # 같은 상대 30분
RANKED_COOLDOWN_GLOBAL = 120    # 전체 랭크전 2분
RANKED_DAILY_CAP = 20           # 일일 랭크전 상한
RANKED_ARENA_CXP_BONUS = 5     # 아레나 채팅방 CXP 보너스

# --- Win-trading / Abuse Prevention ---
RANKED_SAME_PAIR_DAILY_MAX = 5  # 같은 상대 일일 최대 대전 횟수
RANKED_SAME_PAIR_RP_DECAY = [1.0, 1.0, 0.5, 0.25, 0.0]  # 1~5회차 RP 배율
RANKED_TIER_GAP_PENALTY = 3     # 티어 3단계 이상 차이 시 상위자 RP 감소
RANKED_TIER_GAP_RP_MIN = 5      # 티어 갭 패널티 시 최소 RP 획득
RANKED_NEWBIE_PROTECTION = 10   # 첫 N전 RP 손실 50% 감소

# --- Weekly Rules (시즌 법칙, 시즌 내내 고정) ---
# 2주 시즌마다 1개 법칙 적용. 타입 벤 + 에픽 제한 포함.
WEEKLY_RULES = {
    # --- 자유 ---
    "open": {
        "name": "제한 없음",
        "icon": "🏆",
        "desc": "풀 오픈 (최강전)",
        "error": "",
    },
    # --- 등급 제한 ---
    "no_ultra": {
        "name": "초전설 금지",
        "icon": "🚫",
        "desc": "초전설 포켓몬 사용 불가",
        "error": "이번 시즌은 초전설 포켓몬을 사용할 수 없습니다!",
    },
    "no_legendary": {
        "name": "전설 금지",
        "icon": "🚫",
        "desc": "전설+초전설 포켓몬 사용 불가",
        "error": "이번 시즌은 전설/초전설 포켓몬을 사용할 수 없습니다!",
    },
    "epic_below": {
        "name": "에픽 이하 전용",
        "icon": "🎯",
        "desc": "에픽 등급까지만 사용 가능",
        "error": "이번 시즌은 에픽 이하 포켓몬만 사용 가능합니다!",
    },
    "no_final_evo": {
        "name": "최종진화 금지",
        "icon": "👶",
        "desc": "최종진화 포켓몬 사용 불가",
        "error": "이번 시즌은 최종진화 포켓몬을 사용할 수 없습니다!",
    },
    # --- 타입 금지 (메타 변동) ---
    "no_normal": {
        "name": "노말타입 금지",
        "icon": "🚫",
        "desc": "노말 타입 포켓몬 사용 불가 (잠만보, 럭키, 해피너스, 캥카 등)",
        "error": "이번 시즌은 노말 타입 포켓몬을 사용할 수 없습니다!",
    },
    "no_dragon": {
        "name": "드래곤타입 금지",
        "icon": "🐉",
        "desc": "드래곤 타입 포켓몬 사용 불가 (망나뇽, 보만다, 한카리아스 등)",
        "error": "이번 시즌은 드래곤 타입 포켓몬을 사용할 수 없습니다!",
    },
    "no_psychic": {
        "name": "에스퍼타입 금지",
        "icon": "🔮",
        "desc": "에스퍼 타입 포켓몬 사용 불가 (뮤츠, 뮤, 메타그로스 등)",
        "error": "이번 시즌은 에스퍼 타입 포켓몬을 사용할 수 없습니다!",
    },
    # --- 에픽 제한 (코스트 밸런스) ---
    "epic_max_2": {
        "name": "에픽 2마리 제한",
        "icon": "🔸",
        "desc": "에픽 등급 최대 2마리까지만 편성",
        "error": "이번 시즌은 에픽 등급 포켓몬을 2마리까지만 편성할 수 있습니다!",
    },
    "epic_water_ice": {
        "name": "에픽 물/얼음만",
        "icon": "🧊",
        "desc": "에픽은 물/얼음 타입만 사용 가능 (마기라스, 망나뇽 등 불가)",
        "error": "이번 시즌은 에픽 등급 포켓몬 중 물/얼음 타입만 사용 가능합니다!",
    },
    "epic_fire_fight": {
        "name": "에픽 불꽃/격투만",
        "icon": "👊",
        "desc": "에픽은 불꽃/격투 타입만 사용 가능 (윈디, 괴력몬 등)",
        "error": "이번 시즌은 에픽 등급 포켓몬 중 불꽃/격투 타입만 사용 가능합니다!",
    },
}

# --- Ranked Rewards (주간 보상) ---
RANKED_REWARDS = {
    "challenger": {"masterball": 5, "bp": 800},
    "master":     {"masterball": 3, "bp": 500},
    "diamond":    {"masterball": 2, "bp": 300},
    "platinum":   {"masterball": 1, "bp": 200},
    "gold":       {"masterball": 0, "bp": 300},
    "silver":     {"masterball": 0, "bp": 150},
    "bronze":     {"masterball": 0, "bp": 50},
}

# --- Ranked Titles ---
RANKED_TITLES = {
    "ranked_first":    ("첫 랭크전",     "squirtle",   "랭크전 1회 참여",    "ranked_total", 1),
    "ranked_silver":   ("실버 도달",     "wartortle",  "실버 티어 달성",     "ranked_tier", "silver"),
    "ranked_gold":     ("골드 도달",     "charmander", "골드 티어 달성",     "ranked_tier", "gold"),
    "ranked_platinum": ("플래티넘 도달", "charmeleon", "플래티넘 티어 달성", "ranked_tier", "platinum"),
    "ranked_diamond":  ("다이아 도달",   "charizard",  "다이아 티어 달성",   "ranked_tier", "diamond"),
    "ranked_master":   ("랭크 마스터",   "crown",      "마스터 티어 달성",   "ranked_tier", "master"),
    "ranked_challenger": ("챌린저",      "crown",      "챌린저 티어 달성",   "ranked_tier", "challenger"),
    "ranked_champion": ("시즌 챔피언",   "champion",   "시즌 1위 달성",      "ranked_rank", 1),
    "ranked_streak5":  ("랭크 5연승",    "moltres",    "랭크전 5연승",       "ranked_streak", 5),
    "ranked_streak10": ("랭크 10연승",   "moltres",    "랭크전 10연승",      "ranked_streak", 10),
}
UNLOCKABLE_TITLES.update(RANKED_TITLES)

# --- Shiny (이로치) Titles ---
SHINY_TITLES = {
    "shiny_hunter":  ("이로치 헌터",   "crystal",    "이로치 포켓몬 3마리 포획",  "shiny_catch", 3),
    "shiny_master":  ("이로치 마스터",  "crystal",    "이로치 포켓몬 10마리 포획", "shiny_catch", 10),
    "shiny_legend":  ("전설의 빛",     "crystal",    "이로치 전설 포켓몬 포획",   "shiny_legendary", 1),
}
SHINY_MAX_FRIENDSHIP = 7              # 이로치 최대 친밀도

def get_max_friendship(pokemon: dict) -> int:
    """이로치면 7, 일반이면 5."""
    return SHINY_MAX_FRIENDSHIP if pokemon.get("is_shiny") else MAX_FRIENDSHIP
UNLOCKABLE_TITLES.update(SHINY_TITLES)

# ============================================================
# Yacha (야차 - Betting Battle)
# ============================================================

YACHA_BP_OPTIONS = [100, 200, 500]         # BP 베팅 프리셋
YACHA_MASTERBALL_OPTIONS = [1, 2, 3]       # 마스터볼 베팅 프리셋
YACHA_COOLDOWN = 600                       # 글로벌 쿨다운 (10분)
YACHA_CHALLENGE_TIMEOUT = 60               # 수락 대기 시간 (1분)

# 야차 티배깅 멘트 (20개, 랜덤)
YACHA_TEABAG_MESSAGES = [
    # --- 상황극/대화 ---
    '💀 {loser}의 포켓몬: "사장님 저 오늘 칼퇴하겠습니다"',
    '💀 {loser}의 포켓몬이 이력서를 업데이트하기 시작했습니다',
    '💀 {winner}: "gg" {loser}: (읽씹)',
    '💀 {winner}: "다음엔 진심으로 해줄래?" {loser}: "이게 진심인데"',
    '💀 {loser}의 포켓몬: "아니 트레이너가 밥을 안 줘서요" (패배 사유서)',
    '💀 {winner}의 포켓몬이 하품을 합니다',
    '💀 {loser}의 포켓몬끼리 카톡방 만듦 (방 제목: 탈출 계획)',
    '💀 {loser}의 포켓몬이 포켓몬센터에서 퇴원을 거부합니다',
    '💀 {loser}의 포켓몬: "저희도 트레이너 뽑기 다시 하고 싶어요"',
    '💀 {winner}: "녹화했는데 올려도 돼?"',
    '💀 {loser}의 포켓몬이 노동청에 전화하는 중',
    '💀 {loser}의 포켓몬이 단체로 연차를 냈습니다',
    '💀 {winner}: "팀 그대로 온 거야..?"',
    # --- 밈/유머 ---
    '💀 속보) {loser}, 오늘도 BP 기부 행사 진행',
    '💀 [알림] {loser}님의 배틀 승률이 사망했습니다 (향년 0.1세)',
    '💀 방금 배틀이 {loser}의 흑역사 컬렉션에 추가됐습니다',
    '💀 오늘의 운세 — {loser}: 배틀을 피하세요',
    '💀 {loser}의 배틀 로그가 실화 검색어 1위에 올랐습니다',
    '💀 {loser} 배틀 영상이 \'이러면 안 됩니다\' 교육자료로 채택됐습니다',
    '💀 [속보] {loser}의 포켓몬 3마리, 집단 명상 돌입',
    '💀 {loser}의 포켓몬이 \'오늘의 배틀\'을 블랙리스트에 추가했습니다',
    '💀 ChatGPT: "??? 난 그런 덱을 하라고 한 적이 없어" — {loser} 팀을 보고',
    '💀 문유가 지급해주는 포켓볼도 아깝다 ㅉㅉ — {winner}',
    # --- 크립토 ---
    '💀 {loser} 청산됨',
    '💀 {loser}의 BP가 루나됨',
    '💀 {loser}에게 마진콜이 왔습니다',
    # --- 허무/감성 ---
    '💀 {loser}: "재밌었다" (재밌지 않았다)',
    '💀 {loser}의 포켓몬이 조용히 몬스터볼 안에서 문을 잠급니다',
    '💀 {loser}: (배틀 끝나고 10분째 멍때리는 중)',
    '💀 오늘 {loser}의 일기: "다신 배틀 안 한다" (내일도 함)',
    '💀 {loser}의 포켓몬: "...우리 산책이나 갈까요?"',
    '💀 {loser}: 조용히 팀 편집 화면을 엽니다',
    '💀 {loser}의 포켓몬이 창밖을 바라보며 한숨을 쉽니다',
    '💀 {loser}: "이번엔 운이 없었어" (매번 운이 없음)',
    '💀 {loser}의 포켓몬이 트레이너에게 우유를 건넵니다 🥛 (위로)',
    # --- 과장/드립 ---
    '💀 {winner}이(가) 밤티를 시전했다 ☕',
    '💀 방금 배틀 한 편으로 {loser} 승률 복구 불가 판정',
    '💀 {loser}의 포켓몬: 트레이너 변경 요청서 제출 완료',
    '💀 지금 {loser}의 포켓몬이 면접 보러 간 트레이너: {winner}',
    '💀 {loser}의 배틀 전적이 \'비공개\'로 전환을 요청합니다',
    '💀 긴급속보) {loser}의 포켓몬 3마리 동시 은퇴 선언',
    '💀 {loser}의 포켓몬이 자기들끼리 팀을 재편성하기 시작했습니다',
    '💀 {winner}의 포켓몬: "오늘 간식 맛있겠다 🍖" (BP로 구매 예정)',
    '💀 {loser}의 포켓몬이 \'트레이너 평가\' 앱에 별 1개를 남겼습니다 ⭐',
    '💀 {loser}: "다음엔 이긴다" (시즌 3 연속 동일 발언)',
    '💀 {loser}의 포켓몬이 자발적으로 야생으로 돌아가려 합니다',
    '💀 포켓몬센터 간호사: "{loser}님 이번 달 벌써 47번째예요"',
]


# --- Custom Emoji IDs (Rarity Badges) ---
RARITY_CUSTOM_EMOJI = {
    "ultra_legendary": "6143244830462975904",  # 빨간색 (초전설)
    "legendary": "6141080849845591919",
    "epic": "6141022159117492116",
    "rare": "6140797725601438152",
    "common": "6140791433474351151",
    "red": "6143244830462975904",
    "blue": "6145689478603217072",
    "bracket_red": "6143460931742475685",
    "bracket_blue": "6143145066962624038",
}

# --- Custom Emoji IDs (Type Badges) ---
# Custom Telegram emoji sticker IDs for type badges.
# Falls back to TYPE_EMOJI (unicode emoji) if empty.
TYPE_CUSTOM_EMOJI = {
    "normal": "6143356168900189669",
    "fire": "6143060735279766934",
    "water": "6143459776396271425",
    "grass": "6143236339312632261",
    "electric": "6142971438614715696",
    "ice": "6141156140622290617",
    "fighting": "6141010996497488948",
    "poison": "6143189953665833634",
    "ground": "6143048400133692919",
    "flying": "6142986866137244114",
    "psychic": "6143119490432375666",
    "bug": "6141032312420180456",
    "rock": "6143423024361118748",
    "ghost": "6143417462378471423",
    "dragon": "6143316101150283963",
    "dark": "6143029137205370024",
    "steel": "6142980178873162454",
    "fairy": "6143002478343364009",
}

# --- Custom Emoji IDs (Ball) ---
BALL_CUSTOM_EMOJI = {
    "pokeball": "6143151702687095487",
    "hyperball": "6142944354550946803",
    "masterball": "6143130859210807699",
    "greatball": "6143092307584359042",
}

# --- Custom Emoji IDs (Icons) ---
ICON_CUSTOM_EMOJI = {
    # Special
    "skull": "6143450305993382989",
    "crystal": "6143120589944004477",
    # Champion animated effects
    "champion_first": "6143110286317461809",
    "champion": "6143325296675266325",
    # Numbers + Check
    "1": "6143285920415097548",
    "2": "6143042181021048615",
    "3": "6143166034992963719",
    "4": "6143030576019414291",
    "5": "6142993896998706810",
    "6": "6143287445128486521",
    "7": "6143241351539465226",
    "8": "6142976008459919189",
    "9": "6143232271978601697",
    "10": "6143456946012824214",
    "check": "6143254176311811828",
    # UI Icons
    "bookmark": "6143229132357509310",
    "container": "6143067620112342405",
    "pokedex": "6143439418251287575",
    "battle": "6143344370625026850",
    "ham": "6142983498882882214",
    "game": "6143111020756868297",
    "favorite": "6143055418110258728",
    "pokemon-love": "6143084091311922140",
    "gotcha": "6143385318843227267",
    "windy": "6143007563584641911",
    "exchange": "6143035201699193195",
    "computer": "6143068826998151784",
    "coin": "6143083713354801765",
    "footsteps": "6143075514262233319",
    "pokecenter": "6142954550803307680",
    "shopping-bag": "6143287260444892433",
    "bolt": "6143251942928818741",
    "skill": "6143088085631507366",
    "stationery": "6143168289850792706",
    # Pokemon characters (titles)
    "caterpie": "6143387998902819747",
    "rattata": "6143003788308389605",
    "pikachu": "6143424549074508692",
    "charmander": "6142987961353903580",
    "crown": "6143265588039916937",
    "mew": "6143355370036274725",
    "chikorita": "6143450619525996657",
    "bellsprout": "6143374276482308192",
    "eevee": "6143466343401268847",
    "victini": "6143322638090510138",
    "dratini": "6143371373084417997",
    "bulbasaur": "6142953352507432594",
    "mankey": "6143320679585422922",
    "zubat": "6143065038836997684",
    "venonat": "6143267851487681129",
    "meowth": "6143055950686199889",
    "jigglypuff": "6143158604699540827",
    "abra": "6143248605739227640",
    "articuno": "6143098067135503734",
    "snorlax": "6143350078636563496",
    "squirtle": "6143034596108803222",
    "moltres": "6142975986985081276",
    "psyduck": "6143060400272317013",
}
