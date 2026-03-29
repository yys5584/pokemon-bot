"""3/29 대회 — 4명 공동우승 보상 지급 스크립트.

봇 내부에서 실행: 관리자 명령 "공동우승" 으로 트리거.
"""
import asyncio
import random
import logging

import config
from database import queries, battle_queries as bq, item_queries
from database import title_queries
from database.connection import get_db
from utils.helpers import icon_emoji, ball_emoji, shiny_emoji

logger = logging.getLogger(__name__)


# ── 참가자 분류 ──
CO_CHAMPIONS = {
    6007036282: "딸딸기",
    7044819211: "Jun_P3",
    7609021791: "Turri",
    7050637391: "러스트",
}

QUARTER_LOSERS = {
    7285104306: "제리",
    8616523632: "Han",
    5237146711: "무색큐브",
    336224560: "E 🥊FIGHT",
}


def _random_shiny_pokemon(rarity: str):
    from models.pokemon_data import ALL_POKEMON
    candidates = [(p[0], p[1]) for p in ALL_POKEMON if p[4] == rarity]
    return random.choice(candidates)


async def award_co_champions(context):
    """4명 공동우승 + 나머지 보상 지급."""
    chat_id = config.TOURNAMENT_CHAT_ID
    mb_emoji = ball_emoji("masterball")
    se = shiny_emoji()
    pool = await get_db()

    # 전체 참가자 로드
    all_regs = await pool.fetch("SELECT user_id, display_name FROM tournament_registrations")
    all_uids = {r[0] for r in all_regs}
    if not all_uids:
        await context.bot.send_message(chat_id=chat_id, text="⚠️ 등록자가 없습니다!")
        return

    awarded = set()
    champion_results = []  # (uid, name, shiny_name, iv_detail)

    # ── 1. 공동우승 4명: 1등 보상 ──
    for uid, name in CO_CHAMPIONS.items():
        # 마스터볼
        try:
            await queries.add_master_ball(uid, config.TOURNAMENT_PRIZE_1ST_MB)
        except Exception as e:
            logger.error(f"MB fail {uid}: {e}")
        # BP
        try:
            await bq.add_bp(uid, config.TOURNAMENT_PRIZE_1ST_BP, "tournament")
        except Exception as e:
            logger.error(f"BP fail {uid}: {e}")
        # 이로치 초전설
        shiny_id, shiny_name = _random_shiny_pokemon(config.TOURNAMENT_PRIZE_1ST_SHINY)
        shiny_ivs = {}
        try:
            _, shiny_ivs = await queries.give_pokemon_to_user(uid, shiny_id, chat_id, is_shiny=True)
        except Exception as e:
            logger.error(f"Shiny fail {uid}: {e}")
        # IV+3 스톤
        try:
            await item_queries.add_user_item(uid, "iv_stone_3", 1)
            # 검증: 실제로 들어갔는지 확인
            items = await item_queries.get_all_user_items(uid)
            iv_item = [i for i in items if i.get("item_type") == "iv_stone_3"]
            if iv_item:
                logger.info(f"IV stone verified for {uid} ({name}): qty={iv_item[0].get('quantity')}")
            else:
                logger.error(f"IV stone NOT found for {uid} ({name}) after insert!")
        except Exception as e:
            logger.error(f"IV stone fail {uid}: {e}")
        # 챔피언 칭호
        try:
            await title_queries.increment_title_stat(uid, "tournament_wins")
        except Exception as e:
            logger.error(f"Title fail {uid}: {e}")

        # IV 정보 포맷
        iv_detail = ""
        if shiny_ivs:
            from utils.battle_calc import iv_total
            total = iv_total(shiny_ivs["iv_hp"], shiny_ivs["iv_atk"], shiny_ivs["iv_def"],
                            shiny_ivs["iv_spa"], shiny_ivs["iv_spdef"], shiny_ivs["iv_spd"])
            grade, _ = config.get_iv_grade(total)
            iv_detail = (
                f"IV: {shiny_ivs['iv_hp']}/{shiny_ivs['iv_atk']}/{shiny_ivs['iv_def']}"
                f"/{shiny_ivs['iv_spa']}/{shiny_ivs['iv_spdef']}/{shiny_ivs['iv_spd']}"
                f" ({total}/186) [{grade}]"
            )

        champion_results.append((uid, name, shiny_name, iv_detail))
        awarded.add(uid)

    # ── 2. 8강 탈락 ──
    for uid, name in QUARTER_LOSERS.items():
        if uid in awarded:
            continue
        try:
            await queries.add_master_ball(uid, config.TOURNAMENT_PRIZE_QUARTER_MB)
        except Exception as e:
            logger.error(f"8강 MB fail {uid}: {e}")
        try:
            await bq.add_bp(uid, config.TOURNAMENT_PRIZE_QUARTER_BP, "tournament")
        except Exception as e:
            logger.error(f"8강 BP fail {uid}: {e}")
        awarded.add(uid)

    # ── 3. 참가 보상 (나머지) ──
    participant_only = all_uids - awarded
    for uid in participant_only:
        try:
            await queries.add_master_ball(uid, config.TOURNAMENT_PRIZE_PARTICIPANT_MB)
        except Exception as e:
            logger.error(f"참가 MB fail {uid}: {e}")
        try:
            await bq.add_bp(uid, config.TOURNAMENT_PRIZE_PARTICIPANT_BP, "tournament")
        except Exception as e:
            logger.error(f"참가 BP fail {uid}: {e}")

    # ── 4. 대회방 공지 ──
    _champ = icon_emoji("champion_first")
    _crown = icon_emoji("crown")
    _coin = icon_emoji("coin")
    _battle = icon_emoji("battle")
    _check = icon_emoji("check")

    lines = [
        f"\n{_champ} 토너먼트 결과 (공동 우승)",
        "━━━━━━━━━━━━━━━",
    ]
    for uid, name, shiny_name, iv_detail in champion_results:
        lines.append(f"{_crown} {name}")
        lines.append(f"   {mb_emoji}×{config.TOURNAMENT_PRIZE_1ST_MB} + {_coin}{config.TOURNAMENT_PRIZE_1ST_BP:,}BP + {se}{shiny_name}(이로치) + IV+3 ×1")

    if QUARTER_LOSERS:
        q_names = ", ".join(QUARTER_LOSERS.values())
        lines.append(f"\n{_battle} 8강 ({len(QUARTER_LOSERS)}명): {q_names}")
        lines.append(f"   {mb_emoji}×{config.TOURNAMENT_PRIZE_QUARTER_MB} + {_coin}{config.TOURNAMENT_PRIZE_QUARTER_BP:,}BP")

    lines.append(f"\n{_check} 참가 보상 ({len(participant_only)}명)")
    lines.append(f"   {mb_emoji}×{config.TOURNAMENT_PRIZE_PARTICIPANT_MB} + {_coin}{config.TOURNAMENT_PRIZE_PARTICIPANT_BP:,}BP")

    lines.append("\n스폰이 곧 재개됩니다.")

    await context.bot.send_message(
        chat_id=chat_id,
        text="\n".join(lines),
        parse_mode="HTML",
    )

    # ── 5. DM 발송 ──
    # 공동 우승자 DM
    for uid, name, shiny_name, iv_detail in champion_results:
        rarity_label = config.RARITY_LABEL.get(config.TOURNAMENT_PRIZE_1ST_SHINY, "초전설")
        dm = (
            f"{_champ} 토너먼트 공동 우승을 축하합니다!\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"{mb_emoji} 마스터볼 {config.TOURNAMENT_PRIZE_1ST_MB}개 지급!\n"
            f"{_coin} {config.TOURNAMENT_PRIZE_1ST_BP:,}BP 지급!\n"
            f"{icon_emoji('champion')} 챔피언 칭호 획득!\n\n"
            f"{se} {shiny_name} (이로치 · {rarity_label})\n"
        )
        if iv_detail:
            dm += f"{iv_detail}\n"
        dm += f"\n🧪 IV+3 스톤 ×1 지급! ('아이템' 입력으로 확인)"
        try:
            await context.bot.send_message(chat_id=uid, text=dm, parse_mode="HTML")
        except Exception:
            logger.warning(f"DM fail champion {uid}")

    # 8강 탈락 DM
    for uid, name in QUARTER_LOSERS.items():
        dm = (
            f"{_battle} 토너먼트 8강에서 아쉽게 탈락했습니다!\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"{mb_emoji} 마스터볼 {config.TOURNAMENT_PRIZE_QUARTER_MB}개 지급!\n"
            f"{_coin} {config.TOURNAMENT_PRIZE_QUARTER_BP:,}BP 지급!\n\n"
            "다음엔 4강을 노려보세요!"
        )
        try:
            await context.bot.send_message(chat_id=uid, text=dm, parse_mode="HTML")
        except Exception:
            logger.warning(f"DM fail quarter {uid}")

    # 참가 보상 DM
    for uid in participant_only:
        dm = (
            f"{_check} 토너먼트 참가 보상!\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"{mb_emoji} 마스터볼 {config.TOURNAMENT_PRIZE_PARTICIPANT_MB}개 지급!\n"
            f"{_coin} {config.TOURNAMENT_PRIZE_PARTICIPANT_BP:,}BP 지급!\n\n"
            "다음 대회도 기대해 주세요!"
        )
        try:
            await context.bot.send_message(chat_id=uid, text=dm, parse_mode="HTML")
        except Exception:
            logger.warning(f"DM fail participant {uid}")

    # ── 6. 등록 테이블 정리 ──
    try:
        await pool.execute("DELETE FROM tournament_registrations")
    except Exception:
        logger.error("Failed to clear tournament_registrations")

    # 스폰 재개
    from services.tournament_prizes import _resume_spawns
    await _resume_spawns(context, chat_id)

    logger.info(f"Co-champion awards complete: {len(champion_results)} champions, "
                f"{len(QUARTER_LOSERS)} quarter, {len(participant_only)} participants")
