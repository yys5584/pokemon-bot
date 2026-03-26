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

## 2026-03-25: _register.py 핸들러 import 누락으로 봇 시작 실패

**증상**: 배포 후 봇이 무한 재시작 (restart counter 100+)

**원인**: `_register.py`에서 어뷰징 관련 핸들러 3개를 등록했지만 import를 추가하지 않음
```python
# 등록은 했지만
app.add_handler(MessageHandler(..., abuse_reset_handler))
app.add_handler(MessageHandler(..., abuse_detail_handler))
app.add_handler(MessageHandler(..., abuse_list_handler))

# import에는 없었음 → NameError
```

**교훈**: `_register.py`에 핸들러 등록 시 **반드시 상단 import도 함께 추가**할 것. 배포 전 `python -c "from handlers._register import register_all_handlers"` 로 import 검증 가능.

**커밋**: `7b8b6f0`, `b7a2ca3`
