# 개발자 플레이북 — TGPoke Bot 회고록

> 바이브 코딩 200시간, 포켓몬 수집/배틀/거래 텔레그램 봇을 만들면서 쌓은
> 설계 철학, AI 협업 워크플로우, 게임 디자인 패턴, 기술적 교훈을 정리한 문서.
> 차기작 기획 및 리서치에 활용 목적.

---

## 목차
1. [프로젝트 개요](#1-프로젝트-개요)
2. [게임 설계 철학](#2-게임-설계-철학)
3. [아키텍처 패턴](#3-아키텍처-패턴)
4. [AI 협업 워크플로우](#4-ai-협업-워크플로우)
5. [경제 시스템 설계](#5-경제-시스템-설계)
6. [배틀 & 밸런싱](#6-배틀--밸런싱)
7. [유저 세분화 & 리텐션](#7-유저-세분화--리텐션)
8. [대시보드 & 분석](#8-대시보드--분석)
9. [인프라 & 운영](#9-인프라--운영)
10. [실수 & 교훈](#10-실수--교훈)
11. [재사용 가능한 레시피](#11-재사용-가능한-레시피)
12. [차기작 체크리스트](#12-차기작-체크리스트)

---

## 1. 프로젝트 개요

| 항목 | 값 |
|------|-----|
| 이름 | TGPoke Bot (텔레그램 포켓몬 봇) |
| 기간 | 2026.01 말 ~ 현재 (약 6주) |
| 스택 | Python, python-telegram-bot, PostgreSQL, Flask, Oracle Cloud VM |
| 규모 | 521마리, 핸들러 12개, 서비스 6개, 대시보드 SPA |
| 유저 | DAU 76~126, MAU ~182, 활성 채팅방 32개 |
| 개발 방식 | 바이브 코딩 (Claude Code 협업) |

### 핵심 루프
```
아케이드 포획 (30초 루프)
  ↓
일반방 스폰 (2시간+)
  ↓
팀 빌딩 + 배틀 + 토너먼트 (22시)
  ↓
육성 + 진화 + 교환 + 합성
  ↓
도감 수집 → 이로치 → 시즌 랭킹
```

---

## 2. 게임 설계 철학

### 2.1 핵심 원칙

**"모든 등급에 가치를 부여하라"**
- 코스트 시스템(팀 COST 18 제한)으로 커먼/레어도 전략적 가치 확보
- 전설만 강한 게임 → 팀 조합이 중요한 게임으로 전환
- 결과: 거래소에서 커먼/레어 거래량 증가

**"희소성은 콘텐츠다"**
- 이로치(색이 다른 포켓몬) = 수집 엔드게임
- 자연 스폰 10%, 강제 스폰 2%, 아케이드 1% → 채널별 차별화
- 초전설 1.5% 스폰 → "나왔다!" 한 마디가 채팅방 활성화 트리거

**"심야 유저를 보상하라"**
- 02~05시 심야 보너스: 에픽 이상 출현률 상승
- 결과: 새벽 활성 유저층 형성 → DAU 분산

**"단계적 콘텐츠 게이팅"**
- Gen 1→2→3 순차 추가 (콘텐츠 소진 방지)
- 시스템도 단계 오픈: 포획→배틀→토너먼트→랭크전→거래소→합성

### 2.2 밸런싱 프레임워크

```
변경 전 체크리스트:
1. 이 변경이 어떤 유저 세그먼트에 영향을 주는가?
2. 경제(BP 인플레이션)에 미치는 영향은?
3. 기존 유저 자산 가치가 훼손되는가?
4. 되돌리기 쉬운가? (config만 바꾸면 되는가 vs DB 변경)
```

### 2.3 스폰/포획 확률 변천사

| 버전 | 커먼 | 레어 | 에픽 | 전설 | 변경 이유 |
|------|------|------|------|------|---------|
| v1.0 | 50% | 30% | 15% | 5% | 초기 설정 |
| v1.5 | 35% | 21% | 31% | 10% | 에픽/전설 3배 부스트 (유저 요청) |
| v2.3 | 49.5% | 30% | 15% | 4% | 코스트 시스템 도입 → 커먼/레어 가치 상승 → 롤백 |

**교훈**: 유저 요청으로 확률을 올렸다가, 시스템 설계(코스트)로 자연스럽게 되돌림.
확률보다 시스템 설계가 우선.

---

## 3. 아키텍처 패턴

### 3.1 레이어 분리 (가장 중요한 결정)

```
handlers/     ← 텔레그램 I/O만 (입력 파싱 + 응답 포맷팅)
services/     ← 비즈니스 로직 (배틀 계산, 스폰, 토너먼트)
database/     ← 쿼리만 (앱 로직 없음)
models/       ← 정적 데이터 (포켓몬 스탯, 스킬)
utils/        ← 공유 헬퍼 (이모지, 배틀 계산, 카드 생성)
config.py     ← 모든 설정값 (한 곳에서 밸런싱)
```

**왜 이렇게 했나**: 배틀 로직을 handlers/에 넣었다가 토너먼트/랭크전에서 재사용 불가 → services/로 분리.
핸들러는 "번역기"일 뿐, 게임 로직을 모른다.

**재사용 포인트**:
- `battle_service._resolve_battle()` → 일반배틀, 토너먼트, 랭크전 모두 동일 엔진 사용
- `spawn_service.roll_rarity()` → 일반 스폰, 강제 스폰, 아케이드 모두 동일 확률 엔진

### 3.2 설정 중앙화 (config.py)

모든 밸런스 수치를 config.py 한 곳에 모음:
- 스폰 확률, 포획률, 배틀 공식 상수, BP 비용
- 커스텀 이모지 ID, 등급 이름, 등급 색상
- 서비스 상수 (쿨타임, 제한, 배수)

**장점**: 밸런스 패치 = config.py만 수정. 로직 변경 없음.

### 3.3 커스텀 이모지 시스템

```python
# config.py — 이모지 ID 등록
ICON_CUSTOM_EMOJI = {"battle": "6143344370625026850", ...}  # 45+ 아이콘
RARITY_CUSTOM_EMOJI = {"epic": "6141022159117492116", ...}
TYPE_CUSTOM_EMOJI = {"fire": "6143060735279766934", ...}
BALL_CUSTOM_EMOJI = {"pokeball": "6143151702687095487", ...}

# utils/helpers.py — 헬퍼 함수
def icon_emoji(key): ...  # → '<tg-emoji emoji-id="ID">fallback</tg-emoji>'
def type_badge(pokemon_id): ...  # → 듀얼타입 이모지
def rarity_badge(rarity): ...  # → 등급 색상 + 라벨

# 역매핑 시스템 (하위호환)
_TITLE_NAME_TO_ICON = {"포켓몬마스터": "pikachu", ...}
# DB에 옛날 이모지("🎯") 저장 → 표시 시 커스텀 이모지로 자동 변환
```

**규칙**:
- `parse_mode="HTML"` 필수 (커스텀 이모지 있는 모든 메시지)
- InlineKeyboardButton 라벨에는 커스텀 이모지 불가 → 기본 이모지 사용
- `query.answer()` 팝업에도 불가

### 3.4 한국어 명령어 처리

```python
# ❌ 안 됨 — CommandHandler는 한국어 지원 안 함
CommandHandler("ㅊ", catch_handler)

# ✅ 됨 — MessageHandler + 필터
MessageHandler(filters.TEXT & filters.Regex(r"^ㅊ$"), catch_handler)
```

이거 모르고 구현했다가 한 번 터짐. **한국어 명령어는 반드시 MessageHandler**.

---

## 4. AI 협업 워크플로우

### 4.1 Claude Code 프로젝트 구조

```
CLAUDE.md                    ← 프로젝트 "북극성" (필수)
.claude/
├── skills/                  ← 재사용 워크플로우 레시피
│   ├── deploy.md            ← 배포 절차
│   ├── pr.md                ← PR 생성/머지
│   └── custom-emoji.md      ← 이모지 추가 절차
├── settings.local.json      ← 로컬 설정
└── launch.json              ← 개발 서버 설정
handlers/CLAUDE.md           ← "한국어 명령어 주의!"
services/CLAUDE.md           ← "battle_service 수정 시 토너먼트/랭크전 영향"
database/CLAUDE.md           ← "스키마 변경 시 마이그레이션 필수"
dashboard/CLAUDE.md          ← "index.html 5000줄 SPA"
memory/MEMORY.md             ← AI가 관리하는 지식 베이스
```

### 4.2 효과적인 AI 협업 규칙

1. **절대 자동 배포하지 않는다** — 항상 확인 먼저
2. **예시 출력을 먼저 보여준다** — UI 변경 전 미리보기
3. **사이드이펙트를 기록한다** — 뭔가 수정했는데 다른 데서 터지면 MEMORY.md에 기록
4. **위험 폴더에 경고판을 세운다** — 폴더별 CLAUDE.md
5. **반복 작업은 스킬로 만든다** — .claude/skills/

### 4.3 AI에게 알려줘야 할 것 (프레임워크)

| 요소 | 질문 | 해결 파일 |
|------|------|---------|
| WHY | 이 시스템이 뭘 하는 거야? | CLAUDE.md |
| WHERE | 파일이 어디 있어? | CLAUDE.md (repo map) |
| RULES | 뭘 하면 안 돼? | CLAUDE.md + 폴더별 CLAUDE.md |
| HOW | 어떻게 작업해? | .claude/skills/ |
| GOTCHA | 어디서 터질 수 있어? | MEMORY.md (사이드이펙트 로그) |

### 4.4 AI 세션 간 지식 연결

```
세션 1: 배틀 공식 변경
  → MEMORY.md에 "battle_service 데미지 공식 변경, 토너먼트에 영향"

세션 2: 토너먼트 버그 신고
  → MEMORY.md 읽음 → "아, 배틀 공식이 바뀌었구나" → 빠르게 원인 파악
```

**핵심**: 프롬프트는 휘발성, 파일은 영구적. 중요한 결정은 반드시 파일로 남긴다.

---

## 5. 경제 시스템 설계

### 5.1 화폐 체계

| 화폐 | 획득처 | 소비처 | 인플레이션 위험 |
|------|--------|--------|--------------|
| BP (배틀포인트) | 배틀 승리, 미션, 출석 | 볼 구매, 교환비, 거래소 | ⚠️ 높음 |
| 마스터볼 | 토너먼트 우승, 미션 | 100% 포획 | 낮음 (희소) |
| 하이퍼볼 | 미션, 마볼 환불 | 3배 포획률 (20BP) | 중간 |
| 아케이드 티켓 | 이벤트 | 아케이드 접근 | 낮음 |

### 5.2 인플레이션 통제 전략

**소비처 설계가 핵심** — 화폐 획득만 늘리면 인플레이션.

```
Level 1 싱크: 하이퍼볼 (20BP/개) — 일상적 소비
Level 2 싱크: 교환 (150BP) — 중간 소비
Level 3 싱크: 거래소 수수료 (5%) — 대량 소비
Level 4 싱크: (예정) 던전 입장료, 시즌패스 — 엔드게임 소비
```

### 5.3 거래소 설계

```
등록: 최소 100BP, 최대 10건 동시 등록, 7일 만료
수수료: 판매가 5%
페이지: 5건/페이지, DM으로 관리
```

**교훈**: 거래소 없을 때 → 유저 간 직거래 → 사기 우려.
거래소 도입 후 → 시장 형성 → 가격 발견 → 유저 만족도 상승.

---

## 6. 배틀 & 밸런싱

### 6.1 데미지 공식

```
기본 데미지 = (공격 / 방어) × 기술 위력 × 명중률
최종 데미지 = 기본 × 타입상성 × 크리티컬 × 친밀도 보너스

타입상성: 유리 1.3x / 불리 0.7x
크리티컬: 10% 확률, 1.5x 데미지
친밀도: 레벨당 +4% (최대 +20%)
고유기술: 30% 확률 발동
```

### 6.2 코스트 시스템

```
팀 COST 제한: 18
전설 5 / 에픽 4 / 레어 3 / 커먼 2

가능한 조합 예시:
- 전설1 + 에픽1 + 레어3 = 5+4+9 = 18
- 에픽2 + 레어2 + 커먼1 = 8+6+2 = 16
- 커먼6 = 12 (COST 여유 → 약하지만 효율적)
```

**설계 의도**: "전설 6마리 팀" 불가 → 팀 조합의 다양성 강제.

### 6.3 배틀 연출 패턴

```python
# turn_data 구조
[
    {"type": "matchup", "c_name": "피카츄", "d_name": "파이리"},
    {"type": "turn", "turn_num": 1, "c_dmg": 45, "d_dmg": 32, "c_crit": "!!"},
    {"type": "ko", "dead_name": "파이리", "next_name": "거북왕"},
    {"type": "timeout"},  # 50턴 초과 시
]

# 토너먼트 연출 티어
16강 이하: 한 줄 요약
8강/4강: HP바 + 매치별 결과
결승: HP바 상세 턴 연출 + 교체 대사
```

---

## 7. 유저 세분화 & 리텐션

### 7.1 유저 세그먼트

| 유형 | 특성 | 리텐션 훅 |
|------|------|---------|
| 수집가 | 도감 완성이 목표 | 이로치, 시즌 한정 |
| 경쟁자 | 랭킹 1위가 목표 | 랭크전, 토너먼트 |
| 심야족 | 새벽에 활동 | 심야 보너스 |
| 캐주얼 | 간간이 참여 | 출석 보상, 뉴비 보호 |
| 소셜 | 채팅방 분위기 주도 | 게시판, 교환 |

### 7.2 리텐션 지표

| 지표 | 현재 | 목표 | 액션 |
|------|------|------|------|
| D+1 | ~40% | 50%+ | 튜토리얼 개선 |
| D+7 | ~15% | 30%+ | 일일 미션 보강 |
| D+30 | TBD | 15%+ | 시즌 시스템 도입 |

### 7.3 뉴비 보호

```python
# 처음 2마리는 100% 포획 보장
if total_catches < 2:
    roll, success = 0.0, True  # Newbie boost
```

**퍼널 분석**: 가입 → 첫 포획 사이에 48% 이탈.
튜토리얼 + 뉴비 부스트로 이 구간을 메움.

---

## 8. 대시보드 & 분석

### 8.1 대시보드 구조

```
dashboard/
├── server.py           ← Flask 라우트 (2000+ 줄)
├── templates/
│   └── index.html      ← SPA (5000+ 줄, HTML+CSS+JS 올인원)
└── CLAUDE.md           ← "5000줄 모놀리스 주의!"

URL: tgpoke.com (Cloudflare tunnel → port 8080)
인증: 텔레그램 로그인 위젯 → 세션 PostgreSQL 영속화
```

### 8.2 게시판 시스템

```
board_type: "notice" (관리자), "community" (유저)
기능: 글쓰기, 이미지, 댓글, 좋아요, 조회수
딥링킹: /board/notice, /board/community, /board/post/{id}
```

### 8.3 분석 데이터

수집 중인 지표:
- 스폰/포획 로그 (spawn_log)
- 배틀 턴 로그 (battles)
- 거래소 거래 내역
- 유저별 포획률, DAU, 채팅방별 활성도

---

## 9. 인프라 & 운영

### 9.1 서버 구성

```
Oracle Cloud VM (Always Free Tier)
├── 봇: systemd → pokemon-bot.service
├── 대시보드: Flask :8080 → Cloudflare Tunnel → tgpoke.com
├── DB: Supabase PostgreSQL (외부)
└── 로그: journalctl -u pokemon-bot -f
```

### 9.2 배포 절차

```bash
# 로컬
git push origin dev

# VM
ssh -i oracle_vm ubuntu@158.180.93.94
cd ~/pokemon-bot && git pull origin dev
sudo systemctl restart pokemon-bot
sudo journalctl -u pokemon-bot -f  # 로그 확인
```

### 9.3 장애 대응

```
1. journalctl로 에러 확인
2. 최근 커밋 확인 (git log --oneline -5)
3. config.py 변경이면 → 값만 롤백
4. 코드 변경이면 → git revert 또는 이전 커밋 체크아웃
5. DB 변경이면 → 마이그레이션 역방향 (신중하게)
```

---

## 10. 실수 & 교훈

### 10.1 "자동 머지 사건"
- **상황**: AI에게 "PR 만들어줘" → 자동 머지됨
- **결과**: 검증 안 된 코드가 main에 배포
- **교훈**: **배포/머지는 반드시 확인 후** (MEMORY.md에 영구 기록)
- **방지책**: CLAUDE.md 금지사항에 명시, AI 메모리에 등록

### 10.2 "커스텀 이모지 깨짐 사건"
- **상황**: InlineKeyboardButton에 커스텀 이모지 HTML 삽입
- **결과**: 버튼이 렌더링 안 됨 (텔레그램 제한)
- **교훈**: 버튼 라벨 = 기본 이모지만, 메시지 본문 = 커스텀 가능
- **방지책**: handlers/CLAUDE.md에 경고 명시

### 10.3 "배틀 공식 변경 → 토너먼트 깨짐"
- **상황**: battle_service 데미지 공식 수정
- **결과**: 토너먼트 결승 연출이 비정상 작동
- **교훈**: battle_service는 3곳에서 사용 (일반/토너먼트/랭크전)
- **방지책**: services/CLAUDE.md에 의존관계 명시

### 10.4 "포획률 제각각 사건"
- **상황**: config.py에 CATCH_RATES 있지만 실제로는 DB 개별값 사용
- **결과**: 커먼인데 15% 포획률인 포켓몬 존재, 유저 혼란
- **교훈**: "참고용" 코드와 "실사용" 코드를 명확히 구분
- **방지책**: config.py에 주석으로 "참고용, 실제는 DB" 명시

### 10.5 "한국어 CommandHandler 사건"
- **상황**: `CommandHandler("ㅊ", ...)` → 한국어 명령 인식 안 됨
- **결과**: 포획 명령이 작동 안 함
- **교훈**: python-telegram-bot의 CommandHandler는 영어만
- **방지책**: handlers/CLAUDE.md에 명시, MessageHandler 사용

---

## 11. 재사용 가능한 레시피

### 11.1 텔레그램 봇 프로젝트 시작 템플릿

```
project/
├── CLAUDE.md           ← AI 협업의 핵심
├── .claude/skills/     ← 배포, PR 등 워크플로우
├── config.py           ← 모든 설정 중앙화
├── main.py             ← 핸들러 등록 + 스케줄러
├── handlers/           ← 텔레그램 I/O (thin)
├── services/           ← 비즈니스 로직
├── database/
│   ├── connection.py   ← 커넥션 풀
│   ├── schema.py       ← 마이그레이션
│   └── queries.py      ← 쿼리 함수
├── models/             ← 정적 데이터
└── utils/              ← 공유 헬퍼
```

### 11.2 콜백 버튼 패턴

```python
# 1. 메인 핸들러 (메뉴 표시)
async def menu_handler(update, context):
    keyboard = [[InlineKeyboardButton("선택", callback_data="action:value")]]
    await update.message.reply_text("선택하세요", reply_markup=...)

# 2. 콜백 핸들러 (버튼 클릭 처리)
async def menu_callback(update, context):
    query = update.callback_query
    action, value = query.data.split(":")
    # 중복 클릭 방지
    # 처리 로직
    await query.edit_message_text(...)
```

### 11.3 마이그레이션 패턴

```python
async def migrate_something():
    pool = await get_db()
    # 이미 적용됐는지 확인 (멱등성)
    row = await pool.fetchrow("SELECT ... WHERE ...")
    if already_migrated:
        return False
    # 마이그레이션 실행
    await pool.execute("UPDATE ...")
    return count
```

### 11.4 커스텀 이모지 적용 패턴

```python
# config.py에 ID 등록
EMOJI = {"icon_name": "1234567890"}

# helpers.py에 헬퍼 함수
def emoji(key):
    eid = EMOJI.get(key)
    fallback = FALLBACK.get(key, "")
    if eid:
        return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'
    return fallback

# 사용 시 반드시 parse_mode="HTML"
await bot.send_message(chat_id, f"{emoji('battle')} 배틀 시작!", parse_mode="HTML")
```

---

## 12. 차기작 체크리스트

### 기획 단계
- [ ] 유저 세그먼트 정의 (최소 3개)
- [ ] 핵심 루프 설계 (30초 / 5분 / 1일 / 1주 루프)
- [ ] 화폐 체계 설계 (획득-소비 균형)
- [ ] 리텐션 훅 설계 (세그먼트별)
- [ ] 단계적 콘텐츠 게이팅 계획

### 설계 단계
- [ ] 레이어 분리 (handler / service / database)
- [ ] config.py 중앙화 (밸런스 수치 한 곳에)
- [ ] CLAUDE.md 작성 (프로젝트 북극성)
- [ ] 폴더별 CLAUDE.md (위험 구역 경고)
- [ ] .claude/skills/ (배포, PR 레시피)
- [ ] 마이그레이션 시스템 설계

### 개발 단계
- [ ] 뉴비 보호 시스템 (첫 N회 보장)
- [ ] 콜백 중복 클릭 방지
- [ ] 한국어 명령어 → MessageHandler
- [ ] 커스텀 이모지 시스템 구축
- [ ] 대시보드 분석 파이프라인

### 운영 단계
- [ ] systemd 서비스 등록
- [ ] 로그 모니터링 (journalctl)
- [ ] 패치노트 게시판
- [ ] MEMORY.md 사이드이펙트 추적
- [ ] 인플레이션 모니터링 대시보드

---

*"프롬프트는 일시적이고, 구조는 영구적이다."*
*"확률보다 시스템이 밸런스를 만든다."*
*"모든 등급에 가치를 부여하면, 모든 유저가 즐긴다."*
