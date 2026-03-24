"""Handler registration — all app.add_handler() calls in one place."""

from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from database import queries
from services.weather_service import get_current_weather, WEATHER_BOOSTS
import config

from handlers.start import (
    start_handler, help_handler, help_callback_handler,
    language_callback_handler, language_command_handler,
    settings_handler, settings_callback_handler,
)
from handlers.group import (
    catch_handler, master_ball_handler, hyper_ball_handler, priority_ball_handler,
    love_easter_egg, love_hidden_handler,
    attendance_handler, daily_money_handler, ranking_handler,
    log_handler, dashboard_handler, room_info_handler,
    my_pokemon_group_handler, on_chat_activity, close_message_callback,
    catch_keep_callback, catch_release_callback,
    shiny_ticket_spawn_handler, group_lang_handler,
    captcha_callback_handler,
)
from handlers.dm_pokedex import (
    pokedex_handler, pokedex_callback,
)
from handlers.dm_mypokemon import my_pokemon_handler
from handlers.dm_mypokemon_actions import my_pokemon_callback
from handlers.dm_title import (
    title_handler, title_callback, title_list_handler, title_list_callback,
    title_page_callback,
)
from handlers.dm_status import (
    status_handler, status_inline_callback,
    appraisal_handler, type_chart_handler,
)
from handlers.battle import (
    partner_handler, partner_callback_handler,
    battle_challenge_handler, battle_callback_handler, battle_result_callback_handler,
    battle_ranking_handler, battle_accept_text_handler, battle_decline_text_handler,
)
from handlers.battle_team import (
    team_handler, team_register_handler, team_clear_handler, team_select_handler,
    team_swap_handler, team_edit_menu_handler, team_callback_handler,
)
from handlers.battle_shop import (
    battle_stats_handler, bp_handler, bp_shop_handler, bp_buy_handler, shop_callback_handler,
    tier_handler,
)
from handlers.battle_ranked import (
    ranked_callback_handler,
    season_info_handler, ranked_ranking_handler,
    auto_ranked_handler,
)
from handlers.battle_yacha import (
    yacha_handler,
    yacha_response_callback, yacha_result_callback,
)
from handlers.dm_nurture import (
    feed_handler, play_handler, evolve_handler,
    nurture_callback_handler, nurture_menu_handler,
)
from handlers.dm_trade import trade_evo_choice_handler
from handlers.dm_market import (
    market_handler, market_register_handler, market_my_handler,
    market_cancel_handler, market_buy_handler, market_search_handler,
    market_callback_handler,
)
from handlers.group_trade import group_trade_handler, group_trade_callback_handler
from handlers.dm_mission import mission_handler
from handlers.dm_release import release_handler, release_callback
from handlers.dm_fusion import fusion_handler, fusion_callback
from handlers.dm_dungeon import dungeon_handler, dungeon_callback
from handlers.tutorial import tutorial_callback, tutorial_dm_handler, tutorial_dm_catch
from handlers.admin import (
    spawn_rate_handler, force_spawn_handler, force_spawn_reset_handler, ticket_force_spawn_handler,
    pokeball_reset_handler,
    event_start_handler, event_list_handler, event_end_handler, event_dm_callback,
    stats_handler, channel_list_handler, grant_masterball_handler, grant_bp_handler, grant_subscription_handler,
    arcade_handler, tournament_chat_handler, force_tournament_reg_handler, force_tournament_run_handler,
    manual_subscription_handler, report_handler,
)
from handlers.dm_subscription import (
    subscription_handler, subscription_callback_handler,
    subscription_status_handler, premium_shop_handler, channel_shop_handler,
    premium_hub_handler, premium_hub_callback_handler,
)
from handlers.tournament import tournament_join_handler
from handlers.dm_gacha import gacha_handler, gacha_callback_handler, item_handler, item_callback_handler
from handlers.dm_cs import dm_cs_start, cs_callback, cs_text_input

try:
    from handlers.camp import (
        camp_handler, camp_callback_handler, camp_round_job,
        camp_create_handler, camp_settings_handler, camp_map_handler, camp_visit_handler,
    )
    from handlers.dm_camp import (
        my_camp_handler, shiny_convert_handler, decompose_handler,
        camp_dm_callback_handler, home_camp_handler, camp_notify_handler,
        camp_guide_handler, camp_hub_handler, camp_welcome_input_handler,
    )
    HAS_CAMP = True
except ImportError:
    HAS_CAMP = False


# --- Small inline handlers ---

async def _optout_handler(update, context):
    """Handle '수신거부' DM command — toggle patch note opt-out."""
    user_id = update.effective_user.id
    await queries.ensure_user(user_id, update.effective_user.first_name or "트레이너")
    opted_out = await queries.toggle_patch_optout(user_id)
    if opted_out:
        await update.message.reply_text("🔕 패치노트 수신이 거부되었습니다.\n포획/미션 등 일반 DM은 정상 수신됩니다.\n\n다시 '수신거부'를 입력하면 해제됩니다.")
    else:
        await update.message.reply_text("🔔 패치노트 수신이 다시 활성화되었습니다!")


async def weather_handler(update, context):
    """Handle '날씨' command — show current weather and active boost."""
    weather = get_current_weather()
    if not weather.get("condition"):
        await update.message.reply_text("날씨 데이터를 아직 불러오지 못했습니다.")
        return

    boost_info = WEATHER_BOOSTS.get(weather["condition"], {})
    label = boost_info.get("label", "보통")
    emoji = boost_info.get("emoji", "")
    temp = weather.get("temp")
    temp_text = f" ({temp}°C)" if temp is not None else ""

    # 캐시가 2시간 이상 오래되면 안내
    from datetime import timedelta
    stale_text = ""
    updated_at = weather.get("updated_at")
    if updated_at and config.get_kst_now() - updated_at > timedelta(hours=2):
        stale_text = "\n⚠️ 날씨 데이터가 오래되었습니다. 곧 업데이트됩니다."

    await update.message.reply_text(
        f"🌍 현재 날씨{temp_text}\n"
        f"{emoji} {label}{stale_text}"
    )


# --- Main registration function ---

from telegram.ext import TypeHandler, ApplicationHandlerStop
from telegram import Update


async def _maintenance_gate(update, context):
    """점검 모드: 관리자만 통과, 나머지 완전 무응답 (봇 꺼진 것과 동일)."""
    if not config.MAINTENANCE_MODE:
        return
    user = update.effective_user
    if user and user.id in config.ADMIN_IDS:
        return
    # 일반 유저: 아무 응답 없이 차단 — 봇이 꺼진 것처럼 보임
    raise ApplicationHandlerStop()


def register_all_handlers(app):
    """Register all message/callback handlers on the Application."""

    # 점검 모드 게이트 — group=-1로 모든 핸들러보다 먼저 실행
    app.add_handler(TypeHandler(Update, _maintenance_gate), group=-1)

    dm = filters.ChatType.PRIVATE
    group = filters.ChatType.GROUPS

    # Latin commands (CommandHandler supports only [a-z0-9_])
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("pokedex", pokedex_handler, filters=dm))

    # Tutorial DM handlers (MUST be before other DM handlers)
    app.add_handler(MessageHandler(dm & filters.Regex(r"^튜토$"), tutorial_dm_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^[ㅊㅎㅁ]$"), tutorial_dm_catch))

    # Language change command (DM) — 언어/language/lang
    app.add_handler(MessageHandler(dm & filters.Regex(r"(?i)^(🌐\s*)?(언어|language|lang)$"), language_command_handler))

    # Patch note opt-out (수신거부)
    app.add_handler(MessageHandler(dm & filters.Regex(r"^수신거부$"), _optout_handler))

    # Korean commands via MessageHandler + Regex (DM only)
    # English/Chinese aliases added with | alternation — Korean commands always work
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(❓\s*)?(도움말|help)$"), help_handler))
    app.add_handler(MessageHandler((dm | group) & filters.Regex(r"(?i)^(📖\s*)?(도감|pokedex|图鉴|圖鑑)(\s+\S+)?$"), pokedex_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^날씨$"), weather_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"(?i)^(📦\s*)?(내포켓몬|mypokemon|my\s*pokemon|我的宝可梦|我的寶可夢)(\s+.+)?$"), my_pokemon_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(💪\s*)?친밀도강화$"), nurture_menu_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^밥(\s+.+)?$"), feed_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^놀기(\s+.+)?$"), play_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^진화(\s+.+)?$"), evolve_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^감정(\s+.+)?$"), appraisal_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^상성(\s+.+)?$"), type_chart_handler))
    # DM trade removed — replaced by group reply trade

    # Marketplace (DM) — 구체적 서브커맨드 먼저 등록
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🛒\s*)?(거래소|market)\s*(등록|register)\s+.+$"), market_register_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🛒\s*)?(거래소|market)\s*(취소|cancel)\s+.+$"), market_cancel_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🛒\s*)?(거래소|market)\s*(구매|buy)\s+.+$"), market_buy_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🛒\s*)?(거래소|market)\s*(검색|search)\s+.+$"), market_search_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🛒\s*)?(거래소|market)\s*(내꺼|mine)$"), market_my_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🛒\s*)?(거래소|market)$"), market_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(방생|release)$"), release_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(합성|fusion)$"), fusion_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"(?i)^(🏰\s*)?(던전|dungeon|地牢)$"), dungeon_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"(?i)^(📋\s*|📌\s*)?(미션|mission|任务|任務)$"), mission_handler))

    # Subscription / Premium system (DM + Group)
    app.add_handler(MessageHandler(dm & filters.Regex(r"(?i)^(💎\s*)?(프리미엄|premium|高级|高級)$"), premium_hub_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(💎\s*)?(구독|subscribe)$"), subscription_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^구독정보$"), subscription_status_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(💎\s*)?프리미엄상점$"), premium_shop_handler))
    app.add_handler(MessageHandler((dm | group) & filters.Regex(r"^채팅상점$"), channel_shop_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(📋\s*)?(칭호목록|titles)$"), title_list_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🏷️\s*)?(칭호|title)$"), title_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"(?i)^(📋\s*)?(상태창|status|状态|狀態)$"), status_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"(?i)^(⚙️\s*)?(설정|settings|设置|設定)$"), settings_handler))

    # CS 문의 시스템
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(📩\s*)?문의$"), dm_cs_start))
    async def _cs_text_wrapper(update, context):
        await cs_text_input(update, context)
    app.add_handler(MessageHandler(dm & filters.TEXT & ~filters.COMMAND, _cs_text_wrapper), group=-3)

    # Camp system v2 (DM)
    if HAS_CAMP:
        # 환영 멘트 입력 (가장 먼저 — 상태가 아니면 무시)
        app.add_handler(MessageHandler(dm & filters.TEXT & ~filters.COMMAND, camp_welcome_input_handler), group=-2)
        app.add_handler(MessageHandler(dm & filters.Regex(r"(?i)^(🏕\s*)?(캠프|camp|营地|營地)$"), camp_hub_handler))
        app.add_handler(MessageHandler(dm & filters.Regex(r"^내캠프$"), my_camp_handler))
        app.add_handler(MessageHandler(dm & filters.Regex(r"^거점캠프$"), home_camp_handler))
        app.add_handler(MessageHandler(dm & filters.Regex(r"^캠프알림$"), camp_notify_handler))
        app.add_handler(MessageHandler(dm & filters.Regex(r"^캠프가이드$"), camp_guide_handler))
        app.add_handler(MessageHandler(dm & filters.Regex(r"^이로치전환$"), shiny_convert_handler))
        app.add_handler(MessageHandler(dm & filters.Regex(r"^분해$"), decompose_handler))

    # Battle system (DM)
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🤝\s*)?파트너(\s+.+)?$"), partner_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(✏️\s*)?팀편집$"), team_edit_menu_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^팀등록[12]?(\s+.+)?$"), team_register_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^팀해제[12]?$"), team_clear_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^팀선택(\s+.+)?$"), team_select_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^팀스왑$"), team_swap_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(⚔️\s*)?팀[12]?$"), team_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🏆\s*)?배틀전적$"), battle_stats_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"(?i)^(⚔️\s*)?(랭크전|ranked|排位赛|排位賽)$"), battle_stats_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"(?i)^(bp)?구매(\s+.+)?$"), bp_buy_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"(?i)^(🏪\s*)?(bp)?(상점|shop|商店)$"), bp_shop_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"(?i)^bp$"), bp_handler))
    # 가챠 (뽑기) + 아이템
    app.add_handler(MessageHandler(dm & filters.Regex(r"(?i)^(🎰\s*)?(뽑기|가챠|gacha|扭蛋|轉蛋)$"), gacha_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"(?i)^(🎒\s*)?(아이템|items?|道具)$"), item_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^티어$"), tier_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^시즌$"), season_info_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(시즌)?랭킹$"), ranked_ranking_handler))

    # Admin commands (DM)
    app.add_handler(MessageHandler(dm & filters.Regex(r"^통계$"), stats_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^채널목록$"), channel_list_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^이벤트시작(\s+.+)?$"), event_start_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^이벤트목록$"), event_list_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^이벤트종료(\s+.+)?$"), event_end_handler))
    app.add_handler(MessageHandler((dm | group) & filters.Regex(r"^마볼지급\s+.+$"), grant_masterball_handler))
    app.add_handler(MessageHandler((dm | group) & filters.Regex(r"^BP지급\s+.+$"), grant_bp_handler))
    app.add_handler(MessageHandler((dm | group) & filters.Regex(r"^구독권지급\s+.+$"), grant_subscription_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^아케이드(\s+.+)?$"), arcade_handler))
    app.add_handler(MessageHandler((dm | group) & filters.Regex(r"^대회방(등록|해제)$"), tournament_chat_handler))
    app.add_handler(MessageHandler((dm | group) & filters.Regex(r"^대회시작$"), force_tournament_reg_handler))
    app.add_handler(MessageHandler((dm | group) & filters.Regex(r"^대회진행$"), force_tournament_run_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^구독승인\s+.+$"), manual_subscription_handler))
    app.add_handler(MessageHandler(dm & filters.Regex(r"^!리포트\s+\d{4}$"), report_handler))

    # Group trade (reply with '교환')
    app.add_handler(MessageHandler(group & filters.Regex(r"^교환\s+.+$"), group_trade_handler))

    # Pokeball recharge
    app.add_handler(MessageHandler(group & filters.Regex(r"^포켓볼\s*충전$"), love_easter_egg))

    # Hidden easter egg
    app.add_handler(MessageHandler(group & filters.Regex(r"^문유\s*사랑해$"), love_hidden_handler))

    # Attendance
    app.add_handler(MessageHandler(group & filters.Regex(r"^출석$"), attendance_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^!돈$"), daily_money_handler))

    # Group Korean commands
    app.add_handler(MessageHandler(group & filters.Regex(r"^랭킹$"), ranking_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^로그$"), log_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^날씨$"), weather_handler))
    app.add_handler(MessageHandler((group | dm) & filters.Regex(r"^대시보드$"), dashboard_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^방정보$"), room_info_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^내포켓몬\s+\S+$"), my_pokemon_group_handler))

    # Camp system v2 (Group)
    if HAS_CAMP:
        app.add_handler(MessageHandler(group & filters.Regex(r"^캠프$"), camp_handler))
        app.add_handler(MessageHandler(group & filters.Regex(r"^캠프개설$"), camp_create_handler))
        app.add_handler(MessageHandler(group & filters.Regex(r"^캠프설정$"), camp_settings_handler))
        app.add_handler(MessageHandler(group & filters.Regex(r"^캠프맵$"), camp_map_handler))
        app.add_handler(MessageHandler(group & filters.Regex(r"^방문$"), camp_visit_handler))

    # Group language setting
    app.add_handler(MessageHandler(group & filters.Regex(r"(?i)^(언어설정|setlang|语言设置|語言設定)(\s+\S+)?$"), group_lang_handler))

    # Battle system (Group)
    app.add_handler(MessageHandler(group & filters.Regex(r"^배틀$"), battle_challenge_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^배틀랭킹$"), battle_ranking_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^배틀수락$"), battle_accept_text_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^배틀거절$"), battle_decline_text_handler))

    # DM auto-ranked battle
    app.add_handler(MessageHandler(dm & filters.Regex(r"^(🏟️\s*)?랭전$"), auto_ranked_handler))

    # Yacha (Betting Battle) — group only
    app.add_handler(MessageHandler(group & filters.Regex(r"^야차$"), yacha_handler))

    # Admin group commands
    app.add_handler(MessageHandler(group & filters.Regex(r"^스폰배율(\s+.+)?$"), spawn_rate_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^\s*강스(\s+.*)?$"), force_spawn_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^\s*강스권\s*$"), ticket_force_spawn_handler))
    app.add_handler(MessageHandler(group & filters.Regex(r"^\s*이로치\s*강스(\s+.*)?$"), shiny_ticket_spawn_handler))
    app.add_handler(MessageHandler(filters.Regex(r"^\s*강제스폰 채널 초기화\s*$"), force_spawn_reset_handler))
    app.add_handler(MessageHandler(filters.Regex(r"^\s*포켓볼초기화\s*$"), pokeball_reset_handler))
    app.add_handler(MessageHandler(filters.Regex(r"^\s*어뷰징초기화(\s+.+)?$"), abuse_reset_handler))
    app.add_handler(MessageHandler(filters.Regex(r"^\s*어뷰징상세(\s+.+)?$"), abuse_detail_handler))
    app.add_handler(MessageHandler(filters.Regex(r"^\s*어뷰징\s*$"), abuse_list_handler))

    # "ㅊㅊ" priority ball handler (group only, exact match) — ㅊ보다 먼저 등록
    app.add_handler(MessageHandler(
        group & filters.TEXT & filters.Regex(r"^ㅊㅊ$"),
        priority_ball_handler,
    ))

    # "ㅊ" / "c" catch handler (group only, exact match)
    app.add_handler(MessageHandler(
        group & filters.TEXT & filters.Regex(r"(?i)^(ㅊ|c)$"),
        catch_handler,
    ))

    # "ㅁ" / "m" master ball handler (group only, exact match)
    app.add_handler(MessageHandler(
        group & filters.TEXT & filters.Regex(r"(?i)^(ㅁ|m)$"),
        master_ball_handler,
    ))

    # "ㅎ" / "h" hyper ball handler (group only, exact match)
    app.add_handler(MessageHandler(
        group & filters.TEXT & filters.Regex(r"(?i)^(ㅎ|h)$"),
        hyper_ball_handler,
    ))

    # "ㄷ" tournament join (group only, arcade channels)
    app.add_handler(MessageHandler(
        group & filters.TEXT & filters.Regex(r"^ㄷ$"),
        tournament_join_handler,
    ))

    # Language selection callback
    app.add_handler(CallbackQueryHandler(language_callback_handler, pattern=r"^lang_"))

    # Settings callback
    app.add_handler(CallbackQueryHandler(settings_callback_handler, pattern=r"^settings_"))

    # Status inline callback (칭호/도감 바로가기)
    app.add_handler(CallbackQueryHandler(status_inline_callback, pattern=r"^status_"))

    # Close message callback (❌ button)
    app.add_handler(CallbackQueryHandler(close_message_callback, pattern=r"^close_msg$"))

    # Catch DM: keep / release callbacks
    app.add_handler(CallbackQueryHandler(catch_keep_callback, pattern=r"^catch_keep_\d+$"))
    app.add_handler(CallbackQueryHandler(catch_release_callback, pattern=r"^catch_release_\d+$"))

    # Pokedex pagination callback
    app.add_handler(CallbackQueryHandler(pokedex_callback, pattern=r"^dex_"))

    # My Pokemon pagination callback
    app.add_handler(CallbackQueryHandler(my_pokemon_callback, pattern=r"^mypoke_"))

    # Release (방생) callback
    app.add_handler(CallbackQueryHandler(release_callback, pattern=r"^rel_"))

    # Fusion (합성) callback
    app.add_handler(CallbackQueryHandler(fusion_callback, pattern=r"^fus_"))

    # Dungeon (던전) callback
    app.add_handler(CallbackQueryHandler(dungeon_callback, pattern=r"^dg_"))

    # Title selection callback
    app.add_handler(CallbackQueryHandler(title_callback, pattern=r"^title_"))
    # Title list pagination callback
    app.add_handler(CallbackQueryHandler(title_list_callback, pattern=r"^tlist_"))
    # Title selection pagination callback
    app.add_handler(CallbackQueryHandler(title_page_callback, pattern=r"^titlep_"))

    # Partner selection callback
    app.add_handler(CallbackQueryHandler(partner_callback_handler, pattern=r"^partner_"))

    # Team selection callback
    app.add_handler(CallbackQueryHandler(team_callback_handler, pattern=r"^t(edit|slot_view|pick|rem|p|f|cl|done|cancel|del|swap|swap_cancel|sw)_"))

    # Battle accept/decline callback
    app.add_handler(CallbackQueryHandler(battle_callback_handler, pattern=r"^battle_"))

    # Ranked battle accept/decline callback
    app.add_handler(CallbackQueryHandler(ranked_callback_handler, pattern=r"^ranked_"))

    # Battle result detail/skip/teabag callback
    app.add_handler(CallbackQueryHandler(battle_result_callback_handler, pattern=r"^b(detail|skip|tbag)_"))

    # Shop purchase callback
    app.add_handler(CallbackQueryHandler(shop_callback_handler, pattern=r"^shop_"))

    # 가챠 (뽑기) callbacks
    app.add_handler(CallbackQueryHandler(gacha_callback_handler, pattern=r"^gacha_"))
    # 아이템 사용 callbacks
    app.add_handler(CallbackQueryHandler(item_callback_handler, pattern=r"^(item_|ivr_|ivstone_|egg_hatch_|sct_|trt_)"))

    # Nurture (feed/play/evolve) duplicate selection callbacks
    app.add_handler(CallbackQueryHandler(nurture_callback_handler, pattern=r"^nurt_"))

    # Marketplace callbacks
    app.add_handler(CallbackQueryHandler(market_callback_handler, pattern=r"^mkt_"))

    # Trade evolution choice callbacks
    app.add_handler(CallbackQueryHandler(trade_evo_choice_handler, pattern=r"^tevo_"))

    # Group trade callbacks
    app.add_handler(CallbackQueryHandler(group_trade_callback_handler, pattern=r"^gtrade_"))

    # Tutorial onboarding callbacks
    app.add_handler(CallbackQueryHandler(tutorial_callback, pattern=r"^tut_"))

    # Yacha (betting battle) callbacks
    app.add_handler(CallbackQueryHandler(yacha_response_callback, pattern=r"^yacha_"))
    app.add_handler(CallbackQueryHandler(yacha_result_callback, pattern=r"^yres_"))

    # Captcha callbacks
    app.add_handler(CallbackQueryHandler(captcha_callback_handler, pattern=r"^captcha_"))

    # Help navigation callbacks
    app.add_handler(CallbackQueryHandler(help_callback_handler, pattern=r"^help_"))

    # Premium hub callbacks (pmenu_subscribe, pmenu_shop, pmenu_guide, pmenu_status)
    app.add_handler(CallbackQueryHandler(premium_hub_callback_handler, pattern=r"^pmenu_"))

    # Subscription callbacks (sub_tier_, sub_token_, sub_check_, sub_cancel_, sub_back, sub_status, sub_pshop_, sub_cshop_)
    app.add_handler(CallbackQueryHandler(subscription_callback_handler, pattern=r"^sub_"))

    # Event DM broadcast callback
    app.add_handler(CallbackQueryHandler(event_dm_callback, pattern=r"^evt_dm_"))

    # Camp callbacks
    if HAS_CAMP:
        app.add_handler(CallbackQueryHandler(camp_callback_handler, pattern=r"^camp_"))
        app.add_handler(CallbackQueryHandler(camp_dm_callback_handler, pattern=r"^cdm_"))

    # CS 문의 콜백
    app.add_handler(CallbackQueryHandler(cs_callback, pattern=r"^cs_"))

    # Activity tracker — runs for every group text message (handler group -1)
    app.add_handler(
        MessageHandler(group & filters.TEXT, on_chat_activity),
        group=-1,
    )
