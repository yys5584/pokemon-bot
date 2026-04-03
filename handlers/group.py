"""Group chat handlers: hub module with re-exports + activity tracking + bot detection (disabled)."""

import asyncio
import logging

from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config

from database import queries, spawn_queries
from services.tournament_service import is_tournament_active
# abuse_service 비활성화 (2026-03-17)
# from services.abuse_service import (
#     record_reaction, should_challenge, create_challenge,
#     get_pending_challenge, resolve_challenge, handle_challenge_timeout,
#     clear_challenge, is_challenge_expired, CHALLENGE_TIMEOUT_SEC,
#     is_catch_locked, format_lock_duration,
# )
from utils.helpers import get_decorated_name, ball_emoji
from utils.honorific import format_actor
from utils.i18n import t, get_group_lang, get_user_lang

logger = logging.getLogger(__name__)

# ── Re-exports for backward compatibility ──────────────────────
from handlers.group_catch import (  # noqa: F401
    catch_handler, master_ball_handler, hyper_ball_handler, priority_ball_handler,
    catch_keep_callback, catch_release_callback,
    _catch_locks,
)
from handlers.group_rewards import (  # noqa: F401
    love_easter_egg, love_hidden_handler,
    attendance_handler, daily_money_handler,
)
from handlers.group_commands import (  # noqa: F401
    ranking_handler, log_handler, dashboard_handler,
    room_info_handler, my_pokemon_group_handler, group_mypoke_callback,
    shiny_ticket_spawn_handler, group_lang_handler,
)

# Activity tracking cooldown: skip DB writes if recently tracked (per chat)
_activity_cooldown: dict[int, float] = {}  # chat_id -> last_tracked_timestamp
_ACTIVITY_COOLDOWN_SEC = 300  # 5분에 1번만 DB 기록


async def close_message_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle ❌ button press — delete the bot message to reduce scroll clutter."""
    query = update.callback_query
    if not query:
        return
    try:
        await query.message.delete()
    except Exception:
        lang = await get_group_lang(query.message.chat_id) if query.message else "ko"
        await query.answer(t(lang, "group.close_msg_fail"))
        return
    await query.answer()


async def on_chat_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Track message activity for spawn eligibility. Runs for every group message.
    Non-blocking: fires DB ops in background so message processing isn't delayed.
    Uses 5-min cooldown per chat to reduce DB writes by ~90%."""
    if not update.effective_chat or not update.effective_message:
        return

    import time as _time
    chat_id = update.effective_chat.id
    now = _time.monotonic()

    last = _activity_cooldown.get(chat_id, 0)
    if now - last < _ACTIVITY_COOLDOWN_SEC:
        return
    _activity_cooldown[chat_id] = now

    if len(_activity_cooldown) > 100:
        cutoff = now - _ACTIVITY_COOLDOWN_SEC * 2
        expired = [k for k, v in _activity_cooldown.items() if v < cutoff]
        for k in expired:
            del _activity_cooldown[k]

    chat_title = update.effective_chat.title
    chat_username = getattr(update.effective_chat, "username", None)
    invite_link = f"https://t.me/{chat_username}" if chat_username else None
    hour_bucket = config.get_kst_now().strftime("%Y-%m-%d-%H")

    async def _bg_track():
        nonlocal invite_link
        try:
            if not invite_link:
                try:
                    chat_info = await context.bot.get_chat(chat_id)
                    if chat_info.invite_link:
                        invite_link = chat_info.invite_link
                    else:
                        invite_link = await context.bot.export_chat_invite_link(chat_id)
                except Exception:
                    pass
            await spawn_queries.increment_activity(chat_id, hour_bucket)
            await queries.ensure_chat_room(chat_id, title=chat_title,
                                           invite_link=invite_link)
        except Exception as e:
            logger.error(f"Activity tracking failed: {e}")

    asyncio.create_task(_bg_track())


# ─── 봇방지: 챌린지 DM 전송 (비활성) ────────────────
async def _send_challenge_dm(context, user_id: int, session: dict) -> bool:
    """챌린지 DM 전송. 이미 pending이면 False, 새로 보냈으면 True."""
    existing = get_pending_challenge(user_id)
    if existing:
        return False

    pokemon_name = session.get("name_ko", "")
    if not pokemon_name:
        return False

    ch = create_challenge(user_id, session["id"], pokemon_name)
    try:
        from utils.card_generator import generate_card
        pokemon_id = session.get("pokemon_id", session.get("id", 0))
        rarity = session.get("rarity", "common")
        emoji = session.get("emoji", "")
        is_shiny = bool(session.get("is_shiny", 0))

        loop = asyncio.get_event_loop()
        card_buf = await loop.run_in_executor(
            None, generate_card, pokemon_id, pokemon_name, rarity, emoji, is_shiny,
        )

        choices = ch["choices"]
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(choices[0], callback_data=f"abot_{ch['session_id']}_{choices[0]}"),
             InlineKeyboardButton(choices[1], callback_data=f"abot_{ch['session_id']}_{choices[1]}")],
            [InlineKeyboardButton(choices[2], callback_data=f"abot_{ch['session_id']}_{choices[2]}"),
             InlineKeyboardButton(choices[3], callback_data=f"abot_{ch['session_id']}_{choices[3]}")],
        ])

        await context.bot.send_photo(
            chat_id=user_id,
            photo=card_buf,
            caption=(
                "🚨 <b>비정상 포획 감지</b>\n\n"
                "자동 포획이 의심됩니다.\n"
                "본인 확인을 위해 이 포켓몬의 이름을 선택하세요. (5분)"
            ),
            parse_mode="HTML",
            reply_markup=keyboard,
        )

        async def _challenge_timeout(uid=user_id):
            await asyncio.sleep(CHALLENGE_TIMEOUT_SEC + 1)
            ch_now = get_pending_challenge(uid)
            if ch_now and not ch_now.get("answered"):
                await handle_challenge_timeout(uid)
                _, remain = is_catch_locked(uid)
                lock_text = f"\n🔒 포획 잠금: {format_lock_duration(remain)}" if remain else ""
                try:
                    await context.bot.send_message(
                        chat_id=uid,
                        text=f"⏰ 시간 초과! 포획이 취소되었습니다.{lock_text}",
                    )
                except Exception:
                    pass
        asyncio.create_task(_challenge_timeout())
        return True
    except Exception:
        clear_challenge(user_id)
        return False


# ─── 봇방지: 챌린지 콜백 핸들러 (DM 버튼) ────────────────
async def challenge_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """DM 4지선다 버튼 응답 처리. callback_data: abot_{session_id}_{answer}"""
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("abot_"):
        return

    user_id = update.effective_user.id
    await query.answer()

    ch = get_pending_challenge(user_id)
    if not ch:
        await query.edit_message_caption(caption="⚠️ 이미 처리된 챌린지입니다.")
        return

    if ch.get("answered"):
        return

    parts = query.data.split("_", 2)
    if len(parts) < 3:
        return
    answer = parts[2]

    if is_challenge_expired(ch):
        await handle_challenge_timeout(user_id)
        _, remain = is_catch_locked(user_id)
        lock_msg = f"\n🔒 포획 잠금: {format_lock_duration(remain)}" if remain else ""
        await query.edit_message_caption(
            caption=f"⏰ 시간이 초과되어 포획이 취소되었습니다.{lock_msg}"
        )
        return

    ch["answered"] = True
    from services.catch_service import record_attempt
    from services.spawn_service import track_attempt_message
    passed = await resolve_challenge(user_id, answer)

    if passed:
        await query.edit_message_caption(caption="✅ 검증 통과! 포획에 참여합니다.")

        session_id = ch["session_id"]
        try:
            await record_attempt(session_id, user_id)

            try:
                from database.connection import get_db as _get_db
                from services.abuse_service import record_reaction
                pool = await _get_db()
                sess = await pool.fetchrow(
                    "SELECT spawned_at, chat_id FROM spawn_sessions WHERE id = $1", session_id
                )
                if sess:
                    await record_reaction(user_id, session_id, sess["spawned_at"], datetime.now(tz=timezone.utc), chat_id=sess.get("chat_id", 0))
            except Exception:
                pass

            sess_row = await spawn_queries.get_spawn_session_by_id(session_id)
            if sess_row and not sess_row.get("is_resolved"):
                chat_id = sess_row["chat_id"]
                _chat_lang = await get_group_lang(chat_id) if chat_id else "ko"
                display_name = update.effective_user.first_name or t(_chat_lang, "common.trainer")
                username = update.effective_user.username
                user = await queries.get_user(user_id)

                from services.subscription_service import get_user_tier
                from services.ranked_service import current_season_id
                from database import ranked_queries as rq
                sub_tier, season_rec = await asyncio.gather(
                    get_user_tier(user_id),
                    rq.get_season_record(user_id, current_season_id()),
                )
                if season_rec and season_rec.get("rp") is not None:
                    _tk, _dv, _ = config.get_division_info(season_rec["rp"])
                    if season_rec.get("tier") == "challenger":
                        _tk = "challenger"
                        _dv = 0
                    r_badge = config.get_ranked_badge_html(_tk, _dv)
                else:
                    r_badge = config.get_ranked_badge_html("bronze", 2)

                decorated = get_decorated_name(
                    display_name,
                    user.get("title", "") if user else "",
                    user.get("title_emoji", "") if user else "",
                    username,
                    html=True,
                    ranked_badge=r_badge,
                )
                throw_text = format_actor(decorated, t(_chat_lang, "group.threw_pokeball"), sub_tier, lang=_chat_lang)
                attempt_msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"{ball_emoji('pokeball')} {throw_text}",
                    parse_mode="HTML",
                )
                track_attempt_message(session_id, chat_id, attempt_msg.message_id)
        except Exception as e:
            logger.error(f"Challenge pass → record_attempt failed: {e}")
    else:
        expected = ch.get("expected", "???")
        _, remain = is_catch_locked(user_id)
        lock_msg = f"\n🔒 포획 잠금: {format_lock_duration(remain)}" if remain else ""
        await query.edit_message_caption(
            caption=f"❌ 오답입니다! (정답: {expected})\n이번 포획은 취소되었습니다.{lock_msg}"
        )
        asyncio.create_task(_notify_admin_if_needed(user_id, context))


# 레거시 텍스트 입력 핸들러 (하위호환 — 버튼 사용 안내)
async def challenge_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """DM 텍스트 입력 시 버튼 사용 안내."""
    if not update.effective_user or not update.message or not update.message.text:
        return
    user_id = update.effective_user.id
    ch = get_pending_challenge(user_id)
    if not ch or ch.get("answered"):
        return
    await update.message.reply_text("위 메시지의 버튼을 눌러 포켓몬 이름을 선택해주세요.")


async def _notify_admin_if_needed(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """챌린지 연속 실패 시 관리자에게 DM 알림."""
    try:
        from services.abuse_service import get_bot_score
        score = await get_bot_score(user_id)
        if score >= 0.8:
            user = await queries.get_user(user_id)
            name = user.get("display_name", "???") if user else "???"
            uname = user.get("username", "") if user else ""
            uname_str = f" (@{uname})" if uname else ""
            await context.bot.send_message(
                chat_id=config.ADMIN_IDS[0] if config.ADMIN_IDS else 0,
                text=(
                    f"🚨 <b>봇 의심 유저 알림</b>\n\n"
                    f"유저: {name}{uname_str}\n"
                    f"ID: <code>{user_id}</code>\n"
                    f"봇 점수: <b>{score:.2f}</b>\n\n"
                    f"<code>/어뷰징상세 {user_id}</code> 로 확인"
                ),
                parse_mode="HTML",
            )
    except Exception as e:
        logger.warning(f"_notify_admin_if_needed error: {e}")


async def captcha_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """관리자 수동 캡차 콜백. callback_data: captcha_{uid}_{answer}"""
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("captcha_"):
        return

    user_id = query.from_user.id
    parts = query.data.split("_", 2)
    if len(parts) < 3:
        await query.answer()
        return

    expected_uid = int(parts[1])
    answer = parts[2]

    if user_id != expected_uid:
        await query.answer("본인만 응답할 수 있습니다.", show_alert=True)
        return

    await query.answer()

    # 메시지에서 정답 추출: "중 OOO을(를)" 패턴
    import re
    text = query.message.text or ""
    match = re.search(r"중\s+(.+?)을\(를\)|중\s+(.+?)을\s|중\s+(.+?)를\s", text)
    correct = None
    if match:
        correct = (match.group(1) or match.group(2) or match.group(3)).strip()
    if not correct:
        # fallback: 버튼 4개 중 메시지 본문에 이름이 언급된 것
        keyboard = query.message.reply_markup
        if keyboard:
            for row in keyboard.inline_keyboard:
                for btn in row:
                    if btn.text and btn.text in text:
                        correct = btn.text
                        break
                if correct:
                    break
    if not correct:
        await query.edit_message_text("⚠️ 챌린지 오류. 관리자에게 문의하세요.")
        return

    if answer == correct:
        await query.edit_message_text("✅ 검증 통과! 정상 유저로 확인되었습니다.")
        # watched 해제 + 위반 카운터 초기화
        try:
            from database.connection import get_db
            pool = await get_db()
            await pool.execute(
                "UPDATE abuse_scores SET is_watched = FALSE, updated_at = NOW() WHERE user_id = $1",
                user_id)
            from handlers.group_catch import _captcha_violation_count
            _captcha_violation_count.pop(user_id, None)
        except Exception:
            pass
    else:
        await query.edit_message_text(
            f"❌ 오답! 정답은 <b>{correct}</b>이었습니다.\n"
            f"🔒 1시간 동안 포획이 제한됩니다.",
            parse_mode="HTML")
        # 1시간 잠금
        from services.abuse_service import _apply_catch_lock
        _apply_catch_lock(user_id)


# ── 데일리 운세 (그룹) ──

_horoscope_cooldown: dict[int, float] = {}  # user_id -> timestamp
HOROSCOPE_COOLDOWN_SEC = 180  # 3분


async def horoscope_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """그룹 '운세' 명령 → 데일리 별자리 운세."""
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return

    # 3분 쿨다운
    import time
    now = time.time()
    last = _horoscope_cooldown.get(user.id, 0)
    if now - last < HOROSCOPE_COOLDOWN_SEC:
        remaining = int(HOROSCOPE_COOLDOWN_SEC - (now - last))
        await msg.reply_text(f"⏳ {remaining}초 후에 다시 시도해주세요.")
        return
    _horoscope_cooldown[user.id] = now

    # 생년월일 확인
    from handlers.dm_fortune import _get_birth_date
    birth_date = await _get_birth_date(user.id)
    if not birth_date:
        await msg.reply_text(
            "🌟 운세를 보려면 생년월일이 필요해요!\n"
            "📩 DM에서 <b>타로</b>를 입력해 생년월일을 등록해주세요.",
            parse_mode="HTML",
        )
        return

    from services.horoscope_service import get_daily_horoscope, format_horoscope_group
    data = await get_daily_horoscope(birth_date, user.first_name)
    if not data:
        await msg.reply_text("운세 생성에 실패했어요. 잠시 후 다시 시도해주세요.")
        return

    display_name = user.first_name or "트레이너"
    text = format_horoscope_group(data, display_name)

    # 첫 운세 시 성격변경권 1개 지급 (DB 기반 중복 방지)
    from handlers.dm_fortune import _check_horoscope_rewarded_today, _mark_horoscope_rewarded
    already_rewarded = await _check_horoscope_rewarded_today(user.id)
    if not already_rewarded:
        from database import item_queries
        await item_queries.add_user_item(user.id, "personality_ticket", 1)
        await _mark_horoscope_rewarded(user.id)
        text += "\n\n🎭 <i>성격변경권 1개를 받았어요!</i>"
    await msg.reply_text(text, parse_mode="HTML")
