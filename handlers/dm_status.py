"""DM handlers for Status (상태창), Appraisal (감정), Type Chart (상성표)."""

import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import config
from database import queries, title_queries
from database import camp_queries as cq
from database import item_queries
from utils.helpers import (
    hearts_display, rarity_badge, icon_emoji, ball_emoji, type_badge,
    _type_emoji, shiny_emoji, resolve_title_badge,
    pokemon_iv_total as _iv_sum,
)
from utils.parse import parse_number, parse_name_arg
from utils.battle_calc import iv_total
from utils.i18n import t, get_user_lang, poke_name

logger = logging.getLogger(__name__)


# ============================================================
# Status (상태창) — DM only
# ============================================================

async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '상태창' command (DM) — show user's full status overview."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    display_name = update.effective_user.first_name or t(lang, "common.trainer")
    await queries.ensure_user(user_id, display_name, update.effective_user.username)

    from database import battle_queries as bq
    from utils.battle_calc import calc_battle_stats, format_stats_line, format_power, calc_power, EVO_STAGE_MAP, get_normalized_base_stats
    from models.pokemon_skills import POKEMON_SKILLS
    from models.pokemon_base_stats import POKEMON_BASE_STATS

    user, pokemon_list, partner, team, battle_stats = await asyncio.gather(
        queries.get_user(user_id),
        queries.get_user_pokemon_list(user_id),
        bq.get_partner(user_id),
        bq.get_battle_team(user_id),
        bq.get_battle_stats(user_id),
    )
    master_balls = user.get("master_balls", 0) if user else 0
    bp = battle_stats.get("battle_points", 0)

    # 칭호
    title = user.get("title", "") if user else ""
    title_emoji_raw = user.get("title_emoji", "") if user else ""
    if title and title_emoji_raw:
        badge = resolve_title_badge(title_emoji_raw, title)
        title_text = f"「{badge} {title}」"
    else:
        title_text = t(lang, "common.none")

    lines = [f"{icon_emoji('bookmark')} {t(lang, 'status_view.header', name=display_name)}\n"]

    # 기본 정보
    lines.append(f"🏷️ {t(lang, 'status_view.title_label')} {title_text}")
    lines.append(f"{ball_emoji('masterball')} {t(lang, 'status_view.masterball_label')} {t(lang, 'status_view.count_unit', n=master_balls)}")
    lines.append(f"{icon_emoji('coin')} BP: {bp}")
    lines.append(f"{icon_emoji('container')} {t(lang, 'status_view.pokemon_count', n=len(pokemon_list))}")

    # 도감 수 (pokedex 테이블 기준 — 방생해도 유지) — 팀2/활성팀도 미리 로드
    pokedex_count, active_num, team2 = await asyncio.gather(
        queries.count_pokedex(user_id),
        bq.get_active_team_number(user_id),
        bq.get_battle_team(user_id, 2),
    )
    shiny_count = sum(1 for p in pokemon_list if p.get("is_shiny"))
    lines.append(f"{icon_emoji('pokedex')} {t(lang, 'status_view.pokedex_count', n=pokedex_count)}")
    if shiny_count > 0:
        lines.append(f"{shiny_emoji()} {t(lang, 'status_view.shiny_count', n=shiny_count)}")

    # 배틀 전적
    wins = battle_stats.get("battle_wins", 0)
    losses = battle_stats.get("battle_losses", 0)
    total = wins + losses
    win_rate = f"{wins / total * 100:.0f}%" if total > 0 else "-"
    best = battle_stats.get("best_streak", 0)
    lines.append(f"\n{icon_emoji('battle')} {t(lang, 'status_view.battle_record', w=wins, l=losses, rate=win_rate)}")
    if best > 0:
        lines.append(f"🔥 {t(lang, 'status_view.best_streak', n=best)}")

    # 파트너
    lines.append("")
    if partner:
        _p_base = get_normalized_base_stats(partner["pokemon_id"])
        evo = 3 if _p_base else EVO_STAGE_MAP.get(partner["pokemon_id"], 3)
        stats = calc_battle_stats(
            partner["rarity"], partner["stat_type"], partner["friendship"], evo_stage=evo,
            iv_hp=partner.get("iv_hp"), iv_atk=partner.get("iv_atk"),
            iv_def=partner.get("iv_def"), iv_spa=partner.get("iv_spa"),
            iv_spdef=partner.get("iv_spdef"), iv_spd=partner.get("iv_spd"),
            **(_p_base or {}),
        )
        base = calc_battle_stats(partner["rarity"], partner["stat_type"], partner["friendship"], evo_stage=evo, **(_p_base or {}))
        tb = type_badge(partner["pokemon_id"], partner["pokemon_type"])
        pbs = POKEMON_BASE_STATS.get(partner["pokemon_id"])
        if pbs:
            type_name = "/".join(t(lang, f"type.{tp}") for tp in pbs[-1])
        else:
            type_name = t(lang, f"type.{partner['pokemon_type']}")
        from models.pokemon_skills import get_skill_display
        _skill_disp = get_skill_display(partner["pokemon_id"])
        lines.append(f"{icon_emoji('pokemon-love')} {t(lang, 'status_view.partner_label')} {tb} {poke_name(partner, lang)}  {type_name}  {icon_emoji('bolt')}{format_power(stats, base)}")
        lines.append(f"   {icon_emoji('favorite')} {t(lang, 'status_view.friendship_label')} {hearts_display(partner['friendship'])}")
        lines.append(f"   {icon_emoji('stationery')} {format_stats_line(stats, base, lang=lang)}")
        lines.append(f"   {icon_emoji('skill')} {t(lang, 'status_view.skill_label')} {_skill_disp}")
    else:
        lines.append(f"{icon_emoji('pokemon-love')} {t(lang, 'status_view.partner_label')} {t(lang, 'status_view.partner_none')}")

    # 팀 (active_num, team2는 위에서 미리 로드됨)
    lines.append("")
    if team:
        lines.append(f"{icon_emoji('battle')} {t(lang, 'status_view.team_header', num=active_num, count=len(team))}")
        total_power = 0
        total_base_power = 0
        for i, tm in enumerate(team, 1):
            _t_base = get_normalized_base_stats(tm["pokemon_id"])
            evo = 3 if _t_base else EVO_STAGE_MAP.get(tm["pokemon_id"], 3)
            stats = calc_battle_stats(
                tm["rarity"], tm["stat_type"], tm["friendship"], evo_stage=evo,
                iv_hp=tm.get("iv_hp"), iv_atk=tm.get("iv_atk"),
                iv_def=tm.get("iv_def"), iv_spa=tm.get("iv_spa"),
                iv_spdef=tm.get("iv_spdef"), iv_spd=tm.get("iv_spd"),
                **(_t_base or {}),
            )
            tbase = calc_battle_stats(tm["rarity"], tm["stat_type"], tm["friendship"], evo_stage=evo, **(_t_base or {}))
            total_power += calc_power(stats)
            total_base_power += calc_power(tbase)
            from models.pokemon_skills import get_skill_display
            _skill_disp = get_skill_display(tm["pokemon_id"])
            ttb = type_badge(tm["pokemon_id"], tm.get("pokemon_type"))
            lines.append(f"  {i}. {ttb} {poke_name(tm, lang)}  {icon_emoji('skill')}{_skill_disp}  {icon_emoji('bolt')}{format_power(stats, tbase)}")
        iv_diff = total_power - total_base_power
        total_tag = f"{total_power}(+{iv_diff})" if iv_diff > 0 else str(total_power)
        lines.append(f"  {icon_emoji('bolt')} {t(lang, 'status_view.team_power', power=total_tag)}")
        if team2:
            lines.append(f"  {t(lang, 'status_view.team2_info', n=len(team2))}")
    else:
        lines.append(f"{icon_emoji('battle')} {t(lang, 'status_view.team_none')}")

    # 아이템
    arcade_tickets = await queries.get_arcade_tickets(user_id)
    hyper_balls = await queries.get_hyper_balls(user_id)
    if arcade_tickets > 0 or hyper_balls > 0:
        lines.append("")
    if arcade_tickets > 0:
        lines.append(f"{icon_emoji('game')} {t(lang, 'status_view.arcade_ticket', n=arcade_tickets)}")
    if hyper_balls > 0:
        lines.append(f"{ball_emoji('hyperball')} {t(lang, 'status_view.hyperball_label', n=hyper_balls)}")

    # 조각 / 결정
    fragments = await cq.get_user_fragments(user_id)
    uni_frags = await item_queries.get_universal_fragments(user_id)
    crystals = await cq.get_crystals(user_id)
    total_frags = sum(fragments.values()) + uni_frags
    crystal_count = crystals.get("crystal", 0)
    rainbow_count = crystals.get("rainbow", 0)
    if total_frags > 0 or crystal_count > 0 or rainbow_count > 0:
        lines.append("")
        frag_parts = []
        if total_frags > 0:
            frag_parts.append(f"🧩 {t(lang, 'status_view.fragment_label', n=total_frags)}")
        if crystal_count > 0:
            frag_parts.append(f"💎 {t(lang, 'status_view.crystal_label', n=crystal_count)}")
        if rainbow_count > 0:
            frag_parts.append(f"🌈 {t(lang, 'status_view.rainbow_label', n=rainbow_count)}")
        lines.append(" / ".join(frag_parts) + f" {t(lang, 'status_view.item_detail_hint')}")

    # 상태창 인라인 버튼 (칭호 바로가기)
    inline_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"🏷️ {t(lang, 'status_view.btn_title')}", callback_data=f"status_title_{user_id}"),
            InlineKeyboardButton(f"📖 {t(lang, 'status_view.btn_pokedex')}", callback_data=f"status_dex_{user_id}"),
        ],
    ])

    await update.message.reply_text("\n".join(lines), reply_markup=inline_kb, parse_mode="HTML")


async def status_inline_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle status_title / status_dex inline button callbacks."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    if data.startswith("status_title_"):
        # 칭호 선택 페이지 표시
        from utils.title_checker import check_and_unlock_titles
        await check_and_unlock_titles(user_id)

        lang = await get_user_lang(user_id)
        unlocked = await title_queries.get_user_titles(user_id)
        user = await queries.get_user(user_id)
        current_title = user.get("title", "") if user else ""

        if not unlocked:
            await query.edit_message_text(
                f"🏷️ {t(lang, 'status_view.no_titles')}"
            )
            return

        from handlers.dm_title import _build_title_select_page
        text, markup = _build_title_select_page(unlocked, current_title, 0)
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")

    elif data.startswith("status_dex_"):
        # 도감 첫 페이지를 새 메시지로 전송
        from handlers.dm_pokedex import _get_dex_filter, _build_dex_view

        lang = await get_user_lang(user_id)
        display_name = query.from_user.first_name or t(lang, "common.trainer")
        filt = _get_dex_filter(context)

        pokedex, user, all_pokemon = await asyncio.gather(
            queries.get_user_pokedex(user_id),
            queries.get_user(user_id),
            queries.get_all_pokemon(),
        )
        caught_ids = {p["pokemon_id"]: p for p in pokedex}
        title_part = f" {user['title_emoji']} {user['title']}" if user and user["title"] else ""

        text_msg, markup = _build_dex_view(
            user_id, display_name, title_part, all_pokemon, caught_ids, 0, filt, lang=lang,
        )
        await query.message.reply_text(text_msg, reply_markup=markup, parse_mode="HTML")


# ============================================================
# IV Appraisal (감정)
# ============================================================

async def appraisal_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '감정 [이름/번호]' command — show Pokemon IV stats."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    await queries.ensure_user(
        user_id,
        update.effective_user.first_name or t(lang, "common.trainer"),
        update.effective_user.username,
    )

    text = update.message.text or ""
    index = parse_number(text)
    name_arg = parse_name_arg(text)

    pokemon = None
    if index is not None:
        pokemon = await queries.get_user_pokemon_by_index(user_id, index)
    elif name_arg:
        pokemon = await queries.get_user_pokemon_by_name(user_id, name_arg)
    else:
        await update.message.reply_text("사용법: 감정 [이름 또는 번호]\n예: 감정 피카츄, 감정 3")
        return

    if not pokemon:
        query_text = index if index is not None else name_arg
        await update.message.reply_text(
            f"'{query_text}' 포켓몬을 찾을 수 없습니다.\n내포켓몬 으로 목록을 확인하세요."
        )
        return

    # Read IVs
    ivs = {
        "HP": pokemon.get("iv_hp"),
        "ATK": pokemon.get("iv_atk"),
        "DEF": pokemon.get("iv_def"),
        "SPA": pokemon.get("iv_spa"),
        "SPDEF": pokemon.get("iv_spdef"),
        "SPD": pokemon.get("iv_spd"),
    }

    total = iv_total(
        ivs["HP"], ivs["ATK"], ivs["DEF"],
        ivs["SPA"], ivs["SPDEF"], ivs["SPD"],
    )
    grade, _ = config.get_iv_grade(total)
    pct = round(total / 186 * 100, 1)

    # Build display
    shiny = shiny_emoji() if pokemon.get("is_shiny") else ""
    rb = rarity_badge(pokemon.get("rarity", "common"))
    name = poke_name(pokemon, lang)

    stat_labels = {
        "HP": "HP   ", "ATK": "공격 ", "DEF": "방어 ",
        "SPA": "특공 ", "SPDEF": "특방 ", "SPD": "스피드",
    }

    lines = [f"📋 {shiny}{rb} {name} 감정 결과\n"]
    max_iv = config.IV_MAX  # 31

    for key in ("HP", "ATK", "DEF", "SPA", "SPDEF", "SPD"):
        v = ivs[key] if ivs[key] is not None else 15
        label = stat_labels[key]
        filled = round(v / max_iv * 6)
        bar = "█" * filled + "░" * (6 - filled)
        # Highlight perfect (31) or near-perfect (28+)
        if v >= 28:
            mark = " ★"
        elif v <= 5:
            mark = " ✗"
        else:
            mark = ""
        lines.append(f"{label} {bar} {v}/{max_iv}{mark}")

    from utils.helpers import format_personality_tag as _fpt
    _pers_tag = _fpt(pokemon.get("personality")).strip()
    lines.append(f"\n총합: {total}/186 ({pct}%)")
    lines.append(f"등급: {grade}")
    if _pers_tag:
        lines.append(f"성격: {_pers_tag}")

    # Grade flavor text
    flavor = {
        "S": "이 포켓몬은 최상급 개체입니다!",
        "A": "매우 뛰어난 개체입니다.",
        "B": "괜찮은 개체입니다.",
        "C": "평범한 개체입니다.",
        "D": "개체값이 낮습니다...",
    }
    lines.append(flavor.get(grade, ""))

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ============================================================
# Type Chart (상성표)
# ============================================================

async def type_chart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle '상성 [타입]' command — show type effectiveness."""
    if not update.effective_user or not update.message:
        return
    lang = await get_user_lang(update.effective_user.id)

    text = update.message.text or ""
    name_arg = parse_name_arg(text)

    if name_arg:
        # Specific type detail
        # Find type by Korean name or English key
        target_type = None
        for eng, ko in config.TYPE_NAME_KO.items():
            if name_arg == ko or name_arg.lower() == eng:
                target_type = eng
                break
        if not target_type:
            type_list = " ".join(f"{_type_emoji(tp)}{config.TYPE_NAME_KO[tp]}" for tp in config.TYPE_ADVANTAGE)
            await update.message.reply_text(f"'{name_arg}' 타입을 찾을 수 없습니다.\n\n사용 가능: {type_list}", parse_mode="HTML")
            return

        te = _type_emoji(target_type)
        ko = config.TYPE_NAME_KO.get(target_type, target_type)

        # Offense: what this type is strong against
        strong = config.TYPE_ADVANTAGE.get(target_type, [])
        # Offense: what this type is immune to (hits for 0.3x)
        immune_vs = config.TYPE_IMMUNITY.get(target_type, [])

        # Defense: what is strong against this type
        weak_to = []
        resist_from = []
        immune_from = []
        for atk_type, adv_list in config.TYPE_ADVANTAGE.items():
            if target_type in adv_list:
                weak_to.append(atk_type)
        for atk_type, res_list in config.TYPE_RESISTANCE.items():
            if target_type in res_list:
                resist_from.append(atk_type)
        for atk_type, imm_list in config.TYPE_IMMUNITY.items():
            if target_type in imm_list:
                immune_from.append(atk_type)

        def fmt(types):
            if not types:
                return "없음"
            return " ".join(f"{_type_emoji(tp)}{config.TYPE_NAME_KO.get(tp, tp)}" for tp in types)

        lines = [
            f"{te} {ko} 타입 상성\n",
            f"⚔️ 공격 시 효과적 (2x):",
            f"  {fmt(strong)}",
        ]
        if immune_vs:
            lines.append(f"\n🚫 공격 시 면역 (0x):")
            lines.append(f"  {fmt(immune_vs)}")
        lines.append(f"\n🛡️ 방어 시 약점 (2x 피해):")
        lines.append(f"  {fmt(weak_to)}")
        if resist_from:
            lines.append(f"\n🛡️ 방어 시 반감 (0.5x 피해):")
            lines.append(f"  {fmt(resist_from)}")
        if immune_from:
            lines.append(f"\n🛡️ 방어 시 면역 (0x 피해):")
            lines.append(f"  {fmt(immune_from)}")

        lines.append(f"\n💡 듀얼타입 상대 시: 각 타입에 대한 배율이 곱해집니다")
        lines.append(f"  예: {te}{ko} → 강철/드래곤 = 강철 배율 × 드래곤 배율")

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    else:
        # Full chart summary
        lines = ["⚔️ 타입 상성표\n"]
        for atk_type, adv_list in config.TYPE_ADVANTAGE.items():
            if not adv_list:
                continue
            te = _type_emoji(atk_type)
            ko = config.TYPE_NAME_KO.get(atk_type, atk_type)
            targets = " ".join(f"{_type_emoji(tp)}{config.TYPE_NAME_KO.get(tp, tp)}" for tp in adv_list)
            lines.append(f"{te}{ko} → {targets}")
        lines.append(f"\n💡 상성 [타입] 으로 상세 보기\n예: 상성 불꽃")
        lines.append(f"\n📖 <b>상성 가이드</b>")
        lines.append(f"• 듀얼타입 포켓몬은 더 유리한 타입 하나로 공격")
        lines.append(f"• 두 타입이 합산되지 않음 (4배 아님)")
        lines.append(f"• 4배는 상대의 두 타입 모두에 유리할 때만")
        lines.append(f"  예: 얼음→한카리아스(드래곤/땅) = 2×2 = 4배")
        lines.append(f"• 불→디아루가(강철/드래곤) = 강철2배×드래곤0.5배 = 1배 (상쇄)")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
