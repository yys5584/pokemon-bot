"""Daily mission handler — DM command '미션'."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

import config
from database import queries
from services.mission_service import ensure_daily_missions
from utils.helpers import icon_emoji, ball_emoji

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

    missions = await ensure_daily_missions(user_id)
    if not missions:
        await update.message.reply_text("미션을 불러올 수 없습니다.")
        return

    done_count = sum(1 for m in missions if m["completed"])
    total = len(missions)

    lines = [f"📋 오늘의 미션 ({done_count}/{total})\n"]

    for m in missions:
        key = m["mission_key"]
        info = config.MISSION_POOL.get(key, {})
        icon = icon_emoji(info.get("icon", "check"))
        label = info.get("label", key)
        prog = m["progress"]
        target = m["target"]

        if m["completed"]:
            mark = "✅"
            status = "완료!"
        else:
            mark = "⬜"
            status = f"{prog}/{target}"

        lines.append(f"{mark} {icon} {label}  {status}")

    # 올클리어 보상 안내
    lines.append("")
    if done_count >= total:
        # 이미 올클리어
        all_claimed = any(m["all_clear_claimed"] for m in missions)
        if all_claimed:
            lines.append(f"🌟 올클리어 보상 수령 완료! {ball_emoji('masterball')} 마스터볼")
        else:
            lines.append(f"🌟 올클리어! {ball_emoji('masterball')} 마스터볼 자동 지급됨!")
    else:
        remaining = total - done_count
        lines.append(
            f"🌟 올클리어 보상: {ball_emoji('masterball')} 마스터볼 "
            f"(남은 미션 {remaining}개)"
        )

    # 개별 보상 안내
    lines.append(
        f"\n💡 미션 1개 완료 시: {ball_emoji('hyperball')} 하이퍼볼 + {config.MISSION_REWARD_BP} BP"
    )

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
