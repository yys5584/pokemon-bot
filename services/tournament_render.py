"""Tournament rendering: bracket display, switch-in lines, MVP, safe send helpers."""

import asyncio
import math
import random
import logging
import unicodedata
import re as _re

from telegram.error import RetryAfter

import config

logger = logging.getLogger(__name__)

# ── Emoji stripping ──────────────────────────────────────────
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
