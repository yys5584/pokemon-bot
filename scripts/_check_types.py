"""듀얼타입 상성 적용 검증."""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

async def main():
    from database.connection import get_db
    pool = await get_db()
    from models.pokemon_base_stats import POKEMON_BASE_STATS
    from utils.battle_calc import get_type_multiplier
    import config

    check = [
        (257, '초염몽', ['fire','fighting']),
        (445, '한카리아스', ['dragon','ground']),
        (376, '메타그로스', ['steel','psychic']),
        (130, '갸라도스', ['water','flying']),
        (248, '마기라스', ['rock','dark']),
        (483, '디아루가', ['steel','dragon']),
        (484, '펄기아', ['water','dragon']),
        (145, '썬더', ['electric','flying']),
        (303, '입치트', ['steel','fairy']),
        (289, '게을킹', ['normal']),
        (245, '스이쿤', ['water']),
        (150, '뮤츠', ['psychic']),
    ]

    print("=== 듀얼타입 상성 적용 검증 ===\n")
    for pid, name, expected in check:
        bs = POKEMON_BASE_STATS.get(pid)
        actual = list(bs[6]) if bs and len(bs) > 6 else ['?']
        match = actual == expected

        row = await pool.fetchrow(
            "SELECT ROUND(AVG(super_effective_hits)::numeric,1) as se, "
            "ROUND(AVG(not_effective_hits)::numeric,1) as ne, "
            "COUNT(*) as bat "
            "FROM battle_pokemon_stats "
            "WHERE pokemon_id = $1",
            pid
        )
        se = row[0] or 0
        ne = row[1] or 0
        bat = row[2]

        status = '✅' if match else '❌'
        types_str = '/'.join(actual)
        print(f"  {status} {name:<12} 타입={types_str:<24} se={se} ne={ne} ({bat}전)")

    # 상성 테이블 vs 본가 크로스체크 — 주요 매치업
    print("\n=== 주요 상성 매치업 검증 ===\n")
    matchups = [
        (['fire'], ['grass'], '불→풀', 2.0),
        (['fire'], ['water'], '불→물', 0.5),
        (['water'], ['fire'], '물→불', 2.0),
        (['electric'], ['water'], '전기→물', 2.0),
        (['electric'], ['ground'], '전기→땅', 0.0),
        (['ground'], ['electric'], '땅→전기', 2.0),
        (['ice'], ['dragon'], '얼음→드래곤', 2.0),
        (['fairy'], ['dragon'], '페어리→드래곤', 2.0),
        (['dragon'], ['fairy'], '드래곤→페어리', 0.0),
        (['fighting'], ['steel'], '격투→강철', 2.0),
        (['fire'], ['steel'], '불→강철', 2.0),
        (['fire'], ['steel', 'dragon'], '불→강철드래곤', 1.0),
        (['fighting'], ['steel', 'dragon'], '격투→강철드래곤', 2.0),
        (['ground'], ['steel', 'dragon'], '땅→강철드래곤', 2.0),
        (['ice'], ['dragon', 'ground'], '얼음→드래곤땅', 4.0),
        (['fairy'], ['dragon', 'ground'], '페어리→드래곤땅', 2.0),
    ]

    all_ok = True
    for atk, defe, label, expected_mult in matchups:
        actual_mult, _ = get_type_multiplier(atk, defe)
        ok = abs(actual_mult - expected_mult) < 0.01
        status = '✅' if ok else '❌'
        if not ok: all_ok = False
        print(f"  {status} {label:<20} 예상={expected_mult}x 실제={actual_mult}x")

    if all_ok:
        print("\n  ✅ 모든 상성 매치업 정상")
    else:
        print("\n  ❌ 상성 매치업 불일치 발견!")

asyncio.run(main())
