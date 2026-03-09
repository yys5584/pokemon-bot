"""DM handler for Pokemon fusion (합성)."""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from services.fusion_service import get_fusable_species, get_fusable_copies, execute_fusion
from utils.helpers import rarity_badge
import config

logger = logging.getLogger(__name__)

SPECIES_PAGE_SIZE = 8

RARITY_FILTERS = [
    ("all", "전체"),
    ("common", "일반"),
    ("rare", "희귀"),
    ("epic", "에픽"),
    ("legendary", "전설"),
    ("ultra_legendary", "초전설"),
]


def _get_state(context) -> dict:
    key = "fusion_state"
    if key not in context.user_data:
        context.user_data[key] = {
            "page": 0,
            "pokemon_id": None,
            "sel_a": None,
            "sel_b": None,
            "rarity_filter": "all",
        }
    # Migration for old state without rarity_filter
    state = context.user_data[key]
    if "rarity_filter" not in state:
        state["rarity_filter"] = "all"
    return state


def _iv_total(p: dict) -> int:
    return sum(p.get(f"iv_{s}", 0) or 0 for s in ("hp", "atk", "def", "spa", "spdef", "spd"))


def _filter_species(species: list[dict], rarity_filter: str) -> list[dict]:
    if rarity_filter == "all":
        return species
    return [s for s in species if s["rarity"] == rarity_filter]


def _build_species_panel(user_id: int, species: list[dict], page: int, rarity_filter: str) -> tuple[str, InlineKeyboardMarkup]:
    """Build species selection panel with rarity filter and pagination."""
    filtered = _filter_species(species, rarity_filter)
    total = len(filtered)
    max_page = max(0, (total - 1) // SPECIES_PAGE_SIZE)
    page = min(page, max_page)
    start = page * SPECIES_PAGE_SIZE
    page_items = filtered[start:start + SPECIES_PAGE_SIZE]

    text = "🔀 <b>포켓몬 합성</b>\n\n"
    text += "같은 종류의 포켓몬 2마리를 합성하면\n새로운 개체값의 포켓몬 1마리가 탄생합니다!\n\n"
    text += "⚠️ 팀/파트너/거래소/즐겨찾기 포켓몬은 제외됩니다.\n\n"

    # Current filter label
    filter_label = next((label for key, label in RARITY_FILTERS if key == rarity_filter), "전체")
    text += f"필터: <b>{filter_label}</b> | 합성 가능: <b>{total}종</b>\n"

    if total == 0:
        text += "\n해당 등급에 합성 가능한 포켓몬이 없습니다."

    rows = []

    # Rarity filter buttons
    filter_row = []
    for key, label in RARITY_FILTERS:
        prefix = "▪" if key == rarity_filter else ""
        filter_row.append(InlineKeyboardButton(f"{prefix}{label}", callback_data=f"fus_rf_{user_id}_{key}"))
    # Split into 2 rows of 3
    rows.append(filter_row[:3])
    rows.append(filter_row[3:])

    for s in page_items:
        btn_emoji = config.RARITY_EMOJI.get(s["rarity"], "")
        label = f"{btn_emoji} {s['name_ko']} ({s['count']}마리)"
        rows.append([InlineKeyboardButton(label, callback_data=f"fus_sp_{user_id}_{s['pokemon_id']}")])

    # Pagination
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀ 이전", callback_data=f"fus_pg_{user_id}_{page - 1}"))
    if page < max_page:
        nav_row.append(InlineKeyboardButton("다음 ▶", callback_data=f"fus_pg_{user_id}_{page + 1}"))
    if nav_row:
        rows.append(nav_row)

    rows.append([InlineKeyboardButton("❌ 취소", callback_data=f"fus_cancel_{user_id}")])

    return text, InlineKeyboardMarkup(rows)


def _build_copies_panel(user_id: int, copies: list[dict], sel_a: int | None, sel_b: int | None) -> tuple[str, InlineKeyboardMarkup]:
    """Build individual copy selection panel."""
    if not copies:
        return "합성 가능한 개체가 없습니다.", InlineKeyboardMarkup([])

    name = copies[0].get("name_ko", "???")
    emoji = rarity_badge(copies[0].get("rarity", ""))
    text = f"🔀 <b>{emoji} {name} 합성</b>\n\n"
    text += "합성할 2마리를 선택하세요:\n\n"

    rows = []
    for p in copies:
        total = _iv_total(p)
        grade, _ = config.get_iv_grade(total)
        shiny_mark = "⭐" if p.get("is_shiny") else ""
        selected = ""
        if p["id"] == sel_a:
            selected = "① "
        elif p["id"] == sel_b:
            selected = "② "
        label = f"{selected}{shiny_mark}[{grade}] IV:{total} (#{p['id']})"
        rows.append([InlineKeyboardButton(label, callback_data=f"fus_sel_{user_id}_{p['id']}")])

    # Action buttons
    action_row = []
    if sel_a and sel_b:
        action_row.append(InlineKeyboardButton("✅ 합성하기", callback_data=f"fus_confirm_{user_id}"))
    action_row.append(InlineKeyboardButton("◀ 돌아가기", callback_data=f"fus_back_{user_id}"))
    rows.append(action_row)
    rows.append([InlineKeyboardButton("❌ 취소", callback_data=f"fus_cancel_{user_id}")])

    # Show selected info
    if sel_a:
        pa = next((p for p in copies if p["id"] == sel_a), None)
        if pa:
            text += f"① {_pokemon_summary(pa)}\n"
    if sel_b:
        pb = next((p for p in copies if p["id"] == sel_b), None)
        if pb:
            text += f"② {_pokemon_summary(pb)}\n"

    if sel_a and sel_b:
        selected = [p for p in copies if p["id"] in (sel_a, sel_b)]
        shiny_count = sum(1 for p in selected if p.get("is_shiny"))
        any_shiny = shiny_count > 0
        both_shiny = shiny_count == 2
        if both_shiny:
            text += "\n→ 결과: ⭐이로치 + 최소 A등급(IV 120+) 보장!\n"
        elif any_shiny:
            text += "\n→ 결과: ⭐이로치 유지 + 랜덤 IV\n"
        else:
            text += "\n→ 결과: 랜덤 IV\n"
        text += "\n⚠️ <b>합성한 포켓몬은 되돌릴 수 없습니다!</b>"

    return text, InlineKeyboardMarkup(rows)


def _pokemon_summary(p: dict) -> str:
    total = _iv_total(p)
    grade, _ = config.get_iv_grade(total)
    shiny = "⭐" if p.get("is_shiny") else ""
    return f"{shiny}[{grade}] IV:{total} (HP:{p.get('iv_hp',0)} ATK:{p.get('iv_atk',0)} DEF:{p.get('iv_def',0)} SpA:{p.get('iv_spa',0)} SpD:{p.get('iv_spdef',0)} SPD:{p.get('iv_spd',0)})"


async def fusion_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '합성' command in DM."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id

    # Reset state
    context.user_data["fusion_state"] = {
        "page": 0,
        "pokemon_id": None,
        "sel_a": None,
        "sel_b": None,
        "rarity_filter": "all",
    }

    species = await get_fusable_species(user_id)
    if not species:
        await update.message.reply_text(
            "🔀 합성 가능한 포켓몬이 없습니다.\n\n"
            "같은 종류의 포켓몬을 2마리 이상 보유해야 합니다.\n"
            "⚠️ 팀/파트너/거래소/즐겨찾기 포켓몬은 제외됩니다.",
            parse_mode="HTML",
        )
        return

    text, kb = _build_species_panel(user_id, species, 0, "all")
    await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")


async def fusion_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all fus_ callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    parts = data.split("_")
    action = parts[1]

    try:
        user_id = int(parts[2])
    except (IndexError, ValueError):
        await query.answer()
        return

    if query.from_user.id != user_id:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    state = _get_state(context)

    if action == "rf":
        # Rarity filter changed
        try:
            rarity = parts[3]
            # Handle ultra_legendary (has extra underscore)
            if len(parts) > 4:
                rarity = "_".join(parts[3:])
        except IndexError:
            await query.answer()
            return

        state["rarity_filter"] = rarity
        state["page"] = 0
        species = await get_fusable_species(user_id)
        await query.answer()
        text, kb = _build_species_panel(user_id, species, 0, rarity)
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    elif action == "sp":
        # Species selected
        try:
            pokemon_id = int(parts[3])
        except (IndexError, ValueError):
            await query.answer()
            return

        state["pokemon_id"] = pokemon_id
        state["sel_a"] = None
        state["sel_b"] = None

        copies = await get_fusable_copies(user_id, pokemon_id)
        if len(copies) < 2:
            await query.answer("합성 가능한 개체가 부족합니다!", show_alert=True)
            return

        await query.answer()
        text, kb = _build_copies_panel(user_id, copies, None, None)
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    elif action == "pg":
        # Page navigation
        try:
            page = int(parts[3])
        except (IndexError, ValueError):
            await query.answer()
            return

        state["page"] = page
        species = await get_fusable_species(user_id)
        await query.answer()
        text, kb = _build_species_panel(user_id, species, page, state.get("rarity_filter", "all"))
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    elif action == "sel":
        # Individual copy selected
        try:
            instance_id = int(parts[3])
        except (IndexError, ValueError):
            await query.answer()
            return

        # Toggle selection
        if state["sel_a"] == instance_id:
            state["sel_a"] = None
        elif state["sel_b"] == instance_id:
            state["sel_b"] = None
        elif state["sel_a"] is None:
            state["sel_a"] = instance_id
        elif state["sel_b"] is None:
            state["sel_b"] = instance_id
        else:
            # Both slots filled, replace second
            state["sel_b"] = instance_id

        copies = await get_fusable_copies(user_id, state["pokemon_id"])
        await query.answer()
        text, kb = _build_copies_panel(user_id, copies, state["sel_a"], state["sel_b"])
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    elif action == "confirm":
        if not state["sel_a"] or not state["sel_b"]:
            await query.answer("2마리를 선택해주세요!", show_alert=True)
            return

        await query.answer("🔀 합성 중...")
        success, msg, result = await execute_fusion(user_id, state["sel_a"], state["sel_b"])

        if not success:
            await query.answer(msg, show_alert=True)
            return

        # Build result message
        text = "🔀 <b>합성 완료!</b>\n\n"
        if result:
            total = _iv_total(result)
            grade, _ = config.get_iv_grade(total)
            emoji = rarity_badge(result.get("rarity", ""))
            name = result.get("name_ko", "???")
            shiny = " ⭐이로치" if result.get("is_shiny") else ""

            text += f"{emoji} <b>{name}</b>{shiny}\n"
            text += f"등급: [{grade}] (IV합계: {total})\n\n"
            text += f"HP: {result.get('iv_hp', 0)}  ATK: {result.get('iv_atk', 0)}  DEF: {result.get('iv_def', 0)}\n"
            text += f"SpA: {result.get('iv_spa', 0)}  SpD: {result.get('iv_spdef', 0)}  SPD: {result.get('iv_spd', 0)}\n"

        # Clear state
        context.user_data.pop("fusion_state", None)

        try:
            await query.edit_message_text(text, parse_mode="HTML")
        except Exception:
            pass

    elif action == "back":
        # Return to species list
        state["pokemon_id"] = None
        state["sel_a"] = None
        state["sel_b"] = None
        species = await get_fusable_species(user_id)
        await query.answer()
        if not species:
            try:
                await query.edit_message_text("합성 가능한 포켓몬이 없습니다.", parse_mode="HTML")
            except Exception:
                pass
            return
        text, kb = _build_species_panel(user_id, species, state.get("page", 0), state.get("rarity_filter", "all"))
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    elif action == "cancel":
        context.user_data.pop("fusion_state", None)
        try:
            await query.edit_message_text("❌ 합성이 취소되었습니다.", parse_mode="HTML")
        except Exception:
            pass
        await query.answer()
