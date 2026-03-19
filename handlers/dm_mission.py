"""Daily mission handler — DM command '미션'."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

import config
from database import queries
from services.mission_service import ensure_daily_missions
from utils.helpers import icon_emoji, ball_emoji
from utils.i18n import t, get_user_lang

logger = logging.getLogger(__name__)


async def mission_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display today's daily missions."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or "트레이너",
        update.effective_user.username,
    )

    lang = await get_user_lang(user_id)

    missions = await ensure_daily_missions(user_id)
    if not missions:
        await update.message.reply_text(t(lang, "mission.cannot_load"))
        return

    done_count = sum(1 for m in missions if m["completed"])
    total = len(missions)

    lines = [f"📋 {t(lang, 'mission.title', done=done_count, total=total)}\n"]

    for m in missions:
        key = m["mission_key"]
        info = config.MISSION_POOL.get(key, {})
        icon = icon_emoji(info.get("icon", "check"))
        label = t(lang, f"mission.{key}", **{"default": info.get("label", key)}) if f"mission.{key}" != t(lang, f"mission.{key}") else info.get("label", key)
        prog = m["progress"]
        target = m["target"]

        if m["completed"]:
            mark = "✅"
            status = t(lang, "mission.completed")
        else:
            mark = "⬜"
            status = t(lang, "mission.progress", current=prog, target=target)

        lines.append(f"{mark} {icon} {label}  {status}")

    # 올클리어 보상 안내
    lines.append("")
    if done_count >= total:
        # 이미 올클리어
        all_claimed = any(m["all_clear_claimed"] for m in missions)
        if all_claimed:
            lines.append(f"🌟 {t(lang, 'mission.all_clear_claimed')} {ball_emoji('masterball')}")
        else:
            lines.append(f"🌟 {t(lang, 'mission.all_clear')} {ball_emoji('masterball')}")
    else:
        remaining = total - done_count
        lines.append(
            f"🌟 {t(lang, 'mission.all_clear_reward', count=1)}: {ball_emoji('masterball')} "
            f"({t(lang, 'mission.remaining_missions', count=remaining)})"
        )

    # 개별 보상 안내
    lines.append(
        f"\n💡 {t(lang, 'mission.per_mission_reward', bp=config.MISSION_REWARD_BP)}: {ball_emoji('hyperball')}"
    )

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
