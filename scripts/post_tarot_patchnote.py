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
    lines.append('<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(80px,1fr));gap:8px">')
    for c in major:
        pokemon = c.get("pokemon", "")
        lines.append(
            f'<div style="text-align:center">'
            f'<img src="{_card_image(c)}" style="width:100%;border-radius:6px;box-shadow:0 2px 8px rgba(0,0,0,0.3)" loading="lazy"/>'
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
        lines.append('<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(80px,1fr));gap:8px">')
        for c in suit_cards:
            pokemon = c.get("pokemon", "")
            lines.append(
                f'<div style="text-align:center">'
                f'<img src="{_card_image(c)}" style="width:100%;border-radius:6px;box-shadow:0 2px 8px rgba(0,0,0,0.3)" loading="lazy"/>'
                f'<div style="font-size:11px;margin-top:4px;color:#e0e0e0">{c["name_ko"]}</div>'
                f'<div style="font-size:10px;color:#888">{pokemon}</div>'
                f'</div>'
            )
        lines.append('</div>')

    return "\n".join(lines)


NOTICE_TITLE = "🔮 타로 시스템 오픈 — 78장 포켓몬 타로 카드"

NOTICE_CONTENT = f"""\
<b>🔮 포켓몬 타로 시스템 오픈!</b>

메이저 아르카나 22장 + 마이너 아르카나 56장.
78장의 카드에 각각 포켓몬이 대응되는 TG포켓만의 타로 덱입니다.
DM에서 <b>타로</b>를 입력하면 바로 리딩을 받을 수 있어요.

<b>📋 주요 기능</b>
• 주제 선택 — 연애, 직장, 재물, 투자, 인간관계, 종합
• 상황별 맞춤 해석 — 연애중/짝사랑/솔로 등 세부 질문
• 기간 선택 — 이번 주 / 이번 달
• 카드 한 장씩 오픈하는 의식 플로우
• Gemini AI 기반 카드별 해석 + 종합 인사이트
• 별자리 연동 (생년월일 등록 시)
• 그룹 공유 기능 — '타로공유' 명령으로 리딩 공유

<b>🌟 데일리 운세</b>
• DM/그룹에서 <b>운세</b> 입력
• Swiss Ephemeris 천문 계산 기반 별자리 운세
• 하루 첫 운세 시 성격변경권 1개 지급

<h3 style="margin:24px 0 8px">🛠️ 이거 만드느라 일주일 걸렸습니다</h3>
<div style="color:#aaa;font-size:13px;line-height:1.6">
커밋 32개, 코드 수천 줄. 간단히 요약하면:
<br><br>
<b>1. 78장 카드 덱 구축</b><br>
전통 라이더-웨이트 타로 78장을 기반으로 각 카드에 포켓몬을 매핑했습니다.
바보(0번) = 고라파덕, 마법사(1번) = 후딘, 태양(19번) = 피카츄 같은 식으로요.
메이저 22장 + 마이너 56장 모든 카드에 한국어 이름, 정방향/역방향 해석, 주제별 의미를 수작업으로 넣었습니다.
<br><br>
<b>2. 78장 카드 이미지 생성</b><br>
포켓몬 공식 스프라이트 + 타로 카드 프레임을 합성해서 78장 전부 이미지를 만들었습니다.
메이저 아르카나는 커스텀 배경, 마이너 아르카나는 슈트별 색상 테마 적용.
<br><br>
<b>3. Gemini AI 해석 엔진</b><br>
Google Gemini Flash API를 연동해서 카드 조합 + 질문자 상황에 맞는 맞춤 해석을 생성합니다.
프롬프트만 10번 넘게 갈아엎었습니다... 시제 규칙, 바넘효과 방지, 카드 원본 의미 존중 등.
해석 결과는 DB에 캐싱해서 같은 조합이면 API 재호출 없이 즉시 반환.
<br><br>
<b>4. Swiss Ephemeris 천문 계산</b><br>
데일리 운세를 위해 실제 행성 위치를 계산하는 swisseph 라이브러리를 붙였습니다.
태양, 달, 수성, 금성, 화성의 현재 별자리 트랜짓을 계산해서 AI에게 넘기면
"오늘 금성이 쌍둥이자리에 있으니 소통이 활발한 날" 같은 해석이 나옵니다.
<br><br>
<b>5. UX 32번의 시행착오</b><br>
스프레드 선택 → 제거, 카드 7장 → 18장 그리드, 피카 화법 → 전문가 톤,
종합해석 서사 → 인사이트 1~2줄, AI 선호출 → 지연호출(속도 개선)...
매일 테스트하고 고치고를 반복한 일주일이었습니다.
</div>

{_build_card_grid()}

<div style="margin-top:24px;color:#888;font-size:12px">
DM에서 <b>타로</b> · <b>운세</b>를 입력해보세요!
</div>"""


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
