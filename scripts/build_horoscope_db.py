"""
운세 해석 DB 자동 구축 스크립트.

Gemini 에이전트 2개 (생성자 + 검증자)가 티키타카하며 해석 품질을 올림.

사용법:
  python scripts/build_horoscope_db.py              # 전체 생성
  python scripts/build_horoscope_db.py --planet sun  # 태양만
  python scripts/build_horoscope_db.py --aspects     # 어스펙트만
  python scripts/build_horoscope_db.py --max-rounds 5  # 최대 개선 라운드

출력: data/horoscope_interpretations.json
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# ── 설정 ──

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "horoscope_interpretations.json"

PLANETS = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn"]
PLANET_KO = {
    "sun": "태양", "moon": "달", "mercury": "수성",
    "venus": "금성", "mars": "화성", "jupiter": "목성", "saturn": "토성",
}
PLANET_SYMBOLS = {
    "sun": "☉", "moon": "☽", "mercury": "☿",
    "venus": "♀", "mars": "♂", "jupiter": "♃", "saturn": "♄",
}

SIGNS = [
    {"name": "양자리", "en": "Aries", "symbol": "♈", "element": "불", "mode": "활동궁",
     "ruler": "화성", "trait": "충동적, 리더십, 에너지 과잉, 경쟁심"},
    {"name": "황소자리", "en": "Taurus", "symbol": "♉", "element": "땅", "mode": "고정궁",
     "ruler": "금성", "trait": "안정 추구, 소유욕, 감각적 쾌락, 완고함"},
    {"name": "쌍둥이자리", "en": "Gemini", "symbol": "♊", "element": "바람", "mode": "변통궁",
     "ruler": "수성", "trait": "호기심, 소통, 변덕, 멀티태스킹"},
    {"name": "게자리", "en": "Cancer", "symbol": "♋", "element": "물", "mode": "활동궁",
     "ruler": "달", "trait": "모성, 감정 기복, 방어적, 가정 중심"},
    {"name": "사자자리", "en": "Leo", "symbol": "♌", "element": "불", "mode": "고정궁",
     "ruler": "태양", "trait": "자존심, 관대함, 주목받고 싶음, 창의력"},
    {"name": "처녀자리", "en": "Virgo", "symbol": "♍", "element": "땅", "mode": "변통궁",
     "ruler": "수성", "trait": "분석력, 완벽주의, 건강 민감, 비판적"},
    {"name": "천칭자리", "en": "Libra", "symbol": "♎", "element": "바람", "mode": "활동궁",
     "ruler": "금성", "trait": "조화, 우유부단, 미적 감각, 관계 지향"},
    {"name": "전갈자리", "en": "Scorpio", "symbol": "♏", "element": "물", "mode": "고정궁",
     "ruler": "명왕성/화성", "trait": "집요함, 비밀주의, 통찰력, 질투"},
    {"name": "사수자리", "en": "Sagittarius", "symbol": "♐", "element": "불", "mode": "변통궁",
     "ruler": "목성", "trait": "자유, 낙관, 솔직함, 무책임"},
    {"name": "염소자리", "en": "Capricorn", "symbol": "♑", "element": "땅", "mode": "활동궁",
     "ruler": "토성", "trait": "야망, 인내, 현실주의, 감정 억제"},
    {"name": "물병자리", "en": "Aquarius", "symbol": "♒", "element": "바람", "mode": "고정궁",
     "ruler": "천왕성/토성", "trait": "독립, 혁신, 반항, 박애주의"},
    {"name": "물고기자리", "en": "Pisces", "symbol": "♓", "element": "물", "mode": "변통궁",
     "ruler": "해왕성/목성", "trait": "직감, 공감, 현실도피, 예술적"},
]

ASPECT_TYPES = {
    "conjunction": {"name": "합(☌)", "angle": 0, "nature": "강화/융합",
                    "desc": "두 행성의 에너지가 합쳐져 강렬하게 작용"},
    "sextile": {"name": "육합(⚹)", "angle": 60, "nature": "조화/기회",
                "desc": "부드러운 협력, 기회가 열림"},
    "square": {"name": "사각(□)", "angle": 90, "nature": "긴장/도전",
               "desc": "갈등과 마찰, 성장의 기회"},
    "trine": {"name": "삼합(△)", "angle": 120, "nature": "조화/행운",
              "desc": "자연스러운 흐름, 재능이 발휘됨"},
    "opposition": {"name": "대립(☍)", "angle": 180, "nature": "대립/균형",
                   "desc": "양극단 사이 균형, 타인과의 관계가 핵심"},
}

# 주요 행성쌍 (모든 조합 대신 의미 있는 것만)
KEY_ASPECT_PAIRS = [
    ("sun", "moon"), ("sun", "mercury"), ("sun", "venus"),
    ("sun", "mars"), ("sun", "jupiter"), ("sun", "saturn"),
    ("moon", "mercury"), ("moon", "venus"), ("moon", "mars"),
    ("moon", "jupiter"), ("moon", "saturn"),
    ("mercury", "venus"), ("mercury", "mars"),
    ("venus", "mars"), ("venus", "jupiter"), ("venus", "saturn"),
    ("mars", "jupiter"), ("mars", "saturn"),
    ("jupiter", "saturn"),
]


# ── Gemini API ──

async def call_gemini(system_prompt: str, user_prompt: str, temperature: float = 0.7) -> str | None:
    """Gemini API 호출."""
    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY not set")
        return None

    payload = {
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 8192,
            "topP": 0.9,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    headers = {"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GEMINI_URL, json=payload, headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    print(f"  Gemini API error {resp.status}: {text[:200]}")
                    return None
                data = await resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    return "\n".join(p["text"] for p in parts if "text" in p).strip()
    except Exception as e:
        print(f"  Gemini API exception: {e}")
    return None


# ── 생성 에이전트 ──

GENERATOR_SYSTEM = """당신은 30년 경력의 서양 점성술 전문가입니다. Robert Hand, William Lilly, Liz Greene의 저서를 기반으로 행성 트랜짓 해석을 작성합니다.

## 프리미엄 운세 해석의 필수 요소 (Cafe Astrology, Co-Star급)
1. **원형적 언어**: "정복하려는 욕구가 솟구친다", "타인이 자신의 거울이 된다" 같은 심층 심리/원형 표현. 단순 키워드 나열 금지.
2. **점성술적 근거**: dignity 상태, 원소 조합, 모드가 "왜" 그런 에너지를 만드는지 설명.
3. **다른 별자리와 대비**: "이전 별자리에서는 ~했지만, 이 별자리에서는 ~" 식의 맥락 전환.
4. **구체적 그림자**: "주의하세요" 수준이 아닌, "소유욕", "수동공격", "자기기만" 등 구체적 심리 패턴 명시.
5. **행동 가능한 조언**: "좋은 시기입니다" 수준이 아닌, 무엇을 하고 무엇을 피해야 하는지.

## 해석 분량: 4~5문장, 80~120단어

## 톤 배분
- domicile/exaltation: 긍정 비중 높되 그림자도 명시
- detriment/fall: 도전/그림자 비중 높되 긍정적 활용법도 제시
- neutral: 균형잡힌 서술

## shadow/advice 작성 규칙 (중요!)
- shadow는 반드시 **구체적 행동 결과**를 포함할 것. "주의해야 합니다" 금지.
  - BAD: "지나친 충동은 문제를 일으킬 수 있습니다"
  - GOOD: "회의 중 상대 말을 끊고 자기 주장만 밀어붙여 팀원들의 반감을 사거나, 충분한 검토 없이 계약서에 서명해 재정적 손실을 볼 수 있습니다"
- advice는 shadow에서 언급한 **구체적 문제에 대한 직접적 해결책**일 것.
  - BAD: "균형 잡힌 시각을 유지하세요"
  - GOOD: "중요한 결정은 최소 24시간 보류하고, 신뢰할 수 있는 동료에게 의견을 구하세요"

## 금지 표현
- "에너지가 높아집니다", "좋은 시기입니다", "주의가 필요합니다" 같은 뜬구름 표현
- 12별자리에서 같은 문장 구조 반복 (예: 매번 "~의 특성상 ~가 강해집니다")
- 연애/직장/재물/건강 중 해당 행성의 영역을 자연스럽게 녹여 넣되, 카테고리 라벨 금지.

## 출력 형식
반드시 유효한 JSON으로만 출력하세요. 마크다운 코드블록이나 설명 없이 순수 JSON만.
"""

CRITIC_SYSTEM = """당신은 서양 점성술 학술 검증관이자 프리미엄 운세 서비스 에디터입니다.
Cafe Astrology, Co-Star 수준의 전문 운세를 기준으로 냉정하게 평가합니다.

## 검증 기준 (각 항목 2점, 총 10점)
1. **점성술 정확성 (2점)**: dignity/detriment/exaltation/fall이 올바르게 반영됐는가? domicile/exaltation에서 긍정 비중이 높고, detriment/fall에서 도전 비중이 높은가?
2. **원형적 깊이 (2점)**: 단순 키워드 나열이 아닌, 행성-별자리 조합의 본질적 역학이 드러나는가? "왜" 그런 에너지가 발생하는지 점성술적 근거가 있는가?
3. **그림자/도전 (2점)**: 부정적 측면이 구체적인가? "주의하세요" 수준이 아닌, 실제 어떤 문제가 생기는지 서술됐는가?
4. **실용성 (2점)**: 구체적 행동 조언이 있는가? "좋은 시기입니다" 수준이 아닌, 무엇을 하고 무엇을 피해야 하는지?
5. **차별화/중복 (2점)**: 12별자리 해석이 각각 독자적인가? 같은 표현/구조가 반복되지 않는가?

## 추가 체크
- 각 해석이 4~5문장, 80~120단어인가? 너무 짧으면 감점.
- "shadow" 필드가 구체적인가? "advice" 필드에 실행 가능한 조언이 있는가?

## 출력 형식
반드시 유효한 JSON으로만 출력하세요. 마크다운 코드블록이나 설명 없이 순수 JSON만.
{
  "overall_score": 1~10,
  "issues": [
    {"sign": "별자리명", "problem": "문제 설명", "suggestion": "개선 제안"}
  ],
  "passed": true/false
}
passed=true는 overall_score >= 9일 때만. 8점 이하는 반드시 false."""


async def generate_planet_transits(planet: str, previous_feedback: str = "") -> dict | None:
    """한 행성의 12별자리 트랜짓 해석 생성."""
    planet_ko = PLANET_KO[planet]
    planet_sym = PLANET_SYMBOLS[planet]

    # dignity 정보
    dignity_info = _get_dignity_info(planet)

    signs_info = "\n".join(
        f"- {s['name']}({s['en']}): 원소={s['element']}, 모드={s['mode']}, 지배행성={s['ruler']}, 특성={s['trait']}"
        for s in SIGNS
    )

    feedback_section = ""
    if previous_feedback:
        feedback_section = f"\n\n## 이전 검증 피드백 (반드시 반영할 것)\n{previous_feedback}"

    prompt = f"""{planet_ko}({planet_sym})이 12별자리 각각에 위치할 때의 트랜짓 해석을 작성하세요.

## {planet_ko}의 dignity 정보
{dignity_info}

## 12별자리 정보
{signs_info}
{feedback_section}

## 참고: Cafe Astrology급 프리미엄 해석 스타일 (이 수준으로 작성할 것)

태양-양자리(exaltation) 예시:
"정복하려는 욕구가 강렬하게 솟구칩니다. 태양이 고양의 자리인 양자리에서 빛나면, 충동적이되 용감하고, 단순하되 개척적인 에너지가 전면에 나섭니다. 과거를 뒤돌아볼 여유 없이 새로운 사이클에 뛰어드는 시기이며, 실패해도 빠르게 털고 일어납니다. 직장에서 주도권을 쥐거나 미뤄둔 프로젝트에 착수하기에 이상적이지만, 앞만 보고 달리다 장기적 결과를 간과하는 근시안이 이 배치의 그림자입니다."

태양-전갈자리(neutral) 예시:
"전갈자리 태양의 인도 원칙은 '나는 갈망한다'입니다. 피상적인 것은 용납되지 않으며, 모든 것의 이면을 파고드는 집요한 에너지가 지배합니다. 천칭자리에서 평등과 공정을 추구했다면, 전갈자리는 본능적으로 삶이 공정하지 않음을 압니다. 복잡한 심리 문제나 숨겨진 진실을 파헤치는 데 탁월하며, 금전적 회복이나 깊은 관계 재건에도 유리합니다. 그러나 질투, 집착, 조종 욕구가 이 강렬함의 어두운 이면입니다."

태양-물병자리(detriment) 예시:
"기존의 질서와 구조가 갑자기 답답하게 느껴집니다. 태양이 손상의 자리인 물병자리에 놓이면, 개인의 자아 표현보다 혁신과 독립에 에너지가 쏠리며 기존 권위와 충돌합니다. 독창적인 사고와 사회적 이상 추구에는 뛰어나지만, 개인적 인정에 대한 욕구가 억눌려 따뜻한 관계 형성에 어려움을 겪습니다. 남들과 다르다는 사실은 인정하되, 고립과 독립을 혼동하지 않도록 경계하세요."

## 출력: JSON object
{{
  "{SIGNS[0]['en'].lower()}": {{
    "keyword": "핵심 키워드 (2~3단어)",
    "tone": "positive|neutral|negative|mixed",
    "dignity": "domicile|exaltation|detriment|fall|neutral",
    "interpretation": "4~5문장 해석 (80~120단어). 위 예시 수준의 깊이와 구체성 필수.",
    "shadow": "이 배치의 그림자/도전 (1문장)",
    "advice": "구체적 행동 조언 (1문장)"
  }},
  ...나머지 11개 별자리
}}"""

    result = await call_gemini(GENERATOR_SYSTEM, prompt, temperature=0.6)
    if not result:
        return None
    return _parse_json(result)


async def critique_planet_transits(planet: str, transits: dict) -> dict | None:
    """12별자리 해석을 검증."""
    planet_ko = PLANET_KO[planet]
    dignity_info = _get_dignity_info(planet)

    transits_text = json.dumps(transits, ensure_ascii=False, indent=2)

    prompt = f"""{planet_ko}의 12별자리 트랜짓 해석을 검증하세요.

## {planet_ko}의 dignity 정보
{dignity_info}

## 검증 대상
{transits_text}

모든 12별자리가 포함됐는지, 점성술적으로 정확한지, 별자리별로 충분히 차별화됐는지 검증하세요."""

    result = await call_gemini(CRITIC_SYSTEM, prompt, temperature=0.3)
    if not result:
        return None
    return _parse_json(result)


async def generate_aspect_interpretations(previous_feedback: str = "") -> dict | None:
    """주요 행성쌍 × 어스펙트 해석 생성."""

    pairs_info = "\n".join(
        f"- {PLANET_KO[p1]}({PLANET_SYMBOLS[p1]}) + {PLANET_KO[p2]}({PLANET_SYMBOLS[p2]})"
        for p1, p2 in KEY_ASPECT_PAIRS
    )
    aspects_info = "\n".join(
        f"- {v['name']}: {v['desc']}"
        for v in ASPECT_TYPES.values()
    )

    feedback_section = ""
    if previous_feedback:
        feedback_section = f"\n\n## 이전 검증 피드백 (반드시 반영할 것)\n{previous_feedback}"

    prompt = f"""주요 행성쌍의 어스펙트 해석을 작성하세요.

## 행성쌍
{pairs_info}

## 어스펙트 종류
{aspects_info}
{feedback_section}

## 참고: Cafe Astrology급 어스펙트 해석 스타일 (이 수준으로 작성할 것)
태양☌목성(합): "활력이 넘치고 자신감이 구축되는 시기입니다. 관대하고 낙관적이며 사교적인 면이 부각되고, 사업을 키우거나 중요한 관계를 발전시키기에 적합합니다. 다만 자신의 능력을 과대평가하거나 무리한 약속을 하지 않도록 경계하세요."
태양□화성(사각): "계절에 관계없이 '봄의 열병'에 걸립니다. 뭔가를 하고 싶은 안절부절한 욕구가 있지만 명확한 목표 없이 충동적으로 행동하기 쉽습니다. 반응이 방어적이거나 경쟁적으로 흐르며, 신체적으로도 사고에 취약해집니다."
태양△토성(삼합): "현실에 단단히 발을 딛고 있습니다. 특정 과제에 집중해서 진전을 이루기 쉬우며, 속도는 느리지만 꾸준합니다. 현실을 직시하려는 의지가 생기고, 상식적인 판단이 빛을 발합니다."

## 출력: JSON object
{{
  "sun_moon": {{
    "conjunction": "2~3문장 해석. 감정묘사+행동지침+주의사항.",
    "sextile": "2~3문장 해석",
    "square": "2~3문장 해석",
    "trine": "2~3문장 해석",
    "opposition": "2~3문장 해석"
  }},
  ...나머지 행성쌍 (총 {len(KEY_ASPECT_PAIRS)}쌍 전부 포함할 것)
}}"""

    result = await call_gemini(GENERATOR_SYSTEM, prompt, temperature=0.6)
    if not result:
        return None
    return _parse_json(result)


# ── 유틸 ──

def _get_dignity_info(planet: str) -> str:
    """행성의 dignity/detriment/exaltation/fall 정보."""
    dignity_map = {
        "sun": "domicile=사자자리, exaltation=양자리, detriment=물병자리, fall=천칭자리",
        "moon": "domicile=게자리, exaltation=황소자리, detriment=염소자리, fall=전갈자리",
        "mercury": "domicile=쌍둥이자리+처녀자리, exaltation=처녀자리, detriment=사수자리+물고기자리, fall=물고기자리",
        "venus": "domicile=황소자리+천칭자리, exaltation=물고기자리, detriment=전갈자리+양자리, fall=처녀자리",
        "mars": "domicile=양자리+전갈자리, exaltation=염소자리, detriment=천칭자리+황소자리, fall=게자리",
        "jupiter": "domicile=사수자리+물고기자리, exaltation=게자리, detriment=쌍둥이자리+처녀자리, fall=염소자리",
        "saturn": "domicile=염소자리+물병자리, exaltation=천칭자리, detriment=게자리+사자자리, fall=양자리",
    }
    return dignity_map.get(planet, "")


def _parse_json(text: str) -> dict | None:
    """Gemini 응답에서 JSON 추출."""
    # 코드블록 제거
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # 첫 줄(```json)과 마지막 줄(```) 제거
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 부분 JSON 시도
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        print(f"  JSON parse failed: {text[:200]}...")
        return None


def _load_existing() -> dict:
    """기존 결과 로드."""
    if OUTPUT_PATH.exists():
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"transits": {}, "aspects": {}}


def _save(data: dict):
    """결과 저장."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  💾 Saved: {OUTPUT_PATH}")


# ── 메인 루프 ──

async def build_planet(planet: str, max_rounds: int = 3) -> dict | None:
    """한 행성의 해석을 생성→검증→개선 루프."""
    print(f"\n{'='*60}")
    print(f"🪐 {PLANET_KO[planet]}({PLANET_SYMBOLS[planet]}) 해석 생성 시작")
    print(f"{'='*60}")

    feedback = ""
    for round_num in range(1, max_rounds + 1):
        print(f"\n── Round {round_num}/{max_rounds} ──")

        # 생성
        print(f"  🤖 생성 에이전트: {PLANET_KO[planet]} × 12별자리 해석 작성 중...")
        transits = await generate_planet_transits(planet, feedback)
        if not transits:
            print("  ❌ 생성 실패")
            continue

        sign_count = len(transits)
        print(f"  ✅ {sign_count}개 별자리 해석 생성 완료")

        # 검증
        print(f"  🔍 검증 에이전트: 품질 검증 중...")
        critique = await critique_planet_transits(planet, transits)
        if not critique:
            print("  ⚠️ 검증 실패 — 생성 결과 그대로 사용")
            return transits

        score = critique.get("overall_score", 0)
        passed = critique.get("passed", False)
        issues = critique.get("issues", [])

        print(f"  📊 점수: {score}/10 | 통과: {'✅' if passed else '❌'}")
        if issues:
            for issue in issues[:5]:
                print(f"     ⚠️ [{issue.get('sign', '?')}] {issue.get('problem', '')}")

        if passed:
            print(f"  🎉 검증 통과! (Round {round_num})")
            return transits

        # 피드백 정리
        feedback = "\n".join(
            f"- {issue.get('sign', '?')}: {issue.get('problem', '')} → {issue.get('suggestion', '')}"
            for issue in issues
        )
        print(f"  🔄 피드백 반영하여 재생성...")

    print(f"  ⚠️ {max_rounds}라운드 소진 — 마지막 결과 사용")
    return transits


async def generate_aspect_batch(pairs: list[tuple], previous_feedback: str = "") -> dict | None:
    """행성쌍 배치의 어스펙트 해석 생성."""
    pairs_info = "\n".join(
        f"- {PLANET_KO[p1]}({PLANET_SYMBOLS[p1]}) + {PLANET_KO[p2]}({PLANET_SYMBOLS[p2]})"
        for p1, p2 in pairs
    )
    aspects_info = "\n".join(
        f"- {v['name']}: {v['desc']}"
        for v in ASPECT_TYPES.values()
    )

    feedback_section = ""
    if previous_feedback:
        feedback_section = f"\n\n## 이전 검증 피드백 (반드시 반영할 것)\n{previous_feedback}"

    pair_keys = [f"{p1}_{p2}" for p1, p2 in pairs]
    example_key = pair_keys[0]

    prompt = f"""아래 행성쌍의 어스펙트 해석을 작성하세요.

## 행성쌍
{pairs_info}

## 어스펙트 종류
{aspects_info}
{feedback_section}

## 참고: Cafe Astrology급 어스펙트 해석 스타일 (이 수준으로 작성할 것)
태양☌목성(합): "활력이 넘치고 자신감이 구축되는 시기입니다. 관대하고 낙관적이며 사교적인 면이 부각되고, 사업을 키우거나 중요한 관계를 발전시키기에 적합합니다. 다만 자신의 능력을 과대평가하거나 무리한 약속을 하지 않도록 경계하세요."
태양□화성(사각): "계절에 관계없이 '봄의 열병'에 걸립니다. 뭔가를 하고 싶은 안절부절한 욕구가 있지만 명확한 목표 없이 충동적으로 행동하기 쉽습니다. 반응이 방어적이거나 경쟁적으로 흐르며, 신체적으로도 사고에 취약해집니다."

## 출력: JSON object (정확히 {len(pairs)}쌍)
{{
  "{example_key}": {{
    "conjunction": "2~3문장 해석. 감정묘사+행동지침+주의사항.",
    "sextile": "2~3문장 해석",
    "square": "2~3문장 해석",
    "trine": "2~3문장 해석",
    "opposition": "2~3문장 해석"
  }},
  ...나머지 {len(pairs)-1}쌍
}}"""

    result = await call_gemini(GENERATOR_SYSTEM, prompt, temperature=0.6)
    if not result:
        return None
    return _parse_json(result)


async def build_aspects(max_rounds: int = 3) -> dict | None:
    """어스펙트 해석 생성 — 배치 분할."""
    print(f"\n{'='*60}")
    print(f"✨ 어스펙트 해석 생성 시작 ({len(KEY_ASPECT_PAIRS)}쌍 × 5종)")
    print(f"{'='*60}")

    # 6~7쌍씩 3배치로 분할 (JSON 잘림 방지)
    batch_size = 7
    batches = []
    for i in range(0, len(KEY_ASPECT_PAIRS), batch_size):
        batches.append(KEY_ASPECT_PAIRS[i:i + batch_size])

    all_aspects = {}
    for batch_idx, batch in enumerate(batches, 1):
        print(f"\n── 배치 {batch_idx}/{len(batches)} ({len(batch)}쌍) ──")

        for round_num in range(1, max_rounds + 1):
            print(f"  🤖 Round {round_num}: 생성 중...")
            result = await generate_aspect_batch(batch)
            if result:
                all_aspects.update(result)
                print(f"  ✅ {len(result)}쌍 완료")
                break
            print(f"  ❌ 실패, 재시도...")
        else:
            print(f"  ⚠️ 배치 {batch_idx} 최종 실패")

    if all_aspects:
        print(f"\n🎉 어스펙트 해석 완료! ({len(all_aspects)}/{len(KEY_ASPECT_PAIRS)}쌍)")
    return all_aspects if all_aspects else None


async def main():
    parser = argparse.ArgumentParser(description="운세 해석 DB 구축")
    parser.add_argument("--planet", help="특정 행성만 (sun/moon/mercury/venus/mars/jupiter/saturn)")
    parser.add_argument("--aspects", action="store_true", help="어스펙트만 생성")
    parser.add_argument("--max-rounds", type=int, default=3, help="최대 개선 라운드 (기본: 3)")
    args = parser.parse_args()

    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY 환경변수를 설정하세요.")
        sys.exit(1)

    data = _load_existing()

    if args.aspects:
        aspects = await build_aspects(args.max_rounds)
        if aspects:
            data["aspects"] = aspects
            _save(data)
        return

    planets_to_build = [args.planet] if args.planet else PLANETS
    for planet in planets_to_build:
        if planet not in PLANETS:
            print(f"❌ 알 수 없는 행성: {planet}")
            continue

        transits = await build_planet(planet, args.max_rounds)
        if transits:
            data["transits"][planet] = transits
            _save(data)  # 행성마다 중간 저장
            print(f"  ✅ {PLANET_KO[planet]} 저장 완료")

    # 어스펙트도 전체 모드일 때 생성
    if not args.planet:
        aspects = await build_aspects(args.max_rounds)
        if aspects:
            data["aspects"] = aspects
            _save(data)

    print(f"\n{'='*60}")
    print(f"🎉 완료! 총 {len(data.get('transits', {}))}개 행성 + 어스펙트")
    print(f"📁 {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
