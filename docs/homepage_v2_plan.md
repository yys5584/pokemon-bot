# 홈페이지 V2 기획서 — 텔레그램 연동 + 내 포켓몬 + AI 팀 시뮬레이터

## 1. 개요

현재 대시보드(홈페이지)는 **공용 통계 뷰어**임. 개인 데이터 없음.
→ 텔레그램 로그인 연동으로 "내 포켓몬" 개인 뷰 + AI 팀 추천 기능 추가.

---

## 2. 핵심 기능 3가지

### 2-1. Connect (텔레그램 로그인)

**현재:** 새로고침 버튼 (헤더 우측)
**변경:** `Connect` 버튼 → 클릭 시 텔레그램 로그인

```
[로그인 전]  헤더: Pokemon Dashboard          [🔗 Connect]
[로그인 후]  헤더: Pokemon Dashboard    [👤 배즙🍭]  [로그아웃]
```

**기술 구현:**
- Telegram Login Widget (공식 OAuth)
- @BotFather → `/setdomain` → `tgpoke.com` 등록 필요 (수동)
- 로그인 성공 시 Telegram이 `id, first_name, username, photo_url, auth_date, hash` 전달
- 서버에서 `HMAC-SHA256(bot_token)` 기반 hash 검증
- 검증 후 세션 쿠키 발급 (HttpOnly, 24시간 만료)

**서버 엔드포인트:**
```
POST /api/auth/telegram    — hash 검증 + 세션 생성
GET  /api/auth/me          — 현재 로그인 유저 정보
POST /api/auth/logout      — 세션 삭제
```

**보안:**
- `auth_date` 5분 이내 검증 (replay attack 방지)
- 세션 쿠키 HttpOnly + Secure + SameSite=Lax
- 서버 메모리 세션 (aiohttp-session or dict)

---

### 2-2. 내 포켓몬 (My Pokemon)

로그인 후 네비게이션에 **"내 포켓몬"** 탭 추가 (로그인 시에만 표시).

#### 메인 레이아웃
```
┌─────────────────────────────────────────────────┐
│  필터/정렬 바                                      │
│  [전체▼] [타입▼] [등급▼]  정렬: [실전투력↓] [IV↓] [이름] │
├─────────────────────────────────────────────────┤
│  #001 이상해씨 🌿 ★3     [C: 68]                  │
│  HP 162  ATK 52(+4)  DEF 55(+6)  ...  실전투력 478 │
├─────────────────────────────────────────────────┤
│  #006 리자몽 🔥 ★5 ✨    [S: 178]                  │
│  HP 285  ATK 98(+12) DEF 71(+3)  ...  실전투력 823 │
├─────────────────────────────────────────────────┤
│  ...                                             │
└─────────────────────────────────────────────────┘
```

#### 각 포켓몬 카드에 표시할 정보
| 항목 | 설명 | 예시 |
|------|------|------|
| 기본 정보 | 이름, 타입 이모지, 레어리티 배지, 이로치 마크 | `리자몽 🔥 Epic ✨` |
| 친밀도 | ★ 개수 | `★★★★★` (5강) |
| IV 등급 | [등급: 총합] | `[S: 178]` |
| 6스텟 | 실제 배틀 수치 + (IV 보정분) | `ATK 98(+12)` |
| 실전투력 | 모든 보정 포함 6스텟 합산 | `823` |

#### 스텟 계산 방식
```
기본 스텟 = 종족값base × spread × friendship × evo_stage
IV 보정   = 기본 스텟 × (IV_mult - 1.0)
           where IV_mult = 0.85 + (iv / 31) × 0.30

실전투력   = Σ(6스텟 with IV 적용)
기본전투력  = Σ(6스텟 without IV, IV_mult=1.0)
IV 기여분  = 실전투력 - 기본전투력
```

**표시 예시:**
```
HP 285(+18)  ATK 98(+12)  DEF 71(+3)  SPA 95(+11)  SPDEF 68(+1)  SPD 82(+7)
                                                           실전투력: 823 (+52)
```
- `(+12)` = IV로 인해 올라간 수치
- `실전투력: 823 (+52)` = 총합 / IV로 인한 총 증가분

#### IV 시너지 등급 (핵심 차별화 포인트)
같은 S급이라도 **어디에 찍혔냐**가 중요함.

```python
# 시너지 점수 계산 (0~100)
def calc_synergy(pokemon_type, stat_type, ivs):
    # stat_type별 핵심 스텟 가중치
    weights = {
        "offensive":  {"atk": 2.0, "spa": 2.0, "spd": 1.5, "hp": 1.0, "def": 0.5, "spdef": 0.5},
        "defensive":  {"hp": 2.0, "def": 2.0, "spdef": 2.0, "spd": 0.5, "atk": 0.5, "spa": 0.5},
        "balanced":   {"hp": 1.2, "atk": 1.2, "def": 1.0, "spa": 1.2, "spdef": 1.0, "spd": 1.2},
        "speedy":     {"spd": 2.5, "atk": 1.5, "spa": 1.5, "hp": 0.5, "def": 0.3, "spdef": 0.3},
    }
    # 배틀에서 ATK vs SPA 중 높은 쪽을 쓰므로, 딜러는 둘 다 중요
    # 가중합 / 최대가능 가중합 × 100 = 시너지 점수
```

**시너지 등급:**
| 등급 | 점수 | 의미 |
|------|------|------|
| ⚡ 완벽 | 90~100 | IV가 핵심 스텟에 집중 |
| 🔥 우수 | 70~89 | 대체로 잘 찍힘 |
| ⚖️ 보통 | 50~69 | 평균적 분배 |
| 💤 아쉬움 | 0~49 | 핵심 스텟에 IV 낮음 |

**표시:**
```
리자몽 🔥 [S: 178] ⚡완벽 시너지
   → 공격형 포켓몬에 ATK 28, SPA 31 — 딜러에게 최적 IV
```

#### 필터/정렬 옵션
- **필터:** 전체 / 타입(18종) / 등급(common~legendary) / 이로치만 / IV등급(S~D)
- **정렬:** 실전투력↓ / IV총합↓ / 시너지↓ / 친밀도↓ / 이름순 / 최근획득

#### API 엔드포인트
```
GET /api/my/pokemon         — 내 포켓몬 전체 (인증 필요)
    Response: [{
        id, pokemon_id, name_ko, emoji, rarity, pokemon_type, stat_type,
        friendship, is_shiny, is_favorite,
        ivs: {hp, atk, def, spa, spdef, spd},
        stats: {hp, atk, def, spa, spdef, spd},      // IV 미적용
        real_stats: {hp, atk, def, spa, spdef, spd},  // IV 적용
        power, real_power, iv_bonus, iv_grade, iv_total,
        synergy_score, synergy_grade
    }]

GET /api/my/summary         — 내 요약 (총 마리수, 평균IV, 최고전투력 등)
```

---

### 2-3. AI 팀 시뮬레이터 (Team Simulator)

로그인 후 **"팀 시뮬레이터"** 탭 추가.

#### 추천 카테고리 (4가지)
```
┌──────────────────────────────────────────────┐
│  🤖 AI 팀 시뮬레이터                            │
│                                              │
│  [💪 전투력 몰빵]  [🎯 특성 시너지]               │
│  [🛡️ 카운터 덱]   [⚖️ 밸런스 추천]               │
│                                              │
│  ─── 추천 결과 ───                             │
│  1. 리자몽 🔥 (실전투력 823)                     │
│  2. 라프라스 💧 (실전투력 756)                    │
│  3. ...                                      │
│                                              │
│  💡 AI 분석:                                   │
│  "공격형 포켓몬 위주로 구성했습니다.                  │
│   다만 얼음 타입 카운터가 없어 드래곤 상대 시         │
│   취약할 수 있습니다. 현재 보유 포켓몬 중            │
│   얼음 타입이 없으므로 향후 확보를 추천합니다."        │
│                                              │
└──────────────────────────────────────────────┘
```

#### 4가지 추천 모드

| 모드 | 설명 | 로직 |
|------|------|------|
| 💪 전투력 몰빵 | 순수 실전투력 TOP 6 | `real_power` 내림차순 + 전설1/에픽중복 제한 |
| 🎯 특성 시너지 | IV-종족값 궁합 최적 | `synergy_score` 기반 + 타입 커버리지 고려 |
| 🛡️ 카운터 덱 | 랭커 팀 카운터 | 상위 랭커 팀 조회 → 상성 유리한 내 포켓몬 선별 |
| ⚖️ 밸런스 추천 | 종합 최적 | 전투력 + 시너지 + 타입 분산 균형 |

#### LLM 연동 (무료)

**선택지: Google Gemini 2.0 Flash (무료 티어)**
- 15 RPM (분당 15회)
- 100만 토큰/분
- 충분함 (팀 추천은 가끔씩 요청)

**하이브리드 접근:**
1. **서버에서 알고리즘으로** 팀 후보 계산 (빠름, 무료, 확정적)
2. **LLM에게** 계산 결과 + 유저 포켓몬 풀을 넘겨서 **자연어 분석/설명** 생성

```
[유저 요청] → 서버 알고리즘 (팀 후보 산출)
           → Gemini Flash API (분석 코멘트 생성)
           → 프론트에 결과 + 코멘트 전달
```

**LLM 프롬프트 예시:**
```
당신은 포켓몬 배틀 전략가입니다.
아래는 유저의 포켓몬 보유 현황과 추천 팀입니다.
배틀 시스템: 1:1 순차 매칭, 타입 상성 1.3배, 공격/특공 중 높은 쪽 사용.

[유저 보유 포켓몬 목록 + 스텟]
[추천 팀 6마리 + 이유]

이 팀의 강점, 약점, 주의사항을 한국어로 3-4문장 간결하게 분석해주세요.
보유 풀에서 부족한 타입이 있으면 언급해주세요.
```

**카운터 덱 로직:**
```python
# 1. 상위 5 랭커의 팀 구성 조회
top_teams = await get_top_ranker_teams(limit=5)

# 2. 랭커 팀의 타입 분포 분석
enemy_types = Counter(p["pokemon_type"] for team in top_teams for p in team)

# 3. 각 적 타입에 유리한 타입 매핑 (TYPE_CHART)
counter_types = get_counter_types(enemy_types)

# 4. 내 포켓몬 중 카운터 타입 + 높은 전투력 선별
my_counters = [p for p in my_pokemon if p["type"] in counter_types]
               .sort(key=real_power, reverse=True)[:6]

# 5. 부족하면 LLM이 "상대 드래곤 타입이 많은데 얼음 포켓몬이 없어 취약" 코멘트
```

#### API 엔드포인트
```
POST /api/my/team-recommend
    Body: { "mode": "power|synergy|counter|balance" }
    Response: {
        "team": [6마리 포켓몬 데이터],
        "analysis": "AI 분석 텍스트...",
        "warnings": ["얼음 타입 부재", "방어형 포켓몬 부족"]
    }
```

---

## 3. UI/UX 변경 요약

### 네비게이션 변경
```
[로그인 전]  홈 | 채널 | 배틀&랭킹 | 포켓몬 티어 | 타입 상성표 | 통계
[로그인 후]  홈 | 채널 | 배틀&랭킹 | 포켓몬 티어 | 타입 상성표 | 통계 | 📦 내 포켓몬 | 🤖 팀 시뮬레이터
```

### 헤더 변경
```
[로그인 전]  Pokemon Dashboard                              [🔗 Connect]
[로그인 후]  Pokemon Dashboard                    [👤 배즙🍭] [로그아웃]
```

---

## 4. 기술 스택

| 구성요소 | 기술 |
|----------|------|
| 인증 | Telegram Login Widget + HMAC-SHA256 검증 |
| 세션 | 서버 메모리 딕셔너리 (세션 ID → user_id, 쿠키) |
| 백엔드 | aiohttp (기존) + 신규 API 엔드포인트 |
| 프론트 | 기존 바닐라 JS + HTML (프레임워크 없음) |
| LLM | Google Gemini 2.0 Flash API (무료 티어) |
| DB | 기존 Supabase PostgreSQL (신규 테이블 없음) |

---

## 5. 필요한 사전 작업

1. **@BotFather → `/setdomain` → `tgpoke.com`** (수동, 텔레그램 앱에서)
2. **Google AI Studio에서 Gemini API Key 발급** (무료, https://aistudio.google.com/)
3. `.env`에 `GEMINI_API_KEY` 추가

---

## 6. 구현 순서

| # | Phase | 내용 | 난이도 |
|---|-------|------|--------|
| 1 | 텔레그램 인증 | Connect 버튼 + 로그인 위젯 + 세션 | 중간 |
| 2 | 내 포켓몬 API | `/api/my/pokemon` + 실전투력/시너지 계산 | 중간 |
| 3 | 내 포켓몬 UI | 포켓몬 카드 리스트 + 필터/정렬 | 중간 |
| 4 | 팀 추천 알고리즘 | 4가지 모드 추천 로직 | 높음 |
| 5 | LLM 연동 | Gemini Flash 분석 코멘트 | 낮음 |
| 6 | 팀 시뮬레이터 UI | 추천 결과 카드 + AI 코멘트 | 중간 |
