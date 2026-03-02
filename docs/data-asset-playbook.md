# DB 자산 활용 기획서
### Pokemon Bot Data Asset Playbook
> 이 문서는 포켓몬봇 운영으로 축적된 데이터를 분석하여, 향후 모든 프로젝트에 재사용 가능한 인사이트와 프레임워크를 정리한 것이다.

---

## 1. 보유 데이터 자산 요약

| 카테고리 | 테이블 수 | 핵심 데이터 |
|----------|----------|------------|
| 유저 행동 | 6개 | 가입, 활동, 잡기, 실패, 연속접속, 새벽활동 |
| 게임 경제 | 5개 | 스폰, 잡기시도, 마스터볼, BP, 교환 |
| 소셜/경쟁 | 4개 | 배틀, 교환, 칭호, 파트너 |
| 채팅방 | 2개 | 방 메타, 시간대별 메시지량 |
| 콘텐츠 | 2개 | 251종 포켓몬, 이벤트 |
| **합계** | **16개 테이블, 25+ 유저 액션 추적, 60+ 쿼리 함수** |

---

## 2. 유저 유형 분류 (User Segmentation)

### 2.1 행동 기반 세그먼트

실제 DB에서 추출 가능한 유저 유형:

#### A. 수집형 (Collector)
```sql
-- 도감 완성률 높고, 잡기 시도 많고, 교환 적극적
SELECT user_id FROM pokedex GROUP BY user_id HAVING COUNT(DISTINCT pokemon_id) > 100
```
**특징:** 도감 완성이 목표. 희귀 포켓몬에 마스터볼 사용. 교환으로 빈 도감 채움.
**핵심 지표:** 도감 완성률, 교환 횟수, 레어 보유 수

#### B. 경쟁형 (Competitor)
```sql
-- 배틀 참여 많고, 팀 구성 완료, BP 소비 활발
SELECT user_id FROM users WHERE battle_wins + battle_losses > 10
```
**특징:** 배틀 랭킹 집착. 팀 최적화에 시간 투자. BP 경제의 주요 소비자.
**핵심 지표:** 승률, 연승, BP 순환율, 팀 변경 빈도

#### C. 올빼미형 (Night Owl)
```sql
-- 새벽 2~5시 활동, midnight_catch_count 높음
SELECT user_id FROM user_title_stats WHERE midnight_catch_count > 10
```
**특징:** 새벽 보너스 시간대 노림. 전설 확률 2배 구간을 알고 활용.
**핵심 지표:** 새벽 잡기 수, 전설 보유 비율, 새벽 접속 빈도

#### D. 캐주얼형 (Casual)
```sql
-- 간헐적 접속, 도감 30 이하, 배틀 미참여
SELECT user_id FROM users u
LEFT JOIN pokedex p ON u.user_id = p.user_id
GROUP BY u.user_id
HAVING COUNT(DISTINCT p.pokemon_id) < 30
AND u.battle_wins + u.battle_losses = 0
```
**특징:** 가끔 "ㅊ"만 입력. 시스템을 깊이 이해하지 않음. 이탈 위험 가장 높음.
**핵심 지표:** 주간 접속 일수, 일일 잡기 시도 수, 연속접속 streak

#### E. 사회형 (Social)
```sql
-- 교환 활발, love_count 높음, 여러 채팅방에서 활동
SELECT user_id FROM trades WHERE status = 'accepted'
GROUP BY from_user_id HAVING COUNT(*) > 5
```
**특징:** 교환과 소통이 주요 동기. 채팅방 분위기 메이커.
**핵심 지표:** 교환 수, love_count, 활동 채팅방 수

#### F. 시스템 악용형 (Exploiter) -- 아래 4장 상세

### 2.2 세그먼트 교차 분석

| | 수집형 | 경쟁형 | 올빼미형 | 캐주얼 | 사회형 |
|--|--------|--------|----------|--------|--------|
| **리텐션** | 매우 높음 | 높음 | 높음 | 낮음 | 중간 |
| **과금 의향** | 높음 | 매우 높음 | 중간 | 낮음 | 중간 |
| **콘텐츠 소비** | 빠름 | 선택적 | 희귀 집중 | 느림 | 교환 중심 |
| **이탈 시그널** | 도감 정체 | 연패 | 시간대 변경 | streak 0 | 교환 거절 |

---

## 3. KPI 프레임워크

### 3.1 핵심 지표 (North Star Metrics)

| 지표 | 산출 방법 | 의미 |
|------|----------|------|
| **DAU** | `COUNT(DISTINCT user_id) FROM catch_attempts WHERE DATE(attempted_at) = today` | 실제 게임 참여자 |
| **일일 잡기 전환율** | `caught / total spawns` (spawn_log) | 콘텐츠 소비 건강도 |
| **7일 리텐션** | 가입 7일 후 catch_attempts 존재 여부 | 신규 유저 정착률 |
| **도감 중앙값** | 전체 유저 도감 수 median | 콘텐츠 진행도 |

### 3.2 경제 건강도 지표

| 지표 | 산출 | 위험 신호 |
|------|------|----------|
| **마스터볼 인플레이션** | `SUM(master_balls) FROM users` 추이 | 총량 급증 → 경제 붕괴 |
| **BP 순환율** | `bp_earned / bp_spent` 비율 | >2.0이면 BP 인플레 |
| **교환 거절률** | `rejected / total trades` | >60%면 교환 시스템 불만 |
| **잡기 한도 소진율** | 일일 한도 도달 유저 비율 | >40%면 한도 상향 검토 |
| **마스터볼 사용률** | `used_master_ball / total attempts` | >10%면 일반 잡기 포기 신호 |

### 3.3 참여도 지표

| 지표 | 산출 | 기준값 |
|------|------|--------|
| **스폰당 참여자 수** | `AVG(participants) FROM spawn_log` | <1.5면 관심 저하 |
| **배틀 참여율** | 배틀 1회 이상 유저 / 전체 유저 | 목표 30% |
| **칭호 해금률** | 칭호별 해금 유저 수 / 전체 유저 | 너무 쉽거나 어려운 칭호 탐지 |
| **이벤트 효과** | 이벤트 중 DAU / 이벤트 전 DAU | <1.2면 이벤트 무의미 |

### 3.4 채팅방 건강도

| 지표 | 산출 | 조치 |
|------|------|------|
| **좀비 방** | 스폰 있지만 participants=0 연속 3회 | 스폰 배율 하향 |
| **과열 방** | 모든 스폰 participants>5 | 스폰 배율 상향 |
| **활동 집중도** | 상위 3개 방 활동 / 전체 활동 | >80%면 방 다양성 부족 |

---

## 4. 유저 우회전략 (Exploit) 탐지

### 4.1 발견된 패턴들

#### 패턴 1: 포켓볼 충전 어뷰징
**행동:** "포켓볼 충전"을 30초 쿨다운마다 반복 → 일일 100회 추가 잡기 확보
```sql
-- 탐지 쿼리
SELECT user_id, bonus_catches FROM catch_limits
WHERE bonus_catches >= 80 AND date = CURRENT_DATE
```
**현재 방어:** 일일 100회 캡, 30초 쿨다운
**학습:** 리소스 생성형 기능은 반드시 일일 상한 + 쿨다운 이중 잠금 필요

#### 패턴 2: 마스터볼 축적 후 전설 독점
**행동:** 마스터볼을 모아두다가 전설 스폰 시에만 사용 → 전설 독점
```sql
-- 탐지: 마스터볼을 전설에만 쓰는 유저
SELECT ca.user_id, COUNT(*) as masterball_on_legendary
FROM catch_attempts ca
JOIN spawn_sessions ss ON ca.session_id = ss.id
JOIN pokemon_master pm ON ss.pokemon_id = pm.id
WHERE ca.used_master_ball = 1 AND pm.rarity = 'legendary'
GROUP BY ca.user_id
```
**현재 방어:** BP상점 일일 3개 제한, 2% 드랍 확률
**학습:** 확정 성공 아이템은 획득 경로를 철저히 제한해야 함

#### 패턴 3: 연속잡기 리셋 회피
**행동:** 2연속 잡기 후 의도적으로 1턴 쉬고 다시 잡기 → 쿨다운 회피
```sql
-- 탐지: 항상 정확히 2연속 후 1턴 쉬는 패턴
SELECT user_id,
  COUNT(CASE WHEN consecutive_catches = 2 THEN 1 END) as hit_limit_count
FROM catch_limits
GROUP BY user_id
HAVING hit_limit_count > 10
```
**학습:** 단순 카운터 기반 쿨다운은 패턴을 읽히면 무력화됨. 랜덤 쿨다운이 더 효과적.

#### 패턴 4: 멀티 채팅방 잡기
**행동:** 여러 채팅방에 가입해서 잡기 기회 극대화
```sql
-- 탐지: 3개 이상 방에서 잡은 유저
SELECT user_id, COUNT(DISTINCT caught_in_chat_id) as chat_count
FROM user_pokemon
GROUP BY user_id
HAVING chat_count >= 3
```
**현재 방어:** 일일 잡기 한도가 전체 공유 (방별이 아님)
**학습:** 글로벌 한도 설계가 멀티 채널 어뷰징의 핵심 방어

#### 패턴 5: 이벤트 타이밍 어뷰징
**행동:** 전설 5배 이벤트 때만 접속해서 몰아잡기
```sql
-- 탐지: 이벤트 기간에만 활동하는 유저
SELECT ca.user_id,
  COUNT(CASE WHEN e.id IS NOT NULL THEN 1 END) as event_catches,
  COUNT(*) as total_catches
FROM catch_attempts ca
LEFT JOIN events e ON ca.attempted_at BETWEEN e.start_time AND e.end_time
  AND e.event_type = 'rarity_boost'
GROUP BY ca.user_id
HAVING event_catches::float / total_catches > 0.7
```
**학습:** 이벤트는 기존 유저 활성화에는 좋지만, 이벤트 의존형 유저를 만들 위험

### 4.2 우회전략 탐지 프레임워크

향후 프로젝트에 적용할 공통 패턴:

```
[모든 리소스 생성 경로]
  ├─ 일일 상한 (hard cap)
  ├─ 쿨다운 (최소 간격)
  ├─ 랜덤 쿨다운 (예측 불가)
  └─ 글로벌 한도 (채널/계정 단위가 아닌 유저 단위)

[확정 성공 아이템]
  ├─ 획득 경로 제한 (BP 교환만, 일일 3개)
  ├─ 보유 상한 검토
  └─ 사용 로그 → 효율 분석

[경쟁 콘텐츠]
  ├─ 동일 상대 쿨다운
  ├─ 전역 쿨다운
  └─ 팀 제한 (전설 1마리 등)
```

---

## 5. 병목 분석 (Bottleneck)

### 5.1 시스템 병목 (이미 해결한 것들)

| 병목 | 원인 | 해결 | 배운 점 |
|------|------|------|---------|
| N+1 쿼리 | 칭호 체크 40+ DB 호출 | 배치 쿼리 3개로 통합 | **이벤트 핸들러에서 절대 루프 내 DB 호출 금지** |
| 이벤트 루프 차단 | 이미지 생성이 동기 실행 | run_in_executor | **CPU 작업은 반드시 별도 스레드** |
| Race condition | 마스터볼 SELECT→UPDATE 분리 | 원자적 UPDATE...RETURNING | **재화 관련은 무조건 원자적 연산** |
| 매 메시지 동기 DB | 활동 추적이 블로킹 | asyncio.create_task | **비핵심 로직은 fire-and-forget** |

### 5.2 콘텐츠 병목

| 병목 | 진단 방법 | 의미 |
|------|----------|------|
| **도감 정체** | 도감 90% 이상 유저 증가 멈춤 | 레어 스폰 확률 or 교환 시스템 문제 |
| **배틀 비참여** | 배틀 0회 유저 비율 | 진입 장벽 (팀 구성 복잡도) |
| **교환 비매칭** | pending 상태 교환 비율 | 수요-공급 불일치 |
| **칭호 도달불가** | 특정 칭호 해금률 0% | 조건이 비현실적 |

### 5.3 유저 여정 병목 (Funnel)

```
가입 → 첫 잡기 → 도감 10 → 도감 50 → 첫 교환 → 첫 배틀 → 도감 100 → 칭호 수집
 100%    ?%        ?%        ?%        ?%         ?%        ?%         ?%
```

각 단계 전환율을 측정하면 이탈 지점 특정 가능:

```sql
-- 퍼널 분석 쿼리
SELECT
  COUNT(*) as total_users,
  COUNT(CASE WHEN dex >= 1 THEN 1 END) as caught_any,
  COUNT(CASE WHEN dex >= 10 THEN 1 END) as dex_10,
  COUNT(CASE WHEN dex >= 50 THEN 1 END) as dex_50,
  COUNT(CASE WHEN trades > 0 THEN 1 END) as traded,
  COUNT(CASE WHEN battles > 0 THEN 1 END) as battled,
  COUNT(CASE WHEN dex >= 100 THEN 1 END) as dex_100
FROM (
  SELECT u.user_id,
    (SELECT COUNT(DISTINCT pokemon_id) FROM pokedex WHERE user_id = u.user_id) as dex,
    (SELECT COUNT(*) FROM trades WHERE (from_user_id = u.user_id OR to_user_id = u.user_id) AND status = 'accepted') as trades,
    u.battle_wins + u.battle_losses as battles
  FROM users u
) sub
```

---

## 6. 향후 프로젝트 적용 프레임워크

### 6.1 데이터 수집 원칙 (포켓몬봇에서 배운 것)

```
원칙 1: 모든 유저 액션에 타임스탬프
  → catch_attempts.attempted_at 덕분에 시간대별 분석 가능

원칙 2: 실패도 기록
  → catch_fail_count 덕분에 "불운한 유저" 탐지 가능

원칙 3: 비정규화된 로그 테이블
  → spawn_log에 이름/이모지 복사해둔 덕분에 JOIN 없이 빠른 조회

원칙 4: 행동 카운터는 별도 테이블
  → user_title_stats 분리 덕분에 유저 테이블 비대화 방지

원칙 5: 글로벌 집계는 캐싱
  → event_service 30초 캐시 → DB 부하 90% 감소
```

### 6.2 모든 프로젝트에 적용할 공통 테이블 설계

```sql
-- 1. 유저 액션 로그 (불변, append-only)
CREATE TABLE user_action_log (
  id SERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  action_type TEXT NOT NULL,    -- 'catch', 'trade', 'battle', 'purchase'...
  target_id TEXT,               -- 대상 (pokemon_id, trade_id 등)
  metadata JSONB,               -- 추가 데이터 (rarity, amount, result 등)
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_action_log_user ON user_action_log(user_id, created_at);
CREATE INDEX idx_action_log_type ON user_action_log(action_type, created_at);

-- 2. 유저 행동 통계 (매일 집계)
CREATE TABLE user_daily_stats (
  user_id BIGINT NOT NULL,
  date DATE NOT NULL,
  action_counts JSONB NOT NULL DEFAULT '{}',  -- {"catch": 5, "battle": 2, ...}
  PRIMARY KEY (user_id, date)
);

-- 3. 시스템 KPI 스냅샷 (1시간 단위)
CREATE TABLE kpi_snapshots (
  id SERIAL PRIMARY KEY,
  snapshot_at TIMESTAMPTZ DEFAULT NOW(),
  metrics JSONB NOT NULL  -- {"dau": 150, "catch_rate": 0.45, ...}
);
```

### 6.3 유저 세그먼트 자동 분류 로직

```python
# 포켓몬봇 데이터로 검증된 세그먼트 기준
SEGMENT_RULES = {
    "collector": {
        "condition": "pokedex_count > median * 1.5",
        "retention_risk": "low",
        "monetization": "cosmetic items, rare access"
    },
    "competitor": {
        "condition": "battle_count > 10 AND battle_count > catch_count * 0.3",
        "retention_risk": "medium (연패 시 이탈)",
        "monetization": "competitive advantage items"
    },
    "night_owl": {
        "condition": "midnight_action_ratio > 0.3",
        "retention_risk": "medium (생활패턴 변화)",
        "monetization": "시간대 보너스"
    },
    "casual": {
        "condition": "weekly_active_days < 3 AND pokedex_count < 30",
        "retention_risk": "very high",
        "monetization": "low (리텐션 먼저)"
    },
    "social": {
        "condition": "trade_count > 5 OR love_count > 10",
        "retention_risk": "low (커뮤니티 의존)",
        "monetization": "social features, gifting"
    },
    "exploiter": {
        "condition": "bonus_catches > 80 OR masterball_legendary_ratio > 0.7",
        "retention_risk": "low (시스템 마스터)",
        "monetization": "high but risky"
    }
}
```

### 6.4 이탈 예측 시그널

포켓몬봇 데이터에서 추출 가능한 이탈 선행 지표:

| 시그널 | 측정 | 위험도 |
|--------|------|--------|
| login_streak 0으로 리셋 | user_title_stats | 경고 |
| 일일 잡기 시도 0회 (기존 활성 유저) | catch_limits 미생성 | 위험 |
| 3연속 잡기 실패 | catch_fail_count 급증 | 경고 |
| 배틀 5연패 | battle_streak 음수 누적 | 위험 |
| 교환 3연속 거절 | trades.status = 'rejected' | 경고 |
| 도감 2주 이상 변화 없음 | pokedex 최근 등록 없음 | 위험 |

### 6.5 게임 경제 밸런스 대시보드 (공통)

모든 프로젝트에 적용할 경제 모니터링:

```
[재화 유입]                    [재화 유출]
  잡기 보상 ──────┐      ┌────── 마스터볼 사용
  배틀 BP ────────┤      ├────── BP 상점 구매
  이벤트 보너스 ──┤      ├────── 교환 수수료 (미래)
  포켓볼 충전 ────┘      └────── 진화 비용 (미래)

  유입 합계 > 유출 합계 → 인플레이션 위험
  유입 합계 < 유출 합계 → 디플레이션 → 유저 불만
```

---

## 7. 데이터 파이프라인 설계

### 7.1 현재 → 분석 DB 구조

```
[운영 DB (PostgreSQL)]
     │
     ├── 실시간: 대시보드 API (현재 구현)
     │
     ├── 일일 배치: KPI 스냅샷 생성 (미구현)
     │    └── DAU, 잡기율, 경제지표, 세그먼트별 수치
     │
     └── 주간 배치: 코호트 분석 (미구현)
          └── 가입 주차별 리텐션, 퍼널 전환율
```

### 7.2 구현 우선순위

| 순서 | 항목 | 난이도 | 임팩트 |
|------|------|--------|--------|
| 1 | 일일 KPI 스냅샷 자동 저장 | 낮음 | 높음 |
| 2 | 유저 세그먼트 자동 태깅 | 중간 | 높음 |
| 3 | 이탈 예측 경고 (텔레그램 알림) | 중간 | 높음 |
| 4 | 코호트 리텐션 차트 | 중간 | 중간 |
| 5 | 경제 밸런스 대시보드 | 높음 | 중간 |
| 6 | A/B 테스트 프레임워크 | 높음 | 높음 |

---

## 8. 핵심 교훈 요약 (다음 프로젝트 체크리스트)

### 설계 단계
- [ ] 모든 유저 액션에 타임스탬프 + 실패 기록
- [ ] 리소스 생성 경로마다 일일 상한 + 쿨다운 설계
- [ ] 확정 성공 아이템은 획득 병목 설계 (BP 200 같은)
- [ ] 글로벌 한도 vs 채널별 한도 결정
- [ ] 비정규화 로그 테이블 별도 설계

### 개발 단계
- [ ] 핸들러 내 루프 DB 호출 금지 → 배치 쿼리
- [ ] 재화 변경은 원자적 연산 (UPDATE...RETURNING)
- [ ] CPU 작업은 executor, 비핵심 로직은 background task
- [ ] concurrent_updates 활성화 (텔레그램봇 기준)
- [ ] 인덱스는 쿼리 패턴에 맞춰 설계

### 운영 단계
- [ ] 일일 KPI 자동 기록
- [ ] 이탈 시그널 모니터링
- [ ] 경제 유입/유출 밸런스 주간 체크
- [ ] 이벤트 전후 DAU 비교 → 효과 검증
- [ ] 어뷰징 패턴 쿼리 주간 실행

---

## 9. 실측 KPI 스냅샷 (2026-03-02 기준)

> 런칭 3일차 실제 데이터 기반. 향후 프로젝트 벤치마크 기준선.

### 9.1 핵심 지표 (North Star)

| 지표 | 수치 | 판정 | 비고 |
|------|------|------|------|
| **DAU** | 76 (3/2), 126 (3/1) | 🟢 | 런칭 직후 피크 → 안정화 중 |
| **잡기 전환율** | 55~57% | 🟢 건강 | 스폰 절반 이상 포획됨 |
| **D+1 리텐션** | 25.6% (3/1 코호트) | 🟡 주의 | 2/28 코호트 69.4%에서 급락 |
| **도감 중앙값** | 1 | 🔴 위험 | 대부분 첫 잡기 수준에서 멈춤 |
| **배틀 참여율** | 9.3% (17/182명) | 🔴 위험 | 목표 30% 대비 매우 낮음 |

### 9.2 경제 건강도

| 지표 | 수치 | 판정 |
|------|------|------|
| 마스터볼 총 보유 | 39개 | 🟢 적절 |
| 마스터볼 총 사용 | 53개 | 🟢 소비 > 보유 → 정상 순환 |
| BP 총 보유량 | 1,405 | 🟢 초기 단계 적절 |
| 스폰당 평균 참여자(24h) | 2.35명 | 🟡 최소 기준(1.5) 충족, 개선 여지 |
| 24시간 포획률 | 54.6% | 🟢 |

### 9.3 유저 세그먼트 분포

| 세그먼트 | 조건 | 인원 | 비율 | 시사점 |
|----------|------|------|------|--------|
| 뉴비 | 도감 0~9 | 146 | **80.2%** | 🔴 온보딩 전환 실패 |
| 캐주얼 | 도감 10~49 | 25 | 13.7% | 이 구간이 핵심 전환점 |
| 적극 수집가 | 도감 50~99 | 9 | 4.9% | 잔존 유저, 충성도 높음 |
| 하드코어 | 도감 100+ | 2 | 1.1% | 최상위 파워유저 |

**분석:** 전체 182명 중 80%가 도감 9 이하. "첫 잡기 → 도감 10"이 최대 병목.
뉴비가 캐주얼로 전환되면 리텐션이 크게 개선될 것으로 예측.

### 9.4 도감 분포

| 통계 | 수치 |
|------|------|
| 중앙값 | 1 |
| Q1 (25%) | 0 |
| Q3 (75%) | 6 |
| 평균 | 9.7 |
| 최대 | 165 |

→ 극단적 우편향(right skew). 소수 파워유저가 평균을 끌어올리고, 대다수는 0~6에 분포.

### 9.5 칭호 해금률

| 칭호 | 해금 수 | 해금률 | 난이도 판정 |
|------|---------|--------|-----------|
| 여정의 시작 (첫 포획) | 95 | 52.2% | 적절 |
| 초보 트레이너 (도감 15) | 27 | 14.8% | 적절 |
| 문유 광팬 | 25 | 13.7% | 쉬움 |
| 잡기의 달인 (100회) | 14 | 7.7% | 적절 |
| 레전드 헌터 | 10 | 5.5% | 적절 |
| 포켓몬 수집가 (도감 45) | 10 | 5.5% | 적절 |
| 레어 헌터 | 8 | 4.4% | 적절 |
| 성도의 초보 | 8 | 4.4% | 적절 |

→ 48%가 첫 잡기 칭호조차 없음 = 가입만 하고 한 번도 안 잡은 유저가 절반.

### 9.6 채팅방 건강도 (24시간)

| 방 | 스폰 | 평균 참여 | 포획 | 상태 |
|----|------|----------|------|------|
| 포켓몬 성지 (문유채팅방) | 107 | **4.6** | - | 🟢 과열 |
| 필립×춘삼 방 | 110 | 2.6 | 58 | 🟢 활발 |
| 비트매매 금지방 | 124 | 2.5 | 71 | 🟢 활발 |
| ㅈ밥 대전 | 125 | 1.5 | 40 | 🟡 참여 낮음 |

→ 32개 활성 방 중 "문유채팅방"이 참여도 1위. 일부 방은 스폰만 되고 참여 저조(좀비 방 후보).

### 9.7 D+1 리텐션 추이

| 코호트 | 가입 | D+1 잔존 | 리텐션 |
|--------|------|---------|--------|
| 2/28 (런칭) | 36 | 25 | **69.4%** |
| 3/1 | 125 | 32 | **25.6%** |
| 3/2 (오늘) | 21 | - | 측정 불가 |

**분석:** 2/28 코호트(초기 얼리어답터)는 69.4%로 높지만, 3/1 대규모 유입 코호트는 25.6%로 급락.
→ 바이럴로 유입된 유저는 초기 몰입도가 낮음. 첫 30분 경험 개선이 핵심.

### 9.8 핵심 액션 아이템

| 우선순위 | 항목 | 근거 |
|---------|------|------|
| 🔴 1 | **뉴비 온보딩 강화** (도감 0→10 유도) | 80%가 도감 9 이하 |
| 🔴 2 | **배틀 진입장벽 낮추기** | 참여율 9.3% (목표 30%) |
| 🟡 3 | **D+1 리텐션 개선** | 3/1 코호트 25.6% |
| 🟡 4 | **좀비 방 관리** | 참여자 0~1 방 스폰 조정 |
| 🟢 5 | 경제 모니터링 유지 | 현재 정상, 인플레 감시 |

---

## 부록: 즉시 실행 가능한 분석 쿼리 모음

### A. 유저 세그먼트 현황
```sql
SELECT
  CASE
    WHEN dex >= 100 THEN 'hardcore_collector'
    WHEN dex >= 50 THEN 'active_collector'
    WHEN dex >= 10 THEN 'casual'
    ELSE 'newbie'
  END as segment,
  COUNT(*) as user_count
FROM (
  SELECT u.user_id, COUNT(DISTINCT p.pokemon_id) as dex
  FROM users u LEFT JOIN pokedex p ON u.user_id = p.user_id
  GROUP BY u.user_id
) sub
GROUP BY segment ORDER BY user_count DESC;
```

### B. 7일 리텐션
```sql
SELECT
  DATE(registered_at) as cohort_date,
  COUNT(*) as signups,
  COUNT(CASE WHEN last_active_at >= registered_at + INTERVAL '7 days' THEN 1 END) as retained_7d,
  ROUND(100.0 * COUNT(CASE WHEN last_active_at >= registered_at + INTERVAL '7 days' THEN 1 END) / COUNT(*), 1) as retention_pct
FROM users
GROUP BY DATE(registered_at)
ORDER BY cohort_date DESC
LIMIT 30;
```

### C. 시간대별 활동 히트맵
```sql
SELECT
  EXTRACT(HOUR FROM TO_TIMESTAMP(hour_bucket, 'YYYY-MM-DD-HH24')) as hour_kst,
  SUM(message_count) as total_messages,
  COUNT(DISTINCT chat_id) as active_chats
FROM chat_activity
WHERE hour_bucket >= TO_CHAR(NOW() - INTERVAL '7 days', 'YYYY-MM-DD-HH24')
GROUP BY hour_kst
ORDER BY hour_kst;
```

### D. 경제 건강도
```sql
SELECT
  (SELECT SUM(master_balls) FROM users) as total_masterball_supply,
  (SELECT COUNT(*) FROM catch_attempts WHERE used_master_ball = 1) as total_masterball_spent,
  (SELECT SUM(battle_points) FROM users) as total_bp_supply,
  (SELECT ROUND(AVG(participants), 2) FROM spawn_log WHERE spawned_at > NOW() - INTERVAL '24 hours') as avg_participants_24h,
  (SELECT ROUND(100.0 * COUNT(CASE WHEN caught_by_user_id IS NOT NULL THEN 1 END) / COUNT(*), 1) FROM spawn_log WHERE spawned_at > NOW() - INTERVAL '24 hours') as catch_rate_24h;
```

### E. 어뷰징 감시
```sql
-- 포켓볼 충전 어뷰저
SELECT user_id, bonus_catches FROM catch_limits
WHERE date = CURRENT_DATE AND bonus_catches >= 80;

-- 마스터볼 전설 독점
SELECT ca.user_id, u.display_name,
  COUNT(CASE WHEN pm.rarity = 'legendary' THEN 1 END) as legendary_uses,
  COUNT(*) as total_uses
FROM catch_attempts ca
JOIN spawn_sessions ss ON ca.session_id = ss.id
JOIN pokemon_master pm ON ss.pokemon_id = pm.id
JOIN users u ON ca.user_id = u.user_id
WHERE ca.used_master_ball = 1
GROUP BY ca.user_id, u.display_name
HAVING COUNT(*) >= 3;
```
