"""DM 가챠 (뽑기) + 아이템 사용 핸들러."""

import os
import random
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ContextTypes

import config
from database import queries
from database.battle_queries import get_bp
from utils.helpers import icon_emoji

logger = logging.getLogger(__name__)

# 가챠 이미지 경로
_GACHA_IMG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "gacha")
_IMG_NORMAL = os.path.join(_GACHA_IMG_DIR, "nomal-gacha.jpg")
_IMG_GOLDEN = os.path.join(_GACHA_IMG_DIR, "golden-gacha.jpg")

# 대박 등급 (골든 이미지 사용)
_JACKPOT_TIERS = {"bp_jackpot", "iv_reroll_one", "shiny_egg", "shiny_spawn"}

# 등급별 연출 텍스트
_TIER_EFFECT = {
    "bp_refund":     ("💰", "..."),
    "hyperball":     ("🔵", "오!"),
    "masterball":    ("🟣", "좋은데?!"),
    "iv_reroll_all": ("🔄", "이거 좋다!"),
    "bp_jackpot":    ("💎", "대박!!!"),
    "iv_reroll_one": ("🎯", "노리기 가능!"),
    "shiny_egg":     ("🥚", "미쳤다!!!"),
    "shiny_spawn":   ("✨", "전설급!!!!"),
}

# 등급별 별 표시
_TIER_STARS = {
    "bp_refund": "⭐", "hyperball": "⭐⭐", "masterball": "⭐⭐⭐",
    "iv_reroll_all": "⭐⭐⭐", "bp_jackpot": "⭐⭐⭐⭐",
    "iv_reroll_one": "⭐⭐⭐⭐", "shiny_egg": "⭐⭐⭐⭐⭐",
    "shiny_spawn": "⭐⭐⭐⭐⭐",
}


async def gacha_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """'뽑기' 명령 — 가챠 메인 메뉴."""
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    bp = await get_bp(user_id)

    lines = [
        f"🎰 <b>BP 뽑기</b>",
        f"",
        f"{icon_emoji('coin')} 보유 BP: <b>{bp}</b>",
        f"💸 1회 비용: <b>{config.GACHA_COST} BP</b>",
        f"",
        f"📋 <b>보상 목록:</b>",
    ]
    for prob, key, name, emo in config.GACHA_TABLE:
        pct = f"{prob*100:.0f}%"
        lines.append(f"  {emo} {name} — {pct}")

    lines.append("")

    buttons = []
    if bp >= config.GACHA_COST:
        buttons.append([
            InlineKeyboardButton("🎰 1회 뽑기", callback_data="gacha_pull_1"),
        ])
        if bp >= config.GACHA_COST * 5:
            buttons.append([
                InlineKeyboardButton("🎰 5연차 뽑기", callback_data="gacha_pull_5"),
            ])
    else:
        lines.append("⚠️ BP가 부족합니다!")

    markup = InlineKeyboardMarkup(buttons) if buttons else None
    try:
        with open(_IMG_NORMAL, "rb") as f:
            await update.message.reply_photo(
                photo=InputFile(f),
                caption="\n".join(lines),
                reply_markup=markup,
                parse_mode="HTML",
            )
    except Exception:
        logger.warning("가챠 이미지 전송 실패, 텍스트로 대체")
        await update.message.reply_text("\n".join(lines), reply_markup=markup, parse_mode="HTML")


async def gacha_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """가챠 콜백 처리."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if data == "gacha_pull_1":
        await _do_pull(query, user_id, 1)
    elif data == "gacha_pull_5":
        await _do_pull(query, user_id, 5)
    elif data.startswith("gacha_again"):
        # 다시 뽑기
        count = int(data.split("_")[-1]) if data.split("_")[-1].isdigit() else 1
        await _do_pull(query, user_id, count)


async def _do_pull(query, user_id: int, count: int):
    """뽑기 실행 (1회 또는 5회)."""
    from services.gacha_service import roll_gacha

    results = []
    for _ in range(count):
        r = await roll_gacha(user_id)
        if not r["success"]:
            if results:
                break  # 이미 일부 뽑았으면 결과 표시
            await query.edit_message_text(f"❌ {r['error']}")
            return
        results.append(r)

    if not results:
        return

    # 결과 표시
    bp_after = results[-1]["bp_after"]

    if count == 1:
        r = results[0]
        emo, reaction = _TIER_EFFECT.get(r["result_key"], ("🎁", "!"))
        stars = _TIER_STARS.get(r["result_key"], "⭐")

        lines = [
            "🎰 <b>뽑기 결과!</b>",
            "",
            f"  {stars}",
            f"  {emo} <b>{r['display_name']}</b>",
            f"  {reaction}",
            "",
            f"  📝 {r['detail']}",
            "",
            f"{icon_emoji('coin')} 남은 BP: <b>{bp_after}</b>",
        ]
    else:
        lines = [f"🎰 <b>{len(results)}연차 뽑기 결과!</b>", ""]
        for i, r in enumerate(results, 1):
            emo = r["emoji"]
            stars = _TIER_STARS.get(r["result_key"], "⭐")
            lines.append(f"  {i}. {emo} {r['display_name']} — {r['detail']}")
        lines.append("")
        lines.append(f"{icon_emoji('coin')} 남은 BP: <b>{bp_after}</b>")

    # 대박 여부 판정
    is_jackpot = any(r["result_key"] in _JACKPOT_TIERS for r in results)
    img_path = _IMG_GOLDEN if is_jackpot else _IMG_NORMAL

    # 다시 뽑기 버튼
    buttons = []
    if bp_after >= config.GACHA_COST:
        row = [InlineKeyboardButton("🎰 1회 더!", callback_data="gacha_again_1")]
        if bp_after >= config.GACHA_COST * 5:
            row.append(InlineKeyboardButton("🎰 5연차!", callback_data="gacha_again_5"))
        buttons.append(row)

    markup = InlineKeyboardMarkup(buttons) if buttons else None

    # 기존 메시지 버튼 제거 후 새 사진 메시지 전송
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    try:
        with open(img_path, "rb") as f:
            await query.message.reply_photo(
                photo=InputFile(f),
                caption="\n".join(lines),
                reply_markup=markup,
                parse_mode="HTML",
            )
    except Exception:
        logger.warning("가챠 결과 이미지 전송 실패, 텍스트로 대체")
        await query.message.reply_text("\n".join(lines), reply_markup=markup, parse_mode="HTML")


# ─── 아이템 목록/사용 ────────────────────────────────────

_ITEM_NAMES = {
    "iv_reroll_all": ("🔄 개체값 재설정권", "보유 포켓몬 1마리의 IV 6종을 전부 리롤합니다."),
    "iv_reroll_one": ("🎯 IV 선택 리롤", "보유 포켓몬 1마리의 특정 IV 1종을 선택해서 리롤합니다."),
}


async def item_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """'아이템' 명령 — 보유 아이템 목록."""
    if not update.effective_user:
        return
    user_id = update.effective_user.id

    items = await queries.get_all_user_items(user_id)
    shiny_tickets = await queries.get_shiny_spawn_tickets(user_id)
    eggs = await queries.get_user_eggs(user_id)

    lines = ["🎒 <b>아이템 가방</b>", ""]

    has_items = False

    for item in items:
        key = item["item_type"]
        qty = item["quantity"]
        if qty <= 0:
            continue
        name_info = _ITEM_NAMES.get(key)
        if name_info:
            lines.append(f"  {name_info[0]} ×{qty}")
            has_items = True

    if shiny_tickets > 0:
        lines.append(f"  ✨ 이로치 강스권 ×{shiny_tickets}")
        has_items = True

    if eggs:
        lines.append("")
        lines.append("🥚 <b>부화 대기 중인 알:</b>")
        now = config.get_kst_now()
        for egg in eggs:
            remaining = egg["hatches_at"] - now
            hours = int(remaining.total_seconds() // 3600)
            mins = int((remaining.total_seconds() % 3600) // 60)
            if remaining.total_seconds() <= 0:
                time_str = "곧 부화!"
            else:
                time_str = f"{hours}시간 {mins}분 후"
            rarity_labels = {"common": "일반", "rare": "레어", "epic": "에픽",
                             "legendary": "전설", "ultra_legendary": "초전설"}
            rarity_name = rarity_labels.get(egg["rarity"], egg["rarity"])
            lines.append(f"  🥚 ??? ({rarity_name}) — {time_str}")
        has_items = True

    if not has_items:
        lines.append("  (비어있음)")
        lines.append("")
        lines.append("💡 DM에서 '뽑기'를 입력해서 아이템을 얻으세요!")
    else:
        lines.append("")

    # 사용 가능한 아이템 버튼
    buttons = []
    for item in items:
        key = item["item_type"]
        if item["quantity"] > 0 and key in _ITEM_NAMES:
            label = _ITEM_NAMES[key][0].split(" ", 1)[1]  # 이모지 제거
            buttons.append([InlineKeyboardButton(f"사용: {label}", callback_data=f"item_use_{key}")])

    markup = InlineKeyboardMarkup(buttons) if buttons else None
    await update.message.reply_text("\n".join(lines), reply_markup=markup, parse_mode="HTML")


async def item_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """아이템 사용 콜백."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if data == "item_use_iv_reroll_all":
        await _start_iv_reroll(query, user_id, "all")
    elif data == "item_use_iv_reroll_one":
        await _start_iv_reroll(query, user_id, "one")
    elif data.startswith("ivr_pk_"):
        # 포켓몬 선택 (iv reroll)
        parts = data.split("_")  # ivr_pk_{mode}_{instance_id}
        mode = parts[2]
        instance_id = int(parts[3])
        if mode == "all":
            await _execute_iv_reroll_all(query, user_id, instance_id)
        else:
            await _show_stat_selection(query, user_id, instance_id)
    elif data.startswith("ivr_st_"):
        # 스탯 선택 (iv reroll one)
        parts = data.split("_")  # ivr_st_{instance_id}_{stat_key}
        instance_id = int(parts[2])
        stat_key = f"iv_{parts[3]}"
        if parts[3] == "spdef":
            stat_key = "iv_spdef"
        await _execute_iv_reroll_one(query, user_id, instance_id, stat_key)
    elif data.startswith("ivr_pg_"):
        # 페이지네이션
        parts = data.split("_")  # ivr_pg_{mode}_{page}
        mode = parts[2]
        page = int(parts[3])
        await _show_pokemon_list(query, user_id, mode, page)


PAGE_SIZE = 8


async def _start_iv_reroll(query, user_id: int, mode: str):
    """IV 리롤 — 포켓몬 선택 화면."""
    item_key = f"iv_reroll_{mode}"
    qty = await queries.get_user_item(user_id, item_key)
    if qty <= 0:
        await query.edit_message_text("❌ 아이템이 부족합니다.")
        return
    await _show_pokemon_list(query, user_id, mode, 0)


async def _show_pokemon_list(query, user_id: int, mode: str, page: int):
    """포켓몬 선택 리스트 (페이지네이션)."""
    pokemon_list = await queries.get_user_pokemon_list(user_id)
    if not pokemon_list:
        await query.edit_message_text("❌ 보유 중인 포켓몬이 없습니다.")
        return

    total = len(pokemon_list)
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total)
    page_list = pokemon_list[start:end]

    mode_label = "개체값 재설정 (6종 전부)" if mode == "all" else "IV 선택 리롤 (1종)"
    lines = [f"🔄 <b>{mode_label}</b>", "", "포켓몬을 선택하세요:", ""]

    buttons = []
    for p in page_list:
        shiny = "✨" if p.get("is_shiny") else ""
        iv_sum = sum(p.get(k, 0) or 0 for k in config.IV_STAT_KEYS)
        label = f"{shiny}{p['name_ko']} (IV합:{iv_sum})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"ivr_pk_{mode}_{p['id']}")])

    # 페이지 네비
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ 이전", callback_data=f"ivr_pg_{mode}_{page-1}"))
    if end < total:
        nav.append(InlineKeyboardButton("다음 ▶", callback_data=f"ivr_pg_{mode}_{page+1}"))
    if nav:
        buttons.append(nav)

    lines.append(f"({start+1}~{end} / {total}마리)")

    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")


async def _execute_iv_reroll_all(query, user_id: int, instance_id: int):
    """개체값 재설정권 사용 — 6종 전부 리롤."""
    ok = await queries.use_user_item(user_id, "iv_reroll_all")
    if not ok:
        await query.edit_message_text("❌ 아이템이 부족합니다.")
        return

    # 해당 포켓몬 정보 조회
    pool = await queries.get_db()
    poke = await pool.fetchrow(
        """SELECT up.*, pm.name_ko FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.id = $1 AND up.user_id = $2 AND up.is_active = 1""",
        instance_id, user_id)
    if not poke:
        await query.edit_message_text("❌ 포켓몬을 찾을 수 없습니다.")
        return

    # 기존 IV
    old_ivs = {k: poke[k] or 0 for k in config.IV_STAT_KEYS}
    old_sum = sum(old_ivs.values())

    # 새 IV 생성
    from utils.battle_calc import generate_ivs
    is_shiny = bool(poke.get("is_shiny"))
    new_ivs = generate_ivs(is_shiny=is_shiny)
    new_sum = sum(new_ivs.values())

    await queries.update_pokemon_all_ivs(instance_id, new_ivs)

    shiny = "✨" if is_shiny else ""
    lines = [
        f"🔄 <b>개체값 재설정 완료!</b>",
        f"",
        f"대상: {shiny}<b>{poke['name_ko']}</b>",
        f"",
    ]
    for k in config.IV_STAT_KEYS:
        name = config.IV_STAT_NAMES[k]
        old_v = old_ivs[k]
        new_v = new_ivs[k]
        diff = new_v - old_v
        arrow = "🔺" if diff > 0 else ("🔻" if diff < 0 else "➖")
        lines.append(f"  {name}: {old_v} → <b>{new_v}</b> {arrow}")

    diff_total = new_sum - old_sum
    arrow_total = "🔺" if diff_total > 0 else ("🔻" if diff_total < 0 else "➖")
    lines.append(f"")
    lines.append(f"  합계: {old_sum} → <b>{new_sum}</b> {arrow_total}")

    await query.edit_message_text("\n".join(lines), parse_mode="HTML")


async def _show_stat_selection(query, user_id: int, instance_id: int):
    """IV 선택 리롤 — 스탯 선택 화면."""
    pool = await queries.get_db()
    poke = await pool.fetchrow(
        """SELECT up.*, pm.name_ko FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.id = $1 AND up.user_id = $2 AND up.is_active = 1""",
        instance_id, user_id)
    if not poke:
        await query.edit_message_text("❌ 포켓몬을 찾을 수 없습니다.")
        return

    shiny = "✨" if poke.get("is_shiny") else ""
    lines = [
        f"🎯 <b>IV 선택 리롤</b>",
        f"대상: {shiny}<b>{poke['name_ko']}</b>",
        f"",
        f"리롤할 스탯을 선택하세요:",
    ]

    buttons = []
    for k in config.IV_STAT_KEYS:
        name = config.IV_STAT_NAMES[k]
        val = poke[k] or 0
        # callback에서 iv_ 접두사 제거
        short_key = k.replace("iv_", "")
        buttons.append([InlineKeyboardButton(
            f"{name}: {val}", callback_data=f"ivr_st_{instance_id}_{short_key}")])

    await query.edit_message_text("\n".join(lines),
                                  reply_markup=InlineKeyboardMarkup(buttons),
                                  parse_mode="HTML")


async def _execute_iv_reroll_one(query, user_id: int, instance_id: int, stat_key: str):
    """IV 선택 리롤 실행."""
    if stat_key not in config.IV_STAT_KEYS:
        await query.edit_message_text("❌ 잘못된 스탯입니다.")
        return

    ok = await queries.use_user_item(user_id, "iv_reroll_one")
    if not ok:
        await query.edit_message_text("❌ 아이템이 부족합니다.")
        return

    pool = await queries.get_db()
    poke = await pool.fetchrow(
        """SELECT up.*, pm.name_ko FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.id = $1 AND up.user_id = $2 AND up.is_active = 1""",
        instance_id, user_id)
    if not poke:
        await query.edit_message_text("❌ 포켓몬을 찾을 수 없습니다.")
        return

    old_val = poke[stat_key] or 0
    is_shiny = bool(poke.get("is_shiny"))
    low = config.IV_SHINY_MIN if is_shiny else config.IV_MIN
    new_val = random.randint(low, config.IV_MAX)

    await queries.update_pokemon_iv(instance_id, stat_key, new_val)

    stat_name = config.IV_STAT_NAMES[stat_key]
    diff = new_val - old_val
    arrow = "🔺" if diff > 0 else ("🔻" if diff < 0 else "➖")
    shiny = "✨" if is_shiny else ""

    lines = [
        f"🎯 <b>IV 선택 리롤 완료!</b>",
        f"",
        f"대상: {shiny}<b>{poke['name_ko']}</b>",
        f"",
        f"  {stat_name}: {old_val} → <b>{new_val}</b> {arrow}",
    ]

    await query.edit_message_text("\n".join(lines), parse_mode="HTML")
