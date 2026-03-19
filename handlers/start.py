"""Start, help, and language selection handlers."""

import random
import logging

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import queries
from utils.helpers import icon_emoji
from utils.i18n import (
    t, get_user_lang, set_user_lang, set_cached_lang,
    LANG_LABELS, SUPPORTED_LANGS, DEFAULT_LANG,
)

logger = logging.getLogger(__name__)


# ─── Language selection ─────────────────────────────

_LANG_SELECT_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("🇰🇷 한국어", callback_data="lang_ko"),
        InlineKeyboardButton("🇺🇸 English", callback_data="lang_en"),
    ],
    [
        InlineKeyboardButton("🇨🇳 简体中文", callback_data="lang_zh-hans"),
        InlineKeyboardButton("🇹🇼 繁體中文", callback_data="lang_zh-hant"),
    ],
])

_LANG_SELECT_MSG = (
    "🌐 <b>언어를 선택해주세요 / Select your language</b>\n"
    "━━━━━━━━━━━━━━━\n\n"
    "🇰🇷 한국어\n"
    "🇺🇸 English\n"
    "🇨🇳 简体中文\n"
    "🇹🇼 繁體中文"
)

# Confirmation messages per language (hardcoded, no locale file dependency)
_LANG_CONFIRM = {
    "ko": "✅ 언어가 한국어로 설정되었습니다!",
    "en": "✅ Language has been set to English!\n⚠️ Some menus are still in Korean. More translations coming soon!",
    "zh-hans": "✅ 语言已设置为简体中文！\n⚠️ 部分菜单仍为韩语，更多翻译即将推出！",
    "zh-hant": "✅ 語言已設置為繁體中文！\n⚠️ 部分選單仍為韓語，更多翻譯即將推出！",
}


def _build_menu_keyboard(lang: str) -> ReplyKeyboardMarkup:
    """Build reply keyboard menu based on language."""
    if lang == "ko":
        return ReplyKeyboardMarkup(
            [
                ["📋 상태창", "📦 내포켓몬"],
                ["🏕 캠프", "🎰 뽑기"],
                ["📌 미션", "🏪 상점"],
                ["🎒 아이템", "🏰 던전"],
                ["⚔️ 랭크전", "💎 프리미엄"],
                ["⚙️ 설정"],
            ],
            resize_keyboard=True,
            input_field_placeholder="명령어를 선택하세요",
        )
    elif lang == "en":
        return ReplyKeyboardMarkup(
            [
                ["📋 Status", "📦 My Pokemon"],
                ["🏕 Camp", "🎰 Gacha"],
                ["📌 Mission", "🏪 Shop"],
                ["🎒 Items", "🏰 Dungeon"],
                ["⚔️ Ranked", "💎 Premium"],
                ["⚙️ Settings"],
            ],
            resize_keyboard=True,
            input_field_placeholder="Select a command",
        )
    elif lang == "zh-hans":
        return ReplyKeyboardMarkup(
            [
                ["📋 状态", "📦 我的宝可梦"],
                ["🏕 营地", "🎰 扭蛋"],
                ["📌 任务", "🏪 商店"],
                ["🎒 道具", "🏰 地牢"],
                ["⚔️ 排位赛", "💎 高级"],
                ["⚙️ 设置"],
            ],
            resize_keyboard=True,
            input_field_placeholder="请选择指令",
        )
    elif lang == "zh-hant":
        return ReplyKeyboardMarkup(
            [
                ["📋 狀態", "📦 我的寶可夢"],
                ["🏕 營地", "🎰 轉蛋"],
                ["📌 任務", "🏪 商店"],
                ["🎒 道具", "🏰 地牢"],
                ["⚔️ 排位賽", "💎 高級"],
                ["⚙️ 設定"],
            ],
            resize_keyboard=True,
            input_field_placeholder="請選擇指令",
        )
    # Fallback to Korean
    return _build_menu_keyboard("ko")


def _welcome_text(lang: str, display_name: str) -> str:
    """Get welcome text for language."""
    if lang == "ko":
        return (
            f"🎮 안녕하세요, {display_name} 트레이너님!\n"
            "포켓몬 봇에 오신 걸 환영합니다!\n"
            "━━━━━━━━━━━━━━━\n\n"
            "아래 버튼으로 빠르게 이동할 수 있어요!\n"
            "'상태창'으로 현재 상태를 확인하세요.\n\n"
            "━━━━━━━━━━━━━━━\n"
            "💡 도움말 — 전체 명령어 보기"
        )
    elif lang == "en":
        return (
            f"🎮 Welcome, {display_name} Trainer!\n"
            "Welcome to the Pokemon Bot!\n"
            "━━━━━━━━━━━━━━━\n\n"
            "Use the buttons below for quick navigation!\n"
            "Check your status with 'Status'.\n\n"
            "━━━━━━━━━━━━━━━\n"
            "💡 Help — View all commands"
        )
    elif lang == "zh-hans":
        return (
            f"🎮 你好, {display_name} 训练师!\n"
            "欢迎来到宝可梦机器人!\n"
            "━━━━━━━━━━━━━━━\n\n"
            "使用下方按钮快速导航!\n"
            "点击'状态'查看当前状态。\n\n"
            "━━━━━━━━━━━━━━━\n"
            "💡 帮助 — 查看所有指令"
        )
    elif lang == "zh-hant":
        return (
            f"🎮 你好, {display_name} 訓練師!\n"
            "歡迎來到寶可夢機器人!\n"
            "━━━━━━━━━━━━━━━\n\n"
            "使用下方按鈕快速導航!\n"
            "點擊'狀態'查看當前狀態。\n\n"
            "━━━━━━━━━━━━━━━\n"
            "💡 幫助 — 查看所有指令"
        )
    return _welcome_text("ko", display_name)


async def _has_language_set(user_id: int) -> bool:
    """Check if user has explicitly set a language (not NULL in DB)."""
    try:
        from database.connection import get_db
        pool = await get_db()
        lang = await pool.fetchval(
            "SELECT language FROM users WHERE user_id = $1", user_id
        )
        # If language is explicitly set (not just the default from column),
        # we consider it "set". We check if user exists and has non-null language.
        # The column has DEFAULT 'ko', so new users will have 'ko'.
        # We use a separate flag approach: check user_data context.
        return lang is not None
    except Exception:
        return False


async def _send_welcome(update_or_query, context, user_id: int, display_name: str, lang: str):
    """Send the welcome message with menu keyboard."""
    menu_keyboard = _build_menu_keyboard(lang)
    welcome = _welcome_text(lang, display_name)

    if hasattr(update_or_query, 'message') and update_or_query.message:
        await update_or_query.message.reply_text(welcome, reply_markup=menu_keyboard)
    else:
        # Called from callback — send new message
        await context.bot.send_message(
            chat_id=user_id,
            text=welcome,
            reply_markup=menu_keyboard,
        )


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    display_name = update.effective_user.first_name or "트레이너"
    username = update.effective_user.username

    await queries.ensure_user(user_id, display_name, username)

    # Check if group or DM
    if update.effective_chat.type == "private":
        # Check if user has language set via context flag
        # For new users (first /start), show language selection
        # For returning users, skip to welcome
        lang = await get_user_lang(user_id)

        # Check if this is truly a first-time user (no pokemon, no catches)
        # by checking if they have any activity, or use a simpler heuristic:
        # store "lang_set" in user_data to track if language was explicitly chosen
        is_first_start = context.user_data.get("_lang_explicitly_set") is None

        # Also check DB: if user has pokemon or battle_points > 500, they're not new
        try:
            from database.connection import get_db
            pool = await get_db()
            poke_count = await pool.fetchval(
                "SELECT COUNT(*) FROM user_pokemon WHERE user_id = $1", user_id
            )
            if poke_count and poke_count > 0:
                is_first_start = False
        except Exception:
            is_first_start = False

        if is_first_start:
            # Show language selection first
            context.user_data["_start_pending"] = True
            await update.message.reply_text(
                _LANG_SELECT_MSG,
                parse_mode="HTML",
                reply_markup=_LANG_SELECT_KEYBOARD,
            )
            return

        # Existing user — show welcome with their language
        await _send_welcome(update, context, user_id, display_name, lang)
    else:
        # In group chat, register the chat room
        chat_id = update.effective_chat.id
        title = update.effective_chat.title
        try:
            count = await context.bot.get_chat_member_count(chat_id)
        except Exception:
            count = 0

        await queries.ensure_chat_room(chat_id, title, count)

        # Schedule spawns for this chat
        from services.spawn_service import schedule_spawns_for_chat, execute_spawn
        await schedule_spawns_for_chat(context.application, chat_id, count)

        # Schedule a welcome spawn within 1 hour (10~60 min, force=True to skip activity check)
        welcome_delay = random.randint(600, 3600)
        context.application.job_queue.run_once(
            execute_spawn,
            when=welcome_delay,
            data={"chat_id": chat_id, "force": True},
            name=f"welcome_spawn_{chat_id}",
        )

        await update.message.reply_text(
            "🎮 포켓몬 봇이 활성화되었습니다!\n"
            "야생 포켓몬이 나타나면 ㅊ 으로 잡으세요!\n"
            "🌿 곧 첫 번째 포켓몬이 나타날 거예요!\n\n"
            "⚠️ 봇을 관리자로 설정하면 채팅방이 깔끔해집니다!\n"
            "(명령어/결과 메시지 자동 정리 기능)"
        )


# ─── Language callback handler ───────────────────────

async def language_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle lang_ko, lang_en, lang_zh-hans, lang_zh-hant callbacks."""
    query = update.callback_query
    await query.answer()

    if not query.data or not query.data.startswith("lang_"):
        return

    lang_code = query.data[5:]  # Remove "lang_" prefix
    if lang_code not in SUPPORTED_LANGS:
        return

    user_id = update.effective_user.id
    display_name = update.effective_user.first_name or "Trainer"

    # Save language
    await set_user_lang(user_id, lang_code)
    context.user_data["_lang_explicitly_set"] = True

    # Send confirmation
    confirm_msg = _LANG_CONFIRM.get(lang_code, _LANG_CONFIRM["ko"])

    # Check if this was from /start (first time)
    is_start_pending = context.user_data.pop("_start_pending", False)
    is_lang_change = context.user_data.pop("_lang_change", False)

    if is_start_pending:
        # First time — edit the language selection message, then send welcome
        await query.edit_message_text(confirm_msg)
        await _send_welcome(update, context, user_id, display_name, lang_code)
    elif is_lang_change:
        # Language change command — just confirm
        await query.edit_message_text(confirm_msg)
    else:
        # Generic language change
        await query.edit_message_text(confirm_msg)


# ─── Language change command ──────────────────────────

async def language_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '언어' / 'language' / 'lang' command — show language selection buttons."""
    if not update.effective_user:
        return

    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)

    current_label = LANG_LABELS.get(lang, LANG_LABELS["ko"])

    context.user_data["_lang_change"] = True

    msg = (
        f"🌐 <b>언어 설정 / Language Settings</b>\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"현재 / Current: <b>{current_label}</b>\n\n"
        f"변경할 언어를 선택하세요.\n"
        f"Select your language."
    )
    await update.message.reply_text(
        msg,
        parse_mode="HTML",
        reply_markup=_LANG_SELECT_KEYBOARD,
    )


# ─── 도움말 시스템 ─────────────────────────────────

_HELP_MAIN = (
    "📖 <b>도움말</b>\n"
    "━━━━━━━━━━━━━━━\n\n"
    "🌿 <b>포획</b> — ㅊ  ㅎ  ㅁ  출석\n"
    "🍚 <b>육성</b> — 내포켓몬  밥  놀기  진화\n"
    "⚔️ <b>배틀</b> — 배틀  랭전  야차  팀등록\n"
    "🔄 <b>교환</b> — 교환  합성  방생\n"
    "🛒 <b>상점</b> — 상점  거래소  프리미엄상점\n"
    "📖 <b>도감</b> — 도감  칭호  상태창\n"
    "📊 <b>정보</b> — 랭킹  날씨  대시보드\n"
    "💎 <b>구독</b> — 구독  구독정보\n\n"
    "아래 버튼을 눌러 상세 명령어를 확인하세요!"
)

_HELP_SECTIONS = {
    "help_catch": (
        "🌿 <b>포획 명령어</b>\n"
        "━━━━━━━━━━━━━━━\n\n"
        "📍 <b>채팅방에서 사용</b>\n"
        "  <code>ㅊ</code> / <code>c</code> — 포켓볼로 잡기 시도\n"
        "  <code>ㅎ</code> / <code>h</code> — 하이퍼볼 사용 (포획률 x2)\n"
        "  <code>ㅁ</code> / <code>m</code> — 마스터볼 사용 (100% 포획)\n"
        "  <code>출석</code> — 일일 출석 (하이퍼볼 +1)\n"
        "  <code>포켓볼 충전</code> — 잡기 횟수 +10\n\n"
        "📍 <b>포획 시스템</b>\n"
        "  • 일일 기본 20회, 충전 시 +10 (최대 120회)\n"
        "  • 포케볼 남은 수량이 표시됩니다\n"
        "  • 구독 시 포케볼 무제한 + 쿨다운 해제"
    ),
    "help_nurture": (
        "🍚 <b>육성 명령어</b>\n"
        "━━━━━━━━━━━━━━━\n\n"
        "📍 <b>DM에서 사용</b>\n"
        "  <code>내포켓몬</code> — 보유 포켓몬 목록\n"
        "  <code>내포켓몬 [이름]</code> — 특정 포켓몬 검색\n"
        "  <code>밥 [이름]</code> — 밥 주기 (친밀도↑, 3회/일)\n"
        "  <code>놀기 [이름]</code> — 놀아주기 (친밀도↑, 2회/일)\n"
        "  <code>진화 [이름]</code> — 진화 (친밀도 MAX 시)\n"
        "  <code>감정 [이름]</code> — IV 개체값 확인\n"
        "  <code>친밀도강화</code> — 육성 메뉴 바로가기\n\n"
        "📍 <b>팁</b>\n"
        "  • 친밀도가 MAX가 되면 진화 가능\n"
        "  • 교환 진화 포켓몬은 교환을 통해 진화"
    ),
    "help_battle": (
        "⚔️ <b>배틀 명령어</b>\n"
        "━━━━━━━━━━━━━━━\n\n"
        "📍 <b>팀 구성 (DM)</b>\n"
        "  <code>파트너</code> / <code>파트너 [이름]</code> — 파트너 지정\n"
        "  <code>팀편집</code> — 팀 편집 메뉴\n"
        "  <code>팀등록</code> — 배틀 팀 등록 (최대 6마리)\n"
        "  <code>팀</code> / <code>팀1</code> / <code>팀2</code> — 팀 확인\n"
        "  <code>팀해제</code> — 팀 초기화\n"
        "  <code>팀스왑</code> — 팀1 ↔ 팀2 교체\n"
        "  💰 COST: 커먼2 / 레어3 / 에픽4 / 전설5 (합계 18 이하)\n\n"
        "📍 <b>대전 (채팅방)</b>\n"
        "  <code>배틀</code> — 상대에게 답장하며 도전\n"
        "  <code>배틀수락</code> / <code>배틀거절</code>\n"
        "  <code>야차</code> — BP/마스터볼 베팅 대결\n\n"
        "📍 <b>랭크전 (DM)</b>\n"
        "  <code>랭전</code> — 자동매칭 랭크 대전\n"
        "  <code>티어</code> — 내 랭크 티어 확인\n"
        "  <code>시즌</code> — 현재 시즌 정보\n\n"
        "📍 <b>전적/랭킹</b>\n"
        "  <code>배틀전적</code> — 승패/연승/BP\n"
        "  <code>배틀랭킹</code> — BP 랭킹 (채팅방)\n"
        "  <code>BP</code> — BP 잔액 확인"
    ),
    "help_trade": (
        "🔄 <b>교환 · 합성 · 방생</b>\n"
        "━━━━━━━━━━━━━━━\n\n"
        "📍 <b>교환 (채팅방 답장)</b>\n"
        "  <code>교환 [내 포켓몬]</code> — 상대에게 답장하며 교환 요청\n"
        "  → DM에서 줄 포켓몬 선택 & 수락/거절\n\n"
        "📍 <b>합성 (DM)</b>\n"
        "  <code>합성</code> — 같은 포켓몬 2마리로 상위 등급 도전\n"
        "  • 이로치×이로치 = A등급 보장\n\n"
        "📍 <b>방생 (DM)</b>\n"
        "  <code>방생</code> — 포켓몬 놓아주기\n"
        "  • 방생 시 친밀도 보너스 획득"
    ),
    "help_shop": (
        "🛒 <b>상점 · 거래소</b>\n"
        "━━━━━━━━━━━━━━━\n\n"
        "📍 <b>BP 상점 (DM)</b>\n"
        "  <code>상점</code> / <code>BP상점</code>\n"
        "  • 마스터볼, 하이퍼볼, 포켓볼 초기화 등\n\n"
        "📍 <b>프리미엄 상점 (DM, 구독자 전용)</b>\n"
        "  <code>프리미엄상점</code>\n"
        "  • 마스터볼 추가 구매 + 하이퍼볼 할인\n\n"
        "📍 <b>채팅상점 (채팅방, 채널장 전용)</b>\n"
        "  <code>채팅상점</code>\n"
        "  • 아케이드 속도 부스트, 시간 연장\n\n"
        "📍 <b>거래소 (DM)</b>\n"
        "  <code>거래소</code> — 거래소 둘러보기\n"
        "  <code>거래소 등록</code> — 포켓몬 판매 등록\n"
        "  <code>거래소 검색</code> — 검색\n"
        "  <code>거래소 내꺼</code> — 내 등록 목록"
    ),
    "help_pokedex": (
        "📖 <b>도감 · 칭호 · 상태</b>\n"
        "━━━━━━━━━━━━━━━\n\n"
        "📍 <b>DM에서 사용</b>\n"
        "  <code>상태창</code> — 내 전체 상태 확인\n"
        "  <code>도감</code> — 보유 도감 (등급/타입 필터)\n"
        "  <code>칭호</code> — 칭호 보기 & 장착\n"
        "  <code>칭호목록</code> — 전체 칭호 & 해금 조건\n"
        "  <code>미션</code> — 일일 미션 (채널경험치 보상)"
    ),
    "help_info": (
        "📊 <b>정보 · 유틸</b>\n"
        "━━━━━━━━━━━━━━━\n\n"
        "📍 <b>채팅방</b>\n"
        "  <code>랭킹</code> — 도감 완성 랭킹\n"
        "  <code>로그</code> — 최근 출현 기록\n"
        "  <code>날씨</code> — 현재 날씨 & 타입 보너스\n"
        "  <code>방정보</code> — 채널 레벨 & 경험치\n\n"
        "📍 <b>공통</b>\n"
        "  <code>대시보드</code> — 실시간 통계 웹페이지\n"
        "  <code>상성 [타입]</code> — 타입 상성표\n\n"
        "📍 <b>DM</b>\n"
        "  <code>수신거부</code> — 패치노트 수신 토글"
    ),
    "help_subscribe": (
        "💎 <b>월간 구독 서비스</b>\n"
        "━━━━━━━━━━━━━━━\n\n"
        "📍 <b>명령어 (DM)</b>\n"
        "  <code>구독</code> — 구독 티어 확인 & 결제\n"
        "  <code>구독정보</code> — 현재 구독 상태/혜택\n\n"
        "📍 <b>베이직</b> ($3.90/월)\n"
        "  포케볼 무제한 · 쿨다운 해제\n"
        "  마스터볼+1/일 · 하이퍼볼+5/일\n"
        "  BP 1.5배 · 미션 1.5배 · 프리미엄상점\n\n"
        "📍 <b>채널장</b> ($9.90/월)\n"
        "  베이직 전부 + 강제스폰 무제한\n"
        "  스폰률 +50% · 채팅상점 · 채널XP 1.5배\n\n"
        "  결제: Base 체인 USDC/USDT"
    ),
}

_HELP_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("🌿 포획", callback_data="help_catch"),
        InlineKeyboardButton("🍚 육성", callback_data="help_nurture"),
    ],
    [
        InlineKeyboardButton("⚔️ 배틀", callback_data="help_battle"),
        InlineKeyboardButton("🔄 교환·합성", callback_data="help_trade"),
    ],
    [
        InlineKeyboardButton("🛒 상점·거래소", callback_data="help_shop"),
        InlineKeyboardButton("📖 도감·칭호", callback_data="help_pokedex"),
    ],
    [
        InlineKeyboardButton("📊 정보", callback_data="help_info"),
        InlineKeyboardButton("💎 구독", callback_data="help_subscribe"),
    ],
])


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /도움말 command — 메인 도움말 + 버튼 네비게이션."""
    await update.message.reply_text(
        _HELP_MAIN,
        parse_mode="HTML",
        reply_markup=_HELP_KEYBOARD,
    )


async def help_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """도움말 인라인 버튼 콜백."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "help_main":
        await query.edit_message_text(
            _HELP_MAIN,
            parse_mode="HTML",
            reply_markup=_HELP_KEYBOARD,
        )
        return

    section_text = _HELP_SECTIONS.get(data)
    if not section_text:
        return

    back_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("← 메인 도움말", callback_data="help_main")],
    ])
    await query.edit_message_text(
        section_text,
        parse_mode="HTML",
        reply_markup=back_keyboard,
    )


# ─── 설정 (Settings) ───────────────────────────────

_SETTINGS_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("❓ 도움말", callback_data="settings_help"),
        InlineKeyboardButton("🌐 언어 변경", callback_data="settings_lang"),
    ],
])


async def settings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '설정' / 'settings' command — show settings menu."""
    logger.info(f"settings_handler triggered by {update.effective_user.id if update.effective_user else '?'}, text={update.message.text if update.message else '?'}")
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    current_label = LANG_LABELS.get(lang, LANG_LABELS["ko"])

    msg = (
        f"⚙️ <b>설정</b>\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"🌐 현재 언어: <b>{current_label}</b>\n"
        f"{'⚠️ <i>현재 던전, 포획 등 일부 메뉴만 다국어 지원됩니다.</i>' if lang != 'ko' else ''}\n"
    )
    await update.message.reply_text(
        msg,
        parse_mode="HTML",
        reply_markup=_SETTINGS_KEYBOARD,
    )


async def settings_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle settings inline button callbacks."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "settings_help":
        await query.edit_message_text(
            _HELP_MAIN,
            parse_mode="HTML",
            reply_markup=_HELP_KEYBOARD,
        )
    elif data == "settings_lang":
        user_id = update.effective_user.id
        lang = await get_user_lang(user_id)
        current_label = LANG_LABELS.get(lang, LANG_LABELS["ko"])
        context.user_data["_lang_change"] = True
        msg = (
            f"🌐 <b>언어 설정 / Language Settings</b>\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"현재 / Current: <b>{current_label}</b>\n\n"
            f"변경할 언어를 선택하세요.\n"
            f"Select your language."
        )
        await query.edit_message_text(
            msg,
            parse_mode="HTML",
            reply_markup=_LANG_SELECT_KEYBOARD,
        )
