# TG 포켓몬 봇 — 개체값·종족값·상성 시스템 상세 기획안

> 작성일: 2026-03-04
> 버전: 2.0
> 현황: 유저 385명 / 보유 포켓몬 7,654마리 / DB 29MB(500MB 한도) / 주간 포획 6,400+

---

## 목차
1. [현재 시스템 완전 분석](#1-현재-시스템-완전-분석)
2. [Phase 1: 개체값(IV) 시스템](#2-phase-1-개체값iv-시스템)
3. [Phase 2: 종족값(Base Stats) 개별화](#3-phase-2-종족값base-stats-개별화)
4. [Phase 3: 타입 상성 확장](#4-phase-3-타입-상성-확장)
5. [Phase 4: 성격(Nature) 시스템](#5-phase-4-성격nature-시스템)
6. [Phase 5: 노력값(EV) / 육성 시스템](#6-phase-5-노력값ev--육성-시스템)
7. [인프라 병목 & 한계 분석](#7-인프라-병목--한계-분석)
8. [밸런스 임팩트 시뮬레이션](#8-밸런스-임팩트-시뮬레이션)
9. [장기 로드맵 & 우선순위](#9-장기-로드맵--우선순위)

---

## 1. 현재 시스템 완전 분석

### 1-1. 현재 스탯 공식

```python
# battle_calc.py — 현재 구현
HP  = int(base × 3 × spread[hp]  × (1 + friendship × 0.04) × evo_mult)
ATK = int(base     × spread[atk] × (1 + friendship × 0.04) × evo_mult)
DEF = int(base     × spread[def] × (1 + friendship × 0.04) × evo_mult)
SPD = int(base     × spread[spd] × (1 + friendship × 0.04) × evo_mult)
```

### 1-2. 현재 입력 변수 (전부 결정적 — 랜덤 요소 0)

| 변수 | 값 범위 | DB 저장 | 비고 |
|------|---------|---------|------|
| `base` (레어리티) | common:45, rare:60, epic:75, legendary:95 | pokemon_master.rarity | **같은 레어리티 = 같은 base** |
| `spread` (성향) | offensive/defensive/balanced/speedy | pokemon_master.stat_type | 포켓몬별 고정 |
| `friendship` | 0~5 (이로치 0~7) | user_pokemon.friendship | 유저 육성 |
| `evo_mult` | 1단:0.85, 2단:0.92, 최종:1.0 | 코드 내 계산 | 진화단계 |

### 1-3. 구조적 문제

```
문제 1: 같은 포켓몬 = 같은 스탯
  → 친밀도 5 리자몽 A = 친밀도 5 리자몽 B (완전 동일)
  → 수집 동기 부족, "내 포켓몬"이라는 애착 없음

문제 2: 레어리티만으로 강함 결정
  → base stat: legendary(95) > epic(75) > rare(60) > common(45)
  → 어떤 전설이든 > 어떤 에픽 (레어리티 서열 100% 고정)
  → 팀 구성의 전략적 다양성 부족

문제 3: 실제 포켓몬 특성 미반영
  → 잠만보(HP 특화)와 후딘(속도 특화)이 같은 epic offensive면 동일 스탯
  → 리자몽과 윈디가 같은 epic offensive면 동일 스탯
  → 포켓몬 고유의 정체성이 없음

문제 4: 개체 차이 없음
  → 같은 종 같은 친밀도 = 100% 동일 → 교환 가치 없음
  → "이 피카츄가 더 좋다"는 판단 기준 부재
```

### 1-4. 현재 스탯 실제 수치 (최종진화, 친밀도 5 기준)

| 포켓몬 | 레어리티 | 성향 | HP | ATK | DEF | SPD |
|--------|---------|------|-----|------|------|------|
| 리자몽 | epic | offensive | 243 | 117 | 72 | 90 |
| 거북왕 | epic | defensive | 324 | 72 | 117 | 72 |
| 이상해꽃 | epic | balanced | 270 | 90 | 90 | 90 |
| 윈디 | epic | offensive | 243 | 117 | 72 | 90 |
| 잠만보 | epic | defensive | 324 | 72 | 117 | 72 |
| 뮤츠 | legendary | offensive | 308 | 148 | 91 | 114 |
| 루기아 | legendary | defensive | 410 | 91 | 148 | 91 |
| 망나뇽 | legendary | offensive | 308 | 148 | 91 | 114 |

**문제 확인:** 리자몽 = 윈디, 거북왕 = 잠만보 (완전 동일 스탯)

### 1-5. 현재 타입 상성 (10타입, 단순화)

```
fire → grass, ice (1.3x)     |  water → fire (1.3x)
grass → water, electric       |  electric → water
ice → grass, dragon           |  fighting → normal, ice, dark
psychic → fighting            |  dragon → dragon
dark → psychic                |  normal → (없음)
```
- 유리: 1.3x / 불리: 0.7x / 면역: 없음
- 듀얼타입 없음 (리자몽 = fire만, flying 없음)

### 1-6. 현재 DB 테이블 구조 (관련 부분)

```sql
-- pokemon_master (251행, 포켓몬 원본 데이터)
id, name_ko, name_en, emoji, rarity, catch_rate,
evolves_from, evolves_to, evolution_method,
pokemon_type, stat_type
-- 개별 종족값 없음, base stat 없음

-- user_pokemon (7,654행, 유저 보유 포켓몬)
id, user_id, pokemon_id, nickname, friendship,
caught_at, caught_in_chat_id, is_active, is_shiny,
fed_today, played_today
-- IV 없음, 성격 없음, EV 없음
```

---

## 2. Phase 1: 개체값(IV) 시스템

> **난이도:** ★★☆☆☆ | **기간:** 1~2일 | **현실성:** ✅ 즉시 가능 | **임팩트:** 높음

### 2-1. 개요

포켓몬 포획 시 HP/ATK/DEF/SPD 각 스탯에 **0~31** 사이 랜덤 값을 부여.
같은 포켓몬이라도 개체값에 따라 스탯이 달라짐.

### 2-2. IV 스펙

```
범위: 0 ~ 31 (정수)
스탯 수: 4개 (HP, ATK, DEF, SPD)
총합 범위: 0 ~ 124
분포: 균등 분포 (각 값이 1/32 확률)
```

**이로치 보너스:**
```
일반 포켓몬: IV 0~31 (균등)
이로치 포켓몬: IV 10~31 (하한 보장, 평균 20.5 vs 일반 15.5)
```

### 2-3. IV 등급 체계

| 총합 범위 | 등급 | 한국어 | 확률 | 표시 |
|-----------|------|--------|------|------|
| 112~124 | S | 최상급 | 2.8% | ⭐⭐⭐ |
| 93~111 | A | 우수 | 14.7% | ⭐⭐ |
| 62~92 | B | 보통 | 49.8% | ⭐ |
| 31~61 | C | 부족 | 25.6% | (없음) |
| 0~30 | D | 열등 | 7.1% | (없음) |

확률 검증 (정규분포 근사: 평균=62, σ=18.5):
- P(≥112) ≈ 0.35σ 이상 = ~2.8%
- S급 1마리 얻으려면 평균 36회 포획 필요

### 2-4. 스탯 공식 변경

```python
# 현재
ATK = int(base × spread[atk] × friend_mult × evo_mult)

# 변경 후
ATK = int(base × spread[atk] × friend_mult × evo_mult × iv_mult(iv_atk))

def iv_mult(iv: int) -> float:
    """IV의 스탯 영향 계수. IV 0 = 0.8x, IV 15 = 1.0x, IV 31 = 1.2x"""
    return 0.8 + (iv / 31) * 0.4
```

**IV 영향범위: ±20%**
- IV 0: 0.80x (현재 대비 -20%)
- IV 15: ~0.99x (현재와 거의 동일)
- IV 31: 1.20x (현재 대비 +20%)

### 2-5. 실제 수치 예시 (리자몽 epic/offensive, 친밀도 5)

| IV (ATK) | iv_mult | ATK | 현재 대비 |
|----------|---------|-----|----------|
| 0 | 0.800 | 94 | -20% |
| 10 | 0.929 | 109 | -7% |
| 15 | 0.994 | 116 | -1% (≈현재) |
| 20 | 1.058 | 124 | +6% |
| 25 | 1.123 | 131 | +12% |
| 31 | 1.200 | 140 | +20% |

### 2-6. DB 마이그레이션

```sql
-- Step 1: 컬럼 추가
ALTER TABLE user_pokemon ADD COLUMN iv_hp SMALLINT DEFAULT NULL;
ALTER TABLE user_pokemon ADD COLUMN iv_atk SMALLINT DEFAULT NULL;
ALTER TABLE user_pokemon ADD COLUMN iv_def SMALLINT DEFAULT NULL;
ALTER TABLE user_pokemon ADD COLUMN iv_spd SMALLINT DEFAULT NULL;

-- Step 2: 기존 포켓몬에 IV 배정 (기존 유저 불이익 방지)
-- 방법 A: 전부 평균치 (15)로 → 기존 밸런스 완전 유지
UPDATE user_pokemon SET iv_hp=15, iv_atk=15, iv_def=15, iv_spd=15
WHERE iv_hp IS NULL;

-- 방법 B: 후한 랜덤 (10~25) → 약간의 재미 + 기존 대비 큰 손해 없음
UPDATE user_pokemon SET
    iv_hp  = floor(random() * 16 + 10)::smallint,
    iv_atk = floor(random() * 16 + 10)::smallint,
    iv_def = floor(random() * 16 + 10)::smallint,
    iv_spd = floor(random() * 16 + 10)::smallint
WHERE iv_hp IS NULL;
```

**용량 추가:** 4컬럼 × 2B = 8B/row → 7,654행 × 8B = **61KB** (무시 가능)

### 2-7. 수정 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `database/schema.py` | iv_hp/atk/def/spd 컬럼 추가 마이그레이션 |
| `database/queries.py` | give_pokemon_to_user()에 IV 생성 및 저장 |
| `utils/battle_calc.py` | calc_battle_stats()에 iv 파라미터 추가 |
| `config.py` | IV_MULT_MIN=0.8, IV_MULT_RANGE=0.4 상수 |
| `services/spawn_service.py` | 포획 시 generate_iv() 호출, 포획 메시지에 등급 표시 |
| `handlers/dm_pokedex.py` | 내포켓몬 상세에 IV 정보 표시 |
| `handlers/battle.py` | 배틀 시 IV 반영된 스탯 사용, 팀 표시에 등급 |
| `dashboard/server.py` | 티어표에 IV 영향 범위 표시 (선택) |

### 2-8. UI 변경 예시

**포획 메시지:**
```
현재: 딸깍! ✨ 배즘 — 🟡리자몽 포획!
변경: 딸깍! ✨ 배즘 — 🟡리자몽 포획! ⭐⭐⭐(S)
```

**내포켓몬 상세:**
```
현재:
  🟡 전설 · 리자몽
  ❤️❤️❤️❤️❤️ (친밀도 5/5)
  HP:243  ATK:117  DEF:72  SPD:90

변경:
  🟡 전설 · 리자몽 ⭐⭐⭐
  ❤️❤️❤️❤️❤️ (친밀도 5/5)
  HP:280  ATK:140  DEF:86  SPD:108
  📊 개체값: 28/31/29/31 (S등급 · 119/124)
```

**팀 등록 화면:**
```
현재:
  1. 🟡🔥 리자몽  HP:243 ATK:117 DEF:72 SPD:90

변경:
  1. 🟡🔥 리자몽 ⭐⭐⭐  HP:280 ATK:140 DEF:86 SPD:108
```

### 2-9. 리스크 & 완화

| 리스크 | 심각도 | 완화 방안 |
|--------|--------|----------|
| 기존 팀 밸런스 붕괴 | 낮음 | 기존 포켓몬 IV=15 (현재와 동일 스탯) |
| "S급 아니면 쓸모없다" 인식 | 중간 | S vs D 차이 = 40% (압도적이진 않음) |
| IV 확인을 위한 DM 남발 | 낮음 | 포획 시 등급 바로 표시 |

---

## 3. Phase 2: 종족값(Base Stats) 개별화

> **난이도:** ★★★☆☆ | **기간:** 3~5일 | **현실성:** ✅ 가능 | **임팩트:** 매우 높음

### 3-1. 개요

현재 레어리티 단일 base(45/60/75/95) → **포켓몬별 개별 종족값 4종** (HP/ATK/DEF/SPD)
원작 6스탯(HP/ATK/DEF/SpA/SpD/SPD)을 봇 4스탯으로 매핑.

### 3-2. 원작 → 봇 스탯 매핑 공식

원작은 6스탯, 봇은 4스탯. 변환 규칙:

```python
# 원작 → 봇 변환
bot_hp  = original_hp                    # HP는 그대로
bot_atk = max(original_atk, original_spa) # 물리/특수 중 높은 쪽
bot_def = (original_def + original_spd) / 2  # 물리방어+특수방어 평균
bot_spd = original_spe                   # 스피드 그대로
```

### 3-3. 정규화 (봇 밸런스 스케일링)

원작 종족값 범위: 5~255 → 봇 밸런스 범위: **20~180**

```python
def normalize(stat, original_min=5, original_max=255, bot_min=20, bot_max=180):
    return round(bot_min + (stat - original_min) / (original_max - original_min) * (bot_max - bot_min))
```

### 3-4. 주요 포켓몬 종족값 (정규화 후)

**전설 (11종)**
| # | 포켓몬 | HP | ATK | DEF | SPD | 합계 | 특성 |
|---|--------|-----|------|------|------|------|------|
| 150 | 뮤츠 | 87 | 117 | 71 | 101 | 376 | 최강 특수딜러 |
| 249 | 루기아 | 87 | 74 | 112 | 89 | 362 | 방어 특화 |
| 250 | 호오 | 87 | 101 | 96 | 74 | 358 | 균형형 전설 |
| 149 | 망나뇽 | 76 | 103 | 77 | 69 | 325 | 물리 딜러 |
| 248 | 마기라스 | 82 | 103 | 83 | 60 | 328 | 느린 파워형 |
| 151 | 뮤 | 82 | 82 | 79 | 82 | 325 | 올라운더 |
| 251 | 세레비 | 82 | 82 | 79 | 82 | 325 | 올라운더 |
| 144 | 프리저 | 75 | 79 | 89 | 72 | 315 | 방어형 |
| 145 | 썬더 | 75 | 97 | 69 | 82 | 323 | 속도형 딜러 |
| 146 | 파이어 | 75 | 97 | 69 | 75 | 316 | 균형 딜러 |
| 243 | 라이코 | 75 | 92 | 69 | 92 | 328 | 고속 딜러 |

**에픽 주요 (24종 중 발췌)**
| # | 포켓몬 | HP | ATK | DEF | SPD | 합계 | 특성 |
|---|--------|-----|------|------|------|------|------|
| 6 | 리자몽 | 69 | 89 | 65 | 82 | 305 | 속도형 화력 |
| 9 | 거북왕 | 69 | 73 | 81 | 68 | 291 | 밸런스 탱커 |
| 3 | 이상해꽃 | 69 | 82 | 72 | 69 | 292 | 균형형 |
| 59 | 윈디 | 75 | 89 | 63 | 79 | 306 | 고스탯 화력 |
| 143 | 잠만보 | 120 | 89 | 69 | 40 | 318 | 초체력 탱커 |
| 130 | 갸라도스 | 79 | 97 | 71 | 70 | 317 | 물리 화력 |
| 131 | 라프라스 | 101 | 73 | 69 | 59 | 302 | 체력형 |
| 65 | 후딘 | 55 | 104 | 55 | 95 | 309 | 유리대포 |
| 94 | 팬텀 | 59 | 101 | 53 | 89 | 302 | 고속 유리포 |
| 68 | 괴력몬 | 75 | 101 | 65 | 55 | 296 | 순수 물리형 |
| 212 | 핫삼 | 65 | 101 | 71 | 62 | 299 | 물리 탱커 |

**레어 주요 (64종 중 발췌)**
| # | 포켓몬 | HP | ATK | DEF | SPD | 합계 | 특성 |
|---|--------|-----|------|------|------|------|------|
| 26 | 라이츄 | 59 | 75 | 53 | 89 | 276 | 속도형 |
| 103 | 나시 | 79 | 97 | 63 | 55 | 294 | 고화력 저속 |
| 121 | 아쿠스타 | 59 | 82 | 67 | 92 | 300 | 균형 고속 |
| 25 | 피카츄 | 41 | 55 | 36 | 75 | 207 | 연약 속도형 |
| 34 | 니드킹 | 70 | 80 | 62 | 72 | 284 | 균형형 |

**커먼 주요 (44종 중 발췌)**
| # | 포켓몬 | HP | ATK | DEF | SPD | 합계 | 특성 |
|---|--------|-----|------|------|------|------|------|
| 20 | 래트 | 55 | 70 | 52 | 79 | 256 | 평범한 속도형 |
| 22 | 깨비드릴조 | 62 | 75 | 55 | 82 | 274 | 조금 강한 커먼 |
| 47 | 파라섹트 | 59 | 79 | 65 | 40 | 243 | 느린 탱커 |
| 129 | 잉어킹 | 32 | 20 | 44 | 69 | 165 | 최약체 |

### 3-5. 스탯 공식 변경

```python
# Phase 2 공식 (Phase 1 IV 포함)
HP  = int(base_hp  × 3 × friend_mult × evo_mult × iv_mult(iv_hp))
ATK = int(base_atk     × friend_mult × evo_mult × iv_mult(iv_atk))
DEF = int(base_def     × friend_mult × evo_mult × iv_mult(iv_def))
SPD = int(base_spd     × friend_mult × evo_mult × iv_mult(iv_spd))
```

- `base × spread[stat]` → `base_stat` 직접 사용
- `stat_type` (offensive/defensive 등) 컬럼은 **삭제하지 않고 참고 정보로 유지**

### 3-6. 점진적 반영 (밸런스 보호)

종족값 도입 시 기존 밸런스가 급변하므로 **반영률 단계적 증가:**

```python
SPECIES_STAT_WEIGHT = 0.5  # 시작: 50% 반영

# 혼합 공식
effective_base_atk = (
    old_base × old_spread[atk] × (1 - SPECIES_STAT_WEIGHT)
    + new_base_atk × SPECIES_STAT_WEIGHT
)
```

- 1주차: 50% 반영 (기존 시스템과 새 종족값의 평균)
- 2주차: 75% 반영
- 3주차: 100% 반영 (완전 전환)

### 3-7. DB 변경

```sql
ALTER TABLE pokemon_master ADD COLUMN base_hp SMALLINT DEFAULT NULL;
ALTER TABLE pokemon_master ADD COLUMN base_atk SMALLINT DEFAULT NULL;
ALTER TABLE pokemon_master ADD COLUMN base_def SMALLINT DEFAULT NULL;
ALTER TABLE pokemon_master ADD COLUMN base_spd SMALLINT DEFAULT NULL;

-- 251종 데이터 INSERT (자동화 스크립트로 원작 데이터 정규화 후 입력)
UPDATE pokemon_master SET base_hp=87, base_atk=117, base_def=71, base_spd=101 WHERE id=150; -- 뮤츠
UPDATE pokemon_master SET base_hp=69, base_atk=89, base_def=65, base_spd=82 WHERE id=6;    -- 리자몽
-- ... 249종 더
```

**용량:** 251행 × 8B = **2KB** (무시 가능)

### 3-8. 데이터 입력 자동화

```python
# 원작 데이터 크롤링 → 정규화 → SQL 생성
# pokemondb.net 또는 pokeapi.co 에서 251종 데이터 수집
import requests

for i in range(1, 252):
    r = requests.get(f"https://pokeapi.co/api/v2/pokemon/{i}")
    stats = {s["stat"]["name"]: s["base_stat"] for s in r.json()["stats"]}

    bot_hp  = normalize(stats["hp"])
    bot_atk = normalize(max(stats["attack"], stats["special-attack"]))
    bot_def = normalize((stats["defense"] + stats["special-defense"]) // 2)
    bot_spd = normalize(stats["speed"])

    print(f"UPDATE pokemon_master SET base_hp={bot_hp}, base_atk={bot_atk}, "
          f"base_def={bot_def}, base_spd={bot_spd} WHERE id={i};")
```

**예상 소요:** 스크립트 30분 + 수동 밸런스 검수 1~2시간

### 3-9. 임팩트 분석

| 변화 | 설명 |
|------|------|
| **레어리티 역전 가능** | 강한 에픽(잠만보 합318) > 약한 전설(프리저 합315) |
| **같은 레어리티 내 다양성** | 리자몽 ≠ 윈디 ≠ 이상해꽃 (각각 고유 스탯) |
| **팀 구성 전략** | "ATK 특화 팀" vs "밸런스 팀" vs "탱커 팀" 등 |
| **티어표 전면 재편** | 현재 ATK 기반 → 종합 전투력 기반으로 변경 필요 |
| **수집 가치 증가** | 높은 종족값 + 높은 IV = 진정한 "강한 포켓몬" |

### 3-10. 리스크

| 리스크 | 심각도 | 완화 |
|--------|--------|------|
| **팀 서열 급변** | 높음 | 점진적 반영률 (50%→75%→100%) |
| **유저 혼란** | 중간 | 공지 + 대시보드 티어표 동시 업데이트 |
| **잉어킹이 너무 약함** | 낮음 | 의도된 디자인 (진화 시 갸라도스로 보상) |
| **251종 데이터 오류** | 중간 | 자동화 + 상위 50종 수동 검수 |

---

## 4. Phase 3: 타입 상성 확장

> **난이도:** ★★★☆☆ | **기간:** 2~3일 | **현실성:** ⚠️ 부분 가능 | **임팩트:** 중간

### 4-1. 현재: 10타입 간소화 상성

```
현재 10타입: normal, fire, water, grass, electric, ice, fighting, psychic, dragon, dark
누락 8타입: poison, ground, flying, bug, rock, ghost, steel, fairy
```

**현재 상성의 문제:**
- 리자몽이 fire 단타입 → 원작의 fire/flying 듀얼타입 미반영
- 팬텀이 psychic 단타입 → 원작의 ghost/poison 미반영
- 상성 관계가 단순해서 전략적 깊이 부족

### 4-2. 옵션 A: 18타입 확장 (원작 완전 반영)

**장점:** 원작 팬에게 친숙, 전략적 깊이 극대화
**단점:** 18×18 = 324개 상성 조합, 유저 학습 곡선 급등

```
추가 타입: poison, ground, flying, bug, rock, ghost, steel, fairy
듀얼타입: 리자몽(fire/flying), 팬텀(ghost/poison) 등

DB 변경:
  ALTER TABLE pokemon_master ADD COLUMN pokemon_type2 TEXT DEFAULT NULL;
```

**듀얼타입 데미지 계산:**
```python
# 공격 시: 두 타입 중 유리한 쪽 적용 (1.3x)
# 방어 시: 두 타입의 배수 곱 (2x, 1x, 0.5x, 0.25x, 0x)
attacker_mult = max(get_mult(atk_type, def_type1), get_mult(atk_type, def_type2))
```

### 4-3. 옵션 B: 14타입 절충안 (추천)

```
현재 10 + 추가 4 = 14타입
추가: ground, flying, ghost, steel
유지하지 않는: poison, bug, rock, fairy (게임 임팩트 낮거나 복잡도만 증가)
```

**이유:**
- ground: 전기 면역이 게임의 핵심 상성
- flying: 격투·풀 저항이 전략적으로 중요
- ghost: 노말 면역 + 에스퍼 상성
- steel: 드래곤·얼음 저항 탱커 역할

### 4-4. 옵션 C: 10타입 유지 + 듀얼타입만 추가

```
타입 수: 현재 10타입 유지
듀얼타입: pokemon_type2 추가
서브타입 영향: 0.5배 (메인타입 1.0배 대비)
```

**가장 안전한 옵션.** 새 타입 학습 부담 없이 전략적 다양성 증가.

### 4-5. 현실성 판단

| 옵션 | 작업량 | 유저 영향 | 추천도 |
|------|--------|----------|--------|
| A: 18타입 | 5일+ | 혼란 높음 | ❌ 보류 |
| B: 14타입 | 3일 | 적응 필요 | ⚠️ 유저 500+ 후 |
| C: 듀얼타입만 | 1~2일 | 낮음 | ✅ 추천 |

---

## 5. Phase 4: 성격(Nature) 시스템

> **난이도:** ★★☆☆☆ | **기간:** 1일 | **현실성:** ⚠️ UI 복잡도 문제 | **임팩트:** 중간

### 5-1. 간소화 성격 (10종)

원작 25종은 과다. 봇에 맞게 **10종으로 간소화:**

| 성격 | 한국어 | +10% | -10% | 설명 |
|------|--------|------|------|------|
| Adamant | 고집 | ATK | SPD | 느리지만 강한 |
| Jolly | 명랑 | SPD | ATK | 빠르지만 약한 |
| Bold | 대담 | DEF | ATK | 방어 특화 |
| Modest | 겸손 | ATK | DEF | 유리대포 |
| Careful | 신중 | DEF | SPD | 느린 탱커 |
| Timid | 소심 | SPD | DEF | 속도 특화 |
| Brave | 용감 | HP | SPD | 체력형 |
| Hasty | 성급 | SPD | HP | 극속도 |
| Relaxed | 여유 | HP | ATK | 순수 탱커 |
| Hardy | 노력 | - | - | 보정 없음 (중립) |

### 5-2. DB 변경

```sql
ALTER TABLE user_pokemon ADD COLUMN nature TEXT DEFAULT NULL;
-- 기존 포켓몬: 'hardy' (보정 없음) 배정
UPDATE user_pokemon SET nature = 'hardy' WHERE nature IS NULL;
```

### 5-3. 판단

**장점:** 같은 IV 같은 종족값이라도 성격에 따라 역할 차별화
**단점:** IV + 종족값 + 성격 = 유저가 이해해야 할 변수 3개 → 복잡도 급등

**결론:** Phase 1(IV) + Phase 2(종족값) 안정화 후 **유저 피드백 보고 결정.**

---

## 6. Phase 5: 노력값(EV) / 육성 시스템

> **난이도:** ★★★★☆ | **기간:** 1주+ | **현실성:** ❌ 현재 불가 | **임팩트:** 높음

### 6-1. 개요

포켓몬 사용(배틀, 밥, 놀기)으로 특정 스탯에 경험치를 쌓아 강화하는 시스템.
원작의 EV(Effort Value) 간소화 버전.

### 6-2. 간소화 안

```
총 투자 포인트: 100
스탯당 최대: 50
획득 방법:
  - 배틀 승리: +2 (랜덤 스탯)
  - 밥주기: +1 HP
  - 놀기: +1 SPD
  - 특수 아이템: +5 (지정 스탯)
```

### 6-3. 현실성 판단

**불가능한 이유:**
1. 현재 배틀이 자동 진행 → EV 투자 전략을 세울 UI가 없음
2. 밥/놀기 횟수가 일일 제한 있어서 EV 성장이 너무 느림
3. DB에 4개 추가 컬럼 필요 (ev_hp, ev_atk, ev_def, ev_spd)
4. 스탯 계산 복잡도: base × IV × EV × friendship × evo × nature = 변수 6개

**보류 조건:**
- 턴제 배틀 또는 수동 전투 시스템 도입 시
- 유저 수 1000+ 도달 시
- Phase 1~2 완전 안정화 후

---

## 7. 인프라 병목 & 한계 분석

### 7-1. Supabase Free Tier 한계

| 리소스 | 한도 | 현재 사용 | Phase 1 후 | Phase 2 후 | 풀 도입 후 |
|--------|------|----------|-----------|-----------|-----------|
| DB 용량 | 500MB | 29MB | 29.1MB | 29.1MB | 29.2MB |
| 동시 연결 | 60개 | ~5개 | ~5개 | ~5개 | ~5개 |
| Row 수 | 무제한 | ~55K | ~55K | ~55K | ~55K |
| API 요청 | 무제한 | - | - | - | - |

**DB 성장 예측 (포켓몬 증가):**

| 시점 | 포켓몬 수 | user_pokemon 크기 | IV 추가분 | 총 DB |
|------|----------|------------------|----------|-------|
| 현재 | 7,654 | 2.3MB | 0 | 29MB |
| 3개월 | ~30,000 | 9MB | 0.24MB | 40MB |
| 6개월 | ~80,000 | 24MB | 0.64MB | 60MB |
| 1년 | ~200,000 | 60MB | 1.6MB | 100MB |
| 2년 | ~500,000 | 150MB | 4MB | 200MB |

**결론:** 2년간 500MB 한도 내 안전. IV 추가 용량은 전체의 2% 미만.

### 7-2. 서버 성능 (Oracle Free: 1 OCPU, 1GB RAM)

| 연산 | 현재 복잡도 | Phase 1 후 | Phase 2 후 |
|------|-----------|-----------|-----------|
| 스탯 계산 | O(1) 사칙연산 | O(1) + DB 1회 | 동일 |
| 배틀 (6v6) | 12회 스탯계산 | 12회 + IV 로드 | 동일 |
| 포획 | DB 2~3회 | DB 3~4회 | 동일 |
| 티어표 API | 143종 루프 | 143종 + 종족값 | 동일 |

**병목 가능성:**
- 스탯 계산: 단순 곱셈 → **병목 없음**
- DB 조회: IV 4컬럼 추가 → 기존 SELECT에 포함되므로 **추가 쿼리 없음**
- 메모리: 종족값 251종 × 4스탯 = 1KB 캐시 → **무시 가능**

### 7-3. 실제 병목 지점 (IV/종족값과 무관)

| 병목 | 현재 상태 | 위험도 |
|------|----------|--------|
| **Supabase 동시 연결 60개** | 5개 사용 | 유저 500+에서 피크 시 도달 가능 |
| **Oracle 1GB RAM** | ~200MB 사용 | Python + asyncpg 풀 확장 시 위험 |
| **spawn_sessions 테이블 비대** | 13,336행/3MB | 6개월 후 10만행 → 인덱스 필요 |
| **catch_attempts 테이블** | 26,148행/3MB | 1년 후 30만행 → 주기적 정리 필요 |

---

## 8. 밸런스 임팩트 시뮬레이션

### 8-1. Phase 1 (IV만) — 같은 포켓몬 간 차이

```
리자몽 (epic/offensive, 친밀도 5)

IV D등급 (총합 20):  HP:202  ATK:97  DEF:60  SPD:75
IV B등급 (총합 62):  HP:243  ATK:117  DEF:72  SPD:90  ← 현재와 유사
IV S등급 (총합 120): HP:284  ATK:137  DEF:84  SPD:105

S급 vs D급 ATK 차이: 137 vs 97 = 41% 차이
→ 같은 레어리티 내에서 의미 있는 차이지만 레어리티 서열은 유지
→ IV D급 전설(ATK 123) > IV S급 에픽(ATK 137)? → 아직 전설이 유리
```

### 8-2. Phase 2 (종족값) — 다른 포켓몬 간 차이

```
잠만보 (epic) vs 프리저 (legendary) — 종족값 도입 후

잠만보: HP:360  ATK:107  DEF:83  SPD:48  (합계 318, HP 극특화)
프리저: HP:225  ATK:95   DEF:107 SPD:86  (합계 315, 밸런스)

→ 잠만보의 총 스탯합이 프리저보다 높음!
→ 에픽이 전설을 이기는 경우 발생
→ 의도된 디자인: "모든 전설 > 모든 에픽"이 아닌 "전설 평균 > 에픽 평균"
```

### 8-3. Phase 1+2 (IV + 종족값) — 최대 격차

```
최강 조합: 뮤츠 + IV S급 (31/31/31/31) + 친밀도 7 (이로치)
ATK = 117 × 1.28 × 1.0 × 1.2 = 179.7 → 180

최약 조합: 잉어킹 + IV D급 (0/0/0/0) + 친밀도 0 + 1단진화
ATK = 20 × 1.0 × 0.85 × 0.8 = 13.6 → 14

최강 vs 최약: 180 vs 14 = 12.9배 차이
현재: 148 vs 38 = 3.9배 차이

→ 격차는 커지지만, 이것은 "뮤츠 이로치 S급 vs 잉어킹 1단 D급"이라는 극단적 비교
→ 실전에서는 같은 티어 내 비교가 의미있음
```

---

## 9. 장기 로드맵 & 우선순위

### 우선순위 매트릭스

```
                    임팩트 높음
                        │
    Phase 2 (종족값)    │    Phase 1 (IV)
    ─ 3~5일            │    ─ 1~2일
    ─ 중간 리스크      │    ─ 낮은 리스크
                        │
  ──────────────────────┼──────────────────── 구현 난이도
                        │
    Phase 5 (EV)       │    Phase 4 (성격)
    ─ 1주+             │    ─ 1일
    ─ 현재 불가        │    ─ UI 복잡도
                        │
                    임팩트 낮음
```

### 실행 일정

```
[즉시]     Phase 1: IV 시스템 (1~2일)
              └─ 포획 시 IV 생성, 스탯 반영, UI 표시

[2주 후]   Phase 2: 종족값 개별화 (3~5일)
              ├─ 251종 데이터 자동화 + 검수
              ├─ 점진적 반영 (50% → 100%)
              └─ 티어표 & 대시보드 재편

[1개월 후] Phase 3C: 듀얼타입 (1~2일)
              └─ pokemon_type2 추가, 방어 시 서브타입 고려

[유저 피드백 후] Phase 4: 성격 (1일)
              └─ 유저가 원할 때만 도입

[장기 보류] Phase 5: EV / 노력값
              └─ 턴제 배틀 시스템 전환 시
```

### 각 Phase 독립성

```
Phase 1 (IV)         → 단독 도입 가능 ✅
Phase 2 (종족값)     → Phase 1 없이도 가능하나, 함께 하면 최적
Phase 3 (타입 확장)  → 완전 독립, 아무 때나 가능
Phase 4 (성격)       → Phase 1 필요 (IV + 성격 = 개체 차별화)
Phase 5 (EV)         → Phase 1+2 선행 필요
```

---

## 부록 A: 원작 포켓몬 타입 상성표 (18타입)

```
공격↓  방어→  노 불 물 풀 전 얼 격 독 땅 비 에 벌 바 고 드 악 강 페
노말     ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ½  0  ·  ·  ½  ·
불꽃     ·  ½  ½  2  ·  2  ·  ·  ·  ·  ·  2  ½  ·  ½  ·  2  ·
물       ·  2  ½  ½  ·  ·  ·  ·  2  ·  ·  ·  2  ·  ½  ·  ·  ·
풀       ·  ½  2  ½  ·  ·  ·  ½  2  ½  ·  ½  2  ·  ½  ·  ½  ·
전기     ·  ·  2  ½  ½  ·  ·  ·  0  2  ·  ·  ·  ·  ½  ·  ·  ·
얼음     ·  ½  ½  2  ·  ½  ·  ·  2  2  ·  ·  ·  ·  2  ·  ½  ·
격투     2  ·  ·  ·  ·  2  ·  ½  ·  ½  ½  ½  2  0  ·  2  2  ½
독       ·  ·  ·  2  ·  ·  ·  ½  ½  ·  ·  ·  ½  ½  ·  ·  0  2
땅       ·  2  ·  ½  2  ·  ·  2  ·  0  ·  ½  2  ·  ·  ·  2  ·
비행     ·  ·  ·  2  ½  ·  2  ·  ·  ·  ·  2  ½  ·  ·  ·  ½  ·
에스퍼   ·  ·  ·  ·  ·  ·  2  2  ·  ·  ½  ·  ·  ·  ·  0  ½  ·
벌레     ·  ½  ·  2  ·  ·  ½  ½  ·  ½  2  ·  ·  ½  ·  2  ½  ½
바위     ·  2  ·  ·  ·  2  ½  ·  ½  2  ·  2  ·  ·  ·  ·  ½  ·
고스트   0  ·  ·  ·  ·  ·  ·  ·  ·  ·  2  ·  ·  2  ·  ½  ·  ·
드래곤   ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  2  ·  ½  0
악       ·  ·  ·  ·  ·  ·  ½  ·  ·  ·  2  ·  ·  2  ·  ½  ·  ½
강철     ·  ½  ½  ·  ½  2  ·  ·  ·  ·  ·  ·  2  ·  ·  ·  ½  2
페어리   ·  ½  ·  ·  ·  ·  2  ½  ·  ·  ·  ·  ·  ·  2  2  ½  ·

범례: 2=효과적, ½=별로, 0=면역, ·=보통
```

## 부록 B: 원작 성격 25종 전체 목록

```
         -ATK    -DEF    -SpA    -SpD    -SPD
+ATK    *고집    외로운   고집     장난     용감
+DEF     대담   *온순    개구쟁이  촐랑     여유
+SpA     겸손    말랑     *수줍    덜렁     냉정
+SpD     차분    얌전    신중     *변덕    건방
+SPD     소심    성급    명랑     천진     *성실

*표시: 중립 (보정 없음)
```

---

*이 문서는 dev 브랜치에서 관리되며, 각 Phase 구현 시 세부 구현 명세로 분리됩니다.*
