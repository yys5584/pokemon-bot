"""Tournament prizes, group stage, bracket generation, and spawn resume."""

import asyncio
import random
import logging

import config

from database import queries, title_queries
from database import battle_queries as bq
from database.connection import get_db
from services.tournament_render import _safe_send
from services.tournament_match import _run_match
from utils.helpers import icon_emoji, ball_emoji, shiny_emoji

logger = logging.getLogger(__name__)


# ── Preliminary Round (for excess players) ────────────────────

async def _run_preliminary_round(context, chat_id: int, players: list, target: int) -> list:
    """Run preliminary matches to reduce players to target size.

    Only the excess players (total - target) need to be eliminated.
    excess*2 players fight in preliminary matches, the rest get byes.

    Args:
        players: list of (uid, data) tuples
        target: power of 2 to reduce to (e.g. 16, 8, 4)
    Returns:
        list of target (uid, data) tuples for the main bracket
    """
    random.shuffle(players)
    excess = len(players) - target  # number of players to eliminate

    # First excess*2 players play prelims, rest get seeded directly
    prelim_players = players[:excess * 2]
    seeded_players = players[excess * 2:]

    # Build prelim match pairs
    matches = []
    for i in range(0, len(prelim_players), 2):
        matches.append((prelim_players[i], prelim_players[i + 1]))

    lines = [f"🏟 예선전 ({len(matches)}경기)"]

    prelim_winners = []
    for mi, (p1, p2) in enumerate(matches):
        winner_id, winner_data = await _run_match(
            context, chat_id,
            p1[0], p1[1], p2[0], p2[1],
            is_final=False, is_semi=False, is_quarter=False,
        )
        winner_name = winner_data["name"]
        mark = f"{mi + 1}."
        lines.append(f"{mark} {p1[1]['name']} vs {p2[1]['name']} → {winner_name} 승리 ✓")

        winner_tuple = (p1[0], p1[1]) if winner_id == p1[0] else (p2[0], p2[1])
        prelim_winners.append(winner_tuple)

    await _safe_send(context.bot, chat_id, text="\n".join(lines))
    await asyncio.sleep(3)

    # Combine: prelim winners + seeded players = 16
    return prelim_winners + seeded_players


# ── Group Stage (for 33+ players → 4 groups, 17+ → 2 groups) ──

GROUP_LABELS = ["A", "B", "C", "D"]


async def _run_group_stage(context, chat_id: int, players: list, num_groups: int) -> list:
    """Run group stage: divide into groups, run single-elimination per group.

    Returns list of (uid, data) tuples — top 2 from each group.
    """
    random.shuffle(players)
    groups = [[] for _ in range(num_groups)]
    for i, p in enumerate(players):
        groups[i % num_groups].append(p)

    # Announce groups
    lines = [
        f"🏟️ 그룹 스테이지 시작!",
        f"━━━━━━━━━━━━━━━",
        f"참가자: {len(players)}명 → {num_groups}그룹",
        "",
    ]
    for gi, group in enumerate(groups):
        label = GROUP_LABELS[gi]
        names = ", ".join(p[1]["name"] for p in group)
        lines.append(f"🔹 {label}조 ({len(group)}명): {names}")
    await _safe_send(context.bot, chat_id, text="\n".join(lines))
    await asyncio.sleep(5)

    # Run each group
    all_qualifiers = []  # (uid, data, group_label, place)

    for gi, group in enumerate(groups):
        label = GROUP_LABELS[gi]
        await _safe_send(context.bot, chat_id,
            text=f"\n🔷 {label}조 토너먼트 시작! ({len(group)}명)",
        )
        await asyncio.sleep(2)

        bracket = _generate_bracket(group)

        # Run single-elimination within group
        current_round = 1
        runner_up_id = None  # Track the player who lost in the final

        while len(bracket) > 0:
            is_group_final = (len(bracket) == 1 and bracket[0][0] is not None and bracket[0][1] is not None)
            round_size = len(bracket) * 2

            winners = []
            match_num = 0
            match_count = sum(1 for a, b in bracket if a is not None or b is not None)

            for p1, p2 in bracket:
                if p1 is None and p2 is None:
                    continue
                match_num += 1
                match_label = f"[{label}조 {match_num}/{match_count}] " if not is_group_final else f"[{label}조 결승] "

                if p1 is None:
                    await _safe_send(context.bot, chat_id,
                        text=f"{match_label}🏃 {p2[1]['name']} — 부전승!")
                    winners.append(p2)
                    await asyncio.sleep(1)
                elif p2 is None:
                    await _safe_send(context.bot, chat_id,
                        text=f"{match_label}🏃 {p1[1]['name']} — 부전승!")
                    winners.append(p1)
                    await asyncio.sleep(1)
                else:
                    winner_id, winner_data = await _run_match(
                        context, chat_id,
                        p1[0], p1[1], p2[0], p2[1],
                        is_final=False,
                        is_semi=False,
                        is_quarter=is_group_final,  # Show some detail for group finals
                        match_label=match_label,
                    )
                    winners.append((winner_id, winner_data))

                    # Track runner-up in group final
                    if is_group_final:
                        loser = p1 if winner_id != p1[0] else p2
                        runner_up_id = loser[0]
                        all_qualifiers.append((*loser, label, 2))

                    await asyncio.sleep(2)

            if is_group_final and winners:
                winner_tuple = winners[0]
                all_qualifiers.append((*winner_tuple, label, 1))
                await _safe_send(context.bot, chat_id,
                    text=f"🏆 {label}조 우승: {winner_tuple[1]['name']}!")
                await asyncio.sleep(3)
                break

            # Build next round bracket
            next_bracket = []
            for i in range(0, len(winners), 2):
                if i + 1 < len(winners):
                    next_bracket.append((winners[i], winners[i + 1]))
                else:
                    next_bracket.append((winners[i], None))

            bracket = next_bracket
            current_round += 1

    # Summary of qualifiers
    qualifier_tuples = [(uid, data) for uid, data, _, _ in all_qualifiers]
    lines = [
        f"\n🏆 본선 진출자 ({len(qualifier_tuples)}명)",
        "━━━━━━━━━━━━━━━",
    ]
    for uid, data, label, place in all_qualifiers:
        rank = "👑" if place == 1 else "🥈"
        lines.append(f"{rank} {label}조 {place}위: {data['name']}")
    await _safe_send(context.bot, chat_id, text="\n".join(lines))
    await asyncio.sleep(5)

    # Cross-match: A1 vs B2, B1 vs A2, C1 vs D2, D1 vs C2 (for 4 groups)
    # For 2 groups: A1 vs B2, B1 vs A2
    seeded = []
    if num_groups == 4:
        # Group winners vs other group's runners-up (cross-seed)
        g = {label: {} for label in GROUP_LABELS[:num_groups]}
        for uid, data, label, place in all_qualifiers:
            g[label][place] = (uid, data)
        seeded = [
            (g["A"][1], g["B"][2]),
            (g["C"][1], g["D"][2]),
            (g["B"][1], g["A"][2]),
            (g["D"][1], g["C"][2]),
        ]
    elif num_groups == 2:
        g = {"A": {}, "B": {}}
        for uid, data, label, place in all_qualifiers:
            g[label][place] = (uid, data)
        seeded = [
            (g["A"][1], g["B"][2]),
            (g["B"][1], g["A"][2]),
        ]

    return seeded


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


# ── Random Shiny Pokemon ──────────────────────────────────────

def _random_shiny_pokemon(rarity: str) -> tuple[int, str]:
    """Pick a random pokemon of the given rarity. Returns (pokemon_id, name_ko)."""
    from models.pokemon_data import ALL_POKEMON
    candidates = [(p[0], p[1]) for p in ALL_POKEMON if p[4] == rarity]
    return random.choice(candidates)


# ── Prize Awards ──────────────────────────────────────────────

async def _award_prizes(context, chat_id, winner_id, winner_data,
                        final_bracket, semi_finalists, all_participants,
                        eliminated=None):
    """Award prizes to top finishers + participation rewards.

    eliminated: dict mapping user_id -> round_size (16, 8, 4, 2) where they lost.
    """
    from utils.battle_calc import iv_total
    if eliminated is None:
        eliminated = {}

    mb_emoji = ball_emoji('masterball')

    # ── 1st place: master balls + BP + shiny legendary + shiny common + title ──
    try:
        await queries.add_master_ball(winner_id, config.TOURNAMENT_PRIZE_1ST_MB)
    except Exception:
        logger.error(f"Failed to give master balls to winner {winner_id}")
    try:
        await bq.add_bp(winner_id, config.TOURNAMENT_PRIZE_1ST_BP, "tournament")
    except Exception:
        logger.error(f"Failed to give BP to winner {winner_id}")
    await title_queries.increment_title_stat(winner_id, "tournament_wins")
    shiny_1st_id, shiny_1st_name = _random_shiny_pokemon(config.TOURNAMENT_PRIZE_1ST_SHINY)
    shiny_1st_ivs = {}
    try:
        _, shiny_1st_ivs = await queries.give_pokemon_to_user(winner_id, shiny_1st_id, chat_id, is_shiny=True)
    except Exception:
        logger.error(f"Failed to give shiny pokemon to winner {winner_id}")
    # Bonus: shiny common
    bonus_1st_id, bonus_1st_name = _random_shiny_pokemon("common")
    bonus_1st_ivs = {}
    try:
        _, bonus_1st_ivs = await queries.give_pokemon_to_user(winner_id, bonus_1st_id, chat_id, is_shiny=True)
    except Exception:
        logger.error(f"Failed to give bonus shiny common to winner {winner_id}")

    # ── 2nd place (runner-up) ──
    runner_up_id = None
    if final_bracket and final_bracket[0]:
        p1, p2 = final_bracket[0]
        if p1 and p2:
            uid1, _ = p1
            uid2, _ = p2
            runner_up_id = uid2 if uid1 == winner_id else uid1

    # ── 2nd place (runner-up): master balls + shiny legendary + shiny common ──
    shiny_2nd_name = ""
    shiny_2nd_ivs = {}
    bonus_2nd_name = ""
    bonus_2nd_ivs = {}
    if runner_up_id:
        try:
            await queries.add_master_ball(runner_up_id, config.TOURNAMENT_PRIZE_2ND_MB)
        except Exception:
            logger.error(f"Failed to give master balls to runner-up {runner_up_id}")
        try:
            await bq.add_bp(runner_up_id, config.TOURNAMENT_PRIZE_2ND_BP, "tournament")
        except Exception:
            logger.error(f"Failed to give BP to runner-up {runner_up_id}")
        s2_id, s2_name = _random_shiny_pokemon(config.TOURNAMENT_PRIZE_2ND_SHINY)
        try:
            _, shiny_2nd_ivs = await queries.give_pokemon_to_user(runner_up_id, s2_id, chat_id, is_shiny=True)
        except Exception:
            logger.error(f"Failed to give shiny pokemon to runner-up {runner_up_id}")
        shiny_2nd_name = s2_name
        # Bonus: shiny common
        b2_id, b2_name = _random_shiny_pokemon("common")
        try:
            _, bonus_2nd_ivs = await queries.give_pokemon_to_user(runner_up_id, b2_id, chat_id, is_shiny=True)
        except Exception:
            logger.error(f"Failed to give bonus shiny common to runner-up {runner_up_id}")
        bonus_2nd_name = b2_name

    # ── Semi-finalists (4강): master balls + shiny epic ──
    finalists = {winner_id}
    if runner_up_id:
        finalists.add(runner_up_id)
    semi_all = semi_finalists | finalists
    semi_reward_targets = semi_all - finalists  # 4강 중 우승/준우승 제외
    shiny_semi_awards = {}  # uid -> (pokemon_name, ivs)
    for uid in semi_reward_targets:
        try:
            await queries.add_master_ball(uid, config.TOURNAMENT_PRIZE_SEMI_MB)
        except Exception:
            logger.error(f"Failed to give master balls to semi-finalist {uid}")
        try:
            await bq.add_bp(uid, config.TOURNAMENT_PRIZE_SEMI_BP, "tournament")
        except Exception:
            logger.error(f"Failed to give BP to semi-finalist {uid}")
        s_id, s_name = _random_shiny_pokemon(config.TOURNAMENT_PRIZE_SEMI_SHINY)
        try:
            _, s_ivs = await queries.give_pokemon_to_user(uid, s_id, chat_id, is_shiny=True)
        except Exception:
            logger.error(f"Failed to give shiny pokemon to semi-finalist {uid}")
            s_ivs = {}
        shiny_semi_awards[uid] = (s_name, s_ivs)

    # ── 8강 탈락: master balls ──
    already_rewarded = {winner_id} | semi_reward_targets
    quarter_losers = {uid for uid, rnd in eliminated.items() if rnd == 8} - already_rewarded
    for uid in quarter_losers:
        try:
            await queries.add_master_ball(uid, config.TOURNAMENT_PRIZE_QUARTER_MB)
        except Exception:
            logger.error(f"Failed to give master ball to quarter-finalist {uid}")
        try:
            await bq.add_bp(uid, config.TOURNAMENT_PRIZE_QUARTER_BP, "tournament")
        except Exception:
            logger.error(f"Failed to give BP to quarter-finalist {uid}")
    already_rewarded |= quarter_losers

    # ── 16강 탈락: master balls ──
    r16_losers = {uid for uid, rnd in eliminated.items() if rnd == 16} - already_rewarded
    for uid in r16_losers:
        try:
            await queries.add_master_ball(uid, config.TOURNAMENT_PRIZE_R16_MB)
        except Exception:
            logger.error(f"Failed to give master ball to R16 participant {uid}")
        try:
            await bq.add_bp(uid, config.TOURNAMENT_PRIZE_R16_BP, "tournament")
        except Exception:
            logger.error(f"Failed to give BP to R16 participant {uid}")
    already_rewarded |= r16_losers

    # ── Participation reward: master ball + BP for the rest ──
    participant_only = all_participants - already_rewarded
    for uid in participant_only:
        try:
            await queries.add_master_ball(uid, config.TOURNAMENT_PRIZE_PARTICIPANT_MB)
        except Exception:
            logger.error(f"Failed to give master ball to participant {uid}")
        try:
            await bq.add_bp(uid, config.TOURNAMENT_PRIZE_PARTICIPANT_BP, "tournament")
        except Exception:
            logger.error(f"Failed to give BP to participant {uid}")

    # Check & unlock titles for winner
    from utils.title_checker import check_and_unlock_titles
    new_titles = await check_and_unlock_titles(winner_id)

    # ── Helper: format IV detail for DM ──
    def _iv_detail(name: str, rarity: str, ivs: dict) -> str:
        if not ivs:
            rarity_label = config.RARITY_LABEL.get(rarity, rarity)
            return f"✨ {name} (이로치 · {rarity_label})"
        total = iv_total(ivs["iv_hp"], ivs["iv_atk"], ivs["iv_def"],
                         ivs["iv_spa"], ivs["iv_spdef"], ivs["iv_spd"])
        grade, _ = config.get_iv_grade(total)
        rarity_label = config.RARITY_LABEL.get(rarity, rarity)
        return (
            f"✨ {name} (이로치 · {rarity_label})\n"
            f"IV: {ivs['iv_hp']}/{ivs['iv_atk']}/{ivs['iv_def']}"
            f"/{ivs['iv_spa']}/{ivs['iv_spdef']}/{ivs['iv_spd']}"
            f" ({total}/186) [{grade}]"
        )

    # ── Build prize message (group chat) ──
    lines = [
        "\n🏆 토너먼트 결과",
        "━━━━━━━━━━━━━━━",
        f"🥇 {winner_data['name']}",
        f"   {mb_emoji} 마스터볼 {config.TOURNAMENT_PRIZE_1ST_MB}개 + 💰{config.TOURNAMENT_PRIZE_1ST_BP:,}BP + ✨이로치 {shiny_1st_name} + ✨이로치 {bonus_1st_name} + 🎖️ 챔피언 칭호",
    ]

    if runner_up_id:
        runner_up_user = await queries.get_user(runner_up_id)
        r_name = runner_up_user["display_name"] if runner_up_user else "???"
        lines.append(f"🥈 {r_name}")
        lines.append(f"   {mb_emoji} 마스터볼 {config.TOURNAMENT_PRIZE_2ND_MB}개 + 💰{config.TOURNAMENT_PRIZE_2ND_BP:,}BP + ✨이로치 {shiny_2nd_name} + ✨이로치 {bonus_2nd_name}")

    fourth_placers = semi_reward_targets
    if fourth_placers:
        for uid in fourth_placers:
            u = await queries.get_user(uid)
            u_name = u["display_name"] if u else "???"
            u_shiny_name = shiny_semi_awards.get(uid, ("???", {}))[0]
            lines.append(f"🏅 {u_name} (4강)")
            lines.append(f"   {mb_emoji} 마스터볼 {config.TOURNAMENT_PRIZE_SEMI_MB}개 + 💰{config.TOURNAMENT_PRIZE_SEMI_BP:,}BP + ✨이로치 {u_shiny_name}")

    if quarter_losers:
        q_names = []
        for uid in quarter_losers:
            u = await queries.get_user(uid)
            q_names.append(u["display_name"] if u else "???")
        lines.append(f"\n⚔️ 8강 ({len(quarter_losers)}명): {', '.join(q_names)}")
        lines.append(f"   {mb_emoji} 마스터볼 {config.TOURNAMENT_PRIZE_QUARTER_MB}개 + 💰{config.TOURNAMENT_PRIZE_QUARTER_BP:,}BP")

    if r16_losers:
        lines.append(f"\n🎯 16강 탈락 ({len(r16_losers)}명)")
        lines.append(f"   {mb_emoji} 마스터볼 {config.TOURNAMENT_PRIZE_R16_MB}개 + 💰{config.TOURNAMENT_PRIZE_R16_BP:,}BP")

    if participant_only:
        lines.append(f"\n🎟️ 참가 보상 ({len(participant_only)}명)")
        lines.append(f"   {mb_emoji} 마스터볼 {config.TOURNAMENT_PRIZE_PARTICIPANT_MB}개 + 💰{config.TOURNAMENT_PRIZE_PARTICIPANT_BP:,}BP")

    # Title unlocks
    if new_titles:
        lines.append("")
        for _, tname, temoji in new_titles:
            badge = icon_emoji(temoji) if temoji in config.ICON_CUSTOM_EMOJI else temoji
            lines.append(f"🎉 {winner_data['name']}이(가) 「{badge} {tname}」 칭호를 획득!")

    lines.append("\n스폰이 곧 재개됩니다.")

    await _safe_send(context.bot, chat_id,
        text="\n".join(lines),
        parse_mode="HTML",
    )

    # ── Champion card image ──
    try:
        winner_team = await bq.get_battle_team(winner_id)
        if winner_team:
            from utils.card_generator import generate_champion_card
            team_data = [
                {
                    "pokemon_id": p["pokemon_id"],
                    "name": p["name_ko"],
                    "rarity": p["rarity"],
                    "is_shiny": bool(p.get("is_shiny")),
                }
                for p in winner_team
            ]
            champion_img = generate_champion_card(winner_data["name"], team_data)
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=champion_img,
                caption=f"🏆 {winner_data['name']}의 우승 팀",
            )
    except Exception:
        logger.error(f"Failed to send champion card for {winner_id}", exc_info=True)

    # ── Send DMs with detailed prize info ──
    # Winner DM
    winner_dm = (
        "🏆 토너먼트 우승을 축하합니다!\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"{mb_emoji} 마스터볼 {config.TOURNAMENT_PRIZE_1ST_MB}개 지급!\n"
        f"💰 {config.TOURNAMENT_PRIZE_1ST_BP:,}BP 지급!\n"
        f"🎖️ 챔피언 칭호 획득!\n\n"
        f"{_iv_detail(shiny_1st_name, config.TOURNAMENT_PRIZE_1ST_SHINY, shiny_1st_ivs)}\n\n"
        f"{_iv_detail(bonus_1st_name, 'common', bonus_1st_ivs)}"
    )
    if new_titles:
        for _, tname, temoji in new_titles:
            badge = icon_emoji(temoji) if temoji in config.ICON_CUSTOM_EMOJI else temoji
            winner_dm += f"\n\n🎉 「{badge} {tname}」 칭호를 획득!"
    try:
        await context.bot.send_message(chat_id=winner_id, text=winner_dm, parse_mode="HTML")
    except Exception:
        logger.warning(f"Failed to DM winner {winner_id}")

    # Runner-up DM
    if runner_up_id:
        dm_text = (
            "🥈 토너먼트 준우승을 축하합니다!\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"{mb_emoji} 마스터볼 {config.TOURNAMENT_PRIZE_2ND_MB}개 지급!\n"
            f"💰 {config.TOURNAMENT_PRIZE_2ND_BP:,}BP 지급!\n\n"
            f"{_iv_detail(shiny_2nd_name, config.TOURNAMENT_PRIZE_2ND_SHINY, shiny_2nd_ivs)}\n\n"
            f"{_iv_detail(bonus_2nd_name, 'common', bonus_2nd_ivs)}"
        )
        try:
            await context.bot.send_message(chat_id=runner_up_id, text=dm_text, parse_mode="HTML")
        except Exception:
            logger.warning(f"Failed to DM runner-up {runner_up_id}")

    # Semi-finalist DMs (4강)
    for uid, (s_name, s_ivs) in shiny_semi_awards.items():
        dm_text = (
            "🏅 토너먼트 4강을 축하합니다!\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"{mb_emoji} 마스터볼 {config.TOURNAMENT_PRIZE_SEMI_MB}개 지급!\n"
            f"💰 {config.TOURNAMENT_PRIZE_SEMI_BP:,}BP 지급!\n\n"
            f"{_iv_detail(s_name, config.TOURNAMENT_PRIZE_SEMI_SHINY, s_ivs)}"
        )
        try:
            await context.bot.send_message(chat_id=uid, text=dm_text, parse_mode="HTML")
        except Exception:
            logger.warning(f"Failed to DM semi-finalist {uid}")

    # 8강 탈락 DMs
    for uid in quarter_losers:
        dm_text = (
            "⚔️ 토너먼트 8강에서 아쉽게 탈락했습니다!\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"{mb_emoji} 마스터볼 {config.TOURNAMENT_PRIZE_QUARTER_MB}개 지급!\n"
            f"💰 {config.TOURNAMENT_PRIZE_QUARTER_BP:,}BP 지급!\n\n"
            "다음엔 4강을 노려보세요! 💪"
        )
        try:
            await context.bot.send_message(chat_id=uid, text=dm_text, parse_mode="HTML")
        except Exception:
            logger.warning(f"Failed to DM quarter-finalist {uid}")

    # 16강 탈락 DMs
    for uid in r16_losers:
        dm_text = (
            "🎯 토너먼트 16강에서 탈락했습니다!\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"{mb_emoji} 마스터볼 {config.TOURNAMENT_PRIZE_R16_MB}개 지급!\n"
            f"💰 {config.TOURNAMENT_PRIZE_R16_BP:,}BP 지급!\n\n"
            "다음엔 8강을 노려보세요! 💪"
        )
        try:
            await context.bot.send_message(chat_id=uid, text=dm_text, parse_mode="HTML")
        except Exception:
            logger.warning(f"Failed to DM R16 participant {uid}")

    # Participant DMs (earlier rounds or no matches)
    for uid in participant_only:
        dm_text = (
            "🎟️ 토너먼트 참가 보상!\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"{mb_emoji} 마스터볼 {config.TOURNAMENT_PRIZE_PARTICIPANT_MB}개 지급!\n"
            f"💰 {config.TOURNAMENT_PRIZE_PARTICIPANT_BP:,}BP 지급!\n\n"
            "다음 대회도 기대해 주세요!"
        )
        try:
            await context.bot.send_message(chat_id=uid, text=dm_text, parse_mode="HTML")
        except Exception:
            logger.warning(f"Failed to DM participant {uid}")

    # ── Save tournament results to DB ──
    try:
        pool = await get_db()
        tourn_id = await pool.fetchval(
            "INSERT INTO tournament_results (chat_id, total_participants) "
            "VALUES ($1, $2) RETURNING id",
            chat_id, len(all_participants),
        )

        # placement 결정
        placements = {}
        placements[winner_id] = "1st"
        if runner_up_id:
            placements[runner_up_id] = "2nd"
        for uid in (semi_finalists or set()):
            if uid not in placements:
                placements[uid] = "4th"
        for uid in eliminated:
            if uid not in placements:
                round_size = eliminated[uid]
                placements[uid] = f"top{round_size}"

        for uid, pdata in all_participants.items():
            placement = placements.get(uid, "participant")
            team_json = None
            if isinstance(pdata, dict) and "team" in pdata:
                import json
                team_json = json.dumps(
                    [{"pokemon_id": p.get("pokemon_id"), "name": p.get("name_ko", ""),
                      "rarity": p.get("rarity", ""), "is_shiny": bool(p.get("is_shiny"))}
                     for p in pdata["team"]],
                    ensure_ascii=False,
                )
            display = pdata["name"] if isinstance(pdata, dict) else str(pdata)
            await pool.execute(
                "INSERT INTO tournament_entries "
                "(tournament_id, user_id, display_name, placement, team_json) "
                "VALUES ($1, $2, $3, $4, $5::jsonb)",
                tourn_id, uid, display, placement, team_json,
            )
        logger.info(f"Tournament #{tourn_id} saved: {len(all_participants)} entries")
    except Exception:
        logger.error("Failed to save tournament results to DB", exc_info=True)

    # ── Post tournament result to homepage notice board ──
    try:
        now = config.get_kst_now()
        today = f"{now.month}/{now.day}"
        notice_title = f"{today} 토너먼트 결과"

        # Build notice content (HTML for dashboard)
        w_name = winner_data['name']
        notice_lines = [
            f"🥇 우승: <b>{w_name}</b>",
            f"   마스터볼 {config.TOURNAMENT_PRIZE_1ST_MB}개 + {config.TOURNAMENT_PRIZE_1ST_BP:,}BP + ✨이로치 {shiny_1st_name}",
        ]
        if runner_up_id:
            r_user = await queries.get_user(runner_up_id)
            r_name = r_user["display_name"] if r_user else "???"
            notice_lines.append(f"🥈 준우승: <b>{r_name}</b>")
            notice_lines.append(f"   마스터볼 {config.TOURNAMENT_PRIZE_2ND_MB}개 + {config.TOURNAMENT_PRIZE_2ND_BP:,}BP + ✨이로치 {shiny_2nd_name}")
        for uid in fourth_placers:
            u = await queries.get_user(uid)
            u_name = u["display_name"] if u else "???"
            u_shiny = shiny_semi_awards.get(uid, ("???", {}))[0]
            notice_lines.append(f"🏅 4강: <b>{u_name}</b>")
            notice_lines.append(f"   마스터볼 {config.TOURNAMENT_PRIZE_SEMI_MB}개 + {config.TOURNAMENT_PRIZE_SEMI_BP:,}BP + ✨이로치 {u_shiny}")

        if quarter_losers:
            q_names = []
            for uid in quarter_losers:
                u = await queries.get_user(uid)
                q_names.append(u["display_name"] if u else "???")
            notice_lines.append(f"\n⚔️ 8강: {', '.join(q_names)}")

        if r16_losers:
            r16_names = []
            for uid in r16_losers:
                u = await queries.get_user(uid)
                r16_names.append(u["display_name"] if u else "???")
            notice_lines.append(f"🎯 16강: {', '.join(r16_names)}")

        if participant_only:
            p_names = []
            for uid in participant_only:
                u = await queries.get_user(uid)
                p_names.append(u["display_name"] if u else "???")
            notice_lines.append(f"🎟️ 참가: {', '.join(p_names)}")

        notice_lines.append(f"\n참가자 {len(all_participants)}명, 수고하셨습니다!")
        notice_content = "\n".join(notice_lines)

        pool = await get_db()
        await pool.execute(
            "INSERT INTO board_posts (board_type, user_id, display_name, title, content) "
            "VALUES ($1, $2, $3, $4, $5)",
            "notice", 1832746512, "TG포켓", notice_title, notice_content,
        )
        logger.info(f"Tournament result posted to notice board: {notice_title}")
    except Exception:
        logger.error("Failed to post tournament result to notice board", exc_info=True)


async def _resume_spawns(context, chat_id: int):
    """Resume arcade spawns after tournament ends."""
    from services.spawn_service import schedule_spawns_for_chat
    try:
        count = await context.bot.get_chat_member_count(chat_id)
    except Exception:
        count = 50  # fallback
    await schedule_spawns_for_chat(context.application, chat_id, count)
    logger.info(f"Spawns resumed for chat {chat_id}")
