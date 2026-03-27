"""Tournament match execution: run individual matches + GIF round building."""

import asyncio
import logging

from telegram.error import RetryAfter

from services.battle_service import _prepare_combatant, _resolve_battle, _hp_bar
from services.tournament_render import (
    _safe_send, _safe_send_photo, _switch_line, _extract_mvp,
    _get_mvp_name, _winner_speech,
)
from utils.helpers import icon_emoji, rarity_badge, shiny_emoji
from utils.card_generator import generate_lineup_card
from database import battle_queries as bq

logger = logging.getLogger(__name__)


# ── GIF Round Builder ──────────────────────────────────────────

def _make_round_comment(rd: dict, r_idx: int, total_rounds: int,
                        p1_score: int, p2_score: int,
                        p1_name: str, p2_name: str) -> str:
    """배틀 상황 기반 멘트. 트레이너 본인이 한마디 하는 느낌.

    Returns: "이름: 멘트" 형식 문자열.
    """
    import random as _rnd

    winner_poke = rd["p1_poke"] if rd["winner"] == "p1" else rd["p2_poke"]
    loser_poke = rd["p2_poke"] if rd["winner"] == "p1" else rd["p1_poke"]
    winner_name = p1_name if rd["winner"] == "p1" else p2_name
    loser_name = p2_name if rd["winner"] == "p1" else p1_name
    type_adv = rd.get("type_advantage", 1.0)
    crit = rd.get("crit", False)
    dmg_dealt = rd.get("damage_dealt", 0)
    dmg_taken = rd.get("damage_taken", 0)
    turn_count = rd.get("turn_count", 3)

    # (speaker: "winner"/"loser", 멘트)
    pool: list[tuple[str, str]] = []

    # 상성
    if type_adv >= 2.0:
        pool += [
            ("loser", f"{loser_poke} 상성이 안 좋았어"),
            ("loser", f"상성 매치가 너무 안 좋다"),
            ("winner", f"{winner_poke}으로 잡으려고 했어"),
        ]
    elif type_adv <= 0.5:
        pool += [
            ("winner", f"상성 안 좋은 거 알았는데 믿었어"),
            ("winner", f"{winner_poke}가 해줄 줄 알았어"),
            ("loser", f"상성 좋았는데 못 잡았네"),
        ]

    # 크리티컬
    if crit:
        pool += [
            ("winner", f"크리티컬 터져줬다"),
            ("loser", f"크리티컬 안 터졌으면 잡았는데"),
            ("winner", f"운이 좋았어"),
        ]

    # 원턴
    if turn_count <= 1:
        pool += [
            ("winner", f"{winner_poke} 화력 믿고 갔다"),
            ("loser", f"한 턴도 못 버텼네"),
            ("winner", f"바로 정리됐다"),
        ]
    elif turn_count >= 5:
        pool += [
            ("winner", f"오래 걸렸다"),
            ("loser", f"버텼는데 결국 졌다"),
            ("winner", f"끝까지 긴장했다"),
        ]

    # 데미지 차이
    if dmg_dealt > 0 and dmg_taken > 0:
        ratio = dmg_dealt / max(dmg_taken, 1)
        if ratio >= 3.0:
            pool += [
                ("winner", f"무난했다"),
                ("loser", f"데미지를 못 넣었다"),
            ]
        elif ratio <= 0.5:
            pool += [
                ("winner", f"솔직히 위험했다"),
                ("loser", f"거의 잡을 뻔했는데"),
                ("winner", f"겨우 이겼다"),
            ]

    # 스코어
    if p1_score == 0 and p2_score == 0:
        pool += [
            ("winner", f"좋은 출발이다"),
            ("loser", f"아직 시작이야"),
        ]
    elif abs(p1_score - p2_score) >= 3:
        leading = "winner" if (
            (p1_score > p2_score and rd["winner"] == "p1") or
            (p2_score > p1_score and rd["winner"] == "p2")
        ) else "loser"
        if leading == "winner":
            pool += [("winner", "이대로 가면 된다")]
        else:
            pool += [("loser", "아직 포기 안 했어")]
    elif r_idx == total_rounds - 1:
        pool += [
            ("winner", f"마지막이다 집중하자"),
            ("loser", f"여기서 지면 끝이다"),
        ]

    # 이로치
    if rd.get("p1_shiny") or rd.get("p2_shiny"):
        shiny_poke = rd["p1_poke"] if rd.get("p1_shiny") else rd["p2_poke"]
        is_winner_shiny = (rd.get("p1_shiny") and rd["winner"] == "p1") or \
                          (rd.get("p2_shiny") and rd["winner"] == "p2")
        if is_winner_shiny:
            pool += [("winner", f"이로치 {shiny_poke} 믿고 있었어")]
        else:
            pool += [("loser", f"이로치였는데 아쉽다")]

    if not pool:
        pool = [
            ("winner", "좋았어"),
            ("loser", "다음에 잡는다"),
        ]

    side, comment = _rnd.choice(pool)
    name = winner_name if side == "winner" else loser_name
    return f"{name}: {comment}"


def _build_gif_rounds(turn_data: list[dict], p1_data: dict, p2_data: dict) -> list[dict]:
    """turn_data → make_round_gif용 rounds 리스트 변환."""
    rounds = []
    current_matchup = None
    current_turns = []

    for td in turn_data:
        if td["type"] == "matchup":
            if current_matchup and current_turns:
                rounds.append(_matchup_to_round(current_matchup, current_turns, p1_data, p2_data))
            current_matchup = td
            current_turns = []
        elif td["type"] == "turn":
            current_turns.append(td)
        elif td["type"] == "ko":
            current_turns.append(td)

    if current_matchup and current_turns:
        rounds.append(_matchup_to_round(current_matchup, current_turns, p1_data, p2_data))

    # 상황기반 멘트 생성
    p1_name = p1_data["name"]
    p2_name = p2_data["name"]
    p1_score, p2_score = 0, 0
    total = len(rounds)
    for i, rd in enumerate(rounds):
        rd["comment"] = _make_round_comment(
            rd, i, total, p1_score, p2_score, p1_name, p2_name,
        )
        if rd["winner"] == "p1":
            p1_score += 1
        else:
            p2_score += 1

    return rounds


def _matchup_to_round(matchup: dict, turns: list[dict], p1_data: dict, p2_data: dict) -> dict:
    """단일 매치업(1v1)의 turn_data → GIF round dict 변환."""
    actual_turns = [t for t in turns if t["type"] == "turn"]
    total_c_dmg = sum(t.get("c_dmg", 0) for t in actual_turns)
    total_d_dmg = sum(t.get("d_dmg", 0) for t in actual_turns)
    has_crit = any(t.get("c_crit") or t.get("d_crit") for t in actual_turns)

    # 상성 배율 (첫 턴 기준)
    type_adv = 1.0
    if actual_turns:
        type_adv = actual_turns[0].get("c_type_mult", 1.0)

    # KO 판정
    ko_side = None
    for t in turns:
        if t["type"] == "ko":
            ko_side = t["side"]
            break

    if ko_side == "defender":
        winner = "p1"
    elif ko_side == "challenger":
        winner = "p2"
    else:
        winner = "p1"

    return {
        "p1_id": matchup.get("c_pokemon_id", 1),
        "p1_poke": matchup["c_name"],
        "p1_rarity": matchup.get("c_rarity", "common"),
        "p1_shiny": matchup.get("c_shiny", False),
        "p2_id": matchup.get("d_pokemon_id", 1),
        "p2_poke": matchup["d_name"],
        "p2_rarity": matchup.get("d_rarity", "common"),
        "p2_shiny": matchup.get("d_shiny", False),
        "winner": winner,
        "damage_dealt": total_c_dmg,
        "damage_taken": total_d_dmg,
        "crit": has_crit,
        "type_advantage": type_adv,
        "turn_count": len(actual_turns),
    }


# ── Match Execution ─────────────────────────────────────────────

async def _run_match(
    context, chat_id: int,
    p1_id: int, p1_data: dict,
    p2_id: int, p2_data: dict,
    is_final: bool = False,
    is_semi: bool = False,
    is_quarter: bool = False,
    match_label: str = "",
) -> tuple[int, dict]:
    """Run a single match between two players.

    Display modes:
    - is_quarter: log 2 lines at a time (1s delay)
    - is_semi: log 1 line at a time (1.5s delay)
    - is_final: rich turn-by-turn with HP bars (2s delay)

    Returns (winner_user_id, winner_data).
    """
    SKULL = icon_emoji("skull")
    # Team labels: challenger = red badge, defender = rare(blue) badge
    C = rarity_badge("red")
    D = rarity_badge("rare")

    # Prepare combatants
    partner1 = await bq.get_partner(p1_id)
    partner1_id = partner1["instance_id"] if partner1 else None
    team1 = [
        _prepare_combatant(p, is_partner=(p.get("pokemon_instance_id") == partner1_id))
        for p in p1_data["team"]
    ]

    partner2 = await bq.get_partner(p2_id)
    partner2_id = partner2["instance_id"] if partner2 else None
    team2 = [
        _prepare_combatant(p, is_partner=(p.get("pokemon_instance_id") == partner2_id))
        for p in p2_data["team"]
    ]

    # Resolve battle
    result = _resolve_battle(team1, team2)

    winner_side = result["winner"]
    if winner_side == "challenger":
        winner_id, winner_data = p1_id, p1_data
        remaining = result["challenger_remaining"]
    else:
        winner_id, winner_data = p2_id, p2_data
        remaining = result["defender_remaining"]

    # MVP line
    mvp_line = _extract_mvp(result["turn_data"], winner_side)

    # Helper: team marker for KO/next based on side
    def _mark(side):
        return C if side == "challenger" else D

    # Helper: build matchup sections from turn_data (with global offsets)
    def _build_sections(turn_data):
        sections, cur, offsets, cur_off = [], [], [], 0
        for i, td in enumerate(turn_data):
            if td["type"] == "matchup" and cur:
                sections.append(cur)
                offsets.append(cur_off)
                cur = [td]
                cur_off = i
            else:
                if not cur:
                    cur_off = i
                cur.append(td)
        if cur:
            sections.append(cur)
            offsets.append(cur_off)
        return sections, offsets

    # Helper: format a section into lines — with HP bars
    # dramatic_mode: "" (none), "serious" (8강), "full" (4강/결승)
    def _format_section(section, dramatic_mode="", offset=0):
        lines = []
        c_trainer = p1_data['name']
        d_trainer = p2_data['name']
        for j, td in enumerate(section):
            global_idx = offset + j
            if td["type"] == "matchup":
                c_sh = f"{shiny_emoji()}" if td.get("c_shiny") else ""
                d_sh = f"{shiny_emoji()}" if td.get("d_shiny") else ""
                lines.append(f"<b>⚔ {C}{td['c_tb']}{c_sh}{td['c_name']}({td['c_idx']+1}/{td['c_total']}) vs {D}{td['d_tb']}{d_sh}{td['d_name']}({td['d_idx']+1}/{td['d_total']})</b>")
            elif td["type"] == "turn":
                if td["first_is_challenger"]:
                    first_mark, second_mark = C, D
                    first_name, first_dmg, first_crit, first_eff = td["c_name"], td["c_dmg"], td["c_crit"], td["c_eff"]
                    second_name, second_dmg, second_crit, second_eff = td["d_name"], td["d_dmg"], td["d_crit"], td["d_eff"]
                    first_target_hp, first_target_max = td["d_hp"], td["d_max_hp"]
                    second_target_hp, second_target_max = td["c_hp"], td["c_max_hp"]
                    first_target_mark, second_target_mark = D, C
                    first_target_name, second_target_name = td["d_name"], td["c_name"]
                else:
                    first_mark, second_mark = D, C
                    first_name, first_dmg, first_crit, first_eff = td["d_name"], td["d_dmg"], td["d_crit"], td["d_eff"]
                    second_name, second_dmg, second_crit, second_eff = td["c_name"], td["c_dmg"], td["c_crit"], td["c_eff"]
                    first_target_hp, first_target_max = td["c_hp"], td["c_max_hp"]
                    second_target_hp, second_target_max = td["d_hp"], td["d_max_hp"]
                    first_target_mark, second_target_mark = C, D
                    first_target_name, second_target_name = td["c_name"], td["d_name"]

                crit1 = " 크리티컬!" if first_crit else ""
                skill1 = f" {first_eff}!" if first_eff else " 공격!"
                bar1 = _hp_bar(first_target_hp, first_target_max)
                lines.append(f"{td['turn_num']}턴 ─ {first_mark}{first_name}{skill1}{crit1}")
                lines.append(f"  {first_target_mark}{first_target_name} {bar1} {first_target_hp}/{first_target_max} (-{first_dmg})")

                if second_dmg > 0:
                    crit2 = " 크리티컬!" if second_crit else ""
                    skill2 = f" {second_eff}!" if second_eff else " 반격!"
                    bar2 = _hp_bar(second_target_hp, second_target_max)
                    lines.append(f"{second_mark}{second_name}{skill2}{crit2}")
                    lines.append(f"  {second_target_mark}{second_target_name} {bar2} {second_target_hp}/{second_target_max} (-{second_dmg})")

            elif td["type"] == "ko":
                m = _mark(td["side"])
                trainer = c_trainer if td["side"] == "challenger" else d_trainer
                if td["next_name"]:
                    is_last = (global_idx == _last_switch_idx[td["side"]])
                    dm = dramatic_mode if is_last else ""
                    lines.append(f"{SKULL} {m}{td['dead_name']} 쓰러짐!")
                    lines.append(_switch_line(trainer, td['dead_name'], td['next_name'], td.get('next_rarity', ''), dramatic=dm))
                else:
                    lines.append(f"{SKULL} {m}{td['dead_name']} 쓰러짐!")
        return lines

    # Pre-scan: find last switch-in index for each side (dramatic entrance)
    _last_switch_idx = {"challenger": -1, "defender": -1}
    for _i, _td in enumerate(result["turn_data"]):
        if _td["type"] == "ko" and _td["next_name"]:
            _last_switch_idx[_td["side"]] = _i

    if is_final:
        # ── Finals: 턴별 텍스트+이미지 + 상황기반 멘트 ──
        p1_name = p1_data['name']
        p2_name = p2_data['name']

        # 라인업 카드
        try:
            lineup_data_1 = [
                {"pokemon_id": m["pokemon_id"], "name": m["name"],
                 "rarity": m["rarity"], "is_shiny": m.get("is_shiny", False)}
                for m in team1
            ]
            lineup_data_2 = [
                {"pokemon_id": m["pokemon_id"], "name": m["name"],
                 "rarity": m["rarity"], "is_shiny": m.get("is_shiny", False)}
                for m in team2
            ]
            loop = asyncio.get_event_loop()
            lineup_buf = await loop.run_in_executor(
                None, generate_lineup_card, p1_name, lineup_data_1, p2_name, lineup_data_2
            )
            await _safe_send_photo(
                context.bot, chat_id, photo=lineup_buf,
                caption=f"🏆 결승전! — {p1_name} vs {p2_name}",
                parse_mode="HTML",
            )
        except Exception:
            logger.error("Failed to generate lineup card", exc_info=True)
            await _safe_send(context.bot, chat_id,
                text=(
                    f"🏆 결승전!\n"
                    f"{C}{p1_name} vs {D}{p2_name}\n"
                    f"━━━━━━━━━━━━━━━"
                ),
                parse_mode="HTML",
            )
        await asyncio.sleep(3)

        # ── 카운트다운 애니메이션 ──
        countdown_msg = await _safe_send(context.bot, chat_id, text="⚡ 3")
        await asyncio.sleep(1)
        if countdown_msg:
            try:
                await countdown_msg.edit_text("⚡⚡ 2")
            except Exception:
                pass
        await asyncio.sleep(1)
        if countdown_msg:
            try:
                await countdown_msg.edit_text("⚡⚡⚡ 1")
            except Exception:
                pass
        await asyncio.sleep(1)
        if countdown_msg:
            try:
                await countdown_msg.edit_text("✦═✦═✦═✦═✦═✦═✦═✦\n⚔️ FIGHT!\n✦═✦═✦═✦═✦═✦═✦═✦")
            except Exception:
                pass
        await asyncio.sleep(2)

        # 상황기반 멘트 준비 (매치업별 멘트 미리 생성)
        _comment_rounds = _build_gif_rounds(result["turn_data"], p1_data, p2_data)
        _comment_map = {}  # matchup_idx → comment
        _matchup_count = 0
        for td in result["turn_data"]:
            if td["type"] == "matchup":
                if _matchup_count < len(_comment_rounds):
                    _comment_map[_matchup_count] = _comment_rounds[_matchup_count].get("comment", "")
                _matchup_count += 1
        _current_matchup_idx = -1

        # HP 추적: 턴 시작 시점의 HP를 기록 (GIF hp_before 용)
        _running_c_hp = None  # 현재 challenger HP
        _running_d_hp = None  # 현재 defender HP
        _score_c = 0  # challenger KO 수
        _score_d = 0  # defender KO 수

        for _i, td in enumerate(result["turn_data"]):
            if td["type"] == "matchup":
                _current_matchup_idx += 1
                # 매치업 시작 시 HP 초기화
                _running_c_hp = td["c_hp"]
                _running_d_hp = td["d_hp"]

                # 매치업 시작 전 상황기반 멘트 (극적 연출)
                _comment = _comment_map.get(_current_matchup_idx, "")
                if _comment and _current_matchup_idx > 0:
                    _score_text = f"[{_score_c} - {_score_d}]"
                    _comment_msg = await _safe_send(context.bot, chat_id,
                        text=f"━══════════════════━\n🧑‍🔬 문박사: {_comment}\n  📊 현재 스코어 {_score_text}\n━══════════════════━",
                    )
                    await asyncio.sleep(2)

                await _safe_send(context.bot, chat_id,
                    text=f"⚔ {C}{td['c_tb']}{td['c_name']}({td['c_idx']+1}/{td['c_total']}) vs {D}{td['d_tb']}{td['d_name']}({td['d_idx']+1}/{td['d_total']})!",
                    parse_mode="HTML",
                )
                await asyncio.sleep(3)

            elif td["type"] == "turn":
                if td["first_is_challenger"]:
                    first_mark, second_mark = C, D
                    first_name, first_dmg, first_crit, first_eff = td["c_name"], td["c_dmg"], td["c_crit"], td["c_eff"]
                    second_name, second_dmg, second_crit, second_eff = td["d_name"], td["d_dmg"], td["d_crit"], td["d_eff"]
                    first_target_hp, first_target_max = td["d_hp"], td["d_max_hp"]
                    second_target_hp, second_target_max = td["c_hp"], td["c_max_hp"]
                    first_target_name, second_target_name = td["d_name"], td["c_name"]
                    first_target_mark, second_target_mark = D, C
                    first_pid, first_rarity, first_shiny = td.get("c_pokemon_id"), td.get("c_rarity", "common"), td.get("c_shiny", False)
                    second_pid, second_rarity, second_shiny = td.get("d_pokemon_id"), td.get("d_rarity", "common"), td.get("d_shiny", False)
                    # GIF용 HP: 첫 공격 대상 = defender
                    _gif_hp_before = (_running_d_hp or 0) / td["d_max_hp"] if td["d_max_hp"] else 1.0
                    _gif_hp_after = max(0, (_running_d_hp or 0) - first_dmg) / td["d_max_hp"] if td["d_max_hp"] else 0.0
                    _gif_atk_hp = (_running_c_hp or 0) / td["c_max_hp"] if td["c_max_hp"] else 1.0
                    _gif_def_pid = td.get("d_pokemon_id")
                    _gif_def_shiny = td.get("d_shiny", False)
                    _gif_def_rarity = td.get("d_rarity", "common")
                else:
                    first_mark, second_mark = D, C
                    first_name, first_dmg, first_crit, first_eff = td["d_name"], td["d_dmg"], td["d_crit"], td["d_eff"]
                    second_name, second_dmg, second_crit, second_eff = td["c_name"], td["c_dmg"], td["c_crit"], td["c_eff"]
                    first_target_hp, first_target_max = td["c_hp"], td["c_max_hp"]
                    second_target_hp, second_target_max = td["d_hp"], td["d_max_hp"]
                    first_target_name, second_target_name = td["c_name"], td["d_name"]
                    first_target_mark, second_target_mark = C, D
                    first_pid, first_rarity, first_shiny = td.get("d_pokemon_id"), td.get("d_rarity", "common"), td.get("d_shiny", False)
                    second_pid, second_rarity, second_shiny = td.get("c_pokemon_id"), td.get("c_rarity", "common"), td.get("c_shiny", False)
                    # GIF용 HP: 첫 공격 대상 = challenger
                    _gif_hp_before = (_running_c_hp or 0) / td["c_max_hp"] if td["c_max_hp"] else 1.0
                    _gif_hp_after = max(0, (_running_c_hp or 0) - first_dmg) / td["c_max_hp"] if td["c_max_hp"] else 0.0
                    _gif_atk_hp = (_running_d_hp or 0) / td["d_max_hp"] if td["d_max_hp"] else 1.0
                    _gif_def_pid = td.get("c_pokemon_id")
                    _gif_def_shiny = td.get("c_shiny", False)
                    _gif_def_rarity = td.get("c_rarity", "common")

                # HP 비율 클램핑
                _gif_hp_before = max(0.0, min(1.0, _gif_hp_before))
                _gif_hp_after = max(0.0, min(1.0, _gif_hp_after))
                _gif_atk_hp = max(0.0, min(1.0, _gif_atk_hp))

                # First attack — Canvas GIF 연출
                crit_label = " 크리티컬!" if first_crit else ""
                skill_label = f" {first_eff}!" if first_eff else " 공격!"
                bar = _hp_bar(first_target_hp, first_target_max)
                caption1 = f"{td['turn_num']}턴 ─ {first_name}{skill_label}{crit_label}\n  → {first_target_name} {bar} {first_target_hp}/{first_target_max} (-{first_dmg})"

                _gif_sent = False
                _is_skill = first_eff and "「" in first_eff
                _is_high_rarity = first_rarity in ("legendary", "ultra_legendary")
                if _is_skill and _is_high_rarity and first_pid:
                    # 미리 생성된 프레임 + 상대 스프라이트 합성 (Playwright 없음, ~0.3초)
                    try:
                        from utils.skill_gif import compose_skill_gif, has_skill_gif
                        if has_skill_gif(first_pid):
                            loop = asyncio.get_event_loop()
                            gif_buf = await loop.run_in_executor(
                                None, compose_skill_gif, first_pid, _gif_def_pid,
                            )
                            if gif_buf:
                                for _retry in range(3):
                                    try:
                                        await context.bot.send_animation(
                                            chat_id=chat_id, animation=gif_buf,
                                            caption=caption1, parse_mode="HTML",
                                        )
                                        _gif_sent = True
                                        break
                                    except RetryAfter as e:
                                        await asyncio.sleep(e.retry_after + 1)
                                    except Exception:
                                        break
                    except Exception:
                        logger.error("스킬 GIF 합성 실패", exc_info=True)

                    if not _gif_sent:
                        await _safe_send(context.bot, chat_id, text=caption1, parse_mode="HTML")
                    await asyncio.sleep(3)
                else:
                    await _safe_send(context.bot, chat_id, text=caption1, parse_mode="HTML")
                    await asyncio.sleep(3)

                # Counter attack (텍스트로 이어감)
                if second_dmg > 0:
                    crit2_label = " 크리티컬!" if second_crit else ""
                    skill2_label = f" {second_eff}!" if second_eff else " 반격!"
                    bar2 = _hp_bar(second_target_hp, second_target_max)
                    caption2 = f"{second_name}{skill2_label}{crit2_label}\n  → {second_target_name} {bar2} {second_target_hp}/{second_target_max} (-{second_dmg})"
                    await _safe_send(context.bot, chat_id, text=caption2, parse_mode="HTML")
                    await asyncio.sleep(2)

                # 턴 끝: running HP 갱신 (다음 턴의 hp_before 용)
                _running_c_hp = max(0, td["c_hp"])
                _running_d_hp = max(0, td["d_hp"])

            elif td["type"] == "ko":
                # 스코어 업데이트 (GIF round_text 용)
                if td["side"] == "challenger":
                    _score_d += 1  # defender가 challenger 포켓몬 KO
                else:
                    _score_c += 1  # challenger가 defender 포켓몬 KO
                m = _mark(td["side"])
                trainer = p1_name if td["side"] == "challenger" else p2_name
                if td["next_name"]:
                    dm = "full" if (_i == _last_switch_idx[td["side"]]) else ""
                    switch = _switch_line(trainer, td['dead_name'], td['next_name'], td.get('next_rarity', ''), dramatic=dm)
                    text = f"{SKULL} {m}{td['dead_name']} 쓰러짐!\n{switch}"
                else:
                    text = f"{SKULL} {m}{td['dead_name']} 쓰러짐!"
                await _safe_send(context.bot, chat_id, text=text, parse_mode="HTML")
                await asyncio.sleep(3)

        # 마지막 라운드 멘트 (KO 후)
        if _comment_rounds:
            _last_comment = _comment_rounds[-1].get("comment", "")
            if _last_comment:
                await _safe_send(context.bot, chat_id, text=f"💬 {_last_comment}")
                await asyncio.sleep(1)

        # ── 우승 확정 축하 애니메이션 ──
        import random as _rng
        _mc_final = [
            "이건... 역대급이었다!!!",
            "소름이 돋는 결승이었습니다!!!",
            "전설의 배틀! 역사에 남을 경기!!!",
            "문박사도 이런 결승은 처음입니다!!!",
            "관중들이 일어났습니다!!!",
        ]
        border = "✦═✦═✦═✦═✦═✦═✦═✦"
        winner_name = winner_data['name']

        # 드라마틱 멈춤
        drama_msg = await _safe_send(context.bot, chat_id, text="🧑‍🔬 문박사: 승부가... 갈립니다...!!!")
        await asyncio.sleep(2)
        if drama_msg:
            try:
                await drama_msg.edit_text("🧑‍🔬 문박사: ...")
            except Exception:
                pass
        await asyncio.sleep(1.5)
        if drama_msg:
            try:
                await drama_msg.edit_text(
                    f"{border}\n\n"
                    f"🏆 <b>{winner_name} 우승!!!</b>\n"
                    f"🎊 남은 {remaining}마리\n\n"
                    f"🧑‍🔬 문박사: {_rng.choice(_mc_final)}\n\n"
                    f"{border}",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        await asyncio.sleep(1)
        # 테두리 반짝 효과
        if drama_msg:
            try:
                await drama_msg.edit_text(
                    f"✦═══════════════════✦\n\n"
                    f"🏆 <b>{winner_name} 우승!!!</b>\n"
                    f"🎊 남은 {remaining}마리\n"
                    f"{mvp_line}\n\n"
                    f"🧑‍🔬 문박사: {_rng.choice(_mc_final)}\n\n"
                    f"✦═══════════════════✦",
                    parse_mode="HTML",
                )
            except Exception:
                pass

        # 🎤 우승 인터뷰
        await asyncio.sleep(3)
        mvp_n = _get_mvp_name(result["turn_data"], winner_side)
        speech = _winner_speech(winner_data['name'], mvp_n)
        await _safe_send(context.bot, chat_id,
            text=f"🎤 <b>우승 인터뷰</b>\n\n{speech}",
            parse_mode="HTML",
        )

    elif is_semi:
        # ── Semi-finals: turn-by-turn, one message per turn (3s delay) ──
        p1_name = p1_data['name']
        p2_name = p2_data['name']
        await _safe_send(context.bot, chat_id,
            text=(
                f"⚔️ 준결승! — {C}{p1_name} vs {D}{p2_name}\n"
                f"━━━━━━━━━━━━━━━"
            ),
            parse_mode="HTML",
        )
        await asyncio.sleep(3)

        for _i, td in enumerate(result["turn_data"]):
            if td["type"] == "matchup":
                await _safe_send(context.bot, chat_id,
                    text=f"⚔ {C}{td['c_tb']}{td['c_name']}({td['c_idx']+1}/{td['c_total']}) vs {D}{td['d_tb']}{td['d_name']}({td['d_idx']+1}/{td['d_total']})!",
                    parse_mode="HTML",
                )
                await asyncio.sleep(3)

            elif td["type"] == "turn":
                lines = []
                if td["first_is_challenger"]:
                    first_mark, second_mark = C, D
                    first_name, first_dmg, first_crit, first_eff = td["c_name"], td["c_dmg"], td["c_crit"], td["c_eff"]
                    second_name, second_dmg, second_crit, second_eff = td["d_name"], td["d_dmg"], td["d_crit"], td["d_eff"]
                    first_target_hp, first_target_max = td["d_hp"], td["d_max_hp"]
                    second_target_hp, second_target_max = td["c_hp"], td["c_max_hp"]
                    first_target_name, second_target_name = td["d_name"], td["c_name"]
                    first_target_mark, second_target_mark = D, C
                else:
                    first_mark, second_mark = D, C
                    first_name, first_dmg, first_crit, first_eff = td["d_name"], td["d_dmg"], td["d_crit"], td["d_eff"]
                    second_name, second_dmg, second_crit, second_eff = td["c_name"], td["c_dmg"], td["c_crit"], td["c_eff"]
                    first_target_hp, first_target_max = td["c_hp"], td["c_max_hp"]
                    second_target_hp, second_target_max = td["d_hp"], td["d_max_hp"]
                    first_target_name, second_target_name = td["c_name"], td["d_name"]
                    first_target_mark, second_target_mark = C, D

                crit_label = " 크리티컬!" if first_crit else ""
                skill_label = f" {first_eff}!" if first_eff else " 공격!"
                bar = _hp_bar(first_target_hp, first_target_max)
                lines.append(f"{td['turn_num']}턴 ─ {first_mark}{first_name}{skill_label}{crit_label}")
                lines.append(f"  {first_target_mark}{first_target_name} {bar} {first_target_hp}/{first_target_max} (-{first_dmg})")

                if second_dmg > 0:
                    crit2_label = " 크리티컬!" if second_crit else ""
                    skill2_label = f" {second_eff}!" if second_eff else " 반격!"
                    bar2 = _hp_bar(second_target_hp, second_target_max)
                    lines.append(f"{second_mark}{second_name}{skill2_label}{crit2_label}")
                    lines.append(f"  {second_target_mark}{second_target_name} {bar2} {second_target_hp}/{second_target_max} (-{second_dmg})")

                await _safe_send(context.bot, chat_id, text="\n".join(lines), parse_mode="HTML")
                await asyncio.sleep(3)

            elif td["type"] == "ko":
                m = _mark(td["side"])
                trainer = p1_name if td["side"] == "challenger" else p2_name
                if td["next_name"]:
                    dm = "full" if (_i == _last_switch_idx[td["side"]]) else ""
                    switch = _switch_line(trainer, td['dead_name'], td['next_name'], td.get('next_rarity', ''), dramatic=dm)
                    text = f"{SKULL} {m}{td['dead_name']} 쓰러짐!\n{switch}"
                else:
                    text = f"{SKULL} {m}{td['dead_name']} 쓰러짐!"
                await _safe_send(context.bot, chat_id, text=text, parse_mode="HTML")
                await asyncio.sleep(3)

        win_text = f"→ {winner_data['name']} 승리! (남은 {remaining}마리)"
        if mvp_line:
            win_text += f"\n{mvp_line}"
        await _safe_send(context.bot, chat_id, text=win_text)

    elif is_quarter:
        # ── Quarter-finals: grouped by matchup (3s delay) ──
        await _safe_send(context.bot, chat_id,
            text=(
                f"⚔️ {C}{p1_data['name']} vs {D}{p2_data['name']}\n"
                f"━━━━━━━━━━━━━━━"
            ),
            parse_mode="HTML",
        )
        await asyncio.sleep(3)

        sections, offsets = _build_sections(result["turn_data"])
        for section, off in zip(sections, offsets):
            lines = _format_section(section, dramatic_mode="serious", offset=off)
            if lines:
                await _safe_send(context.bot, chat_id, text="\n".join(lines), parse_mode="HTML")
                await asyncio.sleep(3)

        win_text = f"→ {winner_data['name']} 승리! (남은 {remaining}마리)"
        if mvp_line:
            win_text += f"\n{mvp_line}"
        await _safe_send(context.bot, chat_id, text=win_text)

    else:
        # ── Lower rounds: one-line summary (match_label + result combined) ──
        win_text = f"{match_label}⚔️ {p1_data['name']} vs {p2_data['name']} → {winner_data['name']} 승리!"
        if mvp_line:
            win_text += f"\n{mvp_line}"
        await _safe_send(context.bot, chat_id, text=win_text, parse_mode="HTML")

    return winner_id, winner_data
