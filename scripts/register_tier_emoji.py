"""
티어 커스텀 이모지 스티커셋 등록 + 테스트 DM
"""
import os, asyncio, aiohttp, json

BOT_TOKEN = open(r"C:\Users\Administrator\Desktop\pokemon-bot\.env").readline().split("=", 1)[1].strip()
ADMIN_ID = 1832746512
ASSET_DIR = r"C:\Users\Administrator\Desktop\pokemon-bot\assets\tier_emoji_v3"
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

EMOJI_FILES = [
    ("tier_bronze_ii.png", "🥉", "브론즈 II"),
    ("tier_bronze_i.png", "🥉", "브론즈 I"),
    ("tier_silver_ii.png", "🥈", "실버 II"),
    ("tier_silver_i.png", "🥈", "실버 I"),
    ("tier_gold_ii.png", "🏅", "골드 II"),
    ("tier_gold_i.png", "🏅", "골드 I"),
    ("tier_platinum_ii.png", "💎", "플래티넘 II"),
    ("tier_platinum_i.png", "💎", "플래티넘 I"),
    ("tier_diamond_ii.png", "💠", "다이아 II"),
    ("tier_diamond_i.png", "💠", "다이아 I"),
    ("tier_master.png", "👑", "마스터"),
    ("tier_challenger.png", "⚔", "챌린저"),
]


async def api_call(session, method, **kwargs):
    url = f"{API}/{method}"
    async with session.post(url, **kwargs) as resp:
        return await resp.json()


async def delete_set_if_exists(session, set_name):
    """기존 세트 삭제 시도"""
    result = await api_call(session, "getStickerSet", json={"name": set_name})
    if result.get("ok"):
        # 스티커 하나씩 삭제 후 세트 삭제
        stickers = result["result"]["stickers"]
        for s in stickers:
            await api_call(session, "deleteStickerFromSet",
                          json={"sticker": s["file_id"]})
        await api_call(session, "deleteStickerSet", json={"name": set_name})
        print(f"  🗑️ 기존 세트 삭제: {set_name}")


async def main():
    async with aiohttp.ClientSession() as session:
        # 봇 유저네임 가져오기
        me = await api_call(session, "getMe")
        bot_username = me["result"]["username"]
        set_name = f"tgpoke_rank_by_{bot_username}"
        print(f"봇: @{bot_username}")
        print(f"세트: {set_name}\n")

        # 기존 세트 삭제
        await delete_set_if_exists(session, set_name)

        # 1. 첫 번째 이모지로 스티커셋 생성
        first = EMOJI_FILES[0]
        file_path = os.path.join(ASSET_DIR, first[0])

        data = aiohttp.FormData()
        data.add_field("user_id", str(ADMIN_ID))
        data.add_field("name", set_name)
        data.add_field("title", "TGPoke 랭크 티어")
        data.add_field("sticker_type", "custom_emoji")
        sticker_json = json.dumps({
            "sticker": "attach://file0",
            "format": "static",
            "emoji_list": [first[1]],
        })
        data.add_field("stickers", f"[{sticker_json}]")
        with open(file_path, "rb") as f:
            data.add_field("file0", f, filename=first[0], content_type="image/png")
            result = await api_call(session, "createNewStickerSet", data=data)

        if result.get("ok"):
            print(f"✅ 세트 생성 완료: {first[2]}")
        else:
            print(f"❌ 세트 생성 실패: {result}")
            # 에러 상세
            if "STICKER_PNG_DIMENSIONS" in str(result):
                print("   → 이미지 사이즈가 100x100이어야 합니다")
            return

        # 2. 나머지 이모지 추가
        for fname, emoji, label in EMOJI_FILES[1:]:
            file_path = os.path.join(ASSET_DIR, fname)
            data = aiohttp.FormData()
            data.add_field("user_id", str(ADMIN_ID))
            data.add_field("name", set_name)

            sticker_json = json.dumps({
                "sticker": "attach://file0",
                "format": "static",
                "emoji_list": [emoji],
            })
            data.add_field("sticker", sticker_json)
            with open(file_path, "rb") as f:
                data.add_field("file0", f, filename=fname, content_type="image/png")
                result = await api_call(session, "addStickerToSet", data=data)

            if result.get("ok"):
                print(f"  ✅ {label}")
            else:
                print(f"  ❌ {label}: {result}")

        # 3. 스티커셋 정보 가져와서 custom_emoji_id 확인
        print("\n📋 등록된 이모지 ID 확인...")
        result = await api_call(session, "getStickerSet", json={"name": set_name})
        if not result.get("ok"):
            print(f"❌ getStickerSet 실패: {result}")
            return

        stickers = result["result"]["stickers"]
        emoji_ids = []
        for i, s in enumerate(stickers):
            eid = s.get("custom_emoji_id", "N/A")
            label = EMOJI_FILES[i][2] if i < len(EMOJI_FILES) else "?"
            print(f"  {label:12s} → custom_emoji_id: {eid}")
            emoji_ids.append(eid)

        # 4. 커스텀 이모지로 테스트 DM 전송
        print("\n📤 커스텀 이모지 테스트 DM 전송...")
        lines = ["🏆 <b>TGPoke 랭크 티어 커스텀 이모지</b>\n"]
        for i, (fname, emoji, label) in enumerate(EMOJI_FILES):
            if i < len(emoji_ids) and emoji_ids[i] != "N/A":
                eid = emoji_ids[i]
                lines.append(
                    f'<tg-emoji emoji-id="{eid}">{emoji}</tg-emoji> {label}'
                )
        text = "\n".join(lines)

        result = await api_call(session, "sendMessage", json={
            "chat_id": ADMIN_ID,
            "text": text,
            "parse_mode": "HTML",
        })
        if result.get("ok"):
            print("✅ DM 전송 완료!")
        else:
            print(f"❌ DM 실패: {result}")

        # emoji_ids를 파일로 저장
        id_map = {}
        for i, (fname, emoji, label) in enumerate(EMOJI_FILES):
            key = fname.replace("tier_", "").replace(".png", "")
            if i < len(emoji_ids):
                id_map[key] = emoji_ids[i]

        with open(os.path.join(ASSET_DIR, "emoji_ids.json"), "w") as f:
            json.dump(id_map, f, indent=2, ensure_ascii=False)
        print(f"\n💾 emoji_ids.json 저장 완료")


asyncio.run(main())
