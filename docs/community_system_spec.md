# 채팅방 레벨 시스템 구현 기획서
> 작성일: 2026-03-08 | 기반: feature_proposals.md #2

---

## 개요

채팅방 레벨 시스템을 구현하여:
- 채널 운영자에게 봇 유지 인센티브 제공 (레벨이 높은 방 = 좋은 방)
- 유저 활동량 증가 (레벨업 → 이로치 확정 스폰, 아케이드 등 확실한 보상)
- 채팅방 소속감 강화

**기존 인프라 활용:**
- `chat_rooms.spawn_multiplier` → 레벨별 스폰 보너스에 연결
- `chat_activity` 테이블 → CXP 보조 지표
- `spawn_service.schedule_spawns_for_chat()` → 레벨 보너스 + 이로치 확정 스폰 주입
- `arcade_passes` 테이블 → Lv.8 자동 아케이드에 재사용

---

## 1. DB 스키마

```sql
-- chat_rooms 테이블에 컬럼 추가 (새 테이블 X, 기존 확장)
ALTER TABLE chat_rooms ADD COLUMN cxp INTEGER NOT NULL DEFAULT 0;
ALTER TABLE chat_rooms ADD COLUMN chat_level INTEGER NOT NULL DEFAULT 1;
ALTER TABLE chat_rooms ADD COLUMN cxp_today INTEGER NOT NULL DEFAULT 0;

-- 일일 CXP 기록 (분석용)
CREATE TABLE IF NOT EXISTS chat_cxp_log (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT REFERENCES chat_rooms(chat_id),
    action TEXT NOT NULL,          -- 'catch', 'battle', 'trade'
    user_id BIGINT,
    amount INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_cxp_log_chat ON chat_cxp_log(chat_id, created_at);
```

**chat_rooms 기존 테이블 확장 이유:**
- 별도 `chat_levels` 테이블을 만들면 JOIN 필요 → 스폰 스케줄링 시 쿼리 복잡
- `chat_rooms`에 3개 컬럼 추가가 더 단순

---

## 2. CXP (채팅방 경험치) 적립 규칙

| 행동 | CXP | 적립 위치 (코드) |
|------|-----|-----------------|
| 포켓몬 포획 성공 | +1 | `handlers/group.py` catch 성공 후 |
| 채팅방 내 배틀 완료 | +2 | `handlers/battle.py` 배틀 결과 콜백 |
| 교환 완료 | +1 | `services/trade_service.py` 교환 성공 후 |
| 강제스폰 사용 | +1 | `handlers/group.py` 강스권 사용 시 |

**일일 CXP 상한: 50** (어뷰징 방지)
- `cxp_today` 컬럼으로 추적
- 자정 리셋 시 `cxp_today = 0` 초기화 (`midnight_reset`에 추가)

---

## 3. 레벨 테이블 & 혜택

### 핵심 설계 원칙
- **이로치 확률**: Lv.2부터 +0.2%씩 점진적 증가 (Lv.10에서 +1.8%)
- **이로치 확정 스폰**: 일일 보너스 스폰 중 1회는 이로치 확정 (레벨이 가져다주는 확실한 메리트)
- **Lv.8 아케이드**: 매일 자동 1시간 아케이드 (기존 아케이드 패스 시스템 재사용)

| 레벨 | 필요 누적CXP | 혜택 | 구현 |
|------|-------------|------|------|
| Lv.1 | 0 | 기본 | - |
| Lv.2 | 100 | 스폰 +1, **이로치 +0.2%** | spawn_bonus, shiny_boost |
| Lv.3 | 300 | 에픽 +10%, **이로치 +0.4%** | rarity_boost |
| Lv.4 | 600 | 스폰 +2, 전설 +5%, **이로치 +0.6%**, **✨일일 이로치 확정 스폰 1회** | daily_shiny_spawn |
| Lv.5 | 1000 | 명예의 전당, **이로치 +0.8%** | 최초포획 기록 표시 |
| Lv.6 | 1500 | 스폰 +3, 에픽 +15%, **이로치 +1.0%** | spawn_bonus 증가 |
| Lv.7 | 2000 | 전설 +10%, **이로치 +1.2%** | rarity_boost 증가 |
| Lv.8 | 3000 | **🎮 일일 자동 아케이드 1시간**, **이로치 +1.4%** | auto_arcade |
| Lv.9 | 5000 | 스폰 +4, 에픽 +20%, **이로치 +1.7%** | spawn_bonus 최대 |
| Lv.10 | 8000 | 전설 +15%, **이로치 +2.0%**, 채팅방 리더보드 | 대시보드 연동 |

### 혜택 누적 요약

| 레벨 | 스폰 보너스 | 에픽 보정 | 전설 보정 | 이로치 보정 | 특수 혜택 |
|------|-----------|----------|----------|-----------|----------|
| 1 | +0 | - | - | - | - |
| 2 | +1 | - | - | +0.2% | - |
| 3 | +1 | +10% | - | +0.4% | - |
| 4 | +2 | +10% | +5% | +0.6% | ✨ 일일 이로치 확정 1회 |
| 5 | +2 | +10% | +5% | +0.8% | 명예의 전당 |
| 6 | +3 | +15% | +5% | +1.0% | - |
| 7 | +3 | +15% | +10% | +1.2% | - |
| 8 | +3 | +15% | +10% | +1.4% | 🎮 일일 아케이드 1시간 |
| 9 | +4 | +20% | +10% | +1.7% | - |
| 10 | +4 | +20% | +15% | +2.0% | 리더보드 |

---

## 4. config.py 추가

```python
# ─── 채팅방 레벨 ─────────────────────────────────
# (level, required_cxp, spawn_bonus, shiny_boost_pct, rarity_boosts, special)
CHAT_LEVEL_TABLE = [
    # special: None, "daily_shiny", "auto_arcade", "leaderboard"
    (1,  0,     0, 0.0, {},                                    None),
    (2,  100,   1, 0.2, {},                                    None),
    (3,  300,   1, 0.4, {"epic": 1.10},                        None),
    (4,  600,   2, 0.6, {"epic": 1.10, "legendary": 1.05},     "daily_shiny"),
    (5,  1000,  2, 0.8, {"epic": 1.10, "legendary": 1.05},     "hall_of_fame"),
    (6,  1500,  3, 1.0, {"epic": 1.15, "legendary": 1.05},     None),
    (7,  2000,  3, 1.2, {"epic": 1.15, "legendary": 1.10},     None),
    (8,  3000,  3, 1.4, {"epic": 1.15, "legendary": 1.10},     "auto_arcade"),
    (9,  5000,  4, 1.7, {"epic": 1.20, "legendary": 1.10},     None),
    (10, 8000,  4, 2.0, {"epic": 1.20, "legendary": 1.15},     "leaderboard"),
]

CXP_PER_CATCH = 1
CXP_PER_BATTLE = 2
CXP_PER_TRADE = 1
CXP_PER_FORCE_SPAWN = 1
CXP_DAILY_CAP = 50
AUTO_ARCADE_DURATION = 3600  # Lv.8 자동 아케이드 (1시간, 초)

def get_chat_level_info(cxp: int):
    """CXP로 현재 레벨 + 혜택 조회."""
    result = CHAT_LEVEL_TABLE[0]
    for row in CHAT_LEVEL_TABLE:
        if cxp >= row[1]:
            result = row
        else:
            break
    level, req_cxp, spawn_bonus, shiny_pct, rarity_boosts, special = result

    # 다음 레벨까지 남은 CXP
    next_cxp = None
    for row in CHAT_LEVEL_TABLE:
        if row[1] > cxp:
            next_cxp = row[1]
            break

    # 이 레벨 이하의 모든 special 혜택 수집
    specials = set()
    for row in CHAT_LEVEL_TABLE:
        if row[0] <= level and row[5]:
            specials.add(row[5])

    return {
        "level": level,
        "spawn_bonus": spawn_bonus,
        "shiny_boost_pct": shiny_pct,     # +0.2% 단위
        "rarity_boosts": rarity_boosts,
        "specials": specials,              # {"daily_shiny", "auto_arcade", ...}
        "next_cxp": next_cxp,             # None이면 MAX
    }
```

---

## 5. queries.py 추가 함수

```python
async def add_chat_cxp(chat_id: int, amount: int, action: str, user_id: int = None):
    """CXP 적립 (일일 상한 체크). 레벨업 시 new_level 반환."""
    pool = await get_db()

    row = await pool.fetchrow(
        "SELECT cxp, chat_level, cxp_today FROM chat_rooms WHERE chat_id = $1",
        chat_id,
    )
    if not row or row["cxp_today"] >= config.CXP_DAILY_CAP:
        return None

    actual = min(amount, config.CXP_DAILY_CAP - row["cxp_today"])
    new_cxp = row["cxp"] + actual

    info = config.get_chat_level_info(new_cxp)
    new_level = info["level"]
    leveled_up = new_level > row["chat_level"]

    await pool.execute(
        """UPDATE chat_rooms
           SET cxp = $1, chat_level = $2, cxp_today = cxp_today + $3
           WHERE chat_id = $4""",
        new_cxp, new_level, actual, chat_id,
    )

    # 로그
    await pool.execute(
        """INSERT INTO chat_cxp_log (chat_id, action, user_id, amount)
           VALUES ($1, $2, $3, $4)""",
        chat_id, action, user_id, actual,
    )

    return new_level if leveled_up else None


async def get_chat_level(chat_id: int):
    """채팅방 레벨 정보 조회."""
    pool = await get_db()
    row = await pool.fetchrow(
        "SELECT cxp, chat_level, cxp_today FROM chat_rooms WHERE chat_id = $1",
        chat_id,
    )
    if not row:
        return {"cxp": 0, "chat_level": 1, "cxp_today": 0}
    return dict(row)


async def reset_daily_cxp():
    """자정에 cxp_today 리셋."""
    pool = await get_db()
    await pool.execute("UPDATE chat_rooms SET cxp_today = 0")
```

---

## 6. 일일 이로치 확정 스폰 (Lv.4+)

### 메커니즘

Lv.4 이상 채팅방은 매일 **1회** 이로치가 확정으로 출현한다.
기존 스폰 스케줄러에서 보너스 스폰 중 1개를 `force_shiny=True`로 마킹.

### 구현 (`spawn_service.py`)

```python
async def schedule_spawns_for_chat(app, chat_id):
    ...
    # 레벨 보너스 계산
    chat_data = await queries.get_chat_level(chat_id)
    level_info = config.get_chat_level_info(chat_data["cxp"])
    level_bonus = level_info["spawn_bonus"]

    num_spawns = min(SPAWN_MAX_DAILY,
                     max(1, int(base_spawns * chat_mult * event_mult) + level_bonus))

    # 스폰 시간 랜덤 배정
    spawn_times = _generate_spawn_times(num_spawns, ...)

    # ★ Lv.4+ 이로치 확정 스폰: 보너스 스폰 중 1개를 force_shiny로
    shiny_spawn_idx = None
    if "daily_shiny" in level_info["specials"] and level_bonus > 0:
        # 보너스 스폰 구간(뒤쪽) 중 랜덤 1개 선택
        bonus_start = num_spawns - level_bonus
        shiny_spawn_idx = random.randint(bonus_start, num_spawns - 1)

    for i, spawn_time in enumerate(spawn_times):
        force_shiny = (i == shiny_spawn_idx)
        app.job_queue.run_once(
            execute_spawn, spawn_time,
            data={"chat_id": chat_id, "force_shiny": force_shiny},
            name=f"spawn_{chat_id}_{i}",
        )
```

### `execute_spawn()` 수정

```python
async def execute_spawn(context):
    data = context.job.data
    chat_id = data["chat_id"]
    force_shiny = data.get("force_shiny", False)

    # 포켓몬 선택 (기존 로직)
    pokemon = select_random_pokemon(chat_id, ...)

    # ★ 이로치 확정
    if force_shiny:
        is_shiny = True
    else:
        # 기존 이로치 판정 로직 + 레벨 보정
        chat_data = await queries.get_chat_level(chat_id)
        level_info = config.get_chat_level_info(chat_data["cxp"])
        shiny_boost = level_info["shiny_boost_pct"]  # 0.2~1.8
        base_shiny_rate = config.SHINY_RATE  # 기존 기본 확률
        is_shiny = random.random() < (base_shiny_rate + shiny_boost / 100)

    ...
```

### 이로치 확정 스폰 메시지 차별화

```
✨🌟 채팅방 보너스! 이로치 포켓몬이 출현했습니다! 🌟✨
```
- 일반 스폰과 구분되는 특별 메시지
- "채팅방 레벨 혜택"임을 명시 → 레벨 시스템 인지도 향상

---

## 7. 일일 자동 아케이드 (Lv.8+)

### 메커니즘

Lv.8 이상 채팅방은 매일 **자동으로 1시간 아케이드**가 활성화된다.
기존 `arcade_passes` 시스템을 그대로 재사용.

### 구현

**자정 리셋 시 자동 생성 (`main.py` midnight_reset 내부):**

```python
async def _activate_auto_arcades():
    """Lv.8+ 채팅방에 자동 아케이드 1시간 생성."""
    pool = await get_db()
    # Lv.8+ 채팅방 목록
    rows = await pool.fetch(
        "SELECT chat_id FROM chat_rooms WHERE chat_level >= 8 AND is_active = 1"
    )
    for row in rows:
        chat_id = row["chat_id"]
        # 이미 활성 아케이드가 있으면 스킵
        existing = await queries.get_active_arcade_pass(chat_id)
        if existing:
            continue
        # 오전 시간대에 자동 활성화 (10시~12시 사이 랜덤)
        delay = random.randint(0, 7200)  # 0~2시간 랜덤 딜레이
        # 1시간 후 만료
        await queries.create_arcade_pass(
            chat_id, user_id=0,  # system-generated
            duration_seconds=config.AUTO_ARCADE_DURATION,
        )
        # 스폰 스케줄링
        await schedule_arcade_spawns(app, chat_id)
```

**활성화 시 채팅방 알림:**

```
🎮 채팅방 레벨 혜택! 아케이드 모드 1시간 자동 활성화!
━━━━━━━━━━━━━━
⏰ 남은 시간: 60분
🎯 30초마다 포켓몬 출현!
━━━━━━━━━━━━━━
💡 Lv.8 이상 채팅방의 매일 혜택입니다.
```

### 기존 아케이드와 차이

| | 티켓 아케이드 | Lv.8 자동 아케이드 |
|---|---|---|
| 활성화 | 유저가 티켓 사용 | 매일 자동 |
| 시간 | 1시간 | 1시간 |
| 비용 | 아케이드 티켓 소모 | 무료 (레벨 혜택) |
| 중복 | 가능 | 기존 활성 아케이드 있으면 스킵 |
| 스폰 간격 | 30초 (영구) / 60초 (임시) | 60초 (임시와 동일) |

---

## 8. CXP 적립 Hook 위치

### 포획 성공 시 (`handlers/group.py`)
```python
# catch 성공 후 기존 코드 뒤에 추가:
asyncio.create_task(_add_cxp_bg(chat_id, config.CXP_PER_CATCH, "catch", user_id, context))
```

### 배틀 완료 시 (`handlers/battle.py`)
```python
# 배틀 결과 콜백에서 채팅방 배틀인 경우:
if chat_id and chat_id < 0:  # 그룹 채팅
    asyncio.create_task(_add_cxp_bg(chat_id, config.CXP_PER_BATTLE, "battle", user_id, context))
```

### 교환 완료 시 (`services/trade_service.py`)
```python
# 교환 성공 후 (채팅방 chat_id가 있으면):
asyncio.create_task(_add_cxp_bg(chat_id, config.CXP_PER_TRADE, "trade", user_id, None))
```

### 공통 백그라운드 함수
```python
async def _add_cxp_bg(chat_id, amount, action, user_id, context):
    """CXP 적립 + 레벨업 알림 (논블로킹)."""
    try:
        new_level = await queries.add_chat_cxp(chat_id, amount, action, user_id)
        if new_level and context:
            benefit = _level_benefit_text(new_level)
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"🎊 <b>채팅방 레벨 UP!</b>\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"🏅 Lv.{new_level} 달성!\n"
                    f"{benefit}\n"
                    f"━━━━━━━━━━━━━━"
                ),
                parse_mode="HTML",
            )
    except Exception:
        pass


def _level_benefit_text(level: int) -> str:
    """레벨업 시 표시할 혜택 텍스트."""
    info = config.get_chat_level_info(
        config.CHAT_LEVEL_TABLE[level - 1][1]  # 해당 레벨의 req_cxp
    )
    lines = []
    if info["spawn_bonus"]:
        lines.append(f"📦 일일 스폰 +{info['spawn_bonus']}회")
    if info["shiny_boost_pct"]:
        lines.append(f"✨ 이로치 확률 +{info['shiny_boost_pct']}%")
    if "epic" in info["rarity_boosts"]:
        pct = int((info["rarity_boosts"]["epic"] - 1) * 100)
        lines.append(f"💜 에픽 확률 +{pct}%")
    if "legendary" in info["rarity_boosts"]:
        pct = int((info["rarity_boosts"]["legendary"] - 1) * 100)
        lines.append(f"⭐ 전설 확률 +{pct}%")
    if "daily_shiny" in info["specials"]:
        lines.append(f"🌟 일일 이로치 확정 스폰 1회!")
    if "auto_arcade" in info["specials"]:
        lines.append(f"🎮 매일 자동 아케이드 1시간!")
    return "\n".join(lines) if lines else "🎁 새로운 혜택이 열렸습니다!"
```

---

## 9. 명령어: `방정보`

**그룹 채팅 전용**

```
📊 크립토 라운지 프로필
━━━━━━━━━━━━━━
🏅 레벨: Lv.5 (CXP 1,234/1,500)
📈 오늘 획득: 23/50 CXP
👥 활동 트레이너: 23명
🎯 총 포획수: 1,847마리
✨ 이로치 출현: 12회
━━━━━━━━━━━━━━
🎁 현재 혜택:
  📦 일일 스폰 +2회
  ✨ 이로치 +0.8%
  💜 에픽 +10%
  ⭐ 전설 +5%
  🌟 일일 이로치 확정 스폰
━━━━━━━━━━━━━━
📊 다음 레벨(Lv.6)까지: 266 CXP
```

**구현:** `handlers/group.py`에 `chat_info_handler` 추가

---

## 10. 스폰 시스템 연동 요약

### `spawn_service.py` 수정 포인트

```python
async def schedule_spawns_for_chat(app, chat_id):
    # 1. 기존: base_spawns 계산
    base_spawns = calculate_daily_spawns(member_count)
    chat_mult = await queries.get_spawn_multiplier(chat_id)
    event_mult = await get_spawn_boost()

    # 2. ★ 레벨 보너스 추가
    chat_data = await queries.get_chat_level(chat_id)
    level_info = config.get_chat_level_info(chat_data["cxp"])
    level_bonus = level_info["spawn_bonus"]

    num_spawns = min(SPAWN_MAX_DAILY,
                     max(1, int(base_spawns * chat_mult * event_mult) + level_bonus))

    # 3. ★ 이로치 확정 스폰 인덱스 결정
    shiny_idx = None
    if "daily_shiny" in level_info["specials"] and level_bonus > 0:
        bonus_start = num_spawns - level_bonus
        shiny_idx = random.randint(bonus_start, num_spawns - 1)

    # 4. 스폰 시간 배정 + job 등록
    for i, t in enumerate(spawn_times):
        app.job_queue.run_once(
            execute_spawn, t,
            data={"chat_id": chat_id, "force_shiny": (i == shiny_idx)},
        )
```

### `execute_spawn()` 수정 포인트

```python
# 이로치 판정 시
if data.get("force_shiny"):
    is_shiny = True
else:
    # 기존 판정 + 레벨 보정
    level_info = config.get_chat_level_info(chat_data["cxp"])
    adjusted_rate = base_shiny_rate + level_info["shiny_boost_pct"] / 100
    is_shiny = random.random() < adjusted_rate

# 레어리티 판정 시
if "epic" in level_info["rarity_boosts"]:
    epic_weight *= level_info["rarity_boosts"]["epic"]
if "legendary" in level_info["rarity_boosts"]:
    legendary_weight *= level_info["rarity_boosts"]["legendary"]
```

---

## 11. 자정 리셋 추가

```python
# main.py midnight_reset() 내부에 추가
await queries.reset_daily_cxp()

# Lv.8+ 자동 아케이드 활성화
await _activate_auto_arcades()
```

---

## 구현 순서 (Step-by-Step)

### Step 1: DB 마이그레이션 (30분)
- [ ] `chat_rooms`에 `cxp`, `chat_level`, `cxp_today` 컬럼 추가
- [ ] `chat_cxp_log` 테이블 생성
- [ ] 기존 채팅방들 `chat_level = 1, cxp = 0` 초기화

### Step 2: config + queries (1시간)
- [ ] `config.py`에 `CHAT_LEVEL_TABLE`, CXP 상수, `get_chat_level_info()` 추가
- [ ] `queries.py`에 `add_chat_cxp()`, `get_chat_level()`, `reset_daily_cxp()` 추가

### Step 3: CXP 적립 Hook (1시간)
- [ ] `handlers/group.py` 포획 성공 후 CXP +1
- [ ] `handlers/battle.py` 배틀 완료 후 CXP +2 (그룹 배틀만)
- [ ] `services/trade_service.py` 교환 완료 후 CXP +1
- [ ] `_add_cxp_bg()` 함수 + 레벨업 알림 메시지
- [ ] `midnight_reset`에 `reset_daily_cxp()` 추가

### Step 4: 스폰 보너스 + 이로치 확정 (1시간)
- [ ] `spawn_service.py`에서 레벨별 스폰 +N 적용
- [ ] 이로치 확정 스폰 (force_shiny) 마킹 로직
- [ ] `execute_spawn()`에서 force_shiny 처리
- [ ] 이로치 보정 (+0.2%~+1.8%) 적용
- [ ] 레어리티 보정 (에픽/전설) 적용

### Step 5: 자동 아케이드 Lv.8 (30분)
- [ ] `_activate_auto_arcades()` 함수
- [ ] `midnight_reset`에 연동
- [ ] 활성화 시 채팅방 알림

### Step 6: `방정보` 명령어 (30분)
- [ ] `handlers/group.py`에 `chat_info_handler` 추가
- [ ] `main.py`에 핸들러 등록

---

## 수치 밸런스

### CXP 적립 속도 (활발한 채팅방, 일 ~43 CXP 기준)

| 레벨 | 도달까지 | 누적 기간 | 핵심 해금 |
|------|---------|----------|----------|
| Lv.2 (100) | ~3일 | 3일 | 스폰 +1 |
| Lv.3 (300) | ~5일 | 8일 | 에픽 +10% |
| Lv.4 (600) | ~7일 | 15일 | **✨ 이로치 확정 스폰** |
| Lv.5 (1000) | ~10일 | 25일 | 명예의 전당 |
| Lv.6 (1500) | ~12일 | 37일 | 스폰 +3 |
| Lv.7 (2000) | ~12일 | 49일 | 전설 +10% |
| Lv.8 (3000) | ~24일 | 73일 | **🎮 자동 아케이드** |
| Lv.10 (8000) | ~119일 | ~6개월 | 리더보드 |

**비활발한 채팅방 (일 10 CXP):**
- Lv.4 (이로치 확정) 도달: ~60일 (2달)
- Lv.8 (자동 아케이드) 도달: ~300일 (10달)

→ 활발한 방은 2주 만에 이로치 확정 혜택, 비활발한 방은 2달.

### 이로치 보정 실제 영향

기존 이로치 기본 확률이 X%라고 할 때:
- Lv.2: X% → X+0.2% (미세하지만 체감 시작)
- Lv.5: X% → X+0.8%
- Lv.10: X% → X+2.0%

**이로치 확정 스폰은 별개** — 확률과 무관하게 매일 1마리 확정.
→ 이것이 Lv.4의 진짜 메리트. 확률 보정은 "추가 보너스".

### 자동 아케이드 경제 영향

- 1시간 아케이드 = 60초 간격 = 약 60회 스폰
- Lv.8 도달까지 73일 소요 → 해당 채팅방은 충분히 활발
- 기존 아케이드 티켓 가치 유지 (Lv.8 미만은 여전히 티켓 필요)

---

## 리스크 & 대응

| 리스크 | 대응 |
|--------|------|
| CXP 어뷰징 | 일일 상한 50 + 기존 catch_limits 연동 |
| 이로치 확정이 너무 강함 | Lv.4 도달에 15일 소요 + 일 1회 한정 |
| 자동 아케이드 남용 | Lv.8 도달에 73일 + 일 1시간 한정 |
| 소규모 방 소외 | Lv.1-3 구간 빠르게 통과 (3~8일) |
| 레벨 혜택이 약해 보임 | 이로치 확정 + 아케이드 = 확실한 메리트 |

---

## 명령어 정리

| 명령어 | 위치 | 설명 |
|--------|------|------|
| `방정보` | 그룹 | 채팅방 레벨/CXP/혜택/통계 표시 |

**새 명령어 1개만 추가.** 기존 명령어 수정 없음.

---

## 파일별 수정 목록

| 파일 | 수정 내용 |
|------|----------|
| `config.py` | `CHAT_LEVEL_TABLE`, CXP 상수, `get_chat_level_info()` |
| `database/queries.py` | `add_chat_cxp()`, `get_chat_level()`, `reset_daily_cxp()` |
| `database/schema.py` | `chat_cxp_log` 테이블 |
| `handlers/group.py` | CXP hook (포획/강스), `chat_info_handler`, `_add_cxp_bg()` |
| `handlers/battle.py` | CXP hook (배틀) |
| `services/trade_service.py` | CXP hook (교환) |
| `services/spawn_service.py` | 레벨 스폰 보너스 + 이로치 확정 + 레어리티 보정 |
| `main.py` | 핸들러 등록, `midnight_reset`에 `reset_daily_cxp()` + `_activate_auto_arcades()` |
