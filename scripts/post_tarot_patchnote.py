"""타로 업데이트 패치노트 — 78장 카드 그리드 + 변경사항 + 개발기."""
import asyncio
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from database.connection import get_db

# ── 카드 데이터 로드 ──
CARD_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "tarot_cards_full.json")
with open(CARD_PATH, encoding="utf-8") as f:
    ALL_CARDS = json.load(f)

SUIT_KO = {"wands": "🔥 지팡이", "cups": "💧 컵", "swords": "🗡️ 검", "pentacles": "🪙 동전"}


def _card_image(c):
    if c["type"] == "major":
        return f"/tarot-assets/{c['value_int']}.jpg"
    return f"/tarot-assets/{c['name_short']}.jpg"


def _build_card_grid():
    """78장 카드 HTML 그리드 생성."""
    lines = []

    # Major Arcana
    major = sorted([c for c in ALL_CARDS if c["type"] == "major"], key=lambda c: c["value_int"])
    lines.append('<h3 style="margin:24px 0 12px">✨ 메이저 아르카나 (22장)</h3>')
    lines.append('<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(80px,1fr));gap:8px;align-items:end">')
    for c in major:
        pokemon = c.get("pokemon", "")
        lines.append(
            f'<div style="text-align:center">'
            f'<img src="{_card_image(c)}" style="width:100%;aspect-ratio:2/3;object-fit:cover;border-radius:6px;box-shadow:0 2px 8px rgba(0,0,0,0.3)" loading="lazy"/>'
            f'<div style="font-size:11px;margin-top:4px;color:#e0e0e0">{c["name_ko"]}</div>'
            f'<div style="font-size:10px;color:#888">{pokemon}</div>'
            f'</div>'
        )
    lines.append('</div>')

    # Minor Arcana by suit
    minor = [c for c in ALL_CARDS if c["type"] != "major"]
    for suit_key in ["wands", "cups", "swords", "pentacles"]:
        suit_cards = sorted(
            [c for c in minor if c.get("suit") == suit_key],
            key=lambda c: c["value_int"],
        )
        suit_label = SUIT_KO.get(suit_key, suit_key)
        lines.append(f'<h3 style="margin:24px 0 12px">{suit_label} ({len(suit_cards)}장)</h3>')
        lines.append('<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(80px,1fr));gap:8px;align-items:end">')
        for c in suit_cards:
            pokemon = c.get("pokemon", "")
            lines.append(
                f'<div style="text-align:center">'
                f'<img src="{_card_image(c)}" style="width:100%;aspect-ratio:2/3;object-fit:cover;border-radius:6px;box-shadow:0 2px 8px rgba(0,0,0,0.3)" loading="lazy"/>'
                f'<div style="font-size:11px;margin-top:4px;color:#e0e0e0">{c["name_ko"]}</div>'
                f'<div style="font-size:10px;color:#888">{pokemon}</div>'
                f'</div>'
            )
        lines.append('</div>')

    return "\n".join(lines)


NOTICE_TITLE = "🔮 타로 시스템 오픈 — 78장 포켓몬 타로 카드"

NOTICE_CONTENT = f"""\
<b>🔮 포켓몬 타로 시스템 오픈!</b>

78장 포켓몬 타로 덱이 나왔습니다.
DM에서 <b>타로</b> 입력하면 바로 리딩, <b>운세</b> 입력하면 데일리 별자리 운세.
주제(연애/직장/재물/투자/인간관계/종합) 고르고, 상황 답하고, 카드 뽑으면 끝!
첫 운세 때 성격변경권 1개 드려요.

<b>🛠️ 개발일기</b>
처음엔 "타로 하나 넣으면 재밌겠다" 싶어서 가볍게 시작했는데, 카드가 78장이더라고요. 22장만 하려다 마이너까지 하게 됐고, 카드마다 포켓몬 붙이고 이미지 만들고 해석 쓰다 보니 이게 왜 이렇게 커지지...? 해석도 처음엔 정해진 문장만 보여줬는데 너무 밋밋해서 AI 해석을 달았더니 "피카 화법"이 오글거려서 전문가 톤으로 바꾸고, 종합해석이 카드 반복이라 인사이트만 남기고, 카드 뽑는 맛이 없어서 한 장씩 오픈하는 연출 넣고... 고치고 고치고 또 고쳤습니다.
운세도 그냥 랜덤 문장 돌리려다가 "진짜 별자리 운세를 하면 어떨까" 욕심이 나서 실제 행성 위치를 계산하는 천문 라이브러리까지 붙였습니다. 오늘 금성이 어디 있는지에 따라 해석이 달라져요.
결과적으로 일주일, 수정 32번. 바보(고라파덕)부터 세계(뮤)까지, 아래에서 전체 카드 구경하세요!
— 문박사 🧑‍🔬

{_build_card_grid()}"""


async def main():
    pool = await get_db()

    await pool.execute(
        "INSERT INTO board_posts (board_type, user_id, display_name, tag, title, content) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        "notice", 1832746512, "TG포켓", "패치노트", NOTICE_TITLE, NOTICE_CONTENT,
    )
    print("OK: Tarot patch note posted to board_posts")


if __name__ == "__main__":
    asyncio.run(main())
