# 🎮 포켓몬 배틀 시스템 기획서

## Context
현재 봇은 포획/육성/교환/도감 수집 중심의 타마고치형 게임.
유저들이 모은 포켓몬으로 **파트너 지정 → 6마리 팀 구성 → 그룹 채팅방에서 PvP 자동 배틀**을 할 수 있는 시스템 추가.
배틀 보상으로 **BP(배틀 포인트)** 적립 + **배틀 전용 칭호** 해금.

### 유저 선택 사항
- ✅ 자동 배틀 (수락 시 즉시 결과 표시)
- ✅ 그룹 채팅방에서 진행 (관전 재미)
- ✅ 간단한 타입 상성 추가
- ✅ BP + 칭호 보상

---

## 1. 능력치 시스템 (간소화)

### 1-1. 설계 철학
> 기존 `pokemon_master`에 컬럼 2개만 추가 (pokemon_type, stat_type).
> 4개의 배틀 스탯(HP/ATK/DEF/SPD)은 **배틀 시점에 공식으로 계산** — DB에 저장하지 않음.

### 1-2. 새 컬럼

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `pokemon_type` | TEXT | 포켓몬 타입 (fire, water, grass, ...) |
| `stat_type` | TEXT | 스탯 성향 (offensive/defensive/balanced/speedy) |

### 1-3. 스탯 계산 공식

```python
# config.py에 추가

RARITY_BASE_STAT = {
    "common": 45, "rare": 60, "epic": 75, "legendary": 95
}

STAT_SPREADS = {
    "offensive": {"hp": 0.9, "atk": 1.3, "def": 0.8, "spd": 1.0},
    "defensive": {"hp": 1.2, "atk": 0.8, "def": 1.3, "spd": 0.8},
    "balanced":  {"hp": 1.0, "atk": 1.0, "def": 1.0, "spd": 1.0},
    "speedy":    {"hp": 0.8, "atk": 1.0, "def": 0.7, "spd": 1.4},
}

FRIENDSHIP_BONUS = 0.04  # 친밀도 1당 +4% (최대 5 = +20%)
```

```python
# utils/battle_calc.py (신규)

def calc_battle_stats(pokemon_id, rarity, stat_type, friendship):
    base = config.RARITY_BASE_STAT[rarity]
    spread = config.STAT_SPREADS[stat_type]
    bonus = 1.0 + (friendship * config.FRIENDSHIP_BONUS)

    return {
        "hp":  int(base * 3 * spread["hp"] * bonus),
        "atk": int(base * spread["atk"] * bonus),
        "def": int(base * spread["def"] * bonus),
        "spd": int(base * spread["spd"] * bonus),
    }
```

### 1-4. 예시 스탯

| 포켓몬 | 레어도 | 성향 | 친밀도 | HP | ATK | DEF | SPD |
|--------|--------|------|--------|-----|-----|-----|-----|
| 잉어킹 | common | defensive | 0 | 162 | 36 | 58 | 36 |
| 피카츄 | rare | speedy | 3 | 161 | 67 | 47 | 94 |
| 리자몽 | epic | offensive | 5 | 243 | 117 | 72 | 90 |
| 뮤츠 | legendary | offensive | 5 | 308 | 148 | 91 | 114 |

→ 레어도가 높을수록 전반적으로 강하지만, 친밀도 MAX common이 친밀도 0 rare를 이길 수 있음 (육성 가치)

---

## 2. 타입 상성 시스템

### 2-1. 타입 목록 (10종 간소화)

| 타입 | 한글 | 이모지 |
|------|------|--------|
| normal | 노말 | ⚪ |
| fire | 불꽃 | 🔥 |
| water | 물 | 💧 |
| grass | 풀 | 🌿 |
| electric | 전기 | ⚡ |
| ice | 얼음 | ❄️ |
| fighting | 격투 | 👊 |
| psychic | 에스퍼 | 🔮 |
| dragon | 드래곤 | 🐉 |
| dark | 악 | 🌑 |

> 원작 18종에서 10종으로 간소화. 독/바위/땅/비행/벌레/고스트/강철/페어리는
> 가장 가까운 타입으로 흡수 (예: 독→dark, 비행→normal, 바위→fighting 등)

### 2-2. 상성표 (효과적 → 1.3x 데미지)

```python
# config.py
TYPE_ADVANTAGE = {
    "fire":     ["grass", "ice"],
    "water":    ["fire"],
    "grass":    ["water", "electric"],
    "electric": ["water"],
    "ice":      ["grass", "dragon"],
    "fighting": ["normal", "ice", "dark"],
    "psychic":  ["fighting"],
    "dragon":   ["dragon"],
    "dark":     ["psychic"],
    "normal":   [],  # 상성 이점 없음
}
```

- 타입 유리: **1.3x** 데미지
- 타입 불리: **0.7x** 데미지
- 중립: **1.0x**

### 2-3. 시드 데이터

`database/seed.py`에서 251종에 `pokemon_type` + `stat_type` 추가 필요.
예시:
```python
# (id, pokemon_type, stat_type)
(1,   "grass",    "balanced"),    # 이상해씨
(4,   "fire",     "offensive"),   # 파이리
(7,   "water",    "defensive"),   # 꼬부기
(25,  "electric", "speedy"),      # 피카츄
(130, "water",    "offensive"),   # 갸라도스
(143, "normal",   "defensive"),   # 잠만보
(150, "psychic",  "offensive"),   # 뮤츠
(151, "psychic",  "balanced"),    # 뮤
```

→ 251종 전체 매핑은 구현 시 원작 기반으로 일괄 생성

---

## 3. 파트너 포켓몬

### 3-1. 개요
보유 포켓몬 중 1마리를 "파트너"로 지정. 프로필에 표시되고 배틀 시 소량 보너스.

### 3-2. DB 변경
`users` 테이블에 컬럼 추가:
```sql
ALTER TABLE users ADD COLUMN partner_pokemon_id INTEGER REFERENCES user_pokemon(id);
```

### 3-3. 명령어

| 명령어 | 동작 |
|--------|------|
| `파트너` | 현재 파트너 확인 + 안내 |
| `파트너 3` | 내포켓몬 3번을 파트너로 지정 |

### 3-4. 파트너 보너스
- 배틀 시 **ATK +5%** (파트너가 팀에 포함된 경우)
- 프로필/도감/내포켓몬에서 🤝 마크 표시

### 3-5. 핸들러 위치
- `handlers/dm_pokedex.py`에 `partner_handler` + `partner_callback` 추가
- 또는 별도 `handlers/battle.py`에 통합

---

## 4. 배틀 팀 (최대 6마리)

### 4-1. 개요
보유 포켓몬 중 최대 6마리를 배틀 팀으로 등록. 순서도 지정 가능.

### 4-2. DB 스키마

```sql
CREATE TABLE IF NOT EXISTS battle_teams (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    slot INTEGER NOT NULL CHECK(slot BETWEEN 1 AND 6),
    pokemon_instance_id INTEGER NOT NULL REFERENCES user_pokemon(id),
    UNIQUE(user_id, slot),
    UNIQUE(user_id, pokemon_instance_id)
);
CREATE INDEX idx_battle_teams_user ON battle_teams(user_id);
```

### 4-3. 명령어

| 명령어 | 동작 |
|--------|------|
| `팀` | 현재 배틀 팀 확인 |
| `팀등록 1 3 5 2` | 내포켓몬 번호로 팀 순서 지정 (최대 6자리) |
| `팀해제` | 팀 초기화 |

### 4-4. 검증 규칙
- 최소 1마리, 최대 6마리
- `is_active = 1`인 포켓몬만 가능
- 중복 불가 (같은 포켓몬 2번 등록 X)
- 팀 미등록 시 배틀 불가 (명시적 팀 설정 필요)

### 4-5. 팀 표시 예시
```
⚔️ 나의 배틀 팀

1️⃣ 🔥 리자몽  ATK:117 DEF:72 SPD:90 HP:243
2️⃣ 💧 거북왕  ATK:72  DEF:117 SPD:72 HP:324
3️⃣ ⚡ 피카츄  ATK:67  DEF:47 SPD:94 HP:161
4️⃣ 🌿 이상해꽃 ATK:90  DEF:90 SPD:90 HP:270
5️⃣ 🐉 망나뇽  ATK:117 DEF:72 SPD:90 HP:243
6️⃣ 🔮 후딘   ATK:104 DEF:56 SPD:112 HP:194

팀등록 [번호들] 로 변경 가능
```

---

## 5. 배틀 시스템 (자동 배틀 / 그룹 채팅)

### 5-1. 배틀 플로우

```
[그룹 채팅방]

유저A: "배틀 @유저B"
  → 봇: "⚔️ 유저A가 유저B에게 배틀을 신청했습니다!
         30초 내에 수락해주세요!
         [✅ 수락] [❌ 거절]"

유저B: [수락 버튼 클릭] 또는 "배틀수락"
  → 봇: 자동 배틀 실행
  → 봇: 배틀 결과 텍스트 출력 (플레이바이플레이)
```

### 5-2. DB 스키마 — 배틀 도전

```sql
CREATE TABLE IF NOT EXISTS battle_challenges (
    id SERIAL PRIMARY KEY,
    challenger_id BIGINT NOT NULL REFERENCES users(user_id),
    defender_id BIGINT NOT NULL REFERENCES users(user_id),
    chat_id BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'accepted', 'declined', 'expired')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    UNIQUE(challenger_id, defender_id, status)
);
```

### 5-3. DB 스키마 — 배틀 기록

```sql
CREATE TABLE IF NOT EXISTS battle_records (
    id SERIAL PRIMARY KEY,
    challenge_id INTEGER REFERENCES battle_challenges(id),
    chat_id BIGINT NOT NULL,
    winner_id BIGINT REFERENCES users(user_id),
    loser_id BIGINT REFERENCES users(user_id),
    winner_team_size INTEGER NOT NULL,
    loser_team_size INTEGER NOT NULL,
    winner_remaining INTEGER NOT NULL,
    total_rounds INTEGER NOT NULL,
    battle_log TEXT,  -- 압축된 배틀 로그
    bp_earned INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_battle_records_winner ON battle_records(winner_id);
CREATE INDEX idx_battle_records_loser ON battle_records(loser_id);
```

### 5-4. DB 스키마 — 유저 배틀 통계

```sql
-- users 테이블에 컬럼 추가
ALTER TABLE users ADD COLUMN battle_wins INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN battle_losses INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN battle_streak INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN best_streak INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN battle_points INTEGER NOT NULL DEFAULT 0;
```

### 5-5. 배틀 엔진 알고리즘

```python
# services/battle_service.py (신규)

async def resolve_battle(challenger_team, defender_team):
    """자동 배틀 실행. 양쪽 팀의 스탯 리스트를 받아 결과 반환."""

    log_lines = []
    c_idx = 0  # 도전자 현재 포켓몬 인덱스
    d_idx = 0  # 수비자 현재 포켓몬 인덱스
    round_num = 0

    c_mon = challenger_team[c_idx]  # {name, emoji, type, stats:{hp,atk,def,spd}, current_hp}
    d_mon = defender_team[d_idx]

    while c_idx < len(challenger_team) and d_idx < len(defender_team):
        round_num += 1
        if round_num > 50:  # 무한루프 방지
            break

        # 1. 속도 순서 결정
        first, second = (c_mon, d_mon) if c_mon["stats"]["spd"] >= d_mon["stats"]["spd"] else (d_mon, c_mon)

        # 2. 선공 공격
        dmg1 = calc_damage(first, second)
        second["current_hp"] -= dmg1

        # 3. 후공 반격 (살아있으면)
        dmg2 = 0
        if second["current_hp"] > 0:
            dmg2 = calc_damage(second, first)
            first["current_hp"] -= dmg2

        # 4. 로그 기록
        log_lines.append(format_round(round_num, first, second, dmg1, dmg2))

        # 5. KO 처리
        if c_mon["current_hp"] <= 0:
            c_idx += 1
            if c_idx < len(challenger_team):
                c_mon = challenger_team[c_idx]
                log_lines.append(f"  💀 {이전몬} 쓰러짐! → {c_mon['emoji']}{c_mon['name']} 등장!")

        if d_mon["current_hp"] <= 0:
            d_idx += 1
            if d_idx < len(defender_team):
                d_mon = defender_team[d_idx]
                log_lines.append(f"  💀 {이전몬} 쓰러짐! → {d_mon['emoji']}{d_mon['name']} 등장!")

    # 승자 판정
    winner = "challenger" if d_idx >= len(defender_team) else "defender"
    return {
        "winner": winner,
        "rounds": round_num,
        "challenger_remaining": len(challenger_team) - c_idx,
        "defender_remaining": len(defender_team) - d_idx,
        "log": "\n".join(log_lines),
    }


def calc_damage(attacker, defender):
    """데미지 계산"""
    # 기본 데미지
    base = max(1, attacker["stats"]["atk"] - defender["stats"]["def"] * 0.4)

    # 타입 상성
    type_mult = 1.0
    if defender["type"] in TYPE_ADVANTAGE.get(attacker["type"], []):
        type_mult = 1.3  # 효과적
    elif attacker["type"] in TYPE_ADVANTAGE.get(defender["type"], []):
        type_mult = 0.7  # 비효과적

    # 크리티컬 (10%)
    crit = 1.5 if random.random() < 0.10 else 1.0

    # 랜덤 편차 (±10%)
    variance = random.uniform(0.9, 1.1)

    return int(base * type_mult * crit * variance)
```

### 5-6. 배틀 결과 표시 예시

```
⚔️ 배틀 결과!
━━━━━━━━━━━━━━━
「👑 챔피언」홍길동  VS  「⭐ 트레이너」김철수
(6마리)                    (5마리)
━━━━━━━━━━━━━━━

🔥리자몽 vs 💧거북왕
 → 거북왕 68 DMG (💧효과적!) | 리자몽 45 DMG
 → 거북왕 72 DMG | 리자몽 51 DMG (크리티컬!)
 💀 리자몽 쓰러짐!

⚡피카츄 vs 💧거북왕(HP:78)
 → 피카츄 95 DMG (⚡효과적!) | 거북왕 0 DMG
 💀 거북왕 쓰러짐!

⚡피카츄(HP:112) vs 🌿이상해꽃
 → 이상해꽃 54 DMG | 피카츄 38 DMG
 → 이상해꽃 61 DMG (크리티컬!)
 💀 피카츄 쓰러짐!

... (중략) ...

🐉망나뇽(HP:45) vs 🔮후딘(HP:67)
 → 망나뇽 89 DMG
 💀 후딘 쓰러짐!

━━━━━━━━━━━━━━━
🏆 홍길동 승리! (남은 포켓몬: 2마리)

💰 +25 BP · 🏆 3연승!
📊 전적: 12승 5패
```

### 5-7. 배틀 규칙

| 규칙 | 값 |
|------|-----|
| 도전 대기 시간 | 30초 (초과 시 자동 만료) |
| 배틀 쿨다운 | 같은 상대 5분, 전체 1분 |
| 최대 라운드 | 50 (초과 시 남은 HP 합산 비교) |
| 최소 팀 인원 | 1마리 |
| 최대 팀 인원 | 6마리 |

---

## 6. 보상 시스템

### 6-1. 배틀 포인트 (BP)

| 결과 | BP |
|------|-----|
| 승리 | +20~30 (상대 팀 크기에 비례) |
| 패배 | +5 (참여 보상) |
| 완승 (0피해) | +50 보너스 |
| 연승 보너스 | 3연승마다 +10 추가 |

### 6-2. BP 상점 (향후 확장 가능)

| 아이템 | BP 비용 |
|--------|---------|
| 마스터볼 x1 | 200 BP |
| (향후 추가 가능) | - |

### 6-3. 배틀 칭호

config.py의 `UNLOCKABLE_TITLES`에 추가:

| ID | 칭호 | 이모지 | 조건 |
|----|------|--------|------|
| `battle_first` | 첫 배틀 | ⚔️ | 배틀 1회 참여 |
| `battle_fighter` | 배틀 파이터 | 🥊 | 배틀 5승 |
| `battle_champion` | 배틀 챔피언 | 🏆 | 배틀 20승 |
| `battle_legend` | 배틀 레전드 | 👑 | 배틀 50승 |
| `battle_streak3` | 연승 전사 | 🔥 | 3연승 달성 |
| `battle_streak10` | 무적의 전사 | 💫 | 10연승 달성 |
| `battle_sweep` | 완벽한 승리 | ✨ | 무피해 완승 |
| `partner_set` | 나의 파트너 | 🤝 | 파트너 지정 |

---

## 7. 명령어 전체 정리

### 7-1. DM 명령어

| 명령어 | 설명 |
|--------|------|
| `파트너` | 현재 파트너 확인 |
| `파트너 [번호]` | 파트너 지정 |
| `팀` | 현재 배틀 팀 확인 |
| `팀등록 [번호들]` | 배틀 팀 순서 등록 (예: 팀등록 3 1 5 2 4 6) |
| `팀해제` | 배틀 팀 초기화 |
| `배틀전적` | 내 배틀 통계 (승패/연승/BP) |
| `BP` | BP 잔액 확인 |
| `BP상점` | BP 교환 상점 |

### 7-2. 그룹 명령어

| 명령어 | 설명 |
|--------|------|
| `배틀 @유저` | 배틀 도전 |
| `배틀수락` | 도전 수락 (인라인 버튼 대안) |
| `배틀거절` | 도전 거절 (인라인 버튼 대안) |
| `배틀랭킹` | 이 방의 배틀 승률 랭킹 |

---

## 8. 수정/신규 파일 목록

### 8-1. 신규 파일

| 파일 | 용도 |
|------|------|
| `services/battle_service.py` | 배틀 엔진 (데미지 계산, 자동 배틀 실행, 결과 생성) |
| `handlers/battle.py` | 배틀 관련 모든 핸들러 (도전/수락/거절/팀/파트너/전적/랭킹/BP상점) |
| `utils/battle_calc.py` | 스탯 계산 유틸리티 |

### 8-2. 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `database/schema.py` | 3개 테이블 추가 (battle_teams, battle_challenges, battle_records) + users 컬럼 추가 + pokemon_master 컬럼 추가 |
| `database/seed.py` | 251종 pokemon_type + stat_type 시드 데이터 |
| `database/queries.py` | 배틀 관련 쿼리 함수 20개+ 추가 |
| `config.py` | 배틀 설정값, 타입 상성표, 스탯 공식, 배틀 칭호, BP 설정 |
| `main.py` | 배틀 핸들러 등록 (DM + 그룹) + 콜백 핸들러 |
| `handlers/start.py` | 도움말에 배틀 명령어 추가 |
| `utils/title_checker.py` | 배틀 칭호 해금 조건 추가 |

---

## 9. 구현 순서 (4단계)

### Phase 1: 기반 (DB + 스탯 + 타입)
1. `pokemon_master`에 `pokemon_type`, `stat_type` 컬럼 추가 (schema.py)
2. 251종 타입/성향 시드 데이터 작성 (seed.py)
3. `config.py`에 배틀 설정값 추가 (상성표, 스탯 공식, BP 설정)
4. `utils/battle_calc.py` 작성 (스탯 계산 함수)
5. `users` 테이블에 배틀 통계 컬럼 추가

### Phase 2: 파트너 + 팀
6. `battle_teams` 테이블 생성
7. `users`에 `partner_pokemon_id` 추가
8. `handlers/battle.py` — 파트너/팀 핸들러 구현
9. `main.py`에 핸들러 등록
10. DM에서 파트너 지정 + 팀 등록 테스트

### Phase 3: 배틀 엔진
11. `battle_challenges`, `battle_records` 테이블 생성
12. `services/battle_service.py` — 배틀 엔진 핵심 구현
13. `handlers/battle.py` — 도전/수락/거절 핸들러 + 인라인 버튼
14. `database/queries.py` — 배틀 관련 쿼리 추가
15. 그룹에서 배틀 → 자동 결과 표시 테스트

### Phase 4: 보상 + 칭호 + 마무리
16. BP 적립/차감 로직
17. BP 상점 핸들러
18. `config.py`에 배틀 칭호 추가
19. `utils/title_checker.py`에 배틀 칭호 조건 추가
20. 배틀 랭킹 + 전적 조회 핸들러
21. 도움말 업데이트
22. 봇 재시작 + 종합 테스트

---

## 10. 검증 체크리스트

1. `팀등록 1 3 5` → 팀 정상 등록
2. `파트너 1` → 파트너 지정
3. `팀` → 팀 확인 시 스탯 표시
4. `배틀 @유저` → 도전 메시지 + 인라인 버튼
5. 수락 → 자동 배틀 실행 → 결과 텍스트 출력
6. 승자에게 BP 적립
7. `배틀전적` → 전적 정상 표시
8. 배틀 칭호 해금 확인
9. 쿨다운 작동 확인
10. 팀 미등록 시 배틀 불가 확인
