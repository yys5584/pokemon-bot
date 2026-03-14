"""BP 가챠 (뽑기) 시스템 서비스."""

import random
import datetime as dt
import logging

import config
from database import queries
from database.battle_queries import get_bp, spend_bp
from database.connection import get_db

logger = logging.getLogger(__name__)


async def roll_gacha(user_id: int) -> dict:
    """가챠 1회 실행. BP 차감 → 확률 뽑기 → 보상 지급 → 결과 반환.

    Returns dict:
        success: bool
        error: str | None
        result_key: str          (config.GACHA_TABLE의 item key)
        display_name: str        (한국어 표시명)
        emoji: str
        detail: str              (추가 설명 텍스트)
        bp_before: int
        bp_after: int
    """
    bp = await get_bp(user_id)
    if bp < config.GACHA_COST:
        return {"success": False, "error": f"BP가 부족합니다. (보유: {bp} / 필요: {config.GACHA_COST})"}

    # BP 차감
    ok = await spend_bp(user_id, config.GACHA_COST)
    if not ok:
        return {"success": False, "error": "BP 차감에 실패했습니다."}

    bp_after = await get_bp(user_id)

    # 확률 뽑기
    roll = random.random()
    cumulative = 0.0
    result_key = "bp_refund"
    display_name = "BP 환급"
    emoji = "💰"

    for prob, key, name, emo in config.GACHA_TABLE:
        cumulative += prob
        if roll < cumulative:
            result_key = key
            display_name = name
            emoji = emo
            break

    # 보상 지급
    detail = await _grant_reward(user_id, result_key)

    # 로그
    await queries.log_gacha(user_id, result_key, config.GACHA_COST)

    return {
        "success": True,
        "error": None,
        "result_key": result_key,
        "display_name": display_name,
        "emoji": emoji,
        "detail": detail,
        "bp_before": bp,
        "bp_after": bp_after,
    }


async def _grant_reward(user_id: int, result_key: str) -> str:
    """보상 지급 후 상세 텍스트 반환."""

    if result_key == "bp_refund":
        amount = random.randint(config.GACHA_BP_REFUND_MIN, config.GACHA_BP_REFUND_MAX)
        pool = await get_db()
        await pool.execute(
            "UPDATE battle_stats SET bp = bp + $2 WHERE user_id = $1",
            user_id, amount)
        return f"+{amount} BP 환급"

    elif result_key == "hyperball":
        await queries.add_hyper_ball(user_id, 2)
        return "하이퍼볼 2개 획득!"

    elif result_key == "masterball":
        await queries.add_master_ball(user_id, 1)
        return "마스터볼 1개 획득!"

    elif result_key == "iv_reroll_all":
        await queries.add_user_item(user_id, "iv_reroll_all", 1)
        return "개체값 재설정권 1개 획득! (DM에서 '아이템' 입력)"

    elif result_key == "bp_jackpot":
        pool = await get_db()
        await pool.execute(
            "UPDATE battle_stats SET bp = bp + $2 WHERE user_id = $1",
            user_id, config.GACHA_BP_JACKPOT)
        return f"+{config.GACHA_BP_JACKPOT} BP 잭팟!!"

    elif result_key == "iv_reroll_one":
        await queries.add_user_item(user_id, "iv_reroll_one", 1)
        return "IV 선택 리롤 1개 획득! (DM에서 '아이템' 입력)"

    elif result_key == "shiny_egg":
        return await _create_shiny_egg(user_id)

    elif result_key == "shiny_spawn":
        await queries.add_shiny_spawn_ticket(user_id, 1)
        return "이로치 강스권 1개 획득! (강제스폰 시 자동 적용)"

    return ""


async def _create_shiny_egg(user_id: int) -> str:
    """이로치 알 생성 — 랜덤 포켓몬 선택, 24시간 부화 타이머."""
    from services.spawn_service import pick_random_pokemon

    # 등급 랜덤 결정 (일반 50%, 레어 30%, 에픽 15%, 전설 4%, 초전설 1%)
    rarity_roll = random.random()
    if rarity_roll < 0.50:
        rarity = "common"
    elif rarity_roll < 0.80:
        rarity = "rare"
    elif rarity_roll < 0.95:
        rarity = "epic"
    elif rarity_roll < 0.99:
        rarity = "legendary"
    else:
        rarity = "ultra_legendary"

    pokemon = await pick_random_pokemon(rarity)
    hatches_at = config.get_kst_now() + dt.timedelta(seconds=config.SHINY_EGG_HATCH_SECONDS)

    egg_id = await queries.create_shiny_egg(user_id, pokemon["id"], rarity, hatches_at)

    rarity_labels = {"common": "일반", "rare": "레어", "epic": "에픽",
                     "legendary": "전설", "ultra_legendary": "초전설"}
    rarity_name = rarity_labels.get(rarity, rarity)

    hatch_time = hatches_at.strftime("%m/%d %H:%M")
    return f"🥚 ??? ({rarity_name}) — {hatch_time} 부화 예정"


async def hatch_ready_eggs(bot) -> list[dict]:
    """부화 시간이 된 알을 처리하고 DM 발송용 데이터 반환."""
    eggs = await queries.get_ready_eggs()
    results = []

    for egg in eggs:
        user_id = egg["user_id"]
        pokemon_id = egg["pokemon_id"]

        # 이로치 확정으로 포켓몬 추가
        from utils.battle_calc import generate_ivs
        ivs = generate_ivs(is_shiny=True)
        instance_id, final_ivs = await queries.add_pokemon_to_user(
            user_id, pokemon_id, chat_id=None, is_shiny=True, ivs=ivs)

        # 도감 등록
        await queries.register_pokedex(user_id, pokemon_id, method="catch")

        await queries.mark_egg_hatched(egg["id"])

        results.append({
            "user_id": user_id,
            "pokemon_id": pokemon_id,
            "name_ko": egg["name_ko"],
            "rarity": egg["rarity"],
            "ivs": final_ivs,
            "instance_id": instance_id,
        })

    return results
