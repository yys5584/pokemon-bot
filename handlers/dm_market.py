"""DM-only marketplace handler: browse, register, buy, cancel, search."""

import asyncio
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from database import queries
from services.market_service import create_listing, buy_listing, cancel_listing_for_user, calc_fee
from utils.battle_calc import iv_total

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────

def _iv_grade(total: int) -> str:
    grade, _ = config.get_iv_grade(total)
    return grade


def _iv_tag(p: dict) -> str:
    if p.get("iv_hp") is None:
        return ""
    total = iv_total(
        p.get("iv_hp"), p.get("iv_atk"), p.get("iv_def"),
        p.get("iv_spa"), p.get("iv_spdef"), p.get("iv_spd"),
    )
    return f" [{_iv_grade(total)}]"


def _listing_line(ml: dict) -> str:
    """Single-line listing summary."""
    shiny = "✨" if ml.get("is_shiny") else ""
    iv = _iv_tag(ml)
    return f"#{ml['id']} {ml['emoji']} {ml['pokemon_name']}{shiny}{iv} — {ml['price_bp']:,} BP"


RARITY_LABELS = {
    "": "전체",
    "common": "커먼",
    "rare": "레어",
    "epic": "에픽",
    "legendary": "전설",
    "ultra_legendary": "초전설",
}

IV_LABELS = {"": "전체", "S": "S", "A": "A", "B": "B"}


def _filter_label(rarity: str, iv_grade: str) -> str:
    """Build active filter display text."""
    parts = []
    if rarity:
        parts.append(RARITY_LABELS.get(rarity, rarity))
    if iv_grade:
        parts.append(f"IV {iv_grade}등급{'+' if iv_grade != 'D' else ''}")
    return " / ".join(parts) if parts else ""


def _build_listing_page(
    listings: list[dict], total: int, page: int, page_size: int,
    search_name: str | None = None,
    rarity: str = "", iv_grade: str = "",
) -> tuple[str, InlineKeyboardMarkup]:
    """Build listing display text + inline keyboard."""
    total_pages = max(1, (total + page_size - 1) // page_size)

    _help = (
        "\n\n📌 거래소 등록 [이름] [가격]"
        "\n📌 거래소 내꺼 → 취소 버튼"
        "\n📌 거래소 검색 [이름]"
    )

    filter_text = _filter_label(rarity, iv_grade)
    filter_suffix = f" [{filter_text}]" if filter_text else ""

    if not listings:
        text = f"🏪 거래소{filter_suffix}\n\n등록된 매물이 없습니다." + _help
        if search_name:
            text = f"🏪 거래소 검색: '{search_name}'{filter_suffix}\n\n검색 결과가 없습니다."
        # Still show filter buttons even when empty
        buttons = []
        buttons.append(_build_filter_row(rarity, iv_grade))
        return text, InlineKeyboardMarkup(buttons)

    header = f"🏪 거래소 ({total}개){filter_suffix}"
    if search_name:
        header = f"🔍 '{search_name}' 검색 ({total}건){filter_suffix}"

    lines = [header, ""]
    for ml in listings:
        lines.append(_listing_line(ml))
        lines.append(f"  판매자: {ml.get('seller_name', '???')}")

    lines.append(f"\n({page+1}/{total_pages} 페이지)")
    if page == 0 and not search_name and not rarity and not iv_grade:
        lines.append("\n📌 거래소 등록 [이름] [가격]")
        lines.append("📌 거래소 내꺼 → 취소 버튼")
        lines.append("📌 거래소 검색 [이름]")
    text = "\n".join(lines)

    # Filter row at top
    buttons = []
    buttons.append(_build_filter_row(rarity, iv_grade))

    # Buy buttons
    for ml in listings:
        shiny = "✨" if ml.get("is_shiny") else ""
        label = f"#{ml['id']} {ml['pokemon_name']}{shiny} {ml['price_bp']:,}BP 구매"
        buttons.append([InlineKeyboardButton(label, callback_data=f"mkt_buy_{ml['id']}")])

    # Pagination row
    nav = []
    fkey = f"r{rarity}_iv{iv_grade}"
    prefix = f"mkt_fp_{fkey}_" if (rarity or iv_grade) else "mkt_page_"
    if search_name:
        prefix = f"mkt_s_{search_name}_"
    if page > 0:
        nav.append(InlineKeyboardButton("◀ 이전", callback_data=f"{prefix}{page-1}"))
    nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="mkt_noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("다음 ▶", callback_data=f"{prefix}{page+1}"))
    if nav:
        buttons.append(nav)

    return text, InlineKeyboardMarkup(buttons)


def _build_filter_row(active_rarity: str = "", active_iv: str = "") -> list[InlineKeyboardButton]:
    """Build a row of filter buttons."""
    rarity_label = RARITY_LABELS.get(active_rarity, "등급") if active_rarity else "등급"
    iv_label = f"IV: {active_iv}" if active_iv else "IV"
    reset = []
    if active_rarity or active_iv:
        reset = [InlineKeyboardButton("초기화", callback_data="mkt_fr")]
    return [
        InlineKeyboardButton(f"📋 {rarity_label}", callback_data=f"mkt_fmenu_r_{active_iv}"),
        InlineKeyboardButton(f"📊 {iv_label}", callback_data=f"mkt_fmenu_iv_{active_rarity}"),
    ] + reset


# ── Text Command Handlers ────────────────────────────────

async def market_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '거래소' or '거래소 목록' — browse listings."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    await queries.ensure_user(user_id, update.effective_user.first_name or "트레이너", update.effective_user.username)

    listings, total = await queries.get_active_listings(page=0, page_size=config.MARKET_PAGE_SIZE)
    text, markup = _build_listing_page(listings, total, 0, config.MARKET_PAGE_SIZE)
    await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def market_register_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '거래소 등록 [포켓몬이름] [가격]'."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    await queries.ensure_user(user_id, update.effective_user.first_name or "트레이너", update.effective_user.username)

    text = (update.message.text or "").strip()
    # Parse: 거래소 등록 피카츄 500
    # or: 거래소 등록 피카츄 #2 500
    parts = text.split()
    if len(parts) < 4:
        await update.message.reply_text(
            "사용법: 거래소 등록 [포켓몬이름] [가격BP]\n"
            "예시: 거래소 등록 피카츄 500\n"
            "중복 시: 거래소 등록 피카츄 #2 500"
        )
        return

    # Check if there's a #N selector
    instance_id = None
    pokemon_name = parts[2]
    price_str = parts[-1]

    # Handle: 거래소 등록 피카츄 #2 500
    if len(parts) >= 5 and parts[3].startswith("#"):
        try:
            select_idx = int(parts[3][1:])
        except ValueError:
            await update.message.reply_text("잘못된 번호입니다. 예: #2")
            return
        # Find all matching and pick by index
        all_pokemon = await queries.get_user_pokemon_list(user_id)
        name_lower = pokemon_name.strip().lower()
        matches = [p for p in all_pokemon if p["name_ko"].lower() == name_lower]
        if not matches:
            matches = [p for p in all_pokemon if name_lower in p["name_ko"].lower()]
        if not matches:
            await update.message.reply_text(f"'{pokemon_name}'을(를) 보유하고 있지 않습니다.")
            return
        if select_idx < 1 or select_idx > len(matches):
            await update.message.reply_text(f"1~{len(matches)} 사이의 번호를 입력하세요.")
            return
        instance_id = matches[select_idx - 1]["id"]

    try:
        price_bp = int(price_str)
    except ValueError:
        await update.message.reply_text("가격은 숫자로 입력하세요. 예: 거래소 등록 피카츄 500")
        return

    success, msg, listing_id, duplicates = await create_listing(
        user_id, pokemon_name, price_bp, instance_id,
    )

    if duplicates:
        # Show inline selection
        fee = calc_fee(price_bp)
        buttons = []
        for i, p in enumerate(duplicates, 1):
            shiny = "✨" if p.get("is_shiny") else ""
            iv = _iv_tag(p)
            label = f"#{i} {p['name_ko']}{shiny}{iv}"
            buttons.append([InlineKeyboardButton(
                label, callback_data=f"mkt_sel_{p['id']}_{price_bp}"
            )])
        markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text(
            f"⚠️ {pokemon_name} {len(duplicates)}마리 보유 중\n"
            f"거래소에 등록할 포켓몬을 선택하세요 ({price_bp:,} BP):",
            reply_markup=markup,
        )
        return

    await update.message.reply_text(msg)


async def market_my_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '거래소 내꺼' — my active listings."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    await queries.ensure_user(user_id, update.effective_user.first_name or "트레이너", update.effective_user.username)

    listings = await queries.get_user_active_listings(user_id)
    if not listings:
        await update.message.reply_text("🏪 등록된 매물이 없습니다.")
        return

    lines = [f"🏪 내 매물 ({len(listings)}개)", ""]
    buttons = []
    for ml in listings:
        shiny = "✨" if ml.get("is_shiny") else ""
        lines.append(f"#{ml['id']} {ml['emoji']} {ml['pokemon_name']}{shiny} — {ml['price_bp']:,} BP")
        buttons.append([InlineKeyboardButton(
            f"#{ml['id']} 취소", callback_data=f"mkt_cancel_{ml['id']}"
        )])

    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("\n".join(lines), reply_markup=markup)


async def market_cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '거래소 취소 [id]'."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id

    text = (update.message.text or "").strip()
    parts = text.split()
    if len(parts) < 3:
        await update.message.reply_text("사용법: 거래소 취소 [번호]\n예시: 거래소 취소 42")
        return

    try:
        listing_id = int(parts[2].replace("#", ""))
    except ValueError:
        await update.message.reply_text("매물 번호를 입력하세요. 예: 거래소 취소 42")
        return

    success, msg = await cancel_listing_for_user(user_id, listing_id)
    await update.message.reply_text(msg)


async def market_buy_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '거래소 구매 [id]'."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    await queries.ensure_user(user_id, update.effective_user.first_name or "트레이너", update.effective_user.username)

    text = (update.message.text or "").strip()
    parts = text.split()
    if len(parts) < 3:
        await update.message.reply_text("사용법: 거래소 구매 [번호]\n예시: 거래소 구매 42")
        return

    try:
        listing_id = int(parts[2].replace("#", ""))
    except ValueError:
        await update.message.reply_text("매물 번호를 입력하세요.")
        return

    # Show confirmation
    listing = await queries.get_listing_by_id(listing_id)
    if not listing or listing["status"] != "active":
        await update.message.reply_text("해당 매물을 찾을 수 없거나 이미 판매되었습니다.")
        return

    if listing["seller_id"] == user_id:
        await update.message.reply_text("자신의 매물은 구매할 수 없습니다.")
        return

    shiny = "✨" if listing.get("is_shiny") else ""
    iv = _iv_tag(listing)
    buttons = [
        [
            InlineKeyboardButton("✅ 구매 확인", callback_data=f"mkt_buyok_{listing_id}"),
            InlineKeyboardButton("❌ 취소", callback_data="mkt_buyno"),
        ]
    ]
    await update.message.reply_text(
        f"🏪 구매 확인\n\n"
        f"{listing['emoji']} {listing['pokemon_name']}{shiny}{iv}\n"
        f"💰 가격: {listing['price_bp']:,} BP\n"
        f"판매자: {listing.get('seller_name', '???')}\n\n"
        f"구매하시겠습니까?",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def market_search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '거래소 검색 [포켓몬이름]'."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    await queries.ensure_user(user_id, update.effective_user.first_name or "트레이너", update.effective_user.username)

    text = (update.message.text or "").strip()
    parts = text.split()
    if len(parts) < 3:
        await update.message.reply_text("사용법: 거래소 검색 [포켓몬이름]\n예시: 거래소 검색 피카츄")
        return

    search_name = parts[2]
    listings, total = await queries.search_listings(search_name, page=0, page_size=config.MARKET_PAGE_SIZE)
    text_out, markup = _build_listing_page(listings, total, 0, config.MARKET_PAGE_SIZE, search_name)
    await update.message.reply_text(text_out, reply_markup=markup, parse_mode="HTML")


# ── Callback Handler ─────────────────────────────────────

async def market_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all mkt_ callbacks."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = query.from_user.id
    data = query.data or ""

    # ── Filter menu: show rarity options ──
    if data.startswith("mkt_fmenu_r_"):
        # mkt_fmenu_r_{current_iv}
        current_iv = data[len("mkt_fmenu_r_"):]
        buttons = []
        for rkey, rlabel in RARITY_LABELS.items():
            cb = f"mkt_f_r{rkey}_iv{current_iv}"
            buttons.append([InlineKeyboardButton(rlabel, callback_data=cb)])
        try:
            await query.edit_message_text("📋 등급 필터 선택:", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            pass
        return

    # ── Filter menu: show IV options ──
    if data.startswith("mkt_fmenu_iv_"):
        current_rarity = data[len("mkt_fmenu_iv_"):]
        buttons = []
        for ivkey, ivlabel in IV_LABELS.items():
            display = "전체" if not ivkey else f"{ivlabel}등급 이상"
            cb = f"mkt_f_r{current_rarity}_iv{ivkey}"
            buttons.append([InlineKeyboardButton(display, callback_data=cb)])
        try:
            await query.edit_message_text("📊 개체값 필터 선택:", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            pass
        return

    # ── Apply filter: mkt_f_r{rarity}_iv{grade} ──
    if data.startswith("mkt_f_r"):
        # Parse: mkt_f_r{rarity}_iv{grade}
        rest = data[len("mkt_f_r"):]
        if "_iv" in rest:
            rarity_val, iv_val = rest.split("_iv", 1)
        else:
            rarity_val, iv_val = rest, ""
        listings, total = await queries.get_active_listings(
            page=0, page_size=config.MARKET_PAGE_SIZE,
            rarity=rarity_val or None, iv_grade=iv_val or None,
        )
        text, markup = _build_listing_page(listings, total, 0, config.MARKET_PAGE_SIZE, rarity=rarity_val, iv_grade=iv_val)
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass
        return

    # ── Filter reset ──
    if data == "mkt_fr":
        listings, total = await queries.get_active_listings(page=0, page_size=config.MARKET_PAGE_SIZE)
        text, markup = _build_listing_page(listings, total, 0, config.MARKET_PAGE_SIZE)
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass
        return

    # ── Filtered pagination: mkt_fp_r{rarity}_iv{grade}_{page} ──
    if data.startswith("mkt_fp_"):
        rest = data[len("mkt_fp_"):]
        # rest = r{rarity}_iv{grade}_{page}
        last_underscore = rest.rfind("_")
        fkey = rest[:last_underscore]
        try:
            page = int(rest[last_underscore + 1:])
        except ValueError:
            return
        # Parse fkey: r{rarity}_iv{grade}
        if "_iv" in fkey:
            rarity_val = fkey.split("_iv")[0][1:]  # strip leading 'r'
            iv_val = fkey.split("_iv")[1]
        else:
            rarity_val, iv_val = "", ""
        listings, total = await queries.get_active_listings(
            page=page, page_size=config.MARKET_PAGE_SIZE,
            rarity=rarity_val or None, iv_grade=iv_val or None,
        )
        text, markup = _build_listing_page(listings, total, page, config.MARKET_PAGE_SIZE, rarity=rarity_val, iv_grade=iv_val)
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass
        return

    # ── Pagination ──
    if data.startswith("mkt_page_"):
        try:
            page = int(data.split("_")[2])
        except (ValueError, IndexError):
            return
        listings, total = await queries.get_active_listings(page=page, page_size=config.MARKET_PAGE_SIZE)
        text, markup = _build_listing_page(listings, total, page, config.MARKET_PAGE_SIZE)
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass
        return

    # ── Search pagination: mkt_s_name_page ──
    if data.startswith("mkt_s_"):
        parts = data.split("_")
        if len(parts) >= 4:
            search_name = parts[2]
            try:
                page = int(parts[3])
            except ValueError:
                return
            listings, total = await queries.search_listings(search_name, page=page, page_size=config.MARKET_PAGE_SIZE)
            text, markup = _build_listing_page(listings, total, page, config.MARKET_PAGE_SIZE, search_name)
            try:
                await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
            except Exception:
                pass
        return

    # ── Buy button from listing ──
    if data.startswith("mkt_buy_"):
        try:
            listing_id = int(data.split("_")[2])
        except (ValueError, IndexError):
            return
        listing = await queries.get_listing_by_id(listing_id)
        if not listing or listing["status"] != "active":
            try:
                await query.edit_message_text("이 매물은 이미 판매되었습니다.")
            except Exception:
                pass
            return

        if listing["seller_id"] == user_id:
            try:
                await query.edit_message_text("자신의 매물은 구매할 수 없습니다.")
            except Exception:
                pass
            return

        shiny = "✨" if listing.get("is_shiny") else ""
        iv = _iv_tag(listing)
        buttons = [
            [
                InlineKeyboardButton("✅ 구매 확인", callback_data=f"mkt_buyok_{listing_id}"),
                InlineKeyboardButton("❌ 취소", callback_data="mkt_buyno"),
            ]
        ]
        try:
            await query.edit_message_text(
                f"🏪 구매 확인\n\n"
                f"{listing['emoji']} {listing['pokemon_name']}{shiny}{iv}\n"
                f"💰 가격: {listing['price_bp']:,} BP\n"
                f"판매자: {listing.get('seller_name', '???')}\n\n"
                f"구매하시겠습니까?",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
        except Exception:
            pass
        return

    # ── Confirm purchase ──
    if data.startswith("mkt_buyok_"):
        try:
            listing_id = int(data.split("_")[2])
        except (ValueError, IndexError):
            return

        success, msg, info = await buy_listing(user_id, listing_id)
        try:
            await query.edit_message_text(msg)
        except Exception:
            pass

        # Mission: trade (buyer)
        if success:
            asyncio.create_task(_check_trade_mission_market(user_id, context.bot))

        # Send DM notification to seller
        if success and info:
            try:
                shiny_tag = "✨" if info["is_shiny"] else ""
                seller_msg = (
                    f"💰 거래소 판매 알림!\n\n"
                    f"{info['emoji']} {info['pokemon_name']}{shiny_tag}이(가) 판매되었습니다.\n"
                    f"💵 수익: {info['seller_gets']:,} BP (수수료 {info['fee']:,} BP)"
                )
                await context.bot.send_message(chat_id=info["seller_id"], text=seller_msg)
            except Exception:
                pass
        return

    # ── Cancel purchase confirmation ──
    if data == "mkt_buyno":
        try:
            await query.edit_message_text("구매를 취소했습니다.")
        except Exception:
            pass
        return

    # ── Select pokemon for listing (duplicates) ──
    if data.startswith("mkt_sel_"):
        parts = data.split("_")
        if len(parts) >= 4:
            try:
                instance_id = int(parts[2])
                price_bp = int(parts[3])
            except ValueError:
                return

            # Get pokemon info
            pokemon = await queries.get_user_pokemon_by_id(instance_id)
            if not pokemon or pokemon["user_id"] != user_id:
                try:
                    await query.edit_message_text("해당 포켓몬을 찾을 수 없습니다.")
                except Exception:
                    pass
                return

            # Show confirmation
            shiny = "✨" if pokemon.get("is_shiny") else ""
            iv = _iv_tag(pokemon)
            fee = calc_fee(price_bp)
            buttons = [
                [
                    InlineKeyboardButton("✅ 등록", callback_data=f"mkt_cfm_{instance_id}_{price_bp}"),
                    InlineKeyboardButton("❌ 취소", callback_data="mkt_cfmno"),
                ]
            ]
            try:
                await query.edit_message_text(
                    f"🏪 거래소 등록 확인\n\n"
                    f"{pokemon['emoji']} {pokemon['name_ko']}{shiny}{iv}\n"
                    f"💰 판매가: {price_bp:,} BP\n"
                    f"📋 수수료: {fee:,} BP\n"
                    f"💵 수익 예상: {price_bp - fee:,} BP\n\n"
                    f"등록하시겠습니까?",
                    reply_markup=InlineKeyboardMarkup(buttons),
                )
            except Exception:
                pass
        return

    # ── Confirm listing ──
    if data.startswith("mkt_cfm_"):
        parts = data.split("_")
        if len(parts) >= 4:
            try:
                instance_id = int(parts[2])
                price_bp = int(parts[3])
            except ValueError:
                return

            pokemon = await queries.get_user_pokemon_by_id(instance_id)
            if not pokemon or pokemon["user_id"] != user_id:
                try:
                    await query.edit_message_text("해당 포켓몬을 찾을 수 없습니다.")
                except Exception:
                    pass
                return

            success, msg, listing_id, _ = await create_listing(
                user_id, pokemon["name_ko"], price_bp, instance_id,
            )
            try:
                await query.edit_message_text(msg)
            except Exception:
                pass
        return

    # ── Cancel listing confirmation ──
    if data == "mkt_cfmno":
        try:
            await query.edit_message_text("등록을 취소했습니다.")
        except Exception:
            pass
        return

    # ── Cancel listing from my list ──
    if data.startswith("mkt_cancel_"):
        try:
            listing_id = int(data.split("_")[2])
        except (ValueError, IndexError):
            return

        success, msg = await cancel_listing_for_user(user_id, listing_id)
        try:
            await query.edit_message_text(msg)
        except Exception:
            pass
        return

    # ── No-op (page indicator) ──
    if data == "mkt_noop":
        return


async def _check_trade_mission_market(user_id: int, bot):
    """Fire-and-forget: check trade mission progress after marketplace purchase."""
    try:
        from services.mission_service import check_mission_progress
        msg = await check_mission_progress(user_id, "trade")
        if msg:
            await bot.send_message(chat_id=user_id, text=msg, parse_mode="HTML")
    except Exception:
        pass
