"""Ranked info handlers: season info, ranking, arena registration."""

from telegram import Update
from telegram.ext import ContextTypes

import config

from utils.helpers import escape_html, icon_emoji
from utils.i18n import t, get_user_lang


async def season_info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '시즌' command (DM). Show current season info + user record."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    from services import ranked_service as rs
    from database import ranked_queries as rq

    season = await rs.ensure_current_season()
    if not season:
        await update.message.reply_text(f"🏟️ {t(lang, 'ranked.no_active_season')}")
        return

    season_id = season["season_id"]
    rule_info = config.WEEKLY_RULES.get(season["weekly_rule"], {})

    lines = [
        f"🏟️ <b>{t(lang, 'ranked.season_title', id=season_id)}</b>",
        t(lang, "ranked.season_period", start=season.get("starts_at", "?").strftime("%m/%d") if hasattr(season.get("starts_at", "?"), "strftime") else "?", end=season.get("ends_at", "?").strftime("%m/%d") if hasattr(season.get("ends_at", "?"), "strftime") else "?"),
        f"{t(lang, 'ranked.season_rule', name=rule_info.get('name', season['weekly_rule']))}",
        f"   └ {rule_info.get('desc', '')}",
        "",
        f"💡 {t(lang, 'ranked.season_dm_hint')}",
        "",
    ]

    # My season record
    rec = await rq.get_season_record(user_id, season_id)
    if rec:
        tier_full = rs.tier_display_full(rec)
        total = rec["ranked_wins"] + rec["ranked_losses"]
        wr = round(rec["ranked_wins"] / total * 100, 1) if total > 0 else 0

        placement_done = rec.get("placement_done", False)

        if not placement_done:
            pg = rec.get("placement_games", 0)
            lines.extend([
                t(lang, "ranked.my_season_record"),
                f"{tier_full}",
            ])
            if pg > 0:
                lines.append(f"🏆 {t(lang, 'battle.wins_losses', wins=rec['ranked_wins'], losses=rec['ranked_losses'], rate=wr)}")
            lines.append(t(lang, "ranked.placement_needed"))
        else:
            lines.extend([
                t(lang, "ranked.my_season_record"),
                f"{tier_full}",
                f"🏆 {t(lang, 'battle.wins_losses', wins=rec['ranked_wins'], losses=rec['ranked_losses'], rate=wr)}",
                f"🔥 {t(lang, 'battle.current_streak', n=rec['ranked_streak'])}  |  {t(lang, 'battle.best_streak_label', n=rec['best_ranked_streak'])}",
            ])
            peak_div = config.get_division_info(rec['peak_rp'])
            peak_disp = config.tier_division_display(
                peak_div[0], peak_div[1], peak_div[2],
                placement_done=True, total_rp=rec['peak_rp'])
            lines.append(t(lang, "ranked.peak_label", tier=peak_disp))

            try:
                mmr_rec = await rq.get_user_mmr(user_id)
                lines.append(t(lang, "ranked.mmr_label", mmr=mmr_rec['mmr'], peak=mmr_rec['peak_mmr']))
            except Exception:
                pass
    else:
        lines.append(t(lang, "ranked.no_season_record"))

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def ranked_ranking_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '랭킹' or '시즌랭킹' command (DM). Show season ranking."""
    if not update.effective_user or not update.message:
        return
    lang = await get_user_lang(update.effective_user.id)

    from services import ranked_service as rs
    from database import ranked_queries as rq

    season = await rs.ensure_current_season()
    if not season:
        await update.message.reply_text(f"🏟️ {t(lang, 'ranked.no_active_season')}")
        return

    ranking = await rq.get_ranked_ranking(season["season_id"], limit=15)
    if not ranking:
        await update.message.reply_text(f"🏟️ {t(lang, 'ranked.no_ranking')}")
        return

    lines = [f"🏟️ <b>{t(lang, 'ranked.ranking_header', id=season['season_id'])}</b>\n"]
    medals = ["🥇", "🥈", "🥉"]
    for i, r in enumerate(ranking):
        medal = medals[i] if i < 3 else f"{i+1}."
        te = r.get("title_emoji", "")
        te_str = f"{icon_emoji(te)} " if te and te in config.ICON_CUSTOM_EMOJI else ""
        name = escape_html(r["display_name"] or "???")

        # 배치 중이면 "🎯 배치중" 표시, 아니면 디비전 표시
        placement_done = r.get("placement_done", True)
        if not placement_done:
            tier_str = t(lang, "ranked.placement_tag")
        else:
            div = config.get_division_info(r["rp"])
            tier_str = config.tier_division_display(
                div[0], div[1], div[2],
                placement_done=True, total_rp=r["rp"])

        lines.append(
            f"{medal} {te_str}{name}  {tier_str}  "
            f"({r['ranked_wins']}승 {r['ranked_losses']}패)"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def arena_register_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '/아레나등록' command (group, admin only). Register chat as arena candidate."""
    if not update.effective_user or not update.message:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)

    # Admin check
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ("administrator", "creator"):
            await update.message.reply_text(t(lang, "ranked.arena_admin_only"))
            return
    except Exception:
        await update.message.reply_text(t(lang, "ranked.arena_perm_fail"))
        return

    chat_name = update.effective_chat.title or str(chat_id)

    from database import ranked_queries as rq
    await rq.register_arena(chat_id, chat_name, user_id)
    await update.message.reply_text(f"✅ {t(lang, 'ranked.arena_registered', name=chat_name)}")
