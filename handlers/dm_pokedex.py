"""DM handlers for Pokedex and My Pokemon."""

import asyncio
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

import config
from database import queries
from utils.helpers import hearts_display, rarity_badge, rarity_badge_label, escape_html, type_badge, _type_emoji, shiny_emoji, icon_emoji, ball_emoji, resolve_title_badge, pokemon_iv_total as _iv_sum, iv_grade
from utils.card_generator import generate_card, generate_pokedex_card
from utils.parse import parse_number, parse_name_arg
from utils.battle_calc import iv_total

logger = logging.getLogger(__name__)

POKEDEX_PAGE_SIZE = 15
MYPOKE_PAGE_SIZE = 10
ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "pokemon")

# ── Pokedex (도감) filter helpers ──

def _get_dex_filter(context) -> dict:
    """Get or init pokedex filter state."""
    filt = context.user_data.setdefault("dex_filter", {
        "gen": None,        # None=전체, 1/2/3
        "status": "all",    # all / caught / uncaught
        "rarity": None,     # None=전체, "legendary" etc
        "type": None,       # None=전체, "fire" etc
    })
    for key in ("gen", "status", "rarity", "type"):
        if key not in filt:
            filt[key] = None if key != "status" else "all"
    return filt


def _apply_dex_filters(all_pokemon: list, caught_ids: dict, filt: dict) -> list:
    """Apply filters to the full pokemon list (all_pokemon is list of pokemon_master dicts)."""
    filtered = list(all_pokemon)

    # Generation filter
    gen = filt.get("gen")
    if gen == 1:
        filtered = [p for p in filtered if 1 <= p["id"] <= 151]
    elif gen == 2:
        filtered = [p for p in filtered if 152 <= p["id"] <= 251]
    elif gen == 3:
        filtered = [p for p in filtered if 252 <= p["id"] <= 386]

    # Caught status filter
    status = filt.get("status", "all")
    if status == "caught":
        filtered = [p for p in filtered if p["id"] in caught_ids]
    elif status == "uncaught":
        filtered = [p for p in filtered if p["id"] not in caught_ids]

    # Rarity filter
    rarity = filt.get("rarity")
    if rarity:
        filtered = [p for p in filtered if p["rarity"] == rarity]

    # Type filter
    type_f = filt.get("type")
    if type_f:
        from models.pokemon_base_stats import POKEMON_BASE_STATS
        result = []
        for p in filtered:
            pbs = POKEMON_BASE_STATS.get(p["id"])
            types = pbs[-1] if pbs else [p.get("pokemon_type", "")]
            if type_f in types:
                result.append(p)
        filtered = result

    return filtered


def _build_dex_view(user_id: int, display_name: str, title_part: str,
                    all_pokemon: list, caught_ids: dict, page: int,
                    filt: dict) -> tuple[str, InlineKeyboardMarkup | None]:
    """Build the pokedex display text and inline keyboard."""
    original_total = len(caught_ids)

    # Apply filters
    has_filter = filt.get("gen") or filt.get("status", "all") != "all" or filt.get("rarity") or filt.get("type")
    if has_filter:
        filtered = _apply_dex_filters(all_pokemon, caught_ids, filt)
    else:
        filtered = all_pokemon

    caught_in_filtered = sum(1 for p in filtered if p["id"] in caught_ids)
    total_filtered = len(filtered)

    # Paginate
    total_pages = max(1, (total_filtered + POKEDEX_PAGE_SIZE - 1) // POKEDEX_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * POKEDEX_PAGE_SIZE
    end = min(start + POKEDEX_PAGE_SIZE, total_filtered)
    page_pokemon = filtered[start:end]

    # Header
    filter_tags = []
    if filt.get("gen"):
        filter_tags.append(f"{filt['gen']}세대")
    if filt.get("status") == "caught":
        filter_tags.append("✓보유")
    elif filt.get("status") == "uncaught":
        filter_tags.append("✗미보유")
    if filt.get("rarity"):
        rl = config.RARITY_LABEL.get(filt["rarity"], filt["rarity"])
        filter_tags.append(rl)
    if filt.get("type"):
        tn = config.TYPE_NAME_KO.get(filt["type"], filt["type"])
        filter_tags.append(tn)
    filter_str = f"  {'·'.join(filter_tags)}" if filter_tags else ""

    if has_filter:
        count_str = f"{caught_in_filtered}/{total_filtered}"
    else:
        count_str = f"{original_total}/386"

    gen1 = sum(1 for pid in caught_ids if pid <= 151)
    gen2 = sum(1 for pid in caught_ids if 152 <= pid <= 251)
    gen3 = sum(1 for pid in caught_ids if 252 <= pid <= 386)

    lines = [f"🏅 {escape_html(display_name)}의 도감 ({count_str}){title_part}"]
    if not has_filter:
        lines.append(f"1세대: {gen1}/151 | 2세대: {gen2}/100 | 3세대: {gen3}/135")
    lines.append("")

    for pm in page_pokemon:
        pid = pm["id"]
        if pid in caught_ids:
            entry = caught_ids[pid]
            evo_mark = " ★진화" if entry["method"] == "evolve" else ""
            trade_mark = " 🔄교환" if entry["method"] == "trade" else ""
            rb = rarity_badge(pm["rarity"])
            tb = type_badge(pid)
            lines.append(f"{pid:03d} {rb}{tb} {pm['name_ko']}{evo_mark}{trade_mark}")
        else:
            lines.append(f"{pid:03d} ・ ???")

    pct = caught_in_filtered / total_filtered * 100 if total_filtered > 0 else 0
    lines.append(f"\n수집률: {pct:.1f}%  ({page + 1}/{total_pages})")

    # ── Build inline keyboard ──
    kbd = []

    # Row 1: Generation filter
    gen_on = filt.get("gen")
    kbd.append([
        InlineKeyboardButton(f"{'✓' if gen_on == 1 else ''}1세대", callback_data=f"dex_gen_{user_id}_1"),
        InlineKeyboardButton(f"{'✓' if gen_on == 2 else ''}2세대", callback_data=f"dex_gen_{user_id}_2"),
        InlineKeyboardButton(f"{'✓' if gen_on == 3 else ''}3세대", callback_data=f"dex_gen_{user_id}_3"),
    ])

    # Row 2: Status + Rarity
    st = filt.get("status", "all")
    rarity_on = filt.get("rarity")
    kbd.append([
        InlineKeyboardButton(f"{'✓' if st == 'caught' else ''}✓보유", callback_data=f"dex_st_{user_id}_caught"),
        InlineKeyboardButton(f"{'✓' if st == 'uncaught' else ''}✗미보유", callback_data=f"dex_st_{user_id}_uncaught"),
        InlineKeyboardButton(f"{'✓' if rarity_on else ''}💎등급", callback_data=f"dex_rm_{user_id}"),
    ])

    # Row 3: Type filter
    type_on = filt.get("type")
    if type_on:
        tn = config.TYPE_NAME_KO.get(type_on, type_on)
        kbd.append([
            InlineKeyboardButton(f"✓{tn} 해제", callback_data=f"dex_tf_{user_id}_x"),
            InlineKeyboardButton("🔄 타입변경", callback_data=f"dex_tm_{user_id}"),
        ])
    else:
        kbd.append([
            InlineKeyboardButton("🏷 타입필터", callback_data=f"dex_tm_{user_id}"),
        ])

    # Row 4: Pagination
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀ 이전", callback_data=f"dex_p_{user_id}_{page - 1}"))
    if end < total_filtered:
        nav_row.append(InlineKeyboardButton("다음 ▶", callback_data=f"dex_p_{user_id}_{page + 1}"))
    if nav_row:
        kbd.append(nav_row)

    markup = InlineKeyboardMarkup(kbd) if kbd else None
    return "\n".join(lines), markup


async def pokedex_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /도감 or /pokedex command (DM only)."""
    if not update.effective_user or not update.message:
        return

    # Block in tournament chat during tournament
    if update.effective_chat and update.effective_chat.type != "private":
        from services.tournament_service import is_tournament_active
        if is_tournament_active(update.effective_chat.id):
            return

    user_id = update.effective_user.id
    display_name = update.effective_user.first_name or "트레이너"

    await queries.ensure_user(user_id, display_name, update.effective_user.username)

    # Check if searching for a specific Pokemon name
    from utils.parse import parse_args, parse_number
    text = (update.message.text or "").strip()
    args = parse_args(text)

    if args and not args[0].isdigit():
        name_query = " ".join(args)
        # Only respond if it looks like a pokemon name (exists in cache or future gen list)
        pokemon = await queries.search_pokemon_by_name(name_query)
        is_future = any(
            name_query == fn or (len(name_query) >= 2 and name_query in fn)
            for fn in _FUTURE_GEN_POKEMON
        )
        if pokemon or is_future:
            await _show_pokemon_detail(update, user_id, name_query)
        return  # Non-pokemon text → silently ignore (no response)

    # Page handling
    page = 0
    num = parse_number(text)
    if num is not None:
        page = num - 1

    # Reset filter on fresh command
    filt = _get_dex_filter(context)

    # Get data — all three queries in parallel
    import asyncio
    pokedex, user, all_pokemon = await asyncio.gather(
        queries.get_user_pokedex(user_id),
        queries.get_user(user_id),
        queries.get_all_pokemon(),
    )
    caught_ids = {p["pokemon_id"]: p for p in pokedex}
    title_part = f" {user['title_emoji']} {user['title']}" if user and user["title"] else ""

    text_msg, markup = _build_dex_view(user_id, display_name, title_part,
                                        all_pokemon, caught_ids, page, filt)

    await update.message.reply_text(text_msg, reply_markup=markup, parse_mode="HTML")


async def pokedex_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Pokedex callbacks: pagination + filters."""
    query = update.callback_query
    if not query or not query.data.startswith("dex_"):
        return

    await query.answer()

    data = query.data
    parts = data.split("_")

    # Legacy format: dex_{page_number} — handle gracefully
    if len(parts) == 2 and parts[1].isdigit():
        # Old callback, treat as page navigation
        user_id = query.from_user.id
        page = int(parts[1]) - 1
        filt = _get_dex_filter(context)
    else:
        action = parts[1]
        user_id = int(parts[2])

        if query.from_user.id != user_id:
            return

        filt = _get_dex_filter(context)
        page = 0  # Reset to first page on filter change

        if action == "p":
            # Pagination: dex_p_{user_id}_{page}
            page = int(parts[3])

        elif action == "gen":
            # Generation toggle: dex_gen_{user_id}_{1/2/3}
            gen_num = int(parts[3])
            filt["gen"] = None if filt.get("gen") == gen_num else gen_num

        elif action == "st":
            # Status toggle: dex_st_{user_id}_{caught/uncaught}
            new_st = parts[3]
            filt["status"] = "all" if filt.get("status") == new_st else new_st

        elif action == "rm":
            # Rarity menu: dex_rm_{user_id} — show rarity options
            rarity_btns = [
                [InlineKeyboardButton("초전설", callback_data=f"dex_rf_{user_id}_ultra_legendary"),
                 InlineKeyboardButton("전설", callback_data=f"dex_rf_{user_id}_legendary")],
                [InlineKeyboardButton("에픽", callback_data=f"dex_rf_{user_id}_epic"),
                 InlineKeyboardButton("레어", callback_data=f"dex_rf_{user_id}_rare")],
                [InlineKeyboardButton("일반", callback_data=f"dex_rf_{user_id}_common")],
                [InlineKeyboardButton("✕ 등급 해제", callback_data=f"dex_rf_{user_id}_x")],
                [InlineKeyboardButton("◀ 돌아가기", callback_data=f"dex_p_{user_id}_0")],
            ]
            try:
                await query.edit_message_text("💎 등급 필터 선택", reply_markup=InlineKeyboardMarkup(rarity_btns))
            except Exception:
                pass
            return

        elif action == "rf":
            # Rarity filter set: dex_rf_{user_id}_{rarity}
            r = parts[3]
            if r == "x":
                filt["rarity"] = None
            else:
                filt["rarity"] = None if filt.get("rarity") == r else r

        elif action == "tm":
            # Type menu: dex_tm_{user_id}
            type_keys = ["fire", "water", "grass", "electric", "ice", "fighting",
                         "poison", "ground", "flying", "psychic", "bug", "rock",
                         "ghost", "dragon", "dark", "steel", "fairy", "normal"]
            btns = []
            row = []
            for tk in type_keys:
                tn = config.TYPE_NAME_KO.get(tk, tk)
                emoji = config.TYPE_EMOJI.get(tk, "")
                row.append(InlineKeyboardButton(f"{emoji}{tn}", callback_data=f"dex_tf_{user_id}_{tk}"))
                if len(row) == 3:
                    btns.append(row)
                    row = []
            if row:
                btns.append(row)
            btns.append([InlineKeyboardButton("✕ 타입 해제", callback_data=f"dex_tf_{user_id}_x")])
            btns.append([InlineKeyboardButton("◀ 돌아가기", callback_data=f"dex_p_{user_id}_0")])
            try:
                await query.edit_message_text("🏷 타입 필터 선택", reply_markup=InlineKeyboardMarkup(btns))
            except Exception:
                pass
            return

        elif action == "tf":
            # Type filter set: dex_tf_{user_id}_{type}
            t = parts[3]
            if t == "x":
                filt["type"] = None
            else:
                filt["type"] = None if filt.get("type") == t else t

    # Build and show — all three queries in parallel
    import asyncio
    pokedex, user, all_pokemon = await asyncio.gather(
        queries.get_user_pokedex(user_id),
        queries.get_user(user_id),
        queries.get_all_pokemon(),
    )
    caught_ids = {p["pokemon_id"]: p for p in pokedex}
    display_name = user["display_name"] if user else "트레이너"
    title_part = f" {user['title_emoji']} {user['title']}" if user and user["title"] else ""

    text_msg, markup = _build_dex_view(user_id, display_name, title_part,
                                        all_pokemon, caught_ids, page, filt)

    try:
        await query.edit_message_text(text_msg, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass


async def my_pokemon_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /내포켓몬 command (DM only) — text list view."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or "트레이너",
        update.effective_user.username,
    )

    pokemon_list = await queries.get_user_pokemon_list(user_id)

    if not pokemon_list:
        await update.message.reply_text(
            "보유한 포켓몬이 없습니다.\n"
            "그룹 채팅방에서 ㅊ 으로 잡아보세요!"
        )
        return

    # Check if a specific index was given: "내포켓몬 3"
    from utils.parse import parse_number
    text = (update.message.text or "").strip()
    num = parse_number(text)

    if num is not None:
        # Direct detail view for a specific pokemon
        idx = max(0, min(num - 1, len(pokemon_list) - 1))
        page = idx // MYPOKE_PAGE_SIZE
        detail_text, detail_markup = _build_detail_view(user_id, pokemon_list, idx, page)
        await update.message.reply_text(detail_text, reply_markup=detail_markup, parse_mode="HTML")
        return

    # Check if a name search was given: "내포켓몬 리자몽"
    import re
    name_match = re.sub(r"^(📦\s*)?내포켓몬\s*", "", text).strip()
    if name_match:
        matches = [
            (i, p) for i, p in enumerate(pokemon_list)
            if name_match in p["name_ko"]
        ]
        if not matches:
            await update.message.reply_text(f"'{name_match}' 이름의 포켓몬을 보유하고 있지 않습니다.")
            return
        if len(matches) == 1:
            # Single match → detail view
            idx = matches[0][0]
            page = idx // MYPOKE_PAGE_SIZE
            detail_text, detail_markup = _build_detail_view(user_id, pokemon_list, idx, page)
            await update.message.reply_text(detail_text, reply_markup=detail_markup, parse_mode="HTML")
        else:
            # Multiple matches → show list with select buttons
            lines = [f"🔍 '{name_match}' 검색 결과 ({len(matches)}마리)"]
            buttons = []
            for i, (idx, p) in enumerate(matches[:20]):
                s = shiny_emoji() if p.get("is_shiny") else ""
                rb = rarity_badge(p.get("rarity", ""))
                tb = type_badge(p["pokemon_id"], p.get("pokemon_type"))
                iv_tag = ""
                if p.get("iv_hp") is not None:
                    grade, _ = config.get_iv_grade(_iv_sum(p))
                    iv_tag = f" [{grade}]"
                team_tag = f" 🎯팀{p['team_num']}" if p.get("team_num") else ""
                lines.append(f"{i+1}. {rb}{tb}{s} {p['name_ko']}{iv_tag}{team_tag}")
                page = idx // MYPOKE_PAGE_SIZE
                buttons.append([InlineKeyboardButton(
                    f"{i+1}. {p['name_ko']}{' ✨' if p.get('is_shiny') else ''}",
                    callback_data=f"mypoke_v_{user_id}_{idx}_{page}",
                )])
            from telegram import InlineKeyboardMarkup
            await update.message.reply_text(
                "\n".join(lines),
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode="HTML",
            )
        return

    # Default: show list view page 0
    filt = _get_filter(context)
    list_text, list_markup = _build_list_view(user_id, pokemon_list, page=0, filt=filt)
    await update.message.reply_text(list_text, reply_markup=list_markup, parse_mode="HTML")


def _get_filter(context) -> dict:
    """Get current filter state from user_data."""
    filt = context.user_data.setdefault("mypoke_filter", {
        "sort": "default",  # default / iv / rarity
        "fav": False,       # 즐겨찾기만 보기
        "type": None,       # None = 전체, "fire" = 특정 타입
        "gen": None,        # None = 전체, 1/2/3 = 세대 필터
        "shiny": False,     # 이로치만 보기
        "gen_open": False,  # 세대 서브필터 열림 상태
    })
    # Ensure keys exist for old sessions
    if "gen" not in filt:
        filt["gen"] = None
    if "shiny" not in filt:
        filt["shiny"] = False
    if "gen_open" not in filt:
        filt["gen_open"] = False
    return filt



def _apply_filters(pokemon_list: list, filt: dict) -> list:
    """Apply filter and sort to pokemon list."""
    filtered = list(pokemon_list)

    # Generation filter
    gen = filt.get("gen")
    if gen == 1:
        filtered = [p for p in filtered if 1 <= p["pokemon_id"] <= 151]
    elif gen == 2:
        filtered = [p for p in filtered if 152 <= p["pokemon_id"] <= 251]
    elif gen == 3:
        filtered = [p for p in filtered if 252 <= p["pokemon_id"] <= 386]

    # Type filter
    if filt.get("type"):
        from models.pokemon_base_stats import POKEMON_BASE_STATS
        target = filt["type"]
        result = []
        for p in filtered:
            pbs = POKEMON_BASE_STATS.get(p["pokemon_id"])
            types = pbs[-1] if pbs else [p.get("pokemon_type", "")]
            if target in types:
                result.append(p)
        filtered = result

    # Shiny filter
    if filt.get("shiny"):
        filtered = [p for p in filtered if p.get("is_shiny")]

    # Favorite filter
    if filt.get("fav"):
        filtered = [p for p in filtered if p.get("is_favorite")]

    # Sort
    sort_mode = filt.get("sort", "default")
    if sort_mode == "iv":
        filtered.sort(key=lambda p: _iv_sum(p), reverse=True)
    elif sort_mode == "rarity":
        rarity_order = {"ultra_legendary": 0, "legendary": 1, "epic": 2, "rare": 3, "common": 4}
        filtered.sort(key=lambda p: (rarity_order.get(p.get("rarity", "common"), 4), -_iv_sum(p)))

    return filtered


def _build_list_view(user_id: int, pokemon_list: list, page: int,
                     filt: dict = None) -> tuple[str, InlineKeyboardMarkup]:
    """Build a text-based list of pokemon with inline buttons.
    Shows team pokemon first, then groups duplicate species.
    """
    original_total = len(pokemon_list)
    slot_emojis = [icon_emoji(str(i)) for i in range(1, 7)]

    # Apply filters if provided
    if filt is None:
        filt = {"sort": "default", "fav": False, "type": None, "gen": None, "shiny": False}
    has_filter = filt.get("sort") != "default" or filt.get("fav") or filt.get("type") or filt.get("gen") or filt.get("shiny")

    if has_filter:
        filtered = _apply_filters(pokemon_list, filt)
    else:
        filtered = pokemon_list

    total = len(filtered)

    # Identify team pokemon (for header display) — only in default mode
    team_pokemon = [p for p in pokemon_list if p.get("team_slot") is not None] if not has_filter else []

    # Group pokemon by pokemon_id — skip grouping in IV sort mode (show individual ranking)
    from collections import OrderedDict
    all_indices = {id(p): i for i, p in enumerate(pokemon_list)}
    skip_grouping = filt.get("sort") == "iv"

    if skip_grouping:
        display_items = [("single", all_indices[id(p)], p) for p in filtered]
    else:
        groups = OrderedDict()
        for p in filtered:
            pid = p["pokemon_id"]
            if pid not in groups:
                groups[pid] = []
            groups[pid].append(p)

        display_items = []
        for pid, members in groups.items():
            if len(members) == 1:
                p = members[0]
                display_items.append(("single", all_indices[id(p)], p))
            else:
                first = members[0]
                indices = [all_indices[id(m)] for m in members]
                display_items.append(("group", pid, indices, first, len(members)))

    # Paginate
    total_items = len(display_items)
    total_pages = max(1, (total_items + MYPOKE_PAGE_SIZE - 1) // MYPOKE_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * MYPOKE_PAGE_SIZE
    end = min(start + MYPOKE_PAGE_SIZE, total_items)
    page_items = display_items[start:end]

    # Header
    filter_tags = []
    if filt.get("gen"):
        filter_tags.append(f"{filt['gen']}세대")
    if filt.get("sort") == "iv":
        filter_tags.append("IV순")
    elif filt.get("sort") == "rarity":
        filter_tags.append("등급순")
    if filt.get("fav"):
        filter_tags.append("⭐즐찾")
    if filt.get("shiny"):
        filter_tags.append("✨이로치")
    if filt.get("type"):
        type_name = config.TYPE_NAME_KO.get(filt["type"], filt["type"])
        filter_tags.append(type_name)
    filter_str = f"  {'·'.join(filter_tags)}" if filter_tags else ""
    count_str = f"{total}/{original_total}마리" if has_filter else f"{original_total}마리"
    lines = [f"🎒 내 포켓몬 ({count_str}){filter_str}  [{page + 1}/{total_pages}]"]

    # Show team section only on first page, default mode
    if page == 0 and team_pokemon and not has_filter:
        teams = {}
        for p in team_pokemon:
            tn = p.get("team_num") or 1
            if tn not in teams:
                teams[tn] = []
            teams[tn].append(p)
        for tn in sorted(teams.keys()):
            lines.append(f"\n{icon_emoji('battle')} 팀{tn}")
            for p in teams[tn]:
                slot = p.get("team_slot", 1) - 1
                se = slot_emojis[slot] if 0 <= slot < 6 else "▸"
                shiny = shiny_emoji() if p.get("is_shiny") else ""
                rb = rarity_badge(p.get("rarity", ""))
                tb = type_badge(p["pokemon_id"], p.get("pokemon_type"))
                iv_tag = ""
                if p.get("iv_hp") is not None:
                    grade, _ = config.get_iv_grade(_iv_sum(p))
                    iv_tag = f" [{grade}]"
                lines.append(f"{se} {rb}{tb}{shiny} {p['name_ko']}{iv_tag}")
        lines.append("━━━━━━━")

    lines.append("")

    if total == 0:
        lines.append("(조건에 맞는 포켓몬이 없습니다)")
    else:
        item_num = start + 1
        for item in page_items:
            if item[0] == "single":
                _, idx, p = item
                max_f = config.get_max_friendship(p)
                hearts = hearts_display(p["friendship"], max_f)
                shiny = shiny_emoji() if p.get("is_shiny") else ""
                fav = "⭐" if p.get("is_favorite") else ""
                evo_mark = ""
                if p["evolves_to"] and p["evolution_method"] == "friendship" and p["friendship"] >= config.MAX_FRIENDSHIP:
                    evo_mark = " ⭐"
                # IV grade
                iv_tag = ""
                if p.get("iv_hp") is not None:
                    iv_sum = _iv_sum(p)
                    grade, _ = config.get_iv_grade(iv_sum)
                    if filt.get("sort") == "iv":
                        iv_tag = f" [{grade}]{iv_sum}"
                    else:
                        iv_tag = f" [{grade}]"
                rb = rarity_badge(p.get("rarity", ""))
                tb = type_badge(p["pokemon_id"], p.get("pokemon_type"))
                team_tag = f" 🎯{p['team_num']}" if p.get("team_num") else ""
                lines.append(f"{item_num}. {rb}{tb}{shiny}{fav} {p['name_ko']}{iv_tag}  {hearts}{evo_mark}{team_tag}")
            else:  # group
                _, pid, indices, first, count = item
                rb = rarity_badge(first.get("rarity", ""))
                tb = type_badge(first["pokemon_id"], first.get("pokemon_type"))
                lines.append(f"{item_num}. {rb}{tb} {first['name_ko']}  x{count}")
            item_num += 1

    # Build buttons
    select_buttons = []

    # Filter/sort row (above pokemon list for easy access)
    sort_mode = filt.get("sort", "default")
    fav_on = filt.get("fav", False)
    type_on = filt.get("type")
    filter_row = [
        InlineKeyboardButton(
            f"{'✓' if sort_mode == 'iv' else ''}⚡IV순",
            callback_data=f"mypoke_sort_{user_id}_iv",
        ),
        InlineKeyboardButton(
            f"{'✓' if sort_mode == 'rarity' else ''}💎등급",
            callback_data=f"mypoke_sort_{user_id}_rarity",
        ),
        InlineKeyboardButton(
            f"{'✓' if fav_on else ''}⭐즐찾",
            callback_data=f"mypoke_favf_{user_id}",
        ),
    ]
    select_buttons.append(filter_row)

    # Compact filter row 2: Type + Generation + Shiny
    gen_on = filt.get("gen")
    shiny_on = filt.get("shiny", False)
    gen_label = f"✓{gen_on}세대" if gen_on else "📅세대"

    if type_on:
        type_name = config.TYPE_NAME_KO.get(type_on, type_on)
        type_btn = InlineKeyboardButton(f"✓{type_name}", callback_data=f"mypoke_tmore_{user_id}")
    else:
        type_btn = InlineKeyboardButton("🏷타입", callback_data=f"mypoke_tmore_{user_id}")

    filter_row2 = [
        type_btn,
        InlineKeyboardButton(gen_label, callback_data=f"mypoke_genm_{user_id}"),
        InlineKeyboardButton(
            f"{'✓' if shiny_on else ''}✨이로치",
            callback_data=f"mypoke_shiny_{user_id}",
        ),
    ]
    select_buttons.append(filter_row2)

    # Generation sub-filter row (expanded when gen_open is True)
    if filt.get("gen_open"):
        gen_sub_row = [
            InlineKeyboardButton(
                f"{'✓' if gen_on == 1 else ''}1세대",
                callback_data=f"mypoke_gen_{user_id}_1",
            ),
            InlineKeyboardButton(
                f"{'✓' if gen_on == 2 else ''}2세대",
                callback_data=f"mypoke_gen_{user_id}_2",
            ),
            InlineKeyboardButton(
                f"{'✓' if gen_on == 3 else ''}3세대",
                callback_data=f"mypoke_gen_{user_id}_3",
            ),
            InlineKeyboardButton("← 닫기", callback_data=f"mypoke_genc_{user_id}"),
        ]
        select_buttons.append(gen_sub_row)

    # Pokemon selection buttons
    row = []
    for i, item in enumerate(page_items):
        num = start + i + 1
        if item[0] == "single":
            _, idx, p = item
            label = f"{num}. {p['name_ko']}"
            cb = f"mypoke_v_{user_id}_{idx}_{page}"
        else:
            _, pid, indices, first, count = item
            label = f"{num}. {first['name_ko']} x{count}"
            cb = f"mypoke_g_{user_id}_{pid}_{page}"
        row.append(InlineKeyboardButton(label, callback_data=cb))
        if len(row) == 2:
            select_buttons.append(row)
            row = []
    if row:
        select_buttons.append(row)

    # Pagination
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀ 이전", callback_data=f"mypoke_l_{user_id}_{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("다음 ▶", callback_data=f"mypoke_l_{user_id}_{page + 1}"))
    if nav_row:
        select_buttons.append(nav_row)

    # Action row: 팀설정 + 방생
    select_buttons.append([
        InlineKeyboardButton("⚔️ 팀설정", callback_data=f"mypoke_team_{user_id}"),
        InlineKeyboardButton("🔄 방생", callback_data=f"mypoke_rel_{user_id}"),
    ])

    markup = InlineKeyboardMarkup(select_buttons)
    return "\n".join(lines), markup


def _build_group_view(user_id: int, pokemon_list: list, pokemon_id: int, page: int) -> tuple[str, InlineKeyboardMarkup]:
    """Show individual pokemon within a duplicate group."""
    members = [p for p in pokemon_list if p["pokemon_id"] == pokemon_id]
    if not members:
        return "해당 포켓몬을 찾을 수 없습니다.", InlineKeyboardMarkup([])

    first = members[0]
    rb = rarity_badge(first.get("rarity", ""))
    tb = type_badge(first["pokemon_id"], first.get("pokemon_type"))
    lines = [f"{rb}{tb} {first['name_ko']} 보유 목록 ({len(members)}마리)\n"]

    buttons = []
    row = []
    for i, p in enumerate(members):
        idx = pokemon_list.index(p)
        num = i + 1
        shiny = f" {shiny_emoji()}이로치" if p.get("is_shiny") else ""
        max_f = config.get_max_friendship(p)
        hearts = hearts_display(p["friendship"], max_f)

        # IV grade
        iv_tag = ""
        iv_hp = p.get("iv_hp")
        if iv_hp is not None:
            total = iv_total(iv_hp, p.get("iv_atk"), p.get("iv_def"),
                             p.get("iv_spa"), p.get("iv_spdef"), p.get("iv_spd"))
            grade, _ = config.get_iv_grade(total)
            iv_tag = f" [{grade}]"

        team_mark = f" ⚔{p.get('team_num') or 1}" if p.get("team_slot") is not None else ""
        lines.append(f"#{num}  {first['name_ko']}{shiny}  {hearts}{iv_tag}{team_mark}")

        label = f"#{num}{shiny[:1]}{iv_tag}"
        row.append(InlineKeyboardButton(label, callback_data=f"mypoke_v_{user_id}_{idx}_{page}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton("📋 목록으로", callback_data=f"mypoke_l_{user_id}_{page}")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def _build_detail_view(user_id: int, pokemon_list: list, idx: int, page: int) -> tuple[str, InlineKeyboardMarkup]:
    """Build detail text for a single pokemon with action buttons."""
    p = pokemon_list[idx]
    total = len(pokemon_list)
    num = idx + 1

    max_f = config.get_max_friendship(p)
    hearts = hearts_display(p["friendship"], max_f)
    shiny_mark = shiny_emoji() if p.get("is_shiny") else ""

    evo_text = ""
    if p["evolves_to"] and p["evolution_method"] == "friendship" and p["friendship"] >= config.MAX_FRIENDSHIP:
        evo_text = "\n⭐ 진화 가능! → '진화 " + str(num) + "' 입력"
    elif p["evolves_to"] and p["evolution_method"] == "trade":
        evo_text = "\n🔄 교환으로 진화 가능"

    rarity_text = rarity_badge_label(p["rarity"])
    shiny_text = f"  {shiny_emoji()}이로치" if p.get("is_shiny") else ""

    # IV information
    from utils.battle_calc import calc_battle_stats, format_stats_line, format_power, iv_total, EVO_STAGE_MAP
    iv_hp = p.get("iv_hp")
    iv_atk = p.get("iv_atk")
    iv_def = p.get("iv_def")
    iv_spa = p.get("iv_spa")
    iv_spdef = p.get("iv_spdef")
    iv_spd = p.get("iv_spd")
    has_iv = iv_hp is not None

    iv_line = ""
    stats_line = ""
    if has_iv:
        total_iv = iv_total(iv_hp, iv_atk, iv_def, iv_spa, iv_spdef, iv_spd)
        grade, _stars = config.get_iv_grade(total_iv)
        iv_line = f"\nIV: {iv_hp}/{iv_atk}/{iv_def}/{iv_spa}/{iv_spdef}/{iv_spd} ({total_iv}/186) [{grade}]"

        # Calculate battle stats with IVs
        pid = p["pokemon_id"]
        evo_stage = EVO_STAGE_MAP.get(pid, 3)
        stats = calc_battle_stats(
            p["rarity"], p.get("stat_type", "balanced"), p["friendship"],
            evo_stage=evo_stage,
            iv_hp=iv_hp, iv_atk=iv_atk, iv_def=iv_def,
            iv_spa=iv_spa, iv_spdef=iv_spdef, iv_spd=iv_spd,
        )
        base = calc_battle_stats(
            p["rarity"], p.get("stat_type", "balanced"), p["friendship"],
            evo_stage=evo_stage,
        )
        stats_line = (
            f"\n{icon_emoji('bolt')} 전투력: {format_power(stats, base)}"
            f"\n{format_stats_line(stats, base)}"
        )

    tb = type_badge(p["pokemon_id"], p.get("pokemon_type"))
    # Type name display
    from models.pokemon_base_stats import POKEMON_BASE_STATS
    pbs = POKEMON_BASE_STATS.get(p["pokemon_id"])
    if pbs:
        types = pbs[-1]
        type_names = "/".join(config.TYPE_NAME_KO.get(t, t) for t in types)
    else:
        type_names = config.TYPE_NAME_KO.get(p.get("pokemon_type", ""), "")
    type_display = f"  {tb}{type_names}" if type_names else ""

    lines = [
        f"내 포켓몬 상세 ({num}/{total})\n",
        f"{shiny_mark}{tb} {p['name_ko']}{shiny_text}",
        f"등급: {rarity_text}{type_display}",
        f"친밀도: {hearts} ({p['friendship']}/{max_f}){evo_text}{iv_line}{stats_line}",
    ]

    # Team info
    team_info = ""
    if p.get("team_slot") is not None:
        team_info = f"\n{icon_emoji('battle')} 팀{p.get('team_num') or 1} — {p['team_slot']}번 슬롯"
    lines.append(team_info)

    # Action buttons
    buttons = []

    # Row 1: care actions (most used)
    care_row = [
        InlineKeyboardButton("🍖 밥", callback_data=f"mypoke_feed_{user_id}_{idx}_{page}"),
        InlineKeyboardButton("🎮 놀기", callback_data=f"mypoke_play_{user_id}_{idx}_{page}"),
    ]
    can_evo_friendship = p["evolves_to"] and p["evolution_method"] == "friendship" and p["friendship"] >= config.MAX_FRIENDSHIP
    can_evo_trade = p["evolves_to"] and p["evolution_method"] == "trade"
    if can_evo_friendship:
        care_row.append(InlineKeyboardButton("⭐ 진화", callback_data=f"mypoke_evo_{user_id}_{idx}_{page}"))
    buttons.append(care_row)

    # Row 2: info + settings
    fav_label = "⭐ 즐찾해제" if p.get("is_favorite") else "☆ 즐찾"
    buttons.append([
        InlineKeyboardButton("📋 감정", callback_data=f"mypoke_appr_{user_id}_{idx}_{page}"),
        InlineKeyboardButton(fav_label, callback_data=f"mypoke_fav_{user_id}_{idx}_{page}"),
        InlineKeyboardButton("⚔1 팀1", callback_data=f"mypoke_t1_{user_id}_{idx}_{page}"),
        InlineKeyboardButton("⚔2 팀2", callback_data=f"mypoke_t2_{user_id}_{idx}_{page}"),
    ])

    # Row 3: navigation
    detail_nav = []
    if idx > 0:
        detail_nav.append(InlineKeyboardButton("◀ 이전", callback_data=f"mypoke_v_{user_id}_{idx - 1}_{page}"))
    detail_nav.append(InlineKeyboardButton("📋 목록", callback_data=f"mypoke_l_{user_id}_{page}"))
    if idx < total - 1:
        detail_nav.append(InlineKeyboardButton("다음 ▶", callback_data=f"mypoke_v_{user_id}_{idx + 1}_{page}"))
    buttons.append(detail_nav)

    markup = InlineKeyboardMarkup(buttons)
    return "\n".join(lines), markup


async def my_pokemon_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 내포켓몬 callbacks: list, detail, group, and action buttons."""
    query = update.callback_query
    if not query or not query.data.startswith("mypoke_"):
        return

    data = query.data
    parts = data.split("_")
    action = parts[1]
    user_id = int(parts[2])

    if query.from_user.id != user_id:
        return

    await query.answer()

    pokemon_list = await queries.get_user_pokemon_list(user_id)
    if not pokemon_list:
        try:
            await query.edit_message_text("보유한 포켓몬이 없습니다.")
        except Exception:
            pass
        return

    filt = _get_filter(context)

    try:
        if action == "l":
            page = int(parts[3])
            text, markup = _build_list_view(user_id, pokemon_list, page, filt=filt)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "sort":
            # mypoke_sort_{user_id}_{mode}
            mode = parts[3]
            if filt["sort"] == mode:
                filt["sort"] = "default"  # toggle off
            else:
                filt["sort"] = mode
            text, markup = _build_list_view(user_id, pokemon_list, 0, filt=filt)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "gen":
            # mypoke_gen_{user_id}_{gen_num} — toggle generation filter
            gen_num = int(parts[3])
            if filt.get("gen") == gen_num:
                filt["gen"] = None  # toggle off
            else:
                filt["gen"] = gen_num
            text, markup = _build_list_view(user_id, pokemon_list, 0, filt=filt)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "genm":
            # mypoke_genm_{user_id} — open generation sub-filter
            filt["gen_open"] = True
            text, markup = _build_list_view(user_id, pokemon_list, 0, filt=filt)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "genc":
            # mypoke_genc_{user_id} — close generation sub-filter
            filt["gen_open"] = False
            text, markup = _build_list_view(user_id, pokemon_list, 0, filt=filt)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "shiny":
            # mypoke_shiny_{user_id} — toggle shiny filter
            filt["shiny"] = not filt.get("shiny", False)
            text, markup = _build_list_view(user_id, pokemon_list, 0, filt=filt)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "favf":
            # mypoke_favf_{user_id} — toggle fav filter
            filt["fav"] = not filt["fav"]
            text, markup = _build_list_view(user_id, pokemon_list, 0, filt=filt)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "fav":
            # mypoke_fav_{user_id}_{idx}_{page} — toggle favorite on a pokemon
            idx = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else 0
            idx = max(0, min(idx, len(pokemon_list) - 1))
            p = pokemon_list[idx]
            new_state = await queries.toggle_favorite(p["id"])
            emoji = "⭐ 즐겨찾기 등록!" if new_state else "즐겨찾기 해제"
            await query.answer(emoji, show_alert=False)
            pokemon_list = await queries.get_user_pokemon_list(user_id)
            idx = max(0, min(idx, len(pokemon_list) - 1))
            text, markup = _build_detail_view(user_id, pokemon_list, idx, page)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "tf":
            # mypoke_tf_{user_id}_{type_key} — set type filter
            type_key = parts[3]
            if type_key == "x":
                filt["type"] = None
            else:
                filt["type"] = type_key
            text, markup = _build_list_view(user_id, pokemon_list, 0, filt=filt)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "tmore":
            # mypoke_tmore_{user_id} — show type filter grid
            type_keys = ["fire", "water", "grass", "electric", "ice", "fighting",
                         "poison", "ground", "flying", "psychic", "bug", "rock",
                         "ghost", "dragon", "dark", "steel", "fairy", "normal"]
            type_names = config.TYPE_NAME_KO
            btns = []
            row = []
            for tk in type_keys:
                tn = type_names.get(tk, tk)
                emoji = config.TYPE_EMOJI.get(tk, "")
                row.append(InlineKeyboardButton(f"{emoji}{tn}", callback_data=f"mypoke_tf_{user_id}_{tk}"))
                if len(row) == 3:
                    btns.append(row)
                    row = []
            if row:
                btns.append(row)
            btns.append([InlineKeyboardButton("✕ 필터 해제", callback_data=f"mypoke_tf_{user_id}_x")])
            btns.append([InlineKeyboardButton("◀ 돌아가기", callback_data=f"mypoke_l_{user_id}_0")])
            await query.edit_message_text("🏷 타입 필터 선택", reply_markup=InlineKeyboardMarkup(btns))

        elif action == "v":
            idx = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else idx // MYPOKE_PAGE_SIZE
            idx = max(0, min(idx, len(pokemon_list) - 1))
            text, markup = _build_detail_view(user_id, pokemon_list, idx, page)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "g":
            # Group view: mypoke_g_{user_id}_{pokemon_id}_{page}
            pokemon_id = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else 0
            text, markup = _build_group_view(user_id, pokemon_list, pokemon_id, page)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "appr":
            # Appraisal: show IV info inline
            idx = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else 0
            idx = max(0, min(idx, len(pokemon_list) - 1))
            p = pokemon_list[idx]
            text = _format_appraisal(p)
            # Back button to detail
            markup = InlineKeyboardMarkup([[
                InlineKeyboardButton("◀ 돌아가기", callback_data=f"mypoke_v_{user_id}_{idx}_{page}")
            ]])
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "feed":
            idx = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else 0
            idx = max(0, min(idx, len(pokemon_list) - 1))
            p = pokemon_list[idx]
            result, fed = await _do_feed(p, user_id)
            await query.answer(result, show_alert=True)
            if fed:
                async def _feed_mission():
                    try:
                        from services.mission_service import check_mission_progress
                        msg = await check_mission_progress(user_id, "feed")
                        if msg:
                            await query.get_bot().send_message(
                                chat_id=user_id, text=msg, parse_mode="HTML",
                            )
                    except Exception:
                        pass
                asyncio.create_task(_feed_mission())
            # Refresh detail
            pokemon_list = await queries.get_user_pokemon_list(user_id)
            idx = max(0, min(idx, len(pokemon_list) - 1))
            text, markup = _build_detail_view(user_id, pokemon_list, idx, page)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "play":
            idx = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else 0
            idx = max(0, min(idx, len(pokemon_list) - 1))
            p = pokemon_list[idx]
            result, played = await _do_play(p, user_id)
            await query.answer(result, show_alert=True)
            if played:
                async def _play_mission():
                    try:
                        from services.mission_service import check_mission_progress
                        msg = await check_mission_progress(user_id, "play")
                        if msg:
                            await query.get_bot().send_message(
                                chat_id=user_id, text=msg, parse_mode="HTML",
                            )
                    except Exception:
                        pass
                asyncio.create_task(_play_mission())
            pokemon_list = await queries.get_user_pokemon_list(user_id)
            idx = max(0, min(idx, len(pokemon_list) - 1))
            text, markup = _build_detail_view(user_id, pokemon_list, idx, page)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "evo":
            idx = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else 0
            idx = max(0, min(idx, len(pokemon_list) - 1))
            p = pokemon_list[idx]
            result = await _do_evolve(p, user_id)
            await query.answer(result, show_alert=True)
            pokemon_list = await queries.get_user_pokemon_list(user_id)
            idx = max(0, min(idx, len(pokemon_list) - 1))
            text, markup = _build_detail_view(user_id, pokemon_list, idx, page)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action in ("t1", "t2"):
            idx = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else 0
            idx = max(0, min(idx, len(pokemon_list) - 1))
            p = pokemon_list[idx]
            team_num = 1 if action == "t1" else 2
            text, markup = await _build_slot_picker(user_id, p, idx, page, team_num)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "tset":
            # mypoke_tset_{uid}_{idx}_{page}_{slot}_{team_num}
            idx = int(parts[3])
            page = int(parts[4])
            slot = int(parts[5])
            team_num = int(parts[6])
            idx = max(0, min(idx, len(pokemon_list) - 1))
            p = pokemon_list[idx]
            result = await _do_set_slot(p, user_id, team_num, slot)
            await query.answer(result, show_alert=True)
            pokemon_list = await queries.get_user_pokemon_list(user_id)
            idx = max(0, min(idx, len(pokemon_list) - 1))
            text, markup = _build_detail_view(user_id, pokemon_list, idx, page)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "team":
            # mypoke_team_{user_id} — 통합 팀설정 메뉴
            text, markup = await _build_team_settings(user_id)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "tact":
            # mypoke_tact_{user_id}_{team_num} — 활성 팀 변경
            team_num = int(parts[3])
            from database import battle_queries as bq
            team = await bq.get_battle_team(user_id, team_num)
            if not team:
                await query.answer(f"팀 {team_num}이(가) 비어있습니다!", show_alert=True)
            else:
                await bq.set_active_team(user_id, team_num)
                await query.answer(f"✅ 팀 {team_num} 활성화!", show_alert=False)
            text, markup = await _build_team_settings(user_id)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "rel":
            # mypoke_rel_{user_id} — 방생 필터 패널 표시
            from handlers.dm_release import _build_panel, _get_filter as _get_rel_filter
            filt_rel = _get_rel_filter(context)
            text, markup = _build_panel(user_id, filt_rel)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

    except Exception:
        pass


def _format_appraisal(p: dict) -> str:
    """Format IV appraisal text for a pokemon."""
    shiny = shiny_emoji() if p.get("is_shiny") else ""
    rb = rarity_badge(p.get("rarity", "common"))
    ivs = {
        "HP": p.get("iv_hp"), "ATK": p.get("iv_atk"), "DEF": p.get("iv_def"),
        "SPA": p.get("iv_spa"), "SPDEF": p.get("iv_spdef"), "SPD": p.get("iv_spd"),
    }
    total = iv_total(ivs["HP"], ivs["ATK"], ivs["DEF"], ivs["SPA"], ivs["SPDEF"], ivs["SPD"])
    grade, _ = config.get_iv_grade(total)
    pct = round(total / 186 * 100, 1)

    stat_labels = {"HP": "HP   ", "ATK": "공격 ", "DEF": "방어 ", "SPA": "특공 ", "SPDEF": "특방 ", "SPD": "스피드"}
    lines = [f"{icon_emoji('bookmark')} {shiny}{rb} {p['name_ko']} 감정 결과\n"]
    for key in ("HP", "ATK", "DEF", "SPA", "SPDEF", "SPD"):
        v = ivs[key] if ivs[key] is not None else 15
        filled = round(v / 31 * 6)
        bar = "█" * filled + "░" * (6 - filled)
        mark = " ★" if v >= 28 else (" ✗" if v <= 5 else "")
        lines.append(f"{stat_labels[key]} {bar} {v}/31{mark}")
    lines.append(f"\n총합: {total}/186 ({pct}%)")
    lines.append(f"등급: {grade}")
    flavor = {"S": "최상급 개체!", "A": "매우 뛰어남", "B": "괜찮은 개체", "C": "평범", "D": "개체값 낮음"}
    lines.append(flavor.get(grade, ""))
    return "\n".join(lines)


async def _do_feed(p: dict, user_id: int) -> tuple[str, bool]:
    """Execute feed action, return (result message, success)."""
    # 칭호 버프: 밥주기 추가 횟수
    feed_limit = config.FEED_PER_DAY
    user_data = await queries.get_user(user_id)
    if user_data and user_data.get("title"):
        buff = config.get_title_buff_by_name(user_data["title"])
        if buff and buff.get("extra_feed"):
            feed_limit += buff["extra_feed"]

    if p["fed_today"] >= feed_limit:
        return f"오늘은 이미 밥을 {feed_limit}번 줬습니다!", False
    max_f = config.get_max_friendship(p)
    if p["friendship"] >= max_f:
        return f"{p['name_ko']} 친밀도 MAX!", False
    from services.event_service import get_friendship_boost
    boost = await get_friendship_boost()
    gain = config.FRIENDSHIP_PER_FEED * boost
    new_f = await queries.atomic_feed(p["id"], gain, max_f)
    if new_f is None:
        return "오류가 발생했습니다.", False
    remaining = feed_limit - p["fed_today"] - 1
    return f"🍖 {p['name_ko']}에게 밥! 친밀도 {new_f}/{max_f} (남은: {remaining}회)", True


async def _do_play(p: dict, user_id: int) -> tuple[str, bool]:
    """Execute play action, return (result message, success)."""
    if p["played_today"] >= config.PLAY_PER_DAY:
        return f"오늘은 이미 {config.PLAY_PER_DAY}번 놀아줬습니다!", False
    max_f = config.get_max_friendship(p)
    if p["friendship"] >= max_f:
        return f"{p['name_ko']} 친밀도 MAX!", False
    from services.event_service import get_friendship_boost
    boost = await get_friendship_boost()
    gain = config.FRIENDSHIP_PER_PLAY * boost
    new_f = await queries.atomic_play(p["id"], gain, max_f)
    if new_f is None:
        return "오류가 발생했습니다.", False
    remaining = config.PLAY_PER_DAY - p["played_today"] - 1
    return f"🎾 {p['name_ko']}와 놀기! 친밀도 {new_f}/{max_f} (남은: {remaining}회)", True


async def _build_team_settings(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Build unified team settings menu (팀설정)."""
    from database import battle_queries as bq

    team1 = await bq.get_battle_team(user_id, 1)
    team2 = await bq.get_battle_team(user_id, 2)
    active = await bq.get_active_team_number(user_id)

    t1_info = f"({len(team1)}마리)" if team1 else "(비어있음)"
    t2_info = f"({len(team2)}마리)" if team2 else "(비어있음)"
    t1_active = f" {icon_emoji('check')}" if active == 1 else ""
    t2_active = f" {icon_emoji('check')}" if active == 2 else ""

    lines = [
        f"{icon_emoji('battle')} <b>팀 설정</b>\n",
        f"팀1 {t1_info}{t1_active}",
        f"팀2 {t2_info}{t2_active}",
    ]

    buttons = [
        [
            InlineKeyboardButton("✏️ 팀1 편집", callback_data=f"tedit_{user_id}_1"),
            InlineKeyboardButton("✏️ 팀2 편집", callback_data=f"tedit_{user_id}_2"),
        ],
        [
            InlineKeyboardButton("🔀 팀1↔팀2 교환", callback_data=f"tswap_teams_{user_id}"),
        ],
    ]

    # 활성 팀 전환 버튼 (비활성 팀만 표시)
    active_row = []
    if active != 1 and team1:
        active_row.append(InlineKeyboardButton("✅ 팀1 활성", callback_data=f"mypoke_tact_{user_id}_1"))
    if active != 2 and team2:
        active_row.append(InlineKeyboardButton("✅ 팀2 활성", callback_data=f"mypoke_tact_{user_id}_2"))
    if active_row:
        buttons.append(active_row)

    buttons.append([
        InlineKeyboardButton("📋 내포켓몬으로", callback_data=f"mypoke_l_{user_id}_0"),
    ])

    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def _do_evolve(p: dict, user_id: int) -> str:
    """Execute evolution, return result message."""
    if not p["evolves_to"]:
        return "이 포켓몬은 진화할 수 없습니다."
    if p["evolution_method"] == "trade":
        return "이 포켓몬은 교환으로만 진화합니다."
    max_f = config.get_max_friendship(p)
    if p["friendship"] < max_f:
        return f"친밀도가 부족합니다 ({p['friendship']}/{max_f})"
    # Perform evolution
    evo_target = await queries.get_pokemon_master(p["evolves_to"])
    if not evo_target:
        return "진화 대상을 찾을 수 없습니다."
    await queries.evolve_pokemon(p["id"], p["evolves_to"])
    return f"🎉 {p['name_ko']}이(가) {evo_target['name_ko']}(으)로 진화했습니다!"


async def _build_slot_picker(user_id: int, p: dict, idx: int, page: int,
                             team_num: int) -> tuple[str, InlineKeyboardMarkup]:
    """Show 6 team slots for placing a pokemon."""
    from database import battle_queries as bq
    team = await bq.get_battle_team(user_id, team_num)
    slot_emojis = [icon_emoji(str(i)) for i in range(1, 7)]
    slot_plain = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]
    slot_map = {t["slot"]: t for t in team}

    shiny = shiny_emoji() if p.get("is_shiny") else ""
    tb = type_badge(p["pokemon_id"], p.get("pokemon_type"))
    lines = [f"{icon_emoji('battle')} 팀{team_num}에 {tb}{shiny} {p['name_ko']} 배치", "슬롯을 선택하세요:\n"]

    buttons = []
    for s in range(1, 7):
        if s in slot_map:
            t = slot_map[s]
            t_iv = ""
            if t.get("iv_hp") is not None:
                total = iv_total(t["iv_hp"], t.get("iv_atk", 0), t.get("iv_def", 0),
                                 t.get("iv_spa", 0), t.get("iv_spdef", 0), t.get("iv_spd", 0))
                grade, _ = config.get_iv_grade(total)
                t_iv = f" [{grade}]{total}"
            ttb = type_badge(t["pokemon_id"], t.get("pokemon_type"))
            t_shiny = shiny_emoji() if t.get("is_shiny") else ""
            lines.append(f"{slot_emojis[s-1]} {ttb}{t_shiny} {t['name_ko']}{t_iv}")
            label = f"{slot_plain[s-1]} {t['name_ko']} → 교체"
        else:
            lines.append(f"{slot_emojis[s-1]} (빈 슬롯)")
            label = f"{slot_plain[s-1]} 빈 슬롯 ← 배치"
        buttons.append([InlineKeyboardButton(
            label, callback_data=f"mypoke_tset_{user_id}_{idx}_{page}_{s}_{team_num}"
        )])

    buttons.append([InlineKeyboardButton("❌ 취소", callback_data=f"mypoke_v_{user_id}_{idx}_{page}")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def _do_set_slot(p: dict, user_id: int, team_num: int, slot: int) -> str:
    """Place pokemon into a specific team slot. Returns result message."""
    from database import battle_queries as bq
    team = await bq.get_battle_team(user_id, team_num)

    # Check if already on this team
    for t in team:
        if t.get("pokemon_instance_id") == p["id"]:
            if t["slot"] == slot:
                return f"이미 슬롯 {slot}에 등록되어 있습니다!"
            return f"이미 팀{team_num}의 슬롯 {t['slot']}에 등록되어 있습니다!"

    # Build new slot map
    slot_map = {t["slot"]: t["pokemon_instance_id"] for t in team}
    replaced_name = None
    for t in team:
        if t["slot"] == slot:
            replaced_name = t["name_ko"]
    slot_map[slot] = p["id"]

    # Validate: ultra_legendary limit (1 per team)
    if p["rarity"] == "ultra_legendary":
        ul_count = sum(
            1 for t in team
            if t.get("rarity") == "ultra_legendary" and t["slot"] != slot
        )
        if ul_count >= 1:
            return "초전설 포켓몬은 팀당 1마리만 가능합니다!"

    # Validate: same-species duplicate (epic/legendary/ultra_legendary)
    if p["rarity"] in ("epic", "legendary", "ultra_legendary"):
        for t in team:
            if t["slot"] != slot and t.get("rarity") in ("epic", "legendary", "ultra_legendary") and t.get("pokemon_id") == p["pokemon_id"]:
                return "같은 종의 포켓몬은 중복 불가!"

    # Validate: COST limit
    import config
    total_cost = config.RANKED_COST.get(p["rarity"], 0)
    for t in team:
        if t["slot"] != slot:
            total_cost += config.RANKED_COST.get(t.get("rarity", ""), 0)
    if total_cost > config.RANKED_COST_LIMIT:
        return f"❌ 팀 코스트 초과! ({total_cost}/{config.RANKED_COST_LIMIT})\n코스트 {config.RANKED_COST_LIMIT} 이하로 편성해주세요."

    # Save
    instance_ids = [slot_map[s] for s in sorted(slot_map.keys())]
    await bq.set_battle_team(user_id, instance_ids, team_num)

    if replaced_name:
        return f"{icon_emoji('check')} 슬롯{slot}: {replaced_name} → {p['name_ko']} 교체!"
    return f"{icon_emoji('check')} {p['name_ko']}을(를) 슬롯 {slot}에 배치!"


# --- Pokemon TMI data (웃긴 버전) ---
POKEMON_TMI = {
    1: "사실 피카츄보다 먼저 디자인된 포켓몬 1호. 도감 번호 001은 우연이 아님. 풀/독이라 약점 4개인데 메가진화 2개 받은 럭키가이.",
    2: "중간 진화라 존재감 제로. 이상해씨 팬도 이상해꽃 팬도 있는데 이상해풀 팬은 찾기 어려움. 중2병 시절 같은 존재.",
    3: "메가진화가 2개나 있는 스타터. 꽃이 피면 암컷이라는 설정 때문에 수컷 이상해꽃 꽃은 뭐냐는 논쟁이 20년째.",
    4: "애니에서 원래 트레이너한테 비 맞으며 버림받은 에피소드가 포켓몬 역대 눈물 TOP5. 지우가 데려간 뒤에도 말 안 들음.",
    5: "리자드 시절부터 지우 말 안 듣기 시작. 진화하면 성격 나빠지는 현실적인 사춘기 포켓몬. 꼬리불 꺼지면 죽는다는 설정 무서움.",
    6: "비행/불꽃인데 드래곤 아님. 30년째 전 세계 팬들이 왜를 외치는 중. PSA 10 1판 카드 4.2억인데 그래도 드래곤 아님. 메가진화 X로 겨우 드래곤 받음.",
    7: "꼬부기부대 선글라스가 밈의 시초. 리더 꼬부기는 뾰족선글라스, 나머지는 둥근 선글라스. 이 디테일 아는 사람이 진짜 팬.",
    8: "꼬부기에서 진화하면 귀가 생김. 거북이한테 귀가 왜 필요한지는 게임프리크만 앎. 중간진화 특유의 애매한 인생.",
    9: "메가거북왕 등에 대포 2개 달림. 초대 스타터 중 경쟁력은 제일 낮았는데 5세대 조개껍질 특성으로 한때 OU급 위엄.",
    10: "캐터피는 버터플 되려고 존재하는 포켓몬. 레벨 7에 진화하니까 사실상 게임 역사상 가장 빠른 중간진화.",
    11: "딱풀은 굳히기만 쓸 수 있음. 현실의 번데기처럼 진짜 아무것도 못 하는 리얼리즘 포켓몬.",
    12: "지우가 버터플 놓아주는 장면이 포켓몬 애니 3대 눈물신. 짝짓기 위해 보내줬는데 시청자들이 더 울었음.",
    13: "독침붕 진화 루트인데 존재감 제로. 뿔충이에서 코쿤, 독침붕까지 가는 라인업에서 코쿤과 함께 누구세요 담당.",
    14: "딱풀이랑 같은 신세. 굳히기만 배우는 번데기 포켓몬 2호. 게임프리크의 복붙 디자인 철학.",
    15: "메가독침붕 공격력 150. 의외로 메가진화 받고 화력깡패 등극. 하지만 내구는 종이라 유리대포 그 자체.",
    16: "초대 노말/비행 새 포켓몬. 모든 세대 초반새의 원조. 피죤투 팬은 있어도 구구 팬은 거의 없는 슬픈 현실.",
    17: "지우의 피죤이 꽤 활약했는데 피죤투 되자마자 풀어줌. 진화시켜놓고 바로 방생하는 갓지우 클래스.",
    18: "지우가 진화 직후 야생 포켓몬 지키라고 놓아줬는데 20년 넘게 안 데리러 옴. 역대급 방치플레이.",
    19: "금은의 반바지 꼬마 민수가 세계 최강의 꼬렛이라고 전화하는 밈이 전설. TOP PERCENTAGE RATTATA 영원히 기억됨.",
    20: "라이벌 그린의 레트라가 상트안느호 이후 사라짐. 그린이 레트라를 죽였다는 팬 이론이 소름. 포켓몬타워에서 그린을 만나는 건 우연이 아닐지도.",
    21: "깨비참은 부리가 짧아서 땅을 잘 못 팜. 설정상 벌레 포켓몬 잡아먹는 포식자인데 게임에선 그냥 약함.",
    22: "깨비드릴조는 무리 지어 공격하는 설정. 애니에서 깨비드릴조 떼가 날아오는 장면은 공포 그 자체.",
    23: "아보는 로켓단 로이의 포켓몬으로 유명. AG 시리즈에서 방생당할 때 로이가 울면서 보내줌.",
    24: "아보크도 로이와 이별. 로켓단 포켓몬 방생 에피소드가 의외로 감동적이었음. 악역도 정이 있다.",
    25: "원래 주인공 파트너는 삐삐였는데 급교체. 지우가 진화석 거부한 건 유명한데 정작 라이츄가 더 강함. 인생은 불공평.",
    26: "마티스 중위의 라이츄가 피카츄한테 지는 장면이 진화만이 답이 아니다의 원조. 근데 경쟁에선 라이츄가 맞음.",
    27: "모래두지는 알로라 폼에서 얼음타입으로 환생. 사막 포켓몬이 북극 포켓몬 되는 극적인 인생역전.",
    28: "고지는 경쟁 환경에서 존재감 거의 없지만 알로라 폼의 숨겨진 특성 눈퍼뜨리기가 의외로 쓸만함.",
    29: "니드런 암컷은 포켓몬 최초의 성별 구분 포켓몬. 암수 구분이 여기서 시작됨.",
    30: "니드리나는 진화했는데 교배가 안 됨. 니드런 암컷은 교배 되는데 진화하면 불임이 되는 의문의 설정.",
    31: "니드퀸도 교배 불가. 포켓몬 세계관 최대 미스터리 중 하나. 게임프리크 코딩 실수라는 게 정설.",
    32: "니드런 수컷은 짝인 니드런 암컷과 함께 성별 시스템의 원조. 근데 인기는 암컷이 더 많음.",
    33: "니드리노는 불레/적 타이틀 화면에 나온 적 있음. 의외로 간판 출연이 있는 중간진화.",
    34: "니드킹은 설정상 꼬리 한 방으로 전봇대를 부러뜨림. 근데 공격 종족값은 102로 그냥 평범.",
    35: "원래 포켓몬 시리즈의 마스코트가 될 뻔했음. 피카츄한테 자리 뺏긴 비운의 포켓몬. 평행세계에선 삐삐가 주인공.",
    36: "6세대에서 노말에서 페어리로 재분류. 경쟁에서 우주파워+지구던지기+따라하기 세트로 의외의 활약. 텔레판 한국 크립토 슈퍼 아이돌이기도 함.",
    37: "식스테일은 알로라 폼에서 얼음/페어리로 환생. 불꽃 여우가 눈의 여우가 되는 디자인 변신이 대성공.",
    38: "나인테일 도감 설정이 꼬리를 잡으면 1000년 저주. 알로라 나인테일은 경쟁에서 오로라베일 세팅용으로 인기.",
    39: "푸린이 노래 부르면 모두 잠듦. 애니에서 잠든 사람 얼굴에 낙서하는 게 시그니처. 화난 푸린 얼굴이 밈.",
    40: "푸크린은 푸린의 진화형인데 존재감이 거의 없음. 진화 전이 더 유명한 슬픈 케이스.",
    41: "게임 역사상 가장 짜증나는 동굴 인카운터. 주바트 없는 동굴이 없음. 또 주바트 밈은 만국공통.",
    42: "골뱃은 입이 몸의 절반. 초대 도트에서는 입이 아예 몸 전체였음. 디자인 공포.",
    43: "뚜벅쵸는 일본 이름이 나조노쿠사(수수께끼의 풀). 이름부터 정체불명인데 실제로도 별 존재감 없음.",
    44: "냄새꼬는 항상 침을 흘리는 디자인. 포켓몬 중 가장 불쾌하게 생긴 Top 10 단골.",
    45: "라플레시아는 세계 최대 꽃 라플레시아에서 따옴. 시체꽃 모티브라 냄새가 역하다는 설정.",
    46: "파라스의 버섯은 동충하초 모티브. 진화하면 버섯이 본체를 완전히 지배함. 파라섹트의 눈이 흰 건 이미 죽었기 때문이라는 설정이 소름.",
    47: "파라섹트는 본체가 아니라 등의 버섯이 조종 중. 포켓몬 세계관에서 가장 무서운 설정 중 하나. 좀비 포켓몬.",
    48: "콘팡은 눈이 엄청 큰데 왜 독타입인지 모르겠는 포켓몬. 모르포나비로 진화하면 눈 디자인이 완전히 바뀜.",
    49: "모르포나비는 원래 버터플의 진화형이었다는 설이 있음. 콘팡과 캐터피의 디자인 스왑 이론이 유명.",
    50: "디그다 땅속 몸이 어떻게 생겼는지 아무도 모름. 포켓몬 최대 미스터리. 공식에서 한 번도 공개 안 함.",
    51: "닥트리오는 디그다 3마리가 모인 건데 속도가 엄청 빠름. 알로라 폼에서 금발 가발 추가되어 헤어샵 다녀옴 밈.",
    52: "로켓단 나옹은 인간 언어를 독학한 천재. 좋아하는 암컷 나옹한테 잘 보이려고 말을 배웠는데 차임. 포켓몬 세계관 최고의 비극.",
    53: "페르시온은 사카키의 무릎 위 포켓몬으로 유명. 보스 고양이 포지션의 원조. 알로라 폼 얼굴이 밈이 됨.",
    54: "고라파덕은 항상 머리가 아프고 초능력이 폭주. 이슬이의 고라파덕은 몬스터볼에서 멋대로 나오는 주인 말 안 듣는 대표 포켓몬.",
    55: "골덕은 진화하면 머리 아픈 게 나음. 수영 속도가 시속 56km. 근데 이슬이 고라파덕은 끝까지 진화 안 함.",
    56: "망키는 분노 포켓몬. 항상 화나있음. 지우 모자 뺏어간 에피소드가 유명. 5분 안에 잡힘.",
    57: "성원숭은 더 화남. 도감 설명이 화나면 죽을 때까지 쫓아옴. 포켓몬 세계관 무서운 설정 시리즈.",
    58: "가디는 전설 포켓몬 분류인데 진짜 전설이 아님. 도감 카테고리가 전설 포켓몬이라 혼동 유발의 원흉.",
    59: "윈디는 한국에서 특히 인기. 해태와 삽살개 모티브설. 경쟁에서도 꾸준히 쓰이는 인기 불꽃타입.",
    60: "발챙이는 배의 소용돌이가 내장이 비치는 거라는 설정. 귀여운 척하지만 설정은 좀 그로테스크.",
    61: "슈륙챙이는 장갑을 끼고 있음. 올챙이가 복싱 글러브를 끼는 진화과정이 포켓몬 로직.",
    62: "강챙이는 의외로 경쟁에서 강함. 숨겨진 특성 쓱쓱으로 비 팀에서 에이스급. 올챙이의 반란.",
    63: "캐이시는 순간이동만 쓰고 도망감. 야생에서 잡기 가장 짜증나는 포켓몬 TOP3. 잠만 자는데 IQ 5000.",
    64: "윤겔라 디자인이 유리 겔러 닮았다고 소송당함. 그래서 TCG에서 수년간 카드 발매 금지. 숟가락이 문제였음.",
    65: "후딘 IQ 5000인데 경쟁에서 메가진화 없으면 애매. 천재인데 취업이 안 되는 현실 반영인가.",
    66: "알통몬은 벨트가 없으면 힘 조절 불가. 포켓몬 세계의 파워 리미터 설정 원조.",
    67: "근력몬은 팔이 4개. 인간형 포켓몬인데 팔이 4개인 건 넘기고 가는 게 포켓몬 팬의 자세.",
    68: "괴력몬은 공식 설정상 이사짐센터에서 일함. 포켓몬 세계관에서 가장 현실적인 취업 사례. 일당이 궁금해짐.",
    69: "모다피 도감번호 69. 영어권 팬들이 매번 킹킹거림. 이름도 Bellsprout인데 번호가 결정적.",
    70: "우츠동은 파리지옥 모티브. 사람을 녹인다는 도감 설정이 있어서 포켓몬인데 살인식물.",
    71: "우츠보트는 로이의 포켓몬인데 맨날 로이를 잡아먹음. 애니에서 매회 로이 머리가 우츠보트 입에.",
    72: "왕눈해는 수중 동굴의 주바트 포지션. 파도타기 하면 1초마다 나옴. 또 왕눈해 트라우마.",
    73: "독파리는 촉수 80개로 독을 쏨. 애니 초기에 거대 독파리가 도시를 습격하는 에피소드는 괴수영화급.",
    74: "꼬마돌은 바위인데 자폭을 배움. 동굴에서 만나면 자폭으로 경험치도 못 주고 아군만 죽이는 테러리스트.",
    75: "데구리는 산에서 굴러다니며 민폐. 도감 설정상 매일 밑으로 굴러가서 누군가 위로 올려줘야 함.",
    76: "딱구리는 자폭의 달인. 경쟁에서 스텔스록 깔고 자폭하는 게 주 전략. 태어난 이유가 자폭.",
    77: "포니타는 불꽃 말인데 가라르에서 유니콘이 됨. 에스퍼/페어리 포니타는 디자인 대호평.",
    78: "날쌩마는 달리는 속도가 시속 240km. 포켓몬 세계에서 교통수단이 왜 필요한지 의문을 갖게 만드는 포켓몬.",
    79: "야돈은 꼬리 물리고 5초 후에 아파함. 공식 설정 IQ가 거의 0에 가까움. 근데 메가진화 받으면 천재가 됨.",
    80: "야도란은 꼬리의 셀러가 본체를 조종한다는 이론. 셀러 떼면 야돈으로 돌아감. 공생인지 기생인지 애매.",
    81: "코일은 전기/강철인데 1세대에선 전기만. 특성 자력으로 메타그로스 잡는 킬러로 활약한 적 있음.",
    82: "레어코일은 코일 3마리가 합체. 왜 3마리가 합치면 이름에 레어가 붙는지는 영원한 의문.",
    83: "일본 속담 오리가 파를 지고 온다=호구 모티브. 파를 들고 다니는 호구 컨셉인데 가라르 폼에서 파를 칼처럼 쓰는 사무라이로 각성.",
    84: "두두는 날개가 없는데 공중날기를 배움. 포켓몬 최대 불가사의 중 하나. 머리로 뛰어서 나는 건가?",
    85: "두트리오는 머리가 3개인데 성격이 다 다름. 알로라 폼에서 금발 가발 쓰고 나와서 웃음벨.",
    86: "쥬쥬는 그냥 물개임. 포켓몬 디자인이 동물 그대로 시대의 유물. 이름도 울음소리 그대로.",
    87: "쥬레곤은 듀공 모티브인데 영어 이름이 Dewgong. 실제 듀공과 이름이 같아서 헷갈리는 희귀 케이스.",
    88: "질퍽이는 슬러지 그 자체. 도감 설정상 걸어간 자리에 풀이 안 자람. 환경파괴 포켓몬.",
    89: "질뻐기는 알로라 폼에서 무지개색. 독극물이 무지개색이 되면 예뻐지는 게 포켓몬 로직. 의외로 알로라 폼 인기 많음.",
    90: "셀러는 혀를 내밀고 있는 조개. 디자인이 좀 그래서 언급하기 어려운 포켓몬 순위 상위권.",
    91: "파르셀은 영어 이름 Cloyster와 디자인이 합쳐져서 인터넷에서 영원히 밈. 경쟁에서 껍질깨기가 사기.",
    92: "고오스는 가스로 이루어진 유령. 초대에서 에스퍼 타입 견제용인데 독타입 때문에 에스퍼한테 약점 잡힘. 본말전도.",
    93: "고우스트는 고오스의 진화형인데 통신교환 안 하면 여기서 멈춤. 친구 없으면 팬텀은 못 쓰는 잔인한 시스템.",
    94: "팬텀은 초대 최강 포켓몬 중 하나. 메가팬텀은 경쟁에서 사용금지급. 그림자밟기로 도망도 못 치게 하는 악마.",
    95: "롱스톤은 크기가 8.8m인데 방어력이 생각보다 낮음. 강철코트 주면 강철톤 되는데 친구가 필요.",
    96: "슬리프는 도감 설정이 아이들의 꿈을 먹음. 포켓몬 세계관 범죄자 포켓몬 1위. 디자인도 수상함.",
    97: "슬리퍼는 슬리프보다 더 무서운 설정. 최면술로 아이를 데려간다는 도감 기록. 이걸 아동용 게임에 넣은 게임프리크 대단.",
    98: "크랩은 그냥 게. 이름도 Krabby. 지우가 잡았는데 오박사 연구소에서 평생 대기.",
    99: "킹크랩은 관장전에서 갑자기 등장해 활약. 지우의 숨겨진 에이스였던 적이 딱 한 번 있음.",
    100: "찌리리공은 몬스터볼을 닮음. 발전소에서 자폭하는 존재. 아이템인 줄 알고 클릭하면 전투 시작되는 트롤.",
    101: "붐볼은 찌리리공의 진화형인데 뒤집은 몬스터볼 디자인. 자폭 위력이 높아서 경쟁에서 자폭셔틀로 쓰임.",
    102: "아라리는 달걀 6개가 모인 포켓몬인데 풀/에스퍼. 달걀이 초능력 쓰는 세계관. 하나가 깨지면 어떻게 되는지는 미지수.",
    103: "나시는 알로라 폼에서 목이 10m로 늘어남. 드래곤 타입 추가. 야자수가 드래곤이 되는 포켓몬 로직에 팬들 폭소.",
    104: "탕구리는 죽은 엄마의 뼈다귀와 두개골을 쓰고 다님. 포켓몬 역대 가장 슬픈 설정. 울음소리도 슬픔.",
    105: "텅구리는 알로라 폼에서 불꽃/고스트. 엄마 원한이 불꽃이 된 건가. 경쟁에서 굵은뼈 아이템으로 화력 2배.",
    106: "시라소몬은 발차기 전문. 일본명이 킥복서 사와무라에서 따옴. 격투 포켓몬의 원조.",
    107: "홍수몬은 펀치 전문. 이름 유래가 복서. 시라소몬이랑 택1 진화라 선택장애 유발.",
    108: "내루미는 혀가 2m. 뭐든 핥는다는 설정. 도감 설명이 점점 이상해지는 포켓몬 대표.",
    109: "또가스는 로켓단 로이의 상징. 독가스인데 이름이 또가스라서 한국에선 방귀 드립의 표적.",
    110: "또도가스는 가라르 폼에서 굴뚝모자 신사가 됨. 독가스가 영국 신사로 변신하는 건 산업혁명 풍자.",
    111: "뿔카노는 시력이 나빠서 직진밖에 못 함. 달리다 멈추면 왜 달렸는지 잊는다는 설정. 공감 가는 포켓몬.",
    112: "코뿌리가 사실 포켓몬 역사상 가장 먼저 프로그래밍된 포켓몬. 도감번호 1번인 이상해씨보다 먼저 만들어짐. 숨겨진 원조.",
    113: "럭키는 경쟁에서 진화의휘석 달면 방특이 미친 수치. HP 255인데 방어 5. 극단적 종족값의 아이콘.",
    114: "덩구리는 덩굴이 얼굴을 가리고 있어서 본체 얼굴을 아무도 모름. 디그다 지하 미스터리와 쌍벽.",
    115: "캥카는 메가진화하면 주머니의 새끼가 나와서 싸움. 아기를 전투에 내보내는 어미라는 윤리적 논쟁 유발.",
    116: "쏘드라는 해마 포켓몬. 킹드라까지 진화하면 드래곤 타입 추가되는데 리자몽은 안 되고 해마는 되는 세상.",
    117: "시드라는 독가시로 기절시킨다는 설정. 중간진화라 존재감 없지만 킹드라 진화 루트의 핵심.",
    118: "콘치는 뿔이 자랑인 금붕어 포켓몬. 이슬이가 좋아하는 포켓몬인데 인기는 별로.",
    119: "왕콘치는 폭포오르기를 배우는 몇 안 되는 포켓몬이었음. 지금은 아무도 안 씀.",
    120: "별가사리는 보석이 본체. 경쟁에서 자연회복과 빛의장막 서포터로 간간이 보임.",
    121: "아쿠스타는 에스퍼/물 복합타입. 보석이 빛나면 뭔가 통신한다는 UFO스러운 설정.",
    122: "배리어는 지우 엄마와 함께 사는 포켓몬. 팬들 사이에서 지우 새아빠라는 밈이 20년째 현역. 가라르에서 배리어드 진화 추가.",
    123: "스라크는 낫 양팔. 도감 설정상 풀을 베는 데 쓰이는데 어떻게 몬스터볼을 터치하는지 의문.",
    124: "루주라는 디자인 인종차별 논란으로 피부색이 검정에서 보라로 변경. 포켓몬 역사상 가장 큰 디자인 수정 사건.",
    125: "에레브는 전기타입 원조 강자. 에레키블로 진화하면서 뚱뚱해져서 팬들 충격.",
    126: "마그마는 불꽃타입 원조. 마그마번으로 진화시 디자인 호불호가 극명.",
    127: "쁘사이저는 메가진화로 비행타입 추가. 사슴벌레가 날게 된 순간. 경쟁에서 깜놀 화력.",
    128: "켄타로스는 지우가 사파리존에서 30마리를 잡음. 한 에피소드에서 30마리. 지우 인생 최고의 사냥 효율.",
    129: "공식 설정 가장 약하고 한심한 포켓몬. 튀어오르기 PP 40짜리 하나로 버팀. 포켓몬센터 앞 상인이 500원에 팔아먹는 사기 이벤트도 있음.",
    130: "갸라도스는 물/비행이지 드래곤 아님. 잉어킹에서 이걸로 싶은 디자인 변화. 색다른 갸라도스는 호수의 분노 이벤트로 유명.",
    131: "라프라스는 바다 위 택시. 파도타기의 상징. 한때 멸종 위기였다가 너무 번식해서 문제라는 도감 설정이 현실적.",
    132: "뮤 복제 실패작이라는 팬 이론이 있음. 교배 만능키라 포켓몬 세계관 최고의 워커홀릭. 좀 쉬어.",
    133: "이브이는 진화형이 8개. 포켓몬 마케팅의 핵심 축. 진화 안 시키고 키우는 팬도 많은 아이돌급 인기.",
    134: "샤미드는 물 이브이. 세포가 물과 비슷해서 물에 녹는다는 설정이 무서움. 인어 모티브 꼬리가 예쁨.",
    135: "쥬피썬더는 번개 이브이. 경쟁에서 볼트체인지 빠른 피봇으로 쓰이기도 함. 털이 바늘처럼 서있는 디자인.",
    136: "부스터는 이브이 진화형 중 가장 불쌍. 1세대에서 불꽃타입인데 물리 불꽃기가 없어서 가장 쓸모없는 이브이 밈의 주인공.",
    137: "포켓몬 쇼크 사건의 억울한 희생양. 실제로 화면 깜빡인 건 피카츄 10만볼트인데 폴리곤이 30년째 방송 출연금지.",
    138: "트위치 플레이즈 포켓몬에서 신 헬릭스로 등극. 화석에서 부활하는데 민주주의 vs 무정부주의 논쟁의 중심이 된 전설의 포켓몬.",
    139: "암스타는 헬릭스의 진화형. 신의 진화형이라 LORD HELIX EVOLVED로 트위치 채팅 폭발했던 순간.",
    140: "투구는 살아있는 화석 포켓몬. 투구벌레 모티브인데 3억년 전 모습 그대로라는 설정.",
    141: "투구푸스는 낫 양팔. 화석 포켓몬인데 의외로 경쟁에서 쓱쓱 비팀 물리어태커로 가끔 보임.",
    142: "프테라는 메가진화 받은 화석 포켓몬. 공중전의 원조 강자. 도감 설정상 고대에는 하늘의 왕이었음.",
    143: "길 막고 서있어서 포켓몬피리 없으면 진행 불가. 하루에 400kg 먹는 설정. 먹고 자고 반복이 라이프스타일의 아이콘.",
    144: "프리져는 3신조 중 얼음. 경쟁에서 가장 약한 편. 가라르 폼에서 에스퍼/비행으로 변경되어 이게 프리져란 반응.",
    145: "썬더는 3신조 중 전기. 경쟁에서 가장 강한 전설의새. 프레셔 특성으로 PP 말리기 전략의 원조.",
    146: "파이어는 3신조 중 불꽃. 디자인이 불붙은 새라서 가장 단순하다는 평가. 가라르 폼은 악/비행으로 변신.",
    147: "미뇽은 바다의 보석이라는 별명. 용 포켓몬의 원조인데 뱀처럼 생김. 귀여움에서 망나뇽으로의 디자인 변화가 충격적.",
    148: "신뇽은 미뇽의 우아한 진화. 망나뇽과 디자인 괴리가 너무 커서 중간에 디자이너 바뀐 거 아니냐는 의혹.",
    149: "신뇽의 우아한 모습에서 갑자기 주황색 카이류. 디자인 변경이 포켓몬 역사상 가장 충격적. 그래도 초대 600족 최강 중 하나.",
    150: "뮤츠는 뮤를 복제해 만든 인공 포켓몬. 극장판 1편의 주인공. 나는 왜 태어났는가가 아동용 영화 대사라니.",
    151: "뮤는 모든 포켓몬의 조상이라는 설정. 151번이라 숨겨진 포켓몬 취급. 트럭 밑에 뮤 있다는 루머로 전 세계가 들썩.",
    152: "죠토 스타터 중 인기 꼴찌. 지우가 선택했지만 왜 치코리타라는 반응이 다수. 풀타입의 한계.",
    153: "베이리프는 지우한테 반해서 들이받는 애정표현. 트레이너에게 사랑을 느끼는 포켓몬 설정이 좀 아슬아슬.",
    154: "메가니움은 경쟁에서 죠토 스타터 중 가장 약함. 풀 단타입에 화력도 내구도 애매. 꽃이 예쁜 게 위안.",
    155: "브케인은 죠토 스타터 인기 1위. 등에 불꽃이 기분에 따라 바뀜. 히노아라시 팬덤이 의외로 거대.",
    156: "마그케인은 중간진화 특유의 존재감 부족. 블레이범으로의 징검다리 인생.",
    157: "블레이범은 죠토 불꽃 스타터 최종. 히스이 폼에서 불꽃/고스트로 부활. 경쟁에서 히스이 폼이 대활약.",
    158: "리아코는 물 악어인데 춤추는 모습이 귀여움. 죠토 물 스타터 팬덤이 꽤 탄탄.",
    159: "엘리게이는 리아코 진화형. 중간진화인데 나름 인기 있음. 악어가 직립보행하는 시점.",
    160: "장크로다일은 영어 이름이 Feraligatr. 10글자 제한 때문에 Feraligator에서 o를 뺌. 글자수 제한의 희생양.",
    161: "꼬리선은 보초 서는 포켓몬. 초반 노말타입의 금은 버전. 꼬렛보다는 귀여운데 그래도 약함.",
    162: "다꼬리는 꼬리선 진화. 길쭉한 몸이 족제비 모티브. 경쟁에서 안 쓰이지만 디자인 팬은 있음.",
    163: "부우부는 올빼미 포켓몬. 야부엉으로 진화. 머리를 180도 돌리는 설정이 현실 올빼미와 동일.",
    164: "야부엉은 지우가 색이 다른 개체를 잡음. 애니에서 색다른 포켓몬 잡는 희귀 이벤트.",
    165: "레디바는 금은 초반 벌레. 5마리가 모여야 활동한다는 설정인데 1마리로 배틀하니 약할 수밖에.",
    166: "레디안은 별빛으로 방향을 잡는다는 로맨틱 설정. 하지만 종족값이 처참해서 경쟁에서는 빛을 못 봄.",
    167: "페이검은 거미 포켓몬. 밤에 거미줄 치고 기다리는 설정. 금은 야간 출현 포켓몬의 대표.",
    168: "아리아도스는 거미줄로 먹이를 잡는 포켓몬. 독/벌레 조합이 약점 투성이라 경쟁에서 고생.",
    169: "크로뱃은 친밀도 진화의 아이콘. 웅이의 크로뱃이 유명. 동굴 악몽 주바트가 최종적으로 강해지는 성장 서사.",
    170: "초라기는 심해어 모티브. 안테나에서 빛을 내는 설정. 물/전기 조합이 독특함.",
    171: "랜턴은 심해에서 빛으로 먹이를 유인. 특성 축전으로 물 기술 흡수. 의외로 방특이 높아서 서포터로 활용.",
    172: "피츄는 피카츄의 베이비 포켓몬. 자기 전기에 자기가 놀라는 설정이 귀여움. 대난투에서도 참전.",
    173: "삐는 삐삐의 베이비. 별똥별 타고 온다는 설정. 우주 포켓몬 팬 이론의 근거.",
    174: "푸푸린은 푸린의 베이비. 공 모양으로 통통 튀는 설정. 존재감은 푸린보다 더 없음.",
    175: "토게피는 금은 발매 전 애니에서 먼저 공개된 2세대 홍보대사. 이슬이의 아기 포켓몬으로 인기폭발.",
    176: "토게틱은 행복한 사람에게만 나타난다는 설정. 4세대에서 토게키스 진화 추가되면서 가치 상승.",
    177: "네이티는 항상 한쪽을 응시하는 새. 토템폴 모티브. 작고 동그란 게 귀여운데 에스퍼/비행이라 약점 많음.",
    178: "네이티오는 미래를 보는 포켓몬. 매직가드 특성으로 경쟁에서 간간이 보임. 항상 같은 방향을 보는 디자인이 독특.",
    179: "메리프는 양 전기 포켓몬. 금은 초반 전기타입 유일한 선택지라 거의 필수 영입.",
    180: "보송송은 메리프 진화. 털이 빠져서 분홍 피부가 드러남. 양모 깎인 양의 현실감.",
    181: "전룡은 메가진화에서 갑자기 드래곤 타입 추가. 양이 용이 되는 이유를 아무도 모름.",
    182: "아르코는 빛의돌로 진화하는 꽃 포켓몬. 냄새꼬의 분기진화인데 존재감이 거의 없는 비운의 진화형.",
    183: "마릴은 금은 발매 전 PIKABLU라는 루머로 유명. 물/페어리가 된 지금도 피카츄 아류 이미지를 벗지 못함.",
    184: "마릴리는 의외로 경쟁에서 강함. 특성 힘세고강한으로 공격력 실질 2배. 귀여운 외모와 달리 물/페어리 격투가.",
    185: "꼬지모는 나무로 위장한 바위 포켓몬. 물뿌리개 쓰면 정체 발각. 금은에서 길 막고 서있는 가짜 나무.",
    186: "왕구리는 왕의징표석으로 진화. 강챙이와 분기진화인데 개구리 왕자 컨셉. 이슬비 특성으로 비팀 서포터.",
    187: "통통코는 바람에 날아가는 민들레 포켓몬. 너무 가벼워서 바람 불면 날아감. 존재 자체가 위태로움.",
    188: "두코는 통통코 진화. 꽃이 피면 기분이 좋아진다는 설정. 중간진화 투명인간.",
    189: "솜솜코는 바람타고 세계여행. 경쟁에서 엽록소 쾌청 세팅으로 가끔 보이지만 대체로 마이너.",
    190: "에이팜은 꼬리 손이 진짜 손보다 기민함. 양손잡이인데 꼬리가 더 유능한 3번째 손.",
    191: "해너츠는 전체 포켓몬 중 종족값 합계가 가장 낮음. 180이라는 처참한 수치.",
    192: "해루미는 해너츠 태양의돌 진화. 맑은 날만 기분 좋고 흐린 날 우울해하는 기상 의존 포켓몬.",
    193: "왕자리는 금은에서 진화가 없었는데 4세대에서 메가자리 진화 추가. 20년 기다린 보람.",
    194: "우파라서 포켓몬 커뮤에서 정치드립 당하는 유일한 포켓몬. 팔데아에서 독타입 우파로 환생. 본인은 그냥 멍때리는 중.",
    195: "누오는 물/땅이라 풀 4배 약점인데 특성 저수면 물 무효. 항상 웃고 있는 얼굴이 밈.",
    196: "에브이는 낮에 친밀도 진화. 에스퍼 이브이라 매직미러 숨특이 핵심. 고양이 같은 우아한 디자인.",
    197: "블래키는 밤에 친밀도 진화. 달빛 링이 빛나는 디자인 인기 1위급. 경쟁에서 막이+독독독 조합으로 상대 멘탈 파괴.",
    198: "니로우는 마피아 보스 모자 디자인. 4세대에서 돈크로우로 진화. 악/비행이라 페어리 등장 전까지 약점 적었음.",
    199: "야도킹은 셀러가 머리를 물어서 천재가 됨. 야도란은 꼬리, 야도킹은 머리. 물리는 위치에 따라 인생이 바뀌는 포켓몬.",
    200: "무우마는 목걸이가 본체라는 설. 금은 유일한 순수 고스트. 4세대에서 무우마직으로 진화하며 경쟁급 상승.",
    201: "안농은 알파벳 26자에 느낌표와 물음표까지 총 28종류. 유적에서만 나오는데 도감 채우려면 28마리 다 잡아야 함.",
    202: "소옹은 반격기만 사용 가능. 카운터와 미러코트뿐. 로켓단 로이의 소옹이 멋대로 볼에서 나오는 게 개그포인트.",
    203: "키링키는 머리와 꼬리가 각각 다른 뇌를 가짐. 꼬리가 잠 안 자고 보초 선다는 설정. 포켓몬계의 투잡러.",
    204: "피콘은 솔방울 모티브인데 벌레타입. 자폭을 배우는 솔방울이라는 위험한 설정.",
    205: "쏘콘은 피콘 진화. 대폭발을 배움. 진화하면 더 크게 자폭하는 게 인생 목표인 포켓몬.",
    206: "노고치는 팬들이 20년 넘게 진화형을 요구. 9세대에서 드디어 노고나가 추가됨. 기다림은 배신하지 않는다.",
    207: "글라이거는 전갈+박쥐 합체 디자인. 4세대에서 글라이온으로 진화하면서 경쟁에서 독살 전략의 핵심이 됨.",
    208: "강철톤은 롱스톤에 금속코트 통신교환 진화. 메가강철톤은 모래힘 특성으로 모래팀 핵심.",
    209: "블루는 불독 모티브인데 페어리 타입. 무서운 얼굴인데 겁쟁이라는 갭 모에 설정.",
    210: "그랑블루는 블루 진화. 입이 거대한데 사실 겁쟁이. 경쟁에서 간간이 위협 특성으로 쓰임.",
    211: "침바루는 복어+성게 합체. 독/물 조합. 히스이 폼에서 독/악으로 변경되고 진화형 하리만론 추가.",
    212: "핫삼은 약점이 불꽃 단 하나. 벌레/강철+테크니션+바렛펀치 조합이 경쟁 역사상 전설. 디자인도 인기도 최상위.",
    213: "단단지는 이론상 포켓몬 중 가장 높은 데미지를 줄 수 있음. 힘세고강한+메트로놈 무한 스택으로 천문학적 수치. 실전에서는 그냥 느림.",
    214: "헤라크로스는 지우의 포켓몬. 벌레타입 최강 중 하나. 메가진화로 스킬링크 연속기 머신.",
    215: "포푸니는 날카로운 발톱의 악/얼음. 4세대에서 포푸니라로 진화. 히스이에서 포푸니치로 분기진화 추가.",
    216: "깜지곰은 꿀 좋아하는 아기곰. 이마의 초승달 마크에 꿀이 스며있다는 설정이 귀여움.",
    217: "링곰은 깜지곰 진화. 숲에서 꿀을 찾아다니는 설정. 히스이에서 다갈곰으로 진화 추가.",
    218: "마그마그는 달팽이 용암 포켓몬. 설정상 체온 1만도인데 옆에 서도 괜찮은 포켓몬 세계관 물리법칙.",
    219: "마그카르고 체온이 1만도. 태양 표면보다 뜨거움. 마그카르고 옆에 서면 증발해야 정상인데 트레이너가 만져도 됨.",
    220: "꾸꾸리는 털이 눈을 가려서 앞이 안 보임. 그래서 코로 냄새 맡으며 다님. 맘모꾸리까지 3단 진화.",
    221: "메꾸리는 꾸꾸리 진화. 4세대에서 맘모꾸리 진화 추가되면서 경쟁에서 스텔스록+얼음뭉치 셔틀로 각광.",
    222: "코산호는 산호 모티브인데 가라르에서 환경파괴로 죽은 고스트 코산호 등장. 포켓몬이 환경문제를 다루는 무거운 순간.",
    223: "총어는 물고기인데 이름에 총이 들어감. 진화하면 문어가 됨. 물고기에서 문어로의 진화가 포켓몬 역사상 가장 이해 안 되는 진화 루트.",
    224: "대포무노는 문어인데 총어에서 진화. 물고기가 문어가 되는 생물학 무시. 먹물 대포를 쏘는 설정.",
    225: "딜리버드는 선물 배달하는 산타 포켓몬. 기술 선물이 랜덤으로 회복이나 데미지. 경쟁에서 쓸 이유가 없는 시즌한정 캐릭터.",
    226: "만타인은 가오리 포켓몬. 7세대에서 만타인서핑 미니게임 추가. 등에 총어가 붙어있는 게 기본 디자인.",
    227: "무장조는 강철/비행. 경쟁에서 스텔스록+회오리바람+도발 깔아놓는 물리수비의 아이콘.",
    228: "델빌은 불꽃/악 개 포켓몬. 밤에 울음소리가 저승사자를 부른다는 설정. 도베르만+지옥견 모티브.",
    229: "헬가는 델빌 진화. 메가진화 시 태양의힘 특성으로 화력 폭발. 디자인이 멋있어서 인기 많은 악타입.",
    230: "킹드라는 물/드래곤. 비바라기팀 에이스. 쓱쓱 특성으로 스피드 2배. 해마가 용이 되는 건 해룡 전설에서 따옴.",
    231: "코코리는 아기 코끼리. 코로 물을 뿌리며 노는 설정이 귀여움. 지우가 알에서 부화시킨 포켓몬.",
    232: "코리갑은 타이어처럼 구르는 코끼리. 구르기 기술이 강력. 방어력이 높아서 물리벽으로 쓰임.",
    233: "폴리곤2는 폴리곤의 업그레이드 진화. 폴리곤 쇼크 사건 때문에 진화형인데도 애니 출연 금지. 연좌제의 피해자.",
    234: "노라키는 뿔 사슴 포켓몬. 뿔에서 공간이 왜곡된다는 설정. 경쟁에서 위협+전기자석파 서포터로 가끔 보임.",
    235: "루브도는 스케치로 모든 기술을 배울 수 있는 유일한 포켓몬. 교배용 기술 유전 필수. 화가 컨셉인데 실전에서는 기술 전달자.",
    236: "배루키는 시라소몬/홍수몬/카포에라 3분기 진화. 공격이 방어보다 높으면 시라소몬, 방어가 높으면 홍수몬, 같으면 카포에라.",
    237: "카포에라는 카포에이라 모티브. 머리로 빙빙 도는 기술. 위협 특성에 마하펀치로 하위 티어에서 활약.",
    238: "뽀뽀라는 루주라의 베이비. 루주라 디자인 논란의 여파로 뽀뽀라도 조용히 처리됨.",
    239: "에레키드는 에레브의 베이비. 전기 플러그 모양 머리가 특징.",
    240: "마그비는 마그마의 베이비. 입에서 불꽃 내뿜는 아기. 포켓몬 세계관 육아의 위험성을 보여줌.",
    241: "목장 관장 꼭두의 구르기 밀탱크가 금은 플레이어 PTSD 원인 1위. 밀탱크만 들어도 손이 떨리는 사람 다수.",
    242: "해피너스는 HP가 255로 전 포켓몬 1위. 자연회복+알낳기로 독살팀의 핵심.",
    243: "라이코는 전설의 3수 중 전기. 금은에서 돌아다니는 로밍 전설의 원조. 잡으려면 마스터볼 아니면 인내심 테스트.",
    244: "앤테이는 전설 3수 중 불꽃. 극장판 3편 주인공. 아빠를 찾는 소녀의 환상으로 등장한 감동 스토리.",
    245: "스이쿤은 전설 3수 중 물. 크리스탈 버전 패키지. 디자인 인기가 3수 중 압도적 1위.",
    246: "애버라스는 유충인데 땅/바위. 마기라스까지 키우는 게 금은의 숨겨진 엔드콘텐츠. 레벨 55에 최종진화라 인내심 필요.",
    247: "데기라스는 번데기인데 격투를 안 배움. 껍질 안에서 움직이는 설정. 중간진화 투명인간 시리즈.",
    248: "마기라스는 고질라 모티브 600족. 모래팀의 핵심. 특성 모래날림으로 등장만 해도 날씨 변경. 메가진화 시 공격 164의 괴물.",
    249: "루기아는 극장판 2편의 주인공. 바다의 신인데 에스퍼/비행. 물타입 아닌 게 30년째 의문.",
    250: "호오우는 애니 1화에서 지우가 처음 본 전설의 포켓몬. 금 버전 패키지인데 루기아가 더 유명한 비운의 전설.",
    251: "세레비는 시간여행 포켓몬. GS볼 이벤트가 미완성으로 남은 포켓몬 역사 최대 미해결 사건. 영원한 떡밥.",
    # --- Gen 3 (호엔 지방) ---
    252: "나무지기는 배에 씨앗 키우는 도마뱀인데 최종진화 나무킹이 닌자 간지라 3세대 스타터 인기 1위 다툼. 포켓몬 불던 시절 이름도 '나무'인데 풀타입이라 직관적.",
    253: "나무돌이는 불가사의 던전 시간/어둠의 탐험대에서 파트너로 나와서 스토리 울면서 본 사람들한테 트라우마급 감동. 팔의 잎사귀 칼날이 실제론 꽤 잔인한 설정.",
    254: "나무킹은 메가진화로 풀/드래곤 받았는데 드래곤주제에 용성군을 못 배움. 커뮤에서 '이게 드래곤이냐' 밈 양산. 스피드 120으로 스타터 최종진화 중 가장 빠름.",
    255: "아차모는 병아리에서 킥복서로 변신하는 포켓몬계 언더독 스토리. 처음 공개됐을 때 '치킨이 왜 격투타입이냐'고 난리났는데 지금은 인기 스타터 TOP10.",
    256: "영치코는 중간진화치고 의외로 팬아트 많음. 닭싸움 격투가 컨셉이 확실하고, 번치코보다 이 단계가 더 멋있다는 소수파도 있음.",
    257: "번치코는 숨특 가속이 너무 사기라 스타터 주제에 Uber 추방당한 전설. 5세대 드림특성 해금 후 경쟁배틀 밸런스를 박살냄. 불/격투 스타터의 원조.",
    258: "물짱이는 인터넷 초창기 'So I herd u liek Mudkipz' 밈으로 세계구급 유명세. 4chan에서 시작된 이 밈이 포켓몬 밈 문화의 시초 중 하나. 얼굴이 너무 밈감.",
    259: "늪짱이는 물짱이의 귀여움이 다 어디 갔냐는 소리 듣는 중간진화. 물/땅 조합의 시작점인데 디자인이 '대짱이까지 참자' 느낌.",
    260: "대짱이는 물/땅이라 약점이 풀 4배 하나뿐인 갓타입. 메가진화까지 받아서 비팀 에이스. Mudkipz 밈 덕에 해외에서 3세대 스타터 인기 1위.",
    261: "포챠나는 3세대 초반루트 악타입 강아지인데 최종진화가 너무 약해서 2번도로 지나면 바로 박스행. 위협 특성만 빼가고 버려지는 비운.",
    262: "그라에나는 디자인은 멋있는 하이에나인데 종족값 합계 420이라 경쟁에선 존재 의미 없음. 위협 특성 물려주고 퇴장하는 도구몬 신세.",
    263: "지그제구리는 줍기 특성으로 아이템 파밍 노예 확정. 자기 의지 상관없이 평생 아이템만 줍다 은퇴하는 포켓몬계의 사축. 갈지자 걷는 모습이 밈.",
    264: "직구리는 배속+신속 콤보로 의외의 깜짝 활약이 가능한데, 99%는 줍기 노예로만 기억함. 8세대 가라르 폼에서 갑자기 악/노말로 재탄생.",
    265: "개무소는 진화가 성격값 랜덤이라 뷰티플라이 원하는데 독케일 뜨면 리셋. 3세대 초반의 가챠 포켓몬. 울면서 리셋한 사람 한둘이 아님.",
    266: "실쿤은 딱풀-단데기 계보의 3세대 번데기. 굳히기밖에 못 쓰는 시리즈 전통. 이 단계에서 레벨업하는 고통은 모든 세대 공통.",
    267: "뷰티플라이는 개무소 가챠에서 당첨인데 막상 써보면 약함. 버터플 호엔 버전이라는 평가가 정확. 나비인데 왜 이렇게 존재감이 없냐.",
    268: "카스쿤은 실쿤이랑 겉모습 거의 같은데 눈빛이 다름. 구분 못 하면 독케일 확정이라 초보들의 트라우마. 번데기 구분법이 공략 필수였던 시절.",
    269: "독케일은 뷰티플라이 원했던 사람들의 원망이 서린 포켓몬. 의외로 독/벌레+방진 특성이 나쁘진 않은데 아무도 안 씀.",
    270: "연꽃몬은 멕시코 솜브레로 쓴 수련잎 갓파. 비 오면 신나서 춤추는 설정이 로파파까지 이어지는 파티 라인의 시작.",
    271: "로토스는 게으른 갓파 그 자체. 비 안 오면 아무것도 안 하다가 비 오면 갑자기 액티브해지는 내향인 포켓몬.",
    272: "로파파는 비 오면 춤추는 파티몬. 쓱쓱+비팀 조합이 경쟁에서 의외로 강력한데, 봤을 때 기분이 좋아지는 디자인이 진짜 장점. 이 녀석 보고 안 웃는 사람 없음.",
    273: "도토링은 나뭇잎 쓰고 나무에 매달려 열매인 척 위장하는 포켓몬. 새 포켓몬한테 실수로 쪼이면 놀라서 떨어지는 코미디 설정.",
    274: "잎새코는 텐구 모티브인데 잎사귀 피리로 사람 홀리는 설정이 은근 무서움. 코가 길수록 센 개체라는 설정 때문에 코 큰 잎새코 잡으려는 사람들 있었음.",
    275: "다탱구는 텐구 완성형인데 풀/악이라 벌레 4배. 엽록소+날씨볼 세팅으로 맑은날팀에서 가끔 쓰이는데, 부채질로 바람 일으키는 모션이 간지.",
    276: "테일로는 근성 특성으로 화상 걸리면 더 강해지는 새. 찌르호크의 호엔 버전인데 용감하게 큰 적한테 덤비는 설정이 좋아서 팬 꽤 있음.",
    277: "스왈로는 근성+화염구슬 콤보의 원조새. 일부러 화상 걸려서 공격력 올리는 마조 전법. 제비 모티브라 디자인도 날렵한데 경쟁에선 찌르호크한테 밀림.",
    278: "갈모매는 파도타기만 쓰면 무조건 만나는 3세대의 주뱃. 호엔 바다 어디서든 갈모매 떼한테 시달리는 트라우마는 RSE 유저 공통 기억.",
    279: "패리퍼는 펠리컨 우편배달부였다가 7세대에서 잔비 특성 받고 OU급 비팀 세터로 대출세. 아무도 예상 못 한 마이너→메이저 역전 드라마의 주인공.",
    280: "랄토스는 가디안/엘레이드까지 키워야 하는데 초반에 잡으면 혼자 레벨업 못해서 학습장치 필수. 노가다의 대가로 에이스를 얻는 포켓몬계의 투자.",
    281: "킬리아는 발레리나 컨셉인데 4세대에서 수컷 전용 엘레이드 분기가 추가됨. 킬리아 단계에서 가디안 갈지 엘레이드 갈지 고민하는 갈림길의 포켓몬.",
    282: "가디안은 원작에선 기사+수호자 컨셉인데 퍼리 문화에서 압도적 인기를 자랑하는 포켓몬. R34 검색량 부동의 1위. 트레이너를 위해 블랙홀도 만드는 헌신 설정이 팬덤을 더 자극함.",
    283: "비구술은 소금쟁이 모티브 물/벌레인데 진화하면 물타입이 사라지고 벌레/비행이 됨. 진화시켰더니 타입이 바뀌어서 당황한 사람 다수.",
    284: "비나방은 비구술에서 진화하면 물이 날아가고 벌레/비행이 되는 사기(?) 진화. 덕분에 물 약점이 사라지긴 하는데 어차피 안 쓰임.",
    285: "버섯꼬는 귀여운 꼬마 버섯인데 진화하면 갑자기 격투 공룡이 됨. 포켓몬 진화 미스터리 TOP5. 뭘 먹고 자랐길래.",
    286: "버섯모는 포자(100% 잠재우기)+마하펀치 콤보가 경쟁배틀 역사상 가장 욕 먹은 전략 중 하나. 잠들면 끝인데 막을 방법이 거의 없음. 상대하면 혈압 오르는 악마.",
    287: "게을로는 하루 20시간 잠자는 설정. 나태 특성의 원조인데 게을킹이 될 놈이 어릴 때부터 이러니 미래가 보임. 이 녀석이 670족의 아기라는 게 반전.",
    288: "발바로는 게을로↔게을킹과 정반대로 절대 가만 못 있는 ADHD 원숭이. 진화 라인에서 혼자 부지런한데, 결국 진화하면 다시 게을러짐. 반항기가 낀 중2.",
    289: "게을킹은 종족값 670으로 비전설 최강급인데 나태 특성 때문에 한 턴 걸러 행동함. 스킬스왑으로 특성 바꾸면 진짜 신이 되는데 그 한 턴이 치명적. 포켓몬계의 능력 봉인 클리셰.",
    290: "토중몬은 진화시키면 아이스크+껍질몬 2마리가 동시에 나오는 유일한 포켓몬. 파티에 빈칸 없으면 껍질몬 못 얻어서 나중에 후회하는 사람 많았음.",
    291: "아이스크는 스피드 160에 가속 특성이라 턴 지날수록 빨라짐. 칼춤 한 번 추면 멈출 수 없는 스윕머신. 3세대 닌자 컨셉 최고봉.",
    292: "껍질몬은 HP 1인데 불가사의부적 때문에 효과발군 아니면 데미지 0. 약점 기술 없는 팀 만나면 영원히 안 죽는 트롤의 정점. 독압정이 천적.",
    293: "소곤룡은 속삭이는 소리인데 놀라면 제트기급 울음소리를 냄. 놀라면 더 시끄럽고, 시끄러우니까 더 놀라는 무한 소음 루프. 방음 아파트 필요.",
    294: "노공룡은 발 구르면 지진 나는 파워. 소곤룡 시절 울보였던 게 거짓말 같은 변신인데, 진화 전 트라우마가 분노로 바뀐 느낌.",
    295: "폭음룡은 이름부터 폭음. 울음소리로 집을 날리는 설정인데 경쟁에선 방음 특성으로 오히려 소리기술 방어용. 이름과 역할이 반대.",
    296: "마크탕은 귀여운 아기 스모 선수. 배때기 토닥토닥하는 모션이 귀여운데, 하리뭉이 되면 진지한 격투가로 변신.",
    297: "하리뭉은 근성+배짱포로 한방 노리는 로망의 스모 챔피언. HP 높고 내구 좋아서 맞으면서 때리는 스타일. 두꺼운 지방 특성도 가능.",
    298: "루리리는 마릴 베이비인데 노말/페어리. 진화하면 물이 되는 타입변경 케이스. 성별비가 75% 암컷이라 진화하면 성별이 바뀌는 버그도 있었음. 트랜스 포켓몬 밈.",
    299: "코코파스는 코가 자석인 모아이. 항상 북쪽 가리키는 나침반인데 4세대에서 대코파스로 진화하면 코 대신 미니코코파스 3마리가 주변을 돔. 뭔가 더 이상해짐.",
    300: "에나비는 고양이 포켓몬 귀여움 담당인데 달의돌 필요. 나옹-페르시온의 호엔 버전인데 경쟁력은 더 슬픈 수준.",
    301: "델케티는 진화해도 종족값 합계 380이라 약함. 정상화 특성이 유일한 개성인데 그마저도 다른 포켓몬이 더 잘 씀. 노말 고양이의 비애.",
    302: "깜까미는 6세대 전까지 약점 0개였던 유일한 타입 조합(악/고스트). 페어리 나오기 전 약점 없는 트롤로 유명했고, 메가진화 매직미러로 진화하면 상대 보조기술 반사하는 궁극의 트롤몬.",
    303: "입치트는 후타쿠치온나(이구녀) 요괴 모티브인데 메가진화 시 거대한힘으로 실질 공격력 2배. 페어리/강철에 공격 172 상당이라 OU에서 날뛰었던 사기캐. 밴 먹을 만했음.",
    304: "가보리는 철 먹는 아기 공룡인데 굶으면 철도 레일이든 다리든 닥치는 대로 먹음. 귀여운 얼굴로 인프라를 파괴하는 포켓몬.",
    305: "갱도라는 몸이 강철이라 트럭이 와도 끄떡없다는 설정. 광산에서 철광석 먹고 사는데 보스로라까지 버티는 레벨업이 고통.",
    306: "보스로라는 메가진화로 필터 특성 받아서 효과발군을 줄임. 풀메탈바디 탱커인데 4배 약점 2개(격투/땅)가 치명적. 간지는 좋은데 약점이 너무 뼈아픔.",
    307: "요가랑은 순수한힘(공격력 실질 2배) 특성의 원조. 작은 몸에서 나오는 미친 화력. 요가 포즈 잡는 모션이 귀여운데 때리면 아픔.",
    308: "요가램은 순수한힘+메가진화로 공격력이 미침. 높은킥 한 방에 웬만한 건 녹음. 격투/에스퍼 조합에 화력까지 갖춘 수행자.",
    309: "썬더라이는 귀여운 전기 강아지. 정전기 특성으로 만지면 마비되는데 귀여워서 만지고 싶은 딜레마. 진화하면 꽤 멋있어짐.",
    310: "썬더볼트는 메가진화로 위협 특성을 받아서 물리 어태커 견제 가능. 번개 갈기 디자인 멋있는데 전기 단타입이라 한계가 있음.",
    311: "플러시는 마이농이랑 세트로 더블배틀 응원단 컨셉인데 싱글에선 존재 의미 없음. 둘이 같이 써도 약하다는 게 진짜 문제.",
    312: "마이농은 플러시 없으면 의미 없고 같이 있어도 약함. 우정 콤보라는 컨셉은 좋은데 현실은 '둘 다 NU도 못 감' 수준. 우정으로 종족값은 못 메꿈.",
    313: "볼비트는 꼬리 빛으로 네오비트한테 구애하는 수컷 전용 반딧불. 경쟁에선 존재감이 진짜 반딧불 수준으로 희미함. 꼬리흔들기로 기억됨.",
    314: "네오비트는 볼비트의 짝인 암컷 전용 반딧불인데 볼비트보다 더 안 쓰임. 나비춤 배우는 게 유일한 개성이었는데 그것도 다른 애들이 더 잘 씀.",
    315: "로젤리아는 원래 단일 포켓몬이었는데 4세대에서 갑자기 로즈레이드 진화+수비 베이비 추가. 중간진화였다는 반전. 독/풀에 자연회복이 쓸만해서 중위권.",
    316: "꼴깍몬은 뭐든 녹이는 위산을 가진 위장 포켓몬. 먹으면 뭐든 소화하는 블랙홀 위장인데, 타이어도 소화한다는 설정이 좀 무서움.",
    317: "꿀꺽몬은 위산이 더 강해져서 폐차도 녹임. 디자인이 징그러운 축에 속하는데 독 단타입이라 경쟁에서도 안 쓰이고, 팬도 거의 없는 슬픈 포켓몬.",
    318: "샤프니아는 피라냐인데 가속 특성이라 턴마다 빨라짐. 떼로 다니면 뭐든 뜯어먹는 설정. 진화하면 메가상어가 되는 로망.",
    319: "샤크니아는 가속으로 속도 올리고 보호로 버티다가 스윕하는 상어. 메가진화 시 강한턱으로 물기기술 위력 폭발. 바다의 깡패인데 경쟁에서도 꽤 쓰임.",
    320: "고래왕자는 동글동글 아기 고래인데 진화하면 14.5m 괴물이 됨. 이 귀여운 게 어떻게 그렇게 커지냐는 의문.",
    321: "고래왕은 14.5m로 역대 가장 큰 포켓몬 중 하나. 고래왕 옆에 에네코 놓은 크기 비교짤이 유명한 밈. 너무 커서 3D 모델이 화면을 뚫음.",
    322: "둔타는 이름부터 '둔하다'. 등에 마그마 혹이 있는 낙타인데 이름이 너무 직관적이라 한 번 들으면 안 까먹음.",
    323: "폭타는 화산 낙타 최종진화. 메가진화 시 분노의발굽으로 지진이 바위에도 효과발군. 트릭룸 에이스로 VGC에서 가끔 보임.",
    324: "코터스는 가뭄 특성으로 맑은날팀 세터. 속도 20이라 트릭룸 필수인데, VGC 더블배틀에서 맑은날+분화 콤보가 강력. 느린 게 장점이 되는 역설.",
    325: "피그점프는 꼬리로 통통 튀는 돼지인데 멈추면 심장이 멈춘다는 공포 설정. 영원히 뛰어야 사는 포켓몬. 뛰다 지치면 어떡하냐는 의문.",
    326: "피그킹은 머리 진주가 커졌는데 경쟁에선 '진주만 크고 할 줄 아는 건 없는' 마이너. 에스퍼 단타입의 한계를 제대로 보여줌.",
    327: "얼루기는 무늬 패턴이 40억 가지 이상이라 같은 개체가 없음. 포켓몬계의 지문. 비틀비틀 걷는 모션 때문에 항상 술 취한 판다 밈.",
    328: "톱치는 개미지옥 유충인데 스피드 10. 역대 가장 느린 포켓몬 중 하나. 근데 이 느림보가 진화하면 플라이곤이라는 반전. 인생은 모르는 거.",
    329: "비브라바는 톱치→플라이곤 사이의 애매한 사춘기. 날개 진동으로 초음파 공격인데, 이 단계에서 레벨업하는 게 고통. 조금만 참으면 플라이곤.",
    330: "플라이곤은 디자인 인기 최상위권인데 메가진화를 못 받음. 같은 세대 가디안한테 메가 뺏겼다는 팬 불만이 10년째 현재진행형. 한국 커뮤에서 '플라이곤 메가 언제냐'는 밈.",
    331: "선인왕은 선인장에 팔이 달린 풀/악인데 너무 마이너라 팬 찾기가 더 어려움. 모래장막 특성은 괜찮은데 종족값이 아쉬움.",
    332: "밤선인은 밤에만 움직이는 허수아비 선인장. 사막에서 길 잃은 여행자를 무리 지어 따라다닌다는 도감 설명이 공포 그 자체. 뒤돌아보면 서 있음.",
    333: "파비코는 솜사탕 같은 새. 머리에 앉으면 솜모자처럼 보이는 귀여움 담당인데, 진화하면 드래곤이 되는 반전. 이 솜뭉치가?",
    334: "파비코리는 메가진화로 드래곤/페어리라는 역대급 갓타입 조합 획득. 솜구름 디자인이 메가진화하면 더 화려해지는데, 이게 파비코의 진화라는 게 아직도 신기함.",
    335: "쟝고는 세비퍼의 천적 몽구스. 독 면역 특성에 배의 상처 무늬가 세비퍼와의 전투 흔적. 애니에서 세비퍼랑 싸우는 장면이 인상적이었는데 경쟁에선 둘 다 안 씀.",
    336: "세비퍼는 쟝고와 영원한 라이벌 독사. 둘의 관계가 나옹과 개와 같다는 설정. 칼춤 배우는데 팔이 없어서 어떻게 추냐는 밈이 있음.",
    337: "루나톤은 달 모양 운석인데 솔록이랑 세트로 나옴. 보름달에 강해진다는 설정이지만 경쟁에선 솔록이랑 같이 '안 쓰는 세트' 취급.",
    338: "솔록은 태양 모양 운석인데 루나톤이랑 같이 안 쓰임. 둘 다 바위/에스퍼인데 차별점도 별로 없고 종족값도 같음. 쌍둥이 마이너.",
    339: "미꾸리는 미꾸라지 모티브 물/땅. 수염으로 지진을 예지하는 설정인데, 일본에서 실제 메기가 지진 예지한다는 전설이 모티브.",
    340: "메깅은 미꾸라지→메기 진화. 물/땅이라 약점이 풀 하나뿐. 둔감 특성으로 도발 안 먹히는 탱커인데 마이너 취급.",
    341: "가재군은 호전적인 아기 가재. 집게로 뭐든 집어서 안 놓는 설정인데, 6세대에서 적응력 받은 가재장군이 대박나면서 재평가.",
    342: "가재장군은 적응력으로 자속 보정 2배라 아쿠아제트+깨물어부수기가 미친 화력. 6세대에서 악타입 추가+메가런처까지 받아서 물의파동이 핵폭탄급. 숨은 강캐.",
    343: "오뚝군은 고대 유적 오뚝이. 천년 동안 한 자세로 명상했다는 설정인데 쓰러뜨려도 다시 일어나는 게 진짜 오뚝이.",
    344: "점토도리는 고대 인형이 살아난 콘셉트. 부유 특성이라 땅타입인데 땅기술 안 먹힘. 자기가 땅인데 땅이 안 통하는 모순 포켓몬.",
    345: "릴링은 고대 바다나리 화석. 흡반 특성으로 상대가 교체 못 하게 잡아둠. 화석 포켓몬인데 디자인이 식물처럼 생겨서 헷갈리는 사람 많음.",
    346: "릴리요는 촉수로 먹이를 잡아먹는 포식 식물. 바위/풀이라 약점이 6개인 비극적 타입 조합. 화석치고 너무 불쌍한 타입 배분.",
    347: "아노딥스는 아노말로카리스 모티브 화석. 쾌속 특성으로 비 오면 스피드 2배인데, 벌레/바위라 물에 약한 게 아이러니.",
    348: "아말도는 갑옷 입은 고대 전사인데 4배 약점 2개(물/바위)라 경쟁에서 힘듦. 디자인은 역대 화석 중 최고급인데 타입이 발목 잡음.",
    349: "빈티나는 3세대의 잉어킹. 특정 타일 6칸에서만 낚이고 확률도 미쳤음. 아름다움 컨디션 올려서 진화하는 과정이 고행인데, 결과물이 밀로틱이라 참을 수 있었음.",
    350: "밀로틱은 포켓몬 역대 가장 아름다운 포켓몬 투표 만년 1위. 빈티나의 못생김→밀로틱의 아름다움이 잉어킹→갸라도스의 3세대 리메이크. 경쟁에서도 화염구슬+불굴의마음으로 쓸만.",
    351: "캐스퐁은 날씨에 따라 폼 변하는 기상캐스터 포켓몬. 맑음/비/눈 3폼인데 종족값 420이라 경쟁에선 날씨 장난감 수준. 컨셉은 좋은데 스펙이 안 따라줌.",
    352: "켈리몬은 색변환 특성으로 맞은 기술 타입으로 바뀌는 카멜레온. 7세대 변환자재 나오기 전까지 유일한 타입변환이었는데, 그마저도 맞아야 바뀌니 실전성 제로.",
    353: "어둠대신은 버려진 인형에 원한이 깃든 고스트. 입에 지퍼 달린 디자인이 소름인데, 저주받은 인형 컨셉이 갸라르 커스텀까지 이어진 인기 디자인.",
    354: "다크펫은 메가진화하면 지퍼가 열리면서 본체가 드러나는 공포 디자인. 저주받은 인형의 완성형. 트릭+라이프오브로 상대 짜증나게 하는 트롤 플레이 가능.",
    355: "해골몽은 해골 가면 쓴 유령인데 가면 안쪽에 진짜 얼굴이 있다는 설정. 하나의 눈으로 벽 너머를 보는데, 뭘 보고 있는지는 아무도 모름. 무서움.",
    356: "미라몽은 4세대에서 야느와르몽으로 추가진화 받기 전까지 진화돌가루+기합머리띠 탱커로 쓰였음. 블랙홀 같은 몸으로 뭐든 흡수하는 설정.",
    357: "트로피우스는 목에 바나나가 열리는 초식공룡. 비행/풀인데 이 체형으로 어떻게 나냐는 의문. 아이들한테 바나나 나눠주는 착한 설정인데 종족값이 너무 아쉬움.",
    358: "치렁은 풍경(풍탁) 모티브 에스퍼인데 4세대에서 랑딸딸 베이비가 추가됨. 바람에 흔들리면 7가지 음을 내는 설정. 존재감은 풍경 수준.",
    359: "앱솔은 재해를 예지하고 경고하러 내려오는데 사람들이 재해 원인으로 오해해서 쫓아냄. 포켓몬 세계관 최대 억울이. 메가진화 디자인이 역대급 간지라 팬아트 폭발.",
    360: "마자는 마임맨 베이비인데 마임맨의 소름끼치는 비주얼 때문에 귀여운 마자도 덩달아 기피됨. 실검에 '마임맨 무서운 이유' 뜨는 게 다 이유가 있음.",
    361: "눈꼬마는 삿갓 쓴 눈 요정. 4세대에서 눈여아 분기진화 추가. 얼음 단타입이라 약점 투성이인데 귀여움으로 버팀.",
    362: "얼음귀신은 메가진화하면 턱이 쩍 벌어지는 공포 디자인. 냉동건조를 배워서 물타입도 잡을 수 있는데, 메가 디자인이 너무 무서워서 밈이 됨. 절대 검색하지 마.",
    363: "대굴레오는 동글동글 아기 물개. 눈밭에서 굴러다니는 모습이 귀여움의 극치인데, 최종진화 씨카이저가 너무 달라서 갭차이 심함.",
    364: "씨레오는 코끝에 뭘 올려서 균형 잡는 서커스 물개. 대굴레오의 귀여움과 씨카이저의 강함 사이 애매한 중간진화.",
    365: "씨카이저는 두꺼운지방 특성으로 불/얼음 반감하는 내구 탱커. 바다코끼리 모티브인데 대굴레오에서 어떻게 이렇게 되냐는 의문.",
    366: "진주몽은 심해의비늘/심해의이빨로 헌테일 or 분홍장이로 갈리는 분기진화. 아이템 구하는 것부터 고민인데 둘 다 약해서 어차피 상관없다는 슬픈 결론.",
    367: "헌테일은 심해의이빨로 진화하는 심해어인데 경쟁에서 거의 안 보임. 껍데기갑옷+배턴터치 세팅이 유일한 활용법이었는데 그마저도 마이너.",
    368: "분홍장이는 아름다운 외모인데 체액을 빨아먹는 포식자. 예쁜 얼굴로 유인하고 잡아먹는 설정이 팜파탈 컨셉. 근데 경쟁에선 안 쓰임.",
    369: "시라칸은 화석 복원이 아니라 야생에서 그냥 잡힘. 1억년을 살아남은 리얼 살아있는 화석. 실러캔스 모티브인데 실제로도 살아있는 화석이라 현실 반영.",
    370: "사랑동이는 하트 모양 물고기인데 종족값 합계 330이라 사랑할 여유도 없음. 밸런타인 이벤트 전용 느낌. 포켓몬계에서 가장 약한 축에 속함.",
    371: "아공이는 하늘을 날고 싶어서 절벽에서 뛰어내리는 무모한 드래곤 아기. 이 소원이 보만다로 진화하면서 이루어지는 포켓몬 도감 역대 최고 감동 스토리.",
    372: "쉘곤은 껍질 속에서 세포가 재구성 중인 번데기. 무거워서 굴러다니는데 이 안에서 보만다의 날개가 만들어지는 중. 인내의 시간.",
    373: "보만다는 아공이의 소원 성취 600족. 날개가 생긴 기쁨에 하늘을 날면서 불을 뿜는데, 메가진화하면 날개가 초승달 모양이 됨. 위협 특성에 용의춤까지 쓰는 OU 에이스.",
    374: "메탕은 잡기율 3으로 전설급 난이도. 게임에선 다이고한테 받는데, 야생에서 잡으려면 볼 수백 개 각오. 강철/에스퍼 600족의 시작이 이 동글이.",
    375: "메탕구는 메탕 2마리가 합체한 형태. 자력으로 떠다니며 강철 발톱이 무서움. 메타그로스까지 레벨업이 55라 키우는 게 인내력 테스트.",
    376: "메타그로스는 슈퍼컴 4개분 두뇌를 가진 600족. 챔피언 다이고의 에이스로 3세대 최고 간지. 메가진화 시 다리 8개에 특성 굳은발톱으로 접촉기 위력 30% 업. 경쟁배틀 탑티어.",
    377: "레지락은 점자 퍼즐로 잡아야 하는 바위 거인. 당시 초등학생들이 점자 해독하느라 도서관까지 간 추억. 인터넷 없던 시절 최고의 교육 콘텐츠(?). ÜN ÜN ÜN 밈의 원조.",
    378: "레지아이스는 남극 빙하로 만들어진 얼음 거인. 레지락 잡고 점자 풀었더니 또 점자. 3연속 점자 퍼즐에 멘탈 나간 사람 다수. 울음소리가 기계음이라 로봇설.",
    379: "레지스틸은 어떤 금속보다 단단한 강철 거인. 레지 시리즈 3연속 점자 퍼즐의 마지막. 공략 없으면 절대 못 잡는다고 해도 과언 아님. 클리어아이스바디로 내구가 미침.",
    380: "라티아스는 극장판에서 인간 여자로 변장한 빨간 비행기 드래곤. 엔딩에서 키스한 게 라티아스인지 여주인지 20년째 결론 안 남. 포켓몬 팬덤 최대 논쟁 중 하나.",
    381: "라티오스는 극장판에서 도시 지키려다 희생하는 장면이 포켓몬 극장판 눈물 TOP3. 라티아스랑 메가진화 세트인데, 라티오스가 더 화력 특화. 형이라 더 슬픔.",
    382: "가이오가는 바다를 만든 전설. 원시회귀 시 특공 180에 시원의파동으로 비팀 역대 최강 물특공. 비 내리면 물기술 1.5배인데 시원의파동 자체가 이미 150. 곱하면 악몽.",
    383: "그란돈은 대륙을 만든 전설. 원시회귀 시 끝의대지가 위력 150+맑은날 보정. 가이오가와의 날씨 전쟁이 ORAS의 핵심인데, 원시회귀하면 물 면역이라 가이오가를 씹음.",
    384: "레쿠쟈는 메가진화 종족값 780으로 너무 강해서 Uber에서도 추방, AG(Anything Goes) 티어가 새로 만들어짐. 기상잠금 특성으로 날씨를 무효화하는 하늘의 중재자.",
    385: "지라치는 천년에 7일만 깨어나서 소원을 들어주는 포켓몬. 극장판에서 아이와 7일간의 우정이 눈물샘 자극. 배의 세 번째 눈이 열리면 소원을 이루는데, 그 눈이 좀 무서움.",
    386: "테오키스는 우주 바이러스가 레이저에 변이된 포켓몬. 어택폼 특공 180은 유리대포의 정석이고, 스피드폼 스피드 180은 역대 최빠. 4개 폼이 각각 극단적이라 취향 타는 외계인.",
}



# 4~9세대 대표 포켓몬 이름 (한국어) — "아직 업데이트 안 됨" 안내용
_FUTURE_GEN_POKEMON = {
    # 4세대
    "모부기", "수풀부기", "토대부기", "불꽃숭이", "파이숭이", "초염몽", "팽도리", "팽태자", "엠페르트",
    "찌르꼬", "찌르버드", "찌르레기", "비달", "비버네일", "코링크", "럭시오", "렌트라",
    "두꺼비", "독개굴", "파치리스", "브이젤", "플로젤", "체리버", "체리꼬",
    "동풍박쥐", "동풍바구", "루카리오", "리올루", "히포포타스", "하마돈", "스콜피", "드래피온",
    "삐뚤기", "대포탑", "진화기", "드래", "갈레이드", "뚜벅쵸", "무장조",
    "로토무", "유크시", "에무리트", "아그놈", "디아루가", "펄기아", "기라티나",
    "크레세리아", "다크라이", "쉐이미", "아르세우스",
    # 5세대
    "주리비얀", "샤비", "염무왕", "뚜꾸리", "챠오꾸리", "대검귀",
    "수댕이", "쌍검귀", "대검귀", "조로아", "조로아크",
    "치라미", "치라치노", "리그레", "오베무", "비크로스", "볼트로스", "토네로스", "랜드로스",
    "레시라무", "제크로무", "큐레무", "켈디오", "메로엣타", "게노세크트",
    # 6세대
    "도치마론", "도치보구", "브리가론", "푸호꼬", "테르나", "마폭시",
    "개구마르", "개굴닌자", "부케", "파르빗", "파르토", "트리미앙",
    "제르네아스", "이벨타르", "지가르데", "디안시", "후파", "볼케니온",
    # 7세대
    "나몰빼미", "올빼미스", "모닥냥", "어흥염", "누리공", "누리레느",
    "이와룡", "큰입해적", "장크로다일", "루가루간", "토게데마루", "미미큐",
    "코스모그", "코스모움", "솔가레오", "루나아라", "네크로즈마", "마기아나", "마샤도",
    # 8세대
    "흥나숭", "고릴타", "염버니", "에이스번", "메소꿩", "인텔리존",
    "울머호크", "가라르마타도가스", "자시안", "자마젠타", "무한다이노", "칼리렉스",
    # 9세대
    "뉴비", "마스카나", "웰카모", "라우드보", "홀비", "파모", "파모트",
    "코라이돈", "미라이돈", "오거폰", "테라파고스",
}


async def _show_pokemon_detail(update: Update, user_id: int, name_query: str):
    """Show detailed info for a specific Pokemon."""
    # Check if it's a future-gen pokemon
    for future_name in _FUTURE_GEN_POKEMON:
        if name_query == future_name or (len(name_query) >= 2 and name_query in future_name):
            await update.message.reply_text(
                f"'{name_query}' 포켓몬은 현재 3세대(호연)까지만 업데이트되어 있습니다.\n"
                "4세대 이후 포켓몬은 추후 업데이트 예정입니다!"
            )
            return

    pokemon = await queries.search_pokemon_by_name(name_query)

    if not pokemon:
        await update.message.reply_text(f"'{name_query}' 포켓몬을 찾을 수 없습니다.")
        return

    pid = pokemon["id"]
    rarity_text = rarity_badge_label(pokemon["rarity"])

    # Check if user has it
    pokedex = await queries.get_user_pokedex(user_id)
    caught_ids = {p["pokemon_id"] for p in pokedex}
    owned = f"{icon_emoji('check')} 보유 중" if pid in caught_ids else "❌ 미보유"

    # Evolution chain
    evo_line = await _build_evo_chain(pokemon)

    # TMI
    tmi = POKEMON_TMI.get(pid, "")

    # Type display
    from models.pokemon_base_stats import POKEMON_BASE_STATS
    tb = type_badge(pid)
    pbs = POKEMON_BASE_STATS.get(pid)
    if pbs:
        type_names = "/".join(config.TYPE_NAME_KO.get(t, t) for t in pbs[-1])
    else:
        type_names = config.TYPE_NAME_KO.get(pokemon.get("pokemon_type", ""), "")

    # Evolution stage
    from utils.battle_calc import EVO_STAGE_MAP
    evo_stage = EVO_STAGE_MAP.get(pid, 3)
    _STAGE_LABELS = {1: "기본", 2: "1진화", 3: "최종"}
    # For single-form pokemon (no evo chain), show "단일"
    stage_label = _STAGE_LABELS[evo_stage]
    if evo_stage == 3 and not pokemon.get("evolves_from"):
        stage_label = "단일"

    lines = [
        f"No.{pid:03d} {pokemon['name_ko']} ({pokemon['name_en']})",
        f"등급: {rarity_text}",
        f"타입: {tb}{type_names}",
        f"포획률: {int(pokemon['catch_rate'] * 100)}% (하이퍼볼 {min(100, int(pokemon['catch_rate'] * config.HYPER_BALL_CATCH_MULTIPLIER * 100))}%)",
        f"상태: {owned}",
    ]

    if evo_line:
        # Bold the current pokemon in the chain
        evo_display = evo_line.replace(pokemon['name_ko'], f"<b>[{pokemon['name_ko']}]</b>")
        lines.append(f"\n📊 진화: {evo_display} ({stage_label})")

    if pokemon["evolution_method"] == "trade":
        lines.append("⚠️ 교환으로만 진화 가능!")

    if tmi:
        lines.append(f"\n💡 {tmi}")

    caption = "\n".join(lines)

    # Generate pokedex-style card image
    is_owned = pid in caught_ids
    card_buf = generate_pokedex_card(
        pokemon_id=pid,
        name_ko=pokemon["name_ko"],
        rarity=pokemon["rarity"],
        type_names=type_names,
        catch_rate=pokemon["catch_rate"],
        owned=is_owned,
    )
    await update.message.reply_photo(photo=card_buf, caption=caption, parse_mode="HTML")


async def _build_evo_chain(pokemon: dict) -> str:
    """Build evolution chain string like 파이리 → 리자드 → 리자몽"""
    chain = []

    # Go to the base form
    current = pokemon
    while current.get("evolves_from"):
        prev = await queries.get_pokemon(current["evolves_from"])
        if not prev:
            break
        current = prev

    # Walk forward
    while current:
        chain.append(current['name_ko'])
        if current.get("evolves_to"):
            nxt = await queries.get_pokemon(current["evolves_to"])
            current = nxt
        else:
            break

    return " → ".join(chain) if len(chain) > 1 else ""


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
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or "트레이너",
        update.effective_user.username,
    )

    unlocked = await queries.get_user_titles(user_id)
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
    unlocked = await queries.get_user_titles(user_id)
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
    display_name = update.effective_user.first_name or "트레이너"
    await queries.ensure_user(user_id, display_name, update.effective_user.username)

    # Check and unlock any new titles first
    from utils.title_checker import check_and_unlock_titles
    await check_and_unlock_titles(user_id)

    unlocked = await queries.get_user_titles(user_id)
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
    unlocked = await queries.get_user_titles(user_id)
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
    title_id = query.data.replace("title_", "")

    if title_id == "none":
        # 기존 칭호에 버프가 있었는지 확인
        user = await queries.get_user(user_id)
        old_title = user.get("title", "") if user else ""
        old_buff = config.get_title_buff_by_name(old_title) if old_title else None
        await queries.equip_title(user_id, "", "")
        warn = ""
        if old_buff:
            warn = "\n\n⚠️ 칭호 효과가 비활성화됩니다!"
        await query.edit_message_text(f"🚫 칭호를 해제했습니다.{warn}")
        return

    # Check if user has this title
    if not await queries.has_title(user_id, title_id):
        await query.edit_message_text("❌ 해금되지 않은 칭호입니다.")
        return

    t_info = config.UNLOCKABLE_TITLES.get(title_id)
    if not t_info:
        return

    name, emoji, desc, _, _ = t_info
    await queries.equip_title(user_id, name, emoji)
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


# ============================================================
# Status (상태창) — DM only
# ============================================================

async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '상태창' command (DM) — show user's full status overview."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    display_name = update.effective_user.first_name or "트레이너"
    await queries.ensure_user(user_id, display_name, update.effective_user.username)

    from database import battle_queries as bq
    from utils.battle_calc import calc_battle_stats, format_stats_line, format_power, calc_power, EVO_STAGE_MAP
    from models.pokemon_skills import POKEMON_SKILLS
    from models.pokemon_base_stats import POKEMON_BASE_STATS

    user = await queries.get_user(user_id)
    pokemon_list = await queries.get_user_pokemon_list(user_id)
    partner = await bq.get_partner(user_id)
    team = await bq.get_battle_team(user_id)
    battle_stats = await bq.get_battle_stats(user_id)
    master_balls = user.get("master_balls", 0) if user else 0
    bp = battle_stats.get("battle_points", 0)

    # 칭호
    title = user.get("title", "") if user else ""
    title_emoji_raw = user.get("title_emoji", "") if user else ""
    if title and title_emoji_raw:
        badge = resolve_title_badge(title_emoji_raw, title)
        title_text = f"「{badge} {title}」"
    else:
        title_text = "없음"

    lines = [f"{icon_emoji('bookmark')} {display_name}님의 상태창\n"]

    # 기본 정보
    lines.append(f"🏷️ 칭호: {title_text}")
    lines.append(f"{ball_emoji('masterball')} 마스터볼: {master_balls}개")
    lines.append(f"{icon_emoji('coin')} BP: {bp}")
    lines.append(f"{icon_emoji('container')} 보유 포켓몬: {len(pokemon_list)}마리")

    # 도감 수
    unique_ids = {p["pokemon_id"] for p in pokemon_list}
    shiny_count = sum(1 for p in pokemon_list if p.get("is_shiny"))
    lines.append(f"{icon_emoji('pokedex')} 도감: {len(unique_ids)}/386종")
    if shiny_count > 0:
        lines.append(f"{shiny_emoji()} 이로치: {shiny_count}마리")

    # 배틀 전적
    wins = battle_stats.get("battle_wins", 0)
    losses = battle_stats.get("battle_losses", 0)
    total = wins + losses
    win_rate = f"{wins / total * 100:.0f}%" if total > 0 else "-"
    best = battle_stats.get("best_streak", 0)
    lines.append(f"\n{icon_emoji('battle')} 배틀 전적: {wins}승 {losses}패 (승률 {win_rate})")
    if best > 0:
        lines.append(f"🔥 최고 연승: {best}연승")

    # 파트너
    lines.append("")
    if partner:
        evo = EVO_STAGE_MAP.get(partner["pokemon_id"], 3)
        stats = calc_battle_stats(
            partner["rarity"], partner["stat_type"], partner["friendship"], evo_stage=evo,
            iv_hp=partner.get("iv_hp"), iv_atk=partner.get("iv_atk"),
            iv_def=partner.get("iv_def"), iv_spa=partner.get("iv_spa"),
            iv_spdef=partner.get("iv_spdef"), iv_spd=partner.get("iv_spd"),
        )
        base = calc_battle_stats(partner["rarity"], partner["stat_type"], partner["friendship"], evo_stage=evo)
        tb = type_badge(partner["pokemon_id"], partner["pokemon_type"])
        pbs = POKEMON_BASE_STATS.get(partner["pokemon_id"])
        if pbs:
            type_name = "/".join(config.TYPE_NAME_KO.get(t, t) for t in pbs[-1])
        else:
            type_name = config.TYPE_NAME_KO.get(partner["pokemon_type"], "")
        from models.pokemon_skills import get_skill_display
        _skill_disp = get_skill_display(partner["pokemon_id"])
        lines.append(f"{icon_emoji('pokemon-love')} 파트너: {tb} {partner['name_ko']}  {type_name}  {icon_emoji('bolt')}{format_power(stats, base)}")
        lines.append(f"   {icon_emoji('favorite')} 친밀도: {hearts_display(partner['friendship'])}")
        lines.append(f"   {icon_emoji('stationery')} {format_stats_line(stats, base)}")
        lines.append(f"   {icon_emoji('skill')} 기술: {_skill_disp}")
    else:
        lines.append(f"{icon_emoji('pokemon-love')} 파트너: 미지정 ('파트너' 명령어로 설정)")

    # 팀
    active_num = await bq.get_active_team_number(user_id)
    team2 = await bq.get_battle_team(user_id, 2)
    lines.append("")
    if team:
        lines.append(f"{icon_emoji('battle')} 배틀팀 {active_num} ({len(team)}/6)")
        total_power = 0
        total_base_power = 0
        for i, t in enumerate(team, 1):
            evo = EVO_STAGE_MAP.get(t["pokemon_id"], 3)
            stats = calc_battle_stats(
                t["rarity"], t["stat_type"], t["friendship"], evo_stage=evo,
                iv_hp=t.get("iv_hp"), iv_atk=t.get("iv_atk"),
                iv_def=t.get("iv_def"), iv_spa=t.get("iv_spa"),
                iv_spdef=t.get("iv_spdef"), iv_spd=t.get("iv_spd"),
            )
            tbase = calc_battle_stats(t["rarity"], t["stat_type"], t["friendship"], evo_stage=evo)
            total_power += calc_power(stats)
            total_base_power += calc_power(tbase)
            from models.pokemon_skills import get_skill_display
            _skill_disp = get_skill_display(t["pokemon_id"])
            ttb = type_badge(t["pokemon_id"], t.get("pokemon_type"))
            lines.append(f"  {i}. {ttb} {t['name_ko']}  {icon_emoji('skill')}{_skill_disp}  {icon_emoji('bolt')}{format_power(stats, tbase)}")
        iv_diff = total_power - total_base_power
        total_tag = f"{total_power}(+{iv_diff})" if iv_diff > 0 else str(total_power)
        lines.append(f"  {icon_emoji('bolt')} 팀 전투력: {total_tag}")
        if team2:
            lines.append(f"  (팀2 등록됨: {len(team2)}마리)")
    else:
        lines.append(f"{icon_emoji('battle')} 배틀팀: 미등록 ('팀등록' 명령어로 설정)")

    # 아이템
    arcade_tickets = await queries.get_arcade_tickets(user_id)
    hyper_balls = await queries.get_hyper_balls(user_id)
    if arcade_tickets > 0 or hyper_balls > 0:
        lines.append("")
    if arcade_tickets > 0:
        lines.append(f"{icon_emoji('game')} 아케이드 티켓: {arcade_tickets}개")
    if hyper_balls > 0:
        lines.append(f"{ball_emoji('hyperball')} 하이퍼볼: {hyper_balls}개")

    # DM 메뉴 키보드
    menu_keyboard = ReplyKeyboardMarkup(
        [
            ["📋 상태창", "📦 내포켓몬"],
            ["🛒 거래소", "🏪 상점"],
            ["💎 구독", "🤝 파트너"],
            ["📖 도감", "🏷️ 칭호"],
            ["❓ 도움말"],
        ],
        resize_keyboard=True,
        input_field_placeholder="명령어를 선택하세요",
    )

    await update.message.reply_text("\n".join(lines), reply_markup=menu_keyboard, parse_mode="HTML")


# ============================================================
# IV Appraisal (감정)
# ============================================================

async def appraisal_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '감정 [이름/번호]' command — show Pokemon IV stats."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or "트레이너",
        update.effective_user.username,
    )

    text = update.message.text or ""
    index = parse_number(text)
    name_arg = parse_name_arg(text)

    pokemon = None
    if index is not None:
        pokemon = await queries.get_user_pokemon_by_index(user_id, index)
    elif name_arg:
        pokemon = await queries.get_user_pokemon_by_name(user_id, name_arg)
    else:
        await update.message.reply_text("사용법: 감정 [이름 또는 번호]\n예: 감정 피카츄, 감정 3")
        return

    if not pokemon:
        query = index if index is not None else name_arg
        await update.message.reply_text(
            f"'{query}' 포켓몬을 찾을 수 없습니다.\n내포켓몬 으로 목록을 확인하세요."
        )
        return

    # Read IVs
    ivs = {
        "HP": pokemon.get("iv_hp"),
        "ATK": pokemon.get("iv_atk"),
        "DEF": pokemon.get("iv_def"),
        "SPA": pokemon.get("iv_spa"),
        "SPDEF": pokemon.get("iv_spdef"),
        "SPD": pokemon.get("iv_spd"),
    }

    total = iv_total(
        ivs["HP"], ivs["ATK"], ivs["DEF"],
        ivs["SPA"], ivs["SPDEF"], ivs["SPD"],
    )
    grade, _ = config.get_iv_grade(total)
    pct = round(total / 186 * 100, 1)

    # Build display
    shiny = shiny_emoji() if pokemon.get("is_shiny") else ""
    rb = rarity_badge(pokemon.get("rarity", "common"))
    name = pokemon["name_ko"]

    stat_labels = {
        "HP": "HP   ", "ATK": "공격 ", "DEF": "방어 ",
        "SPA": "특공 ", "SPDEF": "특방 ", "SPD": "스피드",
    }

    lines = [f"📋 {shiny}{rb} {name} 감정 결과\n"]
    max_iv = config.IV_MAX  # 31

    for key in ("HP", "ATK", "DEF", "SPA", "SPDEF", "SPD"):
        v = ivs[key] if ivs[key] is not None else 15
        label = stat_labels[key]
        filled = round(v / max_iv * 6)
        bar = "█" * filled + "░" * (6 - filled)
        # Highlight perfect (31) or near-perfect (28+)
        if v >= 28:
            mark = " ★"
        elif v <= 5:
            mark = " ✗"
        else:
            mark = ""
        lines.append(f"{label} {bar} {v}/{max_iv}{mark}")

    lines.append(f"\n총합: {total}/186 ({pct}%)")
    lines.append(f"등급: {grade}")

    # Grade flavor text
    flavor = {
        "S": "이 포켓몬은 최상급 개체입니다!",
        "A": "매우 뛰어난 개체입니다.",
        "B": "괜찮은 개체입니다.",
        "C": "평범한 개체입니다.",
        "D": "개체값이 낮습니다...",
    }
    lines.append(flavor.get(grade, ""))

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ============================================================
# Type Chart (상성표)
# ============================================================

async def type_chart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '상성 [타입]' command — show type effectiveness."""
    if not update.effective_user or not update.message:
        return

    text = update.message.text or ""
    name_arg = parse_name_arg(text)

    if name_arg:
        # Specific type detail
        # Find type by Korean name or English key
        target_type = None
        for eng, ko in config.TYPE_NAME_KO.items():
            if name_arg == ko or name_arg.lower() == eng:
                target_type = eng
                break
        if not target_type:
            type_list = " ".join(f"{_type_emoji(t)}{config.TYPE_NAME_KO[t]}" for t in config.TYPE_ADVANTAGE)
            await update.message.reply_text(f"'{name_arg}' 타입을 찾을 수 없습니다.\n\n사용 가능: {type_list}", parse_mode="HTML")
            return

        te = _type_emoji(target_type)
        ko = config.TYPE_NAME_KO.get(target_type, target_type)

        # Offense: what this type is strong against
        strong = config.TYPE_ADVANTAGE.get(target_type, [])
        # Offense: what this type is immune to (hits for 0.3x)
        immune_vs = config.TYPE_IMMUNITY.get(target_type, [])

        # Defense: what is strong against this type
        weak_to = []
        resist_from = []
        immune_from = []
        for atk_type, adv_list in config.TYPE_ADVANTAGE.items():
            if target_type in adv_list:
                weak_to.append(atk_type)
        for atk_type, res_list in config.TYPE_RESISTANCE.items():
            if target_type in res_list:
                resist_from.append(atk_type)
        for atk_type, imm_list in config.TYPE_IMMUNITY.items():
            if target_type in imm_list:
                immune_from.append(atk_type)

        def fmt(types):
            if not types:
                return "없음"
            return " ".join(f"{_type_emoji(t)}{config.TYPE_NAME_KO.get(t, t)}" for t in types)

        lines = [
            f"{te} {ko} 타입 상성\n",
            f"⚔️ 공격 시 효과적 (2x):",
            f"  {fmt(strong)}",
        ]
        if immune_vs:
            lines.append(f"\n🚫 공격 시 면역 (0x):")
            lines.append(f"  {fmt(immune_vs)}")
        lines.append(f"\n🛡️ 방어 시 약점 (2x 피해):")
        lines.append(f"  {fmt(weak_to)}")
        if resist_from:
            lines.append(f"\n🛡️ 방어 시 반감 (0.5x 피해):")
            lines.append(f"  {fmt(resist_from)}")
        if immune_from:
            lines.append(f"\n🛡️ 방어 시 면역 (0x 피해):")
            lines.append(f"  {fmt(immune_from)}")

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    else:
        # Full chart summary
        lines = ["⚔️ 타입 상성표\n"]
        for atk_type, adv_list in config.TYPE_ADVANTAGE.items():
            if not adv_list:
                continue
            te = _type_emoji(atk_type)
            ko = config.TYPE_NAME_KO.get(atk_type, atk_type)
            targets = " ".join(f"{_type_emoji(t)}{config.TYPE_NAME_KO.get(t, t)}" for t in adv_list)
            lines.append(f"{te}{ko} → {targets}")
        lines.append(f"\n💡 상성 [타입] 으로 상세 보기\n예: 상성 불꽃")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
