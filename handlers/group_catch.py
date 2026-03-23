"""Group catch handlers: ㅊ (pokeball), ㅁ (master ball), ㅎ (hyper ball), catch DM callbacks."""

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

import config

from database import queries, spawn_queries
from database import battle_queries as bq
from services.catch_service import can_attempt_catch, record_attempt
from services.spawn_service import track_attempt_message
from services.tournament_service import is_tournament_active
from utils.helpers import get_decorated_name, schedule_delete, ball_emoji
from utils.honorific import format_actor
from utils.i18n import t, get_group_lang, get_user_lang

logger = logging.getLogger(__name__)

# Prevent duplicate catch from rapid ㅊㅊ (race condition guard)
_catch_locks: set[tuple[int, int]] = set()  # (session_id, user_id)

# 캡차 미응답 포획 카운터 {user_id: count}
_captcha_violation_count: dict[int, int] = {}


CAPTCHA_AUTO_BAN_THRESHOLD = 15  # 이 횟수 이상 누적 시 자동 24시간 정지
CAPTCHA_AUTO_BAN_DURATION = 86400  # 24시간 (초)


async def _check_captcha_violation(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """watched 유저가 캡차 미응답 상태로 포획 시도 시 카운팅.
    15회 이상 누적 시 24시간 자동 정지."""
    try:
        from database.connection import get_db
        pool = await get_db()
        watched = await pool.fetchval(
            "SELECT is_watched FROM abuse_scores WHERE user_id = $1", user_id)
        if not watched:
            return False
        # 캡차 미응답 상태로 포획 = 위반 누적
        _captcha_violation_count[user_id] = _captcha_violation_count.get(user_id, 0) + 1
        cnt = _captcha_violation_count[user_id]

        # 자동 정지: 임계치 도달 시 24시간 포획 차단
        if cnt >= CAPTCHA_AUTO_BAN_THRESHOLD and cnt % CAPTCHA_AUTO_BAN_THRESHOLD == 0:
            from services.abuse_service import _apply_catch_lock
            strike, duration = _apply_catch_lock(user_id, duration_override=CAPTCHA_AUTO_BAN_DURATION)
            _captcha_violation_count[user_id] = 0  # 카운터 리셋
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"🔒 <b>캡차 무시로 24시간 포획 정지!</b>\n\n"
                        f"캡차를 {cnt}회 연속 무시하여 자동 제재되었습니다.\n"
                        f"24시간 후 포획이 다시 가능합니다."
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass
            # 관리자 알림
            try:
                user = await pool.fetchrow("SELECT display_name, username FROM users WHERE user_id = $1", user_id)
                uname = f"@{user['username']}" if user and user['username'] else ""
                dname = user['display_name'] if user else str(user_id)
                await context.bot.send_message(
                    chat_id=config.ADMIN_IDS[0],
                    text=f"🔒 캡차 무시 자동 정지: <b>{dname}</b> {uname} — {cnt}회 누적 → 24시간 차단",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return True  # 포획 차단

        # 3회마다 경고
        if cnt % 3 == 0:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"⚠️ <b>캡차 미응답 경고 ({cnt}회 누적)</b>\n\n"
                        f"캡차를 풀지 않고 포획을 계속하고 있습니다.\n"
                        f"지금 즉시 위 캡차를 풀어주세요!\n\n"
                        f"🔒 {CAPTCHA_AUTO_BAN_THRESHOLD}회 누적 시 <b>24시간 자동 정지</b>됩니다."
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass
            # 관리자에게도 알림
            try:
                user = await pool.fetchrow("SELECT display_name, username FROM users WHERE user_id = $1", user_id)
                uname = f"@{user['username']}" if user and user['username'] else ""
                dname = user['display_name'] if user else str(user_id)
                await context.bot.send_message(
                    chat_id=config.ADMIN_IDS[0],
                    text=f"🚨 캡차 무시 감지: <b>{dname}</b> {uname} — {cnt}회 누적 포획",
                    parse_mode="HTML",
                )
            except Exception:
                pass
    except Exception:
        pass
    return False


async def _get_ranked_badge(user_id: int, season_rec: dict | None) -> str:
    """공통: 시즌 레코드에서 랭크 뱃지 HTML 생성."""
    if season_rec and season_rec.get("rp") is not None:
        _tk, _dv, _ = config.get_division_info(season_rec["rp"])
        if season_rec.get("tier") == "challenger":
            _tk = "challenger"
            _dv = 0
        return config.get_ranked_badge_html(_tk, _dv)
    return config.get_ranked_badge_html("bronze", 2)



async def catch_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'ㅊ' message in group chat — attempt to catch a Pokemon."""
    if not update.effective_user or not update.effective_chat:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    lang = await get_user_lang(user_id)
    display_name = update.effective_user.first_name or t(lang, "common.trainer")
    username = update.effective_user.username

    if is_tournament_active(chat_id):
        return

    # 포획 잠금 체크
    from services.abuse_service import is_catch_locked_async
    locked, _ = await is_catch_locked_async(user_id)
    if locked:
        schedule_delete(update.message, config.AUTO_DEL_CATCH_CMD)
        return

    schedule_delete(update.message, config.AUTO_DEL_CATCH_CMD)
    await _check_captcha_violation(user_id, context)

    try:
        _, session = await asyncio.gather(
            queries.ensure_user(user_id, display_name, username),
            spawn_queries.get_active_spawn(chat_id),
        )

        if session is None:
            return

        # Tutorial + login streak: fire-and-forget
        async def _bg_tutorial_streak():
            try:
                from database import title_queries
                tut_step = await queries.get_tutorial_step(user_id)
                if tut_step == 0:
                    await queries.update_tutorial_step(user_id, 1)
                    from handlers.tutorial import send_tutorial_step
                    asyncio.create_task(send_tutorial_step(context, user_id, 1))
            except Exception:
                pass
            try:
                from database import title_queries
                await title_queries.update_login_streak(user_id)
            except Exception:
                pass
        asyncio.create_task(_bg_tutorial_streak())

        lock_key = (session["id"], user_id)
        if lock_key in _catch_locks:
            return
        _catch_locks.add(lock_key)
        try:
            from services.subscription_service import get_user_tier
            from services.ranked_service import current_season_id
            from database import ranked_queries as rq
            already, (allowed, reason, remaining, max_today), user, sub_tier, season_rec = await asyncio.gather(
                spawn_queries.has_attempted_session(session["id"], user_id),
                can_attempt_catch(user_id),
                queries.get_user(user_id),
                get_user_tier(user_id),
                rq.get_season_record(user_id, current_season_id()),
            )

            if already:
                return

            if not allowed:
                resp = await update.message.reply_text(reason)
                schedule_delete(resp, config.AUTO_DEL_CATCH_ATTEMPT)
                return

            await record_attempt(session["id"], user_id)

            after_remaining = max(0, remaining - 1) if remaining >= 0 else -1
            if after_remaining == -1:
                ball_count_tag = " (∞)"
            else:
                ball_count_tag = f" ({after_remaining}/{max_today})"

            r_badge = await _get_ranked_badge(user_id, season_rec)
            decorated = get_decorated_name(
                display_name,
                user.get("title", "") if user else "",
                user.get("title_emoji", "") if user else "",
                username,
                html=True,
                ranked_badge=r_badge,
            )

            throw_text = format_actor(decorated, t(lang, "group.threw_pokeball"), sub_tier, lang=lang)
            attempt_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"{ball_emoji('pokeball')} {throw_text}{ball_count_tag}",
                parse_mode="HTML",
            )
            track_attempt_message(session["id"], chat_id, attempt_msg.message_id)
        finally:
            _catch_locks.discard(lock_key)

    except Exception as e:
        logger.error(f"Catch handler error: {e}")


async def master_ball_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'ㅁ' message in group chat — use master ball for guaranteed catch."""
    if not update.effective_user or not update.effective_chat:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    lang = await get_user_lang(user_id)
    display_name = update.effective_user.first_name or t(lang, "common.trainer")
    username = update.effective_user.username

    if is_tournament_active(chat_id):
        return

    # 포획 잠금 체크
    from services.abuse_service import is_catch_locked_async
    locked, _ = await is_catch_locked_async(user_id)
    if locked:
        schedule_delete(update.message, config.AUTO_DEL_CATCH_CMD)
        return

    schedule_delete(update.message, config.AUTO_DEL_CATCH_CMD)
    await _check_captcha_violation(user_id, context)

    try:
        _, session = await asyncio.gather(
            queries.ensure_user(user_id, display_name, username),
            spawn_queries.get_active_spawn(chat_id),
        )
        if session is None:
            return

        if session.get("is_newbie_spawn"):
            resp = await update.message.reply_text(
                t(lang, "group.newbie_no_special_ball", ball=t(lang, "catch.masterball")),
            )
            schedule_delete(resp, config.AUTO_DEL_CATCH_ATTEMPT)
            return

        lock_key = (session["id"], user_id)
        if lock_key in _catch_locks:
            return
        _catch_locks.add(lock_key)
        try:
            from database.connection import get_db
            pool = await get_db()
            row, already, balls = await asyncio.gather(
                pool.fetchrow("SELECT is_resolved FROM spawn_sessions WHERE id = $1", session["id"]),
                spawn_queries.has_attempted_session(session["id"], user_id),
                queries.get_master_balls(user_id),
            )
            if not row or row["is_resolved"] == 1:
                return
            if already:
                return

            if balls < 1:
                resp = await update.message.reply_text(f"{ball_emoji('masterball')} {t(lang, 'group.no_masterball')}", parse_mode="HTML")
                schedule_delete(resp, config.AUTO_DEL_CATCH_ATTEMPT)
                return

            remaining = await queries.use_master_ball(user_id)
            if remaining is None:
                return

            from services.subscription_service import get_user_tier
            from services.ranked_service import current_season_id
            from database import ranked_queries as rq
            _, user, sub_tier, season_rec = await asyncio.gather(
                spawn_queries.record_catch_attempt(session["id"], user_id, used_master_ball=True),
                queries.get_user(user_id),
                get_user_tier(user_id),
                rq.get_season_record(user_id, current_season_id()),
            )

            r_badge = await _get_ranked_badge(user_id, season_rec)
            decorated = get_decorated_name(
                display_name,
                user.get("title", "") if user else "",
                user.get("title_emoji", "") if user else "",
                username,
                html=True,
                ranked_badge=r_badge,
            )
            throw_text = format_actor(decorated, t(lang, "group.threw_masterball"), sub_tier, lang=lang)
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"{ball_emoji('masterball')} {throw_text} ({t(lang, 'group.remaining_count', count=remaining)})",
                parse_mode="HTML",
            )
            track_attempt_message(session["id"], chat_id, msg.message_id)
        finally:
            _catch_locks.discard(lock_key)

    except Exception as e:
        logger.error(f"Master ball handler error: {e}")


async def priority_ball_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'ㅊㅊ' message — use priority ball (dungeon item, 100% catch)."""
    if not update.effective_user or not update.effective_chat:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    lang = await get_user_lang(user_id)
    display_name = update.effective_user.first_name or t(lang, "common.trainer")
    username = update.effective_user.username

    if is_tournament_active(chat_id):
        return

    from services.abuse_service import is_catch_locked_async
    locked, _ = await is_catch_locked_async(user_id)
    if locked:
        return

    # ㅊㅊ 메시지는 삭제하지 않음

    try:
        _, session = await asyncio.gather(
            queries.ensure_user(user_id, display_name, username),
            spawn_queries.get_active_spawn(chat_id),
        )
        if session is None:
            return

        if session.get("is_newbie_spawn"):
            return

        lock_key = (session["id"], user_id)
        if lock_key in _catch_locks:
            return
        _catch_locks.add(lock_key)
        try:
            from database.connection import get_db
            from database import item_queries as _iq
            pool = await get_db()
            row, already = await asyncio.gather(
                pool.fetchrow("SELECT is_resolved FROM spawn_sessions WHERE id = $1", session["id"]),
                spawn_queries.has_attempted_session(session["id"], user_id),
            )
            if not row or row["is_resolved"] == 1:
                return
            if already:
                return

            qty = await _iq.get_user_item(user_id, "priority_ball")
            if qty < 1:
                resp = await update.message.reply_text(
                    f"{ball_emoji('greatball')} 우선포획볼이 없습니다! (던전 보상으로 획득)",
                    parse_mode="HTML",
                )
                schedule_delete(resp, config.AUTO_DEL_CATCH_ATTEMPT)
                return

            used = await _iq.use_user_item(user_id, "priority_ball")
            if not used:
                return

            # record_catch_attempt를 먼저 실행 — 타임아웃 방지
            await spawn_queries.record_catch_attempt(session["id"], user_id, used_priority_ball=True)

            from services.subscription_service import get_user_tier
            from services.ranked_service import current_season_id
            from database import ranked_queries as rq
            user, sub_tier, season_rec = await asyncio.gather(
                queries.get_user(user_id),
                get_user_tier(user_id),
                rq.get_season_record(user_id, current_season_id()),
            )

            r_badge = await _get_ranked_badge(user_id, season_rec)
            decorated = get_decorated_name(
                display_name,
                user.get("title", "") if user else "",
                user.get("title_emoji", "") if user else "",
                username,
                html=True,
                ranked_badge=r_badge,
            )
            remaining_qty = await _iq.get_user_item(user_id, "priority_ball")
            throw_text = format_actor(decorated, "우선포획볼을 던졌다!", sub_tier, lang=lang)
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"{ball_emoji('greatball')} {throw_text} (남은: {remaining_qty}개)",
                parse_mode="HTML",
            )
            track_attempt_message(session["id"], chat_id, msg.message_id)
        finally:
            _catch_locks.discard(lock_key)

    except Exception as e:
        logger.error(f"Priority ball handler error: {e}")


async def hyper_ball_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'ㅎ' message in group chat — use hyper ball (20 BP, 3x catch rate)."""
    if not update.effective_user or not update.effective_chat:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    lang = await get_user_lang(user_id)
    display_name = update.effective_user.first_name or t(lang, "common.trainer")
    username = update.effective_user.username

    if is_tournament_active(chat_id):
        return

    # 포획 잠금 체크
    from services.abuse_service import is_catch_locked_async as _is_locked
    _lk, _ = await _is_locked(user_id)
    if _lk:
        schedule_delete(update.message, config.AUTO_DEL_CATCH_CMD)
        return

    try:
        _, session = await asyncio.gather(
            queries.ensure_user(user_id, display_name, username),
            spawn_queries.get_active_spawn(chat_id),
        )
        if session is None:
            return

        if session.get("is_newbie_spawn"):
            resp = await update.message.reply_text(
                t(lang, "group.newbie_no_special_ball", ball=t(lang, "catch.hyperball")),
            )
            schedule_delete(resp, config.AUTO_DEL_CATCH_ATTEMPT)
            return

        lock_key = (session["id"], user_id)
        if lock_key in _catch_locks:
            return
        _catch_locks.add(lock_key)
        try:
            from database.connection import get_db
            pool = await get_db()
            row, already = await asyncio.gather(
                pool.fetchrow("SELECT is_resolved FROM spawn_sessions WHERE id = $1", session["id"]),
                spawn_queries.has_attempted_session(session["id"], user_id),
            )
            if not row or row["is_resolved"] == 1:
                return
            if already:
                return

            success = await queries.use_hyper_ball(user_id)
            if not success:
                remaining = await queries.get_hyper_balls(user_id)
                await update.message.reply_text(
                    f"{ball_emoji('hyperball')} {t(lang, 'group.no_hyperball', count=remaining, cost=config.BP_HYPER_BALL_COST)}",
                    parse_mode="HTML",
                )
                return

            from services.subscription_service import get_user_tier
            from services.ranked_service import current_season_id
            from database import ranked_queries as rq
            _, user, remaining, sub_tier, season_rec = await asyncio.gather(
                spawn_queries.record_catch_attempt(session["id"], user_id, used_hyper_ball=True),
                queries.get_user(user_id),
                queries.get_hyper_balls(user_id),
                get_user_tier(user_id),
                rq.get_season_record(user_id, current_season_id()),
            )

            r_badge = await _get_ranked_badge(user_id, season_rec)
            decorated = get_decorated_name(
                display_name,
                user.get("title", "") if user else "",
                user.get("title_emoji", "") if user else "",
                username,
                html=True,
                ranked_badge=r_badge,
            )
            throw_text = format_actor(decorated, t(lang, "group.threw_hyperball"), sub_tier, lang=lang)
            hyper_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"{ball_emoji('hyperball')} {throw_text} ({t(lang, 'group.remaining_count', count=remaining)})",
                parse_mode="HTML",
            )
            track_attempt_message(session["id"], chat_id, hyper_msg.message_id)
        finally:
            _catch_locks.discard(lock_key)

    except Exception as e:
        logger.error(f"Hyper ball handler error: {e}")


# --- Catch DM: Keep / Release callbacks ---

async def catch_keep_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '가방에 넣기' button on catch DM — just remove buttons."""
    query = update.callback_query
    if not query:
        return
    user_id = query.from_user.id
    lang = await get_user_lang(user_id)

    try:
        instance_id = int(query.data.split("_")[-1])
    except (ValueError, IndexError):
        await query.answer(t(lang, "error.generic"))
        return

    from database.connection import get_db
    pool = await get_db()
    owner = await pool.fetchval(
        "SELECT user_id FROM user_pokemon WHERE id = $1", instance_id
    )
    if owner != user_id:
        await query.answer(t(lang, "group.catch_own_only"))
        return

    new_text = (query.message.text_html or query.message.text) + f"\n\n{t(lang, 'group.catch_keep_done')}"
    try:
        await query.message.edit_text(new_text, parse_mode="HTML")
    except Exception:
        pass
    await query.answer(t(lang, "group.catch_keep_done"))


async def catch_release_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '방생하기' button on catch DM — deactivate pokemon + grant hyperball."""
    query = update.callback_query
    if not query:
        return
    user_id = query.from_user.id
    lang = await get_user_lang(user_id)

    try:
        instance_id = int(query.data.split("_")[-1])
    except (ValueError, IndexError):
        await query.answer(t(lang, "error.generic"))
        return

    from database.connection import get_db
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT user_id, is_active FROM user_pokemon WHERE id = $1", instance_id
    )
    if not row or row["user_id"] != user_id:
        await query.answer(t(lang, "group.catch_own_only"))
        return
    if row["is_active"] == 0:
        await query.answer(t(lang, "group.catch_release_already"))
        return

    await queries.deactivate_pokemon(instance_id)
    await queries.add_hyper_ball(user_id, 1)

    be_hyper = ball_emoji("hyperball")
    new_text = (query.message.text_html or query.message.text) + f"\n\n{t(lang, 'group.catch_release_done', ball=be_hyper)}"
    try:
        await query.message.edit_text(new_text, parse_mode="HTML")
    except Exception:
        pass
    await query.answer(t(lang, "group.catch_release_done", ball=""))


