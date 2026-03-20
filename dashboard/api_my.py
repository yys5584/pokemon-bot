"""Dashboard API — My Pokemon, Summary, Pokedex, Camp, Fusion."""

import asyncio
import logging

from aiohttp import web
from asyncpg import InterfaceError

import config
from database import queries
from utils.battle_calc import (
    calc_battle_stats, calc_power, iv_total,
    get_normalized_base_stats, EVO_STAGE_MAP, _iv_mult,
)
from models.pokemon_base_stats import POKEMON_BASE_STATS

logger = logging.getLogger(__name__)

# Synergy weight presets per stat_type
_SYNERGY_WEIGHTS = {
    "offensive":  {"hp": 0.8, "atk": 2.0, "def": 0.4, "spa": 2.0, "spdef": 0.4, "spd": 1.5},
    "defensive":  {"hp": 2.0, "atk": 0.4, "def": 2.0, "spa": 0.4, "spdef": 2.0, "spd": 0.5},
    "balanced":   {"hp": 1.2, "atk": 1.2, "def": 1.0, "spa": 1.2, "spdef": 1.0, "spd": 1.2},
    "speedy":     {"hp": 0.5, "atk": 1.5, "def": 0.3, "spa": 1.5, "spdef": 0.3, "spd": 2.5},
}

_SYNERGY_LABELS = {90: "완벽", 70: "우수", 50: "보통", 0: "아쉬움"}
_SYNERGY_EMOJI = {90: "⚡", 70: "🔥", 50: "⚖️", 0: "💤"}


def _calc_synergy(stat_type: str, ivs: dict) -> tuple[int, str, str]:
    """Calculate synergy score (0-100) and grade label/emoji."""
    weights = _SYNERGY_WEIGHTS.get(stat_type, _SYNERGY_WEIGHTS["balanced"])
    iv_keys = ["hp", "atk", "def", "spa", "spdef", "spd"]
    iv_map = {"hp": "iv_hp", "atk": "iv_atk", "def": "iv_def",
              "spa": "iv_spa", "spdef": "iv_spdef", "spd": "iv_spd"}

    weighted_sum = sum(weights[k] * (ivs.get(iv_map[k]) or 0) for k in iv_keys)
    max_sum = sum(weights[k] * 31 for k in iv_keys)
    score = int(weighted_sum / max_sum * 100) if max_sum > 0 else 0

    label = "아쉬움"
    emoji = "💤"
    for threshold in sorted(_SYNERGY_LABELS.keys(), reverse=True):
        if score >= threshold:
            label = _SYNERGY_LABELS[threshold]
            emoji = _SYNERGY_EMOJI[threshold]
            break
    return score, label, emoji


async def _build_pokemon_data(rows, battle_stats: dict | None = None) -> list[dict]:
    """Build full pokemon data list with stats + synergy from DB rows.
    battle_stats: optional {pokemon_id: {uses, win_rate, avg_damage, ...}} from _get_user_battle_stats().
    """
    result = []
    for r in rows:
        pid = r["pokemon_id"]
        rarity = r["rarity"]
        stat_type = r["stat_type"]
        friendship = r["friendship"]
        base_raw = get_normalized_base_stats(pid)
        evo_stage = 3 if base_raw else EVO_STAGE_MAP.get(pid, 3)

        ivs = {
            "iv_hp": r.get("iv_hp"), "iv_atk": r.get("iv_atk"),
            "iv_def": r.get("iv_def"), "iv_spa": r.get("iv_spa"),
            "iv_spdef": r.get("iv_spdef"), "iv_spd": r.get("iv_spd"),
        }

        base_kw = base_raw if base_raw else {}

        # 어드바이저 기준 강화: 이로치 7강, 일반 5강
        advisor_friendship = 7 if r.get("is_shiny", 0) else 5

        # Stats WITH IV (어드바이저 기준 강화)
        real_stats = calc_battle_stats(
            rarity, stat_type, advisor_friendship, evo_stage,
            ivs["iv_hp"], ivs["iv_atk"], ivs["iv_def"],
            ivs["iv_spa"], ivs["iv_spdef"], ivs["iv_spd"],
            **base_kw,
        )
        # Stats WITHOUT IV (IV_mult=1.0)
        base_stats = calc_battle_stats(
            rarity, stat_type, advisor_friendship, evo_stage,
            None, None, None, None, None, None,
            **base_kw,
        )

        real_power = calc_power(real_stats)
        base_power = calc_power(base_stats)
        iv_bonus = real_power - base_power

        iv_sum = iv_total(ivs["iv_hp"], ivs["iv_atk"], ivs["iv_def"],
                          ivs["iv_spa"], ivs["iv_spdef"], ivs["iv_spd"])
        iv_grade, _ = config.get_iv_grade(iv_sum)

        synergy_score, synergy_label, synergy_emoji = _calc_synergy(stat_type, ivs)

        # Type info from base stats
        bs_entry = POKEMON_BASE_STATS.get(pid)
        types = bs_entry[6] if bs_entry else [r.get("pokemon_type", "normal")]

        entry = {
            "id": r["id"],  # instance id
            "pokemon_id": pid,
            "name_ko": r["name_ko"],
            "emoji": r["emoji"],
            "rarity": rarity,
            "pokemon_type": types[0] if types else "normal",
            "type2": types[1] if len(types) > 1 else None,
            "stat_type": stat_type,
            "friendship": friendship,
            "is_shiny": bool(r.get("is_shiny", 0)),
            "is_favorite": bool(r.get("is_favorite", 0)),
            "evo_stage": evo_stage,
            "ivs": {k.replace("iv_", ""): (v if v is not None else 0) for k, v in ivs.items()},
            "stats": base_stats,
            "real_stats": real_stats,
            "power": base_power,
            "real_power": real_power,
            "iv_bonus": iv_bonus,
            "iv_total": iv_sum,
            "iv_grade": iv_grade,
            "synergy_score": synergy_score,
            "synergy_label": synergy_label,
            "synergy_emoji": synergy_emoji,
            "team_num": r.get("team_num"),
            "team_slot": r.get("team_slot"),
        }
        # Attach battle stats if available
        if battle_stats:
            bs = battle_stats.get(pid)
            if bs:
                entry["battle_uses"] = int(bs["uses"])
                entry["battle_win_rate"] = float(bs["win_rate"])
                entry["battle_avg_damage"] = int(bs["avg_damage"])
                entry["battle_avg_kills"] = float(bs["avg_kills"])
        result.append(entry)

    return result


async def api_my_pokemon(request):
    """Return all pokemon for the logged-in user with full stat data."""
    from dashboard.server import _get_session, pg_json_response
    sess = await _get_session(request)
    if not sess:
        return web.json_response({"error": "Unauthorized"}, status=401)

    pool = await queries.get_db()
    rows = await pool.fetch("""
        SELECT up.id, up.pokemon_id, up.friendship, up.is_shiny, up.is_favorite,
               up.iv_hp, up.iv_atk, up.iv_def, up.iv_spa, up.iv_spdef, up.iv_spd,
               pm.name_ko, pm.emoji, pm.rarity, pm.pokemon_type, pm.stat_type,
               pm.evolves_to,
               bt.team_number AS team_num, bt.slot AS team_slot
        FROM user_pokemon up
        JOIN pokemon_master pm ON up.pokemon_id = pm.id
        LEFT JOIN battle_teams bt ON bt.pokemon_instance_id = up.id
        WHERE up.user_id = $1 AND up.is_active = 1
        ORDER BY up.id DESC
    """, sess["user_id"])

    data = await _build_pokemon_data(rows)
    return pg_json_response(data)


async def api_my_summary(request):
    """Return summary stats for the logged-in user."""
    from dashboard.server import _get_session, pg_json_response
    sess = await _get_session(request)
    if not sess:
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        pool = await queries.get_db()
        uid = sess["user_id"]

        row, battle_row = await asyncio.gather(
            pool.fetchrow("""
                SELECT COUNT(*) as total,
                       COUNT(CASE WHEN is_shiny = 1 THEN 1 END) as shiny_count,
                       COUNT(DISTINCT pokemon_id) as dex_count
                FROM user_pokemon WHERE user_id = $1 AND is_active = 1
            """, uid),
            pool.fetchrow("""
                SELECT battle_points, battle_wins, battle_losses, best_streak
                FROM users WHERE user_id = $1
            """, uid),
        )

        result = {
            "total_pokemon": row["total"],
            "shiny_count": row["shiny_count"],
            "dex_count": row["dex_count"],
            "battle_points": battle_row["battle_points"] if battle_row else 0,
            "battle_wins": battle_row["battle_wins"] if battle_row else 0,
            "battle_losses": battle_row["battle_losses"] if battle_row else 0,
            "best_streak": battle_row["best_streak"] if battle_row else 0,
        }

        # --- 랭크 정보 (현재 시즌 + MMR) ---
        import config as cfg
        try:
            season = await pool.fetchrow(
                "SELECT season_id FROM seasons WHERE NOW() BETWEEN starts_at AND ends_at ORDER BY id DESC LIMIT 1"
            )
            if season:
                sr = await pool.fetchrow("""
                    SELECT rp, tier, ranked_wins, ranked_losses,
                           ranked_streak, best_ranked_streak, peak_rp, peak_tier,
                           placement_done, placement_games
                    FROM season_records
                    WHERE user_id = $1 AND season_id = $2
                """, uid, season["season_id"])
                mmr_row = await pool.fetchrow(
                    "SELECT mmr, peak_mmr, games_played FROM user_mmr WHERE user_id = $1", uid
                )
                if sr:
                    pd = sr.get("placement_done", True)
                    rp = sr["rp"] or 0
                    div = cfg.get_division_info(rp)
                    result["ranked"] = {
                        "rp": rp,
                        "tier": div[0],
                        "division": div[1],
                        "division_rp": div[2],
                        "division_display": cfg.tier_division_display(
                            div[0], div[1], div[2],
                            placement_done=pd, total_rp=rp),
                        "ranked_wins": sr["ranked_wins"] or 0,
                        "ranked_losses": sr["ranked_losses"] or 0,
                        "ranked_streak": sr["ranked_streak"] or 0,
                        "best_ranked_streak": sr["best_ranked_streak"] or 0,
                        "peak_rp": sr["peak_rp"] or 0,
                        "peak_tier": sr["peak_tier"] or "unranked",
                        "placement_done": pd,
                        "placement_games": sr.get("placement_games", 0),
                        "mmr": mmr_row["mmr"] if mmr_row else 1200,
                        "peak_mmr": mmr_row["peak_mmr"] if mmr_row else 1200,
                        "mmr_games": mmr_row["games_played"] if mmr_row else 0,
                    }
                    # peak tier display
                    peak_div = cfg.get_division_info(sr["peak_rp"] or 0)
                    result["ranked"]["peak_display"] = cfg.tier_division_display(
                        peak_div[0], peak_div[1], peak_div[2],
                        placement_done=True, total_rp=sr["peak_rp"] or 0)
        except Exception:
            pass  # 랭크 정보 없으면 무시

        return pg_json_response(result)
    except InterfaceError:
        return web.json_response({"error": "서버 재시작 중입니다"}, status=503)


async def api_my_pokedex(request):
    """Return user's pokedex: all 493 pokemon with caught status."""
    from dashboard.server import _get_session, pg_json_response
    sess = await _get_session(request)
    if not sess:
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        pool = await queries.get_db()
        uid = sess["user_id"]

        # All pokemon master data + user's caught pokemon in parallel
        all_pm, caught_rows = await asyncio.gather(
            pool.fetch("""
                SELECT id, name_ko, name_en, emoji, rarity, pokemon_type, catch_rate,
                       evolves_from, evolves_to, evolution_method
                FROM pokemon_master ORDER BY id
            """),
            pool.fetch("""
                SELECT pokemon_id, method, first_caught_at
                FROM pokedex WHERE user_id = $1
            """, uid),
        )
        caught_map = {r["pokemon_id"]: {"method": r["method"]} for r in caught_rows}

        # Get type2 info from base stats + evo stage + TMI
        from models.pokemon_base_stats import POKEMON_BASE_STATS
        from utils.battle_calc import EVO_STAGE_MAP
        from handlers.dm_pokedex import POKEMON_TMI

        # Build a lookup for evo chains
        pm_map = {r["id"]: r for r in all_pm}
        result = []
        for pm in all_pm:
            pid = pm["id"]
            pbs = POKEMON_BASE_STATS.get(pid)
            types = pbs[-1] if pbs else [pm["pokemon_type"]]
            type2 = types[1] if len(types) > 1 else None
            caught = caught_map.get(pid)

            # Build evolution chain
            evo_chain = []
            # Walk backwards to find base
            base_id = pid
            while pm_map.get(base_id, {}).get("evolves_from"):
                base_id = pm_map[base_id]["evolves_from"]
                if base_id == pid:
                    break  # Prevent infinite loop
            # Walk forwards from base
            cur = base_id
            while cur:
                p = pm_map.get(cur)
                if not p:
                    break
                evo_chain.append(p["name_ko"])
                cur = p["evolves_to"]
                if cur == base_id:
                    break

            evo_stage = EVO_STAGE_MAP.get(pid, 3)
            stage_labels = {1: "기본", 2: "1진화", 3: "최종"}
            stage = stage_labels.get(evo_stage, "최종")
            if evo_stage == 3 and not pm.get("evolves_from"):
                stage = "단일"

            # Base stats (normalized to 20~180)
            bs = None
            if pbs:
                def norm(s): return round(20 + (s - 5) / (255 - 5) * (180 - 20))
                bs = {"hp": norm(pbs[0]), "atk": norm(pbs[1]), "def": norm(pbs[2]),
                      "spa": norm(pbs[3]), "spdef": norm(pbs[4]), "spd": norm(pbs[5])}

            result.append({
                "id": pid,
                "name_ko": pm["name_ko"],
                "name_en": pm["name_en"],
                "emoji": pm["emoji"],
                "rarity": pm["rarity"],
                "type1": pm["pokemon_type"],
                "type2": type2,
                "catch_rate": float(pm["catch_rate"]),
                "caught": caught is not None,
                "method": caught["method"] if caught else None,
                "evo_chain": " → ".join(evo_chain) if len(evo_chain) > 1 else None,
                "stage": stage,
                "stats": bs,
                "tmi": POKEMON_TMI.get(pid, ""),
            })

        return pg_json_response(result)
    except InterfaceError:
        return web.json_response({"error": "서버 재시작 중입니다"}, status=503)


async def api_my_camp(request):
    """GET /api/my/camp — user's camp status: home camp, fragments, crystals, placements."""
    from dashboard.server import _get_session, pg_json_response
    sess = await _get_session(request)
    if not sess:
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        pool = await queries.get_db()
        uid = sess["user_id"]

        # 거점 캠프 정보
        settings_row = await pool.fetchrow(
            """SELECT home_chat_id, home_camp_set_at,
                      COALESCE(camp_notify, TRUE) AS camp_notify
               FROM camp_user_settings WHERE user_id = $1""", uid)

        home_camp = None
        if settings_row and settings_row["home_chat_id"]:
            hc = settings_row["home_chat_id"]
            camp_row, chat_row = await asyncio.gather(
                pool.fetchrow("SELECT level, xp FROM camps WHERE chat_id = $1", hc),
                pool.fetchrow("SELECT chat_title, invite_link FROM chat_rooms WHERE chat_id = $1", hc),
            )
            if camp_row:
                home_camp = {
                    "chat_id": hc,
                    "chat_title": chat_row["chat_title"] if chat_row else None,
                    "invite_link": chat_row["invite_link"] if chat_row else None,
                    "level": camp_row["level"],
                    "xp": camp_row["xp"],
                    "set_at": settings_row["home_camp_set_at"].isoformat() if settings_row["home_camp_set_at"] else None,
                    "notify": settings_row["camp_notify"],
                }

        # 조각
        frag_rows = await pool.fetch(
            "SELECT field_type, amount FROM camp_fragments WHERE user_id = $1 AND amount > 0", uid)
        fragments = {r["field_type"]: r["amount"] for r in frag_rows}

        # 결정
        crystal_row = await pool.fetchrow(
            "SELECT COALESCE(crystal, 0) AS crystal, COALESCE(rainbow, 0) AS rainbow FROM camp_crystals WHERE user_id = $1", uid)
        crystals = {"crystal": crystal_row["crystal"] if crystal_row else 0,
                    "rainbow": crystal_row["rainbow"] if crystal_row else 0}

        # 배치 현황
        placement_rows = await pool.fetch("""
            SELECT cp.field_id, cf.field_type, cp.pokemon_id, cp.score, cp.placed_at,
                   pm.name_ko, pm.rarity, up.is_shiny,
                   cr.chat_title
            FROM camp_placements cp
            JOIN camp_fields cf ON cf.id = cp.field_id
            JOIN user_pokemon up ON up.id = cp.instance_id
            JOIN pokemon_master pm ON pm.id = cp.pokemon_id
            LEFT JOIN chat_rooms cr ON cr.chat_id = cp.chat_id
            WHERE cp.user_id = $1
            ORDER BY cp.placed_at
        """, uid)
        placements = [{
            "field_type": r["field_type"],
            "pokemon_id": r["pokemon_id"],
            "name_ko": r["name_ko"],
            "rarity": r["rarity"],
            "score": r["score"],
            "is_shiny": bool(r["is_shiny"]),
            "chat_title": r["chat_title"],
        } for r in placement_rows]

        return pg_json_response({
            "home_camp": home_camp,
            "fragments": fragments,
            "crystals": crystals,
            "placements": placements,
        })
    except InterfaceError:
        return web.json_response({"error": "서버 재시작 중입니다"}, status=503)


async def api_camp_list(request):
    """GET /api/camps — public list of active camps."""
    from dashboard.server import pg_json_response
    try:
        pool = await queries.get_db()
        rows = await pool.fetch("""
            SELECT c.chat_id, c.level, c.xp, cr.chat_title, cr.member_count, cr.invite_link,
                   (SELECT COUNT(*) FROM camp_placements cp WHERE cp.chat_id = c.chat_id) AS total_placements,
                   (SELECT COUNT(DISTINCT cp.user_id) FROM camp_placements cp WHERE cp.chat_id = c.chat_id) AS active_users
            FROM camps c
            JOIN chat_rooms cr ON cr.chat_id = c.chat_id
            WHERE cr.is_active = TRUE
            ORDER BY c.level DESC, c.xp DESC
        """)
        camps = [{
            "chat_title": r["chat_title"],
            "level": r["level"],
            "xp": r["xp"],
            "member_count": r["member_count"] or 0,
            "invite_link": r["invite_link"],
            "total_placements": r["total_placements"],
            "active_users": r["active_users"],
        } for r in rows]
        return pg_json_response({"camps": camps})
    except InterfaceError:
        return web.json_response({"error": "서버 재시작 중입니다"}, status=503)


async def api_my_fusion(request):
    """POST /api/my/fusion — fuse two same-species Pokemon."""
    from dashboard.server import _get_session, pg_json_response
    from dashboard.api_admin import _admin_send_dm
    sess = await _get_session(request)
    if not sess:
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        body = await request.json()
        id_a = int(body["instance_id_a"])
        id_b = int(body["instance_id_b"])
    except (KeyError, ValueError, TypeError):
        return web.json_response({"error": "instance_id_a, instance_id_b 필요"}, status=400)

    from services.fusion_service import execute_fusion
    try:
        success, msg, result = await execute_fusion(sess["user_id"], id_a, id_b)
    except Exception as e:
        logger.exception("Fusion error: user=%s a=%s b=%s", sess["user_id"], id_a, id_b)
        return web.json_response({"error": "서버 오류가 발생했습니다."}, status=500)

    if not success:
        return web.json_response({"error": msg}, status=400)

    # Build result data matching api_my_pokemon format
    if result:
        iv_t = sum(result.get(f"iv_{s}", 0) or 0 for s in ("hp", "atk", "def", "spa", "spdef", "spd"))
        grade, _ = config.get_iv_grade(iv_t)
        res_data = {
            "id": result["id"],
            "pokemon_id": result["pokemon_id"],
            "name_ko": result.get("name_ko", ""),
            "emoji": result.get("emoji", ""),
            "rarity": result.get("rarity", ""),
            "is_shiny": bool(result.get("is_shiny")),
            "iv_hp": result.get("iv_hp", 0),
            "iv_atk": result.get("iv_atk", 0),
            "iv_def": result.get("iv_def", 0),
            "iv_spa": result.get("iv_spa", 0),
            "iv_spdef": result.get("iv_spdef", 0),
            "iv_spd": result.get("iv_spd", 0),
            "iv_total": iv_t,
            "iv_grade": grade,
            "friendship": result.get("friendship", 0),
        }

        # Send DM notification with custom emoji
        rarity = result.get("rarity", "")
        eid = config.RARITY_CUSTOM_EMOJI.get(rarity, "")
        fallback = config.RARITY_EMOJI.get(rarity, "⚪")
        badge = f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>' if eid else fallback
        name = result.get("name_ko", "???")
        shiny = " ⭐이로치" if result.get("is_shiny") else ""
        dm_text = (
            f"🔀 <b>합성 완료!</b> (대시보드)\n\n"
            f"{badge} <b>{name}</b>{shiny}\n"
            f"등급: [{grade}] (IV합계: {iv_t})\n\n"
            f"HP: {result.get('iv_hp', 0)}  ATK: {result.get('iv_atk', 0)}  DEF: {result.get('iv_def', 0)}\n"
            f"SpA: {result.get('iv_spa', 0)}  SpD: {result.get('iv_spdef', 0)}  SPD: {result.get('iv_spd', 0)}"
        )
        await _admin_send_dm(sess["user_id"], dm_text)
    else:
        res_data = None

    return web.json_response({"success": True, "message": msg, "result": res_data})


def setup_routes(app):
    """Register My-data routes."""
    app.router.add_get("/api/my/pokemon", api_my_pokemon)
    app.router.add_get("/api/my/pokedex", api_my_pokedex)
    app.router.add_get("/api/my/summary", api_my_summary)
    app.router.add_post("/api/my/fusion", api_my_fusion)
    app.router.add_get("/api/my/camp", api_my_camp)
    app.router.add_get("/api/camps", api_camp_list)
