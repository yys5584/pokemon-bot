"""Camp v2 DM handlers — 내캠프, 이로치전환, 분해, 거점설정."""

import time
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import config
from database import camp_queries as cq
from database import queries
from services import camp_service as cs

logger = logging.getLogger(__name__)

# ── Duplicate-click guard ──
_callback_dedup: dict[str, float] = {}


def _is_duplicate_callback(query) -> bool:
    key = f"{query.message.message_id}:{query.data}:{query.from_user.id}"
    now = time.monotonic()
    if len(_callback_dedup) > 200:
        cutoff = now - 60
        stale = [k for k, v in _callback_dedup.items() if v < cutoff]
        for k in stale:
            del _callback_dedup[k]
    if key in _callback_dedup:
        return True
    _callback_dedup[key] = now
    return False


# ═══════════════════════════════════════════════════════
# DM 명령: 내캠프
# ═══════════════════════════════════════════════════════

async def my_camp_handler(update, context):
    """DM '내캠프' — 배치 현황 + 조각 + 결정."""
    user_id = update.effective_user.id
    user = await queries.get_user(user_id)
    if not user:
        await update.message.reply_text("먼저 포켓몬을 잡아보세요!")
        return

    summary = await cs.get_user_camp_summary(user_id)

    lines = ["🏕 내 캠프 현황", "━━━━━━━━━━━━━"]

    # 거점 캠프
    if summary["home_camp"]:
        lines.append(f"🏠 거점 캠프: {summary['home_camp']}")
    else:
        lines.append("🏠 거점 캠프: 미설정 (그룹에서 '거점설정')")

    # 조각
    frags = summary["fragments"]
    if frags:
        total = sum(frags.values())
        lines.append(f"\n🧩 조각 (총 {total}개)")
        for fkey, finfo in config.CAMP_FIELDS.items():
            amount = frags.get(fkey, 0)
            if amount > 0:
                lines.append(f"  {finfo['emoji']} {finfo['name']}: {amount}개")
    else:
        lines.append("\n🧩 조각: 없음")

    # 결정
    crystals = summary["crystals"]
    if crystals["crystal"] > 0 or crystals["rainbow"] > 0:
        lines.append(f"\n💎 결정: {crystals['crystal']}개")
        if crystals["rainbow"] > 0:
            lines.append(f"🌈 무지개 결정: {crystals['rainbow']}개")

    # 쿨타임
    if summary["cooldown_remaining"]:
        hours = int(summary["cooldown_remaining"] // 3600)
        mins = int((summary["cooldown_remaining"] % 3600) // 60)
        lines.append(f"\n⏰ 전환 쿨타임: {hours}시간 {mins}분 남음")

    lines.append("\n━━━━━━━━━━━━━")

    # 배치 현황
    placements = summary["placements"]
    if placements:
        lines.append(f"📋 배치 현황 ({len(placements)}마리)")
        for p in placements:
            fi = config.CAMP_FIELDS.get(p.get("field_type", ""), {})
            shiny = "✨" if p.get("is_shiny") else ""
            lines.append(f"  {fi.get('emoji', '🏕')} {shiny}{p['name_ko']} ({p['score']}점)")
    else:
        lines.append("📋 배치: 없음")

    lines.append("━━━━━━━━━━━━━")

    # 힌트
    hints = []
    total_frags = sum(frags.values()) if frags else 0
    if total_frags >= 12:
        hints.append("✨ '이로치전환'으로 이로치 변환!")
    if crystals["crystal"] == 0 and total_frags > 0:
        hints.append("🔨 '분해'로 이로치를 결정으로!")
    if hints:
        lines.extend(hints)

    await update.message.reply_text("\n".join(lines))


# ═══════════════════════════════════════════════════════
# DM 명령: 이로치전환
# ═══════════════════════════════════════════════════════

async def shiny_convert_handler(update, context):
    """DM '이로치전환' — 전환 가능 포켓몬 리스트."""
    user_id = update.effective_user.id
    user = await queries.get_user(user_id)
    if not user:
        await update.message.reply_text("먼저 포켓몬을 잡아보세요!")
        return

    # 보유 자원
    frags = await cq.get_user_fragments(user_id)
    crystals = await cq.get_crystals(user_id)

    # 비이로치 포켓몬 중 타입이 매칭되는 것들
    pokemon_list = await queries.get_user_pokemon_list(user_id)
    eligible = []
    for p in pokemon_list:
        if p.get("is_shiny"):
            continue
        matching_fields = cs.get_matching_fields(p["pokemon_id"])
        if not matching_fields:
            continue

        rarity = p.get("rarity", "common")
        frag_cost = config.CAMP_SHINY_COST.get(rarity, 12)
        crystal_cost = config.CAMP_CRYSTAL_COST.get(rarity, 0)
        rainbow_cost = config.CAMP_RAINBOW_COST.get(rarity, 0)

        # 어느 필드든 조각 충분한지
        can_afford_frags = any(frags.get(f, 0) >= frag_cost for f in matching_fields)
        can_afford_crystal = crystals["crystal"] >= crystal_cost
        can_afford_rainbow = crystals["rainbow"] >= rainbow_cost
        can_afford = can_afford_frags and can_afford_crystal and can_afford_rainbow

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
        })

    if not eligible:
        await update.message.reply_text(
            "✨ 이로치 전환 가능한 포켓몬이 없습니다.\n"
            "조각이 부족하거나, 보유 포켓몬이 모두 이로치입니다."
        )
        return

    # 전환 가능한 것만 상위 표시
    affordable = [e for e in eligible if e["can_afford"]][:10]
    unaffordable = [e for e in eligible if not e["can_afford"]][:5]

    total_frags = sum(frags.values())
    lines = [
        "✨ 이로치 전환",
        "━━━━━━━━━━━━━",
        f"🧩 보유 조각: {total_frags}개",
        f"💎 결정: {crystals['crystal']}개 | 🌈 무지개: {crystals['rainbow']}개",
        "",
    ]

    buttons = []
    if affordable:
        lines.append("── 전환 가능 ──")
        for e in affordable:
            cost_parts = [f"{e['frag_cost']}조각"]
            if e["crystal_cost"]:
                cost_parts.append(f"결정{e['crystal_cost']}")
            if e["rainbow_cost"]:
                cost_parts.append(f"무지개{e['rainbow_cost']}")
            rarity_tag = {"ultra_legendary": "🌟", "legendary": "⭐", "epic": "💎"}.get(e["rarity"], "")
            lines.append(f"✅ {rarity_tag}{e['name_ko']} — {'+'.join(cost_parts)}")
            buttons.append([InlineKeyboardButton(
                f"✨ {e['name_ko']} 전환",
                callback_data=f"cdm_conv_{user_id}_{e['instance_id']}",
            )])

    if unaffordable:
        lines.append("\n── 자원 부족 ──")
        for e in unaffordable:
            cost_parts = [f"{e['frag_cost']}조각"]
            if e["crystal_cost"]:
                cost_parts.append(f"결정{e['crystal_cost']}")
            rarity_tag = {"ultra_legendary": "🌟", "legendary": "⭐", "epic": "💎"}.get(e["rarity"], "")
            lines.append(f"❌ {rarity_tag}{e['name_ko']} — {'+'.join(cost_parts)}")

    lines.append("━━━━━━━━━━━━━")

    markup = InlineKeyboardMarkup(buttons) if buttons else None
    await update.message.reply_text("\n".join(lines), reply_markup=markup)


# ═══════════════════════════════════════════════════════
# DM 명령: 분해
# ═══════════════════════════════════════════════════════

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

    lines = [
        "🔨 이로치 분해",
        "━━━━━━━━━━━━━",
        f"💎 결정: {crystals['crystal']}개 | 🌈 무지개: {crystals['rainbow']}개",
        "",
        "⚠️ 분해하면 이로치가 해제됩니다!",
        "",
    ]

    buttons = []
    for p in shinies[:15]:
        rarity = p.get("rarity", "common")
        crystal_gain = config.CAMP_DECOMPOSE_CRYSTAL.get(rarity, 1)
        rainbow_gain = config.CAMP_DECOMPOSE_RAINBOW.get(rarity, 0)

        gain_parts = [f"💎+{crystal_gain}"]
        if rainbow_gain:
            gain_parts.append(f"🌈+{rainbow_gain}")

        rarity_tag = {"ultra_legendary": "🌟", "legendary": "⭐", "epic": "💎"}.get(rarity, "")
        lines.append(f"✨ {rarity_tag}{p['name_ko']} → {' '.join(gain_parts)}")
        buttons.append([InlineKeyboardButton(
            f"🔨 {p['name_ko']} 분해",
            callback_data=f"cdm_dec_{user_id}_{p['id']}",
        )])

    lines.append("━━━━━━━━━━━━━")

    await update.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))


# ═══════════════════════════════════════════════════════
# 콜백 라우터 (cdm_*)
# ═══════════════════════════════════════════════════════

async def camp_dm_callback_handler(update, context):
    """cdm_* 콜백 전체 라우터."""
    query = update.callback_query
    if not query or not query.data:
        return

    if _is_duplicate_callback(query):
        await query.answer()
        return

    data = query.data
    parts = data.split("_")

    # ── cdm_conv_{uid}_{instance_id} — 전환 확인 ──
    if data.startswith("cdm_conv_"):
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
            f"⏰ 전환 후 쿨타임: {cooldown_h}시간\n"
            f"⚠️ 되돌릴 수 없습니다!"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ 전환!", callback_data=f"cdm_ok_{uid}_{instance_id}")],
            [InlineKeyboardButton("❌ 취소", callback_data=f"cdm_cancel_{uid}")],
        ])

        await query.answer()
        try:
            await query.edit_message_text(text, reply_markup=markup)
        except Exception:
            pass

    # ── cdm_ok_{uid}_{instance_id} — 전환 실행 ──
    elif data.startswith("cdm_ok_"):
        uid = int(parts[2])
        instance_id = int(parts[3])
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        success, msg = await cs.convert_to_shiny(uid, instance_id)
        await query.answer(msg[:200], show_alert=True)
        try:
            await query.edit_message_text(msg)
        except Exception:
            pass

    # ── cdm_dec_{uid}_{instance_id} — 분해 확인 ──
    elif data.startswith("cdm_dec_"):
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
            await query.edit_message_text(text, reply_markup=markup)
        except Exception:
            pass

    # ── cdm_decok_{uid}_{instance_id} — 분해 실행 ──
    elif data.startswith("cdm_decok_"):
        uid = int(parts[2])
        instance_id = int(parts[3])
        if query.from_user.id != uid:
            await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
            return

        success, msg = await cs.decompose_shiny(uid, instance_id)
        await query.answer(msg[:200], show_alert=True)
        try:
            await query.edit_message_text(msg)
        except Exception:
            pass

    # ── cdm_cancel_{uid} — 취소 ──
    elif data.startswith("cdm_cancel_"):
        uid = int(parts[2])
        if query.from_user.id != uid:
            await query.answer()
            return
        await query.answer()
        try:
            await query.edit_message_text("취소되었습니다.")
        except Exception:
            pass
