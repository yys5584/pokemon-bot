"""
티어 이모지 샘플 DM 전송 + 커스텀 이모지 스티커셋 생성
"""
import os, asyncio, aiohttp

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 1832746512
ASSET_DIR = r"C:\Users\Administrator\Desktop\pokemon-bot\assets\tier_emoji_v3"

API = f"https://api.telegram.org/bot{BOT_TOKEN}"


async def send_photo(session, chat_id, photo_path, caption=""):
    url = f"{API}/sendPhoto"
    with open(photo_path, "rb") as f:
        data = aiohttp.FormData()
        data.add_field("chat_id", str(chat_id))
        data.add_field("photo", f, filename=os.path.basename(photo_path))
        if caption:
            data.add_field("caption", caption)
        async with session.post(url, data=data) as resp:
            result = await resp.json()
            if not result.get("ok"):
                print(f"  ❌ sendPhoto failed: {result}")
            return result


async def get_bot_username(session):
    url = f"{API}/getMe"
    async with session.get(url) as resp:
        result = await resp.json()
        return result["result"]["username"]


async def create_custom_emoji_set(session, bot_username):
    """커스텀 이모지 스티커셋 생성"""
    set_name = f"ranked_tiers_by_{bot_username}"

    # 파일 목록 (순서대로)
    files = [
        ("tier_bronze_ii.png", "🥉"),
        ("tier_bronze_i.png", "🥉"),
        ("tier_silver_ii.png", "🥈"),
        ("tier_silver_i.png", "🥈"),
        ("tier_gold_ii.png", "🏅"),
        ("tier_gold_i.png", "🏅"),
        ("tier_platinum_ii.png", "💎"),
        ("tier_platinum_i.png", "💎"),
        ("tier_diamond_ii.png", "💠"),
        ("tier_diamond_i.png", "💠"),
        ("tier_master.png", "👑"),
        ("tier_challenger.png", "⚔"),
    ]

    # 1. 첫 번째 이모지로 스티커셋 생성
    first_file = files[0]
    file_path = os.path.join(ASSET_DIR, first_file[0])

    with open(file_path, "rb") as f:
        data = aiohttp.FormData()
        data.add_field("user_id", str(ADMIN_ID))
        data.add_field("name", set_name)
        data.add_field("title", "TGPoke 랭크 티어")
        data.add_field("sticker_type", "custom_emoji")
        # sticker as JSON input_sticker
        import json
        sticker_data = json.dumps({
            "sticker": "attach://sticker_file",
            "format": "static",
            "emoji_list": [first_file[1]],
        })
        data.add_field("stickers", f"[{sticker_data}]")
        data.add_field("sticker_file", f, filename=first_file[0])

        url = f"{API}/createNewStickerSet"
        async with session.post(url, data=data) as resp:
            result = await resp.json()
            if result.get("ok"):
                print(f"  ✅ 스티커셋 생성: {set_name}")
            else:
                if "name is already taken" in str(result):
                    print(f"  ℹ️ 스티커셋 이미 존재: {set_name}")
                else:
                    print(f"  ❌ 생성 실패: {result}")
                    return set_name

    # 2. 나머지 이모지 추가
    for fname, emoji in files[1:]:
        file_path = os.path.join(ASSET_DIR, fname)
        with open(file_path, "rb") as f:
            data = aiohttp.FormData()
            data.add_field("user_id", str(ADMIN_ID))
            data.add_field("name", set_name)
            sticker_data = json.dumps({
                "sticker": "attach://sticker_file",
                "format": "static",
                "emoji_list": [emoji],
            })
            data.add_field("sticker", sticker_data)
            data.add_field("sticker_file", f, filename=fname)

            url = f"{API}/addStickerToSet"
            async with session.post(url, data=data) as resp:
                result = await resp.json()
                label = fname.replace("tier_", "").replace(".png", "")
                if result.get("ok"):
                    print(f"  ✅ 추가: {label}")
                else:
                    print(f"  ❌ 추가 실패 {label}: {result}")

    return set_name


async def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN 환경변수 없음")
        return

    async with aiohttp.ClientSession() as session:
        # 1. 프리뷰 이미지 DM 전송
        preview_path = os.path.join(ASSET_DIR, "_preview.png")
        print("📤 프리뷰 이미지 전송...")
        await send_photo(session, ADMIN_ID, preview_path,
                        "🏆 랭크 티어 이모지 v3 샘플\n\n"
                        "브론즈 II/I → 실버 → 골드 → 플래티넘 → 다이아 → 마스터 → 챌린저\n\n"
                        "확인 후 커스텀 이모지로 등록할게요!")

        # 2. 개별 이미지도 전송 (큰 사이즈로 확인)
        tier_files = [
            ("tier_bronze_ii.png", "브론즈 II"),
            ("tier_gold_i.png", "골드 I"),
            ("tier_diamond_ii.png", "다이아 II"),
            ("tier_master.png", "마스터"),
            ("tier_challenger.png", "챌린저"),
        ]
        for fname, label in tier_files:
            fpath = os.path.join(ASSET_DIR, fname)
            await send_photo(session, ADMIN_ID, fpath, label)

        print("\n✅ DM 전송 완료!")


asyncio.run(main())
