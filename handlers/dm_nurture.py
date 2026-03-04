"""DM handlers for nurturing: 밥, 놀기, 진화."""

import logging
from telegram import Update
from telegram.ext import ContextTypes

import config
from database import queries
from services.evolution_service import try_evolve
from services.event_service import get_friendship_boost
from utils.helpers import hearts_display, type_badge
from utils.parse import parse_number, parse_name_arg, parse_select_index
from utils.battle_calc import iv_total

logger = logging.getLogger(__name__)


def _iv_grade_tag(p: dict) -> str:
    """Return IV grade string like ' [A]' for a pokemon dict."""
    if p.get("iv_hp") is None:
        return ""
    total = iv_total(p.get("iv_hp"), p.get("iv_atk"), p.get("iv_def"),
                     p.get("iv_spa"), p.get("iv_spdef"), p.get("iv_spd"))
    grade, _ = config.get_iv_grade(total)
    return f" [{grade}]"


async def _resolve_pokemon(update, user_id, text, cmd):
    """Resolve pokemon from text, handling duplicates.
    Returns (pokemon_dict, None) on success,
    or (None, True) if duplicate list was shown,
    or (None, None) if not found.
    """
    index = parse_number(text)
    name_arg = parse_name_arg(text)
    select_idx = parse_select_index(text)

    if index is not None:
        pokemon = await queries.get_user_pokemon_by_index(user_id, index)
        if not pokemon:
            await update.message.reply_text(
                f"'{index}' 포켓몬을 찾을 수 없습니다.\n내포켓몬 으로 목록을 확인하세요."
            )
            return None, None
        return pokemon, None

    if not name_arg:
        await update.message.reply_text(f"사용법: {cmd} [이름/번호]\n예: {cmd} 피카츄, {cmd} 3")
        return None, None

    all_matches = await queries.find_all_user_pokemon_by_name(user_id, name_arg)

    if not all_matches:
        await update.message.reply_text(
            f"'{name_arg}' 포켓몬을 찾을 수 없습니다.\n내포켓몬 으로 목록을 확인하세요."
        )
        return None, None

    if len(all_matches) == 1:
        return all_matches[0], None

    # Multiple matches
    if select_idx is not None:
        if 1 <= select_idx <= len(all_matches):
            return all_matches[select_idx - 1], None
        await update.message.reply_text(f"잘못된 번호입니다. 1~{len(all_matches)} 사이를 입력하세요.")
        return None, None

    # Show selection list
    lines = [f"⚠️ {name_arg}을(를) {len(all_matches)}마리 보유 중입니다.\n번호를 지정해주세요:\n"]
    for i, p in enumerate(all_matches, 1):
        shiny = " ✨이로치" if p.get("is_shiny") else ""
        tb = type_badge(p["pokemon_id"])
        iv_tag = _iv_grade_tag(p)
        hearts = hearts_display(p["friendship"], config.get_max_friendship(p))
        lines.append(f"  #{i} — {tb} {p['name_ko']}{shiny}{iv_tag}  {hearts}")
    lines.append(f"\n사용법: {cmd} {name_arg} #번호")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    return None, True


async def feed_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '밥 [번호]' command."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or "트레이너",
        update.effective_user.username,
    )

    text = update.message.text or ""
    pokemon, shown = await _resolve_pokemon(update, user_id, text, "밥")
    if pokemon is None:
        return

    if pokemon["fed_today"] >= config.FEED_PER_DAY:
        await update.message.reply_text(
            f"오늘은 이미 {pokemon['name_ko']}에게 밥을 {config.FEED_PER_DAY}번 줬습니다!"
        )
        return

    max_f = config.get_max_friendship(pokemon)
    if pokemon["friendship"] >= max_f:
        await update.message.reply_text(
            f"{pokemon['name_ko']}의 친밀도가 이미 MAX입니다!\n"
            f"진화 {pokemon['name_ko']} 로 진화를 시도해보세요."
        )
        return

    boost = await get_friendship_boost()
    gain = config.FRIENDSHIP_PER_FEED * boost
    new_friendship = min(max_f, pokemon["friendship"] + gain)
    await queries.update_pokemon_friendship(pokemon["id"], new_friendship)
    await queries.increment_feed(pokemon["id"])

    remaining = config.FEED_PER_DAY - pokemon["fed_today"] - 1
    hearts = hearts_display(new_friendship, max_f)
    boost_text = f" (이벤트 {boost}배!)" if boost > 1 else ""

    evo_hint = ""
    if new_friendship >= config.MAX_FRIENDSHIP:
        if pokemon["evolves_to"] and pokemon["evolution_method"] == "friendship":
            evo_hint = f"\n\n✨ 친밀도 MAX! 진화 {pokemon['name_ko']} 로 진화할 수 있습니다!"
        elif pokemon["evolves_to"] and pokemon["evolution_method"] == "trade":
            evo_hint = f"\n\n✨ 친밀도 MAX! 이 포켓몬은 교환으로만 진화합니다."

    await update.message.reply_text(
        f"🍖 {pokemon['name_ko']}에게 밥을 줬습니다!{boost_text}\n"
        f"친밀도: {hearts} ({new_friendship}/{max_f})\n"
        f"남은 횟수: {remaining}회"
        f"{evo_hint}"
    )


async def play_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '놀기 [번호]' command."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or "트레이너",
        update.effective_user.username,
    )

    text = update.message.text or ""
    pokemon, shown = await _resolve_pokemon(update, user_id, text, "놀기")
    if pokemon is None:
        return

    if pokemon["played_today"] >= config.PLAY_PER_DAY:
        await update.message.reply_text(
            f"오늘은 이미 {pokemon['name_ko']}와(과) {config.PLAY_PER_DAY}번 놀았습니다!"
        )
        return

    max_f = config.get_max_friendship(pokemon)
    if pokemon["friendship"] >= max_f:
        await update.message.reply_text(
            f"{pokemon['name_ko']}의 친밀도가 이미 MAX입니다!\n"
            f"진화 {pokemon['name_ko']} 로 진화를 시도해보세요."
        )
        return

    boost = await get_friendship_boost()
    gain = config.FRIENDSHIP_PER_PLAY * boost
    new_friendship = min(max_f, pokemon["friendship"] + gain)
    await queries.update_pokemon_friendship(pokemon["id"], new_friendship)
    await queries.increment_play(pokemon["id"])

    remaining = config.PLAY_PER_DAY - pokemon["played_today"] - 1
    hearts = hearts_display(new_friendship, max_f)
    boost_text = f" (이벤트 {boost}배!)" if boost > 1 else ""

    evo_hint = ""
    if new_friendship >= config.MAX_FRIENDSHIP:
        if pokemon["evolves_to"] and pokemon["evolution_method"] == "friendship":
            evo_hint = f"\n\n✨ 친밀도 MAX! 진화 {pokemon['name_ko']} 로 진화할 수 있습니다!"
        elif pokemon["evolves_to"] and pokemon["evolution_method"] == "trade":
            evo_hint = f"\n\n✨ 친밀도 MAX! 이 포켓몬은 교환으로만 진화합니다."

    await update.message.reply_text(
        f"🎾 {pokemon['name_ko']}와(과) 놀아줬습니다!{boost_text}\n"
        f"친밀도: {hearts} ({new_friendship}/{max_f})\n"
        f"남은 횟수: {remaining}회"
        f"{evo_hint}"
    )


async def evolve_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '진화 [번호]' command."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or "트레이너",
        update.effective_user.username,
    )

    text = update.message.text or ""
    pokemon, shown = await _resolve_pokemon(update, user_id, text, "진화")
    if pokemon is None:
        return

    success, message = await try_evolve(user_id, pokemon["id"])
    await update.message.reply_text(message)
