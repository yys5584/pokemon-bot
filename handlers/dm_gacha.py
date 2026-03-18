"""DM 가챠 (뽑기) + 아이템 사용 핸들러."""

import asyncio
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

# 유저별 가챠 진행 중 락 (중복 뽑기 방지)
_gacha_lock: dict[int, float] = {}
_GACHA_LOCK_DURATION = 15  # 초

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

# 일반 힌트 멘트 (랜덤) — 이미지 캡션
_HINT_NORMAL = [
    "🔮 구슬이 잔잔하게 빛납니다...\n\n결과를 확인하는 중...",
    "🔮 피카츄가 고개를 갸웃합니다...\n\n운명의 구슬을 들여다보는 중...",
    "🔮 구슬 속에 잔잔한 빛이 맴돕니다...\n\n결과를 확인하는 중...",
    "🔮 피카츄가 무표정하게 바라봅니다...\n\n운명의 구슬을 들여다보는 중...",
    "🔮 구슬이 희미하게 반짝입니다...\n\n결과를 확인하는 중...",
]

# 대박 힌트 멘트 (랜덤) — 이미지 캡션
_HINT_JACKPOT = [
    "🔮 구슬이 미친듯이 빛나고 있습니다...!!\n\n뭔가 심상치 않습니다...",
    "🔮 피카츄가 눈을 크게 뜨고 있습니다...!!\n\n뭔가 심상치 않습니다...",
    "🔮 뒤에서 무언가의 기척이...?!\n\n뭔가 심상치 않습니다...",
    "🔮 심상치 않은 기운이 감돕니다...!!\n\n뭔가 심상치 않습니다...",
    "🔮 구슬에서 무지개빛이 터져나옵니다...!!\n\n뭔가 심상치 않습니다...",
]

_GACHA_DELAY = 10  # 힌트 → 결과 딜레이 (초)

# 아이템 상세 가이드
_ITEM_GUIDE = {
    "bp_refund": "",
    "hyperball": "💡 하이퍼볼: 야생 포획 시 사용 (포획률 ↑↑)",
    "masterball": "💡 마스터볼: 야생 포획 시 사용 (100% 포획)",
    "iv_reroll_all": "💡 개체값 재설정권: DM에서 '아이템' → 포켓몬 선택 → IV 6종 전부 랜덤 리롤!",
    "bp_jackpot": "",
    "iv_reroll_one": "💡 IV 선택 리롤: DM에서 '아이템' → 포켓몬 선택 → 원하는 스탯 1개만 골라서 리롤!",
    "shiny_egg": "💡 이로치 알: 24시간 후 자동 부화 → 확정 이로치! DM에서 '아이템'으로 확인 가능",
    "shiny_spawn": "💡 이로치 강스권: 채팅방에서 '강스' 또는 '이로치강스' 입력 → 확정 이로치 출현!",
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
    """뽑기 실행 (1회 또는 5회).

    플로우: 기존 버튼 제거 → 힌트 멘트 + 이미지 → 상세 결과 텍스트 + 다시뽑기 버튼
    """
    import time as _time
    from services.gacha_service import roll_gacha

    # 중복 뽑기 방지 (10초 딜레이 동안 재클릭 차단)
    now = _time.monotonic()
    last = _gacha_lock.get(user_id)
    if last is not None and (now - last) < _GACHA_LOCK_DURATION:
        try:
            await query.answer("뽑기 결과를 확인 중입니다! 잠시만 기다려주세요.", show_alert=True)
        except Exception:
            pass
        return
    _gacha_lock[user_id] = now

    result_sent = False
    try:
        results = []
        for _ in range(count):
            r = await roll_gacha(user_id)
            if not r["success"]:
                if results:
                    break  # 이전 결과는 표시
                try:
                    await query.edit_message_text(f"❌ {r['error']}")
                except Exception:
                    try:
                        await query.message.reply_text(f"❌ {r['error']}")
                    except Exception:
                        pass
                return
            results.append(r)

        if not results:
            return

        # ① 기존 메시지 버튼 제거
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

        # ② 대박 여부 판정
        is_jackpot = any(r["result_key"] in _JACKPOT_TIERS for r in results)
        img_path = _IMG_GOLDEN if is_jackpot else _IMG_NORMAL
        hint = random.choice(_HINT_JACKPOT if is_jackpot else _HINT_NORMAL)

        # ③ 힌트 멘트 + 이미지 전송
        try:
            with open(img_path, "rb") as f:
                await query.message.reply_photo(
                    photo=InputFile(f),
                    caption=f"<b>{hint}</b>",
                    parse_mode="HTML",
                )
        except Exception:
            logger.warning("가챠 힌트 이미지 전송 실패")
            try:
                await query.message.reply_text(f"<b>{hint}</b>", parse_mode="HTML")
            except Exception:
                pass

        # 10초 대기 — 긴장감 연출
        await asyncio.sleep(_GACHA_DELAY)

        # ④ 상세 결과 텍스트
        bp_after = await get_bp(user_id)  # 최신 BP 조회 (중간 실패 대비)

        if len(results) == 1 and count == 1:
            r = results[0]
            emo, reaction = _TIER_EFFECT.get(r["result_key"], ("🎁", "!"))
            stars = _TIER_STARS.get(r["result_key"], "⭐")
            guide = _ITEM_GUIDE.get(r["result_key"], "")

            lines = [
                f"🎰 <b>뽑기 결과!</b>",
                "",
                f"  {stars}",
                f"  {emo} <b>{r['display_name']}</b>",
                f"  {reaction}",
                "",
                f"  📝 {r['detail']}",
            ]
            if guide:
                lines.append("")
                lines.append(f"  {guide}")
            lines.append("")
            lines.append(f"{icon_emoji('coin')} 남은 BP: <b>{bp_after}</b>")
        else:
            pulled = len(results)
            failed = count - pulled
            lines = [f"🎰 <b>{pulled}연차 뽑기 결과!</b>", ""]
            if failed > 0:
                lines.append(f"⚠️ {count}회 중 {pulled}회만 성공 (BP 부족으로 {failed}회 중단)")
                lines.append("")
            guides = []
            for i, r in enumerate(results, 1):
                emo = r["emoji"]
                lines.append(f"  {i}. {emo} {r['display_name']} — {r['detail']}")
                guide = _ITEM_GUIDE.get(r["result_key"], "")
                if guide and guide not in guides:
                    guides.append(guide)
            lines.append("")
            if guides:
                for g in guides:
                    lines.append(f"  {g}")
                lines.append("")
            lines.append(f"{icon_emoji('coin')} 남은 BP: <b>{bp_after}</b>")

        # ⑤ 다시 뽑기 버튼
        buttons = []
        if bp_after >= config.GACHA_COST:
            row = [InlineKeyboardButton("🎰 1회 더!", callback_data="gacha_again_1")]
            if bp_after >= config.GACHA_COST * 5:
                row.append(InlineKeyboardButton("🎰 5연차!", callback_data="gacha_again_5"))
            buttons.append(row)

        markup = InlineKeyboardMarkup(buttons) if buttons else None
        try:
            await query.message.reply_text("\n".join(lines), reply_markup=markup, parse_mode="HTML")
            result_sent = True
        except Exception:
            try:
                await query.message.reply_text("\n".join(lines), reply_markup=markup)
                result_sent = True
            except Exception:
                logger.exception(f"[Gacha] 결과 메시지 전송 실패 (user={user_id})")
    except Exception:
        logger.exception(f"[Gacha] _do_pull 전체 예외 (user={user_id}, count={count})")
        if not result_sent:
            try:
                await query.message.reply_text(
                    "⚠️ 뽑기 처리 중 오류가 발생했습니다.\n"
                    "보상은 정상 지급되었을 수 있습니다. '아이템'과 '상태창'을 확인해주세요."
                )
            except Exception:
                pass
    finally:
        _gacha_lock.pop(user_id, None)


# ─── 아이템 목록/사용 ────────────────────────────────────

_ITEM_NAMES = {
    "iv_reroll_all": ("🔄 개체값 재설정권", "보유 포켓몬 1마리의 IV 6종을 전부 리롤합니다."),
    "iv_reroll_one": ("🎯 IV 선택 리롤", "보유 포켓몬 1마리의 특정 IV 1종을 선택해서 리롤합니다."),
    "gacha_ticket_5": ("🎰 5연뽑기권", "BP 차감 없이 뽑기 5회를 실행합니다."),
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

    iv_stones = await queries.get_iv_stones(user_id)
    uni_frags = await queries.get_universal_fragments(user_id)
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

    if iv_stones > 0:
        lines.append(f"  💠 IV스톤 ×{iv_stones}")
        has_items = True

    if uni_frags > 0:
        lines.append(f"  🧩 만능 조각 ×{uni_frags}")
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

    if iv_stones > 0:
        buttons.append([InlineKeyboardButton(f"사용: IV스톤 ({iv_stones}개)", callback_data="ivstone_start")])

    buttons.append([InlineKeyboardButton("❌ 닫기", callback_data="item_close")])
    await update.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")


async def item_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """아이템 사용 콜백."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if data == "item_close":
        try:
            await query.edit_message_text("닫았습니다.")
        except Exception:
            pass
        return

    # IV 스톤 콜백들
    if data == "ivstone_start":
        await _ivstone_show_pokemon(query, user_id, 0, "all")
        return
    elif data.startswith("ivstone_ft_"):
        # ivstone_ft_{rarity}_{page}
        parts = data.split("_")
        rarity_filter = parts[2]
        page = int(parts[3]) if len(parts) > 3 else 0
        await _ivstone_show_pokemon(query, user_id, page, rarity_filter)
        return
    elif data.startswith("ivstone_pg_"):
        # ivstone_pg_{rarity}_{page}
        parts = data.split("_")
        if len(parts) >= 4:
            rarity_filter = parts[2]
            page = int(parts[3])
        else:
            rarity_filter = "all"
            page = int(parts[2])
        await _ivstone_show_pokemon(query, user_id, page, rarity_filter)
        return
    elif data.startswith("ivstone_pk_"):
        instance_id = int(data.split("_")[2])
        await _ivstone_show_stats(query, user_id, instance_id)
        return
    elif data.startswith("ivstone_st_"):
        parts = data.split("_")  # ivstone_st_{instance_id}_{stat_short}
        instance_id = int(parts[2])
        stat_short = parts[3]
        stat_key = f"iv_{stat_short}"
        if stat_short == "spdef":
            stat_key = "iv_spdef"
        await _ivstone_confirm(query, user_id, instance_id, stat_key)
        return
    elif data.startswith("ivstone_yes_"):
        parts = data.split("_")  # ivstone_yes_{instance_id}_{stat_short}
        instance_id = int(parts[2])
        stat_short = parts[3]
        stat_key = f"iv_{stat_short}"
        if stat_short == "spdef":
            stat_key = "iv_spdef"
        await _ivstone_execute(query, user_id, instance_id, stat_key)
        return

    if data == "item_use_gacha_ticket_5":
        await _use_gacha_ticket_5(query, user_id)
        return
    elif data == "item_use_iv_reroll_all":
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
    elif data.startswith("ivr_ft_"):
        # 등급 필터
        parts = data.split("_")  # ivr_ft_{mode}_{rarity}_{page}
        mode = parts[2]
        rarity_filter = parts[3]
        page = int(parts[4]) if len(parts) > 4 else 0
        await _show_pokemon_list(query, user_id, mode, page, rarity_filter)
    elif data.startswith("ivr_pg_"):
        # 페이지네이션 (ivr_pg_{mode}_{rarity}_{page} 또는 레거시 ivr_pg_{mode}_{page})
        parts = data.split("_")
        mode = parts[2]
        if len(parts) >= 5:
            rarity_filter = parts[3]
            page = int(parts[4])
        else:
            rarity_filter = "all"
            page = int(parts[3])
        await _show_pokemon_list(query, user_id, mode, page, rarity_filter)


async def _use_gacha_ticket_5(query, user_id: int):
    """5연뽑기권 사용 — BP 차감 없이 가챠 5회. 일반 뽑기와 동일한 연출."""
    import time as _time
    from services.gacha_service import roll_gacha

    # 중복 사용 방지
    now = _time.monotonic()
    last = _gacha_lock.get(user_id)
    if last is not None and (now - last) < _GACHA_LOCK_DURATION:
        try:
            await query.answer("뽑기 결과를 확인 중입니다! 잠시만 기다려주세요.", show_alert=True)
        except Exception:
            pass
        return
    _gacha_lock[user_id] = now

    result_sent = False
    try:
        qty = await queries.get_user_item(user_id, "gacha_ticket_5")
        if qty <= 0:
            await query.edit_message_text("❌ 5연뽑기권이 없습니다.")
            return

        # 아이템 차감
        ok = await queries.use_user_item(user_id, "gacha_ticket_5", 1)
        if not ok:
            await query.edit_message_text("❌ 아이템 사용에 실패했습니다.")
            return

        # ① 버튼 제거
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

        # ② 5회 뽑기 (free=True) — 결과 먼저 확보
        results = []
        for _ in range(config.GACHA_MULTI_TICKET_PULLS):
            r = await roll_gacha(user_id, free=True)
            if r["success"]:
                results.append(r)

        if not results:
            await query.message.reply_text("⚠️ 뽑기 처리 중 오류가 발생했습니다.")
            return

        # ③ 대박 여부 판정 → 이미지 + 힌트 멘트
        is_jackpot = any(r["result_key"] in _JACKPOT_TIERS for r in results)
        img_path = _IMG_GOLDEN if is_jackpot else _IMG_NORMAL
        hint = random.choice(_HINT_JACKPOT if is_jackpot else _HINT_NORMAL)

        try:
            with open(img_path, "rb") as f:
                await query.message.reply_photo(
                    photo=InputFile(f),
                    caption=f"<b>{hint}</b>",
                    parse_mode="HTML",
                )
        except Exception:
            logger.warning("5연뽑기권 힌트 이미지 전송 실패")
            try:
                await query.message.reply_text(f"<b>{hint}</b>", parse_mode="HTML")
            except Exception:
                pass

        # ④ 10초 대기 — 긴장감 연출
        await asyncio.sleep(_GACHA_DELAY)

        # ⑤ 상세 결과
        bp_after = await get_bp(user_id)

        lines = [f"🎰 <b>5연뽑기권 결과!</b> (무료)", ""]
        guides = []
        for i, r in enumerate(results, 1):
            emo = r["emoji"]
            lines.append(f"  {i}. {emo} {r['display_name']} — {r['detail']}")
            guide = _ITEM_GUIDE.get(r["result_key"], "")
            if guide and guide not in guides:
                guides.append(guide)
        lines.append("")
        if guides:
            for g in guides:
                lines.append(f"  {g}")
            lines.append("")

        remaining_tickets = await queries.get_user_item(user_id, "gacha_ticket_5")
        lines.append(f"{icon_emoji('coin')} 남은 BP: <b>{bp_after:,}</b>")
        if remaining_tickets > 0:
            lines.append(f"🎰 남은 5연뽑기권: {remaining_tickets}개")

        await query.message.reply_text("\n".join(lines), parse_mode="HTML")
        result_sent = True
    except Exception:
        logger.exception(f"[Gacha] 5연뽑기권 예외 (user={user_id})")
        if not result_sent:
            try:
                await query.message.reply_text(
                    "⚠️ 뽑기 처리 중 오류가 발생했습니다.\n"
                    "보상은 정상 지급되었을 수 있습니다. '아이템'과 '상태창'을 확인해주세요."
                )
            except Exception:
                pass
    finally:
        _gacha_lock.pop(user_id, None)


PAGE_SIZE = 8


async def _start_iv_reroll(query, user_id: int, mode: str):
    """IV 리롤 — 포켓몬 선택 화면."""
    item_key = f"iv_reroll_{mode}"
    qty = await queries.get_user_item(user_id, item_key)
    if qty <= 0:
        await query.edit_message_text("❌ 아이템이 부족합니다.")
        return
    await _show_pokemon_list(query, user_id, mode, 0)


_RARITY_FILTERS = [
    ("all", "전체"),
    ("UL", "울트라전설"),
    ("L", "전설"),
    ("E", "에픽"),
    ("R", "레어"),
    ("C", "커먼"),
]
_RARITY_KEY_MAP = {
    "UL": "ultra_legendary",
    "L": "legendary",
    "E": "epic",
    "R": "rare",
    "C": "common",
}


async def _show_pokemon_list(query, user_id: int, mode: str, page: int, rarity_filter: str = "all"):
    """포켓몬 선택 리스트 (페이지네이션 + 등급필터)."""
    pokemon_list = await queries.get_user_pokemon_list(user_id)
    if not pokemon_list:
        await query.edit_message_text("❌ 보유 중인 포켓몬이 없습니다.")
        return

    # 등급 필터 적용 (약어 → 실제 rarity 키 변환)
    actual_rarity = _RARITY_KEY_MAP.get(rarity_filter)
    if actual_rarity:
        pokemon_list = [p for p in pokemon_list if p.get("rarity") == actual_rarity]

    total = len(pokemon_list)
    if total == 0:
        # 필터 결과 없을 때 — 필터 버튼만 표시
        mode_label = "개체값 재설정 (6종 전부)" if mode == "all" else "IV 선택 리롤 (1종)"
        lines = [f"🔄 <b>{mode_label}</b>", "", "해당 등급의 포켓몬이 없습니다.", ""]
        filter_row = []
        for fkey, flabel in _RARITY_FILTERS:
            mark = "▸" if fkey == rarity_filter else ""
            filter_row.append(InlineKeyboardButton(f"{mark}{flabel}", callback_data=f"ivr_ft_{mode}_{fkey}_0"))
        # 3개씩 두 줄로
        buttons = [filter_row[:3], filter_row[3:]]
        buttons.append([InlineKeyboardButton("❌ 닫기", callback_data="item_close")])
        await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
        return

    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total)
    page_list = pokemon_list[start:end]

    mode_label = "개체값 재설정 (6종 전부)" if mode == "all" else "IV 선택 리롤 (1종)"
    lines = [f"🔄 <b>{mode_label}</b>", "", "포켓몬을 선택하세요:", ""]

    # 등급 필터 버튼
    filter_row = []
    for fkey, flabel in _RARITY_FILTERS:
        mark = "▸" if fkey == rarity_filter else ""
        filter_row.append(InlineKeyboardButton(f"{mark}{flabel}", callback_data=f"ivr_ft_{mode}_{fkey}_0"))

    buttons = [filter_row[:3], filter_row[3:]]

    for p in page_list:
        shiny = "✨" if p.get("is_shiny") else ""
        iv_sum = sum(p.get(k, 0) or 0 for k in config.IV_STAT_KEYS)
        label = f"{shiny}{p['name_ko']} (IV합:{iv_sum})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"ivr_pk_{mode}_{p['id']}")])

    # 페이지 네비
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ 이전", callback_data=f"ivr_pg_{mode}_{rarity_filter}_{page-1}"))
    if end < total:
        nav.append(InlineKeyboardButton("다음 ▶", callback_data=f"ivr_pg_{mode}_{rarity_filter}_{page+1}"))
    if nav:
        buttons.append(nav)

    filter_label = dict(_RARITY_FILTERS).get(rarity_filter, "전체")
    lines.append(f"({start+1}~{end} / {total}마리) [{filter_label}]")

    buttons.append([InlineKeyboardButton("❌ 닫기", callback_data="item_close")])
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


# ─── IV 스톤 UI ──────────────────────────────────────────

_IVSTONE_PAGE_SIZE = 8


async def _ivstone_show_pokemon(query, user_id: int, page: int, rarity_filter: str = "all"):
    """IV 스톤 사용 — 포켓몬 선택 (등급 필터 + 페이지네이션)."""
    stones = await queries.get_iv_stones(user_id)
    if stones <= 0:
        await query.edit_message_text("❌ IV스톤이 없습니다.")
        return

    pokemon_list = await queries.get_user_pokemon_list(user_id)
    # IV가 31 미만인 스탯이 1개라도 있는 포켓몬만
    eligible = []
    for p in pokemon_list:
        ivs = [p.get(k) for k in config.IV_STAT_KEYS]
        if any((v or 0) < config.IV_MAX for v in ivs):
            eligible.append(p)

    if not eligible:
        await query.edit_message_text("❌ IV를 강화할 수 있는 포켓몬이 없습니다. (모두 최대)")
        return

    # 등급 필터 적용
    actual_rarity = _RARITY_KEY_MAP.get(rarity_filter)
    if actual_rarity:
        eligible = [p for p in eligible if p.get("rarity") == actual_rarity]

    # 등급 필터 버튼 (항상 표시)
    filter_row = []
    for fkey, flabel in _RARITY_FILTERS:
        mark = "▸" if fkey == rarity_filter else ""
        filter_row.append(InlineKeyboardButton(f"{mark}{flabel}", callback_data=f"ivstone_ft_{fkey}_0"))
    buttons = [filter_row[:3], filter_row[3:]]

    total = len(eligible)
    if total == 0:
        lines = [f"💠 <b>IV스톤 사용</b> (보유: {stones}개)", "", "해당 등급의 포켓몬이 없습니다.", ""]
        buttons.append([InlineKeyboardButton("❌ 닫기", callback_data="item_close")])
        await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
        return

    total_pages = (total + _IVSTONE_PAGE_SIZE - 1) // _IVSTONE_PAGE_SIZE
    page = max(0, min(page, total_pages - 1))
    start = page * _IVSTONE_PAGE_SIZE
    end = min(start + _IVSTONE_PAGE_SIZE, total)
    page_items = eligible[start:end]

    filter_label = dict(_RARITY_FILTERS).get(rarity_filter, "전체")
    lines = [
        f"💠 <b>IV스톤 사용</b> (보유: {stones}개)",
        f"IV를 강화할 포켓몬을 선택하세요.",
        f"",
    ]

    for p in page_items:
        iv_sum = sum(p.get(k) or 0 for k in config.IV_STAT_KEYS)
        grade = _iv_grade_letter(iv_sum)
        shiny = "✨" if p.get("is_shiny") else ""
        name = p.get("name_ko", p.get("name", "???"))
        buttons.append([InlineKeyboardButton(
            f"{shiny}{name} [{grade}]{iv_sum}",
            callback_data=f"ivstone_pk_{p['id']}"
        )])

    # 페이지네이션
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ 이전", callback_data=f"ivstone_pg_{rarity_filter}_{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton("다음 ▶", callback_data=f"ivstone_pg_{rarity_filter}_{page + 1}"))
    if nav:
        buttons.append(nav)

    lines.append(f"({start+1}~{end} / {total}마리) [{filter_label}]")
    buttons.append([InlineKeyboardButton("❌ 닫기", callback_data="item_close")])
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")


def _iv_grade_letter(total: int) -> str:
    for threshold, letter, _ in config.IV_GRADE_THRESHOLDS:
        if total >= threshold:
            return letter
    return "D"


async def _ivstone_show_stats(query, user_id: int, instance_id: int):
    """IV 스톤 — 스탯 선택."""
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
        f"💠 <b>IV스톤 — 스탯 선택</b>",
        f"",
        f"대상: {shiny}<b>{poke['name_ko']}</b>",
        f"강화할 스탯을 선택하세요. (+3, 최대 31)",
        f"",
    ]

    buttons = []
    for stat_key in config.IV_STAT_KEYS:
        val = poke.get(stat_key) or 0
        name = config.IV_STAT_NAMES[stat_key]
        short_key = stat_key.replace("iv_", "")
        if val >= config.IV_MAX:
            lines.append(f"  {name}: {val}/31 ✅ MAX")
        else:
            new_val = min(val + 3, config.IV_MAX)
            lines.append(f"  {name}: {val} → {new_val}")
            buttons.append([InlineKeyboardButton(
                f"{name} ({val}→{new_val})",
                callback_data=f"ivstone_st_{instance_id}_{short_key}"
            )])

    buttons.append([InlineKeyboardButton("◀️ 돌아가기", callback_data="ivstone_pg_0")])
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")


async def _ivstone_confirm(query, user_id: int, instance_id: int, stat_key: str):
    """IV 스톤 — 확인."""
    pool = await queries.get_db()
    poke = await pool.fetchrow(
        """SELECT up.*, pm.name_ko FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.id = $1 AND up.user_id = $2 AND up.is_active = 1""",
        instance_id, user_id)
    if not poke:
        await query.edit_message_text("❌ 포켓몬을 찾을 수 없습니다.")
        return

    val = poke.get(stat_key) or 0
    new_val = min(val + 3, config.IV_MAX)
    stat_name = config.IV_STAT_NAMES.get(stat_key, stat_key)
    shiny = "✨" if poke.get("is_shiny") else ""
    short_key = stat_key.replace("iv_", "")

    lines = [
        f"💠 <b>IV스톤 사용 확인</b>",
        f"",
        f"대상: {shiny}<b>{poke['name_ko']}</b>",
        f"스탯: {stat_name} {val} → <b>{new_val}</b>",
        f"",
        f"IV스톤 1개를 사용합니다. 진행할까요?",
    ]

    buttons = [
        [InlineKeyboardButton("✅ 사용", callback_data=f"ivstone_yes_{instance_id}_{short_key}"),
         InlineKeyboardButton("❌ 취소", callback_data=f"ivstone_pk_{instance_id}")],
    ]
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")


async def _ivstone_execute(query, user_id: int, instance_id: int, stat_key: str):
    """IV 스톤 적용."""
    result = await queries.apply_iv_stone(user_id, instance_id, stat_key)
    if not result:
        await query.edit_message_text("❌ IV스톤이 부족하거나 포켓몬을 찾을 수 없습니다.")
        return

    pool = await queries.get_db()
    poke = await pool.fetchrow(
        """SELECT pm.name_ko, up.is_shiny FROM user_pokemon up
           JOIN pokemon_master pm ON up.pokemon_id = pm.id
           WHERE up.id = $1""",
        instance_id)

    stat_name = config.IV_STAT_NAMES.get(stat_key, stat_key)
    new_val = result.get(stat_key, 0)
    iv_sum = sum(result.get(k) or 0 for k in config.IV_STAT_KEYS)
    grade = _iv_grade_letter(iv_sum)
    shiny = "✨" if (poke and poke.get("is_shiny")) else ""
    name = poke["name_ko"] if poke else "???"
    remaining = await queries.get_iv_stones(user_id)

    lines = [
        f"💠 <b>IV스톤 적용 완료!</b>",
        f"",
        f"대상: {shiny}<b>{name}</b>",
        f"  {stat_name}: → <b>{new_val}</b>",
        f"  총 IV: {iv_sum}/186 [{grade}]",
        f"",
        f"남은 IV스톤: {remaining}개",
    ]

    buttons = []
    if remaining > 0:
        buttons.append([InlineKeyboardButton("💠 계속 사용", callback_data="ivstone_start")])
    buttons.append([InlineKeyboardButton("❌ 닫기", callback_data="item_close")])
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
