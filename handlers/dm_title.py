"""DM handlers for Title (칭호) system."""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from database import queries, title_queries
from utils.helpers import icon_emoji, resolve_title_badge
from utils.i18n import t, get_user_lang

logger = logging.getLogger(__name__)


# ============================================================
# Title List (all titles + how to unlock)
# ============================================================

TITLE_LIST_CATEGORIES = None  # lazy-init


def _get_title_categories():
    global TITLE_LIST_CATEGORIES
    if TITLE_LIST_CATEGORIES is None:
        TITLE_LIST_CATEGORIES = [
            (f"{icon_emoji('pokedex')} 1세대 도감 (관동)", ["beginner", "collector", "trainer", "master", "champion", "living_dex"]),
            (f"{icon_emoji('chikorita')} 2세대 도감 (성도)", ["gen2_starter", "gen2_collector", "gen2_trainer", "gen2_master"]),
            (f"{icon_emoji('mew')} 그랜드", ["grand_master"]),
            (f"{icon_emoji('dratini')} 전설", ["legend_hunter"]),
            (f"{icon_emoji('gotcha')} 활동 기반", ["first_catch", "catch_master", "run_expert", "owl", "decisive", "love_fan", "diligent"]),
            (f"{icon_emoji('crystal')} 수집 특화", ["furry", "rare_hunter"]),
            ("🟣 마스터볼", ["masterball_rich"]),
            (f"{icon_emoji('exchange')} 교환", ["trader"]),
            (f"{icon_emoji('battle')} 배틀", ["battle_first", "battle_fighter", "battle_champion", "battle_legend",
                        "battle_streak3", "battle_streak10", "battle_sweep", "partner_set"]),
            ("🏆 토너먼트", ["tournament_first", "inaugural_champ", "tournament_champ"]),
            (f"{icon_emoji('crystal')} 이로치", ["shiny_hunter", "shiny_master", "shiny_legend"]),
        ]
    return TITLE_LIST_CATEGORIES


TITLE_LIST_PAGE_SIZE = 3  # categories per page


def _build_title_list_page(unlocked_ids: set, page: int) -> tuple[str, InlineKeyboardMarkup | None]:
    """Build a page of the title list."""
    cats = _get_title_categories()
    total_pages = max(1, -(-len(cats) // TITLE_LIST_PAGE_SIZE))  # ceil div
    page = max(0, min(page, total_pages - 1))
    start = page * TITLE_LIST_PAGE_SIZE
    page_cats = cats[start:start + TITLE_LIST_PAGE_SIZE]

    total = len(config.UNLOCKABLE_TITLES)
    got = len(unlocked_ids)
    lines = [f"🏷️ 전체 칭호 목록 ({page+1}/{total_pages})  해금: {got}/{total}개\n"]

    for cat_name, title_ids in page_cats:
        cat_lines = []
        for tid in title_ids:
            t_info = config.UNLOCKABLE_TITLES.get(tid)
            if not t_info:
                continue
            name, emoji, desc, _, _ = t_info
            status = icon_emoji("check") if tid in unlocked_ids else "🔒"
            badge = icon_emoji(emoji) if emoji in config.ICON_CUSTOM_EMOJI else emoji
            buff = config.TITLE_BUFFS.get(tid)
            buff_text = ""
            if buff:
                bparts = []
                if buff.get("daily_masterball"):
                    bparts.append(f"마볼+{buff['daily_masterball']}/일")
                if buff.get("extra_feed"):
                    bparts.append(f"밥+{buff['extra_feed']}")
                if bparts:
                    buff_text = f" ✨{', '.join(bparts)}"
            cat_lines.append(f"  {status} {badge} {name} — {desc}{buff_text}")
        if cat_lines:
            lines.append(f"\n{cat_name}")
            lines.extend(cat_lines)

    lines.append("\n'칭호' 명령어로 장착할 수 있어요!")

    # Pagination buttons
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀ 이전", callback_data=f"tlist_{page-1}"))
    nav_row.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="tlist_noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("다음 ▶", callback_data=f"tlist_{page+1}"))
    markup = InlineKeyboardMarkup([nav_row]) if total_pages > 1 else None

    return "\n".join(lines), markup


async def title_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '칭호목록' command (DM) — show all titles and unlock conditions."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or t(lang, "common.trainer"),
        update.effective_user.username,
    )

    unlocked = await title_queries.get_user_titles(user_id)
    unlocked_ids = {ut["title_id"] for ut in unlocked}

    text, markup = _build_title_list_page(unlocked_ids, 0)
    await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def title_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle tlist_{page} callback for title list pagination."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    if data == "tlist_noop":
        await query.answer()
        return
    if not data.startswith("tlist_"):
        return

    try:
        page = int(data.split("_")[1])
    except (ValueError, IndexError):
        await query.answer()
        return

    user_id = query.from_user.id
    lang = await get_user_lang(user_id)
    unlocked = await title_queries.get_user_titles(user_id)
    unlocked_ids = {ut["title_id"] for ut in unlocked}

    text, markup = _build_title_list_page(unlocked_ids, page)
    await query.answer()
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass


# ============================================================
# Title Selection
# ============================================================

TITLE_SELECT_PAGE_SIZE = 8  # titles per page


def _build_title_select_page(unlocked: list[dict], current_title: str, page: int) -> tuple[str, InlineKeyboardMarkup]:
    """Build a page of title selection buttons."""
    # Build flat list of (tid, t_info)
    items = []
    for ut in unlocked:
        tid = ut["title_id"]
        t_info = config.UNLOCKABLE_TITLES.get(tid)
        if t_info:
            items.append((tid, t_info))

    total_pages = max(1, -(-len(items) // TITLE_SELECT_PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    start = page * TITLE_SELECT_PAGE_SIZE
    page_items = items[start:start + TITLE_SELECT_PAGE_SIZE]

    lines = [f"🏷️ 내 칭호 ({page+1}/{total_pages})\n"]
    buttons = []
    for tid, t_info in page_items:
        name, emoji, desc, _, _ = t_info
        badge = icon_emoji(emoji) if emoji in config.ICON_CUSTOM_EMOJI else emoji
        equipped = f" {icon_emoji('check')}" if name == current_title else ""
        buff = config.TITLE_BUFFS.get(tid)
        buff_text = ""
        if buff:
            bparts = []
            if buff.get("daily_masterball"):
                bparts.append(f"마볼+{buff['daily_masterball']}/일")
            if buff.get("extra_feed"):
                bparts.append(f"밥+{buff['extra_feed']}")
            if bparts:
                buff_text = f" ✨{', '.join(bparts)}"
        lines.append(f"{badge} {name}{equipped} — {desc}{buff_text}")
        btn_label = f"{'✅ ' if name == current_title else ''}{name}"
        buttons.append(InlineKeyboardButton(btn_label, callback_data=f"title_{tid}"))

    # Add "remove title" button (always on first page)
    if page == 0:
        no_mark = f" {icon_emoji('check')}" if not current_title else ""
        lines.append(f"\n🚫 칭호 없음{no_mark}")
        buttons.append(InlineKeyboardButton(f"{'✅ ' if not current_title else ''}🚫 해제", callback_data="title_none"))

    # 2 buttons per row
    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]

    # Navigation row
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀ 이전", callback_data=f"titlep_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="titlep_noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("다음 ▶", callback_data=f"titlep_{page+1}"))
        keyboard.append(nav)

    return "\n".join(lines) + "\n\n⬇️ 장착할 칭호를 선택하세요:", InlineKeyboardMarkup(keyboard)


async def title_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '칭호' command (DM) — show unlocked titles and let user equip one."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    display_name = update.effective_user.first_name or t(lang, "common.trainer")
    await queries.ensure_user(user_id, display_name, update.effective_user.username)

    # Check and unlock any new titles first
    from utils.title_checker import check_and_unlock_titles
    await check_and_unlock_titles(user_id)

    unlocked = await title_queries.get_user_titles(user_id)
    user = await queries.get_user(user_id)
    current_title = user.get("title", "") if user else ""

    if not unlocked:
        await update.message.reply_text(
            "🏷️ 아직 해금된 칭호가 없습니다!\n\n"
            "포켓몬을 잡고, 활동하면 칭호가 해금돼요.\n"
            "예: 첫 포획, 도감 15종, 잡기 실패 50회 등"
        )
        return

    text, markup = _build_title_select_page(unlocked, current_title, 0)
    await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def title_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle titlep_{page} callback for title selection pagination."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    if data == "titlep_noop":
        await query.answer()
        return
    if not data.startswith("titlep_"):
        return

    try:
        page = int(data.split("_")[1])
    except (ValueError, IndexError):
        await query.answer()
        return

    user_id = query.from_user.id
    lang = await get_user_lang(user_id)
    unlocked = await title_queries.get_user_titles(user_id)
    user = await queries.get_user(user_id)
    current_title = user.get("title", "") if user else ""

    text, markup = _build_title_select_page(unlocked, current_title, page)
    await query.answer()
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass


async def title_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle title selection callback."""
    query = update.callback_query
    if not query or not query.data.startswith("title_"):
        return

    await query.answer()
    user_id = query.from_user.id
    lang = await get_user_lang(user_id)
    title_id = query.data.replace("title_", "")

    if title_id == "none":
        # 기존 칭호에 버프가 있었는지 확인
        user = await queries.get_user(user_id)
        old_title = user.get("title", "") if user else ""
        old_buff = config.get_title_buff_by_name(old_title) if old_title else None
        await title_queries.equip_title(user_id, "", "")
        warn = ""
        if old_buff:
            warn = "\n\n⚠️ 칭호 효과가 비활성화됩니다!"
        await query.edit_message_text(f"🚫 칭호를 해제했습니다.{warn}")
        return

    # Check if user has this title
    if not await title_queries.has_title(user_id, title_id):
        await query.edit_message_text("❌ 해금되지 않은 칭호입니다.")
        return

    t_info = config.UNLOCKABLE_TITLES.get(title_id)
    if not t_info:
        return

    name, emoji, desc, _, _ = t_info
    await title_queries.equip_title(user_id, name, emoji)
    badge = icon_emoji(emoji) if emoji in config.ICON_CUSTOM_EMOJI else emoji

    buff = config.TITLE_BUFFS.get(title_id)
    buff_msg = ""
    if buff:
        parts = []
        if buff.get("daily_masterball"):
            parts.append(f"  • 매일 마스터볼 +{buff['daily_masterball']}개 지급")
        if buff.get("extra_feed"):
            parts.append(f"  • 밥주기 횟수 +{buff['extra_feed']}회 (일 {config.FEED_PER_DAY + buff['extra_feed']}회)")
        if parts:
            buff_msg = "\n\n✨ 칭호 효과 활성화!\n" + "\n".join(parts)

    await query.edit_message_text(
        f"{icon_emoji('check')} 칭호 장착: 「{badge} {name}」\n\n"
        f"채팅방에서 이름 옆에 표시됩니다!{buff_msg}",
        parse_mode="HTML",
    )
