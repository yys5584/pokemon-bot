"""배틀로얄: 전원 동시 투입, 매 라운드 랜덤 재해, 최후의 1마리 우승.

AI Masters 이벤트용. 토너먼트 대체.
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field

from utils.helpers import icon_emoji, type_badge

logger = logging.getLogger(__name__)


# ── 재해 테이블 ──────────────────────────────────────────────────

@dataclass
class Disaster:
    name: str
    emoji: str
    immune_types: list[str]
    damage: int
    flavor: str  # "물타입 면역" 같은 한줄 설명


DISASTERS = [
    Disaster("해일",       "🌊", ["water"],           40, "물타입 면역"),
    Disaster("화산 폭발",  "🔥", ["fire"],            40, "불타입 면역"),
    Disaster("번개 폭풍",  "⚡", ["electric"],         40, "전기타입 면역"),
    Disaster("맹독 늪",    "☠️", ["poison", "grass"],  35, "독/풀타입 면역"),
    Disaster("운석 충돌",  "☄️", ["rock", "steel"],    45, "바위/강철타입 면역"),
    Disaster("눈보라",     "❄️", ["ice"],              40, "얼음타입 면역"),
    Disaster("태풍",       "🌪️", ["flying"],           40, "비행타입 면역"),
    Disaster("지진",       "🏔️", ["ground", "flying"], 40, "땅/비행타입 면역"),
    Disaster("초능력파",   "🔮", ["psychic", "dark"],  35, "에스퍼/악타입 면역"),
    Disaster("드래곤 브레스","🐉", ["dragon", "fairy"], 45, "드래곤/페어리타입 면역"),
]

SUDDEN_DEATH = Disaster("서든데스", "💀", [], 80, "면역 없음! 전원 대데미지!")
HEALING_WIND = Disaster("힐링 바람", "💚", [], -25, "전원 회복!")


# ── 참가자 ───────────────────────────────────────────────────────

@dataclass
class Contestant:
    user_id: int
    user_name: str
    pokemon_id: int
    pokemon_name: str
    pokemon_emoji: str
    pokemon_type: str
    rarity: str
    hp: int = 100
    max_hp: int = 100
    alive: bool = True
    death_round: int = 0  # 탈락 라운드 (0 = 생존중)


# ── 코어 로직 ────────────────────────────────────────────────────

def _get_pokemon_type(pokemon_id: int) -> str:
    """pokemon_battle_data에서 타입 가져오기."""
    from models.pokemon_battle_data import POKEMON_BATTLE_DATA
    data = POKEMON_BATTLE_DATA.get(pokemon_id)
    if data:
        return data[0]  # primary type
    return "normal"


def build_contestants(participants: dict) -> list[Contestant]:
    """tournament_state participants → Contestant 리스트."""
    result = []
    for user_id, data in participants.items():
        team = data.get("team", [])
        if not team:
            continue
        pkmn = team[0]
        ptype = pkmn.get("pokemon_type") or _get_pokemon_type(pkmn.get("pokemon_id", 0))
        result.append(Contestant(
            user_id=user_id,
            user_name=data["name"],
            pokemon_id=pkmn.get("pokemon_id", 0),
            pokemon_name=pkmn.get("name_ko", "???"),
            pokemon_emoji=pkmn.get("emoji", ""),
            pokemon_type=ptype,
            rarity=pkmn.get("rarity", "common"),
        ))
    return result


def pick_disaster(round_num: int, total_rounds_est: int, alive_count: int) -> Disaster:
    """라운드에 맞는 재해 선택."""
    # 생존자 3명 이하 → 서든데스
    if alive_count <= 3:
        return SUDDEN_DEATH
    # 가끔 힐링 (25% 확률, 라운드 3 이후)
    if round_num >= 3 and random.random() < 0.2:
        return HEALING_WIND
    return random.choice(DISASTERS)


def apply_disaster(contestants: list[Contestant], disaster: Disaster, round_num: int) -> tuple[list[Contestant], list[Contestant]]:
    """재해 적용. (생존자, 이번 라운드 탈락자) 반환."""
    newly_dead = []
    for c in contestants:
        if not c.alive:
            continue
        if c.pokemon_type in disaster.immune_types:
            continue  # 면역
        variance = random.randint(-5, 5)
        if disaster.damage < 0:
            # 힐링: HP 회복
            c.hp = min(c.hp + abs(disaster.damage) + variance, c.max_hp)
        else:
            # 데미지
            c.hp -= (disaster.damage + variance)
        if c.hp <= 0:
            c.hp = 0
            c.alive = False
            c.death_round = round_num
            newly_dead.append(c)

    alive = [c for c in contestants if c.alive]
    return alive, newly_dead


def compute_placements(contestants: list[Contestant]) -> dict[int, int]:
    """user_id → 순위. 늦게 죽을수록 높은 순위."""
    # 생존자 = 1등
    # death_round 큰 순서 = 높은 순위
    sorted_c = sorted(contestants, key=lambda c: (-c.death_round if not c.alive else float('inf'), c.user_id))
    # 생존자 먼저, 그 다음 늦게 죽은 순서
    alive_sorted = [c for c in contestants if c.alive]
    dead_sorted = sorted([c for c in contestants if not c.alive], key=lambda c: -c.death_round)

    placements = {}
    rank = 1
    for c in alive_sorted:
        placements[c.user_id] = rank
        rank += 1

    # 같은 라운드 탈락 = 공동 순위
    prev_round = None
    prev_rank = rank
    for c in dead_sorted:
        if c.death_round != prev_round:
            prev_rank = rank
            prev_round = c.death_round
        placements[c.user_id] = prev_rank
        rank += 1

    return placements


# ── 디스플레이 ───────────────────────────────────────────────────

async def run_battle_royale(context, chat_id: int, participants: dict) -> dict[int, int]:
    """배틀로얄 실행. 채팅에 실시간 중계. placements dict 반환."""
    from services.tournament_render import _safe_send

    contestants = build_contestants(participants)
    if len(contestants) < 2:
        await _safe_send(context.bot, chat_id, text="참가자가 부족합니다!", parse_mode="HTML")
        return {}

    total = len(contestants)
    battle_icon = icon_emoji("battle")
    skull = icon_emoji("skull")

    # ── 인트로 ──
    intro_lines = [
        f"{battle_icon} 포켓몬 배틀로얄!",
        "━━━━━━━━━━━━━━━",
        f"참가자 {total}명의 포켓몬이 투입됩니다!",
        "",
    ]
    # 참가자 목록 (최대 30명까지만, 넘으면 요약)
    show_list = contestants[:30]
    for c in show_list:
        tb = type_badge(c.pokemon_id)
        intro_lines.append(f"  {tb} {c.pokemon_name} ({c.user_name})")
    if len(contestants) > 30:
        intro_lines.append(f"  ...외 {len(contestants) - 30}마리")
    intro_lines.append(f"\n전원 HP {contestants[0].max_hp}로 시작!")

    await _safe_send(context.bot, chat_id, text="\n".join(intro_lines), parse_mode="HTML")
    await asyncio.sleep(5)

    # ── 라운드 루프 ──
    round_num = 0
    mc_comments = [
        "문박사: 상황이 급변하고 있습니다!",
        "문박사: 누가 살아남을 것인가!",
        "문박사: 긴장감이 최고조입니다!",
        "문박사: 아직 끝나지 않았다!",
        "문박사: 운명의 장난인가!",
    ]

    while True:
        alive = [c for c in contestants if c.alive]
        if len(alive) <= 1:
            break
        if round_num >= 20:  # 안전장치
            break

        round_num += 1
        disaster = pick_disaster(round_num, 12, len(alive))
        alive_before = len(alive)
        alive_list, newly_dead = apply_disaster(contestants, disaster, round_num)
        alive_after = len(alive_list)

        # ── 재해 발표 ──
        header = (
            f"{disaster.emoji} {round_num}라운드 — {disaster.name}!\n"
            f"{disaster.flavor}, 나머지 {'+' if disaster.damage < 0 else '-'}{abs(disaster.damage)}HP!"
        )
        await _safe_send(context.bot, chat_id, text=header, parse_mode="HTML")
        await asyncio.sleep(2)

        # ── 탈락자 한 명씩 표시 ──
        if newly_dead:
            for c in newly_dead:
                await _safe_send(context.bot, chat_id,
                    text=f"{skull} {type_badge(c.pokemon_id)}{c.user_name}({c.pokemon_name}) 탈락!",
                    parse_mode="HTML",
                )
                await asyncio.sleep(1)
        elif disaster.damage < 0:
            await _safe_send(context.bot, chat_id, text="전원 체력 회복!", parse_mode="HTML")
        else:
            await _safe_send(context.bot, chat_id, text="이번엔 탈락자 없음!", parse_mode="HTML")

        # ── 생존 현황 ──
        survive_lines = [f"생존: {alive_after}/{total}마리"]
        if disaster.immune_types:
            immune = [c for c in alive_list if c.pokemon_type in disaster.immune_types]
            if immune and len(immune) <= 8:
                immune_names = [f"{type_badge(c.pokemon_id)}{c.pokemon_name}" for c in immune]
                survive_lines.append(f"면역: {', '.join(immune_names)}")

        await _safe_send(context.bot, chat_id, text="\n".join(survive_lines), parse_mode="HTML")

        # 딜레이
        if alive_after <= 5:
            await asyncio.sleep(4)
        else:
            await asyncio.sleep(3)

        # 가끔 문박사 멘트
        if round_num % 3 == 0 and alive_after > 1:
            await _safe_send(context.bot, chat_id, text=random.choice(mc_comments), parse_mode="HTML")
            await asyncio.sleep(2)

    # ── 결과 ──
    placements = compute_placements(contestants)
    alive = [c for c in contestants if c.alive]

    if alive:
        winner = alive[0]
        champ = icon_emoji("champion_first")
        await _safe_send(context.bot, chat_id,
            text=(
                f"================\n\n"
                f"{champ} 최후의 생존자!\n\n"
                f"  {type_badge(winner.pokemon_id)} <b>{winner.pokemon_name}</b>\n"
                f"  트레이너: <b>{winner.user_name}</b>\n"
                f"  남은 HP: {winner.hp}/{winner.max_hp}\n\n"
                f"  {total}마리 중 끝까지 살아남았다!\n\n"
                f"================"
            ),
            parse_mode="HTML",
        )
    else:
        # 전멸 (동시 탈락)
        await _safe_send(context.bot, chat_id,
            text=f"{icon_emoji('skull')} 전멸! 승자 없음!",
            parse_mode="HTML",
        )

    return placements
