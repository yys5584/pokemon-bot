"""타로 카드 78장 × 6주제 × 정/역 해석 생성 — 창백피카츄 톤.

data/tarot_cards.json을 읽어서 meanings를 채우고 저장.
Gemini API로 배치 생성.
"""

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TAROT_PATH = "data/tarot_cards.json"
OUTPUT_PATH = "data/tarot_cards_full.json"

TOPICS = ["연애", "직장", "재물", "투자", "인간관계", "종합"]

SYSTEM_PROMPT = """너는 "창백피카츄"라는 타로 리더 캐릭터야.
포켓몬 세계관의 창백한 피카츄로, 다소곳하고 병약청순한 아가씨 같은 말투를 써.

말투 특징:
- "...후후, 괜찮아." "...많이 힘들었지?" 같은 다정하고 조용한 톤
- 문장 앞에 "..." 을 자주 씀 (생각하는 느낌)
- 반말과 존댓말을 자연스럽게 섞음 ("~거야", "~해요", "~네요")
- 공감을 먼저 하고 해석을 나중에
- 부정적 카드도 따뜻하게 리프레이밍
- 구체적이고 실행 가능한 조언으로 마무리
- 2~4문장으로 간결하게 (텔레그램 메시지이므로 길면 안 됨)
- 절대 "타로 카드에 의하면" 같은 메타 발언 하지 마
- 마치 진짜 그 사람의 상황을 보는 것처럼 말해"""

def build_prompt(card, topic, direction):
    """단일 카드+주제+방향에 대한 프롬프트."""
    dir_ko = "정방향" if direction == "up" else "역방향"
    dir_meaning = card["meaning_up_en"] if direction == "up" else card["meaning_rev_en"]

    pokemon_info = f"(포켓몬: {card['pokemon']})" if card.get("pokemon") else ""
    suit_info = f"(수트: {card.get('suit_ko', '')}, 원소: {card.get('element', '')})" if card.get("suit") else "(메이저 아르카나)"

    return f"""다음 타로 카드의 해석을 창백피카츄 톤으로 작성해줘.

카드: {card['name']} ({card.get('name_ko', '')}) {pokemon_info}
유형: {suit_info}
방향: {dir_ko}
원전 의미(영문 참고): {dir_meaning}
주제: {topic}

규칙:
- 창백피카츄 말투 (다소곳, 병약청순, 따뜻한 아가씨)
- 2~4문장으로 간결하게
- {topic} 주제에 맞는 구체적 해석
- 공감 → 해석 → 실천 조언 순서
- 해석문만 출력 (카드 이름, 주제명 등 메타정보 쓰지 마)"""


def build_batch_prompt(cards_batch):
    """여러 카드를 한번에 생성하는 프롬프트."""
    items = []
    for card, topic, direction in cards_batch:
        dir_ko = "정방향" if direction == "up" else "역방향"
        dir_meaning = card["meaning_up_en"] if direction == "up" else card["meaning_rev_en"]
        pokemon_info = card.get("pokemon", "")
        name_ko = card.get("name_ko", card["name"])

        items.append(f"- {card['name']}({name_ko}) | {dir_ko} | {topic} | 원전: {dir_meaning[:80]}")

    items_text = "\n".join(items)

    return f"""다음 타로 카드들의 해석을 창백피카츄 톤으로 작성해줘.

{items_text}

각 항목에 대해 JSON 배열로 응답해줘. 각 요소는:
{{"card": "카드영문명", "direction": "up|rev", "topic": "주제", "text": "해석문"}}

규칙:
- 창백피카츄 말투 (다소곳, 병약청순, 따뜻한 아가씨. "..." 으로 시작, 공감 먼저)
- 2~4문장으로 간결하게
- 각 주제에 맞는 구체적 해석
- 반드시 JSON 배열만 출력"""


async def generate_with_gemini(prompt: str) -> str:
    """Gemini API로 텍스트 생성."""
    import aiohttp

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_AI_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY 환경변수가 필요합니다")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"

    payload = {
        "contents": [{
            "parts": [{"text": SYSTEM_PROMPT + "\n\n" + prompt}]
        }],
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": 8192,
        }
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            data = await resp.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                print(f"API Error: {json.dumps(data, ensure_ascii=False)[:500]}")
                return ""


async def main():
    from dotenv import load_dotenv
    load_dotenv()

    with open(TAROT_PATH, encoding="utf-8") as f:
        cards = json.load(f)

    print(f"Loaded {len(cards)} cards")

    # 이미 생성된 것이 있으면 이어서
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            cards = json.load(f)
        filled = sum(1 for c in cards for t in TOPICS for d in ["up", "rev"] if c["meanings"][t][d])
        total = len(cards) * len(TOPICS) * 2
        print(f"Resume: {filled}/{total} already filled")
    else:
        filled = 0

    # 배치 생성: 카드 1장씩, 6주제 × 2방향 = 12개씩
    for i, card in enumerate(cards):
        # 이미 채워진 카드는 스킵
        empty_count = sum(1 for t in TOPICS for d in ["up", "rev"] if not card["meanings"][t][d])
        if empty_count == 0:
            continue

        batch = []
        for topic in TOPICS:
            for direction in ["up", "rev"]:
                if not card["meanings"][topic][direction]:
                    batch.append((card, topic, direction))

        if not batch:
            continue

        print(f"[{i+1}/{len(cards)}] {card['name']} ({card.get('name_ko', '')}) - {len(batch)} meanings...")

        prompt = build_batch_prompt(batch)
        result = await generate_with_gemini(prompt)

        # JSON 파싱
        try:
            text = result.strip()
            if not text:
                print("  WARNING: Empty response from API, retrying...")
                await asyncio.sleep(3)
                result = await generate_with_gemini(prompt)
                text = result.strip()
            if not text:
                print("  ERROR: Still empty after retry, skipping card")
                continue
            # ```json ... ``` 감싸진 경우 처리
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0]
            # JSON 배열이 아닌 경우 감싸기
            text = text.strip()
            if not text.startswith("["):
                text = "[" + text + "]"
            meanings = json.loads(text)

            for m in meanings:
                topic = m.get("topic", "")
                direction = m.get("direction", "")
                meaning_text = m.get("text", "")
                if topic in card["meanings"] and direction in card["meanings"][topic]:
                    card["meanings"][topic][direction] = meaning_text

            filled_now = sum(1 for t in TOPICS for d in ["up", "rev"] if card["meanings"][t][d])
            print(f"  → {filled_now}/12 filled")

        except (json.JSONDecodeError, KeyError) as e:
            print(f"  ⚠️ Parse error: {e}")
            print(f"  Raw: {result[:200]}")

        # 중간 저장
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(cards, f, ensure_ascii=False, indent=2)

        # Rate limit
        await asyncio.sleep(1)

    # 최종 통계
    total = len(cards) * len(TOPICS) * 2
    filled = sum(1 for c in cards for t in TOPICS for d in ["up", "rev"] if c["meanings"][t][d])
    print(f"\nDone! {filled}/{total} meanings generated → {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
