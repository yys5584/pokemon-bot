"""Tournament system: daily single-elimination in arcade channels."""

import asyncio
import math
import random
import logging
from datetime import datetime

from telegram.ext import ContextTypes

from telegram.error import RetryAfter

import config
from database import queries
from database import battle_queries as bq
from database.connection import get_db
from services.battle_service import _prepare_combatant, _resolve_battle, _hp_bar

# ── Bracket Tree Renderer ──────────────────────────────────────
import unicodedata


def _dw(s: str) -> int:
    """Display width: CJK/fullwidth chars count as 2."""
    return sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in s)


def _rpad(s: str, target: int) -> str:
    """Right-pad string to target display width."""
    return s + ' ' * max(0, target - _dw(s))


def _render_bracket(bracket, round_results=None) -> str:
    """Render tournament bracket as ASCII tree in <pre> block.

    bracket: list of (p1, p2) tuples for round 1.
    round_results: dict {round_num: [winner_name, ...]} — completed rounds.
                   round 1 = first round (leaf), round 2 = next level, etc.
    """
    if round_results is None:
        round_results = {}

    players = []
    for p1, p2 in bracket:
        players.append(p1[1]['name'] if p1 else "부전승")
        players.append(p2[1]['name'] if p2 else "부전승")

    if len(players) < 2:
        return ""

    nw = max(_dw(n) for n in players)

    # Mutable counter: track match index per round level
    round_counters = {}

    def _build(names, root=False):
        n = len(names)
        rnd = int(math.log2(n))  # round number for this junction

        # Look up result for this junction
        idx = round_counters.get(rnd, 0)
        round_counters[rnd] = idx + 1
        winner = None
        if rnd in round_results and idx < len(round_results[rnd]):
            w = round_results[rnd][idx]
            if w:
                winner = w

        if n == 2:
            a = _rpad(names[0], nw)
            b = _rpad(names[1], nw)
            sp = ' ' * nw
            if winner:
                tag = f"  ├─🏆 {winner}" if root else f"  ├─ {winner}"
                return [a + " ─┐", sp + tag, b + " ─┘"], 1
            else:
                tag = "  ├─🏆" if root else "  │"
                return [a + " ─┐", sp + tag, b + " ─┘"], 1

        mid = n // 2
        top, tj = _build(names[:mid])
        bot, bj = _build(names[mid:])

        cw = max(_dw(l) for l in top + bot)
        out = []

        for i, line in enumerate(top):
            p = ' ' * (cw - _dw(line))
            if i == tj:
                out.append(line + p + " ─┐")
            elif i > tj:
                out.append(line + p + "  │")
            else:
                out.append(line + p + "   ")

        sp = ' ' * cw
        if root:
            out.append(sp + (f"  ├─🏆 {winner}" if winner else "  ├─🏆"))
        else:
            out.append(sp + (f"  ├─ {winner}" if winner else "  ├──"))
        jrow = len(out) - 1

        for i, line in enumerate(bot):
            p = ' ' * (cw - _dw(line))
            if i == bj:
                out.append(line + p + " ─┘")
            elif i < bj:
                out.append(line + p + "  │")
            else:
                out.append(line + p + "   ")

        return out, jrow

    lines, _ = _build(players, root=True)
    return "<pre>" + "\n".join(lines) + "</pre>"


# ── Switch-in lines (randomly picked) ─────────────────────────
_SWITCH_NORMAL = [
    "{trainer}: {dead} 돌아와! 가라, {next}!",
    "{trainer}: {dead} 수고했어! {next}, 네 차례야!",
    "{trainer}: {dead} 돌아와! 부탁해, {next}!",
    "{trainer}: {dead} 잘 싸웠어! {next}, 출발!",
    "{trainer}: {dead} 고생했어! 가자, {next}!",
]
_SWITCH_LEGENDARY = [
    "{trainer}: ...{next}, 네 힘을 보여줘!",
    "{trainer}: 최후의 카드다... 가라, {next}!",
    "{trainer}: 전설의 힘이여... {next}, 출격!",
    "{trainer}: 승부를 결정지어라, {next}!",
    "{trainer}: 이건 양보할 수 없다... {next}, 간다!",
]


def _switch_line(trainer: str, dead: str, next_name: str, next_rarity: str = "") -> str:
    """Pick a random switch-in line. Legendary gets dramatic lines."""
    pool = _SWITCH_LEGENDARY if next_rarity in ("legendary", "epic") else _SWITCH_NORMAL
    return random.choice(pool).format(trainer=trainer, dead=dead, next=next_name)


async def _safe_send(bot, chat_id, text, **kwargs):
    """send_message with RetryAfter auto-retry."""
    for attempt in range(3):
        try:
            return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
        except RetryAfter as e:
            wait = e.retry_after + 1
            logger.warning(f"Flood control, waiting {wait}s (attempt {attempt+1})")
            await asyncio.sleep(wait)
    # last attempt without catch
    return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
from utils.helpers import icon_emoji, ball_emoji, rarity_badge

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


def is_tournament_active(chat_id: int) -> bool:
    """Return True if tournament is running or registering in this chat."""
    if not _tournament_state["chat_id"]:
        return False
    return (
        _tournament_state["chat_id"] == chat_id
        and (_tournament_state["running"] or _tournament_state["registering"])
    )


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

    await _safe_send(context.bot, chat_id,
        text=(
            "🏟️ 아케이드 토너먼트!\n"
            "━━━━━━━━━━━━━━━\n\n"
            "🕘 등록 시간: 지금 ~ 22:00\n"
            "📋 참가 방법: ㄷ 입력\n"
            "⚔️ 배틀팀이 등록되어 있어야 참가 가능!\n\n"
            "🏆 우승 보상\n"
            f"  🥇 마스터볼 {config.TOURNAMENT_PRIZE_1ST_MB}개 + {config.TOURNAMENT_PRIZE_1ST_BP} BP + 챔피언 칭호 (밥+1회)\n"
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
            "🏆 우승: 마스터볼 2개 + 200 BP + 챔피언 칭호 (밥+1회)\n"
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

    # Check battle team exists (validation only, snapshot later at 21:50)
    team = await bq.get_battle_team(user_id)
    if not team:
        return False, "배틀팀이 없습니다! DM에서 '팀등록'으로 팀을 먼저 구성하세요."

    _tournament_state["participants"][user_id] = {
        "name": display_name,
        "team": None,  # will be snapshotted at 21:50
    }

    count = len(_tournament_state["participants"])
    return True, (
        f"{icon_emoji('check')} {display_name} 참가 등록 완료!\n"
        f"현재 참가자: {count}명\n"
        f"💡 21:50에 배틀팀이 확정됩니다. 그 전에 팀을 변경할 수 있습니다."
    )


async def snapshot_teams(context: ContextTypes.DEFAULT_TYPE):
    """JobQueue callback — 21:50 KST: snapshot all registered players' teams."""
    if not _tournament_state["registering"]:
        return

    chat_id = _tournament_state["chat_id"]
    participants = _tournament_state["participants"]
    if not participants:
        return

    removed = []
    for user_id, data in list(participants.items()):
        team = await bq.get_battle_team(user_id)
        if not team:
            removed.append(data["name"])
            del participants[user_id]
        else:
            data["team"] = team

    lines = [
        f"⚔️ 배틀팀 확정! ({len(participants)}명)",
        "━━━━━━━━━━━━━━━",
        "이제부터 팀 변경이 대회에 반영되지 않습니다.",
    ]
    if removed:
        lines.append(f"\n⚠️ 팀 미등록으로 제외: {', '.join(removed)}")

    await _safe_send(context.bot, chat_id, text="\n".join(lines))


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
    # Team labels: challenger = red badge, defender = rare(blue) badge
    C = rarity_badge("red")
    D = rarity_badge("rare")

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

    # Helper: team marker for KO/next based on side
    def _mark(side):
        return C if side == "challenger" else D

    # Helper: build matchup sections from turn_data
    def _build_sections(turn_data):
        sections, cur = [], []
        for td in turn_data:
            if td["type"] == "matchup" and cur:
                sections.append(cur)
                cur = [td]
            else:
                cur.append(td)
        if cur:
            sections.append(cur)
        return sections

    # Helper: format a section into lines (for quarter/semi) — with HP bars
    def _format_section(section):
        lines = []
        # Get trainer name for KO messages
        c_trainer = p1_data['name']
        d_trainer = p2_data['name']
        for td in section:
            if td["type"] == "matchup":
                lines.append(f"⚔ {C}{td['c_tb']}{td['c_name']} vs {D}{td['d_tb']}{td['d_name']}")
            elif td["type"] == "turn":
                # Determine who goes first
                if td["first_is_challenger"]:
                    first_mark, second_mark = C, D
                    first_name, first_dmg, first_crit, first_eff = td["c_name"], td["c_dmg"], td["c_crit"], td["c_eff"]
                    second_name, second_dmg, second_crit, second_eff = td["d_name"], td["d_dmg"], td["d_crit"], td["d_eff"]
                    first_target_hp, first_target_max = td["d_hp"], td["d_max_hp"]
                    second_target_hp, second_target_max = td["c_hp"], td["c_max_hp"]
                    first_target_mark, second_target_mark = D, C
                    first_target_name, second_target_name = td["d_name"], td["c_name"]
                else:
                    first_mark, second_mark = D, C
                    first_name, first_dmg, first_crit, first_eff = td["d_name"], td["d_dmg"], td["d_crit"], td["d_eff"]
                    second_name, second_dmg, second_crit, second_eff = td["c_name"], td["c_dmg"], td["c_crit"], td["c_eff"]
                    first_target_hp, first_target_max = td["c_hp"], td["c_max_hp"]
                    second_target_hp, second_target_max = td["d_hp"], td["d_max_hp"]
                    first_target_mark, second_target_mark = C, D
                    first_target_name, second_target_name = td["c_name"], td["d_name"]

                crit1 = " 크리티컬!" if first_crit else ""
                skill1 = f" {first_eff}!" if first_eff else " 공격!"
                bar1 = _hp_bar(first_target_hp, first_target_max)
                lines.append(f"{td['turn_num']}턴 ─ {first_mark}{first_name}{skill1}{crit1}")
                lines.append(f"  {first_target_mark}{first_target_name} {bar1} {first_target_hp}/{first_target_max} (-{first_dmg})")

                if second_dmg > 0:
                    crit2 = " 크리티컬!" if second_crit else ""
                    skill2 = f" {second_eff}!" if second_eff else " 반격!"
                    bar2 = _hp_bar(second_target_hp, second_target_max)
                    lines.append(f"{second_mark}{second_name}{skill2}{crit2}")
                    lines.append(f"  {second_target_mark}{second_target_name} {bar2} {second_target_hp}/{second_target_max} (-{second_dmg})")

            elif td["type"] == "ko":
                m = _mark(td["side"])
                trainer = c_trainer if td["side"] == "challenger" else d_trainer
                if td["next_name"]:
                    lines.append(f"{SKULL} {m}{td['dead_name']} 쓰러짐!")
                    lines.append(_switch_line(trainer, td['dead_name'], td['next_name'], td.get('next_rarity', '')))
                else:
                    lines.append(f"{SKULL} {m}{td['dead_name']} 쓰러짐!")
        return lines

    if is_final:
        # ── Finals: rich turn-by-turn display (3s delay) ──
        p1_name = p1_data['name']
        p2_name = p2_data['name']
        await _safe_send(context.bot, chat_id,
            text=(
                f"🏆 결승전!\n"
                f"{C}{p1_name} vs {D}{p2_name}\n"
                f"━━━━━━━━━━━━━━━"
            ),
            parse_mode="HTML",
        )
        await asyncio.sleep(3)

        # Track current matchup indices for header
        cur_c_idx, cur_d_idx = 0, 0
        cur_c_total, cur_d_total = 0, 0

        for td in result["turn_data"]:
            if td["type"] == "matchup":
                cur_c_idx = td["c_idx"]
                cur_d_idx = td["d_idx"]
                cur_c_total = td["c_total"]
                cur_d_total = td["d_total"]
                await _safe_send(context.bot, chat_id,
                    text=f"⚔ {C}{td['c_tb']}{td['c_name']} vs {D}{td['d_tb']}{td['d_name']}!",
                    parse_mode="HTML",
                )
                await asyncio.sleep(3)

            elif td["type"] == "turn":
                lines = []
                # 헤더: 트레이너명 + 몇 번째 포켓몬
                lines.append(f"{C}{p1_name}({td.get('c_idx', cur_c_idx)+1}/{td.get('c_total', cur_c_total)}) vs {D}{p2_name}({td.get('d_idx', cur_d_idx)+1}/{td.get('d_total', cur_d_total)})")

                if td["first_is_challenger"]:
                    first_mark, second_mark = C, D
                    first_name, first_dmg, first_crit, first_eff = td["c_name"], td["c_dmg"], td["c_crit"], td["c_eff"]
                    second_name, second_dmg, second_crit, second_eff = td["d_name"], td["d_dmg"], td["d_crit"], td["d_eff"]
                    first_target_hp, first_target_max = td["d_hp"], td["d_max_hp"]
                    second_target_hp, second_target_max = td["c_hp"], td["c_max_hp"]
                    first_target_name, second_target_name = td["d_name"], td["c_name"]
                    first_target_mark, second_target_mark = D, C
                else:
                    first_mark, second_mark = D, C
                    first_name, first_dmg, first_crit, first_eff = td["d_name"], td["d_dmg"], td["d_crit"], td["d_eff"]
                    second_name, second_dmg, second_crit, second_eff = td["c_name"], td["c_dmg"], td["c_crit"], td["c_eff"]
                    first_target_hp, first_target_max = td["c_hp"], td["c_max_hp"]
                    second_target_hp, second_target_max = td["d_hp"], td["d_max_hp"]
                    first_target_name, second_target_name = td["c_name"], td["d_name"]
                    first_target_mark, second_target_mark = C, D

                crit_label = " 크리티컬!" if first_crit else ""
                skill_label = f" {first_eff}!" if first_eff else " 공격!"
                lines.append(f"{td['turn_num']}턴 ─ {first_mark}{first_name}{skill_label}{crit_label}")
                bar = _hp_bar(first_target_hp, first_target_max)
                lines.append(f"  {first_target_mark}{first_target_name} {bar} {first_target_hp}/{first_target_max} (-{first_dmg})")

                if second_dmg > 0:
                    crit2_label = " 크리티컬!" if second_crit else ""
                    skill2_label = f" {second_eff}!" if second_eff else " 반격!"
                    lines.append(f"{second_mark}{second_name}{skill2_label}{crit2_label}")
                    bar2 = _hp_bar(second_target_hp, second_target_max)
                    lines.append(f"  {second_target_mark}{second_target_name} {bar2} {second_target_hp}/{second_target_max} (-{second_dmg})")

                await _safe_send(context.bot, chat_id, text="\n".join(lines), parse_mode="HTML")
                await asyncio.sleep(3)

            elif td["type"] == "ko":
                m = _mark(td["side"])
                trainer = p1_name if td["side"] == "challenger" else p2_name
                if td["next_name"]:
                    switch = _switch_line(trainer, td['dead_name'], td['next_name'], td.get('next_rarity', ''))
                    text = f"{SKULL} {m}{td['dead_name']} 쓰러짐!\n{switch}"
                else:
                    text = f"{SKULL} {m}{td['dead_name']} 쓰러짐!"
                await _safe_send(context.bot, chat_id, text=text, parse_mode="HTML")
                await asyncio.sleep(3)

        await _safe_send(context.bot, chat_id,
            text=f"\n🎉 {winner_data['name']} 우승! (남은 {remaining}마리)",
        )

    elif is_semi:
        # ── Semi-finals: 2 turns per message (3s delay) ──
        await _safe_send(context.bot, chat_id,
            text=(
                f"⚔️ 준결승! — {C}{p1_data['name']} vs {D}{p2_data['name']}\n"
                f"━━━━━━━━━━━━━━━"
            ),
            parse_mode="HTML",
        )
        await asyncio.sleep(3)

        # Format all lines, then send 2 lines at a time
        all_lines = _format_section(result["turn_data"])
        for i in range(0, len(all_lines), 2):
            chunk = "\n".join(all_lines[i:i+2])
            await _safe_send(context.bot, chat_id, text=chunk, parse_mode="HTML")
            await asyncio.sleep(3)

        await _safe_send(context.bot, chat_id,
            text=f"→ {winner_data['name']} 승리! (남은 {remaining}마리)",
        )

    elif is_quarter:
        # ── Quarter-finals: grouped by matchup (3s delay) ──
        await _safe_send(context.bot, chat_id,
            text=(
                f"⚔️ {C}{p1_data['name']} vs {D}{p2_data['name']}\n"
                f"━━━━━━━━━━━━━━━"
            ),
            parse_mode="HTML",
        )
        await asyncio.sleep(3)

        for section in _build_sections(result["turn_data"]):
            lines = _format_section(section)
            if lines:
                await _safe_send(context.bot, chat_id, text="\n".join(lines), parse_mode="HTML")
                await asyncio.sleep(3)

        await _safe_send(context.bot, chat_id,
            text=f"→ {winner_data['name']} 승리! (남은 {remaining}마리)",
        )

    else:
        # ── Lower rounds: one-line summary ──
        await _safe_send(context.bot, chat_id,
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

    # Fallback: if snapshot_teams didn't run (e.g. bot restart), snapshot now
    for user_id, data in list(participants.items()):
        if data.get("team") is None:
            team = await bq.get_battle_team(user_id)
            if not team:
                del participants[user_id]
            else:
                data["team"] = team

    count = len(participants)

    if count < config.TOURNAMENT_MIN_PLAYERS:
        await _safe_send(context.bot, chat_id,
            text=(
                f"❌ 참가자 부족으로 대회가 취소되었습니다.\n"
                f"(참가자: {count}명 / 최소: {config.TOURNAMENT_MIN_PLAYERS}명)\n\n"
                "스폰이 재개됩니다."
            ),
        )
        _reset_state()
        await _resume_spawns(context, chat_id)
        return

    await _safe_send(context.bot, chat_id,
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
    original_bracket = list(bracket)
    round_results = {}

    # Show bracket — ASCII tree for ≤16 players, text list for larger tournaments
    total_players = len(player_list)
    if total_players <= 16:
        tree = _render_bracket(bracket)
        if tree:
            await _safe_send(context.bot, chat_id,
                text=f"📋 대진표\n{tree}",
                parse_mode="HTML",
            )
    else:
        # Large tournament: show match list in chunks (Telegram 4096 char limit)
        lines = [f"📋 대진표 ({total_players}명 참가)"]
        for i, (bp1, bp2) in enumerate(bracket, 1):
            n1 = bp1[1]['name'] if bp1 else "부전승"
            n2 = bp2[1]['name'] if bp2 else "부전승"
            lines.append(f"{i}. {n1} vs {n2}")
            if len("\n".join(lines)) > 3500:
                await _safe_send(context.bot, chat_id, text="\n".join(lines))
                lines = [f"📋 대진표 (계속)"]
                await asyncio.sleep(1)
        if len(lines) > 1:
            await _safe_send(context.bot, chat_id, text="\n".join(lines))
    await asyncio.sleep(3)

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
                # Show bracket for this round
                bracket_lines = [f"📋 {round_name} 대진표", "━━━━━━━━━━━━━━━"]
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
                    text=f"\n📢 {round_name}",
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
                match_label = f"\n[ {match_num}번째 매치 ]" if match_count > 1 and not is_final else ""
                if p1 is None:
                    # p2 gets bye
                    uid2, data2 = p2
                    await _safe_send(context.bot, chat_id,
                        text=f"{match_label}\n🏃 {data2['name']} — 부전승!" if match_label else f"🏃 {data2['name']} — 부전승!",
                    )
                    winners.append(p2)
                    round_winner_names.append(data2['name'])
                elif p2 is None:
                    # p1 gets bye
                    uid1, data1 = p1
                    await _safe_send(context.bot, chat_id,
                        text=f"{match_label}\n🏃 {data1['name']} — 부전승!" if match_label else f"🏃 {data1['name']} — 부전승!",
                    )
                    winners.append(p1)
                    round_winner_names.append(data1['name'])
                else:
                    uid1, data1 = p1
                    uid2, data2 = p2

                    # Track semi-finalists for 4th place prize
                    if is_semi:
                        semi_finalists.add(uid1)
                        semi_finalists.add(uid2)

                    # Match label (e.g. "[ 1번째 매치 ]")
                    if match_label:
                        await _safe_send(context.bot, chat_id, text=match_label)
                        await asyncio.sleep(1)

                    winner_id, winner_data = await _run_match(
                        context, chat_id,
                        uid1, data1, uid2, data2,
                        is_final=is_final,
                        is_semi=is_semi,
                        is_quarter=is_quarter,
                    )
                    winners.append((winner_id, winner_data))
                    round_winner_names.append(winner_data['name'])
                    await asyncio.sleep(2)

            round_results[current_round] = round_winner_names

            if is_final:
                # Show final bracket tree with champion (skip if too large)
                if total_players <= 16:
                    tree = _render_bracket(original_bracket, round_results)
                    if tree and len(tree) < 4000:
                        await _safe_send(context.bot, chat_id,
                            text=f"📋 최종 대진표\n{tree}",
                            parse_mode="HTML",
                        )
                        await asyncio.sleep(3)
                # Tournament complete — give prizes
                if winners:
                    winner_uid, winner_d = winners[0]
                    await _award_prizes(context, chat_id, winner_uid, winner_d, bracket, semi_finalists)
                break

            # Show updated bracket after this round
            # Large tournaments: only show ASCII tree from quarterfinals onward
            if len(bracket) <= 8:
                tree = _render_bracket(original_bracket, round_results)
                if tree and len(tree) < 4000:
                    await _safe_send(context.bot, chat_id,
                        text=f"📋 대진표 ({round_name} 결과)\n{tree}",
                        parse_mode="HTML",
                    )
                    await asyncio.sleep(7)
            else:
                # Just show round summary for large early rounds
                summary = f"📋 {round_name} 종료 — {len(winners)}명 진출"
                await _safe_send(context.bot, chat_id, text=summary)
                await asyncio.sleep(3)

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
        await _safe_send(context.bot, chat_id,
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
        f"   {ball_emoji('masterball')} 마스터볼 {config.TOURNAMENT_PRIZE_1ST_MB}개 + {config.TOURNAMENT_PRIZE_1ST_BP} BP + 🎖️ 챔피언 칭호 (밥+1회)",
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

    await _safe_send(context.bot, chat_id,
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
