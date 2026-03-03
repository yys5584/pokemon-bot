# 개체값(IV) 시스템 & 실제 종족값 반영 기획안

> 작성일: 2026-03-04
> 대상: TG 포켓몬 봇 (텔레그램)
> 현재 유저: 385명, 보유 포켓몬: 7,654마리, DB: 29MB/500MB

---

## 1. 현재 시스템 분석

### 현재 스탯 계산 (battle_calc.py)
```
HP  = base × 3 × spread[hp]  × (1 + friendship×0.04) × evo_mult
ATK = base     × spread[atk] × (1 + friendship×0.04) × evo_mult
DEF = base     × spread[def] × (1 + friendship×0.04) × evo_mult
SPD = base     × spread[spd] × (1 + friendship×0.04) × evo_mult
```

**입력 변수 (4개):**
| 변수 | 값 | 비고 |
|------|-----|------|
| base (레어리티) | common:45, rare:60, epic:75, legendary:95 | 레어리티별 고정 |
| spread (성향) | offensive/defensive/balanced/speedy | 포켓몬별 고정 |
| friendship | 0~5 (이로치 0~7) | 유저 육성 |
| evo_mult | 1단:0.85, 2단:0.92, 최종:1.0 | 진화단계 고정 |

### 현재 문제점
- **같은 포켓몬 = 같은 스탯**: 리자몽 A와 리자몽 B가 친밀도만 같으면 완전히 동일
- **레어리티만으로 강함 결정**: 전설 > 에픽 > 레어 > 커먼 고정 서열
- **개체 간 차별화 없음**: 수집/육성 동기 부족
- **실제 포켓몬 종족값 미반영**: 리자몽과 잠만보의 스탯 분포가 성향(offensive/defensive)으로만 구분

---

## 2. 제안: 3단계 로드맵

### Phase 1: 개체값(IV) 도입 ✅ 현실적 / 단기 (1-2일)

**개요:** 포켓몬 포획 시 0~31 사이 개체값 4개(HP/ATK/DEF/SPD)를 랜덤 부여

**DB 변경:**
```sql
ALTER TABLE user_pokemon ADD COLUMN iv_hp SMALLINT DEFAULT NULL;
ALTER TABLE user_pokemon ADD COLUMN iv_atk SMALLINT DEFAULT NULL;
ALTER TABLE user_pokemon ADD COLUMN iv_def SMALLINT DEFAULT NULL;
ALTER TABLE user_pokemon ADD COLUMN iv_spd SMALLINT DEFAULT NULL;
```
- 4컬럼 × 2바이트 = 포켓몬당 8바이트 추가
- 7,654마리 × 8B = **61KB** 추가 (무시할 수준)
- 향후 10만마리까지 0.8MB (문제없음)

**스탯 공식 변경:**
```
ATK = base × spread[atk] × (1 + friendship×0.04) × evo_mult × (0.8 + iv_atk/31 × 0.4)
```
- IV 0 → 0.8배 (하위), IV 31 → 1.2배 (상위)
- IV 영향범위: ±20% (원작 대비 완화, 밸런스 유지)

**IV 등급 시스템:**
| 총합 (0~124) | 등급 | 확률 | 표시 |
|-------------|------|------|------|
| 112~124 | S (최상) | ~3% | ⭐⭐⭐ |
| 93~111 | A (상) | ~15% | ⭐⭐ |
| 62~92 | B (중) | ~50% | ⭐ |
| 31~61 | C (하) | ~25% | - |
| 0~30 | D (최하) | ~7% | - |

**이로치 보너스:** IV 최소값 10 보장 (일반: 0~31, 이로치: 10~31)

**UI 표시:**
```
📦 내포켓몬 상세:
🟡 리자몽 ⭐⭐⭐ (IV: S)
HP 156  ATK 189  DEF 98  SPD 134
개체값: 28/31/22/29 (총합 109/124)
```

**영향 범위:**
- `battle_calc.py`: calc_battle_stats()에 iv 파라미터 추가
- `spawn_service.py`: 포획 시 IV 생성 로직
- `dm_pokedex.py`: 상세 화면에 IV 표시
- `battle.py`: 팀 표시에 IV 등급 표시

**병목/리스크:**
- 기존 7,654마리의 IV가 NULL → 레거시 처리 필요 (NULL이면 IV 15/15/15/15로 간주, 또는 최초 조회 시 랜덤 배정)
- 배틀 밸런스 변동 (최대 ±20% 스윙)

---

### Phase 2: 종족값(Base Stats) 개별화 ⚠️ 중간 난이도 / 중기 (3-5일)

**개요:** 현재 레어리티 기반 단일 base값(45/60/75/95) → 포켓몬별 개별 종족값

**DB 변경:**
```sql
ALTER TABLE pokemon_master ADD COLUMN base_hp SMALLINT DEFAULT NULL;
ALTER TABLE pokemon_master ADD COLUMN base_atk SMALLINT DEFAULT NULL;
ALTER TABLE pokemon_master ADD COLUMN base_def SMALLINT DEFAULT NULL;
ALTER TABLE pokemon_master ADD COLUMN base_spd SMALLINT DEFAULT NULL;
```
- 251종 × 8B = **2KB** (무시할 수준)

**데이터 소스:** 원작 종족값 기반 + 게임 밸런스 조정
- 원작 종족값 범위: HP 1~255, ATK 5~190, DEF 5~230, SPD 5~180
- 봇 밸런스 범위: 20~180 (정규화)

**정규화 공식:**
```python
# 원작 종족값을 봇 밸런스 범위로 매핑
bot_stat = 20 + (original_stat / 255) * 160
```

**예시 (정규화 후):**
| 포켓몬 | HP | ATK | DEF | SPD | 특성 |
|--------|-----|------|------|------|------|
| 리자몽 | 68 | 134 | 68 | 120 | 고화력 유리포 |
| 잠만보 | 180 | 80 | 75 | 40 | 초고체력 탱커 |
| 라이츄 | 52 | 100 | 52 | 128 | 속도형 딜러 |
| 뮤츠 | 116 | 170 | 100 | 150 | 올라운더 최강 |
| 잉어킹 | 32 | 20 | 52 | 96 | 최약체 |

**스탯 공식 변경:**
```
ATK = base_atk × (1 + friendship×0.04) × evo_mult × (0.8 + iv_atk/31 × 0.4)
```
- `base × spread[atk]` 대신 `base_atk` 직접 사용
- stat_type 컬럼은 유지 (타입 상성 힌트로 활용)

**밸런스 영향:**
- 같은 레어리티 내에서도 강약 차이 발생 (이게 목적)
- 레어리티 서열 역전 가능 (예: 강한 에픽 > 약한 전설)
- 티어표 완전 재편 필요

**작업량:**
1. 251종 종족값 데이터 입력 (가장 노동집약적)
   - 원작 데이터 크롤링 후 정규화 스크립트로 자동화 가능
   - 수동 밸런스 조정 최소 1시간
2. battle_calc.py 공식 변경
3. 티어표 API 재계산
4. pokemon_master 시드 데이터 업데이트

**병목/리스크:**
- **밸런스 붕괴**: 종족값 도입 시 기존 팀 구성이 무의미해질 수 있음
  - 완화: 점진적 도입 (처음엔 종족값 차이를 50%만 반영)
- **데이터 입력 노동**: 251종 × 4스탯 = 1004개 수치
  - 완화: 원작 데이터 자동 매핑 스크립트
- **stat_type 컬럼과의 충돌**: 기존 성향 시스템 제거해야 할 수 있음

---

### Phase 3: 성격/특성/상성 확장 ❌ 장기 / 복잡도 높음 (2주+)

**3-A. 성격(Nature) 시스템**
- 25가지 성격 중 포획 시 랜덤 부여
- 2개 스탯에 ±10% 영향 (예: "용감한" → ATK+10%, SPD-10%)
- DB: user_pokemon에 `nature` TEXT 컬럼 1개 추가

**현실성:** ⚠️ 구현은 간단하나 UI/UX 복잡도 폭증. 유저가 이해해야 할 변수가 너무 많아짐.

**3-B. 특성(Ability) 시스템**
- 포켓몬별 1~2개 특성 보유 (포획 시 랜덤)
- 배틀 시 특수 효과 발동 (예: "위협" → 상대 ATK -10%, "가속" → 매 턴 SPD +10%)
- DB: pokemon_master에 abilities JSON, user_pokemon에 ability TEXT

**현실성:** ❌ 배틀 로직 전면 재설계 필요. 현재 배틀은 단순 스탯 비교인데, 특성은 턴제 배틀과 맞물려야 의미있음.

**3-C. 타입 상성 확장 (18타입)**
- 현재 10타입 → 원작 18타입 (독, 땅, 비행, 벌레, 바위, 고스트, 강철, 페어리)
- 듀얼타입 지원 (예: 리자몽 = 불/비행)

**현실성:** ⚠️ 기술적으로 가능하나 18×18 상성표는 유저 학습 곡선이 급격히 높아짐.
- 타협안: 현재 10타입 유지하되, 듀얼타입만 추가 (서브타입 0.5배 영향)

---

## 3. 병목 & 리스크 분석

### DB 용량 (Supabase Free: 500MB)

| 시나리오 | 현재 | +10만마리 | +50만마리 |
|---------|------|----------|----------|
| user_pokemon (기본) | 2.3MB | 30MB | 150MB |
| +IV 4컬럼 | +61KB | +0.8MB | +4MB |
| +종족값 (master) | +2KB | +2KB | +2KB |
| spawn_sessions | 3MB | 20MB | 100MB |
| **합계 예상** | **29MB** | **~80MB** | **~300MB** |

**결론:** 50만마리까지 500MB 안에 들어옴. IV 추가는 DB에 거의 영향 없음.

### 서버 성능 (Oracle Free: 1 OCPU, 1GB RAM)

| 연산 | 현재 | IV 추가 후 | 종족값 추가 후 |
|------|------|-----------|-------------|
| 스탯 계산 | O(1) 메모리 | O(1) + DB 1회 조회 | 동일 |
| 배틀 (6v6) | ~12회 계산 | 동일 | 동일 |
| 스폰/포획 | DB 2~3회 | DB 3~4회 (+IV 저장) | 동일 |
| 대시보드 티어 | 143종 루프 | 동일 | 종족값 기반 재계산 |

**결론:** 성능 병목 없음. 모든 연산이 단순 사칙연산이라 CPU/메모리 영향 미미.

### 밸런스 리스크

| 리스크 | 심각도 | 완화 방안 |
|--------|--------|----------|
| IV 격차로 같은 포켓몬 간 20% 차이 | 낮음 | 원작보다 낮은 영향도 (±20%) |
| 기존 팀 밸런스 붕괴 (종족값) | 높음 | 점진적 반영률 (50% → 75% → 100%) |
| 유저 혼란 (너무 많은 변수) | 중간 | Phase 1만 먼저, UI 단순하게 |
| 기존 포켓몬 IV NULL 처리 | 중간 | 기본값 15 또는 최초 조회 시 랜덤 |

---

## 4. 추천 실행 계획

### 즉시 실행 가능: Phase 1 (IV)
```
Day 1: DB 마이그레이션 + battle_calc 수정 + 포획 시 IV 생성
Day 2: UI 표시 (내포켓몬 상세, 포획 메시지) + 기존 포켓몬 IV 배정
```

### 2주 후: Phase 2 (종족값)
```
Day 1: 원작 데이터 크롤링 + 정규화 스크립트
Day 2: pokemon_master 업데이트 + battle_calc 공식 변경
Day 3: 밸런스 테스트 + 티어표 재생성
Day 4: 유저 공지 + 라이브 배포
```

### Phase 3은 보류
- 성격/특성은 턴제 배틀 시스템 전환 시에만 의미있음
- 타입 확장은 유저 수 500+ 이후 검토

---

## 5. Phase 1 상세 구현 스펙

### 5-1. DB 마이그레이션
```sql
-- user_pokemon에 IV 컬럼 추가
ALTER TABLE user_pokemon ADD COLUMN iv_hp SMALLINT DEFAULT NULL;
ALTER TABLE user_pokemon ADD COLUMN iv_atk SMALLINT DEFAULT NULL;
ALTER TABLE user_pokemon ADD COLUMN iv_def SMALLINT DEFAULT NULL;
ALTER TABLE user_pokemon ADD COLUMN iv_spd SMALLINT DEFAULT NULL;

-- 기존 포켓몬에 랜덤 IV 배정 (10~25 범위, 완전 랜덤보다 후한 편)
UPDATE user_pokemon SET
    iv_hp = floor(random() * 16 + 10)::smallint,
    iv_atk = floor(random() * 16 + 10)::smallint,
    iv_def = floor(random() * 16 + 10)::smallint,
    iv_spd = floor(random() * 16 + 10)::smallint
WHERE iv_hp IS NULL;
```

### 5-2. IV 생성 로직 (spawn_service.py)
```python
import random

def generate_iv(is_shiny: bool = False) -> dict:
    """Generate IV values for a newly caught pokemon."""
    min_val = 10 if is_shiny else 0
    return {
        "iv_hp": random.randint(min_val, 31),
        "iv_atk": random.randint(min_val, 31),
        "iv_def": random.randint(min_val, 31),
        "iv_spd": random.randint(min_val, 31),
    }

def iv_grade(iv_hp, iv_atk, iv_def, iv_spd) -> tuple[str, str]:
    """Return (grade_letter, display_stars) for IV total."""
    total = iv_hp + iv_atk + iv_def + iv_spd
    if total >= 112: return ("S", "⭐⭐⭐")
    if total >= 93: return ("A", "⭐⭐")
    if total >= 62: return ("B", "⭐")
    if total >= 31: return ("C", "")
    return ("D", "")
```

### 5-3. 스탯 공식 변경 (battle_calc.py)
```python
def calc_battle_stats(rarity, stat_type, friendship, evo_stage=3,
                      iv_hp=15, iv_atk=15, iv_def=15, iv_spd=15):
    base = BASE_STATS[rarity]
    spread = STAT_SPREADS[stat_type]
    evo_mult = EVO_MULTIPLIERS[evo_stage]
    friend_mult = 1 + friendship * 0.04

    def iv_mult(iv):
        return 0.8 + (iv / 31) * 0.4  # IV 0 = 0.8x, IV 31 = 1.2x

    return {
        "hp": round(base * 3 * spread["hp"] * friend_mult * evo_mult * iv_mult(iv_hp)),
        "atk": round(base * spread["atk"] * friend_mult * evo_mult * iv_mult(iv_atk)),
        "def": round(base * spread["def"] * friend_mult * evo_mult * iv_mult(iv_def)),
        "spd": round(base * spread["spd"] * friend_mult * evo_mult * iv_mult(iv_spd)),
    }
```

### 5-4. 포획 메시지 변경
```
현재: 딸깍! ✨ 배즘 — 🟡리자몽 포획!
변경: 딸깍! ✨ 배즘 — 🟡리자몽 포획! ⭐⭐⭐(S)
```

### 5-5. 내포켓몬 상세 변경
```
현재:
🟡 리자몽
❤️❤️❤️❤️❤️ (친밀도 5)

변경:
🟡 리자몽 ⭐⭐⭐ (IV: S)
❤️❤️❤️❤️❤️ (친밀도 5)
HP 156  ATK 189  DEF 98  SPD 134
IV: 28/31/22/29 (총합 110/124)
```

---

## 6. FAQ

**Q: 기존 포켓몬의 밸런스가 깨지지 않나?**
A: 기존 포켓몬에 10~25 범위의 IV를 부여하므로 평균적으로 현재와 유사. 신규 포획 포켓몬만 0~31 풀 범위.

**Q: IV 때문에 배틀 결과가 크게 바뀌나?**
A: IV의 최대 영향은 ±20%. 레어리티 차이(45 vs 95)에 비하면 작음. 같은 레어리티 내에서 미세 차이를 만드는 용도.

**Q: 종족값 없이 IV만 넣으면 의미있나?**
A: 있음. "같은 리자몽이라도 내 리자몽이 더 강할 수 있다"는 수집 동기 부여. 종족값은 "리자몽과 잠만보가 다르다"를 구현하는 것이고, IV는 "내 리자몽과 네 리자몽이 다르다"를 구현하는 것.

**Q: Supabase Free Tier에서 문제없나?**
A: 현재 29MB/500MB. IV 추가 시 50만마리까지도 300MB 이내. 병목은 DB 용량이 아닌 동시 연결 수(Supabase Free: 60개)이나, 현재 유저 규모로는 문제없음.
