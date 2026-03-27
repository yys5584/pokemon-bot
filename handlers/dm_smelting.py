"""DM handler for 이로치 제련소 (Shiny Smelting)."""

import asyncio
import logging
import random

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from database import queries
from database import smelting_queries as sq
from services import smelting_service
from utils.helpers import rarity_badge, pokemon_iv_total, iv_grade
from utils.i18n import get_user_lang

logger = logging.getLogger(__name__)

PAGE_SIZE = 8

RARITY_FILTERS = [
    ("all", "전체"),
    ("common", "일반"),
    ("rare", "레어"),
    ("epic", "에픽"),
    ("legendary", "전설"),
    ("ultra_legendary", "초전설"),
]

# 보상 아이템 한글명
_ITEM_NAMES = {
    "bp": "BP",
    "fragment": "만능 조각",
    "hyperball": "하이퍼볼",
    "masterball": "마스터볼",
    "iv_reroll_all": "IV 리롤권",
    "iv_stone_3": "IV 강화석 III",
    "time_reduce_ticket": "시간단축권",
    "shiny_spawn": "이로치 소환권",
    "mega_stone_ticket": "메가스톤 제련권",
}


# ── 상태 관리 ──────────────────────────────────────────────

def _get_state(context) -> dict:
    key = "smelting_state"
    if key not in context.user_data:
        context.user_data[key] = {
            "page": 0,
            "selected_ids": [],
            "rarity_filter": "all",
            "shiny_filter": False,
            "pokemon_cache": None,
        }
    return context.user_data[key]


def _clear_state(context):
    context.user_data.pop("smelting_state", None)


async def _get_subscription(user_id: int) -> str:
    try:
        from services.subscription_service import get_user_tier
        tier = await get_user_tier(user_id)
        return tier or "none"
    except Exception:
        return "none"


# ── 게이지 바 ──────────────────────────────────────────────

def _gauge_bar(gauge: float, length: int = 10) -> str:
    pct = min(max(gauge, 0), 100)
    filled = round(pct / 100 * length)
    return "▓" * filled + "░" * (length - filled)


def _get_rates_display(gauge: float) -> tuple[float, float]:
    """현재 게이지에 따른 (이로치%, 메가스톤%) 표시용."""
    shiny_rate, mega_rate = 2.0, 0.7
    for threshold, s, m in config.SMELTING_RATES:
        if gauge >= threshold:
            shiny_rate, mega_rate = s, m
    return shiny_rate, mega_rate


# ── 포켓몬 필터 ────────────────────────────────────────────

def _filter_pokemon(pokemon_list: list[dict], rarity_filter: str, shiny_filter: bool) -> list[dict]:
    filtered = pokemon_list
    if rarity_filter != "all":
        filtered = [p for p in filtered if p.get("rarity") == rarity_filter]
    if shiny_filter:
        filtered = [p for p in filtered if p.get("is_shiny")]
    return filtered


# ── 메인 메뉴 패널 ─────────────────────────────────────────

async def _build_main_menu(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    gauge_data = await sq.get_smelting_gauge(user_id)
    gauge = gauge_data["gauge"]
    shiny_rate, mega_rate = _get_rates_display(gauge)

    user = await queries.get_user(user_id)
    bp = user.get("battle_points", 0) if user else 0
    sub = await _get_subscription(user_id)
    sub_label = {"none": "일반", "basic": "베이직", "channel_owner": "채널장"}.get(sub, "일반")
    sub_mult = config.SMELTING_SUB_MULTIPLIER.get(sub, 1.0)

    border = "✦═══════════════════✦"

    lines = [
        f"🔥 <b>이로치 제련소</b>",
        "",
        border,
        f"  📊 게이지: {_gauge_bar(gauge)} {gauge:.1f}%",
        f"  ✨ 이로치 확률: {shiny_rate}%",
        f"  💎 메가스톤 확률: {mega_rate}%",
        border,
        "",
        f"💰 보유 BP: {bp:,}",
        f"🎫 제련 비용: {config.SMELTING_BP_COST} BP",
        f"👤 구독: {sub_label} (x{sub_mult})",
        "",
        "포켓몬 10마리를 투입하여 이로치 또는",
        "메가스톤 제련권을 노려보세요!",
        "",
        "💡 높은 등급 포켓몬 = 더 많은 게이지",
        "💡 게이지가 높을수록 확률 UP",
    ]

    buttons = [
        [InlineKeyboardButton("🔥 제련 시작", callback_data=f"sml_start_{user_id}")],
    ]
    if gauge >= 100:
        lines.insert(4, "  ⚡ <b>게이지 MAX! 메가스톤 확정!</b>")

    return "\n".join(lines), InlineKeyboardMarkup(buttons)


# ── 선택 패널 ──────────────────────────────────────────────

def _build_select_panel(
    user_id: int,
    pokemon_list: list[dict],
    selected_ids: list[int],
    page: int,
    rarity_filter: str,
    shiny_filter: bool,
) -> tuple[str, InlineKeyboardMarkup]:
    filtered = _filter_pokemon(pokemon_list, rarity_filter, shiny_filter)
    total = len(filtered)
    max_page = max(0, (total - 1) // PAGE_SIZE)
    page = min(page, max_page)
    start = page * PAGE_SIZE
    page_items = filtered[start:start + PAGE_SIZE]

    count = len(selected_ids)
    required = config.SMELTING_REQUIRED_COUNT

    text = f"🔥 <b>제련 포켓몬 선택</b>\n\n"
    text += f"선택: <b>{count}/{required}</b>\n"

    # 필터 라벨
    filter_label = next((label for key, label in RARITY_FILTERS if key == rarity_filter), "전체")
    shiny_label = " + ✨이로치" if shiny_filter else ""
    text += f"필터: {filter_label}{shiny_label} ({total}마리)\n\n"

    if total == 0:
        text += "해당 조건의 포켓몬이 없습니다."

    rows: list[list[InlineKeyboardButton]] = []

    # 등급 필터 (2줄 × 3)
    filter_row1 = []
    filter_row2 = []
    for i, (key, label) in enumerate(RARITY_FILTERS):
        prefix = "▪" if key == rarity_filter else ""
        btn = InlineKeyboardButton(
            f"{prefix}{label}",
            callback_data=f"sml_rf_{user_id}_{key}",
        )
        if i < 3:
            filter_row1.append(btn)
        else:
            filter_row2.append(btn)
    # 이로치 토글
    shiny_mark = "▪" if shiny_filter else ""
    filter_row2.append(InlineKeyboardButton(
        f"{shiny_mark}✨이로치",
        callback_data=f"sml_sf_{user_id}",
    ))
    rows.append(filter_row1)
    rows.append(filter_row2)

    # 포켓몬 목록
    for p in page_items:
        iid = p["id"]
        is_selected = iid in selected_ids
        check = "✅" if is_selected else "⬜"
        rarity_emoji = config.RARITY_EMOJI.get(p.get("rarity", ""), "")
        name = p.get("name_ko", "???")
        rarity_label = config.RARITY_LABEL.get(p.get("rarity", ""), "")
        shiny_mark = "✨" if p.get("is_shiny") else ""
        iv_t = pokemon_iv_total(p)
        grade = iv_grade(iv_t)

        label = f"{check} {rarity_emoji} {shiny_mark}{name} [{rarity_label}] [{grade}]"
        rows.append([InlineKeyboardButton(
            label,
            callback_data=f"sml_tog_{user_id}_{iid}",
        )])

    # 페이지네이션
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀", callback_data=f"sml_pg_{user_id}_{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"{page + 1}/{max_page + 1}", callback_data=f"sml_noop_{user_id}"))
    if page < max_page:
        nav_row.append(InlineKeyboardButton("▶", callback_data=f"sml_pg_{user_id}_{page + 1}"))
    rows.append(nav_row)

    # 하단 버튼
    bottom_row = []
    if count == required:
        bottom_row.append(InlineKeyboardButton("🔥 제련!", callback_data=f"sml_confirm_{user_id}"))
    bottom_row.append(InlineKeyboardButton("🗑 초기화", callback_data=f"sml_reset_{user_id}"))
    bottom_row.append(InlineKeyboardButton("🔙 돌아가기", callback_data=f"sml_back_{user_id}"))
    rows.append(bottom_row)

    return text, InlineKeyboardMarkup(rows)


# ── 확인 패널 ──────────────────────────────────────────────

async def _build_confirm_panel(
    user_id: int,
    pokemon_list: list[dict],
    selected_ids: list[int],
) -> tuple[str, InlineKeyboardMarkup]:
    selected = [p for p in pokemon_list if p["id"] in selected_ids]

    gauge_data = await sq.get_smelting_gauge(user_id)
    current_gauge = gauge_data["gauge"]
    sub = await _get_subscription(user_id)
    gauge_gain = smelting_service.calculate_gauge(selected, sub)
    new_gauge = min(round(current_gauge + gauge_gain, 2), 100)
    shiny_rate, mega_rate = _get_rates_display(new_gauge)

    border = "✦═══════════════════✦"

    lines = [
        f"🔥 <b>제련 확인</b>",
        "",
        border,
    ]

    # 투입 포켓몬 목록
    for i, p in enumerate(selected, 1):
        rarity_emoji = config.RARITY_EMOJI.get(p.get("rarity", ""), "")
        name = p.get("name_ko", "???")
        shiny = "✨" if p.get("is_shiny") else ""
        lines.append(f"  {i}. {rarity_emoji} {shiny}{name}")

    lines.extend([
        border,
        "",
        f"📊 게이지: {current_gauge:.1f}% → <b>{new_gauge:.1f}%</b> (+{gauge_gain:.1f}%)",
        f"✨ 이로치 확률: <b>{shiny_rate}%</b>",
        f"💎 메가스톤 확률: <b>{mega_rate}%</b>",
        f"💰 비용: {config.SMELTING_BP_COST} BP",
        "",
        "⚠️ <b>투입된 포켓몬은 되돌릴 수 없습니다!</b>",
    ])

    buttons = [
        [
            InlineKeyboardButton("🔥 제련 실행!", callback_data=f"sml_exec_{user_id}"),
            InlineKeyboardButton("🔙 돌아가기", callback_data=f"sml_reselect_{user_id}"),
        ],
    ]

    return "\n".join(lines), InlineKeyboardMarkup(buttons)


# ── MC 애니메이션 ──────────────────────────────────────────

async def _play_smelting_animation(
    query,
    user_id: int,
    selected_pokemon: list[dict],
    result: dict,
):
    """문박사 MC 나레이션 + 제련 애니메이션.

    같은 메시지를 반복 edit하여 애니메이션 효과 구현.
    """
    border = "✦═══════════════════✦"
    consumed_count = len(selected_pokemon)

    for i, p in enumerate(selected_pokemon):
        name = p.get("name_ko", "???")
        shiny = "✨" if p.get("is_shiny") else ""
        display_name = f"{shiny}{name}"

        # 희생 멘트
        sacrifice_line = random.choice(config.SMELTING_MC_SACRIFICE).format(name=display_name)
        # 진행 멘트
        progress_line = config.SMELTING_MC_PROGRESS[i] if i < len(config.SMELTING_MC_PROGRESS) else ""

        # 게이지 바 (투입 수 기반)
        pct = round((i + 1) / consumed_count * 100)
        bar = _gauge_bar(pct)

        lines = [
            f"🔥 <b>이로치 제련소</b>",
            "",
            border,
            f"  🔥 {progress_line}",
            border,
            "",
            f"  {sacrifice_line}",
            "",
            f"  {bar} {pct}% ({i + 1}/{consumed_count})",
            "",
        ]

        # 지나간 포켓몬 목록 (흐린 표시)
        if i > 0:
            lines.append("  ───────────────")
            for j in range(max(0, i - 2), i):
                prev = selected_pokemon[j]
                prev_name = prev.get("name_ko", "???")
                prev_shiny = "✨" if prev.get("is_shiny") else ""
                lines.append(f"  🕯 {prev_shiny}{prev_name}")
            lines.append("")

        text = "\n".join(lines)

        try:
            await query.edit_message_text(text, parse_mode="HTML")
        except Exception:
            pass

        # 타이밍: 마지막 3개는 3초, 나머지 2초
        delay = 3.0 if i >= consumed_count - 3 else 2.0
        await asyncio.sleep(delay)

    # 최종 판정 대기
    await asyncio.sleep(2.0)

    # 결과 화면
    await _show_result(query, user_id, result)


# ── 결과 화면 ──────────────────────────────────────────────

async def _show_result(query, user_id: int, result: dict):
    border = "✦═══════════════════✦"
    result_type = result["result"]
    gauge_after = result["gauge_after"]
    gauge_gained = result["gauge_gained"]
    reward = result.get("reward", {})

    # MC 리액션
    mc_lines = config.SMELTING_MC_RESULT.get(result_type, config.SMELTING_MC_RESULT["fail"])
    mc_line = random.choice(mc_lines)

    lines = [
        f"🔥 <b>이로치 제련소</b>",
        "",
        border,
    ]

    if result_type == "shiny":
        detail = reward.get("detail", {})
        poke_name = detail.get("name", "???")
        rarity = detail.get("rarity", "common")
        rarity_emoji = config.RARITY_EMOJI.get(rarity, "")
        rarity_label = config.RARITY_LABEL.get(rarity, "")
        lines.extend([
            f"  🎉 <b>대성공!!!</b>",
            "",
            f"  ✨ {rarity_emoji} <b>{poke_name}</b> [{rarity_label}]",
            f"  이로치 포켓몬을 획득했습니다!",
        ])

    elif result_type == "mega_ticket":
        lines.extend([
            f"  💎 <b>초대박!!!</b>",
            "",
            f"  🔮 <b>메가스톤 제련권</b> 획득!",
            f"  메가진화 포켓몬을 제련할 수 있습니다!",
        ])

    else:
        # 소각 보상
        tier_label = reward.get("tier", "⬜ 일반")
        item_key = reward.get("item", "bp")
        amount = reward.get("amount", 0)
        item_name = _ITEM_NAMES.get(item_key, item_key)
        lines.extend([
            f"  📦 <b>소각 보상</b> ({tier_label})",
            "",
            f"  🎁 {item_name} x{amount}",
        ])

    shiny_rate, mega_rate = _get_rates_display(gauge_after)
    lines.extend([
        "",
        border,
        f"  💬 {mc_line}",
        border,
        "",
        f"📊 게이지: {_gauge_bar(gauge_after)} {gauge_after:.1f}% (+{gauge_gained:.1f}%)",
        f"✨ 이로치 확률: {shiny_rate}% | 💎 메가스톤: {mega_rate}%",
    ])

    buttons = [
        [InlineKeyboardButton("🔥 다시 도전!", callback_data=f"sml_retry_{user_id}")],
    ]

    text = "\n".join(lines)
    try:
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════════════
# 핸들러
# ══════════════════════════════════════════════════════════

async def smelting_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '제련' / '제련소' command in DM."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id

    # 상태 초기화
    _clear_state(context)

    text, kb = await _build_main_menu(user_id)
    await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")


async def smelting_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all sml_ callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    parts = data.split("_")
    # sml_{action}_{user_id}[_{extra}]
    if len(parts) < 3:
        await query.answer()
        return

    action = parts[1]

    try:
        user_id = int(parts[2])
    except (IndexError, ValueError):
        await query.answer()
        return

    # 본인 체크
    if query.from_user.id != user_id:
        await query.answer("본인만 사용할 수 있습니다!", show_alert=True)
        return

    state = _get_state(context)

    # ── noop ──
    if action == "noop":
        await query.answer()
        return

    # ── 메인 메뉴 → 선택 시작 ──
    if action == "start":
        await query.answer()

        # BP 체크
        user = await queries.get_user(user_id)
        bp = user.get("battle_points", 0) if user else 0
        if bp < config.SMELTING_BP_COST:
            try:
                await query.edit_message_text(
                    f"❌ BP가 부족합니다.\n"
                    f"보유: {bp:,} BP / 필요: {config.SMELTING_BP_COST} BP",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return

        # 포켓몬 캐시 로드
        pokemon_list = await smelting_service.get_smeltable_pokemon(user_id)
        if len(pokemon_list) < config.SMELTING_REQUIRED_COUNT:
            try:
                await query.edit_message_text(
                    f"❌ 제련 가능한 포켓몬이 부족합니다.\n"
                    f"보유: {len(pokemon_list)}마리 / 필요: {config.SMELTING_REQUIRED_COUNT}마리\n\n"
                    f"💡 팀/보호 중인 포켓몬은 제외됩니다.",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return

        state["pokemon_cache"] = pokemon_list
        state["selected_ids"] = []
        state["page"] = 0
        state["rarity_filter"] = "all"
        state["shiny_filter"] = False

        text, kb = _build_select_panel(
            user_id, pokemon_list, [], 0, "all", False,
        )
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    # ── 등급 필터 ──
    elif action == "rf":
        rarity = parts[3] if len(parts) > 3 else "all"
        # ultra_legendary 처리
        if len(parts) > 4:
            rarity = "_".join(parts[3:])
        state["rarity_filter"] = rarity
        state["page"] = 0
        await query.answer()

        cache = state.get("pokemon_cache") or []
        text, kb = _build_select_panel(
            user_id, cache, state["selected_ids"],
            0, rarity, state["shiny_filter"],
        )
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    # ── 이로치 필터 토글 ──
    elif action == "sf":
        state["shiny_filter"] = not state["shiny_filter"]
        state["page"] = 0
        await query.answer()

        cache = state.get("pokemon_cache") or []
        text, kb = _build_select_panel(
            user_id, cache, state["selected_ids"],
            0, state["rarity_filter"], state["shiny_filter"],
        )
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    # ── 포켓몬 토글 선택 ──
    elif action == "tog":
        try:
            instance_id = int(parts[3])
        except (IndexError, ValueError):
            await query.answer()
            return

        selected = state["selected_ids"]
        required = config.SMELTING_REQUIRED_COUNT

        if instance_id in selected:
            selected.remove(instance_id)
            await query.answer()
        elif len(selected) >= required:
            await query.answer(f"{required}마리까지만 선택할 수 있습니다!", show_alert=True)
            return
        else:
            selected.append(instance_id)
            await query.answer()

        cache = state.get("pokemon_cache") or []
        text, kb = _build_select_panel(
            user_id, cache, selected,
            state["page"], state["rarity_filter"], state["shiny_filter"],
        )
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    # ── 페이지네이션 ──
    elif action == "pg":
        try:
            page = int(parts[3])
        except (IndexError, ValueError):
            await query.answer()
            return
        state["page"] = page
        await query.answer()

        cache = state.get("pokemon_cache") or []
        text, kb = _build_select_panel(
            user_id, cache, state["selected_ids"],
            page, state["rarity_filter"], state["shiny_filter"],
        )
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    # ── 선택 초기화 ──
    elif action == "reset":
        state["selected_ids"] = []
        state["page"] = 0
        await query.answer("선택이 초기화되었습니다.")

        cache = state.get("pokemon_cache") or []
        text, kb = _build_select_panel(
            user_id, cache, [],
            0, state["rarity_filter"], state["shiny_filter"],
        )
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    # ── 선택 → 메인 메뉴 돌아가기 ──
    elif action == "back":
        _clear_state(context)
        await query.answer()

        text, kb = await _build_main_menu(user_id)
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    # ── 확인 화면 ──
    elif action == "confirm":
        selected = state["selected_ids"]
        if len(selected) != config.SMELTING_REQUIRED_COUNT:
            await query.answer(f"{config.SMELTING_REQUIRED_COUNT}마리를 선택해주세요!", show_alert=True)
            return
        await query.answer()

        cache = state.get("pokemon_cache") or []
        text, kb = await _build_confirm_panel(user_id, cache, selected)
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    # ── 확인 → 선택으로 돌아가기 ──
    elif action == "reselect":
        await query.answer()

        cache = state.get("pokemon_cache") or []
        text, kb = _build_select_panel(
            user_id, cache, state["selected_ids"],
            state["page"], state["rarity_filter"], state["shiny_filter"],
        )
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    # ── 제련 실행 ──
    elif action == "exec":
        selected = state["selected_ids"]
        if len(selected) != config.SMELTING_REQUIRED_COUNT:
            await query.answer("잘못된 요청입니다.", show_alert=True)
            return

        await query.answer("🔥 제련 시작...")

        sub = await _get_subscription(user_id)
        result = await smelting_service.execute_smelting(user_id, selected, sub)

        if not result.get("success"):
            error = result.get("error", "알 수 없는 오류")
            try:
                await query.edit_message_text(f"❌ {error}", parse_mode="HTML")
            except Exception:
                pass
            return

        # 애니메이션에 필요한 포켓몬 정보 추출
        cache = state.get("pokemon_cache") or []
        selected_pokemon = [p for p in cache if p["id"] in selected]
        # selected 순서 유지
        id_to_pokemon = {p["id"]: p for p in selected_pokemon}
        ordered_pokemon = [id_to_pokemon[iid] for iid in selected if iid in id_to_pokemon]

        # 상태 클리어 (포켓몬은 이미 소각됨)
        _clear_state(context)

        # MC 애니메이션 시작
        await _play_smelting_animation(query, user_id, ordered_pokemon, result)

    # ── 다시 도전 ──
    elif action == "retry":
        _clear_state(context)
        await query.answer()

        text, kb = await _build_main_menu(user_id)
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass

    else:
        await query.answer()
