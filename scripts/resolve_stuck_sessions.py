"""재시작으로 미해결된 세션 수동 resolve + 마볼 환불 + DM 발송."""
import asyncio
import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# 미해결 세션 ID 목록 (DB에서 확인됨)
# 166147: 이로치 얼루기 (chat -1003762500964) — 16명 전원 마볼
# 166148, 166149, 166150: 일반 스폰 (재시작 시점)
# 166119: 오래된 미해결 (15:43)
# 166339~166343: 현재 활성 스폰 (건드리지 않음)
STUCK_SESSION_IDS = [166147, 166148, 166149, 166150, 166119]


async def main():
    import asyncpg
    from telegram import Bot

    bot = Bot(token=BOT_TOKEN)
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)

    for session_id in STUCK_SESSION_IDS:
        print(f"\n--- Session {session_id} ---")

        sess = await conn.fetchrow(
            "SELECT ss.id, ss.chat_id, ss.pokemon_id, pm.name_ko, pm.rarity, "
            "pm.catch_rate, ss.is_shiny, ss.is_resolved, ss.spawned_at "
            "FROM spawn_sessions ss JOIN pokemon_master pm ON ss.pokemon_id = pm.id "
            "WHERE ss.id = $1", session_id
        )
        if not sess:
            print(f"  Session not found")
            continue
        if sess["is_resolved"] == 1:
            print(f"  Already resolved, skipping")
            continue

        print(f"  {sess['name_ko']} shiny={sess['is_shiny']} chat={sess['chat_id']}")

        # 시도 목록
        attempts = await conn.fetch(
            "SELECT user_id, used_master_ball, used_hyper_ball, attempted_at "
            "FROM catch_attempts WHERE session_id = $1 ORDER BY attempted_at",
            session_id
        )
        print(f"  {len(attempts)} attempts")

        if not attempts:
            # 아무도 안 던짐 → 도망 처리
            await conn.execute(
                "UPDATE spawn_sessions SET is_resolved = 1 WHERE id = $1", session_id
            )
            print(f"  No attempts, marked escaped")
            continue

        # 승자 결정: 마볼 우선, 같으면 첫 번째
        master_users = [a for a in attempts if a["used_master_ball"] == 1]
        if master_users:
            winner = master_users[0]  # 가장 먼저 던진 마볼 유저
        else:
            # 일반볼: catch_rate 기반 랜덤
            catch_rate = sess["catch_rate"] or 0.5
            winners = []
            for a in attempts:
                if a["used_hyper_ball"]:
                    rate = min(1.0, catch_rate * 2.0)
                else:
                    rate = catch_rate
                roll = random.random()
                if roll < rate:
                    winners.append((a, roll))
            if winners:
                winners.sort(key=lambda x: x[1])
                winner = winners[0][0]
            else:
                # 모두 실패
                await conn.execute(
                    "UPDATE spawn_sessions SET is_resolved = 1 WHERE id = $1", session_id
                )
                print(f"  All failed, marked escaped")
                # 마볼/하볼 환불
                for a in attempts:
                    if a["used_master_ball"]:
                        await conn.execute(
                            "UPDATE users SET master_balls = master_balls + 1 WHERE user_id = $1",
                            a["user_id"]
                        )
                        print(f"  Refunded master ball to {a['user_id']}")
                    if a["used_hyper_ball"]:
                        await conn.execute(
                            "UPDATE users SET hyper_balls = hyper_balls + 1 WHERE user_id = $1",
                            a["user_id"]
                        )
                        print(f"  Refunded hyper ball to {a['user_id']}")
                continue

        winner_id = winner["user_id"]
        print(f"  Winner: {winner_id} (master_ball={winner['used_master_ball']})")

        # 포켓몬 지급
        import json
        iv_hp = random.randint(0, 31)
        iv_atk = random.randint(0, 31)
        iv_def = random.randint(0, 31)
        iv_spa = random.randint(0, 31)
        iv_spdef = random.randint(0, 31)
        iv_spd = random.randint(0, 31)

        inst_id = await conn.fetchval(
            "INSERT INTO user_pokemon (user_id, pokemon_id, is_shiny, friendship, "
            "iv_hp, iv_atk, iv_def, iv_spa, iv_spdef, iv_spd, caught_in_chat_id) "
            "VALUES ($1, $2, $3, 0, $4, $5, $6, $7, $8, $9, $10) RETURNING id",
            winner_id, sess["pokemon_id"], sess["is_shiny"],
            iv_hp, iv_atk, iv_def, iv_spa, iv_spdef, iv_spd,
            sess["chat_id"]
        )
        print(f"  Pokemon instance {inst_id} created")

        # 도감 등록
        await conn.execute(
            "INSERT INTO pokedex (user_id, pokemon_id) VALUES ($1, $2) "
            "ON CONFLICT (user_id, pokemon_id) DO NOTHING",
            winner_id, sess["pokemon_id"]
        )

        # 세션 resolved
        await conn.execute(
            "UPDATE spawn_sessions SET is_resolved = 1 WHERE id = $1", session_id
        )

        # 패배자 마볼/하볼 환불
        refunded_users = []
        for a in attempts:
            if a["user_id"] == winner_id:
                continue
            if a["used_master_ball"]:
                await conn.execute(
                    "UPDATE users SET master_balls = master_balls + 1 WHERE user_id = $1",
                    a["user_id"]
                )
                refunded_users.append(a["user_id"])
                print(f"  Refunded master ball to {a['user_id']}")
            if a["used_hyper_ball"]:
                await conn.execute(
                    "UPDATE users SET hyper_balls = hyper_balls + 1 WHERE user_id = $1",
                    a["user_id"]
                )

        # 승자 이름 조회
        winner_row = await conn.fetchrow(
            "SELECT display_name FROM users WHERE user_id = $1", winner_id
        )
        winner_name = winner_row["display_name"] if winner_row else str(winner_id)

        shiny_tag = "이로치 " if sess["is_shiny"] else ""
        iv_sum = iv_hp + iv_atk + iv_def + iv_spa + iv_spdef + iv_spd

        # 그룹 채팅에 결과 발송
        try:
            msg = (
                f"🔄 <b>서버 복구</b> — {winner_name}님이 "
                f"{shiny_tag}{sess['name_ko']}을(를) 포획했습니다! "
                f"[IV: {iv_sum}/186]\n"
                f"⚠️ 서버 재시작으로 지연된 포획이 처리되었습니다."
            )
            if refunded_users:
                msg += f"\n🔄 마스터볼 {len(refunded_users)}개 환불 완료"
            await bot.send_message(chat_id=sess["chat_id"], text=msg, parse_mode="HTML")
            print(f"  Group message sent")
        except Exception as e:
            print(f"  Group message failed: {e}")

        # 승자 DM
        try:
            dm = (
                f"🔄 <b>서버 복구 알림</b>\n"
                f"{'✨ ' if sess['is_shiny'] else ''}{sess['name_ko']} 포획 완료!\n"
                f"IV: {iv_hp}/{iv_atk}/{iv_def}/{iv_spa}/{iv_spdef}/{iv_spd} ({iv_sum}/186)\n\n"
                f"서버 재시작으로 포획 알림이 지연되었습니다. 자동으로 가방에 넣었습니다."
            )
            await bot.send_message(chat_id=winner_id, text=dm, parse_mode="HTML")
            print(f"  Winner DM sent")
        except Exception as e:
            print(f"  Winner DM failed: {e}")

        # 환불 DM 발송
        for uid in refunded_users:
            try:
                await bot.send_message(
                    chat_id=uid,
                    text="🔄 서버 점검으로 인해 마스터볼이 환불되었습니다.",
                    parse_mode="HTML",
                )
            except Exception:
                pass

    await conn.close()
    await bot.close()
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
