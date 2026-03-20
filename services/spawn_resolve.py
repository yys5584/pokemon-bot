"""Spawn resolution: resolve_spawn, resolve_unresolved_sessions, helpers."""

import asyncio
import random
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config

from database import queries, spawn_queries, stats_queries, title_queries
from services.event_service import get_catch_boost
from utils.helpers import close_button, rarity_badge, type_badge, ball_emoji, shiny_emoji, icon_emoji
from utils.i18n import t, get_group_lang, get_user_lang, poke_name

logger = logging.getLogger(__name__)


async def resolve_spawn(context: ContextTypes.DEFAULT_TYPE):
    """Resolve a spawn after 30 seconds. Determine who catches the Pokemon."""
    from services.spawn_service import _get_chat_lock, _attempt_messages, _add_cxp_bg
    from services.spawn_execute import _auto_keep_pokemon

    data = context.job.data
    chat_id = data["chat_id"]
    session_id = data["session_id"]
    pokemon_id = data["pokemon_id"]
    pokemon_name = data["pokemon_name"]
    pokemon_name_en = data.get("pokemon_name_en", "")
    pokemon_emoji = data["pokemon_emoji"]
    rarity = data["rarity"]
    is_shiny = data.get("is_shiny", False)
    is_newbie_spawn = data.get("is_newbie_spawn", False)
    # Mini-dict for poke_name() until full pokemon dict is loaded
    _poke_mini = {"name_ko": pokemon_name, "name_en": pokemon_name_en}

    # 포획 메시지 전송 완료까지 다음 스폰 차단
    lock = _get_chat_lock(chat_id)
    await lock.acquire()

    try:
        # Check if session is already resolved (avoid duplicate resolution)
        from database.connection import get_db
        pool = await get_db()
        row = await pool.fetchrow(
            "SELECT is_resolved FROM spawn_sessions WHERE id = $1", session_id
        )
        if not row or row["is_resolved"] == 1:
            logger.debug(f"Session {session_id} already resolved, skipping")
            lock.release()
            return

        # Mark as resolved FIRST to prevent race condition with catch/master ball handlers
        await pool.execute(
            "UPDATE spawn_sessions SET is_resolved = 1 WHERE id = $1",
            session_id,
        )

        # Get all catch attempts
        attempts = await spawn_queries.get_session_attempts(session_id)

        # Clean up tracking (but keep messages visible)
        _attempt_messages.pop(session_id, None)

        if not attempts:
            # Nobody tried
            _lang = await get_group_lang(chat_id)
            shiny_tag = f" {shiny_emoji()}{t(_lang, 'spawn_msg.shiny_label').strip()}" if is_shiny else ""
            rbadge = rarity_badge(rarity)
            tb = type_badge(pokemon_id)
            await context.bot.send_message(
                chat_id=chat_id,
                text=t(_lang, "spawn_msg.escaped", icon=icon_emoji('windy'), shiny=shiny_tag, badge=rbadge, tb=tb, name=poke_name(_poke_mini, _lang)),
                parse_mode="HTML",
            )
            lock.release()  # 도망 메시지 전송 완료 → 다음 스폰 허용
            await spawn_queries.close_spawn_session(session_id)
            await spawn_queries.log_spawn(
                chat_id, pokemon_id, pokemon_name, pokemon_emoji,
                rarity, None, None, 0, is_shiny=is_shiny,
            )
            return

        # Get catch rate with event boost
        pokemon = await queries.get_pokemon(pokemon_id)
        base_rate = pokemon["catch_rate"] if pokemon else 0.5
        catch_boost = await get_catch_boost()
        catch_rate = min(1.0, base_rate * catch_boost)

        # 🌱 뉴비 스폰: 도감 수 기준 우선순위
        if is_newbie_spawn:
            all_user_ids = [a["user_id"] for a in attempts]
            pokedex_counts = await stats_queries.count_pokedex_bulk(all_user_ids) if all_user_ids else {}
            thresholds = config.NEWBIE_TIER_THRESHOLDS  # [100, 200, 300]
            logger.info(f"🌱 Newbie spawn resolve: {len(attempts)} attempts, pokedex={pokedex_counts}")

            results = []
            for attempt in attempts:
                pdex = pokedex_counts.get(attempt["user_id"], 0)
                # 티어: 0(도감<100) > 1(도감<200) > 2(도감<300) > 3(도감≥300)
                tier = 0 if pdex < thresholds[0] else (1 if pdex < thresholds[1] else (2 if pdex < thresholds[2] else 3))
                roll = random.random()
                # 마볼/하볼 사용자: 환불 처리, 일반 포획으로 전환
                if attempt.get("used_master_ball"):
                    await queries.add_master_balls_bulk([attempt["user_id"]])
                    logger.info(f"Newbie spawn: refunded master ball to {attempt['user_id']}")
                if attempt.get("used_hyper_ball"):
                    await queries.add_hyper_balls_bulk([attempt["user_id"]])
                    logger.info(f"Newbie spawn: refunded hyper ball to {attempt['user_id']}")
                # 뉴비(tier 0,1,2)는 포획 보장, 고인물(tier 3)은 일반 확률
                if tier < 3:
                    success = True
                else:
                    success = roll < catch_rate
                results.append({
                    "user_id": attempt["user_id"],
                    "display_name": attempt["display_name"],
                    "username": attempt["username"],
                    "roll": roll,
                    "success": success,
                    "used_master_ball": False,  # 환불 후 일반 전환
                    "used_hyper_ball": False,
                    "_tier": tier,
                })
            # 성공한 사람 중 도감 적은 사람(tier 낮은) 우선, 같은 티어면 roll 낮은 사람
            winners = sorted(
                [r for r in results if r["success"]],
                key=lambda x: (x["_tier"], x["roll"]),
            )
            for r in results:
                logger.info(f"  🌱 {r['display_name']}: tier={r['_tier']}, roll={r['roll']:.4f}, success={r['success']}")
            if winners:
                logger.info(f"  🌱 Winner: {winners[0]['display_name']} (tier={winners[0]['_tier']})")
        else:
            # ── 기존 포획 로직 ──
            # Pre-fetch catch counts for newbie boost (batch)
            normal_user_ids2 = [
                a["user_id"] for a in attempts
                if not a.get("used_master_ball") and not a.get("used_hyper_ball")
            ]
            catch_counts2 = await stats_queries.count_total_catches_bulk(normal_user_ids2) if normal_user_ids2 else {}

            # Roll for each catcher (master ball > hyper ball > newbie > regular)
            results = []
            for attempt in attempts:
                if attempt.get("used_master_ball"):
                    roll = -1.0  # Highest priority
                    success = True
                elif attempt.get("used_hyper_ball"):
                    # Hyper ball: 3x catch rate
                    hyper_rate = min(1.0, catch_rate * config.HYPER_BALL_CATCH_MULTIPLIER)
                    roll = random.random()
                    success = roll < hyper_rate
                else:
                    # Newbie boost: first 2 catches are guaranteed
                    total = catch_counts2.get(attempt["user_id"], 0)
                    if total < 2:
                        roll = 0.0  # Lower priority than master ball
                        success = True
                    else:
                        roll = random.random()
                        success = roll < catch_rate
                results.append({
                    "user_id": attempt["user_id"],
                    "display_name": attempt["display_name"],
                    "username": attempt["username"],
                    "roll": roll,
                    "success": success,
                    "used_master_ball": bool(attempt.get("used_master_ball")),
                    "used_hyper_ball": bool(attempt.get("used_hyper_ball")),
                })

            winners = [r for r in results if r["success"]]
        participants = len(attempts)

        if not winners:
            # Everyone failed
            _lang = await get_group_lang(chat_id)
            shiny_tag = f" {shiny_emoji()}{t(_lang, 'spawn_msg.shiny_label').strip()}" if is_shiny else ""
            rbadge = rarity_badge(rarity)
            tb = type_badge(pokemon_id)
            await context.bot.send_message(
                chat_id=chat_id,
                text=t(_lang, "spawn_msg.escaped", icon=icon_emoji('windy'), shiny=shiny_tag, badge=rbadge, tb=tb, name=poke_name(_poke_mini, _lang)),
                parse_mode="HTML",
            )
            lock.release()  # 도망 메시지 전송 완료 → 다음 스폰 허용
            await spawn_queries.close_spawn_session(session_id)
            await spawn_queries.log_spawn(
                chat_id, pokemon_id, pokemon_name, pokemon_emoji,
                rarity, None, None, participants, is_shiny=is_shiny,
            )
            return

        # Pick winner
        if is_newbie_spawn:
            # 뉴비 스폰: 이미 (tier, roll) 기준 정렬됨
            winner = winners[0]
        else:
            # 일반: lowest roll = luckiest
            winners.sort(key=lambda x: x["roll"])
            winner = winners[0]
        winner_id = winner["user_id"]
        winner_name = winner["display_name"]

        # Refund master balls to losers (batch) — 뉴비 스폰에서는 이미 환불 완료
        master_refund_ids2 = [
            r["user_id"] for r in results
            if r["used_master_ball"] and r["user_id"] != winner_id
        ] if not is_newbie_spawn else []
        if master_refund_ids2:
            await queries.add_master_balls_bulk(master_refund_ids2)
            for loser in results:
                if loser["used_master_ball"] and loser["user_id"] != winner_id:
                    logger.info(f"Refunded master ball to {loser['display_name']} ({loser['user_id']})")
                    try:
                        _loser_lang = await get_user_lang(loser["user_id"])
                        await context.bot.send_message(
                            chat_id=loser["user_id"],
                            text=f"{ball_emoji('masterball')} {t(_loser_lang, 'spawn_msg.masterball_refund')}",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass

        # Refund hyper balls when master ball user wins (hyper had no chance)
        if winner.get("used_master_ball"):
            hyper_refund_ids = [
                r["user_id"] for r in results
                if r["used_hyper_ball"] and r["user_id"] != winner_id
            ]
            if hyper_refund_ids:
                await queries.add_hyper_balls_bulk(hyper_refund_ids)
                for loser in results:
                    if loser["used_hyper_ball"] and loser["user_id"] != winner_id:
                        logger.info(f"Refunded hyper ball to {loser['display_name']} (master ball override)")
                        try:
                            _loser_lang = await get_user_lang(loser["user_id"])
                            await context.bot.send_message(
                                chat_id=loser["user_id"],
                                text=f"{ball_emoji('hyperball')} {t(_loser_lang, 'spawn_msg.hyperball_refund')}",
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass

        # Collect failed user IDs for title tracking
        failed_ids = [r["user_id"] for r in results if not r["success"]]

        # Give Pokemon + register pokedex + close session (transaction)
        _inst_id, caught_ivs = await queries.catch_pokemon_transaction(
            winner_id, pokemon_id, chat_id, is_shiny, session_id,
        )

        # Mission: catch
        asyncio.create_task(_notify_mission(context, winner_id, "catch"))

        # CXP: +1 for catch
        asyncio.create_task(_add_cxp_bg(context, chat_id, config.CXP_PER_CATCH, "catch", winner_id))

        # 복귀 유저 환영
        asyncio.create_task(_check_returning_user(context, chat_id, winner_id, winner_name))

        # Check if first catch in chat (for rare+ announcement)
        is_first = await queries.is_first_catch_in_chat(chat_id, pokemon_id)

        # Build message with decorated name (HTML bold for titled users)
        from utils.helpers import get_decorated_name
        from utils.honorific import honorific_name as _hon_name, honorific_catch_verb as _hon_verb
        user_data = await queries.get_user(winner_id)

        _lang = await get_user_lang(winner_id)  # 포획자 개인 언어

        # 구독자 존칭 적용
        _winner_tier = None
        try:
            from services.subscription_service import get_user_tier
            _winner_tier = await get_user_tier(winner_id)
        except Exception:
            pass
        _display = _hon_name(winner_name, _winner_tier, lang=_lang) if _winner_tier else winner_name

        decorated = get_decorated_name(
            _display,
            user_data.get("title", "") if user_data else "",
            user_data.get("title_emoji", "") if user_data else "",
            winner.get("username"),
            html=True,
        )
        shiny_label = f"{shiny_emoji()}{t(_lang, 'spawn_msg.shiny_label')}" if is_shiny else ""

        # IV grade display
        from utils.battle_calc import iv_total
        iv_sum = iv_total(caught_ivs["iv_hp"], caught_ivs["iv_atk"],
                          caught_ivs["iv_def"], caught_ivs["iv_spa"],
                          caught_ivs["iv_spdef"], caught_ivs["iv_spd"])
        iv_grade, _stars = config.get_iv_grade(iv_sum)
        iv_tag = f" [{iv_grade}]"

        rbadge = rarity_badge(rarity)
        tb = type_badge(pokemon_id)
        be_pokeball = ball_emoji("pokeball")
        be_master = ball_emoji("masterball")
        be_hyper = ball_emoji("hyperball")
        _catch = _hon_verb(t(_lang, "spawn_msg.catch_verb"), _winner_tier, lang=_lang)
        _catch_confirm = _hon_verb(t(_lang, "spawn_msg.catch_verb_confirm"), _winner_tier, lang=_lang)
        _pname = poke_name(pokemon or _poke_mini, _lang)
        if is_newbie_spawn and winner.get("_tier", 99) < 2:
            msg = t(_lang, "spawn_msg.catch_newbie", user=decorated, shiny=shiny_label, badge=rbadge, tb=tb, name=_pname, verb=_catch, iv=iv_tag)
        elif winner.get("used_master_ball"):
            msg = f"{be_master} {t(_lang, 'spawn_msg.catch_masterball', user=decorated, shiny=shiny_label, badge=rbadge, tb=tb, name=_pname, verb=_catch_confirm, iv=iv_tag)}"
            await title_queries.increment_title_stat(winner_id, "master_ball_used")
        elif winner.get("used_hyper_ball"):
            msg = f"{be_hyper} {t(_lang, 'spawn_msg.catch_hyperball', user=decorated, shiny=shiny_label, badge=rbadge, tb=tb, name=_pname, verb=_catch, iv=iv_tag)}"
        elif rarity in ("epic", "legendary", "ultra_legendary") and is_first:
            msg = t(_lang, "spawn_msg.catch_first", user=decorated, shiny=shiny_label, badge=rbadge, tb=tb, name=_pname, verb=_catch, iv=iv_tag)
        else:
            msg = f"{be_pokeball} {t(_lang, 'spawn_msg.catch_normal', user=decorated, shiny=shiny_label, badge=rbadge, tb=tb, name=_pname, verb=_catch, iv=iv_tag)}"

        # Shiny catch announcement
        if is_shiny:
            _se = shiny_emoji()
            _shiny_verb = _hon_verb(t(_lang, "spawn_msg.shiny_verb"), _winner_tier, lang=_lang) if _winner_tier else t(_lang, "spawn_msg.shiny_verb")
            msg += f"\n\n{_se}{_se}{_se} {t(_lang, 'spawn_msg.shiny_announcement', verb=_shiny_verb)}"

        # Track midnight catch for title
        hour = config.get_kst_hour()
        if 2 <= hour < 5:
            await title_queries.increment_title_stat(winner_id, "midnight_catch_count")

        # Track catch failures for title (batch)
        if failed_ids:
            await asyncio.gather(
                *(title_queries.increment_title_stat(uid, "catch_fail_count") for uid in failed_ids)
            )

        # Catch BP reward (하루 포획 성공 100마리까지만, KST 자정 기준)
        from database.battle_queries import add_bp
        today_catches = await pool.fetchval(
            "SELECT COUNT(*) FROM spawn_log WHERE caught_by_user_id = $1 "
            "AND spawned_at >= date_trunc('day', NOW() AT TIME ZONE 'Asia/Seoul') AT TIME ZONE 'Asia/Seoul'",
            winner_id,
        )
        if today_catches < config.CATCH_BP_DAILY_LIMIT:
            catch_bp = random.randint(config.CATCH_BP_MIN, config.CATCH_BP_MAX)
            await add_bp(winner_id, catch_bp, "catch")
            msg += f"\n{icon_emoji('coin')} +{catch_bp} BP"

        # Master Ball random drop (2% chance on catch)
        master_ball_drop = random.random() < 0.02
        if master_ball_drop:
            await queries.add_master_ball(winner_id)
            msg += f"\n\n{ball_emoji('masterball')} {t(_lang, 'spawn_msg.masterball_drop')}"

        # Journey system check
        from services.journey_service import check_journey
        journey_msg = await check_journey(winner_id)
        if journey_msg:
            msg += f"\n\n{journey_msg}"

        catch_msg = await context.bot.send_message(
            chat_id=chat_id, text=msg, parse_mode="HTML",
            reply_markup=close_button(),
        )
        lock.release()  # 포획 메시지 전송 완료 → 다음 스폰 허용

        # DM notification to catcher (with stats + power)
        try:
            from utils.battle_calc import calc_battle_stats, format_stats_line, format_power, EVO_STAGE_MAP, get_normalized_base_stats
            stat_type = pokemon.get("stat_type", "balanced") if pokemon else "balanced"

            # Base stats (without IV)
            norm = get_normalized_base_stats(pokemon_id)
            evo_stage = 3 if norm else EVO_STAGE_MAP.get(pokemon_id, 3)
            base_kwargs = norm or {}

            stats_with_iv = calc_battle_stats(
                rarity, stat_type, 0, evo_stage=evo_stage,
                iv_hp=caught_ivs["iv_hp"], iv_atk=caught_ivs["iv_atk"],
                iv_def=caught_ivs["iv_def"], iv_spa=caught_ivs["iv_spa"],
                iv_spdef=caught_ivs["iv_spdef"], iv_spd=caught_ivs["iv_spd"],
                **base_kwargs,
            )
            stats_base = calc_battle_stats(
                rarity, stat_type, 0, evo_stage=evo_stage,
                **base_kwargs,
            )

            _dm_lang = await get_user_lang(winner_id)
            _dm_pname = poke_name(pokemon or _poke_mini, _dm_lang)
            shiny_dm = f" {shiny_emoji()}{t(_dm_lang, 'spawn_msg.shiny_label').strip()}" if is_shiny else ""
            iv_line = (f"IV: {caught_ivs['iv_hp']}/{caught_ivs['iv_atk']}/{caught_ivs['iv_def']}"
                       f"/{caught_ivs['iv_spa']}/{caught_ivs['iv_spdef']}/{caught_ivs['iv_spd']}"
                       f" ({iv_sum}/186)")
            own_count = await queries.count_user_pokemon_species(winner_id, pokemon_id)
            own_tag = t(_dm_lang, "spawn_msg.dm_owned_count", count=own_count) if own_count > 1 else t(_dm_lang, "spawn_msg.dm_owned_new")
            if winner.get("used_master_ball"):
                dm_ball = f"{ball_emoji('masterball')} "
            elif winner.get("used_hyper_ball"):
                dm_ball = f"{ball_emoji('hyperball')} "
            else:
                dm_ball = f"{ball_emoji('pokeball')} "
            dm_text = (
                f"{dm_ball}{rbadge}{tb} {t(_dm_lang, 'spawn_msg.dm_caught', name=_dm_pname)}{shiny_dm} [{iv_grade}]\n"
                f"{iv_line}\n"
                f"{icon_emoji('bolt')} {format_power(stats_with_iv, stats_base)}\n"
                f"{format_stats_line(stats_with_iv, stats_base, lang=_dm_lang)}\n\n"
                f"{own_tag}"
            )
            catch_buttons = InlineKeyboardMarkup([[
                InlineKeyboardButton(t(_dm_lang, "group.catch_keep_btn"), callback_data=f"catch_keep_{_inst_id}"),
                InlineKeyboardButton(t(_dm_lang, "group.catch_release_btn"), callback_data=f"catch_release_{_inst_id}"),
            ]])

            try:
                dm_msg = await context.bot.send_message(
                    chat_id=winner_id, text=dm_text,
                    parse_mode="HTML", reply_markup=catch_buttons,
                )
                logger.info(f"Catch DM sent to {winner_id} for {pokemon_name}")

                # 5분 후 자동 가방 넣기
                context.job_queue.run_once(
                    _auto_keep_pokemon,
                    when=300,
                    data={
                        "chat_id": winner_id,
                        "message_id": dm_msg.message_id,
                        "instance_id": _inst_id,
                    },
                )
            except Exception as dm_err:
                logger.warning(f"Failed to send catch DM to {winner_id}: {dm_err}")
        except Exception as e:
            logger.error(f"Catch DM construction failed for {winner_id}: {e}")

        # Check and unlock titles
        from utils.title_checker import check_and_unlock_titles
        from utils.helpers import escape_html
        new_titles = await check_and_unlock_titles(winner_id)
        if new_titles:
            title_msgs = [
                f"🎉 <b>「{icon_emoji(temoji) if temoji in config.ICON_CUSTOM_EMOJI else temoji} {tname}」</b> 칭호 해금!"
                for _, tname, temoji in new_titles
            ]
            safe_name = escape_html(winner_name)
            title_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"🏷️ {safe_name}의 새 칭호!\n" + "\n".join(title_msgs) + "\nDM에서 '칭호'로 장착하세요!",
                parse_mode="HTML",
            )
            # title msg stays visible

        # Also check titles for failed catchers (background, non-blocking)
        async def _bg_check_failed():
            try:
                for uid in failed_ids:
                    await check_and_unlock_titles(uid)
            except Exception:
                pass
        if failed_ids:
            asyncio.create_task(_bg_check_failed())

        # Log
        await spawn_queries.log_spawn(
            chat_id, pokemon_id, pokemon_name, pokemon_emoji,
            rarity, winner_id, winner_name, participants, is_shiny=is_shiny,
        )

        logger.info(
            f"{winner_name} caught {pokemon_name} in chat {chat_id}"
        )

    except Exception as e:
        logger.error(f"Spawn resolution failed for session {session_id}: {e}")
        await spawn_queries.close_spawn_session(session_id)
    finally:
        # 어떤 경로로든 락이 아직 잡혀있으면 해제
        if lock.locked():
            lock.release()


async def resolve_unresolved_sessions(bot) -> list[tuple[int, str]]:
    """Resolve pending spawn sessions on startup instead of just cleaning up.
    Returns list of (user_id, ball_type) for refunded balls."""
    from database.connection import get_db

    pool = await get_db()
    # Find unresolved sessions with pokemon info
    sessions = await pool.fetch("""
        SELECT ss.id, ss.chat_id, ss.pokemon_id, pm.name_ko, pm.name_en, pm.emoji,
               pm.rarity, pm.catch_rate, ss.is_shiny,
               CASE WHEN ss.spawned_at < NOW() - INTERVAL '5 minutes' THEN 1 ELSE 0 END as too_old
        FROM spawn_sessions ss
        JOIN pokemon_master pm ON ss.pokemon_id = pm.id
        WHERE ss.is_resolved = 0
    """)

    if not sessions:
        return []

    refunded = []
    for sess in sessions:
        session_id = sess["id"]
        chat_id = sess["chat_id"]
        pokemon_id = sess["pokemon_id"]
        pokemon_name = sess["name_ko"]
        _poke_mini = {"name_ko": sess["name_ko"], "name_en": sess.get("name_en", "")}
        rarity = sess["rarity"]
        catch_rate = sess["catch_rate"]
        is_shiny = bool(sess.get("is_shiny"))

        try:
            # Mark resolved
            await pool.execute(
                "UPDATE spawn_sessions SET is_resolved = 1 WHERE id = $1", session_id
            )

            # Too old (>5min) — just refund balls, skip resolve
            if sess["too_old"]:
                refund_rows = await pool.fetch(
                    """SELECT user_id, used_master_ball, used_hyper_ball
                       FROM catch_attempts WHERE session_id = $1
                       AND (used_master_ball = 1 OR used_hyper_ball = 1)""",
                    session_id,
                )
                for r in refund_rows:
                    if r["used_master_ball"]:
                        await pool.execute(
                            "UPDATE users SET master_balls = master_balls + 1 WHERE user_id = $1",
                            r["user_id"],
                        )
                        refunded.append((r["user_id"], "master"))
                    if r["used_hyper_ball"]:
                        await pool.execute(
                            "UPDATE users SET hyper_balls = hyper_balls + 1 WHERE user_id = $1",
                            r["user_id"],
                        )
                        refunded.append((r["user_id"], "hyper"))
                continue

            # Get attempts
            attempts = await spawn_queries.get_session_attempts(session_id)
            if not attempts:
                _lang = await get_group_lang(chat_id)
                rbadge = rarity_badge(rarity)
                tb = type_badge(pokemon_id)
                await bot.send_message(
                    chat_id=chat_id,
                    text=t(_lang, "spawn_msg.escaped", icon=icon_emoji('windy'), shiny="", badge=rbadge, tb=tb, name=poke_name(_poke_mini, _lang)),
                    parse_mode="HTML",
                )
                await spawn_queries.log_spawn(
                    chat_id, pokemon_id, pokemon_name, sess["emoji"],
                    rarity, None, None, 0,
                )
                continue

            # Roll catches
            catch_boost = await get_catch_boost()
            effective_rate = min(1.0, catch_rate * catch_boost)

            # Pre-fetch catch counts for newbie boost (batch)
            normal_ids_r = [
                a["user_id"] for a in attempts
                if not a.get("used_master_ball") and not a.get("used_hyper_ball")
            ]
            cc_r = await stats_queries.count_total_catches_bulk(normal_ids_r) if normal_ids_r else {}

            results = []
            for attempt in attempts:
                if attempt.get("used_master_ball"):
                    roll, success = -1.0, True
                elif attempt.get("used_hyper_ball"):
                    hyper_rate = min(1.0, effective_rate * config.HYPER_BALL_CATCH_MULTIPLIER)
                    roll = random.random()
                    success = roll < hyper_rate
                else:
                    total = cc_r.get(attempt["user_id"], 0)
                    if total < 2:
                        roll, success = 0.0, True
                    else:
                        roll = random.random()
                        success = roll < effective_rate
                results.append({
                    "user_id": attempt["user_id"],
                    "display_name": attempt["display_name"],
                    "username": attempt["username"],
                    "roll": roll, "success": success,
                    "used_master_ball": bool(attempt.get("used_master_ball")),
                    "used_hyper_ball": bool(attempt.get("used_hyper_ball")),
                })

            winners = [r for r in results if r["success"]]
            participants = len(attempts)

            if not winners:
                _lang = await get_group_lang(chat_id)
                rbadge = rarity_badge(rarity)
                tb = type_badge(pokemon_id)
                await bot.send_message(
                    chat_id=chat_id,
                    text=t(_lang, "spawn_msg.escaped", icon=icon_emoji('windy'), shiny="", badge=rbadge, tb=tb, name=poke_name(_poke_mini, _lang)),
                    parse_mode="HTML",
                )
                await spawn_queries.log_spawn(
                    chat_id, pokemon_id, pokemon_name, sess["emoji"],
                    rarity, None, None, participants,
                )
                continue

            # Pick winner
            winners.sort(key=lambda x: x["roll"])
            winner = winners[0]
            winner_id = winner["user_id"]
            winner_name = winner["display_name"]

            # Refund master balls to losers (batch)
            mr_ids = [r["user_id"] for r in results
                      if r["used_master_ball"] and r["user_id"] != winner_id]
            if mr_ids:
                await queries.add_master_balls_bulk(mr_ids)
                refunded.extend((uid, "master") for uid in mr_ids)

            # Refund hyper balls when master ball user wins
            if winner.get("used_master_ball"):
                hr_ids = [r["user_id"] for r in results
                          if r["used_hyper_ball"] and r["user_id"] != winner_id]
                if hr_ids:
                    await queries.add_hyper_balls_bulk(hr_ids)
                    refunded.extend((uid, "hyper") for uid in hr_ids)

            # Give pokemon (transaction)
            _inst_id, caught_ivs = await queries.catch_pokemon_transaction(
                winner_id, pokemon_id, chat_id, is_shiny, session_id,
            )

            # Build message
            from utils.helpers import get_decorated_name
            from utils.battle_calc import iv_total
            user_data = await queries.get_user(winner_id)
            decorated = get_decorated_name(
                winner_name,
                user_data.get("title", "") if user_data else "",
                user_data.get("title_emoji", "") if user_data else "",
                winner.get("username"), html=True,
            )
            iv_sum = iv_total(caught_ivs["iv_hp"], caught_ivs["iv_atk"],
                              caught_ivs["iv_def"], caught_ivs["iv_spa"],
                              caught_ivs["iv_spdef"], caught_ivs["iv_spd"])
            iv_grade, _ = config.get_iv_grade(iv_sum)
            iv_tag = f" [{iv_grade}]"
            rbadge = rarity_badge(rarity)
            tb = type_badge(pokemon_id)
            be = ball_emoji("masterball") if winner["used_master_ball"] else \
                 ball_emoji("hyperball") if winner["used_hyper_ball"] else \
                 ball_emoji("pokeball")
            _lang = await get_group_lang(chat_id)
            shiny_label = f"{shiny_emoji()}{t(_lang, 'spawn_msg.shiny_label')}" if is_shiny else ""
            msg = t(_lang, "spawn_msg.server_recover", ball=be, user=decorated, shiny=shiny_label, badge=rbadge, tb=tb, name=poke_name(_poke_mini, _lang), iv=iv_tag)

            # Catch BP reward (하루 포획 성공 100마리까지만, KST 자정 기준)
            from database.battle_queries import add_bp
            today_catches = await pool.fetchval(
                "SELECT COUNT(*) FROM spawn_log WHERE caught_by_user_id = $1 "
                "AND spawned_at >= (NOW() AT TIME ZONE 'Asia/Seoul')::date "
                "AT TIME ZONE 'Asia/Seoul'",
                winner_id,
            )
            if today_catches < config.CATCH_BP_DAILY_LIMIT:
                catch_bp = random.randint(config.CATCH_BP_MIN, config.CATCH_BP_MAX)
                await add_bp(winner_id, catch_bp, "catch")
                msg += f"\n+{catch_bp} BP"

            # Journey system check
            from services.journey_service import check_journey
            journey_msg = await check_journey(winner_id)
            if journey_msg:
                msg += f"\n\n{journey_msg}"

            await bot.send_message(
                chat_id=chat_id, text=msg, parse_mode="HTML",
            )
            await spawn_queries.log_spawn(
                chat_id, pokemon_id, pokemon_name, sess["emoji"],
                rarity, winner_id, winner_name, participants,
            )

            # Mission: catch (startup resolve - no context, use bot directly)
            try:
                from services.mission_service import check_mission_progress
                mission_msg = await check_mission_progress(winner_id, "catch")
                if mission_msg:
                    await bot.send_message(chat_id=winner_id, text=mission_msg, parse_mode="HTML")
            except Exception:
                pass

            logger.info(f"[startup resolve] {winner_name} caught {pokemon_name} in {chat_id}")

        except Exception as e:
            logger.error(f"[startup resolve] session {session_id} failed: {e}")
            # 실패해도 볼 환불은 해줘야 함
            try:
                refund_rows = await pool.fetch(
                    """SELECT user_id, used_master_ball, used_hyper_ball
                       FROM catch_attempts WHERE session_id = $1
                       AND (used_master_ball = 1 OR used_hyper_ball = 1)""",
                    session_id,
                )
                for r in refund_rows:
                    if r["used_master_ball"]:
                        await pool.execute(
                            "UPDATE users SET master_balls = master_balls + 1 WHERE user_id = $1",
                            r["user_id"],
                        )
                        refunded.append((r["user_id"], "master"))
                    if r["used_hyper_ball"]:
                        await pool.execute(
                            "UPDATE users SET hyper_balls = hyper_balls + 1 WHERE user_id = $1",
                            r["user_id"],
                        )
                        refunded.append((r["user_id"], "hyper"))
                logger.info(f"[startup resolve] session {session_id}: refunded {len(refund_rows)} balls on error")
            except Exception as refund_err:
                logger.error(f"[startup resolve] session {session_id} refund also failed: {refund_err}")
            await spawn_queries.close_spawn_session(session_id)

    if refunded:
        logger.info(f"[startup resolve] Refunded {len(refunded)} balls")
    return refunded


async def _notify_mission(context, user_id: int, mission_key: str):
    """Fire-and-forget: check mission progress and DM user on completion."""
    try:
        from services.mission_service import check_mission_progress
        msg = await check_mission_progress(user_id, mission_key)
        if msg:
            await context.bot.send_message(
                chat_id=user_id, text=msg, parse_mode="HTML",
            )
    except Exception:
        pass


async def _check_returning_user(context, chat_id: int, user_id: int, display_name: str):
    """7일+ 미포획 후 복귀한 유저를 캠프 채팅방에 환영."""
    try:
        last_catch = await queries.get_last_catch_time(user_id)
        if not last_catch:
            return  # 첫 포획이거나 데이터 없음

        import datetime as dt
        now = config.get_kst_now()
        if last_catch.tzinfo is None:
            last_catch = last_catch.replace(tzinfo=dt.timezone.utc)

        days_away = (now - last_catch).days
        if days_away < config.CAMP_RETURN_DAYS:
            return

        # 캠프가 있는 채팅방인지 확인
        from database import camp_queries as cq
        camp = await cq.get_camp(chat_id)
        if not camp:
            return

        from utils.helpers import icon_emoji
        _lang = await get_group_lang(chat_id)
        msg = (
            f"{icon_emoji('pokecenter')} {t(_lang, 'spawn_msg.returning_welcome')}\n\n"
            f"{display_name} — {days_away}d {icon_emoji('heart')}"
        )
        await context.bot.send_message(
            chat_id=chat_id, text=msg, parse_mode="HTML",
        )
    except Exception:
        logger.debug(f"Returning user check failed for {user_id}", exc_info=True)
