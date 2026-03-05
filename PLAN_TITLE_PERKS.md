# 토너먼트 챔피언 칭호 퍽(Perk) 시스템

## Context
토너먼트(22시 대회) 우승 칭호에 실용적 + 과시형 혜택을 부여.
- "초대 챔피언" 삭제 (챔피언 칭호와 중복)
- "토너먼트 챔피언" 칭호에 퍽 추가

## 퍽 내용
| 퍽 | 효과 |
|----|------|
| 밥/놀기 +1 | 일일 밥 4회, 놀기 3회 (이로치 7까지 빠르게) |
| 마스터볼 구매 +1 | 일일 한도 3→4개 |
| 전용 포획 이펙트 | 포획 메시지에 특별 이모지/텍스트 |
| 랭킹 하이라이트 | 랭킹에서 이름 옆 왕관 마크 |
| 프로필 배지 | 상태창에 토너먼트 우승 횟수 표시 |

---

## 구현

### 1. `config.py`

**삭제**: `tournament_first` 칭호

**추가**: 칭호 퍽 설정
```python
TITLE_PERKS = {
    "tournament_champ": {
        "feed_bonus": 1,              # 밥 +1
        "play_bonus": 1,              # 놀기 +1
        "masterball_limit_bonus": 1,  # 마볼 구매 +1
        "catch_effect": "🏆",         # 포획 이펙트
        "ranking_highlight": "👑",    # 랭킹 하이라이트
        "profile_badge": True,        # 상태창 배지
    },
}
```

### 2. 퍽 헬퍼 함수 — `utils/helpers.py`

```python
def get_title_perks(user: dict) -> dict:
    """유저의 장착 칭호에 연결된 퍽 반환. 없으면 빈 dict."""
    if not user:
        return {}
    equipped_title = user.get("title", "")
    # title_id 역매핑: UNLOCKABLE_TITLES에서 name이 일치하는 항목 찾기
    for title_id, (name, emoji, *_) in config.UNLOCKABLE_TITLES.items():
        if name == equipped_title:
            return config.TITLE_PERKS.get(title_id, {})
    return {}
```

### 3. `handlers/dm_nurture.py` — 밥/놀기 제한 수정

**밥 핸들러** (line ~49):
```python
user = await queries.get_user(user_id)
perks = get_title_perks(user)
feed_limit = config.FEED_PER_DAY + perks.get("feed_bonus", 0)
if pokemon["fed_today"] >= feed_limit:
    # "오늘은 이미 밥을 N번 줬습니다!"
```

**놀기 핸들러** (line ~120):
```python
play_limit = config.PLAY_PER_DAY + perks.get("play_bonus", 0)
if pokemon["played_today"] >= play_limit:
    # ...
```

### 4. `handlers/battle.py` — 마스터볼 구매 한도

BP상점 마스터볼 구매 (line ~854):
```python
user = await queries.get_user(user_id)
perks = get_title_perks(user)
mb_limit = config.BP_MASTERBALL_DAILY_LIMIT + perks.get("masterball_limit_bonus", 0)
if bought_today >= mb_limit:
    # "오늘 마스터볼 구매 한도(N개)를 초과"
```

### 5. `services/spawn_service.py` — 전용 포획 이펙트

포획 성공 메시지 (line ~539):
```python
perks = get_title_perks(user_data)
catch_effect = perks.get("catch_effect", "")
# 마스터볼/하이퍼볼 사용 시에는 기존 이펙트 유지, 일반 포획일 때만 챔피언 이펙트 적용
if catch_effect and not winner.get("used_master_ball") and not winner.get("used_hyper_ball"):
    msg = f"{catch_effect} {decorated} — {shiny_label}{pokemon_emoji} {pokemon_name} 포획!"
else:
    # 기존 로직 유지
```

### 6. `handlers/group.py` — 랭킹 하이라이트

ranking_handler (line ~329):
```python
for i, r in enumerate(rankings):
    perks = get_title_perks(r)  # r은 user dict (title, title_emoji 포함)
    highlight = perks.get("ranking_highlight", "")
    decorated = get_decorated_name(...)
    if highlight:
        lines.append(f"{medal} {highlight} {decorated} — {r['caught_count']}/251")
    else:
        lines.append(f"{medal} {decorated} — {r['caught_count']}/251")
```

### 7. `handlers/dm_pokedex.py` — 상태창 배지

status_handler (line ~829):
```python
perks = get_title_perks(user)
if perks.get("profile_badge"):
    stats = await queries.get_title_stats(user_id)
    t_wins = stats.get("tournament_wins", 0) if stats else 0
    if t_wins > 0:
        lines.append(f"🏆 토너먼트 우승: {t_wins}회")
```

### 8. 칭호 장착 시 퍽 안내

`handlers/dm_pokedex.py` — title_callback (line ~796):
```python
perks = config.TITLE_PERKS.get(title_id, {})
if perks:
    perk_lines = []
    if perks.get("feed_bonus"):
        perk_lines.append(f"🍚 밥 +{perks['feed_bonus']}회/일")
    if perks.get("play_bonus"):
        perk_lines.append(f"🎮 놀기 +{perks['play_bonus']}회/일")
    if perks.get("masterball_limit_bonus"):
        perk_lines.append(f"🔮 마볼 구매 +{perks['masterball_limit_bonus']}개/일")
    if perks.get("catch_effect"):
        perk_lines.append(f"{perks['catch_effect']} 전용 포획 이펙트")
    perk_text = "\n".join(perk_lines)
    msg = f"✅ 칭호 장착: 「{emoji} {name}」\n\n🎁 칭호 특전:\n{perk_text}"
```

---

## 수정 파일 요약

| 파일 | 변경 |
|------|------|
| `config.py` | tournament_first 삭제, TITLE_PERKS 추가 |
| `utils/helpers.py` | `get_title_perks()` 함수 추가 |
| `handlers/dm_nurture.py` | 밥/놀기 제한에 퍽 보너스 적용 |
| `handlers/battle.py` | 마볼 구매 한도에 퍽 보너스 적용 |
| `services/spawn_service.py` | 전용 포획 이펙트 |
| `handlers/group.py` | 랭킹 하이라이트 |
| `handlers/dm_pokedex.py` | 상태창 배지 + 칭호 장착 시 퍽 안내 |
