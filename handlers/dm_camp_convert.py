"""Camp DM handlers — 이로치전환, 분해."""

import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import config
from database import camp_queries as cq
from database import queries
from services import camp_service as cs
from utils.helpers import rarity_badge, shiny_emoji, icon_emoji
from utils.card_generator import generate_card

from handlers.dm_camp_shared import (
    _is_duplicate_callback, _pokemon_name,
    CONVERT_PAGE_SIZE, DECOMPOSE_PAGE_SIZE,
)


_RARITY_FILTER_MAP = {
    "all": ("전체", None),
    "ul": ("초전설", "ultra_legendary"),
    "leg": ("전설", "legendary"),
    "ep": ("에픽", "epic"),
    "ra": ("레어", "rare"),
    "co": ("커먼", "common"),
}


def _build_convert_eligible(pokemon_list: list, frags: dict, crystals: dict,
                            pending_ids: set | None = None) -> list:
    """이로치 전환 가능 포켓몬 목록 빌드."""
    pending_ids = pending_ids or set()
    eligible = []
    for p in pokemon_list:
        if p.get("is_shiny"):
            continue
        if p["id"] in pending_ids:
            continue
        matching_fields = cs.get_matching_fields(p["pokemon_id"])
        if not matching_fields:
            continue
        rarity = p.get("rarity", "common")
        frag_cost = config.CAMP_SHINY_COST.get(rarity, 12)
        crystal_cost = config.CAMP_CRYSTAL_COST.get(rarity, 0)
        rainbow_cost = config.CAMP_RAINBOW_COST.get(rarity, 0)
        can_afford_frags = any(frags.get(f, 0) >= frag_cost for f in matching_fields)
        can_afford_crystal = crystals["crystal"] >= crystal_cost
        can_afford_rainbow = crystals["rainbow"] >= rainbow_cost
        can_afford = can_afford_frags and can_afford_crystal and can_afford_rainbow
        from utils.helpers import pokemon_iv_total
        iv_sum = pokemon_iv_total(p)
        eligible.append({
            "instance_id": p["id"],
            "pokemon_id": p["pokemon_id"],
            "name_ko": p["name_ko"],
            "rarity": rarity,
            "frag_cost": frag_cost,
            "crystal_cost": crystal_cost,
            "rainbow_cost": rainbow_cost,
            "can_afford": can_afford,
            "matching_fields": matching_fields,
            "iv_sum": iv_sum,
        })
    # 전환 가능한 것 먼저, IV 내림차순
    eligible.sort(key=lambda e: (0 if e["can_afford"] else 1, -e["iv_sum"], e["name_ko"]))
    return eligible


def _build_convert_page(eligible: list, uid: int, frags: dict, crystals: dict,
                         page: int = 0, rarity_filter: str = "all") -> tuple[str, InlineKeyboardMarkup]:
    """이로치 전환 목록 페이지 빌드."""
    # 희귀도 필터 적용
    if rarity_filter != "all":
        target_rarity = _RARITY_FILTER_MAP.get(rarity_filter, (None, None))[1]
        filtered = [e for e in eligible if e["rarity"] == target_rarity] if target_rarity else eligible
    else:
        filtered = eligible

    total_pages = max(1, (len(filtered) + CONVERT_PAGE_SIZE - 1) // CONVERT_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * CONVERT_PAGE_SIZE
    page_items = filtered[start:start + CONVERT_PAGE_SIZE]

    total_frags = sum(frags.values())
    filter_label = _RARITY_FILTER_MAP.get(rarity_filter, ("전체", None))[0]
    # 필드별 조각 요약
    frag_detail = " / ".join(
        f"{config.CAMP_FIELDS[fk]['emoji']}{amt}"
        for fk, amt in frags.items() if amt > 0
    )
    lines = [
        f"{shiny_emoji()} 이로치 전환",
        "",
        f"🧩 보유 조각: {total_frags}개" + (f"  ({frag_detail})" if frag_detail else ""),
        f"💎 결정: {crystals['crystal']}개 | 🌈 무지개: {crystals['rainbow']}개",
        "",
    ]

    # 희귀도 탭 버튼
    tab_row = []
    for key, (label, _) in _RARITY_FILTER_MAP.items():
        display = f"[{label}]" if key == rarity_filter else label
        tab_row.append(InlineKeyboardButton(display, callback_data=f"cdm_cf_{uid}_{key}"))
    buttons = [tab_row[:3], tab_row[3:]]  # 2줄로 나눔

    if not filtered:
        lines.append(f"해당 희귀도의 전환 가능 포켓몬이 없습니다.")
    else:
        for e in page_items:
            cost_parts = [f"{e['frag_cost']}조각"]
            if e["crystal_cost"]:
                cost_parts.append(f"결정{e['crystal_cost']}")
            if e["rainbow_cost"]:
                cost_parts.append(f"무지개{e['rainbow_cost']}")
            rarity_tag = rarity_badge(e.get("rarity", ""))
            iv_tag = f" ({e['iv_sum']}/186)" if e.get("iv_sum") else ""
            if e["can_afford"]:
                lines.append(f"{icon_emoji('check')} {rarity_tag}{e['name_ko']}{iv_tag} — {'+'.join(cost_parts)}")
                buttons.append([InlineKeyboardButton(
                    f"✨ {e['name_ko']} 전환",
                    callback_data=f"cdm_conv_{uid}_{e['instance_id']}",
                )])
            else:
                lines.append(f"❌ {rarity_tag}{e['name_ko']}{iv_tag} — {'+'.join(cost_parts)}")

    if total_pages > 1:
        lines.append(f"\n📄 {page + 1}/{total_pages} ({len(filtered)}마리)")
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀ 이전", callback_data=f"cdm_convpg_{uid}_{page - 1}_{rarity_filter}"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("다음 ▶", callback_data=f"cdm_convpg_{uid}_{page + 1}_{rarity_filter}"))
        buttons.append(nav)

    lines.append("")
    buttons.append([InlineKeyboardButton("❌ 닫기", callback_data=f"cdm_cancel_{uid}")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def _build_decompose_page(shinies: list, uid: int, crystals: dict, page: int = 0) -> tuple[str, InlineKeyboardMarkup]:
    """분해 목록 페이지 빌드 (공용)."""
    total_pages = max(1, (len(shinies) + DECOMPOSE_PAGE_SIZE - 1) // DECOMPOSE_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * DECOMPOSE_PAGE_SIZE
    page_items = shinies[start:start + DECOMPOSE_PAGE_SIZE]

    lines = [
        "🔨 이로치 분해",
        "",
        f"💎 결정: {crystals['crystal']}개 | 🌈 무지개: {crystals['rainbow']}개",
        "",
        "⚠️ 분해하면 이로치가 해제됩니다!",
        "",
    ]

    buttons = []
    for p in page_items:
        rarity = p.get("rarity", "common")
        crystal_gain = config.CAMP_DECOMPOSE_CRYSTAL.get(rarity, 1)
        rainbow_gain = config.CAMP_DECOMPOSE_RAINBOW.get(rarity, 0)
        gain_parts = [f"💎+{crystal_gain}"]
        if rainbow_gain:
            gain_parts.append(f"🌈+{rainbow_gain}")
        rarity_tag = rarity_badge(rarity or "")
        iv_total = sum(p.get(k, 0) for k in ("iv_hp", "iv_atk", "iv_def", "iv_spa", "iv_spdef", "iv_spd"))
        lines.append(f"{shiny_emoji()} {rarity_tag}{p['name_ko']} (IV:{iv_total}) → {' '.join(gain_parts)}")
        buttons.append([InlineKeyboardButton(
            f"🔨 {p['name_ko']} (IV:{iv_total}) 분해",
            callback_data=f"cdm_dec_{uid}_{p['id']}",
        )])

    if total_pages > 1:
        lines.append(f"\n📄 {page + 1}/{total_pages} ({len(shinies)}마리)")
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀ 이전", callback_data=f"cdm_decpg_{uid}_{page - 1}"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("다음 ▶", callback_data=f"cdm_decpg_{uid}_{page + 1}"))
        buttons.append(nav)

    lines.append("")
    buttons.append([InlineKeyboardButton("❌ 닫기", callback_data=f"cdm_cancel_{uid}")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def shiny_convert_handler(update, context):
    """DM '이로치전환' — 전환 가능 포켓몬 리스트."""
    user_id = update.effective_user.id
    user = await queries.get_user(user_id)
    if not user:
        await update.message.reply_text("먼저 포켓몬을 잡아보세요!")
        return

    frags = await cq.get_user_fragments(user_id)
    crystals = await cq.get_crystals(user_id)
    pokemon_list = await queries.get_user_pokemon_list(user_id)
    pendings = await cq.get_shiny_pending(user_id)
    pending_ids = {p["instance_id"] for p in pendings}
    eligible = _build_convert_eligible(pokemon_list, frags, crystals, pending_ids)

    if not eligible:
        await update.message.reply_text(
            f"{shiny_emoji()} 이로치 전환 가능한 포켓몬이 없습니다.\n"
            "조각이 부족하거나, 보유 포켓몬이 모두 이로치입니다.",
            parse_mode="HTML",
        )
        return

    text, markup = _build_convert_page(eligible, user_id, frags, crystals, 0)
    await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def decompose_handler(update, context):
    """DM '분해' — 이로치 분해로 결정 획득."""
    user_id = update.effective_user.id
    user = await queries.get_user(user_id)
    if not user:
        await update.message.reply_text("먼저 포켓몬을 잡아보세요!")
        return

    pokemon_list = await queries.get_user_pokemon_list(user_id)
    shinies = [p for p in pokemon_list if p.get("is_shiny")]

    if not shinies:
        await update.message.reply_text("분해할 이로치 포켓몬이 없습니다.")
        return

    crystals = await cq.get_crystals(user_id)
    text, markup = _build_decompose_page(shinies, user_id, crystals, 0)
    await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")


# ═══════════════════════════════════════════════════════
# 콜백 핸들러: 이로치전환/분해 관련
# ═══════════════════════════════════════════════════════

async def _handle_conv(query, parts):
    """cdm_conv_{uid}_{instance_id} — 전환 확인."""
    uid = int(parts[2])
    instance_id = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    pokemon = await queries.get_user_pokemon_by_id(instance_id)
    if not pokemon or pokemon["user_id"] != uid:
        await query.answer("잘못된 선택입니다.", show_alert=True)
        return

    rarity = pokemon.get("rarity", "common")
    frag_cost = config.CAMP_SHINY_COST.get(rarity, 12)
    crystal_cost = config.CAMP_CRYSTAL_COST.get(rarity, 0)
    rainbow_cost = config.CAMP_RAINBOW_COST.get(rarity, 0)
    cooldown_sec = config.CAMP_SHINY_COOLDOWN.get(rarity, 21600)
    cooldown_h = cooldown_sec // 3600

    matching_fields = cs.get_matching_fields(pokemon["pokemon_id"])
    field_names = "/".join(config.CAMP_FIELDS[f]["name"] for f in matching_fields)

    cost_parts = [f"🧩 {field_names} 조각 {frag_cost}개"]
    if crystal_cost:
        cost_parts.append(f"💎 결정 {crystal_cost}개")
    if rainbow_cost:
        cost_parts.append(f"🌈 무지개 결정 {rainbow_cost}개")

    text = (
        f"✨ {pokemon['name_ko']}을(를) 이로치로 전환하시겠습니까?\n\n"
        f"비용:\n" + "\n".join(f"  {c}" for c in cost_parts) + "\n\n"
        f"⏰ 전환 소요 시간: {cooldown_h}시간\n"
        f"⚠️ 되돌릴 수 없습니다!"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ 전환!", callback_data=f"cdm_ok_{uid}_{instance_id}")],
        [InlineKeyboardButton("❌ 취소", callback_data=f"cdm_cancel_{uid}")],
    ])

    await query.answer()
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass


async def _handle_ok(query, parts, context):
    """cdm_ok_{uid}_{instance_id} — 전환 대기 등록."""
    uid = int(parts[2])
    instance_id = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    # 포켓몬 이름 미리 가져오기 (연출용)
    poke = await queries.get_user_pokemon_by_id(instance_id)
    poke_name_str = poke["name_ko"] if poke else "포켓몬"

    # 연출: 빛나기 시작
    await query.answer()
    try:
        await query.edit_message_text(
            f"✨ <b>{poke_name_str}</b>이(가)... 빛나기 시작한다...!", parse_mode="HTML")
    except Exception:
        pass
    await asyncio.sleep(1.5)

    # 전환 대기 등록
    success, msg, info = await cs.convert_to_shiny(uid, instance_id)

    if success and info:
        hours = info.get("duration_sec", 0) // 3600
        # 대기 시작 메시지
        try:
            await query.edit_message_text(msg, parse_mode="HTML")
        except Exception:
            pass
    else:
        try:
            await query.edit_message_text(msg, parse_mode="HTML")
        except Exception:
            pass


async def _handle_dec(query, parts):
    """cdm_dec_{uid}_{instance_id} — 분해 확인."""
    uid = int(parts[2])
    instance_id = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    pokemon = await queries.get_user_pokemon_by_id(instance_id)
    if not pokemon or pokemon["user_id"] != uid:
        await query.answer("잘못된 선택입니다.", show_alert=True)
        return

    rarity = pokemon.get("rarity", "common")
    crystal_gain = config.CAMP_DECOMPOSE_CRYSTAL.get(rarity, 1)
    rainbow_gain = config.CAMP_DECOMPOSE_RAINBOW.get(rarity, 0)

    gain_parts = [f"💎 결정 +{crystal_gain}"]
    if rainbow_gain:
        gain_parts.append(f"🌈 무지개 결정 +{rainbow_gain}")

    text = (
        f"🔨 {pokemon['name_ko']}(이로치)를 분해하시겠습니까?\n\n"
        f"획득:\n" + "\n".join(f"  {g}" for g in gain_parts) + "\n\n"
        f"⚠️ 이로치가 해제됩니다! 되돌릴 수 없습니다!"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔨 분해!", callback_data=f"cdm_decok_{uid}_{instance_id}")],
        [InlineKeyboardButton("❌ 취소", callback_data=f"cdm_cancel_{uid}")],
    ])

    await query.answer()
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass


async def _handle_decok(query, parts):
    """cdm_decok_{uid}_{instance_id} — 분해 실행."""
    uid = int(parts[2])
    instance_id = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    success, msg = await cs.decompose_shiny(uid, instance_id)
    await query.answer(msg[:200], show_alert=True)
    try:
        await query.edit_message_text(msg, parse_mode="HTML")
    except Exception:
        pass


async def _handle_convpg(query, parts):
    """cdm_convpg_{uid}_{page}_{filter} — 이로치전환 페이지네이션."""
    uid = int(parts[2])
    page = int(parts[3])
    rarity_filter = parts[4] if len(parts) > 4 else "all"
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return
    await query.answer()
    frags = await cq.get_user_fragments(uid)
    crystals_data = await cq.get_crystals(uid)
    pokemon_list = await queries.get_user_pokemon_list(uid)
    pendings = await cq.get_shiny_pending(uid)
    pending_ids = {p["instance_id"] for p in pendings}
    eligible = _build_convert_eligible(pokemon_list, frags, crystals_data, pending_ids)
    text, markup = _build_convert_page(eligible, uid, frags, crystals_data, page, rarity_filter)
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass


async def _handle_cf(query, parts):
    """cdm_cf_{uid}_{filter} — 이로치전환 희귀도 필터."""
    uid = int(parts[2])
    rarity_filter = parts[3] if len(parts) > 3 else "all"
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return
    await query.answer()
    frags = await cq.get_user_fragments(uid)
    crystals_data = await cq.get_crystals(uid)
    pokemon_list = await queries.get_user_pokemon_list(uid)
    pendings = await cq.get_shiny_pending(uid)
    pending_ids = {p["instance_id"] for p in pendings}
    eligible = _build_convert_eligible(pokemon_list, frags, crystals_data, pending_ids)
    text, markup = _build_convert_page(eligible, uid, frags, crystals_data, 0, rarity_filter)
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass


async def _handle_decpg(query, parts):
    """cdm_decpg_{uid}_{page} — 분해 페이지네이션."""
    uid = int(parts[2])
    page = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return
    await query.answer()
    pokemon_list = await queries.get_user_pokemon_list(uid)
    shinies = [p for p in pokemon_list if p.get("is_shiny")]
    crystals_data = await cq.get_crystals(uid)
    text, markup = _build_decompose_page(shinies, uid, crystals_data, page)
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass


async def _handle_hub_convert(query, parts):
    """cdm_hub_convert_{uid} — 이로치전환 (허브에서)."""
    uid = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    await query.answer()
    frags = await cq.get_user_fragments(uid)
    crystals_data = await cq.get_crystals(uid)
    pokemon_list = await queries.get_user_pokemon_list(uid)
    pendings = await cq.get_shiny_pending(uid)
    pending_ids = {p["instance_id"] for p in pendings}
    eligible = _build_convert_eligible(pokemon_list, frags, crystals_data, pending_ids)

    if not eligible:
        try:
            await query.edit_message_text(
                f"{shiny_emoji()} 이로치 전환 가능한 포켓몬이 없습니다.\n"
                "조각이 부족하거나, 보유 포켓몬이 모두 이로치입니다.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    text, markup = _build_convert_page(eligible, uid, frags, crystals_data, 0)
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass


async def _handle_hub_decompose(query, parts):
    """cdm_hub_decompose_{uid} — 분해 (허브에서)."""
    uid = int(parts[3])
    if query.from_user.id != uid:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    await query.answer()
    pokemon_list = await queries.get_user_pokemon_list(uid)
    shinies = [p for p in pokemon_list if p.get("is_shiny")]

    if not shinies:
        try:
            await query.edit_message_text("분해할 이로치 포켓몬이 없습니다.")
        except Exception:
            pass
        return

    crystals_data = await cq.get_crystals(uid)
    text, markup = _build_decompose_page(shinies, uid, crystals_data, 0)
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass
