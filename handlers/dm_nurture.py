"""DM handlers for nurturing: 밥, 놀기, 진화."""

import logging
from telegram import Update
from telegram.ext import ContextTypes

import config
from database import queries
from services.evolution_service import try_evolve
from services.event_service import get_friendship_boost
from utils.helpers import hearts_display
from utils.parse import parse_number

logger = logging.getLogger(__name__)


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

    index = parse_number(update.message.text or "")
    if index is None:
        await update.message.reply_text("사용법: 밥 [번호]\n예: 밥 1")
        return

    pokemon = await queries.get_user_pokemon_by_index(user_id, index)

    if not pokemon:
        await update.message.reply_text(
            f"{index}번 포켓몬을 찾을 수 없습니다.\n내포켓몬 으로 목록을 확인하세요."
        )
        return

    if pokemon["fed_today"] >= config.FEED_PER_DAY:
        await update.message.reply_text(
            f"오늘은 이미 {pokemon['name_ko']}에게 밥을 {config.FEED_PER_DAY}번 줬습니다!"
        )
        return

    if pokemon["friendship"] >= config.MAX_FRIENDSHIP:
        await update.message.reply_text(
            f"{pokemon['name_ko']}의 친밀도가 이미 MAX입니다!\n"
            f"진화 {index} 로 진화를 시도해보세요."
        )
        return

    boost = await get_friendship_boost()
    gain = config.FRIENDSHIP_PER_FEED * boost
    new_friendship = min(config.MAX_FRIENDSHIP, pokemon["friendship"] + gain)
    await queries.update_pokemon_friendship(pokemon["id"], new_friendship)
    await queries.increment_feed(pokemon["id"])

    remaining = config.FEED_PER_DAY - pokemon["fed_today"] - 1
    hearts = hearts_display(new_friendship)
    boost_text = f" (이벤트 {boost}배!)" if boost > 1 else ""

    evo_hint = ""
    if new_friendship >= config.MAX_FRIENDSHIP:
        if pokemon["evolves_to"] and pokemon["evolution_method"] == "friendship":
            evo_hint = f"\n\n✨ 친밀도 MAX! 진화 {index} 로 진화할 수 있습니다!"
        elif pokemon["evolves_to"] and pokemon["evolution_method"] == "trade":
            evo_hint = f"\n\n✨ 친밀도 MAX! 이 포켓몬은 교환으로만 진화합니다."

    await update.message.reply_text(
        f"🍖 {pokemon['name_ko']}에게 밥을 줬습니다!{boost_text}\n"
        f"친밀도: {hearts} ({new_friendship}/{config.MAX_FRIENDSHIP})\n"
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

    index = parse_number(update.message.text or "")
    if index is None:
        await update.message.reply_text("사용법: 놀기 [번호]\n예: 놀기 1")
        return

    pokemon = await queries.get_user_pokemon_by_index(user_id, index)

    if not pokemon:
        await update.message.reply_text(
            f"{index}번 포켓몬을 찾을 수 없습니다.\n내포켓몬 으로 목록을 확인하세요."
        )
        return

    if pokemon["played_today"] >= config.PLAY_PER_DAY:
        await update.message.reply_text(
            f"오늘은 이미 {pokemon['name_ko']}와(과) {config.PLAY_PER_DAY}번 놀았습니다!"
        )
        return

    if pokemon["friendship"] >= config.MAX_FRIENDSHIP:
        await update.message.reply_text(
            f"{pokemon['name_ko']}의 친밀도가 이미 MAX입니다!\n"
            f"진화 {index} 로 진화를 시도해보세요."
        )
        return

    boost = await get_friendship_boost()
    gain = config.FRIENDSHIP_PER_PLAY * boost
    new_friendship = min(config.MAX_FRIENDSHIP, pokemon["friendship"] + gain)
    await queries.update_pokemon_friendship(pokemon["id"], new_friendship)
    await queries.increment_play(pokemon["id"])

    remaining = config.PLAY_PER_DAY - pokemon["played_today"] - 1
    hearts = hearts_display(new_friendship)
    boost_text = f" (이벤트 {boost}배!)" if boost > 1 else ""

    evo_hint = ""
    if new_friendship >= config.MAX_FRIENDSHIP:
        if pokemon["evolves_to"] and pokemon["evolution_method"] == "friendship":
            evo_hint = f"\n\n✨ 친밀도 MAX! 진화 {index} 로 진화할 수 있습니다!"
        elif pokemon["evolves_to"] and pokemon["evolution_method"] == "trade":
            evo_hint = f"\n\n✨ 친밀도 MAX! 이 포켓몬은 교환으로만 진화합니다."

    await update.message.reply_text(
        f"🎾 {pokemon['name_ko']}와(과) 놀아줬습니다!{boost_text}\n"
        f"친밀도: {hearts} ({new_friendship}/{config.MAX_FRIENDSHIP})\n"
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

    index = parse_number(update.message.text or "")
    if index is None:
        await update.message.reply_text("사용법: 진화 [번호]\n예: 진화 1")
        return

    pokemon = await queries.get_user_pokemon_by_index(user_id, index)

    if not pokemon:
        await update.message.reply_text(
            f"{index}번 포켓몬을 찾을 수 없습니다.\n내포켓몬 으로 목록을 확인하세요."
        )
        return

    success, message = await try_evolve(user_id, pokemon["id"])
    await update.message.reply_text(message)
