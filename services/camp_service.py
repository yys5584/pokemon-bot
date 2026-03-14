"""Camp system v2 business logic.

책임 분리:
- camp_service.py: 비즈니스 로직 (점수 계산, 라운드 정산, 이로치 전환 등)
- camp_queries.py: DB 읽기/쓰기
- handlers/camp.py: 텔레그램 메시지/콜백 (그룹)
- handlers/dm_camp.py: 텔레그램 DM 핸들러
"""

import random
import logging
from datetime import datetime

import config
from database import camp_queries as cq
from database import queries
from models.pokemon_base_stats import POKEMON_BASE_STATS
from models.pokemon_data import ALL_POKEMON
from utils.helpers import shiny_emoji, icon_emoji

import math

logger = logging.getLogger(__name__)

# ── 캠프 날씨 (라운드별) ──
_camp_weather: dict[int, tuple] = {}  # chat_id → (name, emoji, boosted_fields)


def roll_weather() -> tuple[str, str, list[str]]:
    """실제 날씨 기반으로 캠프 날씨 결정. fallback: 랜덤."""
    try:
        from services.weather_service import get_current_weather
        w = get_current_weather()
        condition = w.get("condition")
        if condition:
            # 실제 날씨 → 캠프 날씨 매핑
            _REAL_TO_CAMP = {
                "rain":        ("비",   "🌧️", ["lake", "forest"]),
                "snow":        ("눈",   "❄️", ["lake", "temple"]),
                "thunder":     ("폭풍", "⛈️", ["city", "cave"]),
                "fog":         ("안개", "🌫️", ["temple", "cave"]),
                "clear_hot":   ("화창", "🔥", ["volcano", "forest"]),
                "clear_night": ("맑은 밤", "🌙", ["temple", "cave"]),
                "wind":        ("바람", "💨", ["lake", "volcano"]),
                "clear":       ("맑음", "☀️", ["forest", "city"]),
            }
            camp_weather = _REAL_TO_CAMP.get(condition)
            if camp_weather:
                return camp_weather
    except Exception:
        pass
    return random.choice(config.CAMP_WEATHER_TABLE)


def get_camp_weather(chat_id: int) -> tuple[str, str, list[str]]:
    """현재 캠프 날씨 반환. 없으면 새로 굴림."""
    if chat_id not in _camp_weather:
        _camp_weather[chat_id] = roll_weather()
    return _camp_weather[chat_id]


def set_camp_weather(chat_id: int, weather: tuple[str, str, list[str]]):
    """캠프 날씨 설정 (라운드 시작 시 호출)."""
    _camp_weather[chat_id] = weather


def _weather_line(weather: tuple[str, str, list[str]]) -> str:
    """날씨 표시 한 줄 생성 (실제 온도 포함)."""
    temp_str = ""
    try:
        from services.weather_service import get_current_weather
        w = get_current_weather()
        if w.get("temp") is not None:
            temp_str = f" {w['temp']}°C"
    except Exception:
        pass
    return f"{weather[1]} 날씨: {weather[0]}{temp_str}"


# ── 포켓몬 이름 캐시 ──
_POKE_NAME: dict[int, str] = {}


def _pokemon_name(pid: int) -> str:
    """포켓몬 ID → 한글 이름."""
    if not _POKE_NAME:
        for p in ALL_POKEMON:
            _POKE_NAME[p[0]] = p[1]
    return _POKE_NAME.get(pid, f"#{pid}")


def _pokemon_rarity(pid: int) -> str:
    """포켓몬 ID → 등급."""
    for p in ALL_POKEMON:
        if p[0] == pid:
            return p[4]
    return "common"


# ═══════════════════════════════════════════════════════
# 타입 헬퍼
# ═══════════════════════════════════════════════════════

def get_pokemon_types(pokemon_id: int) -> list[str]:
    """포켓몬 타입 리스트 반환. 없으면 빈 리스트."""
    stats = POKEMON_BASE_STATS.get(pokemon_id)
    if stats:
        return stats[-1]
    return []


def pokemon_matches_field(pokemon_id: int, field_type: str) -> bool:
    """포켓몬 타입이 필드 타입 그룹에 맞는지 확인."""
    field_info = config.CAMP_FIELDS.get(field_type)
    if not field_info:
        return False
    ptypes = get_pokemon_types(pokemon_id)
    if not ptypes:
        return False
    return any(t in field_info["types"] for t in ptypes)


def get_matching_fields(pokemon_id: int) -> list[str]:
    """포켓몬이 배치 가능한 필드 키 리스트."""
    ptypes = get_pokemon_types(pokemon_id)
    fields = []
    for fkey, finfo in config.CAMP_FIELDS.items():
        if any(t in finfo["types"] for t in ptypes):
            fields.append(fkey)
    return fields


def _get_field_pokemon_pool(field_type: str) -> list[int]:
    """필드 타입에 맞는 전체 포켓몬 ID 리스트."""
    field_types = config.CAMP_FIELDS[field_type]["types"]
    pool = []
    for pid, stats in POKEMON_BASE_STATS.items():
        ptypes = stats[-1]
        if any(t in field_types for t in ptypes):
            pool.append(pid)
    return pool


# ═══════════════════════════════════════════════════════
# 캠프 레벨 헬퍼
# ═══════════════════════════════════════════════════════

def get_level_info(level: int) -> tuple:
    """레벨 정보 반환: (lv, fields, base_slots, cap, xp_needed, name)."""
    return config.get_camp_level_info(level)


def calc_total_slots(level: int, member_count: int) -> int:
    """필드당 총 슬롯 = 기본슬롯 + 멤버 보너스(500명당 +1)."""
    _, _, base_slots, *_ = get_level_info(level)
    bonus = member_count // config.CAMP_MEMBER_BONUS_PER
    return base_slots + bonus


def check_level_up(current_level: int, current_xp: int) -> int | None:
    """XP 기준 레벨업 가능하면 새 레벨 반환, 아니면 None."""
    if current_level >= config.CAMP_MAX_LEVEL:
        return None
    next_info = get_level_info(current_level + 1)
    xp_needed = next_info[4]
    if current_xp >= xp_needed:
        return current_level + 1
    return None


# ═══════════════════════════════════════════════════════
# 배치 횟수 계산
# ═══════════════════════════════════════════════════════

def get_daily_placement_limit(pokedex_count: int) -> int:
    """도감 수 기반 일일 배치 횟수."""
    limit = 2
    for min_dex, count in config.CAMP_DAILY_PLACEMENT_TABLE:
        if pokedex_count >= min_dex:
            limit = count
    return limit


# ═══════════════════════════════════════════════════════
# 점수 계산
# ═══════════════════════════════════════════════════════

def calc_placement_score(
    pokemon_id: int,
    is_shiny: bool,
    ivs: dict[str, int],
    bonus_pokemon_id: int | None,
    bonus_stat: str | None,
    bonus_value: int | None,
) -> tuple[int, str]:
    """배치 포켓몬 점수 계산.

    Returns:
        (score, description)
    """
    # 보너스 포켓몬이 아닌 경우: 타입만 맞으면 1점
    if bonus_pokemon_id is None or pokemon_id != bonus_pokemon_id:
        return config.CAMP_SCORE_TYPE_ONLY, "타입매칭 1점"

    # 보너스 포켓몬 매칭
    iv_met = False
    if bonus_stat and bonus_value is not None:
        iv_val = ivs.get(bonus_stat, 0)
        iv_met = iv_val >= bonus_value

    if is_shiny and iv_met:
        stat_name = config.CAMP_IV_STAT_NAMES.get(bonus_stat, "")
        return config.CAMP_SCORE_BONUS_FULL, f"보너스+이로치+{stat_name} 7점"
    elif iv_met:
        stat_name = config.CAMP_IV_STAT_NAMES.get(bonus_stat, "")
        return config.CAMP_SCORE_BONUS_IV, f"보너스+{stat_name} 4점"
    elif is_shiny:
        return config.CAMP_SCORE_BONUS_SHINY, "보너스+이로치 4점"
    else:
        return config.CAMP_SCORE_BONUS_POKEMON, "보너스포켓몬 2점"


# ═══════════════════════════════════════════════════════
# 라운드 보너스 생성
# ═══════════════════════════════════════════════════════

async def generate_round_bonus(chat_id: int, fields: list[dict], round_time: datetime):
    """각 필드마다 라운드 보너스 포켓몬 + 개체값 조건 생성 & 저장."""
    for field in fields:
        pool = _get_field_pokemon_pool(field["field_type"])
        if not pool:
            continue

        pokemon_id = random.choice(pool)
        stat = random.choice(config.CAMP_IV_STATS)
        low, high = config.CAMP_MISSION_IV_RANGE
        value = random.randint(low, high)

        await cq.set_round_bonus(
            chat_id, field["id"], pokemon_id, stat, value, round_time,
        )


# ═══════════════════════════════════════════════════════
# 라운드 정산 (핵심 로직)
# ═══════════════════════════════════════════════════════

async def settle_round(chat_id: int, round_time: datetime) -> dict:
    """라운드 정산: 각 필드 점수 합산 → 캡 적용 → 엔빵 분배.

    Returns:
        {
            "fields": [{
                "field_type": str,
                "total_score": int,
                "capped": int,
                "users": [user_id, ...],
                "per_user": int,
                "bonus": {pokemon_id, stat, value},
            }, ...],
            "total_xp": int,
            "level_up": int | None,
        }
    """
    camp = await cq.get_camp(chat_id)
    if not camp:
        return {"fields": [], "total_xp": 0, "level_up": None}

    level = camp["level"]
    level_info = get_level_info(level)
    cap = level_info[3]  # 필드당 캡

    fields = await cq.get_fields(chat_id)
    bonuses = await cq.get_round_bonus(chat_id, round_time)
    bonus_map = {b["field_id"]: b for b in bonuses}

    result_fields = []
    total_xp = 0

    for field in fields:
        placements = await cq.get_field_placements(field["id"])
        if not placements:
            result_fields.append({
                "field_type": field["field_type"],
                "field_id": field["id"],
                "total_score": 0,
                "capped": 0,
                "users": [],
                "per_user": 0,
                "bonus": None,
            })
            continue

        bonus = bonus_map.get(field["id"])

        # 각 배치 점수 재계산 (라운드 보너스 기준)
        now = config.get_kst_now()
        total_score = 0
        user_ids = []
        for p in placements:
            # 상시 배치 어뷰징 방지: 1시간 미만 유지 시 점수 미인정
            placed_at = p.get("placed_at")
            if placed_at and (now - placed_at).total_seconds() < config.CAMP_MIN_HOLD_SECONDS:
                continue

            ivs = {
                "iv_hp": p.get("iv_hp", 0),
                "iv_atk": p.get("iv_atk", 0),
                "iv_def": p.get("iv_def", 0),
                "iv_spa": p.get("iv_spa", 0),
                "iv_spdef": p.get("iv_spdef", 0),
                "iv_spd": p.get("iv_spd", 0),
            }
            score, _ = calc_placement_score(
                p["pokemon_id"],
                bool(p.get("is_shiny")),
                ivs,
                bonus["pokemon_id"] if bonus else None,
                bonus["stat_type"] if bonus else None,
                bonus["stat_value"] if bonus else None,
            )
            total_score += score
            user_ids.append(p["user_id"])

        # 캡 적용
        capped = min(total_score, cap)

        # 엔빵
        unique_users = list(set(user_ids))
        per_user = max(1, capped // len(unique_users)) if unique_users else 0

        # 날씨 부스트 적용
        weather = get_camp_weather(chat_id)
        weather_boosted = field["field_type"] in weather[2]
        if weather_boosted and per_user > 0:
            per_user = math.ceil(per_user * config.CAMP_WEATHER_MULTIPLIER)

        # 조각 분배 (필드 타입 귀속)
        frag_type = field["field_type"]
        for uid in unique_users:
            await cq.add_fragments(uid, frag_type, per_user)
            await cq.log_fragment(uid, chat_id, frag_type, per_user, "round")

        total_xp += capped

        result_fields.append({
            "field_type": field["field_type"],
            "field_id": field["id"],
            "total_score": total_score,
            "capped": capped,
            "users": unique_users,
            "per_user": per_user,
            "weather_boosted": weather_boosted,
            "bonus": {
                "pokemon_id": bonus["pokemon_id"],
                "stat_type": bonus["stat_type"],
                "stat_value": bonus["stat_value"],
            } if bonus else None,
        })

    # XP 누적 & 레벨업 체크
    if total_xp > 0:
        new_xp = await cq.update_camp_xp(chat_id, total_xp)
        new_level = check_level_up(level, new_xp)
        if new_level:
            await cq.update_camp_level(chat_id, new_level)
    else:
        new_level = None

    return {
        "fields": result_fields,
        "total_xp": total_xp,
        "level_up": new_level,
    }


# ═══════════════════════════════════════════════════════
# 소식 메시지 빌드
# ═══════════════════════════════════════════════════════

def build_round_announcement(round_result: dict, camp_level: int, chat_id: int = 0) -> str:
    """정산 결과로 소식 메시지 생성. (DM용 — 채팅방은 build_combined_announcement 사용)"""
    level_info = get_level_info(camp_level)
    level_name = level_info[5]

    lines = [f"🏕 캠프 소식 ({level_name})"]

    if chat_id:
        weather = get_camp_weather(chat_id)
        lines.append(_weather_line(weather))
        boosted_names = [config.CAMP_FIELDS[ft]["name"] for ft in weather[2] if ft in config.CAMP_FIELDS]
        if boosted_names:
            lines.append(f"  → {'/'.join(boosted_names)} 조각 ×{config.CAMP_WEATHER_MULTIPLIER}")

    lines.append("")

    for f in round_result["fields"]:
        field_info = config.CAMP_FIELDS.get(f["field_type"], {})
        emoji = field_info.get("emoji", "🏕")
        name = field_info.get("name", f["field_type"])

        if not f["users"]:
            lines.append(f"{emoji} {name}: 비어있음")
            continue

        weather_tag = " 🌤" if f.get("weather_boosted") else ""
        lines.append(f"{emoji} {name}: +{f['per_user']}조각/인 ({f['capped']}/{f['total_score']}점){weather_tag}")

    if round_result["total_xp"] > 0:
        lines.append(f"\n{icon_emoji('stationery')} 캠프 경험치 +{round_result['total_xp']}")

    if round_result["level_up"]:
        new_info = get_level_info(round_result["level_up"])
        lines.append(f"🎉 캠프가 {new_info[5]}(으)로 성장했습니다!")
        new_fields = new_info[1]
        old_info = get_level_info(round_result["level_up"] - 1)
        if new_fields > old_info[1]:
            lines.append("🆕 새 필드를 열 수 있습니다! 소유자가 '캠프설정'에서 선택하세요.")

    return "\n".join(lines)


def build_combined_announcement(
    round_result: dict,
    camp_level: int,
    fields: list[dict],
    bonuses: list[dict],
    chat_id: int = 0,
) -> str:
    """정산 결과 + 새 라운드 보너스를 하나의 메시지로 합침."""
    level_info = get_level_info(camp_level)
    level_name = level_info[5]
    bonus_map = {b["field_id"]: b for b in bonuses}

    lines = [f"🏕 <b>캠프 소식</b> ({level_name})"]

    # 새 라운드 날씨
    if chat_id:
        weather = get_camp_weather(chat_id)
        lines.append(_weather_line(weather))
        boosted_names = [config.CAMP_FIELDS[ft]["name"] for ft in weather[2] if ft in config.CAMP_FIELDS]
        if boosted_names:
            lines.append(f"  → {'/'.join(boosted_names)} 조각 ×{config.CAMP_WEATHER_MULTIPLIER}")

    # 이전 라운드 정산 결과
    lines.append("")
    lines.append("📊 <b>지난 라운드 결과</b>")
    for f in round_result["fields"]:
        field_info = config.CAMP_FIELDS.get(f["field_type"], {})
        emoji = field_info.get("emoji", "🏕")
        name = field_info.get("name", f["field_type"])

        if not f["users"]:
            lines.append(f"{emoji} {name}: 비어있음")
            continue

        weather_tag = " 🌤" if f.get("weather_boosted") else ""
        lines.append(f"{emoji} {name}: +{f['per_user']}조각/인 ({f['capped']}/{f['total_score']}점){weather_tag}")

    if round_result["total_xp"] > 0:
        lines.append(f"{icon_emoji('stationery')} 캠프 경험치 +{round_result['total_xp']}")

    if round_result["level_up"]:
        new_info = get_level_info(round_result["level_up"])
        lines.append(f"🎉 캠프가 {new_info[5]}(으)로 성장했습니다!")
        new_fields = new_info[1]
        old_info = get_level_info(round_result["level_up"] - 1)
        if new_fields > old_info[1]:
            lines.append("🆕 새 필드를 열 수 있습니다!")

    # 새 라운드 보너스
    lines.append("")
    lines.append("⭐ <b>이번 라운드 보너스</b>")
    for field in fields:
        field_info = config.CAMP_FIELDS.get(field["field_type"], {})
        emoji = field_info.get("emoji", "🏕")
        name = field_info.get("name", field["field_type"])

        bonus = bonus_map.get(field["id"])
        if bonus:
            pname = _pokemon_name(bonus["pokemon_id"])
            stat_name = config.CAMP_IV_STAT_NAMES.get(bonus["stat_type"], "")
            lines.append(f"{emoji} {name}: {pname} ({stat_name} {bonus['stat_value']}↑)")
        else:
            lines.append(f"{emoji} {name}: 타입 맞는 포켓몬 배치")

    lines.append("")
    lines.append("💡 배치: 그룹에서 <code>캠프</code> 또는 DM에서 <code>거점캠프</code>")
    return "\n".join(lines)


def build_bonus_announcement(fields: list[dict], bonuses: list[dict], chat_id: int = 0) -> str:
    """접수 타임 시작 시 보너스 포켓몬 안내 메시지. (fallback용)"""
    bonus_map = {b["field_id"]: b for b in bonuses}

    lines = ["🏕 캠프 라운드 시작!"]

    if chat_id:
        weather = get_camp_weather(chat_id)
        lines.append(_weather_line(weather))
        boosted_names = [config.CAMP_FIELDS[ft]["name"] for ft in weather[2] if ft in config.CAMP_FIELDS]
        if boosted_names:
            lines.append(f"  → {'/'.join(boosted_names)} 조각 ×{config.CAMP_WEATHER_MULTIPLIER}")

    lines.append("")

    for field in fields:
        field_info = config.CAMP_FIELDS.get(field["field_type"], {})
        emoji = field_info.get("emoji", "🏕")
        name = field_info.get("name", field["field_type"])

        bonus = bonus_map.get(field["id"])
        if bonus:
            pname = _pokemon_name(bonus["pokemon_id"])
            stat_name = config.CAMP_IV_STAT_NAMES.get(bonus["stat_type"], "")
            lines.append(f"{emoji} {name}: {pname} ({stat_name} {bonus['stat_value']}↑)")
        else:
            lines.append(f"{emoji} {name}: 타입 맞는 포켓몬 배치")

    lines.append("")
    lines.append("💡 배치: 그룹에서 <code>캠프</code> 또는 DM에서 <code>거점캠프</code>")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# 배치 처리
# ═══════════════════════════════════════════════════════

async def try_place_pokemon(
    chat_id: int,
    field_id: int,
    user_id: int,
    instance_id: int,
    member_count: int,
    pokedex_count: int,
) -> tuple[bool, str]:
    """포켓몬 배치 시도.

    Args:
        instance_id: user_pokemon 테이블의 PK (id 컬럼)

    Returns:
        (success, message)
    """
    # 1) 캠프 존재 확인
    camp = await cq.get_camp(chat_id)
    if not camp:
        return False, "이 채팅방에는 캠프가 없습니다."

    # 2) 포켓몬 정보 가져오기
    user_pokemon = await queries.get_user_pokemon_by_id(instance_id)
    if not user_pokemon or user_pokemon.get("user_id") != user_id:
        return False, "소유하지 않은 포켓몬입니다."

    pokemon_id = user_pokemon["pokemon_id"]

    # 3) 필드 존재 확인
    field = await cq.get_field_by_id(field_id)
    if not field or field["chat_id"] != chat_id:
        return False, "존재하지 않는 필드입니다."

    # 4) 타입 매칭 확인
    if not pokemon_matches_field(pokemon_id, field["field_type"]):
        field_info = config.CAMP_FIELDS[field["field_type"]]
        type_names = "/".join(field_info["types"])
        return False, f"이 필드에는 {type_names} 타입만 배치할 수 있습니다."

    # 5) 일일 배치 횟수 확인
    daily_limit = get_daily_placement_limit(pokedex_count)
    daily_used = await cq.get_daily_placement_count(user_id)
    if daily_used >= daily_limit:
        return False, f"오늘 배치 횟수를 모두 사용했습니다. ({daily_used}/{daily_limit})"

    # 6) 슬롯 여유 확인
    total_slots = calc_total_slots(camp["level"], member_count)
    current_count = await cq.count_field_placements(field_id)

    # 이미 해당 필드에 배치 중인지 확인 (업데이트 가능)
    existing = await cq.get_user_placements_in_chat(chat_id, user_id)
    already_in_field = any(p["field_id"] == field_id for p in existing)

    if not already_in_field and current_count >= total_slots:
        return False, f"이 필드의 슬롯이 가득 찼습니다. ({current_count}/{total_slots})"

    # 7) 승인제 확인
    settings = await cq.get_chat_camp_settings(chat_id)
    if settings and settings.get("approval_mode"):
        approval_slots = settings.get("approval_slots", 0)
        if approval_slots > 0 and not already_in_field:
            free_slots = total_slots - approval_slots
            if current_count >= free_slots:
                req_id = await cq.add_approval_request(chat_id, field_id, user_id, pokemon_id, instance_id)
                return False, f"승인대기|{req_id}"  # 핸들러가 이 패턴 감지

    # 8) 점수 계산 (현재 라운드 보너스 기준)
    now = config.get_kst_now()
    bonuses = await cq.get_round_bonus(chat_id, _get_current_round_time(now))
    bonus = None
    for b in bonuses:
        if b["field_id"] == field_id:
            bonus = b
            break

    ivs = {
        "iv_hp": user_pokemon.get("iv_hp", 0),
        "iv_atk": user_pokemon.get("iv_atk", 0),
        "iv_def": user_pokemon.get("iv_def", 0),
        "iv_spa": user_pokemon.get("iv_spa", 0),
        "iv_spdef": user_pokemon.get("iv_spdef", 0),
        "iv_spd": user_pokemon.get("iv_spd", 0),
    }

    score, desc = calc_placement_score(
        pokemon_id,
        bool(user_pokemon.get("is_shiny")),
        ivs,
        bonus["pokemon_id"] if bonus else None,
        bonus["stat_type"] if bonus else None,
        bonus["stat_value"] if bonus else None,
    )

    # 9) 배치 (upsert)
    await cq.place_pokemon(chat_id, field_id, user_id, pokemon_id, instance_id, "free", score)
    await cq.increment_daily_placement(user_id)

    pname = _pokemon_name(pokemon_id)
    field_info = config.CAMP_FIELDS[field["field_type"]]
    return True, f"{field_info['emoji']} {pname} 배치 완료! ({desc})"


def _get_current_round_time(now: datetime) -> datetime:
    """현재 시각 기준 진행 중 라운드의 시작 시각."""
    hours = config.CAMP_ROUND_HOURS
    current_hour = now.hour

    # 현재 시간 이하인 가장 가까운 라운드 시각
    round_hour = hours[0]
    for h in hours:
        if h <= current_hour:
            round_hour = h
        else:
            break

    # 0시(자정) 처리: 현재가 0시 이후 ~ 9시 이전이면 전날 0시 라운드
    if current_hour < hours[0] and hours[-1] == 0:
        round_hour = 0

    return now.replace(hour=round_hour, minute=0, second=0, microsecond=0)


def get_previous_round_time(now: datetime) -> datetime:
    """현재 시각 기준 이전 라운드의 시작 시각 (정산용).

    CAMP_ROUND_HOURS=[9,12,15,18,21,0] 기준:
      now=09:00 → 이전 라운드 = 당일 00:00
      now=12:00 → 이전 라운드 = 당일 09:00
      now=00:00 → 이전 라운드 = 당일 21:00
    """
    from datetime import timedelta

    # 시간순 정렬 (0, 9, 12, 15, 18, 21)
    sorted_hours = sorted(config.CAMP_ROUND_HOURS)
    current_hour = now.hour

    # 현재 시각의 인덱스 찾기 → 한 칸 앞이 이전 라운드
    if current_hour in sorted_hours:
        idx = sorted_hours.index(current_hour)
        prev_hour = sorted_hours[idx - 1]  # idx=0이면 [-1] → 마지막 원소(21)
    else:
        # 라운드 시각이 아닌 시간대 (일반적으론 잡이 정시에만 호출)
        prev_hour = sorted_hours[0]
        for h in sorted_hours:
            if h < current_hour:
                prev_hour = h

    result = now.replace(hour=prev_hour, minute=0, second=0, microsecond=0)
    # 이전 라운드가 현재보다 큰 시각이면 전날 (예: now=00시, prev=21시)
    if prev_hour > current_hour:
        result -= timedelta(days=1)
    return result


def normalize_round_time(now: datetime) -> datetime:
    """시각을 라운드 시각으로 정규화 (초/분 제거)."""
    return now.replace(minute=0, second=0, microsecond=0)


# ═══════════════════════════════════════════════════════
# 이로치 전환
# ═══════════════════════════════════════════════════════

async def convert_to_shiny(user_id: int, instance_id: int) -> tuple[bool, str, dict | None]:
    """이로치 전환 시도.

    Args:
        instance_id: user_pokemon 테이블 PK

    Returns:
        (success, message, info_dict | None)
        info_dict: {"pokemon_id", "name", "rarity"} on success
    """
    # 포켓몬 정보
    pokemon = await queries.get_user_pokemon_by_id(instance_id)
    if not pokemon or pokemon.get("user_id") != user_id:
        return False, "소유하지 않은 포켓몬입니다.", None

    if pokemon.get("is_shiny"):
        return False, "이미 이로치입니다.", None

    pokemon_id = pokemon["pokemon_id"]
    rarity = pokemon.get("rarity") or _pokemon_rarity(pokemon_id)
    pname = _pokemon_name(pokemon_id)

    # 1) 쿨타임 확인
    cooldown_sec = config.CAMP_SHINY_COOLDOWN.get(rarity, 86400)
    last_convert = await cq.get_shiny_cooldown(user_id)
    if last_convert:
        now = config.get_kst_now()
        elapsed = (now - last_convert).total_seconds()
        if elapsed < cooldown_sec:
            remaining = cooldown_sec - elapsed
            hours = int(remaining // 3600)
            mins = int((remaining % 3600) // 60)
            return False, f"전환 쿨타임 중입니다. ({hours}시간 {mins}분 남음)", None

    # 2) 필드 귀속 조각 확인 (듀얼타입은 어느 필드든 가능)
    matching_fields = get_matching_fields(pokemon_id)
    if not matching_fields:
        return False, "이 포켓몬은 어떤 필드에도 맞지 않습니다.", None

    frag_cost = config.CAMP_SHINY_COST.get(rarity, 12)
    user_frags = await cq.get_user_fragments(user_id)

    # 매칭 필드 중 조각이 충분한 것 찾기
    chosen_field = None
    for fkey in matching_fields:
        if user_frags.get(fkey, 0) >= frag_cost:
            chosen_field = fkey
            break

    if not chosen_field:
        field_names = ", ".join(
            config.CAMP_FIELDS[f]["name"] for f in matching_fields
        )
        best = max((user_frags.get(f, 0) for f in matching_fields), default=0)
        return False, f"{field_names} 조각이 부족합니다. ({best}/{frag_cost})", None

    # 3) 결정 확인
    crystal_cost = config.CAMP_CRYSTAL_COST.get(rarity, 0)
    rainbow_cost = config.CAMP_RAINBOW_COST.get(rarity, 0)

    # 3~6) 결정 + 조각 소모 + 이로치 전환을 트랜잭션으로 원자 처리
    if crystal_cost > 0 or rainbow_cost > 0:
        crystals = await cq.get_crystals(user_id)
        if crystals["crystal"] < crystal_cost:
            return False, f"결정이 부족합니다. ({crystals['crystal']}/{crystal_cost})", None
        if crystals["rainbow"] < rainbow_cost:
            return False, f"무지개 결정이 부족합니다. ({crystals['rainbow']}/{rainbow_cost})", None

    from database.connection import get_db
    pool = await get_db()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # 결정 소모
                if crystal_cost > 0 or rainbow_cost > 0:
                    row = await conn.fetchrow(
                        """UPDATE camp_crystals
                           SET crystal = crystal - $2, rainbow = rainbow - $3
                           WHERE user_id = $1 AND crystal >= $2 AND rainbow >= $3
                           RETURNING crystal""",
                        user_id, crystal_cost, rainbow_cost,
                    )
                    if not row:
                        return False, "결정 소모에 실패했습니다.", None

                # 조각 소모
                row = await conn.fetchrow(
                    """UPDATE camp_fragments
                       SET amount = amount - $3
                       WHERE user_id = $1 AND field_type = $2 AND amount >= $3
                       RETURNING amount""",
                    user_id, chosen_field, frag_cost,
                )
                if not row:
                    return False, "조각 소모에 실패했습니다.", None

                # 이로치 전환
                row = await conn.fetchrow(
                    "UPDATE user_pokemon SET is_shiny = TRUE WHERE id = $1 RETURNING id",
                    instance_id,
                )
                if not row:
                    return False, "전환에 실패했습니다.", None

                # 쿨타임 기록
                await conn.execute(
                    """INSERT INTO camp_shiny_cooldown (user_id, last_convert)
                       VALUES ($1, NOW())
                       ON CONFLICT (user_id) DO UPDATE SET last_convert = NOW()""",
                    user_id,
                )
    except Exception as e:
        logger.error("이로치 전환 트랜잭션 실패: %s", e)
        return False, "전환 처리 중 오류가 발생했습니다.", None

    # 7) 로그
    field_name = config.CAMP_FIELDS[chosen_field]["name"]
    await cq.log_fragment(user_id, 0, chosen_field, -frag_cost, "shiny_convert")

    cost_parts = [f"{field_name}조각 {frag_cost}개"]
    if crystal_cost:
        cost_parts.append(f"결정 {crystal_cost}개")
    if rainbow_cost:
        cost_parts.append(f"무지개결정 {rainbow_cost}개")
    cost_str = " + ".join(cost_parts)

    info = {"pokemon_id": pokemon_id, "name": pname, "rarity": rarity}
    return True, f"{shiny_emoji()} {pname}(이/가) 이로치로 변했습니다! 🎉\n소모: {cost_str}", info


# ═══════════════════════════════════════════════════════
# 분해 시스템
# ═══════════════════════════════════════════════════════

async def decompose_shiny(user_id: int, instance_id: int) -> tuple[bool, str]:
    """이로치 분해 → 결정/무지개 결정 획득.

    Args:
        instance_id: user_pokemon 테이블 PK

    Returns:
        (success, message)
    """
    pokemon = await queries.get_user_pokemon_by_id(instance_id)
    if not pokemon or pokemon.get("user_id") != user_id:
        return False, "소유하지 않은 포켓몬입니다."

    if not pokemon.get("is_shiny"):
        return False, "이로치가 아닙니다."

    pokemon_id = pokemon["pokemon_id"]
    rarity = pokemon.get("rarity") or _pokemon_rarity(pokemon_id)
    pname = pokemon.get("name_ko") or _pokemon_name(pokemon_id)

    crystal_gain = config.CAMP_DECOMPOSE_CRYSTAL.get(rarity, 1)
    rainbow_gain = config.CAMP_DECOMPOSE_RAINBOW.get(rarity, 0)

    # 이로치 해제 (is_shiny = 0)
    try:
        from database.connection import get_db
        pool = await get_db()
        result = await pool.execute(
            "UPDATE user_pokemon SET is_shiny = 0 WHERE id = $1 AND is_shiny = 1",
            instance_id,
        )
        if not result.endswith("1"):
            return False, "분해에 실패했습니다."
    except Exception as e:
        logger.error(f"[Camp Decompose] Error: {e}")
        return False, "분해 처리 중 오류가 발생했습니다."

    # 결정 지급
    await cq.add_crystals(user_id, crystal_gain, rainbow_gain)

    # 캠프 배치에서 제거 (이로치 해제됐으므로 점수 변동)
    await cq.remove_user_pokemon_placements(user_id, instance_id)

    parts = [f"💎 결정 +{crystal_gain}"]
    if rainbow_gain > 0:
        parts.append(f"🌈 무지개결정 +{rainbow_gain}")
    gain_str = ", ".join(parts)

    return True, f"🔨 {pname} 분해 완료!\n{gain_str}"


# ═══════════════════════════════════════════════════════
# 캠프 개설
# ═══════════════════════════════════════════════════════

async def create_camp(chat_id: int, creator_id: int, first_field: str) -> tuple[bool, str]:
    """캠프 개설 + 첫 필드 생성.

    Returns:
        (success, message)
    """
    existing = await cq.get_camp(chat_id)
    if existing:
        return False, "이미 캠프가 존재합니다."

    if first_field not in config.CAMP_FIELDS:
        return False, "존재하지 않는 필드 타입입니다."

    await cq.create_camp(chat_id, creator_id)
    await cq.add_field(chat_id, first_field, 1)

    field_info = config.CAMP_FIELDS[first_field]
    return True, (
        f"🏕 캠프가 개설되었습니다!\n"
        f"첫 번째 필드: {field_info['emoji']} {field_info['name']}\n"
        f"레벨 1 — 🏜️ 빈 터"
    )


# ═══════════════════════════════════════════════════════
# 필드 추가/변경
# ═══════════════════════════════════════════════════════

async def add_new_field(chat_id: int, field_type: str) -> tuple[bool, str]:
    """레벨업 시 새 필드 추가."""
    camp = await cq.get_camp(chat_id)
    if not camp:
        return False, "캠프가 없습니다."

    level_info = get_level_info(camp["level"])
    max_fields = level_info[1]

    fields = await cq.get_fields(chat_id)
    if len(fields) >= max_fields:
        return False, f"현재 레벨에서 최대 {max_fields}개 필드까지 가능합니다."

    # 중복 필드 체크
    existing_types = {f["field_type"] for f in fields}
    if field_type in existing_types:
        return False, "이미 열려있는 필드입니다."

    if field_type not in config.CAMP_FIELDS:
        return False, "존재하지 않는 필드 타입입니다."

    unlock_order = len(fields) + 1
    await cq.add_field(chat_id, field_type, unlock_order)

    field_info = config.CAMP_FIELDS[field_type]
    return True, f"🆕 {field_info['emoji']} {field_info['name']} 필드가 열렸습니다!"


async def change_field_type(chat_id: int, field_id: int, new_type: str) -> tuple[bool, str]:
    """필드 타입 변경 (쿨타임 3시간)."""
    field = await cq.get_field_by_id(field_id)
    if not field or field["chat_id"] != chat_id:
        return False, "존재하지 않는 필드입니다."

    if new_type not in config.CAMP_FIELDS:
        return False, "존재하지 않는 필드 타입입니다."

    if field["field_type"] == new_type:
        return False, "이미 같은 타입입니다."

    # 중복 체크
    fields = await cq.get_fields(chat_id)
    if any(f["field_type"] == new_type for f in fields):
        return False, "이미 열려있는 필드 타입입니다."

    # 쿨타임 체크
    settings = await cq.get_chat_camp_settings(chat_id)
    if settings and settings.get("last_field_change"):
        now = config.get_kst_now()
        elapsed = (now - settings["last_field_change"]).total_seconds()
        if elapsed < config.CAMP_SETTING_COOLDOWN:
            remaining = config.CAMP_SETTING_COOLDOWN - elapsed
            mins = int(remaining // 60)
            return False, f"필드 변경 쿨타임 중입니다. ({mins}분 남음)"

    # 기존 배치 삭제 + 필드 타입 변경을 트랜잭션으로 처리
    from database.connection import get_db
    pool = await get_db()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM camp_placements WHERE field_id = $1", field_id)
            await conn.execute(
                "UPDATE camp_fields SET field_type = $1 WHERE id = $2",
                new_type, field_id,
            )
    await cq.update_chat_camp_settings(
        chat_id, last_field_change=config.get_kst_now(),
    )

    old_info = config.CAMP_FIELDS[field["field_type"]]
    new_info = config.CAMP_FIELDS[new_type]
    return True, f"필드 변경: {old_info['emoji']} {old_info['name']} → {new_info['emoji']} {new_info['name']}"


# ═══════════════════════════════════════════════════════
# 승인 처리
# ═══════════════════════════════════════════════════════

async def process_approval(request_id: int, member_count: int) -> tuple[bool, str]:
    """승인 요청 처리 → 실제 배치 (수동 승인)."""
    req = await cq.approve_request(request_id)
    if not req:
        return False, "이미 처리된 요청입니다."

    return await _execute_placement(req, member_count)


async def _execute_placement(req: dict, member_count: int) -> tuple[bool, str]:
    """승인된 요청을 실제 배치로 변환."""
    camp = await cq.get_camp(req["chat_id"])
    if not camp:
        return False, "캠프가 없습니다."

    total_slots = calc_total_slots(camp["level"], member_count)
    current = await cq.count_field_placements(req["field_id"])
    if current >= total_slots:
        return False, "슬롯이 가득 찼습니다."

    pokemon = await queries.get_user_pokemon_by_id(req["instance_id"])
    if not pokemon or pokemon.get("user_id") != req["user_id"]:
        return False, "포켓몬을 찾을 수 없습니다."

    await cq.place_pokemon(
        req["chat_id"], req["field_id"], req["user_id"],
        req["pokemon_id"], req["instance_id"], "approved", 1,
    )

    pname = _pokemon_name(req["pokemon_id"])
    return True, f"✅ {pname} 배치 승인 완료!"


async def process_auto_approvals(chat_id: int, member_count: int) -> list[str]:
    """30분 초과 대기 승인 자동 처리. 결과 메시지 리스트 반환."""
    approved = await cq.auto_approve_expired(chat_id, config.CAMP_APPROVAL_TIMEOUT)
    results = []
    for req in approved:
        # auto_approve_expired가 이미 status='approved'로 변경했으므로
        # approve_request를 거치지 않고 바로 배치 실행
        ok, msg = await _execute_placement(req, member_count)
        if ok:
            pname = _pokemon_name(req["pokemon_id"])
            results.append(f"⏰ {pname} 자동 승인 (30분 초과)")
    return results


# ═══════════════════════════════════════════════════════
# DM 현황
# ═══════════════════════════════════════════════════════

async def get_weekly_mvp(chat_id: int, days: int = 7) -> list[dict]:
    """주간 MVP 랭킹 조회. [{user_id, total, first_name, username, rank}, ...]"""
    rows = await cq.get_weekly_top_contributors(chat_id, days=days, limit=10)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


async def get_user_camp_summary(user_id: int) -> dict:
    """DM '내캠프' 현황 데이터 생성.

    Returns:
        {
            "home_camp": chat_id | None,
            "placements": [placement_dict, ...],
            "fragments": {field_type: amount, ...},
            "crystals": {crystal: int, rainbow: int},
            "cooldown_remaining": seconds | None,
        }
    """
    settings = await cq.get_user_camp_settings(user_id)
    home_camp = settings["home_chat_id"] if settings else None

    placements = await cq.get_user_placements(user_id)
    fragments = await cq.get_user_fragments(user_id)
    crystals = await cq.get_crystals(user_id)

    # 쿨타임
    last_convert = await cq.get_shiny_cooldown(user_id)
    cooldown_remaining = None
    if last_convert:
        now = config.get_kst_now()
        # 가장 긴 쿨타임 기준으로 표시 (실제 전환 시 등급별 체크)
        elapsed = (now - last_convert).total_seconds()
        # 커먼 쿨타임(6h)으로 표시
        min_cooldown = config.CAMP_SHINY_COOLDOWN["common"]
        if elapsed < min_cooldown:
            cooldown_remaining = min_cooldown - elapsed

    return {
        "home_camp": home_camp,
        "placements": placements,
        "fragments": fragments,
        "crystals": crystals,
        "cooldown_remaining": cooldown_remaining,
    }


async def set_home_camp(user_id: int, chat_id: int) -> tuple[bool, str]:
    """거점 캠프 설정 (7일 쿨다운)."""
    settings = await cq.get_user_camp_settings(user_id)

    # 기존 거점이 같은 방이면 무시
    if settings and settings.get("home_chat_id") == chat_id:
        return False, "이미 이 채팅방이 거점 캠프입니다."

    # 2번째 거점과도 같은지 확인
    if settings and settings.get("home_chat_id_2") == chat_id:
        return False, "이미 이 채팅방이 2번째 거점 캠프입니다."

    # 7일 쿨다운 체크
    if settings and settings.get("home_camp_set_at"):
        now = config.get_kst_now()
        elapsed = (now - settings["home_camp_set_at"]).total_seconds()
        cooldown = 7 * 86400  # 7일
        if elapsed < cooldown:
            remaining = cooldown - elapsed
            days = int(remaining // 86400)
            hours = int((remaining % 86400) // 3600)
            return False, f"거점 변경 쿨다운 중입니다. ({days}일 {hours}시간 남음)"

    camp = await cq.get_camp(chat_id)
    if not camp:
        return False, "해당 채팅방에 캠프가 없습니다."

    is_first = settings is None or settings.get("home_chat_id") is None
    await cq.set_home_camp(user_id, chat_id)

    if is_first:
        return True, "FIRST_HOME"  # 핸들러에서 튜토리얼 트리거
    return True, "🏠 거점 캠프가 변경되었습니다!"


async def set_home_camp_2(user_id: int, chat_id: int) -> tuple[bool, str]:
    """2번째 거점 캠프 설정 (구독자 전용, 7일 쿨다운)."""
    from services.subscription_service import get_user_tier
    tier = await get_user_tier(user_id)
    has_dual = config.SUBSCRIPTION_TIERS.get(tier, {}).get("benefits", {}).get("dual_home_camp")
    if not has_dual:
        return False, "2번째 거점캠프는 구독자 전용 혜택입니다."

    settings = await cq.get_user_camp_settings(user_id)

    # 기존 거점과 같은지 확인
    if settings and settings.get("home_chat_id") == chat_id:
        return False, "이미 1번째 거점과 같은 캠프입니다."

    # 2번째 거점이 같은 방이면 무시
    if settings and settings.get("home_chat_id_2") == chat_id:
        return False, "이미 이 채팅방이 2번째 거점 캠프입니다."

    # 7일 쿨다운 체크 (2번째 거점 별도 쿨다운)
    if settings and settings.get("home_camp_set_at_2"):
        now = config.get_kst_now()
        elapsed = (now - settings["home_camp_set_at_2"]).total_seconds()
        cooldown = 7 * 86400  # 7일
        if elapsed < cooldown:
            remaining = cooldown - elapsed
            days = int(remaining // 86400)
            hours = int((remaining % 86400) // 3600)
            return False, f"2번째 거점 변경 쿨다운 중입니다. ({days}일 {hours}시간 남음)"

    camp = await cq.get_camp(chat_id)
    if not camp:
        return False, "해당 채팅방에 캠프가 없습니다."

    await cq.set_home_camp_2(user_id, chat_id)
    return True, "🏠 2번째 거점 캠프가 설정되었습니다!"


async def remove_home_camp_2(user_id: int) -> tuple[bool, str]:
    """2번째 거점 캠프 해제."""
    settings = await cq.get_user_camp_settings(user_id)
    if not settings or not settings.get("home_chat_id_2"):
        return False, "2번째 거점 캠프가 설정되어 있지 않습니다."
    await cq.remove_home_camp_2(user_id)
    return True, "🏠 2번째 거점 캠프가 해제되었습니다."


# ═══════════════════════════════════════════════════════
# 배치 모드 설정 (소유자)
# ═══════════════════════════════════════════════════════

async def toggle_approval_mode(chat_id: int, enable: bool, slots: int = 0) -> tuple[bool, str]:
    """승인제 토글. enable=True이면 slots개를 승인 슬롯으로 설정."""
    settings = await cq.get_chat_camp_settings(chat_id)
    if settings and settings.get("last_mode_change"):
        now = config.get_kst_now()
        elapsed = (now - settings["last_mode_change"]).total_seconds()
        if elapsed < config.CAMP_SETTING_COOLDOWN:
            remaining = config.CAMP_SETTING_COOLDOWN - elapsed
            mins = int(remaining // 60)
            return False, f"모드 변경 쿨타임 중입니다. ({mins}분 남음)"

    await cq.update_chat_camp_settings(
        chat_id,
        approval_mode=enable,
        approval_slots=max(0, min(slots, config.CAMP_MAX_APPROVAL_SLOTS)) if enable else 0,
        last_mode_change=config.get_kst_now(),
    )

    if enable:
        return True, f"🔒 승인제 전환 (승인 슬롯: {slots}칸)"
    else:
        return True, "🔓 자유 배치 모드로 전환"
