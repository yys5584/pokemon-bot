"""Group chat info commands: 랭킹, 로그, 대시보드, 방정보, 내포켓몬, 이로치강스, 언어설정."""

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

import config

from database import queries, item_queries, spawn_queries
from database import battle_queries as bq
from services.tournament_service import is_tournament_active
from utils.helpers import (
    time_ago, get_decorated_name, truncate_name, schedule_delete,
    ball_emoji, shiny_emoji, icon_emoji, rarity_badge, type_badge,
)
from utils.i18n import t, get_group_lang, poke_name

logger = logging.getLogger(__name__)


async def ranking_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /랭킹 command in group chat — 승률 랭킹."""
    if not update.effective_chat:
        return
    if is_tournament_active(update.effective_chat.id):
        return

    chat_id = update.effective_chat.id
    lang = await get_group_lang(chat_id)

    try:
        rankings = await bq.get_winrate_ranking(limit=5, min_games=5)

        if not rankings:
            await update.message.reply_text(t(lang, "group.ranking_no_data"))
            return

        medals = ["🥇", "🥈", "🥉", "4.", "5."]
        lines = [t(lang, "group.ranking_title")]
        for i, r in enumerate(rankings):
            medal = medals[i] if i < len(medals) else f"{i+1}."
            decorated = get_decorated_name(
                truncate_name(r["display_name"], 5),
                r.get("title", ""),
                r.get("title_emoji", ""),
                r.get("username"),
                html=True,
            )
            wr = r["winrate"] or 0
            w = r["battle_wins"]
            total = r["total_games"]
            lines.append(
                f"{medal} {decorated} — {t(lang, 'group.ranking_entry', winrate=wr, wins=w, total=total)}"
            )

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ranking handler error: {e}")
        await update.message.reply_text(t(lang, "group.ranking_error"))


async def log_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /로그 command in group chat."""
    if not update.effective_chat:
        return
    if is_tournament_active(update.effective_chat.id):
        return

    chat_id = update.effective_chat.id
    lang = await get_group_lang(chat_id)

    try:
        logs = await spawn_queries.get_recent_logs(chat_id, limit=10)

        if not logs:
            await update.message.reply_text(t(lang, "group.log_no_data"))
            return

        lines = [f"{icon_emoji('bookmark')} {t(lang, 'group.log_title')}"]
        for log in logs:
            ago = time_ago(log["spawned_at"])
            shiny = shiny_emoji() if log.get("is_shiny") else ""
            if log["caught_by_name"]:
                result = t(lang, "group.log_caught", name=log["caught_by_name"])
            else:
                result = t(lang, "group.log_escaped")
            lines.append(
                f"{ago} {shiny}{log['pokemon_emoji']} {log['pokemon_name']} {result}"
            )

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    except Exception as e:
        logger.error(f"Log handler error: {e}")
        await update.message.reply_text(t(lang, "group.log_error"))


async def dashboard_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '대시보드' command — show dashboard link."""
    if update.effective_chat and is_tournament_active(update.effective_chat.id):
        return
    chat_id = update.effective_chat.id if update.effective_chat else None
    lang = await get_group_lang(chat_id) if chat_id else "ko"
    await update.message.reply_text(
        f"{icon_emoji('computer')} {t(lang, 'group.dashboard_title')}\n\n"
        f"🔗 <a href='{config.DASHBOARD_URL}'>tgpoke.com</a>\n\n"
        f"{t(lang, 'group.dashboard_desc')}",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def room_info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '방정보' command — show chat room level & CXP status."""
    if not update.effective_chat or not update.message:
        return
    if is_tournament_active(update.effective_chat.id):
        return

    chat_id = update.effective_chat.id
    lang = await get_group_lang(chat_id)
    try:
        row = await queries.get_chat_level(chat_id)
        if not row:
            await update.message.reply_text(t(lang, "group.room_no_data"))
            return

        info = config.get_chat_level_info(row["cxp"])
        level = info["level"]
        cxp = row["cxp"]
        cxp_today = row["cxp_today"]
        next_cxp = info["next_cxp"]

        # Progress bar
        if next_cxp:
            prev_req = config.CHAT_LEVEL_TABLE[level - 1][1]
            progress = cxp - prev_req
            total = next_cxp - prev_req
            pct = min(100, int(progress / total * 100)) if total > 0 else 100
            filled = pct // 10
            bar = "█" * filled + "░" * (10 - filled)
            progress_text = f"{bar} {cxp}/{next_cxp} CXP ({pct}%)"
        else:
            progress_text = f"MAX — {cxp} CXP"

        # Benefits list
        benefits = []
        if info["spawn_bonus"]:
            benefits.append(t(lang, "group.room_spawn_bonus", count=info["spawn_bonus"]))
        if info["shiny_boost_pct"]:
            benefits.append(t(lang, "group.room_shiny_boost", pct=f"{info['shiny_boost_pct']:.1f}"))
        if info["rarity_boosts"]:
            rb = ", ".join(f"{k} ×{v:.2f}" for k, v in info["rarity_boosts"].items())
            benefits.append(t(lang, "group.room_rarity_boost", detail=rb))
        if "daily_shiny" in info["specials"]:
            benefits.append(t(lang, "group.room_daily_shiny"))
        if "auto_arcade" in info["specials"]:
            benefits.append(t(lang, "group.room_auto_arcade"))

        benefits_text = "\n".join(benefits) if benefits else t(lang, "group.none")

        text = (
            f"{t(lang, 'group.room_title')}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"{t(lang, 'group.room_level', level=level)}\n"
            f"{progress_text}\n"
            f"{t(lang, 'group.room_today_xp', today=cxp_today, cap=config.CXP_DAILY_CAP)}\n\n"
            f"{t(lang, 'group.room_benefits')}\n{benefits_text}"
        )
        await update.message.reply_text(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Room info handler error: {e}")
        await update.message.reply_text(t(lang, "group.room_error"))


async def my_pokemon_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '내포켓몬 {이름}' command in group chat — search specific pokemon."""
    if not update.effective_user or not update.message:
        return
    if update.effective_chat and is_tournament_active(update.effective_chat.id):
        return

    chat_id = update.effective_chat.id if update.effective_chat else None
    lang = await get_group_lang(chat_id) if chat_id else "ko"

    import re
    text = (update.message.text or "").strip()
    name_query = re.sub(r"^내포켓몬\s*", "", text).strip()
    if not name_query:
        await update.message.reply_text(t(lang, "group.my_pokemon_usage"))
        return

    user_id = update.effective_user.id
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or t(lang, "common.trainer"),
        update.effective_user.username,
    )
    user = await queries.get_user(user_id)
    display_name = get_decorated_name(
        user.get("display_name", update.effective_user.first_name or t(lang, "common.trainer")) if user else (update.effective_user.first_name or t(lang, "common.trainer")),
        user.get("title", "") if user else "",
        user.get("title_emoji", "") if user else "",
        update.effective_user.username,
        html=True,
    )

    pokemon_list = await queries.get_user_pokemon_list(user_id)
    if not pokemon_list:
        await update.message.reply_text(t(lang, "group.my_pokemon_none"))
        return

    matches = [(i, p) for i, p in enumerate(pokemon_list)
               if name_query in p["name_ko"] or name_query.lower() in poke_name(p, lang).lower()]
    if not matches:
        msg = await update.message.reply_text(t(lang, "group.my_pokemon_not_found", name=name_query))
        schedule_delete(msg, 30)
        return

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from utils.helpers import format_personality_iv_tag

    PAGE_SIZE = 10  # mypoke 페이지 사이즈

    rarity_labels = {
        "ultra_legendary": t(lang, "rarity.ultra_legendary"),
        "legendary": t(lang, "rarity.legendary"),
        "epic": t(lang, "rarity.epic"),
        "rare": t(lang, "rarity.rare"),
        "common": t(lang, "rarity.common"),
    }
    lines = [f"🔍 <b>{display_name}</b> {t(lang, 'group.my_pokemon_title', name='', query=name_query, count=len(matches)).strip()}"]
    lines.append("━━━━━━━━━━━━━━━")
    buttons = []
    for n, (idx, p) in enumerate(matches[:15]):
        rb = rarity_badge(p.get("rarity", "common"))
        tb = type_badge(p["pokemon_id"], p.get("pokemon_type"))
        s = " ✨" if p.get("is_shiny") else ""
        iv_tag = ""
        if p.get("iv_hp") is not None:
            iv_sum = sum(p.get(f"iv_{st}", 0) for st in ["hp", "atk", "def", "spa", "spdef", "spd"])
            grade, _ = config.get_iv_grade(iv_sum)
            iv_tag = format_personality_iv_tag(p.get("personality"), grade)
        team_tag = f" 🎯{t(lang, 'team.team_title', num=p['team_num'])}" if p.get("team_num") else ""
        rl = rarity_labels.get(p.get("rarity", ""), "")
        lines.append(f"{n+1}. {rb}{tb}{s} {poke_name(p, lang)} ({rl}){iv_tag}{team_tag}")
        page = idx // PAGE_SIZE
        buttons.append([InlineKeyboardButton(
            f"{n+1}. {poke_name(p, lang)}{' ✨' if p.get('is_shiny') else ''}",
            callback_data=f"mypoke_v_{user_id}_{idx}_{page}",
        )])

    if len(matches) > 15:
        lines.append(t(lang, "group.my_pokemon_more", count=len(matches) - 15))

    markup = InlineKeyboardMarkup(buttons) if buttons else None
    msg = await update.message.reply_text("\n".join(lines), reply_markup=markup, parse_mode="HTML")
    schedule_delete(msg, 60)


# ── 이로치 강스권 (일반 유저용) ──────────────────────────────────

_shiny_ticket_locks: dict[int, asyncio.Lock] = {}


async def shiny_ticket_spawn_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '이로치강스' command — any user with a shiny spawn ticket can force-spawn a shiny."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    lang = await get_group_lang(chat_id)

    schedule_delete(update.message, config.AUTO_DEL_FORCE_SPAWN_CMD)

    if update.effective_chat.type == "private":
        resp = await update.message.reply_text(t(lang, "common.group_only"))
        schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
        return

    ticket_count = await item_queries.get_shiny_spawn_tickets(user_id)
    if ticket_count <= 0:
        resp = await update.message.reply_text(f"✨ {t(lang, 'dungeon.no_tickets')}")
        schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
        return

    if chat_id not in _shiny_ticket_locks:
        _shiny_ticket_locks[chat_id] = asyncio.Lock()
    lock = _shiny_ticket_locks[chat_id]

    if lock.locked():
        return

    async with lock:
        from services.spawn_service import get_arcade_state, execute_spawn
        is_permanent_arcade = chat_id in config.ARCADE_CHAT_IDS
        arcade_state = get_arcade_state(context.application, chat_id)
        if is_permanent_arcade or (arcade_state and arcade_state.get("active")):
            resp = await update.message.reply_text(t(lang, "group.arcade_active_no_use"))
            schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            return

        active = await spawn_queries.get_active_spawn(chat_id)
        if active:
            resp = await update.message.reply_text(
                t(lang, "group.already_spawned", tb=type_badge(active['pokemon_id']), name=poke_name(active, lang)),
                parse_mode="HTML",
            )
            schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            return

        room = await queries.get_chat_room(chat_id)
        member_count = room["member_count"] if room else 0
        if member_count < config.SPAWN_MIN_MEMBERS:
            resp = await update.message.reply_text(
                t(lang, "group.min_members", min=config.SPAWN_MIN_MEMBERS, current=member_count)
            )
            schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            return

        ok = await item_queries.use_shiny_spawn_ticket(user_id)
        if not ok:
            resp = await update.message.reply_text(t(lang, "group.shiny_ticket_empty"))
            schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            return

        try:
            class _FakeJob:
                def __init__(self, data):
                    self.data = data
                    self.name = None

            class _FakeCtx:
                def __init__(self, bot, job_queue, data):
                    self.bot = bot
                    self.job_queue = job_queue
                    self.job = _FakeJob(data)

            spawn_data = {"chat_id": chat_id, "force": True, "force_shiny": True}
            # 관리자 전용: 포켓몬 ID 지정 (이로치강스 150 → ✨뮤츠)
            if user_id in config.ADMIN_IDS:
                text_args = update.message.text.split()[1:]
                for arg in text_args:
                    if arg.isdigit():
                        spawn_data["force_pokemon_id"] = int(arg)

            fake_ctx = _FakeCtx(
                context.bot,
                context.application.job_queue,
                spawn_data,
            )
            await execute_spawn(fake_ctx)

            resp = await context.bot.send_message(
                chat_id=chat_id,
                text=t(lang, "group.shiny_ticket_used"),
                parse_mode="HTML",
            )
            schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            logger.info(f"shiny_ticket_spawn: user {user_id} used ticket in chat {chat_id}")
        except Exception as e:
            await item_queries.add_shiny_spawn_ticket(user_id, 1)
            logger.error(f"shiny_ticket_spawn FAILED in chat {chat_id}: {e}", exc_info=True)
            try:
                resp = await context.bot.send_message(chat_id=chat_id, text=t(lang, "group.shiny_ticket_fail"))
                schedule_delete(resp, config.AUTO_DEL_FORCE_SPAWN_RESP)
            except Exception:
                pass


# ─── 그룹 언어 설정 ─────────────────────────────────

async def group_lang_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """그룹 관리자/채널장이 '언어설정 en' 등으로 그룹 언어 변경."""
    if not update.effective_user or not update.message:
        return
    if update.effective_chat.type == "private":
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    import re
    m = re.match(r"^(?:언어설정|setlang|语言设置|語言設定)\s+(\S+)$", text, re.IGNORECASE)
    if not m:
        await update.message.reply_text(
            "🌐 <b>그룹 언어 설정</b>\n"
            "━━━━━━━━━━━━━━━\n\n"
            "그룹의 기본 언어를 변경합니다.\n"
            "스폰 출현/도주 등 공통 메시지에 적용됩니다.\n"
            "(포획 메시지는 각 유저의 개인 언어로 표시)\n\n"
            "📝 <b>사용법</b>\n"
            "<code>언어설정 ko</code> — 🇰🇷 한국어\n"
            "<code>언어설정 en</code> — 🇺🇸 English\n"
            "<code>언어설정 zh-hans</code> — 🇨🇳 简体中文\n"
            "<code>언어설정 zh-hant</code> — 🇹🇼 繁體中文\n\n"
            "⚠️ 관리자만 변경 가능합니다.",
            parse_mode="HTML",
        )
        return

    new_lang = m.group(1).lower()
    from utils.i18n import SUPPORTED_LANGS, set_group_lang, LANG_LABELS
    if new_lang not in SUPPORTED_LANGS:
        await update.message.reply_text(
            f"❌ 지원하지 않는 언어: {new_lang}\n"
            f"지원: {', '.join(SUPPORTED_LANGS)}",
        )
        return

    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ("creator", "administrator") and user_id not in config.ADMIN_IDS:
            await update.message.reply_text("❌ 관리자만 언어를 변경할 수 있습니다.")
            return
    except Exception:
        pass

    await set_group_lang(chat_id, new_lang)
    label = LANG_LABELS.get(new_lang, new_lang)
    await update.message.reply_text(
        f"✅ 그룹 언어가 <b>{label}</b>로 변경되었습니다!",
        parse_mode="HTML",
    )
