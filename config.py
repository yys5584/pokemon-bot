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
    (10, 29, 2),
    (30, 49, 3),
    (50, 99, 4),
    (100, 499, 5),
    # 500+: use formula 2 + floor((members - 10) / 500)
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

# --- Title System ---
TITLES = [
    # (min_pokemon_count, title_text, emoji)
    (251, "그랜드마스터", "💫"),
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
    "beginner":     ("초보 트레이너",   "🔰", "1세대 도감 15종 달성",     "pokedex_gen1", 15),
    "collector":    ("포켓몬 수집가",   "📦", "1세대 도감 45종 달성",     "pokedex_gen1", 45),
    "trainer":      ("포켓몬 트레이너", "⭐", "1세대 도감 75종 달성",     "pokedex_gen1", 75),
    "master":       ("포켓몬 마스터",   "🏆", "1세대 도감 120종 달성",    "pokedex_gen1", 120),
    "champion":     ("챔피언",         "👑", "1세대 도감 151종 완성!",   "pokedex_gen1", 151),
    "living_dex":   ("살아있는 도감",   "📖", "1세대 도감 100종 달성",    "pokedex_gen1", 100),
    # 2세대 도감 기반 (성도)
    "gen2_starter":   ("성도의 초보",    "🌏", "2세대 도감 15종 달성",   "pokedex_gen2", 15),
    "gen2_collector": ("성도 수집가",    "🎒", "2세대 도감 45종 달성",   "pokedex_gen2", 45),
    "gen2_trainer":   ("성도 트레이너",  "🌟", "2세대 도감 75종 달성",   "pokedex_gen2", 75),
    "gen2_master":    ("성도 마스터",    "🏅", "2세대 도감 100종 완성!", "pokedex_gen2", 100),
    # 전체 도감
    "grand_master":   ("그랜드마스터",   "💫", "전체 도감 251종 완성!",  "pokedex_all", 251),
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
    # 배틀 칭호
    "battle_first":    ("첫 배틀",       "⚔️", "배틀 1회 참여",     "battle_total", 1),
    "battle_fighter":  ("배틀 파이터",   "🥊", "배틀 5승 달성",     "battle_wins", 5),
    "battle_champion": ("배틀 챔피언",   "🏆", "배틀 20승 달성",    "battle_wins", 20),
    "battle_legend":   ("배틀 레전드",   "👑", "배틀 50승 달성",    "battle_wins", 50),
    "battle_streak3":  ("연승 전사",     "🔥", "3연승 달성",        "battle_streak", 3),
    "battle_streak10": ("무적의 전사",   "💫", "10연승 달성",       "battle_streak", 10),
    "battle_sweep":    ("완벽한 승리",   "✨", "무피해 완승",       "battle_sweep", 1),
    "partner_set":     ("나의 파트너",   "🤝", "파트너 포켓몬 지정", "partner_set", 1),
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
}

# --- Eevee Evolution ---
EEVEE_ID = 133
EEVEE_EVOLUTIONS = [134, 135, 136, 196, 197]  # 샤미드, 쥬피썬더, 부스터, 에브이, 블래키

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
    (168, "S", ""),   # ~90%+ (top ~3%)
    (140, "A", ""),   # ~75%+
    (93,  "B", ""),   # ~50%+
    (47,  "C", ""),   # ~25%+
    (0,   "D", ""),   # bottom
]

def get_iv_grade(total: int) -> tuple[str, str]:
    """Return (grade_letter, display) for an IV total (0~186)."""
    for threshold, grade, display in IV_GRADE_THRESHOLDS:
        if total >= threshold:
            return grade, display
    return "D", ""

# --- Battle Stats ---
RARITY_BASE_STAT = {
    "common": 45, "rare": 60, "epic": 75, "legendary": 95,
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

# 타입 면역: key 타입 공격이 value 리스트 타입에 무효 (0x → 0.3x로 완화)
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

# --- Battle Rules ---
BATTLE_CHALLENGE_TIMEOUT = 30       # 도전 대기 시간 (초)
BATTLE_COOLDOWN_SAME = 300          # 같은 상대 쿨다운 (5분)
BATTLE_COOLDOWN_GLOBAL = 60         # 전체 배틀 쿨다운 (1분)
BATTLE_MAX_ROUNDS = 50              # 최대 라운드
BATTLE_TEAM_MIN = 1                 # 최소 팀원
BATTLE_TEAM_MAX = 6                 # 최대 팀원
BATTLE_CRIT_RATE = 0.10             # 크리티컬 확률 10%
BATTLE_CRIT_MULT = 1.5              # 크리티컬 배수
BATTLE_TYPE_ADVANTAGE_MULT = 1.3    # 타입 유리
BATTLE_TYPE_DISADVANTAGE_MULT = 0.7 # 타입 불리
BATTLE_PARTNER_ATK_BONUS = 0.05     # 파트너 ATK 보너스 5%
BATTLE_SKILL_RATE = 0.30             # 고유기술 발동 확률 30%

# --- BP (Battle Points) ---
BP_WIN_BASE = 20                    # 승리 기본 BP
BP_WIN_PER_ENEMY = 2               # 상대 팀 사이즈당 추가 BP
BP_LOSE = 5                         # 패배 참여 보상
BP_PERFECT_WIN = 50                 # 무피해 완승 보너스
BP_STREAK_BONUS = 10                # 3연승마다 추가
BP_MASTERBALL_COST = 200            # 마스터볼 1개 가격
BP_MASTERBALL_DAILY_LIMIT = 3       # 마스터볼 일일 구매 제한
BP_FORCE_SPAWN_TICKET_COST = 500      # 강제스폰권 가격 (이벤트: 무료, 원래 500)
BP_POKEBALL_RESET_COST = 200          # 포켓볼 초기화(100개) 가격 (이벤트: 무료, 원래 200)
BP_HYPER_BALL_COST = 20              # 하이퍼볼 1회 사용 BP
HYPER_BALL_CATCH_MULTIPLIER = 3.0    # 하이퍼볼 포획률 배수

# --- Arcade Pass ---
ARCADE_PASS_COST = 200               # 아케이드 이용권 가격 (BP)
ARCADE_PASS_DURATION = 3600          # 이용권 지속시간 (초) = 1시간
ARCADE_PASS_DAILY_LIMIT = 3          # 일일 구매 제한

# --- Shiny System ---
SHINY_RATE_NATURAL = 1 / 64          # 자연 스폰 샤이니 확률 (~1.56%)
SHINY_RATE_ARCADE = 1 / 512          # 아케이드 샤이니 확률 (~0.20%)

# --- Battle Titles ---
# title_id: (name, emoji, description, check_type, threshold)
BATTLE_TITLES = {
    "battle_first":    ("첫 배틀",       "⚔️", "배틀 1회 참여",     "battle_total", 1),
    "battle_fighter":  ("배틀 파이터",   "🥊", "배틀 5승 달성",     "battle_wins", 5),
    "battle_champion": ("배틀 챔피언",   "🏆", "배틀 20승 달성",    "battle_wins", 20),
    "battle_legend":   ("배틀 레전드",   "👑", "배틀 50승 달성",    "battle_wins", 50),
    "battle_streak3":  ("연승 전사",     "🔥", "3연승 달성",        "battle_streak", 3),
    "battle_streak10": ("무적의 전사",   "💫", "10연승 달성",       "battle_streak", 10),
    "battle_sweep":    ("완벽한 승리",   "✨", "무피해 완승",       "battle_sweep", 1),
    "partner_set":     ("나의 파트너",   "🤝", "파트너 포켓몬 지정", "partner_set", 1),
}

# Merge battle titles into main UNLOCKABLE_TITLES so they appear in 칭호목록 and can be equipped
UNLOCKABLE_TITLES.update(BATTLE_TITLES)

SPAWN_MAX_DAILY = 20  # 하루 최대 스폰 수

# --- Tournament ---
TOURNAMENT_REG_HOUR = 21        # 등록 시작 시각 (21시 KST)
TOURNAMENT_START_HOUR = 22      # 대회 시작 시각 (22시 KST)
TOURNAMENT_MIN_PLAYERS = 4      # 최소 참가자
TOURNAMENT_PRIZE_1ST_MB = 2     # 우승 마스터볼
TOURNAMENT_PRIZE_1ST_BP = 200   # 우승 BP
TOURNAMENT_PRIZE_2ND_BP = 100   # 준우승 BP
TOURNAMENT_PRIZE_4TH_BP = 50    # 4강 BP

# --- Tournament Titles ---
TOURNAMENT_TITLES = {
    "tournament_first": ("쉬었음청년",     "🏛️", "임시대회 우승자",  "tournament_first", 1),
    "tournament_champ": ("토너먼트 챔피언", "🏆", "토너먼트 우승 1회",       "tournament_win", 1),
}
UNLOCKABLE_TITLES.update(TOURNAMENT_TITLES)

# --- Shiny (이로치) Titles ---
SHINY_TITLES = {
    "shiny_hunter":  ("이로치 헌터",   "✨", "이로치 포켓몬 3마리 포획",  "shiny_catch", 3),
    "shiny_master":  ("이로치 마스터",  "🌟", "이로치 포켓몬 10마리 포획", "shiny_catch", 10),
    "shiny_legend":  ("전설의 빛",     "💫", "이로치 전설 포켓몬 포획",   "shiny_legendary", 1),
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
    # --- 크립토 테마 ---
    '💀 {loser} 청산됨',
    '💀 {winner}: "{loser}아 시드 얼마 남았어" {loser}: "..."',
    '💀 아직도 야차해? 비탈릭도 팔고 있는데',
    '💀 비트 1억 간다! 아.. {loser} BP는 0원 간다',
    '💀 {loser}의 BP가 루나됨',
    '💀 {winner}: "고점에 물렸네 ㅋ"',
    '💀 {loser}아 존버해봤자 상폐인데',
    '💀 숏 쳤는데 떡상한 기분이 이런건가 — {loser}',
    '💀 {winner}: "김프 먹듯이 잘 먹었습니다"',
    '💀 {loser} 물타기 하고 싶은데 물이 없음',
    '💀 {loser}의 BP 차트 데드크로스 뜸',
    '💀 {winner}: "이거 투자야 기부야?"',
    '💀 {loser}아 손절은 빠를수록 좋은건데',
    '💀 {loser}에게 마진콜이 왔습니다',
    '💀 코인은 반등이라도 있지.. 야차는 없어',
    '💀 {loser} 매수 타이밍 실화냐 고점 롱이잖아',
    '💀 {winner}: "다이아몬드 핸즈래놓고 종이였네"',
    '💀 {loser}아 업비트 말고 야차부터 접어',
    '💀 {loser}의 포폴: BTC -90% ETH -95% 야차 -100%',
    '💀 {winner}: "또 와 ㅎ 오늘 수익률 좋다"',
    # --- 일반/트렌드 ---
    '💀 {loser} 공양 감사합니다',
    '💀 {winner}: "팀 그대로 온거야..?"',
    '💀 {loser}아 그거 배틀이야 기부야',
    '💀 {winner}이(가) 밤티를 시전했다 ☕',
    '💀 {loser}의 포켓몬이 트레이너를 원망하는 눈빛',
    '💀 {winner}: "아 미안 나 팀도 안 바꿨는데"',
    '💀 {loser}아 리플레이 볼 필요 없어 봐도 답 없음',
    '💀 {winner}: "녹화했는데 올려도 돼?"',
    '💀 {loser} 택배 왔다 📦 (내용물: L)',
    '💀 {loser}아 배틀 말고 수집이 맞는 것 같아',
    '💀 {winner}: "스킬 한번도 안 떴어? 그건 좀.."',
    '💀 {loser}아 포켓몬한테 미안하지도 않냐',
    '💀 {loser}의 포켓몬이 트레이너를 바꾸고 싶어함',
    '💀 {winner}: "다음엔 팀 좀 바꿔와"',
    "💀 방금 그 배틀 교본에 실린다 '이러면 안 됩니다' 편",
    '💀 {loser}아 이겨본 적은 있지? 설마',
    '💀 {winner}: "gg" {loser}: (읽씹)',
    '💀 세상에 공짜는 없는데 {loser} BP는 공짜였음',
    '💀 {loser}아 그 팀으로 야차를 왜 걸어 용감하긴 하다',
    '💀 {winner}: "저녁은 {loser} BP로 먹는다 🍗"',
    '💀 {winner}: "ChatGPT한테 배틀 상담 좀 받고올래?"',
]


# --- Custom Emoji IDs (Rarity Badges) ---
RARITY_CUSTOM_EMOJI = {
    "legendary": "6141080849845591919",
    "epic": "6141022159117492116",
    "rare": "6140797725601438152",
    "common": "6140791433474351151",
}

# --- Custom Emoji IDs (Type Badges) ---
# Placeholder: add custom Telegram emoji IDs here when created.
# When empty, falls back to TYPE_EMOJI (unicode emoji).
TYPE_CUSTOM_EMOJI = {}
