"""Handler for tournament registration command: ㄷ."""

import logging
from telegram import Update
from telegram.ext import ContextTypes

import config
from database import queries
from services.tournament_service import register_player

logger = logging.getLogger(__name__)


async def tournament_join_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'ㄷ' command in arcade channel — register for tournament."""
    if not update.effective_user or not update.message:
        return

    chat_id = update.effective_chat.id

    # Only works in arcade channels
    if chat_id not in config.ARCADE_CHAT_IDS:
        return

    user_id = update.effective_user.id
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or "트레이너",
        update.effective_user.username,
    )

    display_name = update.effective_user.first_name or "트레이너"

    success, message = await register_player(user_id, display_name)
    await update.message.reply_text(message)
