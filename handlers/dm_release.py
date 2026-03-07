"""DM handler for bulk Pokemon release (방생)."""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import queries
import config

logger = logging.getLogger(__name__)

RARITY_ORDER = ["common", "rare", "epic", "legendary", "ultra_legendary"]
IV_GRADES = ["D", "C", "B", "A", "S"]


def _get_filter(context) -> dict:
    """Get or init release filter state."""
    key = "release_filter"
    if key not in context.user_data:
        context.user_data[key] = {
            "rarities": set(),     # selected rarities (empty = none selected)
            "iv_grades": set(),    # selected IV grades
            "keep_one": True,      # keep 1 per species for pokedex
        }
    return context.user_data[key]


def _iv_total(p: dict) -> int:
    """Calculate total IV from a pokemon dict."""
    return sum(p.get(f"iv_{s}", 0) or 0 for s in ("hp", "atk", "def", "spa", "spdef", "spd"))


def _build_panel(user_id: int, filt: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Build the filter selection panel."""
    text = "🔄 <b>포켓몬 방생</b>\n\n필터를 선택한 후 [미리보기]를 눌러주세요.\n"

    # Show current selection summary
    sel_r = [config.RARITY_LABEL.get(r, r) for r in RARITY_ORDER if r in filt["rarities"]]
    sel_iv = sorted(filt["iv_grades"], key=lambda g: IV_GRADES.index(g))
    if sel_r:
        text += f"\n선택된 희귀도: {', '.join(sel_r)}"
    if sel_iv:
        text += f"\n선택된 IV등급: {', '.join(sel_iv)}"
    if not sel_r and not sel_iv:
        text += "\n<i>최소 1개의 필터를 선택하세요</i>"

    # Rarity buttons
    rarity_row = []
    for r in RARITY_ORDER:
        label = config.RARITY_LABEL[r]
        if r in filt["rarities"]:
            label = f"✓ {label}"
        rarity_row.append(InlineKeyboardButton(label, callback_data=f"rel_r_{user_id}_{r}"))

    # IV grade buttons
    iv_row = []
    for g in IV_GRADES:
        label = g
        if g in filt["iv_grades"]:
            label = f"✓ {g}"
        iv_row.append(InlineKeyboardButton(label, callback_data=f"rel_iv_{user_id}_{g}"))

    # Keep-one toggle
    keep_label = "✓ 도감용 1마리 남기기" if filt["keep_one"] else "✗ 도감용 1마리 남기기"
    keep_row = [InlineKeyboardButton(keep_label, callback_data=f"rel_keep_{user_id}")]

    # Action buttons
    action_row = [
        InlineKeyboardButton("🔍 미리보기", callback_data=f"rel_preview_{user_id}"),
        InlineKeyboardButton("❌ 취소", callback_data=f"rel_cancel_{user_id}"),
    ]

    kb = InlineKeyboardMarkup([
        rarity_row[:3],    # common, rare, epic
        rarity_row[3:],    # legendary, ultra_legendary
        iv_row,            # D, C, B, A, S
        keep_row,
        action_row,
    ])
    return text, kb


async def _get_candidates(user_id: int, filt: dict) -> list[dict]:
    """Get Pokemon eligible for release based on filters."""
    all_pokemon = await queries.get_user_pokemon_list(user_id)
    protected = await queries.get_protected_pokemon_ids(user_id)

    candidates = []
    for p in all_pokemon:
        # Skip protected
        if p["id"] in protected:
            continue
        # Skip favorites
        if p.get("is_favorite"):
            continue
        # Skip shiny
        if p.get("is_shiny"):
            continue
        # Skip team members
        if p.get("slot") is not None:
            continue

        # Apply rarity filter (if any selected)
        if filt["rarities"] and p.get("rarity") not in filt["rarities"]:
            continue

        # Apply IV grade filter (if any selected)
        if filt["iv_grades"]:
            total = _iv_total(p)
            grade, _ = config.get_iv_grade(total)
            if grade not in filt["iv_grades"]:
                continue

        candidates.append(p)

    # Keep-one-per-species logic
    if filt["keep_one"] and candidates:
        # Group by pokemon_id, keep the best IV one
        species_best: dict[int, dict] = {}
        for p in all_pokemon:
            pid = p["pokemon_id"]
            if p.get("is_active", 1) and pid not in species_best:
                species_best[pid] = p
            elif p.get("is_active", 1) and pid in species_best:
                if _iv_total(p) > _iv_total(species_best[pid]):
                    species_best[pid] = p

        keep_ids = {p["id"] for p in species_best.values()}
        # Also count how many active per species
        species_count: dict[int, int] = {}
        for p in all_pokemon:
            pid = p["pokemon_id"]
            species_count[pid] = species_count.get(pid, 0) + 1

        # Remove candidates that are the only/best one of their species
        final = []
        for p in candidates:
            pid = p["pokemon_id"]
            if species_count.get(pid, 0) <= 1:
                # Only copy of this species, keep it
                continue
            if p["id"] in keep_ids:
                # This is the best IV of its species, keep it
                continue
            final.append(p)
        candidates = final

    return candidates


async def release_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '방생' command in DM."""
    user_id = update.effective_user.id

    # Reset filter state
    context.user_data["release_filter"] = {
        "rarities": set(),
        "iv_grades": set(),
        "keep_one": True,
    }
    filt = _get_filter(context)
    text, kb = _build_panel(user_id, filt)
    await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")


async def release_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all rel_ callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    parts = data.split("_")
    # rel_r_{uid}_{rarity}, rel_iv_{uid}_{grade}, rel_keep_{uid},
    # rel_preview_{uid}, rel_confirm_{uid}, rel_cancel_{uid}

    action = parts[1]

    try:
        user_id = int(parts[2])
    except (IndexError, ValueError):
        await query.answer()
        return

    if query.from_user.id != user_id:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    filt = _get_filter(context)

    if action == "r":
        # Toggle rarity
        rarity = parts[3] if len(parts) > 3 else ""
        if rarity in RARITY_ORDER:
            if rarity in filt["rarities"]:
                filt["rarities"].discard(rarity)
            else:
                filt["rarities"].add(rarity)
        await query.answer()
        text, kb = _build_panel(user_id, filt)
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    elif action == "iv":
        # Toggle IV grade
        grade = parts[3] if len(parts) > 3 else ""
        if grade in IV_GRADES:
            if grade in filt["iv_grades"]:
                filt["iv_grades"].discard(grade)
            else:
                filt["iv_grades"].add(grade)
        await query.answer()
        text, kb = _build_panel(user_id, filt)
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    elif action == "keep":
        filt["keep_one"] = not filt["keep_one"]
        await query.answer()
        text, kb = _build_panel(user_id, filt)
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    elif action == "preview":
        # Check at least one filter selected
        if not filt["rarities"] and not filt["iv_grades"]:
            await query.answer("최소 1개의 필터를 선택해주세요!", show_alert=True)
            return

        await query.answer("🔍 계산 중...")
        candidates = await _get_candidates(user_id, filt)

        if not candidates:
            await query.answer("조건에 맞는 포켓몬이 없습니다!", show_alert=True)
            return

        count = len(candidates)

        # Build filter summary
        parts_text = []
        if filt["rarities"]:
            parts_text.append(", ".join(config.RARITY_LABEL.get(r, r) for r in RARITY_ORDER if r in filt["rarities"]))
        if filt["iv_grades"]:
            parts_text.append(", ".join(sorted(filt["iv_grades"], key=lambda g: IV_GRADES.index(g))) + "등급")
        filter_summary = " / ".join(parts_text)
        if filt["keep_one"]:
            filter_summary += " / 도감용 남기기 ✓"

        text = f"🔄 <b>방생 미리보기</b>\n\n"
        text += f"필터: {filter_summary}\n"
        text += f"방생 대상: <b>{count}마리</b>\n"
        text += f"보상: 하이퍼볼 <b>{count}개</b>\n\n"

        # Sample list (max 10)
        sample = candidates[:10]
        for p in sample:
            total = _iv_total(p)
            grade, _ = config.get_iv_grade(total)
            emoji = config.RARITY_EMOJI.get(p.get("rarity", ""), "")
            name = p.get("name_ko", "???")
            text += f"• {emoji} {name} [{grade}]\n"
        if count > 10:
            text += f"  ... 외 {count - 10}마리\n"

        text += f"\n⚠️ <b>방생한 포켓몬은 되돌릴 수 없습니다!</b>"

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ 방생 실행", callback_data=f"rel_confirm_{user_id}"),
                InlineKeyboardButton("◀ 돌아가기", callback_data=f"rel_back_{user_id}"),
            ],
            [InlineKeyboardButton("❌ 취소", callback_data=f"rel_cancel_{user_id}")],
        ])
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    elif action == "confirm":
        # Re-fetch candidates (fresh data)
        if not filt["rarities"] and not filt["iv_grades"]:
            await query.answer("필터가 초기화되었습니다. 다시 시도해주세요.", show_alert=True)
            return

        candidates = await _get_candidates(user_id, filt)
        if not candidates:
            await query.answer("방생할 포켓몬이 없습니다!", show_alert=True)
            return

        count = len(candidates)
        instance_ids = [p["id"] for p in candidates]

        # Execute release
        released = await queries.bulk_deactivate_pokemon(instance_ids)
        if released > 0:
            await queries.add_hyper_ball(user_id, released)

        # Clear filter state
        context.user_data.pop("release_filter", None)

        text = f"✅ <b>{released}마리 방생 완료!</b>\n하이퍼볼 {released}개를 획득했습니다!"
        try:
            await query.edit_message_text(text, parse_mode="HTML")
        except Exception:
            pass
        await query.answer()

    elif action == "back":
        # Return to filter panel
        await query.answer()
        text, kb = _build_panel(user_id, filt)
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    elif action == "cancel":
        context.user_data.pop("release_filter", None)
        try:
            await query.edit_message_text("❌ 방생이 취소되었습니다.", parse_mode="HTML")
        except Exception:
            pass
        await query.answer()
