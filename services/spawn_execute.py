"""Spawn execution: execute_spawn, _auto_keep_pokemon, _resolve_overlapping_spawn."""

import asyncio
import random
import logging
from datetime import timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config

from database import queries, spawn_queries, stats_queries, title_queries
from services.event_service import get_catch_boost, get_shiny_boost
from services.weather_service import get_weather_display
from utils.card_generator import generate_card
from utils.helpers import schedule_delete, close_button, rarity_badge, type_badge, ball_emoji, shiny_emoji, icon_emoji
from utils.i18n import t, get_group_lang, get_user_lang, poke_name

logger = logging.getLogger(__name__)


async def _resolve_overlapping_spawn(context: ContextTypes.DEFAULT_TYPE, active: dict):
    """Quick-resolve an overlapping spawn before starting a new one.
    This prevents catch attempts from being silently discarded in arcade mode."""
    from database.connection import get_db
    from services.spawn_service import _attempt_messages

    session_id = active["id"]
    chat_id = active["chat_id"]
    is_newbie_spawn = bool(active.get("is_newbie_spawn"))

    try:
        pool = await get_db()
        row = await pool.fetchrow(
            "SELECT is_resolved FROM spawn_sessions WHERE id = $1", session_id
        )
        if not row or row["is_resolved"] == 1:
            return  # Already resolved

        # Mark as resolved
        await pool.execute(
            "UPDATE spawn_sessions SET is_resolved = 1 WHERE id = $1", session_id
        )

        # Get pokemon info
        _prow = await pool.fetchrow(
            "SELECT pm.id, pm.name_ko, pm.name_en, pm.emoji, pm.rarity, pm.catch_rate, "
            "pm.stat_type, ss.is_shiny, ss.personality "
            "FROM spawn_sessions ss "
            "JOIN pokemon_master pm ON ss.pokemon_id = pm.id "
            "WHERE ss.id = $1", session_id
        )
        if not _prow:
            await spawn_queries.close_spawn_session(session_id)
            return
        pokemon = dict(_prow)

        pokemon_id = pokemon["id"]
        pokemon_name = pokemon["name_ko"]
        rarity = pokemon["rarity"]
        is_shiny = bool(pokemon.get("is_shiny"))
        _pers_str = pokemon.get("personality")  # "T3:atk:사나움" or None

        # Get catch attempts
        attempts = await spawn_queries.get_session_attempts(session_id)
        _attempt_messages.pop(session_id, None)

        if not attempts:
            # Nobody tried — just close silently (don't spam "ran away" in arcade)
            await spawn_queries.close_spawn_session(session_id)
            await spawn_queries.log_spawn(
                chat_id, pokemon_id, pokemon_name, pokemon["emoji"],
                rarity, None, None, 0, is_shiny=is_shiny, personality=_pers_str,
            )
            logger.info(f"Overlap resolve {session_id}: no attempts, closed")
            return

        # Get catch rate with event boost
        base_rate = pokemon["catch_rate"]
        catch_boost = await get_catch_boost()
        catch_rate = min(1.0, base_rate * catch_boost)

        # 🌱 뉴비 스폰: 도감 수 기준 우선순위
        if is_newbie_spawn:
            all_user_ids = [a["user_id"] for a in attempts]
            pokedex_counts = await stats_queries.count_pokedex_bulk(all_user_ids) if all_user_ids else {}
            thresholds = config.NEWBIE_TIER_THRESHOLDS

            results = []
            for attempt in attempts:
                pdex = pokedex_counts.get(attempt["user_id"], 0)
                tier = 0 if pdex < thresholds[0] else (1 if pdex < thresholds[1] else (2 if pdex < thresholds[2] else 3))
                roll = random.random()
                if attempt.get("used_master_ball"):
                    await queries.add_master_balls_bulk([attempt["user_id"]])
                    logger.info(f"Newbie spawn (overlap): refunded master ball to {attempt['user_id']}")
                if attempt.get("used_hyper_ball"):
                    await queries.add_hyper_balls_bulk([attempt["user_id"]])
                    logger.info(f"Newbie spawn (overlap): refunded hyper ball to {attempt['user_id']}")
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
                    "used_master_ball": False,
                    "used_hyper_ball": False,
                    "_tier": tier,
                })
            winners = sorted(
                [r for r in results if r["success"]],
                key=lambda x: (x["_tier"], x["roll"]),
            )
        else:
            # Pre-fetch catch counts for newbie boost (batch)
            normal_user_ids = [
                a["user_id"] for a in attempts
                if not a.get("used_master_ball") and not a.get("used_hyper_ball")
            ]
            catch_counts = await stats_queries.count_total_catches_bulk(normal_user_ids) if normal_user_ids else {}

            # Roll for each catcher
            results = []
            for attempt in attempts:
                if attempt.get("used_master_ball"):
                    roll, success = -1.0, True
                elif attempt.get("used_hyper_ball"):
                    hyper_rate = min(1.0, catch_rate * config.HYPER_BALL_CATCH_MULTIPLIER)
                    roll = random.random()
                    success = roll < hyper_rate
                else:
                    total = catch_counts.get(attempt["user_id"], 0)
                    if total < 2:
                        roll, success = 0.0, True
                    else:
                        roll = random.random()
                        success = roll < catch_rate
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
            # Everyone failed
            _lang = await get_group_lang(chat_id)
            shiny_tag = f" {shiny_emoji()}{t(_lang, 'spawn_msg.shiny_label').strip()}" if is_shiny else ""
            rbadge = rarity_badge(rarity)
            tb = type_badge(pokemon_id)
            await context.bot.send_message(
                chat_id=chat_id,
                text=t(_lang, "spawn_msg.escaped", icon=icon_emoji('windy'), shiny=shiny_tag, badge=rbadge, tb=tb, name=poke_name(pokemon, _lang)),
                parse_mode="HTML",
            )
            await spawn_queries.close_spawn_session(session_id)
            await spawn_queries.log_spawn(
                chat_id, pokemon_id, pokemon_name, pokemon["emoji"],
                rarity, None, None, participants, is_shiny=is_shiny, personality=_pers_str,
            )
            logger.info(f"Overlap resolve {session_id}: all failed, {pokemon_name} escaped")
            return

        # Pick winner
        if is_newbie_spawn:
            winner = winners[0]  # 이미 (tier, roll) 정렬됨
        else:
            winners.sort(key=lambda x: x["roll"])
            winner = winners[0]
        winner_id = winner["user_id"]
        winner_name = winner["display_name"]

        # Refund master balls to losers (batch) — 뉴비 스폰에서는 이미 환불 완료
        master_refund_ids = [
            r["user_id"] for r in results
            if r["used_master_ball"] and r["user_id"] != winner_id
        ] if not is_newbie_spawn else []
        if master_refund_ids:
            await queries.add_master_balls_bulk(master_refund_ids)
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
        if not is_newbie_spawn and winner.get("used_master_ball"):
            hyper_refund_ids = [
                r["user_id"] for r in results
                if r["used_hyper_ball"] and r["user_id"] != winner_id
            ]
            if hyper_refund_ids:
                await queries.add_hyper_balls_bulk(hyper_refund_ids)
                for loser in results:
                    if loser["used_hyper_ball"] and loser["user_id"] != winner_id:
                        logger.info(f"Refunded hyper ball to {loser['display_name']} (master ball override, overlap)")
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
            personality=_pers_str,
        )

        # Build result message
        from utils.helpers import get_decorated_name
        from utils.battle_calc import iv_total
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
            winner.get("username"), html=True,
        )
        iv_sum = iv_total(caught_ivs["iv_hp"], caught_ivs["iv_atk"],
                          caught_ivs["iv_def"], caught_ivs["iv_spa"],
                          caught_ivs["iv_spdef"], caught_ivs["iv_spd"])
        iv_grade, _ = config.get_iv_grade(iv_sum)
        iv_tag = f" [{iv_grade}]"
        rbadge = rarity_badge(rarity)
        tb = type_badge(pokemon_id)
        shiny_label = f"{shiny_emoji()}{t(_lang, 'spawn_msg.shiny_label')}" if is_shiny else ""
        be_pokeball = ball_emoji("pokeball")
        be_master = ball_emoji("masterball")
        be_hyper = ball_emoji("hyperball")

        _catch = _hon_verb(t(_lang, "spawn_msg.catch_verb"), _winner_tier, lang=_lang)
        _catch_confirm = _hon_verb(t(_lang, "spawn_msg.catch_verb_confirm"), _winner_tier, lang=_lang)
        _pname = poke_name(pokemon, _lang)
        if is_newbie_spawn and winner.get("_tier", 99) < 2:
            msg = t(_lang, "spawn_msg.catch_newbie", user=decorated, shiny=shiny_label, badge=rbadge, tb=tb, name=_pname, verb=_catch, iv=iv_tag)
        elif winner.get("used_master_ball"):
            msg = f"{be_master} {t(_lang, 'spawn_msg.catch_masterball', user=decorated, shiny=shiny_label, badge=rbadge, tb=tb, name=_pname, verb=_catch_confirm, iv=iv_tag)}"
            await title_queries.increment_title_stat(winner_id, "master_ball_used")
        elif winner.get("used_hyper_ball"):
            msg = f"{be_hyper} {t(_lang, 'spawn_msg.catch_hyperball', user=decorated, shiny=shiny_label, badge=rbadge, tb=tb, name=_pname, verb=_catch, iv=iv_tag)}"
        else:
            msg = f"{be_pokeball} {t(_lang, 'spawn_msg.catch_normal', user=decorated, shiny=shiny_label, badge=rbadge, tb=tb, name=_pname, verb=_catch, iv=iv_tag)}"

        if is_shiny:
            _se = shiny_emoji()
            _shiny_verb = _hon_verb(t(_lang, "spawn_msg.shiny_verb"), _winner_tier, lang=_lang) if _winner_tier else t(_lang, "spawn_msg.shiny_verb")
            msg += f"\n\n{_se}{_se}{_se} {t(_lang, 'spawn_msg.shiny_announcement', verb=_shiny_verb)}"

        # Track midnight catch for title
        hour = config.get_kst_hour()
        if 2 <= hour < 5:
            await title_queries.increment_title_stat(winner_id, "midnight_catch_count")
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

        # Master Ball random drop
        if random.random() < 0.02:
            await queries.add_master_ball(winner_id)
            msg += f"\n\n{ball_emoji('masterball')} {t(_lang, 'spawn_msg.masterball_drop')}"

        # Journey system check
        from services.journey_service import check_journey
        journey_msg = await check_journey(winner_id)
        if journey_msg:
            msg += f"\n\n{journey_msg}"

        from utils.helpers import close_button
        await context.bot.send_message(
            chat_id=chat_id, text=msg, parse_mode="HTML",
            reply_markup=close_button(),
        )

        # Mission: catch
        from services.spawn_resolve import _notify_mission
        asyncio.create_task(_notify_mission(context, winner_id, "catch"))

        # CXP: +1 for catch
        from services.spawn_service import _add_cxp_bg
        asyncio.create_task(_add_cxp_bg(context, chat_id, config.CXP_PER_CATCH, "catch", winner_id))

        # DM notification
        try:
            from utils.battle_calc import calc_battle_stats, format_stats_line, format_power, EVO_STAGE_MAP, get_normalized_base_stats
            stat_type = pokemon.get("stat_type", "balanced") or "balanced"
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
                rarity, stat_type, 0, evo_stage=evo_stage, **base_kwargs,
            )
            _dm_lang = await get_user_lang(winner_id)
            _dm_pname = poke_name(pokemon, _dm_lang)
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
            # 성격 표시
            from utils.battle_calc import personality_from_str as _pfs
            _pers = _pfs(_pers_str)
            _pers_dm = ""
            if _pers:
                _te = {"T1": "⚪", "T2": "🔵", "T3": "🟡", "T4": "🟢"}.get(_pers["tier"], "⚪")
                _pers_dm = f"{_te} 성격: {_pers['name']}\n"
            dm_text = (
                f"{dm_ball}{rbadge}{tb} {t(_dm_lang, 'spawn_msg.dm_caught', name=_dm_pname)}{shiny_dm} [{iv_grade}]\n"
                f"{_pers_dm}"
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

        # Title checks (background)
        from utils.title_checker import check_and_unlock_titles
        from utils.helpers import escape_html
        new_titles = await check_and_unlock_titles(winner_id)
        if new_titles:
            title_msgs = [
                f"🎉 <b>「{icon_emoji(temoji) if temoji in config.ICON_CUSTOM_EMOJI else temoji} {tname}」</b> 칭호 해금!"
                for _, tname, temoji in new_titles
            ]
            safe_name = escape_html(winner_name)
            await context.bot.send_message(
                chat_id=winner_id,
                text=f"🏷️ {safe_name}의 새 칭호!\n" + "\n".join(title_msgs) + "\n'칭호'를 입력해서 장착하세요!",
                parse_mode="HTML",
            )

        # Log
        await spawn_queries.log_spawn(
            chat_id, pokemon_id, pokemon_name, pokemon["emoji"],
            rarity, winner_id, winner_name, participants, is_shiny=is_shiny, personality=_pers_str,
        )
        logger.info(f"Overlap resolve {session_id}: {winner_name} caught {pokemon_name}")

    except Exception as e:
        logger.error(f"Overlap resolve failed for session {session_id}: {e}")
        await spawn_queries.close_spawn_session(session_id)


async def _auto_keep_pokemon(context: ContextTypes.DEFAULT_TYPE):
    """5분 경과 시 자동으로 가방에 넣기 (버튼 제거)."""
    data = context.job.data
    chat_id = data["chat_id"]
    message_id = data["message_id"]

    try:
        # 버튼 제거 시도 — 이미 사용자가 버튼을 눌렀으면 reply_markup이 없어서 무시됨
        await context.bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=None,
        )
        logger.info(f"Auto-keep: buttons removed for instance {data.get('instance_id')} (user {chat_id})")
    except Exception:
        # 이미 버튼이 제거된 경우 (사용자가 선택 완료) — 무시
        pass


async def execute_spawn(context: ContextTypes.DEFAULT_TYPE):
    """Execute a single spawn event. Called by JobQueue."""
    from services.spawn_schedule import is_midnight_bonus, roll_rarity, pick_random_pokemon
    from services.spawn_resolve import resolve_spawn
    from services.spawn_service import _get_chat_lock

    chat_id = context.job.data["chat_id"]
    force = context.job.data.get("force", False)
    force_shiny = context.job.data.get("force_shiny", False)
    # Arcade = permanent OR temp arcade (job name starts with arcade_)
    job_name = getattr(context.job, "name", None) or ""
    arcade = chat_id in config.ARCADE_CHAT_IDS or job_name.startswith(f"arcade_{chat_id}")

    # Skip spawns in tournament chat while tournament is active
    from services.tournament_service import is_tournament_active
    if is_tournament_active(chat_id) and not context.job.data.get("admin_force"):
        return

    try:
        # 1. Activity check (skip if force spawn or arcade)
        if not force and not arcade:
            activity = await spawn_queries.get_recent_activity(chat_id, hours=1)
            if activity < 1:
                # No activity — retry later
                # Cancel existing retry jobs for this chat to prevent accumulation
                retry_name = f"spawn_retry_{chat_id}"
                for job in context.job_queue.jobs():
                    if job.name == retry_name:
                        job.schedule_removal()
                retry_delay = random.randint(
                    config.SPAWN_RETRY_MIN_SECONDS,
                    config.SPAWN_RETRY_MAX_SECONDS,
                )
                context.job_queue.run_once(
                    execute_spawn,
                    when=retry_delay,
                    data={"chat_id": chat_id},
                    name=retry_name,
                )
                logger.info(f"No activity in {chat_id}, retrying in {retry_delay}s")
                return

        # 2. Check if there's already an active spawn
        active = await spawn_queries.get_active_spawn(chat_id)
        if active:
            if not arcade and not force:
                return  # Normal spawn: skip if active spawn exists
            # Arcade/force: resolve old spawn before creating new one
            old_session_id = active["id"]
            old_resolve_name = f"resolve_{old_session_id}"

            # Cancel the scheduled resolve job (we'll resolve inline)
            for job in context.job_queue.jobs():
                if job.name == old_resolve_name:
                    job.schedule_removal()
                    break

            # Quick-resolve the overlapping spawn (determine catch, send result)
            await _resolve_overlapping_spawn(context, active)

            # Note: don't delete old spawn image — keep it as context
            # (normal resolve_spawn also doesn't delete the photo)

        # 2.5 Cooldown: skip if last spawn was within 5 minutes (skip for arcade and force)
        if not arcade and not force:
            last_spawn = await spawn_queries.get_last_spawn_time(chat_id)
            if last_spawn:
                if last_spawn.tzinfo is None:
                    import datetime as _dt
                    last_spawn = last_spawn.replace(tzinfo=_dt.timezone.utc)
                elapsed = (config.get_kst_now() - last_spawn).total_seconds()
                if elapsed < 300:  # 5 minutes cooldown
                    # Re-schedule after remaining cooldown instead of dropping
                    remaining = int(300 - elapsed) + 10  # +10s buffer
                    retry_name = f"spawn_retry_{chat_id}"
                    for job in context.job_queue.jobs():
                        if job.name == retry_name:
                            job.schedule_removal()
                    context.job_queue.run_once(
                        execute_spawn,
                        when=remaining,
                        data={"chat_id": chat_id},
                        name=retry_name,
                    )
                    logger.debug(f"Spawn cooldown for {chat_id}: {elapsed:.0f}s elapsed, retrying in {remaining}s")
                    return

        # 3. Roll rarity with midnight bonus + event boosts + chat level boosts
        midnight = is_midnight_bonus()
        _level_rarity_boosts = None
        try:
            _lr = await queries.get_chat_level(chat_id)
            if _lr:
                _li = config.get_chat_level_info(_lr["cxp"])
                if _li["rarity_boosts"]:
                    _level_rarity_boosts = _li["rarity_boosts"]
        except Exception:
            pass
        # 관리자 포켓몬 ID 지정
        force_pokemon_id = context.job.data.get("force_pokemon_id")
        if force_pokemon_id:
            pokemon = await queries.get_pokemon(force_pokemon_id)
            if pokemon:
                rarity = pokemon.get("rarity", "common")
            else:
                rarity = await roll_rarity(midnight_bonus=midnight, rarity_boosts=_level_rarity_boosts)
                pokemon = await pick_random_pokemon(rarity)
        else:
            rarity = await roll_rarity(midnight_bonus=midnight, rarity_boosts=_level_rarity_boosts)
            pokemon = await pick_random_pokemon(rarity)

        # 4.5 뉴비 스폰 판정 (관리자 아케이드 전용, 10% 확률) — shiny 판정 전에 결정
        is_newbie_spawn = (chat_id in config.ARCADE_CHAT_IDS) and random.random() < config.NEWBIE_SPAWN_CHANCE

        # 4.6 Shiny determination (자연 스폰은 확정만, 강스/아케이드는 랜덤 유지)
        if force_shiny:
            is_shiny = True
        else:
            if is_newbie_spawn:
                shiny_rate = config.NEWBIE_SPAWN_SHINY_RATE
            elif arcade:
                shiny_rate = config.SHINY_RATE_ARCADE
            elif force:
                shiny_rate = config.SHINY_RATE_FORCE
            else:
                shiny_rate = config.SHINY_RATE_NATURAL

            # Anti-abuse: 강스/아케이드 이로치 차단 조건
            # 1) 최근 30분간 포획 참여자 1명 이하 (단, 최소 2회 이상 스폰 이력 필요)
            # 2) 최근 10회 스폰 전부 미포획(도망)
            if (force or arcade) and shiny_rate > 0:
                try:
                    catch_users = await spawn_queries.get_recent_catch_user_count(chat_id, minutes=30)
                    caught, total = await spawn_queries.get_recent_spawn_catch_rate(chat_id, limit=10)
                    if total >= 2 and catch_users <= 1:
                        shiny_rate = 0.0
                        logger.info(f"Shiny blocked in {chat_id}: only {catch_users} catcher(s) in last 30min")
                    elif total >= 10 and caught == 0:
                        shiny_rate = 0.0
                        logger.info(f"Shiny blocked in {chat_id}: 0/{total} caught in last {total} spawns")
                except Exception as e:
                    logger.warning(f"Anti-abuse check failed for {chat_id}: {e}")

            # Chat level shiny boost (강스/아케이드에만 의미 있음)
            level_shiny_add = 0.0
            try:
                _lrow = await queries.get_chat_level(chat_id)
                if _lrow:
                    _linfo = config.get_chat_level_info(_lrow["cxp"])
                    level_shiny_add = _linfo["shiny_boost_pct"] / 100.0
            except Exception:
                pass
            shiny_mult = await get_shiny_boost()
            is_shiny = random.random() < min(1.0, shiny_rate * shiny_mult + level_shiny_add)

        # 5. Generate card image FIRST (before creating session)
        _lang = await get_group_lang(chat_id)
        shiny_text = f" {shiny_emoji()}{t(_lang, 'spawn_msg.shiny_label').strip()}" if is_shiny else ""
        from utils.helpers import _type_emoji
        bonus_text = f" {_type_emoji('dark')}" if midnight else ""

        # Check for active event indicator
        from services.event_service import get_active_event_summary
        event_summary = await get_active_event_summary()
        event_tag = ""

        # Weather indicator
        weather_tag = get_weather_display()

        # Catch window: arcade uses interval-based, force spawn = 30s, normal = 60s
        spawn_interval = context.job.data.get("interval")
        if arcade and spawn_interval:
            window = max(spawn_interval - 10, config.ARCADE_SPAWN_WINDOW)
        elif arcade:
            window = config.ARCADE_SPAWN_WINDOW
        elif force:
            window = 30
        else:
            window = config.SPAWN_WINDOW_SECONDS

        tb = type_badge(pokemon["id"], pokemon.get("pokemon_type"))
        newbie_tag = ""
        if is_newbie_spawn:
            newbie_tag = t(_lang, "spawn_msg.newbie_tag")

        # 스폰 시 성격 + IV 미리 결정 (카드 표시 + 포획 시 동일 사용)
        from utils.battle_calc import generate_personality as _gen_pers, generate_ivs, personality_to_str, iv_total as _iv_total_fn
        _personality = _gen_pers(is_shiny=is_shiny)
        _personality_str = personality_to_str(_personality)
        _pre_ivs = generate_ivs(is_shiny=is_shiny)

        # 성격 태그 (티어 색상 이모지 + 이름)
        _pers_name = _personality["name"]
        _pers_tier = _personality["tier"]
        _tier_emoji = {"T1": "⚪", "T2": "🔵", "T3": "🟡", "T4": "🟢"}.get(_pers_tier, "⚪")
        personality_tag = f"{_tier_emoji}<b>{_pers_name}</b> "
        caption = t(_lang, "spawn_msg.wild_appeared",
                     icon=icon_emoji('footsteps'), shiny=shiny_text, tb=tb,
                     name=poke_name(pokemon, _lang), bonus=bonus_text, weather=weather_tag,
                     window=window, newbie=newbie_tag, personality=personality_tag)

        # Generate card image (Playwright async 렌더링)
        _types = pokemon.get("pokemon_type")
        if isinstance(_types, str):
            _types = [_types]
        _spawn_iv = _iv_total_fn(
            _pre_ivs["iv_hp"], _pre_ivs["iv_atk"], _pre_ivs["iv_def"],
            _pre_ivs["iv_spa"], _pre_ivs["iv_spdef"], _pre_ivs["iv_spd"])
        try:
            from utils.card_renderer import render_card_html_async
            card_buf = await render_card_html_async(
                pokemon["id"], f"야생의 {pokemon['name_ko']}", rarity,
                is_shiny=is_shiny, iv_total=_spawn_iv, types=_types,
                personality_str=_personality_str,
            )
        except Exception as e:
            logger.warning(f"Playwright render failed, falling back to PIL: {e}")
            from functools import partial
            loop = asyncio.get_event_loop()
            card_buf = await loop.run_in_executor(
                None, partial(generate_card, pokemon["id"], f"야생의 {pokemon['name_ko']}",
                              rarity, pokemon["emoji"], is_shiny, types=_types, iv_total=_spawn_iv)
            )

        # 이전 스폰의 포획 메시지가 완전히 전송될 때까지 대기
        lock = _get_chat_lock(chat_id)
        await asyncio.wait_for(lock.acquire(), timeout=10)
        lock.release()

        # Send photo BEFORE creating session (so catch isn't possible without image)
        message = await context.bot.send_photo(
            chat_id=chat_id,
            photo=card_buf,
            caption=caption,
            parse_mode="HTML",
        )

        # Auto-delete spawn image after 1 hour to reduce chat clutter
        schedule_delete(message, 3600)

        # 6. Create spawn session AFTER image is sent
        expires = (config.get_kst_now() + timedelta(seconds=window))

        session_id = await spawn_queries.create_spawn_session(
            chat_id, pokemon["id"], expires, is_shiny=is_shiny,
            is_newbie_spawn=is_newbie_spawn,
            pre_ivs=_pre_ivs, personality=_personality_str,
        )

        # Update session with message_id
        from database.connection import get_db
        pool = await get_db()
        await pool.execute(
            "UPDATE spawn_sessions SET message_id = $1 WHERE id = $2",
            message.message_id, session_id,
        )

        # 7. Record spawn
        await spawn_queries.record_spawn_in_chat(chat_id)

        # 8. Schedule resolution
        context.job_queue.run_once(
            resolve_spawn,
            when=window,
            data={
                "chat_id": chat_id,
                "session_id": session_id,
                "pokemon_id": pokemon["id"],
                "pokemon_name": pokemon["name_ko"],
                "pokemon_name_en": pokemon.get("name_en", ""),
                "pokemon_emoji": pokemon["emoji"],
                "rarity": rarity,
                "is_shiny": is_shiny,
                "is_newbie_spawn": is_newbie_spawn,
                "personality": _personality_str,
            },
            name=f"resolve_{session_id}",
        )

        logger.info(
            f"Spawned {pokemon['name_ko']} ({rarity}) in chat {chat_id}"
        )

    except Exception as e:
        # Handle group → supergroup migration
        if "migrate" in str(e).lower() and hasattr(e, "new_chat_id"):
            new_id = e.new_chat_id
            logger.info(f"Chat {chat_id} migrated to {new_id}, updating DB...")
            try:
                pool = await queries.get_db()
                await pool.execute(
                    "UPDATE chat_rooms SET chat_id = $1 WHERE chat_id = $2",
                    new_id, chat_id,
                )
                logger.info(f"Chat migration {chat_id} → {new_id} done.")
            except Exception as me:
                logger.error(f"Chat migration update failed: {me}")
        elif "kicked" in str(e).lower() or "forbidden" in str(e).lower():
            logger.info(f"Bot kicked from chat {chat_id}, deactivating...")
            try:
                pool = await queries.get_db()
                await pool.execute(
                    "UPDATE chat_rooms SET is_active = 0 WHERE chat_id = $1",
                    chat_id,
                )
                logger.info(f"Chat {chat_id} deactivated.")
            except Exception as de:
                logger.error(f"Chat deactivation failed: {de}")
        else:
            logger.error(f"Spawn execution failed for chat {chat_id}: {e}")
