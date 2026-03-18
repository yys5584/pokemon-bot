"""Tournament system: daily single-elimination in arcade channels."""

import asyncio
import math
import os
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
from utils.card_generator import generate_card, generate_lineup_card, generate_battle_card

# ── Bracket Tree Renderer ──────────────────────────────────────
import unicodedata


import re as _re
_EMOJI_RE = _re.compile(
    "["
    "\U0001F000-\U0001FFFF"  # SMP emoji (emoticons, symbols, flags, etc.)
    "\u2600-\u27BF"          # misc symbols & dingbats
    "\uFE00-\uFE0F"          # variation selectors
    "\u200D"                 # ZWJ
    "\u20E3"                 # combining enclosing keycap
    "\u2B05-\u2B55"          # arrows, circles
    "]+", _re.UNICODE
)


def _strip_emoji(s: str) -> str:
    """Remove emoji from string for monospace-safe rendering."""
    return _EMOJI_RE.sub("", s).strip()


def _dw(s: str) -> int:
    """Display width: CJK/fullwidth chars count as 2."""
    return sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in s)


def _rpad(s: str, target: int) -> str:
    """Right-pad string to target display width."""
    return s + ' ' * max(0, target - _dw(s))


def _trunc(s: str, max_dw: int = 8) -> str:
    """Truncate emoji-stripped string to max display width, adding … if needed.

    max_dw=8 → 한글 4자(dw8) / 영어 7자+… / 혼합도 안전.
    """
    s = _strip_emoji(s)
    if not s:
        s = "?"
    w = 0
    for i, c in enumerate(s):
        cw = 2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1
        if w + cw > max_dw - 1:  # leave room for …
            return s[:i] + "…"
        w += cw
    return s


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
        players.append(_trunc(p1[1]['name']) if p1 else "부전승")
        players.append(_trunc(p2[1]['name']) if p2 else "부전승")

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
                winner = _trunc(w)

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


# ── Switch-in lines (randomly picked, tiered) ─────────────────
_SWITCH_NORMAL = [
    "{trainer}: {dead} 돌아와! 가라, {next}!",
    "{trainer}: {dead} 수고했어! {next}, 네 차례야!",
    "{trainer}: {dead} 돌아와! 부탁해, {next}!",
    "{trainer}: {dead} 잘 싸웠어! {next}, 출발!",
    "{trainer}: {dead} 고생했어! 가자, {next}!",
    "{trainer}: {next}, 출동!",
    "{trainer}: 좋아, {next} 네가 해줘!",
    "{trainer}: {dead} 충분해! {next}, 나가!",
    "{trainer}: 교대! {next}, 준비됐지?",
    "{trainer}: {next}, 힘내자!",
    "{trainer}: {dead} 물러나! {next}, 가!",
    "{trainer}: 다음은 {next}, 네 차례야!",
    "{trainer}: {next}, 믿고 있어!",
    "{trainer}: {dead} 쉬어! 나가, {next}!",
    "{trainer}: 자, {next}! 보여줘!",
    "{trainer}: {dead} 돌아와! {next}, 파이팅!",
    "{trainer}: 가자 {next}, 할 수 있어!",
    "{trainer}: {next}, 부탁할게!",
    "{trainer}: 좋아 {next}, 네 차례다!",
    "{trainer}: {dead} 수고! {next}, 출격!",
]

_SWITCH_EPIC = [
    "{trainer}: {next}, 실력을 보여줘!",
    "{trainer}: 여기서부터 본게임이다, 가라 {next}!",
    "{trainer}: {next}, 네 힘을 믿는다!",
    "{trainer}: 에이스 투입! {next}, 출격!",
    "{trainer}: {dead} 고생했어, {next} 각오해라!",
    "{trainer}: {next}! 전력으로 간다!",
    "{trainer}: 여기서 밀릴 수 없어, {next}!",
    "{trainer}: 자, {next}! 흐름을 바꿔줘!",
    "{trainer}: {next}, 네가 아니면 안 돼!",
    "{trainer}: 주력이다! 나와라, {next}!",
    "{trainer}: 분위기 반전! {next}, 간다!",
    "{trainer}: {next}, 승부를 걸어줘!",
    "{trainer}: 지금이야! 나와, {next}!",
    "{trainer}: 핵심 전력 투입, {next}!",
    "{trainer}: {next}, 제대로 보여주자!",
    "{trainer}: 여기서 끝낸다! {next}, 출동!",
    "{trainer}: 숨겨둔 패다, 가라 {next}!",
    "{trainer}: {next}, 진짜 실력을 보여줄 때야!",
    "{trainer}: 이제 본격적으로 간다! {next}!",
    "{trainer}: {dead} 수고했어, {next} 짓밟아줘!",
]

_SWITCH_LEGENDARY = [
    "{trainer}: 가라, {next}! 여기서 끝내자!",
    "{trainer}: 마지막 카드다, {next}!",
    "{trainer}: {next}, 네가 나올 차례야!",
    "{trainer}: {dead} 고생했어. {next}, 정리해줘!",
    "{trainer}: 여기서 밀리면 안 돼, {next} 간다!",
    "{trainer}: {next}! 이거 하나만 부탁한다!",
    "{trainer}: 이제 진짜다, 나와 {next}!",
    "{trainer}: {next}, 확실하게 끝장내자!",
    "{trainer}: 비장의 한 수, {next} 가!",
    "{trainer}: {next}, 뒤집어줘!",
    "{trainer}: 아끼고 있었다, {next} 지금이야!",
    "{trainer}: {next}, 네가 아니면 답이 없어!",
    "{trainer}: 여기까지 왔잖아, {next} 부탁해!",
    "{trainer}: {next}, 끝을 보자!",
    "{trainer}: 나와라 {next}, 밀어붙여!",
    "{trainer}: 이쯤에서 끝내지, {next} 가자!",
    "{trainer}: 한방이면 충분해, {next}!",
    "{trainer}: {next}, 보여줄 게 있잖아!",
    "{trainer}: 숨겨둔 패다, {next} 출격!",
    "{trainer}: {next}, 지금 안 나오면 언제 나와!",
]

_SWITCH_ULTRA = [
    "{trainer}: {next}, 끝장내자.",
    "{trainer}: {next}. 더 말할 것도 없지.",
    "{trainer}: 나와라 {next}, 쓸어버려.",
    "{trainer}: {next}, 네가 나오면 끝이야.",
    "{trainer}: 마지막이다, {next} 가.",
    "{trainer}: {next}. 밟아줘.",
    "{trainer}: {next}, 정리하고 와.",
    "{trainer}: 다 필요없고, {next} 간다.",
    "{trainer}: {next}. 조용히 끝내자.",
    "{trainer}: 이제 됐어, {next} 나와.",
    "{trainer}: {next}, 마무리 부탁해.",
    "{trainer}: {next}, 깔끔하게.",
    "{trainer}: 최종병기 {next}, 투입.",
    "{trainer}: {next}. 아직 안 끝났거든.",
    "{trainer}: {next}, 한 방이면 돼.",
    "{trainer}: {next}, 네가 나서면 끝이잖아.",
    "{trainer}: {next}. 이번엔 확실하게.",
    "{trainer}: 오래 기다렸지? {next}, 가.",
    "{trainer}: {next}, 이제 네 시간이야.",
    "{trainer}: {next} 나간다.",
]

# ── Dramatic entrance effects (4강/결승 전용) ────────────────────
_DRAMATIC_SERIOUS = [
    "🔥 {trainer}: {next}, 여기서 지면 끝이야! 가자!",
    "🔥 {trainer}: 여기까지 왔는데 질 수 없지! {next}!",
    "🌟 {trainer}: 아직 안 끝났어! {next}, 뒤집어!",
    "💫 {trainer}: 마지막 한 방, {next} 부탁해!",
    "💥 {trainer}: {next}, 이 경기 네가 끝내줘!",
    "🔥 {trainer}: 지금 아니면 언제! {next}!",
    "💥 {trainer}: 우승까지 한 발, {next} 간다!",
]
_DRAMATIC_JOKE = []

# ── 우승 소감 ────────────────────────────────────────
_WINNER_SPEECHES = [
    "\"중요한 것은 꺾이지 않는 마음입니다.\"\n— {trainer}",
    "\"다 계획이 있었습니다.\"\n— {trainer}",
    "\"{mvp}는 노력하는 천재입니다.\"\n— {trainer}",
    "\"연습은 거짓말을 하지 않습니다.\"\n— {trainer}",
    "\"나보다 더 땀 흘린 트레이너가 있다면 우승컵 가져가도 좋다.\"\n— {trainer}",
    "\"99도까지 올려놓아도 마지막 1도를 못 넘기면 물은 안 끓습니다.\"\n— {trainer}",
    "\"9000번 넘게 졌지만, 그게 제가 우승한 이유입니다.\"\n— {trainer}",
]
# 날짜 고정 소감 (특별 이벤트용)
_WINNER_SPEECH_OVERRIDE: dict[str, str] = {
    "2026-03-15": "\"우리 {mvp} 월클 아닙니다. 하지만 오늘만큼은 월클입니다.\"\n— {trainer}",
}


def _get_mvp_name(turn_data: list[dict], winner_side: str) -> str:
    """MVP 포켓몬 이름만 반환."""
    dmg_by_name: dict[str, int] = {}
    kills_by_name: dict[str, int] = {}
    for td in turn_data:
        if td["type"] == "turn":
            if winner_side == "challenger":
                name, dmg = td["c_name"], td["c_dmg"]
            else:
                name, dmg = td["d_name"], td["d_dmg"]
            dmg_by_name[name] = dmg_by_name.get(name, 0) + dmg
        elif td["type"] == "ko" and td["side"] != winner_side:
            if winner_side == "challenger":
                cur = None
                for prev in turn_data:
                    if prev is td:
                        break
                    if prev["type"] == "matchup":
                        cur = prev["c_name"]
                if cur:
                    kills_by_name[cur] = kills_by_name.get(cur, 0) + 1
            else:
                cur = None
                for prev in turn_data:
                    if prev is td:
                        break
                    if prev["type"] == "matchup":
                        cur = prev["d_name"]
                if cur:
                    kills_by_name[cur] = kills_by_name.get(cur, 0) + 1
    if not dmg_by_name:
        return "???"
    return max(dmg_by_name, key=lambda n: (dmg_by_name[n], kills_by_name.get(n, 0)))


def _winner_speech(trainer: str, mvp_name: str) -> str:
    """우승 소감 생성. 날짜 고정 있으면 우선."""
    today = config.get_kst_now().strftime("%Y-%m-%d")
    template = _WINNER_SPEECH_OVERRIDE.get(today)
    if not template:
        template = random.choice(_WINNER_SPEECHES)
    return template.format(trainer=trainer, mvp=mvp_name)


def _switch_line(trainer: str, dead: str, next_name: str,
                 next_rarity: str = "", dramatic: str = "") -> str:
    """Pick a random switch-in line based on next pokemon's rarity.

    dramatic: "" (none), "serious" (8강), "full" (4강/결승, includes jokes).
    """
    if next_rarity == "ultra_legendary":
        pool = _SWITCH_ULTRA
    elif next_rarity == "legendary":
        pool = _SWITCH_LEGENDARY
    elif next_rarity == "epic":
        pool = _SWITCH_EPIC
    else:
        pool = _SWITCH_NORMAL
    line = random.choice(pool).format(trainer=trainer, dead=dead, next=next_name)
    if dramatic:
        d_pool = _DRAMATIC_SERIOUS + _DRAMATIC_JOKE if dramatic == "full" else _DRAMATIC_SERIOUS
        effect = random.choice(d_pool).format(trainer=trainer, next=next_name)
        line = f"{line}\n{effect}"
    return line


def _extract_mvp(turn_data: list[dict], winner_side: str) -> str | None:
    """Extract MVP Pokemon line from turn_data for the winning side.

    Returns formatted string like "⭐ MVP: 리자몽 (딜 482 / 킬 3)" or None.
    """
    # Track damage dealt and kills per pokemon name on each side
    dmg_by_name: dict[str, int] = {}   # name -> total damage
    kills_by_name: dict[str, int] = {}  # name -> kill count

    # Current active pokemon names per side (for attributing kills)
    current_c_name = None
    current_d_name = None

    for td in turn_data:
        if td["type"] == "matchup":
            current_c_name = td["c_name"]
            current_d_name = td["d_name"]

        elif td["type"] == "turn":
            if winner_side == "challenger":
                name = td["c_name"]
                dmg = td["c_dmg"]
            else:
                name = td["d_name"]
                dmg = td["d_dmg"]
            dmg_by_name[name] = dmg_by_name.get(name, 0) + dmg

        elif td["type"] == "ko":
            # Who killed this pokemon?
            # side = which side's pokemon died
            if td["side"] != winner_side:
                # Enemy pokemon died → attribute kill to our current active pokemon
                if winner_side == "challenger" and current_c_name:
                    kills_by_name[current_c_name] = kills_by_name.get(current_c_name, 0) + 1
                elif winner_side == "defender" and current_d_name:
                    kills_by_name[current_d_name] = kills_by_name.get(current_d_name, 0) + 1

    if not dmg_by_name:
        return None

    # Pick MVP: highest damage, tiebreak by kills
    mvp_name = max(dmg_by_name, key=lambda n: (dmg_by_name[n], kills_by_name.get(n, 0)))
    total_dmg = dmg_by_name[mvp_name]
    total_kills = kills_by_name.get(mvp_name, 0)

    if total_kills > 0:
        return f"⭐ MVP: {mvp_name} (딜 {total_dmg} / 킬 {total_kills})"
    else:
        return f"⭐ MVP: {mvp_name} (딜 {total_dmg})"


async def _safe_send(bot, chat_id, text, **kwargs):
    """send_message with RetryAfter/TimedOut/NetworkError auto-retry + auto-split."""
    from telegram.error import TimedOut, NetworkError, BadRequest
    for attempt in range(5):
        try:
            return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
        except BadRequest as e:
            if "too long" in str(e).lower():
                # 메시지가 너무 길면 분할 전송
                return await _split_send(bot, chat_id, text, **kwargs)
            raise
        except RetryAfter as e:
            wait = e.retry_after + 1
            logger.warning(f"Flood control, waiting {wait}s (attempt {attempt+1})")
            await asyncio.sleep(wait)
        except (TimedOut, NetworkError) as e:
            wait = 3 * (attempt + 1)
            logger.warning(f"Network error in _safe_send: {e}, retry in {wait}s (attempt {attempt+1})")
            await asyncio.sleep(wait)
    # last attempt without catch
    return await bot.send_message(chat_id=chat_id, text=text, **kwargs)


async def _split_send(bot, chat_id, text, **kwargs):
    """긴 메시지를 4000자 단위로 분할 전송."""
    MAX_LEN = 4000
    lines = text.split("\n")
    chunks = []
    current = []
    current_len = 0

    for line in lines:
        # 한 줄이 MAX_LEN 초과 시 강제 분할
        while len(line) > MAX_LEN:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            chunks.append(line[:MAX_LEN])
            line = line[MAX_LEN:]

        line_len = len(line) + 1  # +1 for \n
        if current_len + line_len > MAX_LEN and current:
            chunks.append("\n".join(current))
            current = [line]
            current_len = line_len
        else:
            current.append(line)
            current_len += line_len
    if current:
        chunks.append("\n".join(current))

    # HTML 태그 보정: <pre> 등이 청크 사이에서 잘리면 닫기/열기 보정
    if kwargs.get("parse_mode", "").upper() == "HTML":
        for i in range(len(chunks)):
            c = chunks[i]
            open_pre = c.count("<pre>")
            close_pre = c.count("</pre>")
            if open_pre > close_pre:
                chunks[i] = c + "</pre>"
            elif close_pre > open_pre:
                chunks[i] = "<pre>" + c

    from telegram.error import TimedOut, NetworkError, RetryAfter
    last_msg = None
    for chunk in chunks:
        for attempt in range(5):
            try:
                last_msg = await bot.send_message(chat_id=chat_id, text=chunk, **kwargs)
                break
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
            except (TimedOut, NetworkError):
                await asyncio.sleep(3 * (attempt + 1))
        else:
            last_msg = await bot.send_message(chat_id=chat_id, text=chunk, **kwargs)
    return last_msg


async def _safe_send_photo(bot, chat_id, photo, caption="", **kwargs):
    """send_photo with RetryAfter/TimedOut/NetworkError auto-retry. Falls back to text on failure."""
    from telegram.error import TimedOut, NetworkError
    for attempt in range(5):
        try:
            return await bot.send_photo(chat_id=chat_id, photo=photo, caption=caption, **kwargs)
        except RetryAfter as e:
            wait = e.retry_after + 1
            logger.warning(f"Flood control (photo), waiting {wait}s (attempt {attempt+1})")
            await asyncio.sleep(wait)
        except (TimedOut, NetworkError) as e:
            wait = 3 * (attempt + 1)
            logger.warning(f"Network error in _safe_send_photo: {e}, retry in {wait}s (attempt {attempt+1})")
            await asyncio.sleep(wait)
        except Exception as e:
            logger.warning(f"send_photo failed (attempt {attempt+1}): {e}")
            return await _safe_send(bot, chat_id, caption, **kwargs)
    # last attempt — fallback to text if photo still fails
    try:
        return await bot.send_photo(chat_id=chat_id, photo=photo, caption=caption, **kwargs)
    except Exception:
        return await _safe_send(bot, chat_id, caption, **kwargs)


from utils.helpers import icon_emoji, ball_emoji, rarity_badge, shiny_emoji

logger = logging.getLogger(__name__)

# ── In-memory tournament state ──────────────────────────────────
_tournament_state = {
    "registering": False,
    "running": False,
    "participants": {},       # {user_id: {"name": str, "team": list[dict]}}
    "chat_id": None,
}


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
    chat_id = config.TOURNAMENT_CHAT_ID
    if not chat_id:
        logger.warning("No tournament chat configured, skipping tournament.")
        return

    _reset_state()
    await _clear_registrations_db()
    _tournament_state["registering"] = True
    _tournament_state["chat_id"] = chat_id

    # Cancel all spawn jobs for this chat (normal + arcade)
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
            "🕘 등록 시간: 지금 ~ 21:50\n"
            "📋 참가 방법: ㄷ 입력\n"
            "⚔️ 배틀팀이 등록되어 있어야 참가 가능!\n\n"
            "🏆 보상\n"
            f"  🥇 우승: 마스터볼 {config.TOURNAMENT_PRIZE_1ST_MB}개 + {config.TOURNAMENT_PRIZE_1ST_BP:,}BP + ✨이로치(초전설+일반) + 챔피언 칭호\n"
            f"  🥈 준우승: 마스터볼 {config.TOURNAMENT_PRIZE_2ND_MB}개 + {config.TOURNAMENT_PRIZE_2ND_BP:,}BP + ✨이로치(전설+일반)\n"
            f"  🏅 4강: 마스터볼 {config.TOURNAMENT_PRIZE_SEMI_MB}개 + {config.TOURNAMENT_PRIZE_SEMI_BP:,}BP + ✨이로치(에픽)\n"
            f"  🎟️ 참가: 마스터볼 {config.TOURNAMENT_PRIZE_PARTICIPANT_MB}개 + {config.TOURNAMENT_PRIZE_PARTICIPANT_BP:,}BP\n\n"
            "스폰은 대회 종료 후 재개됩니다."
        ),
    )
    logger.info(f"Tournament registration started for chat {chat_id}")

    # Send DM notification to all users
    if not os.path.exists("/tmp/skip_tournament_dm"):
        asyncio.create_task(_broadcast_tournament_dm(context))
    else:
        os.remove("/tmp/skip_tournament_dm")
        logger.info("Skipped tournament DM broadcast (flag file)")


async def _broadcast_tournament_dm(context: ContextTypes.DEFAULT_TYPE):
    """Send DM to all registered users about tournament registration."""
    try:
        user_ids = await queries.get_recently_active_user_ids(minutes=240)
        logger.info(f"Broadcasting tournament DM to {len(user_ids)} users")

        _mb = ball_emoji("masterball")
        _se = shiny_emoji()
        _bt = icon_emoji("battle")
        msg = (
            f"{_bt} 아케이드 토너먼트 개최!\n\n"
            "⏰ 21:00~21:50 등록 / 22:00 대회 시작\n"
            f"{icon_emoji('bookmark')} 아래 채널에서 ㄷ 입력으로 참가!\n"
            f"👉 {config.BOT_CHANNEL_URL}\n\n"
            f"{_bt} 배틀팀 필수 — DM에서 '팀등록'으로 구성\n\n"
            f"{icon_emoji('crown')} 우승: {_mb}마스터볼 {config.TOURNAMENT_PRIZE_1ST_MB}개 + 💰{config.TOURNAMENT_PRIZE_1ST_BP:,}BP + {_se}이로치(초전설+일반) + 챔피언 칭호\n"
            f"🥈 준우승: {_mb}마스터볼 {config.TOURNAMENT_PRIZE_2ND_MB}개 + 💰{config.TOURNAMENT_PRIZE_2ND_BP:,}BP + {_se}이로치(전설+일반)\n"
            f"{icon_emoji('champion')} 4강: {_mb}마스터볼 {config.TOURNAMENT_PRIZE_SEMI_MB}개 + 💰{config.TOURNAMENT_PRIZE_SEMI_BP:,}BP + {_se}이로치(에픽)\n"
            f"{icon_emoji('gotcha')} 참가: {_mb}마스터볼 {config.TOURNAMENT_PRIZE_PARTICIPANT_MB}개 + 💰{config.TOURNAMENT_PRIZE_PARTICIPANT_BP:,}BP"
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

    # Check battle team exists + cost validation
    team = await bq.get_battle_team(user_id)
    if not team:
        return False, "배틀팀이 없습니다! DM에서 '팀등록'으로 팀을 먼저 구성하세요."

    total_cost = sum(config.RANKED_COST.get(p.get("rarity", ""), 0) for p in team)
    if total_cost > config.RANKED_COST_LIMIT:
        return False, (
            f"❌ 팀 코스트 초과! ({total_cost}/{config.RANKED_COST_LIMIT})\n"
            f"코스트 {config.RANKED_COST_LIMIT} 이하로 편성해주세요."
        )

    _tournament_state["participants"][user_id] = {
        "name": display_name,
        "team": None,  # will be snapshotted at 21:50
    }
    await _save_registration_db(user_id, display_name)

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
    cost_removed = []
    for user_id, data in list(participants.items()):
        team = await bq.get_battle_team(user_id)
        if not team:
            removed.append(data["name"])
            del participants[user_id]
        else:
            total_cost = sum(config.RANKED_COST.get(p.get("rarity", ""), 0) for p in team)
            if total_cost > config.RANKED_COST_LIMIT:
                cost_removed.append(f"{data['name']}({total_cost})")
                del participants[user_id]
            else:
                data["team"] = team

    # Close registration after snapshot
    _tournament_state["registering"] = False

    lines = [
        f"⚔️ 배틀팀 확정! ({len(participants)}명)",
        "━━━━━━━━━━━━━━━",
        "대회 접수가 마감되었습니다.",
    ]
    if removed:
        lines.append(f"\n⚠️ 팀 미등록으로 제외: {', '.join(removed)}")
    if cost_removed:
        lines.append(f"\n⚠️ 코스트 초과로 제외: {', '.join(cost_removed)}")

    await _safe_send(context.bot, chat_id, text="\n".join(lines))


# ── Group Stage (for 17+ players) ─────────────────────────────

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


# ── GIF Round Builder ──────────────────────────────────────────

_DRAMATIC_COMMENTS = [
    "간다!", "이번엔 진다!", "아직이야!", "크윽...", "다음은 내 차례!",
    "이 정도쯤이야!", "마지막이다!", "각오해라!", "여기서 끝이야!",
]

def _build_gif_rounds(turn_data: list[dict], p1_data: dict, p2_data: dict) -> list[dict]:
    """turn_data → generate_tournament_battle_gif용 rounds 리스트 변환."""
    import random as _rnd
    rounds = []
    current_matchup = None
    current_turns = []

    for td in turn_data:
        if td["type"] == "matchup":
            # 이전 매치업 저장
            if current_matchup and current_turns:
                rounds.append(_matchup_to_round(current_matchup, current_turns, p1_data, p2_data))
            current_matchup = td
            current_turns = []
        elif td["type"] == "turn":
            current_turns.append(td)
        elif td["type"] == "ko":
            current_turns.append(td)

    # 마지막 매치업
    if current_matchup and current_turns:
        rounds.append(_matchup_to_round(current_matchup, current_turns, p1_data, p2_data))

    # 멘트 배분 (홀수 라운드에 before, 짝수에 after)
    comments = list(_DRAMATIC_COMMENTS)
    _rnd.shuffle(comments)
    for i, rd in enumerate(rounds):
        if i > 0 and i < len(comments):
            rd["comment_before"] = comments[i]

    return rounds


def _matchup_to_round(matchup: dict, turns: list[dict], p1_data: dict, p2_data: dict) -> dict:
    """단일 매치업(1v1)의 turn_data → GIF round dict 변환."""
    # 총 데미지 집계
    total_c_dmg = sum(t.get("c_dmg", 0) for t in turns if t["type"] == "turn")
    total_d_dmg = sum(t.get("d_dmg", 0) for t in turns if t["type"] == "turn")
    has_crit = any(t.get("c_crit") or t.get("d_crit") for t in turns if t["type"] == "turn")

    # KO 판정
    ko_side = None
    for t in turns:
        if t["type"] == "ko":
            ko_side = t["side"]
            break

    # winner: p1이 challenger
    if ko_side == "defender":
        winner = "p1"  # 적(defender) 쓰러짐 → p1 승리
    elif ko_side == "challenger":
        winner = "p2"
    else:
        winner = "p1"  # 기본

    return {
        "p1_id": matchup.get("c_pokemon_id", 1),
        "p1_poke": matchup["c_name"],
        "p1_rarity": matchup.get("c_rarity", "common"),
        "p1_shiny": matchup.get("c_shiny", False),
        "p2_id": matchup.get("d_pokemon_id", 1),
        "p2_poke": matchup["d_name"],
        "p2_rarity": matchup.get("d_rarity", "common"),
        "p2_shiny": matchup.get("d_shiny", False),
        "winner": winner,
        "damage_dealt": total_c_dmg,
        "damage_taken": total_d_dmg,
        "crit": has_crit,
    }


# ── Match Execution ─────────────────────────────────────────────

async def _run_match(
    context, chat_id: int,
    p1_id: int, p1_data: dict,
    p2_id: int, p2_data: dict,
    is_final: bool = False,
    is_semi: bool = False,
    is_quarter: bool = False,
    match_label: str = "",
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

    winner_side = result["winner"]
    if winner_side == "challenger":
        winner_id, winner_data = p1_id, p1_data
        remaining = result["challenger_remaining"]
    else:
        winner_id, winner_data = p2_id, p2_data
        remaining = result["defender_remaining"]

    # MVP line
    mvp_line = _extract_mvp(result["turn_data"], winner_side)

    # Helper: team marker for KO/next based on side
    def _mark(side):
        return C if side == "challenger" else D

    # Helper: build matchup sections from turn_data (with global offsets)
    def _build_sections(turn_data):
        sections, cur, offsets, cur_off = [], [], [], 0
        for i, td in enumerate(turn_data):
            if td["type"] == "matchup" and cur:
                sections.append(cur)
                offsets.append(cur_off)
                cur = [td]
                cur_off = i
            else:
                if not cur:
                    cur_off = i
                cur.append(td)
        if cur:
            sections.append(cur)
            offsets.append(cur_off)
        return sections, offsets

    # Helper: format a section into lines — with HP bars
    # dramatic_mode: "" (none), "serious" (8강), "full" (4강/결승)
    def _format_section(section, dramatic_mode="", offset=0):
        lines = []
        c_trainer = p1_data['name']
        d_trainer = p2_data['name']
        for j, td in enumerate(section):
            global_idx = offset + j
            if td["type"] == "matchup":
                c_sh = f"{shiny_emoji()}" if td.get("c_shiny") else ""
                d_sh = f"{shiny_emoji()}" if td.get("d_shiny") else ""
                lines.append(f"<b>⚔ {C}{td['c_tb']}{c_sh}{td['c_name']}({td['c_idx']+1}/{td['c_total']}) vs {D}{td['d_tb']}{d_sh}{td['d_name']}({td['d_idx']+1}/{td['d_total']})</b>")
            elif td["type"] == "turn":
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
                    is_last = (global_idx == _last_switch_idx[td["side"]])
                    dm = dramatic_mode if is_last else ""
                    lines.append(f"{SKULL} {m}{td['dead_name']} 쓰러짐!")
                    lines.append(_switch_line(trainer, td['dead_name'], td['next_name'], td.get('next_rarity', ''), dramatic=dm))
                else:
                    lines.append(f"{SKULL} {m}{td['dead_name']} 쓰러짐!")
        return lines

    # Pre-scan: find last switch-in index for each side (dramatic entrance)
    _last_switch_idx = {"challenger": -1, "defender": -1}
    for _i, _td in enumerate(result["turn_data"]):
        if _td["type"] == "ko" and _td["next_name"]:
            _last_switch_idx[_td["side"]] = _i

    if is_final:
        # ── Finals: each hit as separate message (3s delay) ──
        p1_name = p1_data['name']
        p2_name = p2_data['name']

        # Lineup card image
        try:
            lineup_data_1 = [
                {"pokemon_id": m["pokemon_id"], "name": m["name"],
                 "rarity": m["rarity"], "is_shiny": m.get("is_shiny", False)}
                for m in team1
            ]
            lineup_data_2 = [
                {"pokemon_id": m["pokemon_id"], "name": m["name"],
                 "rarity": m["rarity"], "is_shiny": m.get("is_shiny", False)}
                for m in team2
            ]
            loop = asyncio.get_event_loop()
            lineup_buf = await loop.run_in_executor(
                None, generate_lineup_card, p1_name, lineup_data_1, p2_name, lineup_data_2
            )
            await _safe_send_photo(
                context.bot, chat_id, photo=lineup_buf,
                caption=f"🏆 결승전! — {p1_name} vs {p2_name}",
                parse_mode="HTML",
            )
        except Exception:
            logger.error("Failed to generate lineup card", exc_info=True)
            await _safe_send(context.bot, chat_id,
                text=(
                    f"🏆 결승전!\n"
                    f"{C}{p1_name} vs {D}{p2_name}\n"
                    f"━━━━━━━━━━━━━━━"
                ),
                parse_mode="HTML",
            )
        await asyncio.sleep(3)

        for _i, td in enumerate(result["turn_data"]):
            if td["type"] == "matchup":
                await _safe_send(context.bot, chat_id,
                    text=f"⚔ {C}{td['c_tb']}{td['c_name']}({td['c_idx']+1}/{td['c_total']}) vs {D}{td['d_tb']}{td['d_name']}({td['d_idx']+1}/{td['d_total']})!",
                    parse_mode="HTML",
                )
                await asyncio.sleep(3)

            elif td["type"] == "turn":
                if td["first_is_challenger"]:
                    first_mark, second_mark = C, D
                    first_name, first_dmg, first_crit, first_eff = td["c_name"], td["c_dmg"], td["c_crit"], td["c_eff"]
                    second_name, second_dmg, second_crit, second_eff = td["d_name"], td["d_dmg"], td["d_crit"], td["d_eff"]
                    first_target_hp, first_target_max = td["d_hp"], td["d_max_hp"]
                    second_target_hp, second_target_max = td["c_hp"], td["c_max_hp"]
                    first_target_name, second_target_name = td["d_name"], td["c_name"]
                    first_target_mark, second_target_mark = D, C
                    first_pid, first_rarity, first_shiny = td.get("c_pokemon_id"), td.get("c_rarity", "common"), td.get("c_shiny", False)
                    second_pid, second_rarity, second_shiny = td.get("d_pokemon_id"), td.get("d_rarity", "common"), td.get("d_shiny", False)
                else:
                    first_mark, second_mark = D, C
                    first_name, first_dmg, first_crit, first_eff = td["d_name"], td["d_dmg"], td["d_crit"], td["d_eff"]
                    second_name, second_dmg, second_crit, second_eff = td["c_name"], td["c_dmg"], td["c_crit"], td["c_eff"]
                    first_target_hp, first_target_max = td["c_hp"], td["c_max_hp"]
                    second_target_hp, second_target_max = td["d_hp"], td["d_max_hp"]
                    first_target_name, second_target_name = td["c_name"], td["d_name"]
                    first_target_mark, second_target_mark = C, D
                    first_pid, first_rarity, first_shiny = td.get("d_pokemon_id"), td.get("d_rarity", "common"), td.get("d_shiny", False)
                    second_pid, second_rarity, second_shiny = td.get("c_pokemon_id"), td.get("c_rarity", "common"), td.get("c_shiny", False)

                # First attack — battle scene image for skills
                crit_label = " 크리티컬!" if first_crit else ""
                skill_label = f" {first_eff}!" if first_eff else " 공격!"
                bar = _hp_bar(first_target_hp, first_target_max)
                caption1 = f"{td['turn_num']}턴 ─ {first_name}{skill_label}{crit_label}\n  → {first_target_name} {bar} {first_target_hp}/{first_target_max} (-{first_dmg})"
                if first_eff and first_pid:
                    # Extract skill name from eff string (e.g. "「화염방사」효과는..." → "화염방사")
                    _skill_name = first_eff
                    if "「" in _skill_name:
                        _skill_name = _skill_name.split("「")[1].split("」")[0]
                    # Get attacker type for FX
                    from models.pokemon_battle_data import POKEMON_BATTLE_DATA
                    _atk_type = POKEMON_BATTLE_DATA.get(first_pid, ("normal",))[0]
                    # Target pokemon id
                    _def_pid = td.get("d_pokemon_id") if td["first_is_challenger"] else td.get("c_pokemon_id")
                    _def_shiny = td.get("d_shiny", False) if td["first_is_challenger"] else td.get("c_shiny", False)
                    loop = asyncio.get_event_loop()
                    card_buf = await loop.run_in_executor(
                        None, generate_battle_card,
                        first_pid, first_name, _def_pid, first_target_name,
                        _skill_name, _atk_type, first_dmg,
                        first_shiny, _def_shiny,
                    )
                    await _safe_send_photo(context.bot, chat_id, photo=card_buf, caption=caption1, parse_mode="HTML")
                    await asyncio.sleep(3)
                else:
                    await _safe_send(context.bot, chat_id, text=caption1, parse_mode="HTML")
                    await asyncio.sleep(3)

                # Counter attack — battle scene image for skills
                if second_dmg > 0:
                    crit2_label = " 크리티컬!" if second_crit else ""
                    skill2_label = f" {second_eff}!" if second_eff else " 반격!"
                    bar2 = _hp_bar(second_target_hp, second_target_max)
                    caption2 = f"{second_name}{skill2_label}{crit2_label}\n  → {second_target_name} {bar2} {second_target_hp}/{second_target_max} (-{second_dmg})"
                    if second_eff and second_pid:
                        _skill_name2 = second_eff
                        if "「" in _skill_name2:
                            _skill_name2 = _skill_name2.split("「")[1].split("」")[0]
                        from models.pokemon_battle_data import POKEMON_BATTLE_DATA
                        _atk_type2 = POKEMON_BATTLE_DATA.get(second_pid, ("normal",))[0]
                        _def_pid2 = td.get("c_pokemon_id") if td["first_is_challenger"] else td.get("d_pokemon_id")
                        _def_shiny2 = td.get("c_shiny", False) if td["first_is_challenger"] else td.get("d_shiny", False)
                        loop = asyncio.get_event_loop()
                        card_buf2 = await loop.run_in_executor(
                            None, generate_battle_card,
                            second_pid, second_name, _def_pid2, second_target_name,
                            _skill_name2, _atk_type2, second_dmg,
                            second_shiny, _def_shiny2,
                        )
                        await _safe_send_photo(context.bot, chat_id, photo=card_buf2, caption=caption2, parse_mode="HTML")
                        await asyncio.sleep(3)
                    else:
                        await _safe_send(context.bot, chat_id, text=caption2, parse_mode="HTML")
                        await asyncio.sleep(3)

            elif td["type"] == "ko":
                m = _mark(td["side"])
                trainer = p1_name if td["side"] == "challenger" else p2_name
                if td["next_name"]:
                    dm = "full" if (_i == _last_switch_idx[td["side"]]) else ""
                    switch = _switch_line(trainer, td['dead_name'], td['next_name'], td.get('next_rarity', ''), dramatic=dm)
                    text = f"{SKULL} {m}{td['dead_name']} 쓰러짐!\n{switch}"
                else:
                    text = f"{SKULL} {m}{td['dead_name']} 쓰러짐!"
                await _safe_send(context.bot, chat_id, text=text, parse_mode="HTML")
                await asyncio.sleep(3)

        win_text = f"\n🎉 {winner_data['name']} 우승! (남은 {remaining}마리)"
        if mvp_line:
            win_text += f"\n{mvp_line}"
        await _safe_send(context.bot, chat_id, text=win_text)

        # 🎬 결승전 GIF 하이라이트
        try:
            from utils.card_generator import generate_tournament_battle_gif
            gif_rounds = _build_gif_rounds(result["turn_data"], p1_data, p2_data)
            if gif_rounds:
                loop = asyncio.get_event_loop()
                gif_buf = await loop.run_in_executor(
                    None, generate_tournament_battle_gif,
                    p1_name, p2_name, gif_rounds,
                )
                for _retry in range(3):
                    try:
                        await context.bot.send_animation(
                            chat_id=chat_id, animation=gif_buf,
                            caption="🎬 결승전 하이라이트",
                        )
                        break
                    except RetryAfter as e:
                        await asyncio.sleep(e.retry_after + 1)
                    except Exception:
                        break
                await asyncio.sleep(2)
        except Exception:
            logger.error("Failed to generate tournament GIF", exc_info=True)

        # 🎤 우승 인터뷰
        await asyncio.sleep(3)
        mvp_n = _get_mvp_name(result["turn_data"], winner_side)
        speech = _winner_speech(winner_data['name'], mvp_n)
        await _safe_send(context.bot, chat_id,
            text=f"🎤 <b>우승 인터뷰</b>\n\n{speech}",
            parse_mode="HTML",
        )

    elif is_semi:
        # ── Semi-finals: turn-by-turn, one message per turn (3s delay) ──
        p1_name = p1_data['name']
        p2_name = p2_data['name']
        await _safe_send(context.bot, chat_id,
            text=(
                f"⚔️ 준결승! — {C}{p1_name} vs {D}{p2_name}\n"
                f"━━━━━━━━━━━━━━━"
            ),
            parse_mode="HTML",
        )
        await asyncio.sleep(3)

        for _i, td in enumerate(result["turn_data"]):
            if td["type"] == "matchup":
                await _safe_send(context.bot, chat_id,
                    text=f"⚔ {C}{td['c_tb']}{td['c_name']}({td['c_idx']+1}/{td['c_total']}) vs {D}{td['d_tb']}{td['d_name']}({td['d_idx']+1}/{td['d_total']})!",
                    parse_mode="HTML",
                )
                await asyncio.sleep(3)

            elif td["type"] == "turn":
                lines = []
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
                bar = _hp_bar(first_target_hp, first_target_max)
                lines.append(f"{td['turn_num']}턴 ─ {first_mark}{first_name}{skill_label}{crit_label}")
                lines.append(f"  {first_target_mark}{first_target_name} {bar} {first_target_hp}/{first_target_max} (-{first_dmg})")

                if second_dmg > 0:
                    crit2_label = " 크리티컬!" if second_crit else ""
                    skill2_label = f" {second_eff}!" if second_eff else " 반격!"
                    bar2 = _hp_bar(second_target_hp, second_target_max)
                    lines.append(f"{second_mark}{second_name}{skill2_label}{crit2_label}")
                    lines.append(f"  {second_target_mark}{second_target_name} {bar2} {second_target_hp}/{second_target_max} (-{second_dmg})")

                await _safe_send(context.bot, chat_id, text="\n".join(lines), parse_mode="HTML")
                await asyncio.sleep(3)

            elif td["type"] == "ko":
                m = _mark(td["side"])
                trainer = p1_name if td["side"] == "challenger" else p2_name
                if td["next_name"]:
                    dm = "full" if (_i == _last_switch_idx[td["side"]]) else ""
                    switch = _switch_line(trainer, td['dead_name'], td['next_name'], td.get('next_rarity', ''), dramatic=dm)
                    text = f"{SKULL} {m}{td['dead_name']} 쓰러짐!\n{switch}"
                else:
                    text = f"{SKULL} {m}{td['dead_name']} 쓰러짐!"
                await _safe_send(context.bot, chat_id, text=text, parse_mode="HTML")
                await asyncio.sleep(3)

        win_text = f"→ {winner_data['name']} 승리! (남은 {remaining}마리)"
        if mvp_line:
            win_text += f"\n{mvp_line}"
        await _safe_send(context.bot, chat_id, text=win_text)

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

        sections, offsets = _build_sections(result["turn_data"])
        for section, off in zip(sections, offsets):
            lines = _format_section(section, dramatic_mode="serious", offset=off)
            if lines:
                await _safe_send(context.bot, chat_id, text="\n".join(lines), parse_mode="HTML")
                await asyncio.sleep(3)

        win_text = f"→ {winner_data['name']} 승리! (남은 {remaining}마리)"
        if mvp_line:
            win_text += f"\n{mvp_line}"
        await _safe_send(context.bot, chat_id, text=win_text)

    else:
        # ── Lower rounds: one-line summary (match_label + result combined) ──
        win_text = f"{match_label}⚔️ {p1_data['name']} vs {p2_data['name']} → {winner_data['name']} 승리!"
        if mvp_line:
            win_text += f"\n{mvp_line}"
        await _safe_send(context.bot, chat_id, text=win_text, parse_mode="HTML")

    return winner_id, winner_data


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
                text=f"📋 {round_label} 대진표 (본선)\n{tree}",
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
                    f"🏟️ 토너먼트 시작!\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"참가자: {count}명\n"
                    f"방식: 예선 {excess}경기 → {round_label} 본선\n\n"
                    f"예선전을 시작합니다..."
                ),
            )
            await asyncio.sleep(3)

            qualifiers = await _run_preliminary_round(context, chat_id, player_list, target)

            q_names = ", ".join(q[1]["name"] for q in qualifiers)
            await _safe_send(context.bot, chat_id,
                text=f"🏆 {round_label} 진출자\n━━━━━━━━━━━━━━━\n{q_names}",
            )
            await asyncio.sleep(5)

            bracket = _generate_bracket(qualifiers)
        else:
            await _safe_send(context.bot, chat_id,
                text=(
                    f"🏟️ 토너먼트 시작!\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"참가자: {count}명\n"
                    f"방식: 싱글 엘리미네이션\n\n"
                    f"대진표를 생성합니다..."
                ),
            )
            await asyncio.sleep(3)
            bracket = _generate_bracket(player_list)

        # Show bracket (ASCII tree)
        tree = _render_bracket(bracket)
        if tree and len(tree) < 4000:
            await _safe_send(context.bot, chat_id,
                text=f"📋 {round_label + ' ' if excess > 0 else ''}대진표\n{tree}",
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
                match_label = f"[ {match_num}번째 매치 ] " if match_count > 1 and not is_final else ""
                if p1 is None:
                    # p2 gets bye
                    uid2, data2 = p2
                    await _safe_send(context.bot, chat_id,
                        text=f"{match_label}🏃 {data2['name']} — 부전승!",
                    )
                    winners.append(p2)
                    round_winner_names.append(data2['name'])
                    await asyncio.sleep(3)
                elif p2 is None:
                    # p1 gets bye
                    uid1, data1 = p1
                    await _safe_send(context.bot, chat_id,
                        text=f"{match_label}🏃 {data1['name']} — 부전승!",
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
                        text=f"📋 최종 결과\n{tree}",
                        parse_mode="HTML",
                    )
                    await asyncio.sleep(3)
                # Tournament complete — give prizes
                if winners:
                    winner_uid, winner_d = winners[0]
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
            next_size = len(next_bracket) * 2
            next_label = "결승" if len(next_bracket) == 1 else (
                "준결승" if len(next_bracket) == 2 else f"{next_size}강"
            )
            tree = _render_bracket(next_bracket, {})
            if tree and len(tree) < 4000:
                await _safe_send(context.bot, chat_id,
                    text=f"📋 {next_label} 대진표\n{tree}",
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
                text="⚠️ 토너먼트 진행 중 오류가 발생했습니다.",
            )
        except Exception:
            logger.error("Failed to send tournament error message")

    # Cleanup
    _reset_state()
    await _clear_registrations_db()
    await _resume_spawns(context, chat_id)


def _random_shiny_pokemon(rarity: str) -> tuple[int, str]:
    """Pick a random pokemon of the given rarity. Returns (pokemon_id, name_ko)."""
    from models.pokemon_data import ALL_POKEMON
    candidates = [(p[0], p[1]) for p in ALL_POKEMON if p[4] == rarity]
    return random.choice(candidates)


async def _award_prizes(context, chat_id, winner_id, winner_data,
                        final_bracket, semi_finalists, all_participants,
                        eliminated=None):
    """Award prizes to top finishers + participation rewards.

    eliminated: dict mapping user_id -> round_size (16, 8, 4, 2) where they lost.
    """
    from utils.battle_calc import iv_total
    if eliminated is None:
        eliminated = {}

    # ── 1st place: master balls + BP + shiny legendary + shiny common + title ──
    try:
        await queries.add_master_ball(winner_id, config.TOURNAMENT_PRIZE_1ST_MB)
    except Exception:
        logger.error(f"Failed to give master balls to winner {winner_id}")
    try:
        await bq.add_bp(winner_id, config.TOURNAMENT_PRIZE_1ST_BP, "tournament")
    except Exception:
        logger.error(f"Failed to give BP to winner {winner_id}")
    await queries.increment_title_stat(winner_id, "tournament_wins")
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
    mb_emoji = ball_emoji('masterball')
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
        from utils.helpers import icon_emoji
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

        from database.connection import get_db
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
