"""토너먼트 dry-run 시뮬레이션 — DB 연결 없이 핵심 로직만 테스트."""
import sys, os, random, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.battle_service import _prepare_combatant, _resolve_battle
from services.tournament_service import _generate_bracket, _render_bracket
from models.pokemon_data import ALL_POKEMON
from models.pokemon_base_stats import POKEMON_BASE_STATS
import config

# ── 가짜 팀 생성 ──
def _fake_team(n=3):
    """무작위 포켓몬 3마리로 팀 구성."""
    pool = [p for p in ALL_POKEMON if p[4] in ("common", "rare", "epic")]
    chosen = random.sample(pool, n)
    team = []
    for p in chosen:
        pid, name_ko, name_en, emoji, rarity = p[0], p[1], p[2], p[3], p[4]
        bs = POKEMON_BASE_STATS.get(pid)
        ptype = bs[-1][0] if bs else "normal"
        ivs = {f"iv_{s}": random.randint(0, 31) for s in ("hp", "atk", "def", "spa", "spdef", "spd")}
        team.append({
            "pokemon_id": pid,
            "name_ko": name_ko,
            "name": name_ko,
            "emoji": emoji,
            "rarity": rarity,
            "pokemon_type": ptype,
            "stat_type": random.choice(["atk", "def", "balanced"]),
            "friendship": random.randint(1, 5),
            "is_shiny": random.random() < 0.1,
            "iv_hp": ivs["iv_hp"], "iv_atk": ivs["iv_atk"], "iv_def": ivs["iv_def"],
            "iv_spa": ivs["iv_spa"], "iv_spdef": ivs["iv_spdef"], "iv_spd": ivs["iv_spd"],
            "pokemon_instance_id": pid * 1000 + random.randint(1, 999),
        })
    return team


def _cost_check(team):
    total = sum(config.RANKED_COST.get(p["rarity"], 0) for p in team)
    return total, total <= config.RANKED_COST_LIMIT


def simulate_match(t1, t2):
    """배틀 시뮬레이션."""
    c1 = [_prepare_combatant(p) for p in t1]
    c2 = [_prepare_combatant(p) for p in t2]
    result = _resolve_battle(c1, c2)
    return result["winner"], result


# ── 다양한 참가자 수 시뮬레이션 ──
errors = []
print("=" * 50)
print("🏟️ 토너먼트 시뮬레이션 시작")
print("=" * 50)

for n_players in [3, 4, 5, 7, 8, 9, 15, 16, 17, 32]:
    print(f"\n── {n_players}명 토너먼트 ──")

    # 참가자 생성
    players = []
    for i in range(n_players):
        team = _fake_team()
        cost, ok = _cost_check(team)
        if not ok:
            team = _fake_team()  # 재시도
            cost, ok = _cost_check(team)
        players.append((i + 1, {"name": f"Player_{i+1}", "team": team}))

    # 예선 필요 여부
    target = 1
    while target * 2 <= n_players:
        target *= 2
    excess = n_players - target

    print(f"  대진표 크기: {target}, 예선 필요: {excess}경기")

    if excess > 0:
        # 예선 시뮬
        random.shuffle(players)
        prelim_players = players[:excess * 2]
        seeded = players[excess * 2:]

        prelim_winners = []
        for k in range(0, len(prelim_players), 2):
            p1, p2 = prelim_players[k], prelim_players[k+1]
            try:
                winner_side, _ = simulate_match(p1[1]["team"], p2[1]["team"])
                w = p1 if winner_side == "challenger" else p2
                prelim_winners.append(w)
            except Exception as e:
                errors.append(f"예선 매치 에러 ({n_players}명): {e}")
                print(f"  ❌ 예선 에러: {e}")
                prelim_winners.append(p1)  # fallback

        main_players = prelim_winners + seeded
        print(f"  예선 완료 → 본선 {len(main_players)}명")
    else:
        main_players = list(players)

    # 대진표 생성
    try:
        bracket = _generate_bracket(main_players)
        print(f"  대진표 생성 OK — {len(bracket)} 매치")
    except Exception as e:
        errors.append(f"대진표 생성 에러 ({n_players}명): {e}")
        print(f"  ❌ 대진표 생성 에러: {e}")
        continue

    # 대진표 렌더링
    try:
        tree = _render_bracket(bracket)
        if tree:
            print(f"  대진표 렌더링 OK ({len(tree)}자)")
        else:
            print(f"  대진표 렌더링: 빈 결과")
    except Exception as e:
        errors.append(f"대진표 렌더링 에러 ({n_players}명): {e}")
        print(f"  ❌ 대진표 렌더링 에러: {e}")

    # 라운드 진행
    round_num = 0
    try:
        while len(bracket) > 0:
            round_num += 1
            is_final = (len(bracket) == 1 and bracket[0][0] is not None and bracket[0][1] is not None)
            round_size = len(bracket) * 2

            winners = []
            for p1, p2 in bracket:
                if p1 is None and p2 is None:
                    continue
                if p1 is None:
                    winners.append(p2)
                elif p2 is None:
                    winners.append(p1)
                else:
                    winner_side, result = simulate_match(p1[1]["team"], p2[1]["team"])
                    w = p1 if winner_side == "challenger" else p2
                    winners.append(w)

            if is_final:
                print(f"  결승: {winners[0][1]['name']} 우승!")
                break

            # 다음 라운드
            next_bracket = []
            for i in range(0, len(winners), 2):
                if i + 1 < len(winners):
                    next_bracket.append((winners[i], winners[i+1]))
                else:
                    next_bracket.append((winners[i], None))

            bracket = next_bracket
            print(f"  {round_size}강 → {len(bracket)}매치 진행")

    except Exception as e:
        errors.append(f"라운드 진행 에러 ({n_players}명, R{round_num}): {e}")
        print(f"  ❌ 라운드 에러 (R{round_num}): {e}")

# ── 상금 로직 테스트 ──
print(f"\n── 상금 설정 확인 ──")
print(f"  1위 마스터볼: {config.TOURNAMENT_PRIZE_1ST_MB}")
print(f"  2위 마스터볼: {config.TOURNAMENT_PRIZE_2ND_MB}")
print(f"  4강 마스터볼: {config.TOURNAMENT_PRIZE_SEMI_MB}")
print(f"  8강 마스터볼: {config.TOURNAMENT_PRIZE_QUARTER_MB}")
print(f"  16강 마스터볼: {config.TOURNAMENT_PRIZE_R16_MB}")
print(f"  참가 마스터볼: {config.TOURNAMENT_PRIZE_PARTICIPANT_MB}")

# _random_shiny_pokemon 테스트
from services.tournament_service import _random_shiny_pokemon
for rarity in ["ultra_legendary", "legendary", "epic", "common"]:
    try:
        pid, name = _random_shiny_pokemon(rarity)
        print(f"  이로치 뽑기 ({rarity}): {name} (#{pid}) ✓")
    except Exception as e:
        errors.append(f"이로치 뽑기 에러 ({rarity}): {e}")
        print(f"  ❌ 이로치 뽑기 에러 ({rarity}): {e}")

# ── 결과 ──
print("\n" + "=" * 50)
if errors:
    print(f"❌ {len(errors)}개 오류 발견:")
    for e in errors:
        print(f"  • {e}")
else:
    print("✅ 오류 없음! 토너먼트 시뮬레이션 통과")
print("=" * 50)
