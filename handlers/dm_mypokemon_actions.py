"""DM handlers for My Pokemon (내포켓몬) — action callbacks (feed/play/evolve/release/team/partner)."""

import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config

from database import queries
from utils.helpers import rarity_badge, rarity_badge_label, shiny_emoji, icon_emoji, type_badge, pokemon_iv_total as _iv_sum
from utils.battle_calc import iv_total
from utils.i18n import t, get_user_lang, poke_name

from handlers.dm_mypokemon import (
    MYPOKE_PAGE_SIZE,
    _get_filter, _build_list_view, _build_detail_view,
    _build_group_view, _format_appraisal,
)

logger = logging.getLogger(__name__)


async def _do_feed(p: dict, user_id: int, lang: str = "ko") -> tuple[str, bool]:
    """Execute feed action, return (result message, success)."""
    # 칭호 버프: 밥주기 추가 횟수
    feed_limit = config.FEED_PER_DAY
    user_data = await queries.get_user(user_id)
    if user_data and user_data.get("title"):
        buff = config.get_title_buff_by_name(user_data["title"])
        if buff and buff.get("extra_feed"):
            feed_limit += buff["extra_feed"]

    if p["fed_today"] >= feed_limit:
        return f"오늘은 이미 밥을 {feed_limit}번 줬습니다!", False
    max_f = config.get_max_friendship(p)
    if p["friendship"] >= max_f:
        return f"{poke_name(p, lang)} 친밀도 MAX!", False
    from services.event_service import get_friendship_boost
    boost = await get_friendship_boost()
    gain = config.FRIENDSHIP_PER_FEED * boost
    new_f = await queries.atomic_feed(p["id"], gain, max_f)
    if new_f is None:
        return "오류가 발생했습니다.", False
    remaining = feed_limit - p["fed_today"] - 1
    return f"🍖 {poke_name(p, lang)}에게 밥! 친밀도 {new_f}/{max_f} (남은: {remaining}회)", True


async def _do_play(p: dict, user_id: int, lang: str = "ko") -> tuple[str, bool]:
    """Execute play action, return (result message, success)."""
    if p["played_today"] >= config.PLAY_PER_DAY:
        return f"오늘은 이미 {config.PLAY_PER_DAY}번 놀아줬습니다!", False
    max_f = config.get_max_friendship(p)
    if p["friendship"] >= max_f:
        return f"{poke_name(p, lang)} 친밀도 MAX!", False
    from services.event_service import get_friendship_boost
    boost = await get_friendship_boost()
    gain = config.FRIENDSHIP_PER_PLAY * boost
    new_f = await queries.atomic_play(p["id"], gain, max_f)
    if new_f is None:
        return "오류가 발생했습니다.", False
    remaining = config.PLAY_PER_DAY - p["played_today"] - 1
    return f"🎾 {poke_name(p, lang)}와 놀기! 친밀도 {new_f}/{max_f} (남은: {remaining}회)", True


async def _build_team_settings(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Build unified team settings menu (팀설정)."""
    from database import battle_queries as bq

    team1, team2, active = await asyncio.gather(
        bq.get_battle_team(user_id, 1),
        bq.get_battle_team(user_id, 2),
        bq.get_active_team_number(user_id),
    )

    t1_info = f"({len(team1)}마리)" if team1 else "(비어있음)"
    t2_info = f"({len(team2)}마리)" if team2 else "(비어있음)"
    t1_active = f" {icon_emoji('check')}" if active == 1 else ""
    t2_active = f" {icon_emoji('check')}" if active == 2 else ""

    lines = [
        f"{icon_emoji('battle')} <b>팀 설정</b>\n",
        f"팀1 {t1_info}{t1_active}",
        f"팀2 {t2_info}{t2_active}",
    ]

    buttons = [
        [
            InlineKeyboardButton("✏️ 팀1 편집", callback_data=f"tedit_{user_id}_1"),
            InlineKeyboardButton("✏️ 팀2 편집", callback_data=f"tedit_{user_id}_2"),
        ],
        [
            InlineKeyboardButton("🔀 팀1↔팀2 교환", callback_data=f"tswap_teams_{user_id}"),
        ],
    ]

    # 활성 팀 전환 버튼 (비활성 팀만 표시)
    active_row = []
    if active != 1 and team1:
        active_row.append(InlineKeyboardButton("✅ 팀1 활성", callback_data=f"mypoke_tact_{user_id}_1"))
    if active != 2 and team2:
        active_row.append(InlineKeyboardButton("✅ 팀2 활성", callback_data=f"mypoke_tact_{user_id}_2"))
    if active_row:
        buttons.append(active_row)

    buttons.append([
        InlineKeyboardButton("📋 내포켓몬으로", callback_data=f"mypoke_l_{user_id}_0"),
    ])

    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def _do_evolve(p: dict, user_id: int, lang: str = "ko") -> str:
    """Execute evolution, return result message."""
    pokemon_id = p.get("pokemon_id") or p.get("id")
    has_branch = pokemon_id in config.BRANCH_EVOLUTIONS
    is_eevee = pokemon_id == config.EEVEE_ID

    if not p["evolves_to"] and not has_branch and not is_eevee:
        return t(lang, "my_pokemon.cannot_evolve")
    if p["evolution_method"] == "trade":
        return t(lang, "my_pokemon.trade_evolve_only")
    max_f = config.get_max_friendship(p)
    if p["friendship"] < max_f:
        return f"친밀도가 부족합니다 ({p['friendship']}/{max_f})"

    # Determine target (분기진화 / 이브이 / 일반)
    if is_eevee:
        import random
        target_id = random.choice(config.EEVEE_EVOLUTIONS)
    elif has_branch:
        import random
        target_id = random.choice(config.BRANCH_EVOLUTIONS[pokemon_id])
    else:
        target_id = p["evolves_to"]

    evo_target = await queries.get_pokemon_master(target_id)
    if not evo_target:
        return t(lang, "my_pokemon.evolve_target_not_found")
    await queries.evolve_pokemon(p["id"], target_id)
    return f"🎉 {poke_name(p, lang)}이(가) {poke_name(evo_target, lang)}(으)로 진화했습니다!"


async def _build_slot_picker(user_id: int, p: dict, idx: int, page: int,
                             team_num: int, lang: str = "ko") -> tuple[str, InlineKeyboardMarkup]:
    """Show 6 team slots for placing a pokemon."""
    from database import battle_queries as bq
    team = await bq.get_battle_team(user_id, team_num)
    slot_emojis = [icon_emoji(str(i)) for i in range(1, 7)]
    slot_plain = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]
    slot_map = {t["slot"]: t for t in team}

    shiny = shiny_emoji() if p.get("is_shiny") else ""
    tb = type_badge(p["pokemon_id"], p.get("pokemon_type"))
    lines = [f"{icon_emoji('battle')} 팀{team_num}에 {tb}{shiny} {poke_name(p, lang)} 배치", "슬롯을 선택하세요:\n"]

    buttons = []
    for s in range(1, 7):
        if s in slot_map:
            t = slot_map[s]
            t_iv = ""
            if t.get("iv_hp") is not None:
                total = iv_total(t["iv_hp"], t.get("iv_atk", 0), t.get("iv_def", 0),
                                 t.get("iv_spa", 0), t.get("iv_spdef", 0), t.get("iv_spd", 0))
                grade, _ = config.get_iv_grade(total)
                t_iv = f" [{grade}]{total}"
            ttb = type_badge(t["pokemon_id"], t.get("pokemon_type"))
            t_shiny = shiny_emoji() if t.get("is_shiny") else ""
            lines.append(f"{slot_emojis[s-1]} {ttb}{t_shiny} {poke_name(t, lang)}{t_iv}")
            label = f"{slot_plain[s-1]} {poke_name(t, lang)} → 교체"
        else:
            lines.append(f"{slot_emojis[s-1]} (빈 슬롯)")
            label = f"{slot_plain[s-1]} 빈 슬롯 ← 배치"
        buttons.append([InlineKeyboardButton(
            label, callback_data=f"mypoke_tset_{user_id}_{idx}_{page}_{s}_{team_num}"
        )])

    buttons.append([InlineKeyboardButton("❌ 취소", callback_data=f"mypoke_v_{user_id}_{idx}_{page}")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def _do_set_slot(p: dict, user_id: int, team_num: int, slot: int, lang: str = "ko") -> str:
    """Place pokemon into a specific team slot. Returns result message."""
    from database import battle_queries as bq
    team = await bq.get_battle_team(user_id, team_num)

    # Check if already on this team
    for t in team:
        if t.get("pokemon_instance_id") == p["id"]:
            if t["slot"] == slot:
                return f"이미 슬롯 {slot}에 등록되어 있습니다!"
            return f"이미 팀{team_num}의 슬롯 {t['slot']}에 등록되어 있습니다!"

    # Build new slot map
    slot_map = {t["slot"]: t["pokemon_instance_id"] for t in team}
    replaced_name = None
    for t in team:
        if t["slot"] == slot:
            replaced_name = poke_name(t, lang)
    slot_map[slot] = p["id"]

    # Validate: ultra_legendary limit (1 per team)
    if p["rarity"] == "ultra_legendary":
        ul_count = sum(
            1 for t in team
            if t.get("rarity") == "ultra_legendary" and t["slot"] != slot
        )
        if ul_count >= 1:
            return "초전설 포켓몬은 팀당 1마리만 가능합니다!"

    # Validate: same-species duplicate (epic/legendary/ultra_legendary)
    if p["rarity"] in ("epic", "legendary", "ultra_legendary"):
        for t in team:
            if t["slot"] != slot and t.get("rarity") in ("epic", "legendary", "ultra_legendary") and t.get("pokemon_id") == p["pokemon_id"]:
                return "같은 종의 포켓몬은 중복 불가!"

    # Validate: COST limit
    import config
    total_cost = config.RANKED_COST.get(p["rarity"], 0)
    for t in team:
        if t["slot"] != slot:
            total_cost += config.RANKED_COST.get(t.get("rarity", ""), 0)
    if total_cost > config.RANKED_COST_LIMIT:
        return f"❌ 팀 코스트 초과! ({total_cost}/{config.RANKED_COST_LIMIT})\n코스트 {config.RANKED_COST_LIMIT} 이하로 편성해주세요."

    # Save
    instance_ids = [slot_map[s] for s in sorted(slot_map.keys())]
    await bq.set_battle_team(user_id, instance_ids, team_num)

    if replaced_name:
        return f"슬롯{slot}: {replaced_name} → {poke_name(p, lang)} 교체!"
    return f"{poke_name(p, lang)}(를) 슬롯 {slot}에 배치!"


async def my_pokemon_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 내포켓몬 callbacks: list, detail, group, and action buttons."""
    query = update.callback_query
    if not query or not query.data.startswith("mypoke_"):
        return

    data = query.data
    parts = data.split("_")
    action = parts[1]
    user_id = int(parts[2])
    lang = await get_user_lang(user_id)

    if query.from_user.id != user_id:
        return

    # feed/play/evo/relconf 등 show_alert 필요한 액션은 자체 answer
    _self_answer_actions = {"feed", "play", "evo", "relconf", "tact", "tset"}
    if action not in _self_answer_actions:
        await query.answer()

    pokemon_list = await queries.get_user_pokemon_list(user_id)
    if not pokemon_list:
        try:
            await query.edit_message_text(t(lang, "my_pokemon.no_pokemon"))
        except Exception:
            pass
        return

    filt = _get_filter(context)

    try:
        if action == "l":
            page = int(parts[3])
            text, markup = _build_list_view(user_id, pokemon_list, page, filt=filt, lang=lang)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "sort":
            # mypoke_sort_{user_id}_{mode}
            mode = parts[3]
            if filt["sort"] == mode:
                filt["sort"] = "default"  # toggle off
            else:
                filt["sort"] = mode
            text, markup = _build_list_view(user_id, pokemon_list, 0, filt=filt, lang=lang)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "gen":
            # mypoke_gen_{user_id}_{gen_num} — toggle generation filter
            gen_num = int(parts[3])
            if filt.get("gen") == gen_num:
                filt["gen"] = None  # toggle off
            else:
                filt["gen"] = gen_num
            text, markup = _build_list_view(user_id, pokemon_list, 0, filt=filt, lang=lang)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "genm":
            # mypoke_genm_{user_id} — open generation sub-filter
            filt["gen_open"] = True
            text, markup = _build_list_view(user_id, pokemon_list, 0, filt=filt, lang=lang)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "genc":
            # mypoke_genc_{user_id} — close generation sub-filter
            filt["gen_open"] = False
            text, markup = _build_list_view(user_id, pokemon_list, 0, filt=filt, lang=lang)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "shiny":
            # mypoke_shiny_{user_id} — toggle shiny filter
            filt["shiny"] = not filt.get("shiny", False)
            text, markup = _build_list_view(user_id, pokemon_list, 0, filt=filt, lang=lang)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")


        elif action == "tf":
            # mypoke_tf_{user_id}_{type_key} — set type filter
            type_key = parts[3]
            if type_key == "x":
                filt["type"] = None
            else:
                filt["type"] = type_key
            text, markup = _build_list_view(user_id, pokemon_list, 0, filt=filt, lang=lang)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "tmore":
            # mypoke_tmore_{user_id} — show type filter grid
            type_keys = ["fire", "water", "grass", "electric", "ice", "fighting",
                         "poison", "ground", "flying", "psychic", "bug", "rock",
                         "ghost", "dragon", "dark", "steel", "fairy", "normal"]
            type_names = config.TYPE_NAME_KO
            btns = []
            row = []
            for tk in type_keys:
                tn = type_names.get(tk, tk)
                emoji = config.TYPE_EMOJI.get(tk, "")
                row.append(InlineKeyboardButton(f"{emoji}{tn}", callback_data=f"mypoke_tf_{user_id}_{tk}"))
                if len(row) == 3:
                    btns.append(row)
                    row = []
            if row:
                btns.append(row)
            btns.append([InlineKeyboardButton("✕ 필터 해제", callback_data=f"mypoke_tf_{user_id}_x")])
            btns.append([InlineKeyboardButton("◀ 돌아가기", callback_data=f"mypoke_l_{user_id}_0")])
            await query.edit_message_text("🏷 타입 필터 선택", reply_markup=InlineKeyboardMarkup(btns))

        elif action == "v":
            idx = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else idx // MYPOKE_PAGE_SIZE
            idx = max(0, min(idx, len(pokemon_list) - 1))
            text, markup = _build_detail_view(user_id, pokemon_list, idx, page, lang=lang)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "g":
            # Group view: mypoke_g_{user_id}_{pokemon_id}_{page}
            pokemon_id = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else 0
            text, markup = _build_group_view(user_id, pokemon_list, pokemon_id, page, lang=lang)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "appr":
            # Appraisal: show IV info inline
            idx = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else 0
            idx = max(0, min(idx, len(pokemon_list) - 1))
            p = pokemon_list[idx]
            text = _format_appraisal(p, lang=lang)
            # Back button to detail
            markup = InlineKeyboardMarkup([[
                InlineKeyboardButton("◀ 돌아가기", callback_data=f"mypoke_v_{user_id}_{idx}_{page}")
            ]])
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "feed":
            idx = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else 0
            idx = max(0, min(idx, len(pokemon_list) - 1))
            p = pokemon_list[idx]
            result, fed = await _do_feed(p, user_id, lang=lang)
            await query.answer(result, show_alert=True)
            if fed:
                async def _feed_mission():
                    try:
                        from services.mission_service import check_mission_progress
                        msg = await check_mission_progress(user_id, "feed")
                        if msg:
                            await query.get_bot().send_message(
                                chat_id=user_id, text=msg, parse_mode="HTML",
                            )
                    except Exception:
                        pass
                asyncio.create_task(_feed_mission())
            # Refresh detail
            pokemon_list = await queries.get_user_pokemon_list(user_id)
            idx = max(0, min(idx, len(pokemon_list) - 1))
            text, markup = _build_detail_view(user_id, pokemon_list, idx, page, lang=lang)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "play":
            idx = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else 0
            idx = max(0, min(idx, len(pokemon_list) - 1))
            p = pokemon_list[idx]
            result, played = await _do_play(p, user_id, lang=lang)
            await query.answer(result, show_alert=True)
            if played:
                async def _play_mission():
                    try:
                        from services.mission_service import check_mission_progress
                        msg = await check_mission_progress(user_id, "play")
                        if msg:
                            await query.get_bot().send_message(
                                chat_id=user_id, text=msg, parse_mode="HTML",
                            )
                    except Exception:
                        pass
                asyncio.create_task(_play_mission())
            pokemon_list = await queries.get_user_pokemon_list(user_id)
            idx = max(0, min(idx, len(pokemon_list) - 1))
            text, markup = _build_detail_view(user_id, pokemon_list, idx, page, lang=lang)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "evo":
            idx = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else 0
            idx = max(0, min(idx, len(pokemon_list) - 1))
            p = pokemon_list[idx]
            result = await _do_evolve(p, user_id, lang=lang)
            await query.answer(result, show_alert=True)
            pokemon_list = await queries.get_user_pokemon_list(user_id)
            idx = max(0, min(idx, len(pokemon_list) - 1))
            text, markup = _build_detail_view(user_id, pokemon_list, idx, page, lang=lang)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action in ("t1", "t2"):
            idx = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else 0
            idx = max(0, min(idx, len(pokemon_list) - 1))
            p = pokemon_list[idx]
            team_num = 1 if action == "t1" else 2
            text, markup = await _build_slot_picker(user_id, p, idx, page, team_num, lang=lang)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "tset":
            # mypoke_tset_{uid}_{idx}_{page}_{slot}_{team_num}
            idx = int(parts[3])
            page = int(parts[4])
            slot = int(parts[5])
            team_num = int(parts[6])
            idx = max(0, min(idx, len(pokemon_list) - 1))
            p = pokemon_list[idx]
            result = await _do_set_slot(p, user_id, team_num, slot, lang=lang)
            await query.answer(result, show_alert=True)
            pokemon_list = await queries.get_user_pokemon_list(user_id)
            idx = max(0, min(idx, len(pokemon_list) - 1))
            text, markup = _build_detail_view(user_id, pokemon_list, idx, page, lang=lang)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "team":
            # mypoke_team_{user_id} — 통합 팀설정 메뉴
            text, markup = await _build_team_settings(user_id)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "tact":
            # mypoke_tact_{user_id}_{team_num} — 활성 팀 변경
            team_num = int(parts[3])
            from database import battle_queries as bq
            team = await bq.get_battle_team(user_id, team_num)
            if not team:
                await query.answer(f"팀 {team_num}이(가) 비어있습니다!", show_alert=True)
            else:
                await bq.set_active_team(user_id, team_num)
                await query.answer(f"✅ 팀 {team_num} 활성화!", show_alert=False)
            text, markup = await _build_team_settings(user_id)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "rel":
            # mypoke_rel_{user_id} — 방생 필터 패널 표시
            from handlers.dm_release import _build_panel, _get_filter as _get_rel_filter
            filt_rel = _get_rel_filter(context)
            text, markup = _build_panel(user_id, filt_rel)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "relone":
            # mypoke_relone_{user_id}_{idx}_{page} — 개별 방생 확인
            idx = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else 0
            idx = max(0, min(idx, len(pokemon_list) - 1))
            p = pokemon_list[idx]
            shiny_mark = "이로치 " if p.get("is_shiny") else ""
            rb_label = rarity_badge_label(p["rarity"])
            text = (
                f"🔄 <b>방생 확인</b>\n\n"
                f"{shiny_mark}{rb_label} <b>{poke_name(p, lang)}</b>을(를)\n"
                f"정말 방생하시겠습니까?\n\n"
                f"보상: 하이퍼볼 1개\n\n"
                f"⚠️ <b>방생한 포켓몬은 되돌릴 수 없습니다!</b>"
            )
            markup = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ 방생", callback_data=f"mypoke_relconf_{user_id}_{p['id']}_{page}"),
                    InlineKeyboardButton("◀ 취소", callback_data=f"mypoke_v_{user_id}_{idx}_{page}"),
                ],
            ])
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

        elif action == "relconf":
            # mypoke_relconf_{user_id}_{instance_id}_{page} — 개별 방생 실행
            instance_id = int(parts[3])
            page = int(parts[4]) if len(parts) > 4 else 0

            # 팀 등록된 포켓몬은 방생 불가
            target = None
            for p in pokemon_list:
                if p["id"] == instance_id:
                    target = p
                    break
            if not target:
                await query.answer(t(lang, "my_pokemon.already_released"), show_alert=True)
                return

            if target.get("team_slot") is not None:
                await query.answer("⚔️ 팀에 등록된 포켓몬은 방생할 수 없습니다! 팀에서 해제 후 시도하세요.", show_alert=True)
                return

            # 캠프/교환/거래소 잠금 체크
            locked, lock_reason = await queries.is_pokemon_locked(instance_id)
            if locked:
                await query.answer(lock_reason, show_alert=True)
                return

            released = await queries.bulk_deactivate_pokemon([instance_id])
            if released > 0:
                await queries.add_hyper_ball(user_id, 1)

            name = poke_name(target, lang)
            await query.answer(f"🔄 {name}을(를) 방생했습니다! 하이퍼볼 +1", show_alert=True)

            # 목록으로 복귀
            pokemon_list = await queries.get_user_pokemon_list(user_id)
            if pokemon_list:
                text, markup = _build_list_view(user_id, pokemon_list, page, filt=filt, lang=lang)
                await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
            else:
                await query.edit_message_text(t(lang, "my_pokemon.no_pokemon"))

        elif action == "partner":
            # mypoke_partner_{user_id} — 파트너 선택 리스트
            from handlers.battle import _build_partner_list
            text_msg, markup = _build_partner_list(user_id, pokemon_list, 0, lang=lang)
            await query.edit_message_text(text_msg, reply_markup=markup, parse_mode="HTML")

    except Exception:
        pass
