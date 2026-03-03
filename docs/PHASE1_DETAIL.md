# Phase 1 상세 기획서
> 작성일: 2026-03-03 | 버전: 1.0

---

## 1. 색이 다른 포켓몬 (Shiny) 상세

### 1.1 개요
스폰된 포켓몬이 일정 확률로 "색이 다른" 변종으로 등장. 순수 수집 요소로 배틀 스탯에는 영향 없음.

### 1.2 확률
| 조건 | Shiny 확률 |
|------|-----------|
| 기본 | 1/512 (0.195%) |
| 커뮤니티 데이 이벤트 | 1/64 (1.56%) |
| Shiny 부스트 이벤트 | 이벤트별 설정 가능 |

- 스폰 시점에 Shiny 여부 결정 (서버 사이드)
- 해당 스폰에 참여하는 모든 유저에게 동일한 Shiny 여부 적용 (전체 공유)

### 1.3 표시
**스폰 메시지**:
```
✨ 야생의 ✨ 🔥 색이 다른 리자몽이(가) 나타났다! 🌙
ㅊ 입력으로 잡기 (60초)
```

**포획 메시지**:
```
✨ 색이 다른 리자몽! — 🔥 리자몽 포획!
```

**카드 이미지**:
- 기존 카드에 ✨ 반짝이 테두리 오버레이
- 카드 좌상단에 ✨ 마크
- 배경에 금색/무지개 그라데이션 효과

### 1.4 DB 변경
```sql
-- user_pokemon 테이블에 shiny 플래그 추가
ALTER TABLE user_pokemon ADD COLUMN is_shiny INTEGER NOT NULL DEFAULT 0;

-- spawn_sessions에 shiny 플래그 추가
ALTER TABLE spawn_sessions ADD COLUMN is_shiny INTEGER NOT NULL DEFAULT 0;

-- spawn_log에 shiny 플래그 추가
ALTER TABLE spawn_log ADD COLUMN is_shiny INTEGER NOT NULL DEFAULT 0;

-- shiny 도감 (기존 pokedex와 별도)
CREATE TABLE IF NOT EXISTS shiny_pokedex (
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    pokemon_id INTEGER NOT NULL REFERENCES pokemon_master(id),
    obtained_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    method TEXT NOT NULL DEFAULT 'catch',
    PRIMARY KEY (user_id, pokemon_id)
);
```

### 1.5 수정 파일
| 파일 | 변경 내용 |
|------|----------|
| `config.py` | `SHINY_RATE = 1/512`, `SHINY_EVENT_RATE = 1/64` 상수 추가 |
| `database/schema.py` | Shiny 마이그레이션 추가 |
| `database/queries.py` | `give_pokemon_to_user`에 is_shiny 파라미터, `register_shiny_pokedex`, `get_shiny_pokedex_count` 추가 |
| `services/spawn_service.py` | `execute_spawn`에서 Shiny 판정, 카드/메시지 분기 |
| `services/card_generator.py` | Shiny 카드 이미지 생성 (테두리/이펙트) |
| `services/event_service.py` | `get_shiny_boost()` 함수 추가 |
| `handlers/group.py` | 포획 메시지에 Shiny 표시 |
| `handlers/private.py` | `/도감`, `/내pokemon` 등에 Shiny 표시 |

### 1.6 게임 규칙
- Shiny 포켓몬은 **교환 시 Shiny 유지**
- Shiny 포켓몬은 **진화 시 Shiny 유지**
- Shiny 여부는 **배틀 스탯에 영향 없음** (순수 수집)
- 마스터볼/하이퍼볼로 Shiny 잡기 가능 (일반 ㅊ과 동일)
- Shiny 도감은 일반 도감과 **별도 트래킹**

### 1.7 Shiny 칭호
| 조건 | 칭호 | 이모지 |
|------|------|--------|
| Shiny 1마리 보유 | 빛의 트레이너 | ✨ |
| Shiny 10종 도감 | 샤이니 헌터 | 🌈 |
| Shiny 50종 도감 | 샤이니 마스터 | 💎 |
| Shiny 전설 1마리 | 빛나는 전설 | 🌟 |

---

## 2. 이벤트 한정몬 상세

### 2.1 개요
특정 기간에만 스폰되는 한정 포켓몬. 이벤트 종료 후 스폰 불가, 보유한 유저만 소장. FOMO 극대화.

### 2.2 DB 변경
```sql
-- pokemon_master에 이벤트 관련 컬럼 추가
ALTER TABLE pokemon_master ADD COLUMN is_event INTEGER NOT NULL DEFAULT 0;
ALTER TABLE pokemon_master ADD COLUMN event_start TIMESTAMPTZ DEFAULT NULL;
ALTER TABLE pokemon_master ADD COLUMN event_end TIMESTAMPTZ DEFAULT NULL;
```

### 2.3 스폰 로직
1. `pick_random_pokemon(rarity)` 실행 시:
   - 기본 풀: `is_event = 0` 인 포켓몬만
   - 활성 이벤트몬: `is_event = 1 AND NOW() BETWEEN event_start AND event_end` 인 포켓몬을 풀에 추가
2. 이벤트몬은 해당 등급의 스폰 풀에 합류 (별도 등급 아님)
3. 이벤트몬 스폰 시 특별 메시지:
```
🎪 이벤트! 야생의 🔥 흑자몽이(가) 나타났다!
⚠️ 한정 이벤트 포켓몬! (3/15까지)
ㅊ 입력으로 잡기 (60초)
```

### 2.4 한정몬 관리
- `/admin addeventmon [id] [name] [rarity] [start] [end]` 명령어로 등록
- 종료된 이벤트몬은 스폰 풀에서 자동 제외
- 보유한 유저의 user_pokemon에는 그대로 유지 (삭제 안 됨)

### 2.5 이벤트몬 도감
- 일반 도감과 **통합** (251 + 이벤트몬)
- 이벤트몬은 도감에 🎪 마크로 구분
- 이벤트 종료 후 도감에 "미보유 - 이벤트 종료" 표시

### 2.6 수정 파일
| 파일 | 변경 내용 |
|------|----------|
| `database/schema.py` | 이벤트몬 컬럼 마이그레이션 |
| `database/queries.py` | `pick_random_pokemon`에 이벤트몬 풀 합류 로직, 이벤트몬 CRUD |
| `services/spawn_service.py` | 스폰 메시지에 이벤트 표시 |
| `handlers/admin.py` | 이벤트몬 등록/종료 명령어 |
| `handlers/private.py` | 도감에 이벤트몬 표시 |

### 2.7 1차 이벤트 계획
| 이벤트 | 기간 | 한정몬 | 등급 | 설명 |
|--------|------|--------|------|------|
| 봄맞이 | 3/10~3/17 | 벚꽃이브이 | Rare | 분홍 이브이, 봄 한정 |
| 다크위크 | 3/17~3/24 | 흑자몽 | Epic | 검은색 리자몽 변종 |
| 만우절 | 4/1~4/3 | 아구몬 | Legendary | 디지몬 콜라보, 3일 한정 |

---

## 3. 아케이드 이용권 상세

### 3.1 개요
아케이드 채널(tg_poke)은 현재 상시 개방. 이용권 시스템 도입으로:
- 아케이드 접근을 이용권 기반으로 전환
- BP 소모처 추가 → BP 인플레 완화
- 시간 제한으로 플레이 가치 상승

### 3.2 기본 스펙
| 항목 | 값 |
|------|-----|
| 가격 | 200 BP |
| 효과 | 구매 시점부터 1시간 아케이드 이용 가능 |
| 일일 구매 한도 | 3회 (KST 00:00 리셋) |
| 구매 위치 | DM 상점 (`구매 아케이드`) |

### 3.3 동작 방식
1. 아케이드 채널에서 `ㅊ` 입력 시:
   - 유효한 이용권 있는지 확인 (현재 시각 < 이용권 만료 시각)
   - **없으면**: "🎮 아케이드 이용권이 필요합니다! DM에서 '구매 아케이드'로 구매하세요." 메시지 후 return
   - **있으면**: 정상 캐치 진행
2. 마스터볼(ㅁ), 하이퍼볼(ㅎ)도 동일하게 이용권 체크
3. 이용권은 **구매 시점부터 1시간** (고정). 남은 시간 안 쓰면 소멸.

### 3.4 DB 변경
```sql
-- 아케이드 이용권 테이블
CREATE TABLE IF NOT EXISTS arcade_passes (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    purchased_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

-- 일일 구매 횟수 트래킹은 기존 bp_purchase_log 활용
-- bp_purchase_log에 item_type = 'arcade_pass' 로 기록
```

### 3.5 수정 파일
| 파일 | 변경 내용 |
|------|----------|
| `config.py` | `BP_ARCADE_PASS_COST = 200`, `ARCADE_PASS_DURATION = 3600`, `ARCADE_PASS_DAILY_LIMIT = 3` |
| `database/schema.py` | arcade_passes 테이블 생성 |
| `database/queries.py` | `buy_arcade_pass`, `get_active_arcade_pass`, `get_arcade_pass_purchases_today` |
| `handlers/battle.py` | 상점에 아케이드 이용권 표시, 구매 로직 |
| `handlers/group.py` | catch_handler, master_ball_handler, hyper_ball_handler에 아케이드 이용권 체크 추가 |

### 3.6 상점 표시
```
🏪 BP 상점

💰 보유 BP: 1,500

🟣 마스터볼 x1 — 200 BP (오늘 2/3개 남음)
⚡ 강제스폰권 x1 — 500 BP (보유: 2개)
🔴 포켓볼 충전 100개 — 200 BP
🔵 하이퍼볼 x1 — 20 BP (보유: 5개)
🎮 아케이드 이용권 (1시간) — 200 BP (오늘 3/3회 남음)

구매: 구매 마스터볼 / 구매 강제스폰 / 구매 포켓볼 / 구매 하이퍼볼 [수량] / 구매 아케이드
```

### 3.7 아케이드 채널 UX
**이용권 없이 ㅊ 입력 시**:
```
🎮 아케이드 이용권이 필요합니다!
DM에서 '구매 아케이드'로 구매하세요. (200 BP/1시간)
```

**이용권 구매 시**:
```
🎮 아케이드 이용권 구매 완료!
💰 남은 BP: 1,300
⏰ 만료: 08:30 KST (오늘 남은 구매: 2회)
```

**이용권 만료 5분 전** (선택적):
```
⏰ 아케이드 이용권이 5분 후 만료됩니다!
```

---

## 4. 일일 리셋 시간 통일 (KST 00:00)

### 4.1 현황
현재 리셋 기준이 혼재:
- catch_limits: `datetime.now().strftime("%Y-%m-%d")` → **서버 시간(UTC)** 기준
- 토너먼트: APScheduler timezone='Asia/Seoul' → **KST** 기준
- force_spawn_count: 별도 리셋 로직 불명확

### 4.2 변경 방침
**모든 일일 리셋을 KST 00:00 (UTC 15:00) 기준으로 통일**

### 4.3 영향 범위
| 시스템 | 현재 기준 | 변경 후 |
|--------|----------|---------|
| 포켓볼 일일 한도 (catch_limits) | UTC 날짜 | KST 날짜 |
| 마스터볼 일일 구매 한도 | UTC 날짜 | KST 날짜 |
| 하이퍼볼 일일 구매 한도 | (없음) | — |
| 아케이드 이용권 구매 한도 | (신규) | KST 날짜 |
| 밥/놀기 일일 횟수 | UTC 날짜 | KST 날짜 |
| 강제스폰 횟수 | 수동 리셋 | 매일 KST 00:00 자동 리셋 |
| 연속 캐치 쿨다운 | UTC 날짜 | KST 날짜 |
| 토너먼트 | KST (이미 정상) | 유지 |

### 4.4 구현 방법
```python
# config.py에 추가
import datetime, zoneinfo

KST = zoneinfo.ZoneInfo("Asia/Seoul")

def get_kst_today() -> str:
    """KST 기준 오늘 날짜 문자열 반환."""
    return datetime.datetime.now(KST).strftime("%Y-%m-%d")
```

기존 `datetime.now().strftime("%Y-%m-%d")` 를 전부 `config.get_kst_today()`로 교체.

### 4.5 수정 파일
| 파일 | 변경 내용 |
|------|----------|
| `config.py` | KST 타임존, `get_kst_today()` 함수 추가 |
| `database/queries.py` | 모든 날짜 비교를 KST 기준으로 변경 |
| `handlers/group.py` | catch_handler 등의 날짜 참조 변경 |
| `handlers/battle.py` | 구매 한도 날짜 참조 변경 |
| `services/spawn_service.py` | resolve_spawn 내 날짜 참조 변경 |
| `handlers/private.py` | 밥/놀기 날짜 참조 변경 |

### 4.6 자동 리셋 스케줄러
```python
# main.py에 추가 - 매일 KST 00:00 자동 리셋
from apscheduler.triggers.cron import CronTrigger

scheduler.add_job(
    daily_reset,
    CronTrigger(hour=0, minute=0, timezone="Asia/Seoul"),
    id="daily_reset",
)

async def daily_reset():
    """매일 KST 00:00에 실행되는 일일 리셋."""
    await queries.reset_force_spawn_counts()  # 강제스폰 횟수 리셋
    await queries.reset_daily_feed_play()     # 밥/놀기 횟수 리셋
    logger.info("Daily reset completed (KST 00:00)")
```

---

## 5. 개발 순서 (DEV 브랜치)

### Step 1: 기반 작업
1. DEV 브랜치 생성
2. KST 리셋 시간 통일 (config.py + 전체 날짜 참조 교체)
3. 테스트

### Step 2: 아케이드 이용권
1. arcade_passes 테이블 생성
2. 구매/체크/만료 로직
3. 상점 표시 업데이트
4. catch_handler에 이용권 체크 추가
5. 테스트

### Step 3: Shiny 시스템
1. DB 마이그레이션 (user_pokemon, spawn_sessions, spawn_log, shiny_pokedex)
2. spawn_service에 Shiny 판정 추가
3. 카드 이미지 Shiny 이펙트
4. 포획/스폰 메시지 분기
5. Shiny 도감 명령어
6. Shiny 칭호 추가
7. 테스트

### Step 4: 이벤트 한정몬
1. pokemon_master 이벤트 컬럼 마이그레이션
2. 스폰 풀에 이벤트몬 합류 로직
3. 이벤트몬 등록 어드민 명령어
4. 이벤트몬 카드 이미지 (🎪 마크)
5. 첫 이벤트몬 데이터 추가
6. 테스트

### Step 5: DEV → Master 머지
1. 전체 기능 통합 테스트
2. 유저 확인 후 Master 머지
3. VM 배포 + 봇 재시작
