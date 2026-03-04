"""Tournament system: daily single-elimination in arcade channels."""

import asyncio
import math
import random
import logging
from datetime import datetime

from telegram.ext import ContextTypes

import config
from database import queries
from database import battle_queries as bq
from database.connection import get_db
from services.battle_service import _prepare_combatant, _resolve_battle, _hp_bar
from utils.helpers import icon_emoji, ball_emoji

logger = logging.getLogger(__name__)

# ── In-memory tournament state ──────────────────────────────────
_tournament_state = {
    "registering": False,
    "running": False,
    "participants": {},       # {user_id: {"name": str, "team": list[dict]}}
    "chat_id": None,
}


def _reset_state():
    _tournament_state["registering"] = False
    _tournament_state["running"] = False
    _tournament_state["participants"] = {}
    _tournament_state["chat_id"] = None


# ── Registration ────────────────────────────────────────────────

async def start_registration(context: ContextTypes.DEFAULT_TYPE):
    """JobQueue callback — 21:00 KST: stop spawns, open registration."""
    if not config.ARCADE_CHAT_IDS:
        logger.warning("No arcade chat IDs configured, skipping tournament.")
        return

    _reset_state()
    chat_id = next(iter(config.ARCADE_CHAT_IDS))
    _tournament_state["registering"] = True
    _tournament_state["chat_id"] = chat_id

    # Cancel all spawn jobs for this chat
    chat_str = str(chat_id)
    for job in context.job_queue.jobs():
        if job.name and chat_str in job.name and (
            job.name.startswith("spawn_") or job.name.startswith("arcade_")
        ):
            job.schedule_removal()

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "🏟️ 아케이드 토너먼트!\n"
            "━━━━━━━━━━━━━━━\n\n"
            "🕘 등록 시간: 지금 ~ 22:00\n"
            "📋 참가 방법: ㄷ 입력\n"
            "⚔️ 배틀팀이 등록되어 있어야 참가 가능!\n\n"
            "🏆 우승 보상\n"
            f"  🥇 마스터볼 {config.TOURNAMENT_PRIZE_1ST_MB}개 + {config.TOURNAMENT_PRIZE_1ST_BP} BP\n"
            f"  🥈 {config.TOURNAMENT_PRIZE_2ND_BP} BP\n"
            f"  🏅 4강 {config.TOURNAMENT_PRIZE_4TH_BP} BP\n\n"
            "스폰은 대회 종료 후 재개됩니다."
        ),
    )
    logger.info(f"Tournament registration started for chat {chat_id}")

    # Send DM notification to all users
    # asyncio.create_task(_broadcast_tournament_dm(context))  # TEMP DISABLED


async def _broadcast_tournament_dm(context: ContextTypes.DEFAULT_TYPE):
    """Send DM to all registered users about tournament registration."""
    try:
        user_ids = await queries.get_recently_active_user_ids(minutes=720)
        logger.info(f"Broadcasting tournament DM to {len(user_ids)} users")

        msg = (
            "🏟️ 오늘 밤 아케이드 토너먼트!\n\n"
            "⏰ 21:00~22:00 등록 / 22:00 대회 시작\n"
            "📋 아케이드 채널에서 ㄷ 입력으로 참가\n"
            "⚔️ 배틀팀 필수 — DM에서 '팀등록'으로 구성\n\n"
            "🏆 우승: 마스터볼 2개 + 200 BP\n"
            "🥈 준우승: 100 BP\n"
            "🏅 4강: 50 BP\n\n"
            "최초 우승자에겐 특별 칭호 🏛️초대 챔피언!\n\n"
            "👉 https://t.me/tg_poke"
        )

        sent = 0
        for uid in user_ids:
            try:
                await context.bot.send_message(chat_id=uid, text=msg)
                sent += 1
            except Exception:
                pass  # User blocked bot or never started DM
            # Rate limit: ~30 msgs/sec → sleep every 25
            if sent % 25 == 0:
                await asyncio.sleep(1)

        logger.info(f"Tournament DM sent to {sent}/{len(user_ids)} users")
    except Exception as e:
        logger.error(f"Tournament DM broadcast error: {e}", exc_info=True)


async def register_player(user_id: int, display_name: str) -> tuple[bool, str]:
    """Register a player for the tournament. Returns (success, message)."""
    if not _tournament_state["registering"]:
        return False, "현재 대회 등록 기간이 아닙니다."

    if _tournament_state["running"]:
        return False, "대회가 이미 진행 중입니다."

    if user_id in _tournament_state["participants"]:
        return False, "이미 등록되었습니다!"

    # Check battle team
    team = await bq.get_battle_team(user_id)
    if not team:
        return False, "배틀팀이 없습니다! DM에서 '팀등록'으로 팀을 먼저 구성하세요."

    _tournament_state["participants"][user_id] = {
        "name": display_name,
        "team": team,
    }

    count = len(_tournament_state["participants"])
    return True, (
        f"{icon_emoji('check')} {display_name} 참가 등록 완료!\n"
        f"현재 참가자: {count}명"
    )


# ── Bracket Generation ──────────────────────────────────────────

def _generate_bracket(players: list) -> list:
    """Generate a single-elimination bracket.

    Pads to the next power of 2 with byes (None).
    Returns list of (p1, p2) tuples for round 1.
    """
    random.shuffle(players)
    n = len(players)
    # Next power of 2
    size = 1
    while size < n:
        size *= 2

    # Pad with byes
    padded = list(players) + [None] * (size - n)

    # Create pairs
    matches = []
    for i in range(0, size, 2):
        matches.append((padded[i], padded[i + 1]))

    return matches


# ── Match Execution ─────────────────────────────────────────────

async def _run_match(
    context, chat_id: int,
    p1_id: int, p1_data: dict,
    p2_id: int, p2_data: dict,
    is_final: bool = False,
    is_semi: bool = False,
    is_quarter: bool = False,
) -> tuple[int, dict]:
    """Run a single match between two players.

    Display modes:
    - is_quarter: log 2 lines at a time (1s delay)
    - is_semi: log 1 line at a time (1.5s delay)
    - is_final: rich turn-by-turn with HP bars (2s delay)

    Returns (winner_user_id, winner_data).
    """
    SKULL = icon_emoji("skull")

    # Prepare combatants
    partner1 = await bq.get_partner(p1_id)
    partner1_id = partner1["instance_id"] if partner1 else None
    team1 = [
        _prepare_combatant(p, is_partner=(p.get("pokemon_instance_id") == partner1_id))
        for p in p1_data["team"]
    ]

    partner2 = await bq.get_partner(p2_id)
    partner2_id = partner2["instance_id"] if partner2 else None
    team2 = [
        _prepare_combatant(p, is_partner=(p.get("pokemon_instance_id") == partner2_id))
        for p in p2_data["team"]
    ]

    # Resolve battle
    result = _resolve_battle(team1, team2)

    if result["winner"] == "challenger":
        winner_id, winner_data = p1_id, p1_data
        remaining = result["challenger_remaining"]
    else:
        winner_id, winner_data = p2_id, p2_data
        remaining = result["defender_remaining"]

    if is_final:
        # ── Finals: rich turn-by-turn display ──
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🏆 결승전!\n"
                f"{p1_data['name']} vs {p2_data['name']}\n"
                f"━━━━━━━━━━━━━━━"
            ),
            parse_mode="HTML",
        )
        await asyncio.sleep(2)

        for td in result["turn_data"]:
            if td["type"] == "matchup":
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"\n⚔ {td['c_tb']}{td['c_name']} vs {td['d_tb']}{td['d_name']}!",
                    parse_mode="HTML",
                )
                await asyncio.sleep(2)

            elif td["type"] == "turn":
                lines = []
                # First attacker
                if td["first_is_challenger"]:
                    first_name, first_dmg, first_crit, first_eff = td["c_name"], td["c_dmg"], td["c_crit"], td["c_eff"]
                    second_name, second_dmg, second_crit, second_eff = td["d_name"], td["d_dmg"], td["d_crit"], td["d_eff"]
                    first_target_hp, first_target_max = td["d_hp"], td["d_max_hp"]
                    second_target_hp, second_target_max = td["c_hp"], td["c_max_hp"]
                    first_target_name, second_target_name = td["d_name"], td["c_name"]
                else:
                    first_name, first_dmg, first_crit, first_eff = td["d_name"], td["d_dmg"], td["d_crit"], td["d_eff"]
                    second_name, second_dmg, second_crit, second_eff = td["c_name"], td["c_dmg"], td["c_crit"], td["c_eff"]
                    first_target_hp, first_target_max = td["c_hp"], td["c_max_hp"]
                    second_target_hp, second_target_max = td["d_hp"], td["d_max_hp"]
                    first_target_name, second_target_name = td["c_name"], td["d_name"]

                # Turn header
                crit_label = " 크리티컬!" if first_crit else ""
                skill_label = f"의{first_eff} 발동!" if first_eff else "의 공격!"
                lines.append(f"{td['turn_num']}턴 ─ {first_name}{skill_label}{crit_label}")
                bar = _hp_bar(first_target_hp, first_target_max)
                lines.append(f"  →{first_dmg} 데미지 ({first_target_name} HP: {bar} {first_target_hp}/{first_target_max})")

                # Second attacker (counterattack)
                if second_dmg > 0:
                    crit2_label = " 크리티컬!" if second_crit else ""
                    skill2_label = f"의{second_eff} 발동!" if second_eff else "의 반격!"
                    lines.append(f"{second_name}{skill2_label}{crit2_label}")
                    bar2 = _hp_bar(second_target_hp, second_target_max)
                    lines.append(f"  ←{second_dmg} 데미지 ({second_target_name} HP: {bar2} {second_target_hp}/{second_target_max})")

                await context.bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode="HTML")
                await asyncio.sleep(2)

            elif td["type"] == "ko":
                if td["next_name"]:
                    text = f"{SKULL} {td['dead_name']} 쓰러짐!\n▶ {td['next_name']} 등장! ({td['next_idx']+1}/{td['next_total']})"
                else:
                    text = f"{SKULL} {td['dead_name']} 쓰러짐!"
                await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
                await asyncio.sleep(1.5)

        # Winner announcement
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"\n🎉 {winner_data['name']} 우승! (남은 {remaining}마리)",
        )

    elif is_semi:
        # ── Semi-finals: 1 line at a time ──
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"⚔️ 준결승! — {p1_data['name']} vs {p2_data['name']}\n"
                f"━━━━━━━━━━━━━━━"
            ),
            parse_mode="HTML",
        )
        await asyncio.sleep(1.5)

        log_lines = result["log"].split("\n")
        for line in log_lines:
            if line.strip():
                await context.bot.send_message(chat_id=chat_id, text=line, parse_mode="HTML")
                await asyncio.sleep(1.5)

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"→ {winner_data['name']} 승리! (남은 {remaining}마리)",
        )

    elif is_quarter:
        # ── Quarter-finals: 2 lines at a time ──
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"⚔️ {p1_data['name']} vs {p2_data['name']}\n"
                f"━━━━━━━━━━━━━━━"
            ),
            parse_mode="HTML",
        )
        await asyncio.sleep(1)

        log_lines = [l for l in result["log"].split("\n") if l.strip()]
        for i in range(0, len(log_lines), 2):
            chunk = "\n".join(log_lines[i:i+2])
            await context.bot.send_message(chat_id=chat_id, text=chunk, parse_mode="HTML")
            await asyncio.sleep(1)

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"→ {winner_data['name']} 승리! (남은 {remaining}마리)",
        )

    else:
        # ── Lower rounds: one-line summary ──
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⚔️ {p1_data['name']} vs {p2_data['name']} → {winner_data['name']} 승리!",
            parse_mode="HTML",
        )

    return winner_id, winner_data


# ── Tournament Execution ────────────────────────────────────────

async def start_tournament(context: ContextTypes.DEFAULT_TYPE):
    """JobQueue callback — 22:00 KST: close registration, run tournament."""
    chat_id = _tournament_state["chat_id"]

    if not _tournament_state["registering"]:
        # Registration wasn't started (no arcade channel configured)
        return

    _tournament_state["registering"] = False
    _tournament_state["running"] = True

    participants = _tournament_state["participants"]
    count = len(participants)

    if count < config.TOURNAMENT_MIN_PLAYERS:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"❌ 참가자 부족으로 대회가 취소되었습니다.\n"
                f"(참가자: {count}명 / 최소: {config.TOURNAMENT_MIN_PLAYERS}명)\n\n"
                "스폰이 재개됩니다."
            ),
        )
        _reset_state()
        await _resume_spawns(context, chat_id)
        return

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"🏟️ 토너먼트 시작!\n"
            f"━━━━━━━━━━━━━━━\n"
            f"참가자: {count}명\n"
            f"방식: 싱글 엘리미네이션\n\n"
            f"대진표를 생성합니다..."
        ),
    )
    await asyncio.sleep(2)

    # Build player list
    player_list = [(uid, data) for uid, data in participants.items()]

    # Generate first round bracket
    bracket = _generate_bracket(player_list)

    # Run rounds
    total_rounds = int(math.log2(len(bracket) * 2))
    current_round = 1
    semi_finalists = set()  # Track 4th place candidates

    try:
        while len(bracket) > 0:
            is_final = (len(bracket) == 1 and bracket[0][0] is not None and bracket[0][1] is not None)
            is_semi = (len(bracket) == 2)
            is_quarter = (len(bracket) <= 4 and not is_semi and not is_final)

            round_name = "결승" if is_final else f"{'준결승' if is_semi else f'{current_round}라운드'}"

            if not is_final:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"\n📢 {round_name}",
                )
                await asyncio.sleep(1)

            winners = []
            for p1, p2 in bracket:
                if p1 is None and p2 is None:
                    continue
                elif p1 is None:
                    # p2 gets bye
                    uid2, data2 = p2
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"🏃 {data2['name']} — 부전승!",
                    )
                    winners.append(p2)
                elif p2 is None:
                    # p1 gets bye
                    uid1, data1 = p1
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"🏃 {data1['name']} — 부전승!",
                    )
                    winners.append(p1)
                else:
                    uid1, data1 = p1
                    uid2, data2 = p2

                    # Track semi-finalists for 4th place prize
                    if is_semi:
                        semi_finalists.add(uid1)
                        semi_finalists.add(uid2)

                    winner_id, winner_data = await _run_match(
                        context, chat_id,
                        uid1, data1, uid2, data2,
                        is_final=is_final,
                        is_semi=is_semi,
                        is_quarter=is_quarter,
                    )
                    winners.append((winner_id, winner_data))
                    await asyncio.sleep(1)

            if is_final:
                # Tournament complete — give prizes
                if winners:
                    winner_uid, winner_d = winners[0]
                    await _award_prizes(context, chat_id, winner_uid, winner_d, bracket, semi_finalists)
                break

            # Next round
            next_bracket = []
            for i in range(0, len(winners), 2):
                if i + 1 < len(winners):
                    next_bracket.append((winners[i], winners[i + 1]))
                else:
                    next_bracket.append((winners[i], None))
            bracket = next_bracket
            current_round += 1
            await asyncio.sleep(2)

    except Exception as e:
        logger.error(f"Tournament error: {e}", exc_info=True)
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ 토너먼트 진행 중 오류가 발생했습니다.",
        )

    # Cleanup
    _reset_state()
    await _resume_spawns(context, chat_id)


async def _award_prizes(context, chat_id, winner_id, winner_data, final_bracket, semi_finalists):
    """Award prizes to top finishers."""
    pool = await get_db()

    # 1st place
    await queries.add_master_ball(winner_id, config.TOURNAMENT_PRIZE_1ST_MB)
    await pool.execute(
        "UPDATE users SET battle_points = battle_points + $1 WHERE user_id = $2",
        config.TOURNAMENT_PRIZE_1ST_BP, winner_id,
    )
    # Track tournament wins for title
    await queries.increment_title_stat(winner_id, "tournament_wins")

    # 2nd place (loser of final)
    runner_up_id = None
    if final_bracket and final_bracket[0]:
        p1, p2 = final_bracket[0]
        if p1 and p2:
            uid1, _ = p1
            uid2, _ = p2
            runner_up_id = uid2 if uid1 == winner_id else uid1
            if runner_up_id:
                await pool.execute(
                    "UPDATE users SET battle_points = battle_points + $1 WHERE user_id = $2",
                    config.TOURNAMENT_PRIZE_2ND_BP, runner_up_id,
                )

    # 4th place (semi-finalists who didn't reach finals)
    finalists = {winner_id}
    if runner_up_id:
        finalists.add(runner_up_id)
    fourth_placers = semi_finalists - finalists
    for uid in fourth_placers:
        await pool.execute(
            "UPDATE users SET battle_points = battle_points + $1 WHERE user_id = $2",
            config.TOURNAMENT_PRIZE_4TH_BP, uid,
        )

    # Check & unlock titles for winner
    from utils.title_checker import check_and_unlock_titles
    new_titles = await check_and_unlock_titles(winner_id)

    # Build prize message
    lines = [
        "\n🏆 토너먼트 결과",
        "━━━━━━━━━━━━━━━",
        f"🥇 {winner_data['name']}",
        f"   {ball_emoji('masterball')} 마스터볼 {config.TOURNAMENT_PRIZE_1ST_MB}개 + {config.TOURNAMENT_PRIZE_1ST_BP} BP",
    ]

    if runner_up_id:
        runner_up_user = await queries.get_user(runner_up_id)
        r_name = runner_up_user["display_name"] if runner_up_user else "???"
        lines.append(f"🥈 {r_name}")
        lines.append(f"   {config.TOURNAMENT_PRIZE_2ND_BP} BP")

    if fourth_placers:
        for uid in fourth_placers:
            u = await queries.get_user(uid)
            u_name = u["display_name"] if u else "???"
            lines.append(f"🏅 {u_name}")
        lines.append(f"   각 {config.TOURNAMENT_PRIZE_4TH_BP} BP")

    # Title unlocks
    if new_titles:
        lines.append("")
        from utils.helpers import icon_emoji
        for _, tname, temoji in new_titles:
            badge = icon_emoji(temoji) if temoji in config.ICON_CUSTOM_EMOJI else temoji
            lines.append(f"🎉 {winner_data['name']}이(가) 「{badge} {tname}」 칭호를 획득!")

    lines.append("\n스폰이 곧 재개됩니다.")

    await context.bot.send_message(
        chat_id=chat_id,
        text="\n".join(lines),
        parse_mode="HTML",
    )


async def _resume_spawns(context, chat_id: int):
    """Resume arcade spawns after tournament ends."""
    from services.spawn_service import schedule_spawns_for_chat
    try:
        count = await context.bot.get_chat_member_count(chat_id)
    except Exception:
        count = 50  # fallback
    await schedule_spawns_for_chat(context.application, chat_id, count)
    logger.info(f"Spawns resumed for chat {chat_id}")
