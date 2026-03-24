# 버그 수정 로그

## 2026-03-24: 내포켓몬 진화 버튼 무반응

**증상**: 내포켓몬 상세에서 ⭐ 진화 버튼을 눌러도 아무 반응 없음 (예전부터)

**원인**: `handlers/dm_mypokemon_actions.py` line 137에서 존재하지 않는 함수 호출
```python
# AS-IS (버그)
evo_target = await queries.get_pokemon_master(target_id)

# TO-BE (수정)
evo_target = await queries.get_pokemon(target_id)
```

`queries.get_pokemon_master()`는 존재하지 않는 함수 → `AttributeError` 발생.
하지만 상위 try/except에서 `except Exception: pass`로 에러를 삼키고 있어서 로그도 없고, 유저에게도 아무 피드백 없었음.

**수정**:
1. `get_pokemon_master()` → `get_pokemon()`으로 변경
2. `except Exception: pass` → 에러 로깅 + 유저에게 오류 팝업 표시

**커밋**: `d14b162`
