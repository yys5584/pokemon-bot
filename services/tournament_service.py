"""Tournament system: daily single-elimination in arcade channels.

This module is the coordinator — it holds state, registration, and the main
tournament orchestrator.  Match execution, rendering, prizes, and bracket
generation live in sub-modules:

    tournament_render.py  — bracket display, switch-in lines, MVP, safe send
    tournament_match.py   — match execution, GIF round building
    tournament_prizes.py  — prizes, group stage, bracket generation
"""

import asyncio
import math
import os
import logging

from telegram.ext import ContextTypes

import config

from database import queries
from database import battle_queries as bq
from database.connection import get_db
from utils.helpers import icon_emoji, ball_emoji, shiny_emoji

# ── Sub-module imports (used by this orchestrator) ──
from services.tournament_render import (
    _render_bracket, _safe_send,
)
from services.tournament_match import _run_match, _build_gif_rounds
from services.tournament_prizes import (
    _run_preliminary_round, _run_group_stage, _generate_bracket,
    _random_shiny_pokemon, _award_prizes, _resume_spawns,
)

# ── Re-exports for backward compatibility ──
# These names are imported by other modules via
#   from services.tournament_service import ...
from services.tournament_render import (  # noqa: F811
    _strip_emoji, _dw, _rpad, _trunc, _render_bracket,
    _get_mvp_name, _winner_speech, _switch_line, _extract_mvp,
    _safe_send, _split_send, _safe_send_photo,
)
from services.tournament_match import (  # noqa: F811
    _make_round_comment, _build_gif_rounds, _matchup_to_round, _run_match,
)
from services.tournament_prizes import (  # noqa: F811
    _run_preliminary_round, GROUP_LABELS, _run_group_stage,
    _generate_bracket, _random_shiny_pokemon, _award_prizes, _resume_spawns,
)


logger = logging.getLogger(__name__)

# ── In-memory tournament state ──────────────────────────────────
_tournament_state = {
    "registering": False,
    "running": False,
    "participants": {},       # {user_id: {"name": str, "team": list[dict]}}
    "chat_id": None,
    "mock": False,            # 모의대회: 보상 없음
    "random_1v1": False,      # 이벤트 모드: 랜덤 1마리 토너먼트
}


_REGISTRATION_MILESTONES = {4, 8, 12, 16, 24, 32}


def _round_label_for_size(size: int) -> str:
    return {16: "16강", 8: "8강", 4: "4강", 2: "결승"}.get(size, f"{size}강")


def _describe_tournament_path(total_players: int) -> str:
    """Return the current bracket path in short chat-friendly form."""
    if total_players > 32:
        return "4개 조 조별예선 후 8강 본선"
    if total_players > 16:
        return "2개 조 조별예선 후 4강 본선"

    target = 1
    while target * 2 <= total_players:
        target *= 2
    excess = total_players - target
    round_label = _round_label_for_size(target)

    if excess > 0:
        return f"예선 {excess}경기 후 {round_label} 본선"
    return f"{round_label} 단일 토너먼트"


def _registration_hype_text(count: int) -> str | None:
    """Extra registration copy shown only on meaningful count milestones."""
    announce_icon = icon_emoji("game")
    next_icon = icon_emoji("footsteps")
    if count not in _REGISTRATION_MILESTONES:
        return None

    min_players = max(2, config.TOURNAMENT_MIN_PLAYERS)
    if count < min_players:
        need = min_players - count
        return f"{announce_icon} 참가자 {count}명 돌파! 개막까지 이제 {need}명 남았습니다."

    next_target = 1
    while next_target < count:
        next_target *= 2

    if count == next_target:
        next_goal = next_target * 2
        next_label = _round_label_for_size(next_target)
        return (
            f"{announce_icon} 참가자 {count}명 도달! 현재 기준 {next_label} 바로 진행입니다.\n"
            f"{next_icon} 다음 목표는 {next_goal}명입니다."
        )

    need = next_target - count
    next_label = _round_label_for_size(next_target)
    return f"{announce_icon} 현재 {count}명. {next_label}까지 {need}명 남았습니다."


def _build_round_recap(round_name: str, winners: list[tuple[int, dict]], next_bracket: list) -> str:
    """Compact recap between rounds so the chat keeps some narrative flow."""
    recap_icon = icon_emoji("computer")
    next_icon = icon_emoji("footsteps")
    shiny_icon = shiny_emoji()
    names = [data["name"] for _, data in winners]
    if len(names) <= 6:
        survivor_text = ", ".join(names)
    else:
        survivor_text = ", ".join(names[:6]) + f" 외 {len(names) - 6}명"

    shiny_survivors = 0
    for _, data in winners:
        team = data.get("team") or []
        if any(bool(p.get("is_shiny")) for p in team):
            shiny_survivors += 1

    next_size = len(next_bracket) * 2
    next_label = _round_label_for_size(next_size) if next_size else "종료"
    next_match_count = sum(1 for p1, p2 in next_bracket if p1 is not None or p2 is not None)

    lines = [
        f"{recap_icon} {round_name} 종료",
        f"생존자 {len(winners)}명: {survivor_text}",
    ]
    if shiny_survivors:
        lines.append(f"{shiny_icon} 이로치 보유 트레이너 {shiny_survivors}명 생존")
    if next_match_count:
        lines.append(f"{next_icon} 다음 무대: {next_label} ({next_match_count}경기)")
    return "\n".join(lines)


async def _clear_registrations_db():
    """Clear tournament registrations from DB."""
    try:
        pool = await get_db()
        await pool.execute("DELETE FROM tournament_registrations")
    except Exception as e:
        logger.warning(f"Failed to clear tournament_registrations: {e}")


async def _save_registration_db(user_id: int, display_name: str):
    """Save a single registration to DB."""
    try:
        pool = await get_db()
        await pool.execute(
            "INSERT INTO tournament_registrations (user_id, display_name) "
            "VALUES ($1, $2) ON CONFLICT (user_id) DO NOTHING",
            user_id, display_name,
        )
    except Exception as e:
        logger.warning(f"Failed to save registration to DB: {e}")


async def _load_registrations_db() -> dict:
    """Load registrations from DB. Returns {user_id: {'name': str, 'team': None}}."""
    try:
        pool = await get_db()
        rows = await pool.fetch("SELECT user_id, display_name FROM tournament_registrations")
        return {r["user_id"]: {"name": r["display_name"], "team": None} for r in rows}
    except Exception as e:
        logger.warning(f"Failed to load registrations from DB: {e}")
        return {}


def _reset_state():
    _tournament_state["registering"] = False
    _tournament_state["running"] = False
    _tournament_state["participants"] = {}
    _tournament_state["chat_id"] = None
    _tournament_state["mock"] = False
    _tournament_state["random_1v1"] = False


def is_tournament_active(chat_id: int) -> bool:
    """Return True if tournament is running or registering in this chat."""
    if not _tournament_state["chat_id"]:
        return False
    return (
        _tournament_state["chat_id"] == chat_id
        and (_tournament_state["running"] or _tournament_state["registering"])
    )


# ── Registration ────────────────────────────────────────────────

async def start_registration(context: ContextTypes.DEFAULT_TYPE, *, mock: bool = False, random_1v1: bool = False):
    """JobQueue callback — 21:00 KST: stop spawns, open registration.

    mock=True: 모의대회 (보상 없음, DM 브로드캐스트 없음).
    random_1v1=True: 이벤트 모드 (랜덤 1마리, 팀 불필요).
    """
    chat_id = config.TOURNAMENT_CHAT_ID
    if not chat_id:
        logger.warning("No tournament chat configured, skipping tournament.")
        return

    _reset_state()
    await _clear_registrations_db()
    _tournament_state["registering"] = True
    _tournament_state["chat_id"] = chat_id
    _tournament_state["mock"] = mock
    _tournament_state["random_1v1"] = random_1v1

    # Cancel all spawn jobs for this chat (normal + arcade)
    chat_str = str(chat_id)
    for job in context.job_queue.jobs():
        if job.name and chat_str in job.name and (
            job.name.startswith("spawn_") or job.name.startswith("arcade_")
        ):
            job.schedule_removal()

    _bt = icon_emoji("battle")
    _champ = icon_emoji("champion_first")
    _crown = icon_emoji("crown")
    _runner = icon_emoji("2")
    _semi = icon_emoji("4")
    _entry = icon_emoji("check")
    _guide = icon_emoji("bookmark")
    _se = shiny_emoji()

    if mock and random_1v1:
        await _safe_send(context.bot, chat_id,
            text=(
                f"{_bt} 이벤트 토너먼트!\n"
                "━━━━━━━━━━━━━━━\n\n"
                f"{_guide} 참가 방법: ㄷ 입력\n"
                f"{_entry} 포켓몬 1마리 이상 보유 시 참가 가능!\n\n"
                "방식: 보유 포켓몬 중 랜덤 1마리로 1:1 대결\n"
                "운명의 포켓몬은 대회 시작 시 공개됩니다!\n\n"
                "스폰은 대회 종료 후 재개됩니다."
            ),
            parse_mode="HTML",
        )
    elif mock:
        await _safe_send(context.bot, chat_id,
            text=(
                f"{_bt} 모의 토너먼트!\n"
                "━━━━━━━━━━━━━━━\n\n"
                f"{_guide} 참가 방법: ㄷ 입력\n"
                f"{_bt} 배틀팀이 등록되어 있어야 참가 가능!\n\n"
                "주의: 모의대회 — 보상 없음\n\n"
                "스폰은 대회 종료 후 재개됩니다."
            ),
            parse_mode="HTML",
        )
    else:
        await _safe_send(context.bot, chat_id,
            text=(
                f"{_bt} 아케이드 토너먼트!\n"
                "━━━━━━━━━━━━━━━\n\n"
                f"{icon_emoji('stationery')} 등록 시간: 지금 ~ 21:50\n"
                f"{_guide} 참가 방법: ㄷ 입력\n"
                f"{_bt} 배틀팀이 등록되어 있어야 참가 가능!\n\n"
                f"{_champ} 보상\n"
                f"  {_crown} 우승: 마스터볼 {config.TOURNAMENT_PRIZE_1ST_MB}개 + {config.TOURNAMENT_PRIZE_1ST_BP:,}BP + {_se}이로치 초전설 + IV+3 + 챔피언 칭호\n"
                f"  {_runner} 준우승: 마스터볼 {config.TOURNAMENT_PRIZE_2ND_MB}개 + {config.TOURNAMENT_PRIZE_2ND_BP:,}BP + {_se}이로치 전설 + IV+3\n"
                f"  {_semi} 4강: 마스터볼 {config.TOURNAMENT_PRIZE_SEMI_MB}개 + {config.TOURNAMENT_PRIZE_SEMI_BP:,}BP + {_se}이로치(에픽)\n"
                f"  {_entry} 참가: 마스터볼 {config.TOURNAMENT_PRIZE_PARTICIPANT_MB}개 + {config.TOURNAMENT_PRIZE_PARTICIPANT_BP:,}BP\n\n"
                "스폰은 대회 종료 후 재개됩니다."
            ),
            parse_mode="HTML",
        )
    logger.info(f"Tournament registration started for chat {chat_id} (mock={mock})")

    # Send DM notification to all users (skip for mock)
    if not mock:
        if not os.path.exists("/tmp/skip_tournament_dm"):
            asyncio.create_task(_broadcast_tournament_dm(context))
        else:
            os.remove("/tmp/skip_tournament_dm")
            logger.info("Skipped tournament DM broadcast (flag file)")


async def _broadcast_tournament_dm(context: ContextTypes.DEFAULT_TYPE):
    """Send DM to all registered users about tournament registration."""
    try:
        user_ids = await queries.get_recently_active_user_ids(minutes=360)
        logger.info(f"Broadcasting tournament DM to {len(user_ids)} users")

        _mb = ball_emoji("masterball")
        _se = shiny_emoji()
        _bt = icon_emoji("battle")
        _note = icon_emoji("stationery")

        # 시즌 룰 안내
        rule_line = ""
        try:
            from services.ranked_service import ensure_current_season
            season = await ensure_current_season()
            if season:
                rule_info = config.WEEKLY_RULES.get(season["weekly_rule"], {})
                rule_name = rule_info.get("name", "")
                rule_desc = rule_info.get("desc", "")
                if rule_name:
                    cost_limit = rule_info.get("cost_limit")
                    if cost_limit:
                        rule_line = f"\n{_note} <b>이번 시즌: 팀 코스트 {cost_limit} 이하</b>\nㄴ {rule_desc}\n"
                    else:
                        rule_line = f"\n{_note} <b>시즌 룰: {rule_name}</b>\nㄴ {rule_desc}\n"
        except Exception:
            pass

        msg = (
            "━━━━━━━━━━━━━━━\n"
            f"{rule_line}"
            f"{_note} 랭크전 / 토너먼트 동일 적용!\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"{_bt} <b>토너먼트 21:00~21:50 등록 / 22:00 시작</b>\n"
            f"{icon_emoji('bookmark')} {config.BOT_CHANNEL_URL} 에서 ㄷ 입력\n\n"
            f"{icon_emoji('crown')} 우승: {_mb}×{config.TOURNAMENT_PRIZE_1ST_MB} + {_se}초전설 + IV+3 + 챔피언 칭호"
        )

        sent = 0
        for uid in user_ids:
            try:
                await context.bot.send_message(chat_id=uid, text=msg, parse_mode="HTML")
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

    # ── 이벤트 모드: 배틀팀 불필요, 포켓몬 1마리 이상만 ──
    if _tournament_state.get("random_1v1"):
        all_pokemon = await bq.get_user_pokemon_for_battle(user_id)
        if not all_pokemon:
            return False, "포켓몬이 없습니다! 먼저 포켓몬을 포획하세요."

        _tournament_state["participants"][user_id] = {
            "name": display_name,
            "team": None,
        }
        await _save_registration_db(user_id, display_name)
        count = len(_tournament_state["participants"])
        return True, (
            f"{icon_emoji('check')} {display_name} 참가 등록!\n"
            f"현재 참가자: {count}명\n"
            f"랜덤 포켓몬 1마리로 대결합니다!"
        )

    # Check battle team exists + cost validation + season rule
    team = await bq.get_battle_team(user_id)
    if not team:
        return False, "배틀팀이 없습니다! DM에서 '팀등록'으로 팀을 먼저 구성하세요."

    # 코스트 제한: 시즌 룰 동적 반영
    from services.ranked_service import get_current_cost_limit
    cost_limit = await get_current_cost_limit()
    total_cost = sum(config.RANKED_COST.get(p.get("rarity", ""), 0) for p in team)
    if total_cost > cost_limit:
        return False, (
            f"불가: 팀 코스트 초과! ({total_cost}/{cost_limit})\n"
            f"코스트 {cost_limit} 이하로 편성해주세요."
        )

    # 시즌 룰 검증
    try:
        from services.ranked_service import validate_team_for_ranked, ensure_current_season
        season = await ensure_current_season()
        if season:
            ok, err = await validate_team_for_ranked(user_id, season)
            if not ok:
                return False, f"불가: 시즌 법칙 위반!\n{err}\n\n팀을 변경 후 다시 참가해주세요."
    except Exception:
        pass  # 시즌 없으면 스킵

    _tournament_state["participants"][user_id] = {
        "name": display_name,
        "team": None,  # will be snapshotted at 21:50
    }
    await _save_registration_db(user_id, display_name)

    count = len(_tournament_state["participants"])
    msg = (
        f"{icon_emoji('check')} {display_name} 참가 등록 완료!\n"
        f"현재 참가자: {count}명"
    )
    if not _tournament_state.get("mock"):
        msg += f"\n{icon_emoji('stationery')} 21:50에 배틀팀이 확정됩니다. 그 전에 팀을 변경할 수 있습니다."
        hype = _registration_hype_text(count)
        if hype:
            msg += f"\n\n{hype}"
    return True, msg


async def snapshot_teams(context: ContextTypes.DEFAULT_TYPE):
    """JobQueue callback — 21:50 KST: snapshot all registered players' teams."""
    if not _tournament_state["registering"]:
        return

    chat_id = _tournament_state["chat_id"]
    participants = _tournament_state["participants"]
    if not participants:
        return

    removed = []
    cost_removed = []

    if _tournament_state.get("random_1v1"):
        # 이벤트 모드: 보유 포켓몬 중 랜덤 1마리 선발
        import random as _rng
        for user_id, data in list(participants.items()):
            all_pokemon = await bq.get_user_pokemon_for_battle(user_id)
            if not all_pokemon:
                removed.append(data["name"])
                del participants[user_id]
            else:
                picked = _rng.choice(all_pokemon)
                data["team"] = [picked]
    else:
        from services.ranked_service import get_current_cost_limit
        cost_limit = await get_current_cost_limit()
        for user_id, data in list(participants.items()):
            team = await bq.get_battle_team(user_id)
            if not team:
                removed.append(data["name"])
                del participants[user_id]
            else:
                total_cost = sum(config.RANKED_COST.get(p.get("rarity", ""), 0) for p in team)
                if total_cost > cost_limit:
                    cost_removed.append(f"{data['name']}({total_cost})")
                    del participants[user_id]
                else:
                    data["team"] = team

    # Close registration after snapshot
    _tournament_state["registering"] = False

    _bt2 = icon_emoji("battle")

    if _tournament_state.get("random_1v1"):
        # 이벤트 모드: 각 참가자에게 뽑힌 포켓몬 공개
        lines = [
            f"{_bt2} 운명의 포켓몬 공개! ({len(participants)}명)",
            "━━━━━━━━━━━━━━━",
        ]
        for uid, data in participants.items():
            pkmn = data["team"][0] if data.get("team") else {}
            emoji = pkmn.get("emoji", "")
            name = pkmn.get("name_ko", "???")
            rarity = pkmn.get("rarity", "")
            lines.append(f"  {data['name']} → {emoji} {name} ({rarity})")
    else:
        lines = [
            f"{_bt2} 배틀팀 확정! ({len(participants)}명)",
            "━━━━━━━━━━━━━━━",
            "대회 접수가 마감되었습니다.",
        ]
    if removed:
        lines.append(f"\n주의: 팀 미등록으로 제외: {', '.join(removed)}")
    if cost_removed:
        lines.append(f"\n주의: 코스트 초과로 제외: {', '.join(cost_removed)}")

    await _safe_send(context.bot, chat_id, text="\n".join(lines), parse_mode="HTML")


# ── Tournament Execution ────────────────────────────────────────

async def start_tournament(context: ContextTypes.DEFAULT_TYPE):
    """JobQueue callback — 22:00 KST: close registration, run tournament."""
    # Fallback: if state was lost (bot restart), reload from DB
    if not _tournament_state["participants"]:
        db_participants = await _load_registrations_db()
        if db_participants:
            _tournament_state["participants"] = db_participants
            logger.info(f"Loaded {len(db_participants)} participants from DB (restart recovery)")
    if not _tournament_state["chat_id"]:
        _tournament_state["chat_id"] = config.TOURNAMENT_CHAT_ID

    chat_id = _tournament_state["chat_id"]

    if not chat_id or not _tournament_state["participants"]:
        logger.warning("start_tournament: no chat_id or participants — aborting")
        return

    _tournament_state["registering"] = False
    _tournament_state["running"] = True

    # ── 이벤트 모드: 배틀로얄 ──
    if _tournament_state.get("random_1v1"):
        participants = _tournament_state["participants"]
        count = len(participants)
        min_players = 2
        if count < min_players:
            await _safe_send(context.bot, chat_id,
                text=f"취소: 참가자 부족 ({count}명 / 최소 {min_players}명)",
            )
            _reset_state()
            await _clear_registrations_db()
            await _resume_spawns(context, chat_id)
            return

        from services.battle_royale import run_battle_royale
        placements = await run_battle_royale(context, chat_id, participants)

        # 전원 DM
        total = len(participants)
        for uid, rank in placements.items():
            pdata = participants.get(uid)
            if not pdata:
                continue
            pname = pdata["name"]
            team = pdata.get("team", [])
            pkmn_name = team[0].get("name_ko", "???") if team else "???"
            pkmn_emoji = team[0].get("emoji", "") if team else ""

            if rank == 1:
                result_text = f"{icon_emoji('champion_first')} 축하합니다! 최후의 생존자!"
            elif rank <= 3:
                result_text = "거의 끝까지 버텼습니다!"
            elif rank <= total // 2:
                result_text = "중반까지 선전했습니다!"
            else:
                result_text = "참가해 주셔서 감사합니다!"

            dm_text = (
                f"{icon_emoji('battle')} 배틀로얄 결과\n"
                "━━━━━━━━━━━━━━━\n\n"
                f"나의 포켓몬: {pkmn_emoji} {pkmn_name}\n"
                f"최종 순위: {rank}/{total}등\n\n"
                f"{result_text}"
            )
            try:
                await context.bot.send_message(chat_id=uid, text=dm_text, parse_mode="HTML")
            except Exception:
                logger.warning(f"Failed to DM event participant {uid}")

        _reset_state()
        await _clear_registrations_db()
        await _resume_spawns(context, chat_id)
        return

    participants = _tournament_state["participants"]
    _bracket_icon = icon_emoji("bookmark")

    # Fallback: if snapshot_teams didn't run (e.g. bot restart), snapshot now
    for user_id, data in list(participants.items()):
        if data.get("team") is None:
            if _tournament_state.get("random_1v1"):
                import random as _rng
                all_pokemon = await bq.get_user_pokemon_for_battle(user_id)
                if not all_pokemon:
                    del participants[user_id]
                else:
                    data["team"] = [_rng.choice(all_pokemon)]
            else:
                team = await bq.get_battle_team(user_id)
                if not team:
                    del participants[user_id]
                else:
                    data["team"] = team

    count = len(participants)

    min_players = 2 if _tournament_state.get("random_1v1") else config.TOURNAMENT_MIN_PLAYERS
    if count < min_players:
        await _safe_send(context.bot, chat_id,
            text=(
                f"취소: 참가자 부족으로 대회가 취소되었습니다.\n"
                f"(참가자: {count}명 / 최소: {config.TOURNAMENT_MIN_PLAYERS}명)\n\n"
                "스폰이 재개됩니다."
            ),
        )
        _reset_state()
        await _clear_registrations_db()
        await _resume_spawns(context, chat_id)
        return

    # Build player list
    player_list = [(uid, data) for uid, data in participants.items()]
    total_players = len(player_list)

    # ── Group Stage: 33+ → 4 groups, 17~32 → 2 groups, ≤16 → direct bracket ──
    use_groups = 0
    if total_players > 32:
        use_groups = 4
    elif total_players > 16:
        use_groups = 2

    if use_groups > 0:
        # Group stage → returns seeded bracket for knockout
        seeded_bracket = await _run_group_stage(context, chat_id, player_list, use_groups)
        bracket = seeded_bracket  # Already paired as [(p1, p2), ...]

        knockout_size = len(bracket) * 2
        round_label = {8: "8강", 4: "4강", 2: "결승"}.get(knockout_size, f"{knockout_size}강")

        # Show knockout bracket
        tree = _render_bracket(bracket)
        if tree and len(tree) < 4000:
            await _safe_send(context.bot, chat_id,
                text=f"{_bracket_icon} {round_label} 대진표 (본선)\n{tree}",
                parse_mode="HTML",
            )
        await asyncio.sleep(5)
    else:
        # ── Small tournament: direct single elimination ──
        # Find target bracket size (largest power of 2 ≤ total_players)
        target = 1
        while target * 2 <= total_players:
            target *= 2
        excess = total_players - target

        round_labels = {16: "16강", 8: "8강", 4: "4강", 2: "결승"}
        round_label = round_labels.get(target, f"{target}강")

        if excess > 0:
            await _safe_send(context.bot, chat_id,
                text=(
                    f"{icon_emoji('battle')} 토너먼트 시작!\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"참가자: {count}명\n"
                    f"방식: 예선 {excess}경기 → {round_label} 본선\n\n"
                    f"예선전을 시작합니다..."
                ),
                parse_mode="HTML",
            )
            await asyncio.sleep(3)

            qualifiers = await _run_preliminary_round(context, chat_id, player_list, target)

            q_names = ", ".join(q[1]["name"] for q in qualifiers)
            await _safe_send(context.bot, chat_id,
                text=f"{icon_emoji('champion_first')} {round_label} 진출자\n━━━━━━━━━━━━━━━\n{q_names}",
                parse_mode="HTML",
            )
            await asyncio.sleep(5)

            bracket = _generate_bracket(qualifiers)
        else:
            await _safe_send(context.bot, chat_id,
                text=(
                    f"{icon_emoji('battle')} 토너먼트 시작!\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"참가자: {count}명\n"
                    f"방식: 싱글 엘리미네이션\n\n"
                    f"대진표를 생성합니다..."
                ),
                parse_mode="HTML",
            )
            await asyncio.sleep(3)
            bracket = _generate_bracket(player_list)

        # Show bracket (ASCII tree)
        tree = _render_bracket(bracket)
        if tree and len(tree) < 4000:
            await _safe_send(context.bot, chat_id,
                text=f"{_bracket_icon} {round_label + ' ' if excess > 0 else ''}대진표\n{tree}",
                parse_mode="HTML",
            )
        await asyncio.sleep(7 if excess > 0 else 3)

    original_bracket = list(bracket)
    round_results = {}

    # Run rounds
    total_rounds = int(math.log2(len(bracket) * 2))
    current_round = 1
    semi_finalists = set()  # Track 4th place candidates
    eliminated = {}  # user_id -> round_size when eliminated (16, 8, etc.)

    try:
        while len(bracket) > 0:
            is_final = (len(bracket) == 1 and bracket[0][0] is not None and bracket[0][1] is not None)
            is_semi = (len(bracket) == 2)
            is_quarter = (len(bracket) <= 4 and not is_semi and not is_final)

            round_size = len(bracket) * 2  # 16, 8, 4, 2
            round_name = "결승" if is_final else ("준결승" if is_semi else f"{round_size}강")

            if not is_final:
                # Show bracket for this round
                bracket_lines = [f"{_bracket_icon} {round_name} 대진표", "━━━━━━━━━━━━━━━"]
                bnum = 0
                for bp1, bp2 in bracket:
                    if bp1 is None and bp2 is None:
                        continue
                    bnum += 1
                    n1 = bp1[1]['name'] if bp1 else "부전승"
                    n2 = bp2[1]['name'] if bp2 else "부전승"
                    bracket_lines.append(f"{bnum}. {n1} vs {n2}")
                await _safe_send(context.bot, chat_id,
                    text="\n".join(bracket_lines),
                )
                await asyncio.sleep(3)

                await _safe_send(context.bot, chat_id,
                    text=f"\n{icon_emoji('game')} {round_name}",
                    parse_mode="HTML",
                )
                await asyncio.sleep(1)

            winners = []
            round_winner_names = []
            match_count = sum(1 for a, b in bracket if a is not None or b is not None)
            match_num = 0
            for p1, p2 in bracket:
                if p1 is None and p2 is None:
                    round_winner_names.append("")
                    continue
                match_num += 1
                match_label = f"[ {match_num}번째 매치 ] " if match_count > 1 and not is_final else ""
                if p1 is None:
                    # p2 gets bye
                    uid2, data2 = p2
                    await _safe_send(context.bot, chat_id,
                        text=f"{match_label}{icon_emoji('footsteps')} {data2['name']} — 부전승!",
                        parse_mode="HTML",
                    )
                    winners.append(p2)
                    round_winner_names.append(data2['name'])
                    await asyncio.sleep(3)
                elif p2 is None:
                    # p1 gets bye
                    uid1, data1 = p1
                    await _safe_send(context.bot, chat_id,
                        text=f"{match_label}{icon_emoji('footsteps')} {data1['name']} — 부전승!",
                        parse_mode="HTML",
                    )
                    winners.append(p1)
                    round_winner_names.append(data1['name'])
                    await asyncio.sleep(3)
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
                        match_label=match_label,
                    )
                    winners.append((winner_id, winner_data))
                    round_winner_names.append(winner_data['name'])
                    await asyncio.sleep(3)

            round_results[current_round] = round_winner_names

            # Track eliminated players by round size (round_size already set above)
            winner_ids_set = {w[0] for w in winners}
            for p1, p2 in bracket:
                if p1 is not None and p1[0] not in winner_ids_set:
                    eliminated[p1[0]] = round_size
                if p2 is not None and p2[0] not in winner_ids_set:
                    eliminated[p2[0]] = round_size

            if is_final:
                # 결승 결과: 결승전 bracket만 컴팩트하게 표시
                tree = _render_bracket(bracket, {1: round_winner_names})
                if tree and len(tree) < 4000:
                    await _safe_send(context.bot, chat_id,
                        text=f"{_bracket_icon} 최종 결과\n{tree}",
                        parse_mode="HTML",
                    )
                    await asyncio.sleep(3)
                # Tournament complete — give prizes (skip for mock)
                if winners:
                    winner_uid, winner_d = winners[0]
                    if _tournament_state.get("mock") and _tournament_state.get("random_1v1"):
                        # ── 이벤트 모드: 전체 순위 발표 + 전원 DM ──
                        total = len(_tournament_state["participants"])
                        placements = {winner_uid: 1}
                        rank = 2
                        for rs in sorted(set(eliminated.values())):
                            users_at = [u for u, r in eliminated.items() if r == rs]
                            for u in users_at:
                                placements[u] = rank
                            rank += len(users_at)
                        for uid in _tournament_state["participants"]:
                            if uid not in placements:
                                placements[uid] = rank
                                rank += 1

                        # 그룹 채팅 순위표
                        rank_lines = []
                        for uid, r in sorted(placements.items(), key=lambda x: x[1]):
                            pdata = _tournament_state["participants"].get(uid)
                            pname = pdata["name"] if pdata else "?"
                            team = pdata.get("team", []) if pdata else []
                            pkmn_name = team[0].get("name_ko", "?") if team else "?"
                            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(r, f"{r}등")
                            rank_lines.append(f"  {medal} {pname} ({pkmn_name})")

                        await _safe_send(context.bot, chat_id,
                            text=(
                                f"{icon_emoji('champion_first')} 이벤트 토너먼트 결과!\n"
                                "━━━━━━━━━━━━━━━\n\n"
                                + "\n".join(rank_lines)
                            ),
                            parse_mode="HTML",
                        )

                        # 전원 DM
                        for uid, r in placements.items():
                            pdata = _tournament_state["participants"].get(uid)
                            pname = pdata["name"] if pdata else "트레이너"
                            team = pdata.get("team", []) if pdata else []
                            pkmn_name = team[0].get("name_ko", "???") if team else "???"
                            pkmn_emoji = team[0].get("emoji", "") if team else ""

                            if r == 1:
                                result_text = f"{icon_emoji('champion_first')} 축하합니다! 우승!"
                            elif r == 2:
                                result_text = "준우승! 아깝다!"
                            elif r <= 4:
                                result_text = "4강 진출! 멋져요!"
                            else:
                                result_text = "참가해 주셔서 감사합니다!"

                            dm_text = (
                                f"{icon_emoji('battle')} 이벤트 토너먼트 결과\n"
                                "━━━━━━━━━━━━━━━\n\n"
                                f"나의 포켓몬: {pkmn_emoji} {pkmn_name}\n"
                                f"최종 순위: {r}/{total}등\n\n"
                                f"{result_text}"
                            )
                            try:
                                await context.bot.send_message(chat_id=uid, text=dm_text, parse_mode="HTML")
                            except Exception:
                                logger.warning(f"Failed to DM event participant {uid}")
                            if r % 25 == 0:
                                await asyncio.sleep(1)

                    elif _tournament_state.get("mock"):
                        await _safe_send(context.bot, chat_id,
                            text=f"{icon_emoji('champion_first')} 모의대회 우승: {winner_d['name']}!\n주의: 모의대회이므로 보상 없음",
                            parse_mode="HTML",
                        )
                    else:
                        all_participants = set(_tournament_state["participants"].keys())
                        await _award_prizes(context, chat_id, winner_uid, winner_d, bracket, semi_finalists, all_participants, eliminated)
                break

            # Next round bracket 구성
            next_bracket = []
            for i in range(0, len(winners), 2):
                if i + 1 < len(winners):
                    next_bracket.append((winners[i], winners[i + 1]))
                else:
                    next_bracket.append((winners[i], None))

            # 다음 라운드 진출자만 컴팩트하게 표시 (전체 누적 트리 대신)
            recap_text = _build_round_recap(round_name, winners, next_bracket)
            if recap_text:
                await _safe_send(context.bot, chat_id, text=recap_text, parse_mode="HTML")
                await asyncio.sleep(2)
            next_size = len(next_bracket) * 2
            next_label = "결승" if len(next_bracket) == 1 else (
                "준결승" if len(next_bracket) == 2 else f"{next_size}강"
            )
            tree = _render_bracket(next_bracket, {})
            if tree and len(tree) < 4000:
                await _safe_send(context.bot, chat_id,
                    text=f"{_bracket_icon} {next_label} 대진표\n{tree}",
                    parse_mode="HTML",
                )
                await asyncio.sleep(7)

            bracket = next_bracket
            current_round += 1
            await asyncio.sleep(3)

    except Exception as e:
        logger.error(f"Tournament error: {e}", exc_info=True)
        try:
            await _safe_send(context.bot, chat_id,
                text="주의: 토너먼트 진행 중 오류가 발생했습니다.",
            )
        except Exception:
            logger.error("Failed to send tournament error message")

    # Cleanup
    _reset_state()
    await _clear_registrations_db()
    await _resume_spawns(context, chat_id)

    # 대회 종료 15분 후 아케이드 자동 재시작
    async def _restart_arcade(ctx):
        from services.spawn_schedule import schedule_arcade_spawns, restore_temp_arcades
        try:
            schedule_arcade_spawns(ctx.application)
            await restore_temp_arcades(ctx.application)
            logger.info("Arcade spawns restarted after tournament")
        except Exception as e:
            logger.error(f"Failed to restart arcade after tournament: {e}")

    context.application.job_queue.run_once(
        _restart_arcade, when=900, name="arcade_restart_after_tournament",
    )


# ══════════════════════════════════════════════════════════
# 대회 재개 (일시적, 준결승부터 재개)
# ══════════════════════════════════════════════════════════

async def resume_tournament_from_semi(context: ContextTypes.DEFAULT_TYPE):
    """준결승부터 대회 재개 — 3/29 대회 중단 복구용 임시 함수.

    대진: 딸딸기 vs Jun_P3, Turri vs 러스트
    8강 탈락: 제리, Han, 무색큐브, E FIGHT
    전체 참가자: tournament_registrations에서 로드 (50명)
    """
    chat_id = config.TOURNAMENT_CHAT_ID
    _bracket_icon = icon_emoji("bookmark")

    # ── 준결승 4명 ID ──
    SEMI = {
        6007036282: "딸딸기",
        7044819211: "Jun_P3",
        7609021791: "Turri",
        7050637391: "러스트",
    }
    # ── 8강 탈락자 ──
    QUARTER_ELIMINATED = {
        7285104306: 8,   # 제리
        8616523632: 8,   # Han
        5237146711: 8,   # 무색큐브
        336224560: 8,    # E FIGHT
    }

    # 팀 로드
    participants = {}
    for uid, name in SEMI.items():
        team = await bq.get_battle_team(uid)
        if not team:
            await _safe_send(context.bot, chat_id,
                text=f"⚠️ {name}의 배틀팀을 찾을 수 없습니다!")
            return
        participants[uid] = {"name": name, "team": team}

    # 전체 참가자 로드 (보상용)
    pool = await get_db()
    all_regs = await pool.fetch(
        "SELECT user_id, display_name FROM tournament_registrations"
    )
    all_participants = {r[0] for r in all_regs}
    if not all_participants:
        await _safe_send(context.bot, chat_id,
            text="⚠️ tournament_registrations가 비어있습니다!")
        return

    # 대진: 딸딸기 vs Jun_P3, Turri vs 러스트
    bracket = [
        ((6007036282, participants[6007036282]),
         (7044819211, participants[7044819211])),
        ((7609021791, participants[7609021791]),
         (7050637391, participants[7050637391])),
    ]

    semi_finalists = set(SEMI.keys())
    eliminated = dict(QUARTER_ELIMINATED)

    _tournament_state["running"] = True
    _tournament_state["chat_id"] = chat_id
    _tournament_state["participants"] = {uid: {"name": name} for uid, name in SEMI.items()}

    try:
        # ── 준결승 안내 ──
        await _safe_send(context.bot, chat_id,
            text=(
                f"⚔️ 대회 재개! (준결승부터)\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"{_bracket_icon} 준결승 대진표\n"
                f"━━━━━━━━━━━━━━━\n"
                f"1. 딸딸기 vs Jun_P3\n"
                f"2. Turri vs 러스트"
            ),
            parse_mode="HTML",
        )
        await asyncio.sleep(3)

        await _safe_send(context.bot, chat_id,
            text=f"\n{icon_emoji('game')} 준결승",
            parse_mode="HTML",
        )
        await asyncio.sleep(1)

        # ── 준결승 매치 ──
        winners = []
        for mi, (p1, p2) in enumerate(bracket):
            uid1, data1 = p1
            uid2, data2 = p2
            match_label = f"[ {mi + 1}번째 매치 ] "
            winner_id, winner_data = await _run_match(
                context, chat_id,
                uid1, data1, uid2, data2,
                is_final=False, is_semi=True, is_quarter=False,
                match_label=match_label,
            )
            winners.append((winner_id, winner_data))
            # 탈락자 기록
            loser_id = uid2 if winner_id == uid1 else uid1
            eliminated[loser_id] = 4
            await asyncio.sleep(3)

        # ── 결승 대진 ──
        final_bracket = [(winners[0], winners[1])]
        tree = _render_bracket(final_bracket, {})
        if tree and len(tree) < 4000:
            await _safe_send(context.bot, chat_id,
                text=f"{_bracket_icon} 결승 대진표\n{tree}",
                parse_mode="HTML",
            )
            await asyncio.sleep(5)

        # ── 결승 매치 ──
        f_p1 = winners[0]
        f_p2 = winners[1]
        champion_id, champion_data = await _run_match(
            context, chat_id,
            f_p1[0], f_p1[1], f_p2[0], f_p2[1],
            is_final=True, is_semi=False, is_quarter=False,
        )
        await asyncio.sleep(3)

        # ── 보상 지급 ──
        await _award_prizes(
            context, chat_id,
            champion_id, champion_data,
            final_bracket, semi_finalists,
            all_participants, eliminated,
        )

    except Exception as e:
        logger.error(f"Resume tournament error: {e}", exc_info=True)
        await _safe_send(context.bot, chat_id,
            text="⚠️ 대회 재개 중 오류가 발생했습니다.")

    # Cleanup
    _reset_state()
    await _clear_registrations_db()
    await _resume_spawns(context, chat_id)
