"""DM-only marketplace handler: browse, register, buy, cancel, search."""

import asyncio
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from database import queries, market_queries
from services.market_service import create_listing, buy_listing, cancel_listing_for_user, calc_fee
from utils.helpers import iv_grade_tag as _iv_tag, iv_grade, type_badge
from utils.battle_calc import iv_total, calc_battle_stats, format_power, EVO_STAGE_MAP, get_normalized_base_stats
from utils.i18n import t, get_user_lang, poke_name

logger = logging.getLogger(__name__)


def _listing_line(ml: dict, lang: str = "ko") -> str:
    """Single-line listing summary."""
    shiny = " ✨이로치" if ml.get("is_shiny") else ""
    iv = _iv_tag(ml)
    name = poke_name(ml, lang)
    return f"#{ml['id']} {type_badge(ml['pokemon_id'])} {name}{shiny}{iv} — {ml['price_bp']:,} BP"


RARITY_LABELS = {
    "": "전체",
    "common": "일반",
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
    lang: str = "ko",
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
        lines.append(_listing_line(ml, lang))
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
        shiny = " ✨이로치" if ml.get("is_shiny") else ""
        label = f"#{ml['id']} {poke_name(ml, lang)}{shiny} {ml['price_bp']:,}BP 구매"
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

    lang = await get_user_lang(user_id)
    listings, total = await market_queries.get_active_listings(page=0, page_size=config.MARKET_PAGE_SIZE)
    text, markup = _build_listing_page(listings, total, 0, config.MARKET_PAGE_SIZE, lang=lang)
    await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def market_register_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '거래소 등록 [포켓몬이름] [가격]'."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    await queries.ensure_user(user_id, update.effective_user.first_name or "트레이너", update.effective_user.username)

    lang = await get_user_lang(user_id)
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
        user_id, pokemon_name, price_bp, instance_id, lang=lang,
    )

    if duplicates:
        # Show inline selection
        fee = calc_fee(price_bp)
        buttons = []
        for i, p in enumerate(duplicates, 1):
            shiny = " ✨이로치" if p.get("is_shiny") else ""
            iv = _iv_tag(p)
            label = f"#{i} {poke_name(p, lang)}{shiny}{iv}"
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

    lang = await get_user_lang(user_id)
    listings = await market_queries.get_user_active_listings(user_id)
    if not listings:
        await update.message.reply_text("🏪 등록된 매물이 없습니다.")
        return

    lines = [f"🏪 내 매물 ({len(listings)}개)", ""]
    buttons = []
    for ml in listings:
        shiny = " ✨이로치" if ml.get("is_shiny") else ""
        lines.append(f"#{ml['id']} {type_badge(ml['pokemon_id'])} {poke_name(ml, lang)}{shiny} — {ml['price_bp']:,} BP")
        buttons.append([InlineKeyboardButton(
            f"#{ml['id']} 취소", callback_data=f"mkt_cancel_{ml['id']}"
        )])

    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("\n".join(lines), reply_markup=markup, parse_mode="HTML")


async def market_cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '거래소 취소 [id]'."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)

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

    success, msg = await cancel_listing_for_user(user_id, listing_id, lang=lang)
    await update.message.reply_text(msg)


async def market_buy_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '거래소 구매 [id]'."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    await queries.ensure_user(user_id, update.effective_user.first_name or "트레이너", update.effective_user.username)
    lang = await get_user_lang(user_id)

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
    listing = await market_queries.get_listing_by_id(listing_id)
    if not listing or listing["status"] != "active":
        await update.message.reply_text("해당 매물을 찾을 수 없거나 이미 판매되었습니다.")
        return

    if listing["seller_id"] == user_id:
        await update.message.reply_text("자신의 매물은 구매할 수 없습니다.")
        return

    shiny = " ✨이로치" if listing.get("is_shiny") else ""
    iv = _iv_tag(listing)
    buttons = [
        [
            InlineKeyboardButton("✅ 구매 확인", callback_data=f"mkt_buyok_{listing_id}"),
            InlineKeyboardButton("❌ 취소", callback_data="mkt_buyno"),
        ]
    ]
    await update.message.reply_text(
        f"🏪 구매 확인\n\n"
        f"{type_badge(listing['pokemon_id'])} {poke_name(listing, lang)}{shiny}{iv}\n"
        f"💰 가격: {listing['price_bp']:,} BP\n"
        f"판매자: {listing.get('seller_name', '???')}\n\n"
        f"구매하시겠습니까?",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
    )


async def market_search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '거래소 검색 [포켓몬이름]'."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    await queries.ensure_user(user_id, update.effective_user.first_name or "트레이너", update.effective_user.username)
    lang = await get_user_lang(user_id)

    text = (update.message.text or "").strip()
    parts = text.split()
    if len(parts) < 3:
        await update.message.reply_text("사용법: 거래소 검색 [포켓몬이름]\n예시: 거래소 검색 피카츄")
        return

    search_name = parts[2]
    listings, total = await market_queries.search_listings(search_name, page=0, page_size=config.MARKET_PAGE_SIZE)
    text_out, markup = _build_listing_page(listings, total, 0, config.MARKET_PAGE_SIZE, search_name, lang=lang)
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
    lang = await get_user_lang(user_id)

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
        listings, total = await market_queries.get_active_listings(
            page=0, page_size=config.MARKET_PAGE_SIZE,
            rarity=rarity_val or None, iv_grade=iv_val or None,
        )
        text, markup = _build_listing_page(listings, total, 0, config.MARKET_PAGE_SIZE, rarity=rarity_val, iv_grade=iv_val, lang=lang)
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass
        return

    # ── Filter reset ──
    if data == "mkt_fr":
        listings, total = await market_queries.get_active_listings(page=0, page_size=config.MARKET_PAGE_SIZE)
        text, markup = _build_listing_page(listings, total, 0, config.MARKET_PAGE_SIZE, lang=lang)
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
        listings, total = await market_queries.get_active_listings(
            page=page, page_size=config.MARKET_PAGE_SIZE,
            rarity=rarity_val or None, iv_grade=iv_val or None,
        )
        text, markup = _build_listing_page(listings, total, page, config.MARKET_PAGE_SIZE, rarity=rarity_val, iv_grade=iv_val, lang=lang)
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
        listings, total = await market_queries.get_active_listings(page=page, page_size=config.MARKET_PAGE_SIZE)
        text, markup = _build_listing_page(listings, total, page, config.MARKET_PAGE_SIZE, lang=lang)
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
            listings, total = await market_queries.search_listings(search_name, page=page, page_size=config.MARKET_PAGE_SIZE)
            text, markup = _build_listing_page(listings, total, page, config.MARKET_PAGE_SIZE, search_name, lang=lang)
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
        listing = await market_queries.get_listing_by_id(listing_id)
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

        shiny = " ✨이로치" if listing.get("is_shiny") else ""
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
                f"{type_badge(listing['pokemon_id'])} {poke_name(listing, lang)}{shiny}{iv}\n"
                f"💰 가격: {listing['price_bp']:,} BP\n"
                f"판매자: {listing.get('seller_name', '???')}\n\n"
                f"구매하시겠습니까?",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode="HTML",
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

        success, msg, info = await buy_listing(user_id, listing_id, lang=lang)

        # 구매자에게 스펙 포함 메시지 표시
        if success and info:
            try:
                ivs = info.get("ivs", {})
                iv_hp = ivs.get("iv_hp")
                iv_atk = ivs.get("iv_atk")
                iv_def = ivs.get("iv_def")
                iv_spa = ivs.get("iv_spa")
                iv_spdef = ivs.get("iv_spdef")
                iv_spd = ivs.get("iv_spd")
                total_iv = iv_total(iv_hp, iv_atk, iv_def, iv_spa, iv_spdef, iv_spd)
                grade = iv_grade(total_iv)
                shiny_tag = " ✨이로치" if info["is_shiny"] else ""

                # 전투력 계산
                pid = info["pokemon_id"]
                norm = get_normalized_base_stats(pid)
                evo_stage = 3 if norm else EVO_STAGE_MAP.get(pid, 3)
                base_kwargs = norm or {}
                stats = calc_battle_stats(
                    pokemon_id=pid, level=1, evo_stage=evo_stage,
                    iv_hp=iv_hp, iv_atk=iv_atk, iv_def=iv_def,
                    iv_spa=iv_spa, iv_spdef=iv_spdef, iv_spd=iv_spd,
                    **base_kwargs,
                )
                power = stats.get("power", 0)

                spec_msg = (
                    f"🎉 거래소 구매 완료!\n\n"
                    f"{type_badge(info['pokemon_id'])} <b>{poke_name(info, lang)}{shiny_tag}</b>\n"
                    f"💰 {info['price']:,} BP 지불\n\n"
                    f"📊 IV: {total_iv}/186 [{grade}]\n"
                    f"  HP {iv_hp or 0} / ATK {iv_atk or 0} / DEF {iv_def or 0}\n"
                    f"  SPA {iv_spa or 0} / SPDEF {iv_spdef or 0} / SPD {iv_spd or 0}\n"
                    f"⚔️ 전투력: {format_power(power)}"
                )
                await query.edit_message_text(spec_msg, parse_mode="HTML")
            except Exception:
                try:
                    await query.edit_message_text(msg)
                except Exception:
                    pass
        else:
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
                seller_lang = await get_user_lang(info["seller_id"])
                shiny_tag = " ✨이로치" if info["is_shiny"] else ""
                sold_name = poke_name(info, seller_lang)
                seller_msg = (
                    f"💰 거래소 판매 알림!\n\n"
                    f"{type_badge(info['pokemon_id'])} {sold_name}{shiny_tag}이(가) 판매되었습니다.\n"
                    f"💵 수익: {info['seller_gets']:,} BP (수수료 {info['fee']:,} BP)"
                )
                # Show remaining listings
                remaining = await market_queries.get_user_active_listings(info["seller_id"])
                if remaining:
                    seller_msg += f"\n\n📋 남은 매물 ({len(remaining)}개):"
                    for ml in remaining[:5]:
                        s = " ✨이로치" if ml.get("is_shiny") else ""
                        seller_msg += f"\n  #{ml['id']} {type_badge(ml['pokemon_id'])} {poke_name(ml, seller_lang)}{s} — {ml['price_bp']:,} BP"
                    if len(remaining) > 5:
                        seller_msg += f"\n  … 외 {len(remaining) - 5}개"
                else:
                    seller_msg += "\n\n📋 남은 매물이 없습니다."
                await context.bot.send_message(chat_id=info["seller_id"], text=seller_msg, parse_mode="HTML")
            except Exception:
                pass

            # Send trade evolution choice DM to buyer
            if info.get("pending_evo"):
                try:
                    evo = info["pending_evo"]
                    source = await queries.get_pokemon(evo["source_id"])
                    target = await queries.get_pokemon(evo["target_id"])
                    if source and target:
                        evo_text = (
                            f"✨ 교환 진화 가능!\n\n"
                            f"{type_badge(source['id'])} {poke_name(source, lang)}을(를)\n"
                            f"{type_badge(target['id'])} {poke_name(target, lang)}(으)로 진화시킬 수 있습니다!\n\n"
                            f"진화하시겠습니까?"
                        )
                        evo_buttons = [[
                            InlineKeyboardButton("✨ 진화시키기", callback_data=f"tevo_yes_{evo['instance_id']}"),
                            InlineKeyboardButton("❌ 그대로 유지", callback_data=f"tevo_no_{evo['instance_id']}"),
                        ]]
                        await context.bot.send_message(
                            chat_id=user_id, text=evo_text,
                            reply_markup=InlineKeyboardMarkup(evo_buttons),
                        )
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
            shiny = " ✨이로치" if pokemon.get("is_shiny") else ""
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
                    f"{type_badge(pokemon['pokemon_id'])} {poke_name(pokemon, lang)}{shiny}{iv}\n"
                    f"💰 판매가: {price_bp:,} BP\n"
                    f"📋 수수료: {fee:,} BP\n"
                    f"💵 수익 예상: {price_bp - fee:,} BP\n\n"
                    f"등록하시겠습니까?",
                    reply_markup=InlineKeyboardMarkup(buttons),
                    parse_mode="HTML",
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
                user_id, pokemon["name_ko"], price_bp, instance_id, lang=lang,
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

        success, msg = await cancel_listing_for_user(user_id, listing_id, lang=lang)
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
